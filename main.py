from __future__ import annotations

import re
import asyncio
from collections.abc import AsyncGenerator, Iterable
from time import monotonic

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, AtAll, Image, Reply
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.custom_filter import CustomFilter


PLUGIN_TAG = "[xiaozhao_smart_mention]"
EXTRA_DECISION = "xiaozhao_smart_mention_decision"
EXTRA_REASON = "xiaozhao_smart_mention_reason"
EXTRA_MODE = "xiaozhao_smart_mention_mode"

DEFAULT_MENTION_KEYWORDS = ["小昭", "小昭猫娘"]
DEFAULT_ALIASES = DEFAULT_MENTION_KEYWORDS
RUNTIME_ALIASES = list(DEFAULT_MENTION_KEYWORDS)
DEFAULT_REPLY_PATTERNS = [
    r"^(?:{keywords})[,，!！?？\s]*(?:你|妳|您)?(?:在吗|出来|来一下|觉得|认为|看|怎么看|咋看|说说|聊聊|帮|救|听|说|解释|告诉|回答|评价|锐评|分析|查|写|做|能|可以|是不是|为什么|怎么|咋|如何|吗|呢)",
    r"(?:问|请|让|叫|喊)(?:一下)?(?:{keywords})",
    r"(?:{keywords}).*(?:吗|嘛|呢|么|？|\?|你觉得|你看|怎么看|咋看|说说|聊聊|评价|锐评|帮我|帮忙|能不能|可不可以|要不要|怎么|如何|为什么|啥|什么|谁|哪里|哪儿|几点|多少)",
]
DEFAULT_SKIP_PATTERNS = [
    r"(?:{keywords}).*(?:别回|不要回|不用回|别回复|不要回复|不用回复|别理|不用理|不要理)",
]
DEFAULT_ACTIVE_REPLY_CUE_PATTERNS = [
    r"[?？]",
    r"(?:怎么|咋|如何|为什么|为啥|啥|什么|谁|哪里|哪儿|哪个|多少|几点|几|怎么办|咋办)",
    r"(?:能不能|可不可以|有没有|要不要|求助|帮忙|帮我|救命|不会|不懂|卡住|报错|没反应|不回复|没回复)",
    r"(?:配置|设置|插件|模型|机器人|provider|token|冷却|限流|429)",
    r"(?:看法|意见|建议|分析一下|解释一下|总结一下)",
]


def _dedupe(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = str(item).strip()
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns if pattern]


def _as_list(
    value,
    fallback: list[str],
    *,
    split_string: bool = False,
) -> list[str]:
    if isinstance(value, list):
        return _dedupe(str(item) for item in value)
    if isinstance(value, str) and value.strip():
        if split_string:
            return _dedupe(re.split(r"[\n,，、]+", value))
        return _dedupe([value])
    return list(fallback)


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _resolve_mention_keywords(config) -> list[str]:
    mention_keywords = _as_list(
        config.get("mention_keywords"),
        [],
        split_string=True,
    )
    aliases = _as_list(config.get("aliases"), [], split_string=True)

    if (
        aliases
        and aliases != DEFAULT_MENTION_KEYWORDS
        and mention_keywords == DEFAULT_MENTION_KEYWORDS
    ):
        return aliases
    if mention_keywords:
        return mention_keywords
    if aliases:
        return aliases
    return list(DEFAULT_MENTION_KEYWORDS)


def _build_keyword_regex(mention_keywords: Iterable[str]) -> str:
    escaped = [re.escape(item) for item in _dedupe(mention_keywords)]
    return "|".join(sorted(escaped, key=len, reverse=True))


def _compile_keyword_patterns(
    patterns: Iterable[str],
    mention_keywords: Iterable[str],
) -> list[re.Pattern[str]]:
    keyword_regex = _build_keyword_regex(mention_keywords)
    expanded = [
        pattern.replace("{keywords}", keyword_regex)
        for pattern in patterns
        if pattern and keyword_regex
    ]
    return _compile_patterns(expanded)


def _contains_keyword(text: str, mention_keywords: Iterable[str]) -> bool:
    return any(keyword and keyword in text for keyword in mention_keywords)


class MentionAliasFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False

        text = event.get_message_str().strip()
        if not text:
            return False

        return _contains_keyword(text, RUNTIME_ALIASES)


class Main(Star):
    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config or {}
        global RUNTIME_ALIASES
        self.use_llm_judge = bool(self.config.get("use_llm_judge", True))
        self.judge_timeout_sec = float(self.config.get("judge_timeout_sec", 8))
        self.active_reply_enabled = bool(self.config.get("active_reply_enabled", True))
        self.active_reply_cooldown_sec = float(
            self.config.get("active_reply_cooldown_sec", 30),
        )
        self.active_judge_attempt_cooldown_sec = _as_float(
            self.config.get("active_judge_attempt_cooldown_sec"),
            45,
        )
        self.judge_failure_backoff_sec = _as_float(
            self.config.get("judge_failure_backoff_sec"),
            120,
        )
        self.directed_reply_guard_enabled = bool(
            self.config.get("directed_reply_guard_enabled", True),
        )
        self.directed_reply_group_cooldown_sec = _as_float(
            self.config.get("directed_reply_group_cooldown_sec"),
            8,
        )
        self.directed_reply_sender_cooldown_sec = _as_float(
            self.config.get("directed_reply_sender_cooldown_sec"),
            60,
        )
        self.directed_reply_owner_bypass = bool(
            self.config.get("directed_reply_owner_bypass", True),
        )
        self.owner_ids = set(
            _as_list(self.config.get("owner_ids"), [], split_string=True),
        )
        self.mention_keywords = _resolve_mention_keywords(self.config)
        self.aliases = list(self.mention_keywords)
        RUNTIME_ALIASES = list(self.mention_keywords)
        self.reply_patterns = _compile_keyword_patterns(
            _as_list(self.config.get("reply_patterns"), DEFAULT_REPLY_PATTERNS),
            self.mention_keywords,
        )
        self.skip_patterns = _compile_keyword_patterns(
            _as_list(self.config.get("skip_patterns"), DEFAULT_SKIP_PATTERNS),
            self.mention_keywords,
        )
        self.active_reply_cue_patterns = _compile_patterns(
            _as_list(
                self.config.get("active_reply_cue_patterns"),
                DEFAULT_ACTIVE_REPLY_CUE_PATTERNS,
            ),
        )
        self._last_active_reply_at: dict[str, float] = {}
        self._last_active_judge_attempt_at: dict[str, float] = {}
        self._judge_backoff_until: dict[str, float] = {}
        self._last_directed_group_at: dict[str, float] = {}
        self._last_directed_sender_at: dict[str, float] = {}

    async def initialize(self) -> None:
        logger.info(
            "%s loaded: mention_keywords=%s, use_llm_judge=%s, active_reply_enabled=%s, directed_guard=%s",
            PLUGIN_TAG,
            ",".join(self.mention_keywords),
            self.use_llm_judge,
            self.active_reply_enabled,
            self.directed_reply_guard_enabled,
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-100)
    async def directed_reply_guard(self, event: AstrMessageEvent) -> None:
        if not self.directed_reply_guard_enabled:
            return
        if self._is_self_message(event):
            return
        if self.directed_reply_owner_bypass and self._is_owner_message(event):
            return
        if not self._has_native_directed_signal(event):
            return

        allowed, reason = self._consume_directed_reply_slot(event)
        if allowed:
            return

        text = event.get_message_str().strip()
        event.set_extra(EXTRA_DECISION, "SKIP")
        event.set_extra(EXTRA_REASON, reason)
        event.set_extra(EXTRA_MODE, "directed_guard")
        logger.info(
            "%s directed skip: group=%s sender=%s reason=%s text=%s",
            PLUGIN_TAG,
            event.get_group_id(),
            event.get_sender_id(),
            reason,
            _clip(text),
        )
        _stop_event_silently(event)

    @filter.custom_filter(MentionAliasFilter, priority=20)
    async def smart_mention(self, event: AstrMessageEvent) -> None:
        if event.is_at_or_wake_command or self._has_native_directed_signal(event):
            return

        text = event.get_message_str().strip()
        if not text:
            _stop_event_silently(event)
            return

        decision, reason = await self._decide(event, text)

        if decision == "REPLY":
            allowed, guard_reason = self._consume_keyword_reply_slot(event)
            if not allowed:
                event.set_extra(EXTRA_DECISION, "SKIP")
                event.set_extra(EXTRA_REASON, guard_reason)
                event.set_extra(EXTRA_MODE, "mention_guard")
                logger.info(
                    "%s skip: group=%s sender=%s reason=%s text=%s",
                    PLUGIN_TAG,
                    event.get_group_id(),
                    event.get_sender_id(),
                    guard_reason,
                    _clip(text),
                )
                return

            event.set_extra(EXTRA_DECISION, decision)
            event.set_extra(EXTRA_REASON, reason)
            event.set_extra(EXTRA_MODE, "mention")
            event.is_wake = True
            event.is_at_or_wake_command = True
            logger.info(
                "%s reply: group=%s sender=%s reason=%s text=%s",
                PLUGIN_TAG,
                event.get_group_id(),
                event.get_sender_id(),
                reason,
                _clip(text),
            )
            return

        event.set_extra(EXTRA_DECISION, decision)
        event.set_extra(EXTRA_REASON, reason)
        event.set_extra(EXTRA_MODE, "mention")
        logger.info(
            "%s skip: group=%s sender=%s reason=%s text=%s",
            PLUGIN_TAG,
            event.get_group_id(),
            event.get_sender_id(),
            reason,
            _clip(text),
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-20)
    async def smart_active_reply(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[ProviderRequest | None, None]:
        """普通群聊消息的智能主动回复。

        该 handler 不直接把所有群消息变成默认 LLM 请求；只有智能判定为 REPLY 时
        才 yield ProviderRequest，让 AstrBot 用当前小昭人格生成主动回复。
        """
        if not self.active_reply_enabled:
            return
        if event.is_at_or_wake_command or self._has_native_directed_signal(event):
            return
        if event.get_extra(EXTRA_DECISION):
            return
        if self._is_self_message(event):
            return

        text = event.get_message_str().strip()
        if not text:
            return
        if _contains_keyword(text, self.mention_keywords):
            return
        if not self._has_active_reply_cue(text):
            logger.debug("%s active skip: no_active_reply_cue", PLUGIN_TAG)
            return

        cooldown_key = event.unified_msg_origin
        elapsed = monotonic() - self._last_active_reply_at.get(cooldown_key, 0)
        if elapsed < self.active_reply_cooldown_sec:
            logger.debug(
                "%s active skip: cooldown %.1fs/%.1fs",
                PLUGIN_TAG,
                elapsed,
                self.active_reply_cooldown_sec,
            )
            return

        backing_off, reason = self._is_judge_backoff_active(event)
        if backing_off:
            logger.debug("%s active skip: %s", PLUGIN_TAG, reason)
            return

        allowed, reason = self._consume_active_judge_attempt_slot(event)
        if not allowed:
            logger.debug("%s active skip: %s", PLUGIN_TAG, reason)
            return

        decision = await self._active_decide(event, text)
        if decision != "REPLY":
            logger.debug(
                "%s active skip: group=%s sender=%s text=%s",
                PLUGIN_TAG,
                event.get_group_id(),
                event.get_sender_id(),
                _clip(text),
            )
            return

        conversation = await self._get_or_create_conversation(event)
        if conversation is None:
            return

        event.set_extra(EXTRA_DECISION, "REPLY")
        event.set_extra(EXTRA_REASON, "active_llm_judge")
        event.set_extra(EXTRA_MODE, "active_reply")
        self._last_active_reply_at[cooldown_key] = monotonic()

        logger.info(
            "%s active reply: group=%s sender=%s text=%s",
            PLUGIN_TAG,
            event.get_group_id(),
            event.get_sender_id(),
            _clip(text),
        )

        yield event.request_llm(
            prompt=text,
            session_id=event.session_id,
            image_urls=await self._collect_image_urls(event),
            conversation=conversation,
        )
        _stop_event_silently(event)

    @filter.on_llm_request(priority=80)
    async def decorate_llm_request(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ) -> None:
        if event.get_extra(EXTRA_DECISION) != "REPLY":
            return

        sender_name = event.get_sender_name() or "未知昵称"
        sender_id = event.get_sender_id() or "未知ID"
        reason = event.get_extra(EXTRA_REASON, "smart_mention")
        mode = event.get_extra(EXTRA_MODE, "mention")
        trigger = (
            "群聊智能主动回复"
            if mode == "active_reply"
            else f"群聊提到{self._mention_keyword_label()}"
        )
        note = (
            "<system_reminder>"
            f"本轮消息触发方式: {trigger}。"
            f"判断原因: {reason}。"
            f"当前发言人昵称/ID: {sender_name}/{sender_id}。"
            "请自然回应当前场景；"
            "不要解释触发机制，不要特意强调对方是不是主人。"
            "</system_reminder>"
        )
        req.system_prompt = (req.system_prompt or "") + "\n" + note

    def _has_native_directed_signal(self, event: AstrMessageEvent) -> bool:
        self_id = str(event.get_self_id())
        for comp in event.get_messages():
            if isinstance(comp, At) and str(comp.qq) in (self_id, "all"):
                return True
            if isinstance(comp, AtAll):
                return True
            if isinstance(comp, Reply) and str(getattr(comp, "sender_id", "")) == self_id:
                return True
        return False

    def _is_self_message(self, event: AstrMessageEvent) -> bool:
        return bool(event.get_self_id()) and str(event.get_sender_id()) == str(
            event.get_self_id(),
        )

    def _is_owner_message(self, event: AstrMessageEvent) -> bool:
        return str(event.get_sender_id()) in self.owner_ids

    def _consume_directed_reply_slot(
        self,
        event: AstrMessageEvent,
        *,
        now: float | None = None,
    ) -> tuple[bool, str]:
        now = monotonic() if now is None else now
        group_key = self._directed_group_key(event)
        sender_key = self._directed_sender_key(event)

        group_elapsed = now - self._last_directed_group_at.get(group_key, 0)
        if (
            self.directed_reply_group_cooldown_sec > 0
            and group_elapsed < self.directed_reply_group_cooldown_sec
        ):
            return (
                False,
                f"group_cooldown:{group_elapsed:.1f}/{self.directed_reply_group_cooldown_sec:.1f}s",
            )

        sender_elapsed = now - self._last_directed_sender_at.get(sender_key, 0)
        if (
            self.directed_reply_sender_cooldown_sec > 0
            and sender_elapsed < self.directed_reply_sender_cooldown_sec
        ):
            return (
                False,
                f"sender_cooldown:{sender_elapsed:.1f}/{self.directed_reply_sender_cooldown_sec:.1f}s",
            )

        self._last_directed_group_at[group_key] = now
        self._last_directed_sender_at[sender_key] = now
        return True, "allowed"

    def _consume_keyword_reply_slot(
        self,
        event: AstrMessageEvent,
    ) -> tuple[bool, str]:
        if not self.directed_reply_guard_enabled:
            return True, "allowed"
        if self.directed_reply_owner_bypass and self._is_owner_message(event):
            return True, "owner_bypass"
        return self._consume_directed_reply_slot(event)

    def _directed_group_key(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:bot:{event.get_self_id()}"

    def _directed_sender_key(self, event: AstrMessageEvent) -> str:
        return f"{self._directed_group_key(event)}:sender:{event.get_sender_id()}"

    def _is_judge_backoff_active(
        self,
        event: AstrMessageEvent,
        *,
        now: float | None = None,
    ) -> tuple[bool, str]:
        now = monotonic() if now is None else now
        key = self._judge_backoff_key(event)
        until = self._judge_backoff_until.get(key, 0)
        if now < until:
            return True, f"judge_backoff:{until - now:.1f}s"
        return False, "allowed"

    def _record_judge_failure(
        self,
        event: AstrMessageEvent,
        mode: str,
        exc: BaseException,
        *,
        now: float | None = None,
    ) -> None:
        if self.judge_failure_backoff_sec <= 0:
            return
        now = monotonic() if now is None else now
        key = self._judge_backoff_key(event)
        self._judge_backoff_until[key] = now + self.judge_failure_backoff_sec
        logger.debug(
            "%s %s judge backoff %.1fs after %s",
            PLUGIN_TAG,
            mode,
            self.judge_failure_backoff_sec,
            _format_exception(exc),
        )

    def _consume_active_judge_attempt_slot(
        self,
        event: AstrMessageEvent,
        *,
        now: float | None = None,
    ) -> tuple[bool, str]:
        now = monotonic() if now is None else now
        key = self._active_judge_attempt_key(event)
        elapsed = now - self._last_active_judge_attempt_at.get(key, 0)
        if (
            self.active_judge_attempt_cooldown_sec > 0
            and elapsed < self.active_judge_attempt_cooldown_sec
        ):
            return (
                False,
                f"active_judge_attempt_cooldown:{elapsed:.1f}/{self.active_judge_attempt_cooldown_sec:.1f}s",
            )

        self._last_active_judge_attempt_at[key] = now
        return True, "allowed"

    def _judge_backoff_key(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:bot:{event.get_self_id()}"

    def _active_judge_attempt_key(self, event: AstrMessageEvent) -> str:
        return self._judge_backoff_key(event)

    def _has_active_reply_cue(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.active_reply_cue_patterns)

    async def _decide(self, event: AstrMessageEvent, text: str) -> tuple[str, str]:
        for pattern in self.skip_patterns:
            if pattern.search(text):
                return "SKIP", f"skip_pattern:{pattern.pattern}"

        for pattern in self.reply_patterns:
            if pattern.search(text):
                return "REPLY", f"reply_pattern:{pattern.pattern}"

        if not self.use_llm_judge:
            return "SKIP", "llm_judge_disabled"

        backing_off, reason = self._is_judge_backoff_active(event)
        if backing_off:
            return "SKIP", reason

        llm_decision = await self._llm_decide(event, text)
        if llm_decision in {"REPLY", "SKIP"}:
            return llm_decision, "llm_judge"

        return "SKIP", "llm_judge_unavailable"

    async def _llm_decide(self, event: AstrMessageEvent, text: str) -> str | None:
        provider = self.context.get_using_provider(event.unified_msg_origin)
        if not provider:
            return None

        bot_label = self._primary_mention_keyword()
        keyword_label = self._mention_keyword_label()
        recent_context = self._recent_group_context(event)
        context_block = (
            f"最近群聊上下文:\n{recent_context}\n\n" if recent_context else ""
        )
        prompt = (
            f"你是群聊机器人“{bot_label}”的回复触发判定器。"
            f"请判断当前群聊消息虽然提到了触发关键词 {keyword_label}，是否需要机器人回复。\n"
            f"只在以下情况输出 REPLY：用户直接叫{bot_label}或这些触发关键词、向机器人提问、请求机器人帮忙、需要机器人澄清或回应。\n"
            f"以下情况输出 SKIP：只是旁观讨论、复述/评价{bot_label}之前的话、开玩笑但没有让机器人接话、明确说不用回复。\n"
            "只能输出 REPLY 或 SKIP，不要输出其他内容。\n\n"
            f"群号: {event.get_group_id()}\n"
            f"发言人ID: {event.get_sender_id()}\n"
            f"发言人昵称: {event.get_sender_name()}\n"
            f"{context_block}"
            f"消息: {text}\n"
        )

        try:
            resp = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt="你只输出 REPLY 或 SKIP。",
                    contexts=[],
                    request_max_retries=1,
                ),
                timeout=self.judge_timeout_sec,
            )
        except Exception as exc:
            self._record_judge_failure(event, "llm", exc)
            logger.warning(
                "%s llm judge failed: %s",
                PLUGIN_TAG,
                _format_exception(exc),
            )
            return None

        answer = (getattr(resp, "completion_text", "") or "").strip().upper()
        if "REPLY" in answer and "SKIP" not in answer:
            return "REPLY"
        if "SKIP" in answer and "REPLY" not in answer:
            return "SKIP"
        return None

    async def _active_decide(self, event: AstrMessageEvent, text: str) -> str | None:
        provider = self.context.get_using_provider(event.unified_msg_origin)
        if not provider:
            return None

        bot_label = self._primary_mention_keyword()
        recent_context = self._recent_group_context(event)
        context_block = (
            f"最近群聊上下文:\n{recent_context}\n\n" if recent_context else ""
        )
        prompt = (
            f"你是群聊机器人“{bot_label}”的主动回复判定器。"
            f"请判断{bot_label}是否应该在没有被点名、没有被@的情况下主动接一句话。\n"
            "只在以下情况输出 REPLY：群里有人提出开放问题或求助、讨论明显卡住、"
            f"有人需要解释/总结/配置帮助、有人邀请大家发表看法、当前话题非常适合{bot_label}自然补充。\n"
            "以下情况输出 SKIP：普通闲聊、短表情/口头禅、广告或刷屏、两个人正在互相对话、"
            "只是陈述近况、接话会显得突兀、刚刚已经主动回复过类似话题。\n"
            f"要求：宁可少回，不要抢话；只有你认为{bot_label}此刻自然插话会有帮助才 REPLY。\n"
            "只能输出 REPLY 或 SKIP，不要输出其他内容。\n\n"
            f"群号: {event.get_group_id()}\n"
            f"发言人ID: {event.get_sender_id()}\n"
            f"发言人昵称: {event.get_sender_name()}\n"
            f"{context_block}"
            f"当前消息: {text}\n"
        )

        try:
            resp = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt="你只输出 REPLY 或 SKIP。",
                    contexts=[],
                    request_max_retries=1,
                ),
                timeout=self.judge_timeout_sec,
            )
        except Exception as exc:
            self._record_judge_failure(event, "active", exc)
            logger.warning(
                "%s active judge failed: %s",
                PLUGIN_TAG,
                _format_exception(exc),
            )
            return None

        answer = (getattr(resp, "completion_text", "") or "").strip().upper()
        if "REPLY" in answer and "SKIP" not in answer:
            return "REPLY"
        if "SKIP" in answer and "REPLY" not in answer:
            return "SKIP"
        return None

    async def _get_or_create_conversation(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        try:
            cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not cid:
                cid = await self.context.conversation_manager.new_conversation(
                    umo,
                    event.get_platform_id(),
                )
            conversation = await self.context.conversation_manager.get_conversation(
                umo,
                cid,
            )
            if conversation is None:
                cid = await self.context.conversation_manager.new_conversation(
                    umo,
                    event.get_platform_id(),
                )
                conversation = await self.context.conversation_manager.get_conversation(
                    umo,
                    cid,
                )
            return conversation
        except Exception as exc:
            logger.warning("%s create conversation failed: %s", PLUGIN_TAG, exc)
            return None

    async def _collect_image_urls(self, event: AstrMessageEvent) -> list[str]:
        image_urls: list[str] = []
        for comp in event.get_messages():
            if not isinstance(comp, Image):
                continue
            try:
                image_urls.append(await comp.convert_to_file_path())
            except Exception as exc:
                logger.warning("%s image convert failed: %s", PLUGIN_TAG, exc)
        return image_urls

    def _recent_group_context(self, event: AstrMessageEvent, limit: int = 8) -> str:
        try:
            metadata = self.context.get_registered_star("astrbot")
            star_cls = getattr(metadata, "star_cls", None) if metadata else None
            group_chat_context = getattr(star_cls, "group_chat_context", None)
            raw_records = getattr(group_chat_context, "raw_records", {})
            records = raw_records.get(event.unified_msg_origin)
            if not records:
                return ""
            return "\n".join(list(records)[-limit:])
        except Exception as exc:
            logger.debug("%s read group context failed: %s", PLUGIN_TAG, exc)
            return ""

    def _primary_mention_keyword(self) -> str:
        if self.mention_keywords:
            return self.mention_keywords[0]
        return DEFAULT_MENTION_KEYWORDS[0]

    def _mention_keyword_label(self) -> str:
        keywords = self.mention_keywords or DEFAULT_MENTION_KEYWORDS
        return "、".join(f"“{keyword}”" for keyword in keywords)


def _clip(text: str, limit: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _format_exception(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def _stop_event_silently(event: AstrMessageEvent) -> None:
    if hasattr(event, "_force_stopped"):
        event._force_stopped = True
        return
    event.stop_event()
