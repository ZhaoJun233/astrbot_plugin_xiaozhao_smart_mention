from __future__ import annotations

import asyncio
import json
import random
import re
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator, Iterable
from time import monotonic

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, AtAll, Image, Plain, Reply
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.custom_filter import CustomFilter


PLUGIN_TAG = "[xiaozhao_smart_mention]"
EXTRA_DECISION = "xiaozhao_smart_mention_decision"
EXTRA_REASON = "xiaozhao_smart_mention_reason"
EXTRA_MODE = "xiaozhao_smart_mention_mode"
ACTION_OUTPUT_KEYWORDS = (
    "动作",
    "舞台",
    "旁白",
    "耳朵",
    "猫耳",
    "尾巴",
    "爪",
    "爪爪",
    "歪头",
    "歪着头",
    "低头",
    "抬头",
    "点头",
    "摇头",
    "眼睛",
    "眼神",
    "看着",
    "看向",
    "眨眼",
    "眨眨眼",
    "挠",
    "捂",
    "拍了拍",
    "后退",
    "跳到",
    "探头",
    "缩了缩",
    "蹭",
    "竖起",
    "抖了抖",
    "晃了晃",
    "摆动",
    "炸毛",
    "脸红",
    "清了清嗓子",
)
ACTION_PARENS_RE = re.compile(r"[（(]([^（）()]{1,120})[）)]")
ACTION_MARKDOWN_RE = re.compile(r"(?<!\*)\*([^*\n]{1,120})\*(?!\*)")
MARKDOWN_EMPHASIS_RE = re.compile(r"(?<!\*)\*{1,2}([^*\n]{1,240}?)\*{1,2}(?!\*)")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(?P<title>[^\n]{1,40})\s*(?:\n+|$)")
CHAT_HEADING_PREFIX_RE = re.compile(
    r"^\s*(?P<title>[^。\n！？!?]{1,30}(?:评价|看法|分析|总结|回复|说明|建议|吐槽|结论|回答|判断))[:：]?\s*",
)
CHAT_BOLD_HEADING_PREFIX_RE = re.compile(r"^\s*\*{1,2}(?P<title>[^*\n]{1,40}?)\*{1,2}\s*")
CHAT_SENTENCE_RE = re.compile(r"[^。！？!?…~～]+[。！？!?…~～]+(?:[❤️❤💕💖✨~～]*)|[^。！？!?…~～]+$")
ISOLATED_PUNCTUATION_RE = re.compile(r"^[。！？!?，,、；;：:…~～—\-]+$")
STRUCTURED_REPLY_MARKERS = (
    "```",
    "`",
    "\n- ",
    "\n1.",
    "\n2.",
    "|",
    "http://",
    "https://",
    "D:\\",
    "/AstrBot/",
)
TECHNICAL_REPLY_KEYWORDS = (
    "配置",
    "路径",
    "命令",
    "日志",
    "插件",
    "报错",
    "验证",
    "action_output_enabled",
    "natural_chat_style_enabled",
    "Traceback",
    "Exception",
)
SEGMENT_UNSUPPORTED_PLATFORMS = {
    "qq_official_webhook",
    "weixin_official_account",
    "dingtalk",
    "webchat",
}
SEGMENT_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

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
DEFAULT_FOLLOWUP_REPLY_CUE_PATTERNS = [
    r"[?？]",
    r"(?:告诉我|直接说|直说|回答|继续|接着|就行|没事|好奇|问问)",
    r"(?:你觉得|你认为|你猜|猜一下|选一个|到底|所以|那你|那么)",
    r"(?:不是|不对|我是说|我问的是|别绕|别跑题|刚才|上一句)",
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


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _looks_like_character_action(text: str) -> bool:
    body = text.strip()
    if not body:
        return False
    return any(keyword in body for keyword in ACTION_OUTPUT_KEYWORDS)


def _strip_character_action_output(text: str) -> str:
    if not text:
        return text

    def replace_action(match: re.Match[str]) -> str:
        body = match.group(1)
        if _looks_like_character_action(body):
            return ""
        return match.group(0)

    cleaned = ACTION_PARENS_RE.sub(replace_action, text)
    cleaned = ACTION_MARKDOWN_RE.sub(replace_action, cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_chatty_heading_output(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped or _is_structured_or_technical_reply(stripped):
        return stripped

    markdown_match = MARKDOWN_HEADING_RE.match(stripped)
    if markdown_match:
        remainder = stripped[markdown_match.end() :].strip()
        if remainder and not _is_structured_or_technical_reply(remainder):
            return remainder

    lines = stripped.splitlines()
    if len(lines) >= 2:
        first = _strip_markdown_emphasis(lines[0]).strip()
        remainder = "\n".join(lines[1:]).strip()
        if _looks_like_chatty_heading(first) and remainder and not _is_structured_or_technical_reply(remainder):
            return remainder

    bold_match = CHAT_BOLD_HEADING_PREFIX_RE.match(stripped)
    if bold_match and _looks_like_chatty_heading(bold_match.group("title")):
        remainder = stripped[bold_match.end() :].strip()
        if remainder and not _is_structured_or_technical_reply(remainder):
            return remainder

    prefix_match = CHAT_HEADING_PREFIX_RE.match(stripped)
    if prefix_match and _looks_like_chatty_heading(prefix_match.group("title")):
        remainder = stripped[prefix_match.end() :].strip()
        if remainder and not _is_structured_or_technical_reply(remainder):
            return remainder

    return stripped


def _looks_like_chatty_heading(title: str) -> bool:
    clean = _strip_markdown_emphasis(title).strip(" #：:")
    if not clean or len(clean) > 30:
        return False
    if any(keyword in clean for keyword in ("配置", "路径", "命令", "日志", "报错", "验证", "代码")):
        return False
    if re.search(r"[。！？!?\n`|]", clean):
        return False
    return bool(
        clean.startswith(("小昭", "回复", "回答", "总结", "评价", "看法", "建议", "分析", "结论", "吐槽"))
        or clean.endswith(("评价", "看法", "建议", "分析", "总结", "回复", "回答", "结论", "吐槽"))
    )


def _format_natural_chat_paragraphs(text: str, max_paragraphs: int = 3) -> str:
    if not text:
        return text

    max_paragraphs = max(1, max_paragraphs)
    stripped = text.strip()
    if "\n\n" in stripped:
        return "\n\n".join(
            _format_natural_chat_paragraphs(part, max_paragraphs)
            for part in stripped.split("\n\n")
        )
    if len(stripped) < 45:
        return stripped
    if any(marker in stripped for marker in STRUCTURED_REPLY_MARKERS):
        return stripped
    if any(keyword in stripped for keyword in TECHNICAL_REPLY_KEYWORDS):
        return stripped

    sentences = [
        match.group(0).strip()
        for match in CHAT_SENTENCE_RE.finditer(stripped)
        if match.group(0).strip()
    ]
    if len(sentences) >= 2 and len(sentences[0]) <= 4 and sentences[0].endswith("…"):
        sentences = [sentences[0] + sentences[1], *sentences[2:]]
    if len(sentences) < 2:
        return stripped

    paragraphs: list[str] = []
    current = ""
    for index, sentence in enumerate(sentences):
        remaining_sentences = len(sentences) - index
        remaining_slots = max_paragraphs - len(paragraphs)
        if not current:
            current = sentence
            continue
        if not paragraphs and len(current) <= 18 and len(sentences) >= 3:
            paragraphs.append(current)
            current = sentence
            continue
        if len(current) < 34 and remaining_sentences >= remaining_slots:
            current += sentence
            continue
        paragraphs.append(current)
        current = sentence
    if current:
        paragraphs.append(current)

    if len(paragraphs) > max_paragraphs:
        paragraphs = paragraphs[: max_paragraphs - 1] + ["".join(paragraphs[max_paragraphs - 1 :])]

    return "\n\n".join(paragraphs)


def _is_structured_or_technical_reply(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if any(marker in stripped for marker in STRUCTURED_REPLY_MARKERS):
        return True
    if re.search(r"(^|\n)\s*(?:[-*]|\d+[.、])\s+", stripped):
        return True
    if re.search(r"(Traceback|Exception|Error:|\[[A-Z]+\]|\w+Error\b)", stripped):
        return True
    if re.search(r"(?m)^\s*(?:python|pip|docker|git|npm|pnpm|yarn|cd|cat|tail)\s+", stripped):
        return True
    if (
        any(keyword in stripped for keyword in TECHNICAL_REPLY_KEYWORDS)
        and ("\n" in stripped or ":" in stripped or "：" in stripped)
        and re.search(r"(配置|路径|命令|日志|报错|验证).{0,12}[:：]", stripped)
    ):
        return True
    return False


def _is_technical_or_code_reply(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if any(marker in stripped for marker in ("```", "`", "http://", "https://", "D:\\", "/AstrBot/")):
        return True
    if "|" in stripped and "\n" in stripped:
        return True
    if re.search(r"(Traceback|Exception|Error:|\[[A-Z]+\]|\w+Error\b)", stripped):
        return True
    if re.search(r"(?m)^\s*(?:python|pip|docker|git|npm|pnpm|yarn|cd|cat|tail)\s+", stripped):
        return True
    if any(keyword in stripped for keyword in TECHNICAL_REPLY_KEYWORDS):
        return True
    return False


def _looks_like_casual_numbered_list(text: str) -> bool:
    stripped = text.strip()
    if _is_technical_or_code_reply(stripped):
        return False
    numbered_items = re.findall(r"(?m)^\s*\d+[.、]\s+", stripped)
    if len(numbered_items) < 2:
        return False
    return not re.search(r"(?m)^\s*(?:[-*]|\d+[.、])\s+`", stripped)


def _natural_local_segments(text: str, max_segments: int) -> list[str]:
    max_segments = max(1, max_segments)
    target_segments = _natural_segment_target_limit(text, max_segments)
    formatted = _format_natural_chat_paragraphs(text, target_segments)
    segments = [
        segment.strip()
        for segment in re.split(r"\n{2,}", formatted)
        if segment.strip()
    ]
    if not segments and text.strip():
        segments = [text.strip()]
    segments = _merge_chat_segments_to_limit(segments, target_segments)
    if len(segments) > max_segments:
        segments = segments[: max_segments - 1] + ["".join(segments[max_segments - 1 :])]
    return segments


def _casual_numbered_list_segments(text: str, max_segments: int) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n{2,}", text.strip()) if part.strip()]
    if len(parts) < 2:
        return _natural_local_segments(text, max_segments)
    return _merge_chat_segments_to_limit(parts, _natural_segment_target_limit(text, max_segments))


def _natural_segment_target_limit(text: str, hard_limit: int) -> int:
    hard_limit = max(1, hard_limit)
    if hard_limit <= 3:
        return hard_limit

    compact_len = len(_normalise_segment_text(text))
    if compact_len < 260:
        target = 3
    elif compact_len < 480:
        target = 4
    else:
        target = 5
    return min(hard_limit, target)


def _merge_chat_segments_to_limit(segments: list[str], limit: int) -> list[str]:
    limit = max(1, limit)
    merged = _absorb_isolated_punctuation_segments(segments)
    while len(merged) > limit:
        candidate_indexes = range(1, len(merged) - 1) if len(merged) > 2 and len(merged[0]) <= 18 else range(len(merged) - 1)
        pair_index = min(candidate_indexes, key=lambda index: len(merged[index]) + len(merged[index + 1]))
        merged[pair_index : pair_index + 2] = [
            merged[pair_index] + merged[pair_index + 1],
        ]
    return merged


def _absorb_isolated_punctuation_segments(segments: list[str]) -> list[str]:
    merged: list[str] = []
    for raw_segment in segments:
        segment = raw_segment.strip()
        if not segment:
            continue
        if ISOLATED_PUNCTUATION_RE.fullmatch(segment):
            if merged:
                merged[-1] += segment
            else:
                merged.append(segment)
            continue
        if merged and ISOLATED_PUNCTUATION_RE.fullmatch(merged[-1]):
            merged[-1] += segment
            continue
        merged.append(segment)
    return merged


def _extract_segment_json(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    candidates = [stripped]
    match = SEGMENT_JSON_RE.search(stripped)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _normalise_model_segments(original: str, raw: str, max_segments: int) -> list[str] | None:
    data = _extract_segment_json(raw)
    if not data:
        return None
    should_split = data.get("split", True)
    if should_split is False:
        return []
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        return None
    segments = _dedupe(
        str(segment).strip()
        for segment in raw_segments
        if isinstance(segment, str) and segment.strip()
    )
    segments = _absorb_isolated_punctuation_segments(segments)
    if not _are_usable_segments(original, segments, max_segments):
        return None
    target_segments = _natural_segment_target_limit(original, max_segments)
    segments = _merge_chat_segments_to_limit(segments, target_segments)
    if not _are_usable_segments(original, segments, max_segments):
        return None
    return segments


def _are_usable_segments(original: str, segments: list[str], max_segments: int) -> bool:
    if len(segments) < 2 or len(segments) > max(1, max_segments):
        return False
    joined = "".join(segments)
    if _normalise_segment_text(joined) != _normalise_segment_text(original):
        return False
    if len(joined) > max(len(original) * 2, len(original) + 80):
        return False
    if any(segment.lower().startswith(("整理后的", "以下是", "好的", "可以，")) for segment in segments):
        return False
    return True


def _normalise_segment_text(text: str) -> str:
    text = _strip_markdown_emphasis(text or "")
    text = _strip_chatty_heading_output(text)
    return re.sub(r"\s+", "", text)


def _strip_markdown_emphasis(text: str) -> str:
    previous = None
    current = text
    while previous != current:
        previous = current
        current = MARKDOWN_EMPHASIS_RE.sub(r"\1", current)
    return current


def _normalise_chat_completions_url(api_base: str) -> str:
    base = api_base.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _extract_openai_completion_text(body: dict) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            return str(content)
    text = first.get("text")
    if text is not None:
        return str(text)
    return ""


async def _post_openai_chat_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str,
    timeout: float,
    temperature: float = 0,
) -> str:
    url = _normalise_chat_completions_url(api_base)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    def request() -> str:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        body = json.loads(raw)
        if not isinstance(body, dict):
            return ""
        return _extract_openai_completion_text(body).strip()

    return await asyncio.to_thread(request)


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
        self.custom_ai_enabled = bool(self.config.get("custom_ai_enabled", False))
        self.custom_ai_api_base = str(self.config.get("custom_ai_api_base") or "").strip()
        self.custom_ai_api_key = str(self.config.get("custom_ai_api_key") or "").strip()
        self.custom_ai_model = str(self.config.get("custom_ai_model") or "").strip()
        self.active_reply_enabled = bool(self.config.get("active_reply_enabled", True))
        self.active_reply_cooldown_sec = float(
            self.config.get("active_reply_cooldown_sec", 30),
        )
        self.natural_chat_style_enabled = bool(
            self.config.get("natural_chat_style_enabled", True),
        )
        self.smart_segment_enabled = bool(
            self.config.get("smart_segment_enabled", True),
        )
        self.smart_segment_use_model = bool(
            self.config.get("smart_segment_use_model", True),
        )
        self.natural_rewrite_use_model = bool(
            self.config.get("natural_rewrite_use_model", False),
        )
        self.natural_rewrite_timeout_sec = max(
            0.1,
            _as_float(self.config.get("natural_rewrite_timeout_sec"), 1.2),
        )
        self.smart_segment_model_timeout_sec = max(
            0.1,
            _as_float(self.config.get("smart_segment_model_timeout_sec"), 2.0),
        )
        self.smart_segment_respect_astrbot = bool(
            self.config.get("smart_segment_respect_astrbot", True),
        )
        self.action_output_enabled = bool(
            self.config.get("action_output_enabled", False),
        )
        self.natural_chat_max_sentences = max(
            1,
            _as_int(self.config.get("natural_chat_max_sentences"), 3),
        )
        self.smart_segment_interval_sec = max(
            0.0,
            _as_float(self.config.get("smart_segment_interval_sec"), 0.8),
        )
        self.followup_reply_window_sec = _as_float(
            self.config.get("followup_reply_window_sec"),
            180,
        )
        self.followup_llm_judge_enabled = bool(
            self.config.get("followup_llm_judge_enabled", True),
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
        self.followup_reply_cue_patterns = _compile_patterns(
            _as_list(
                self.config.get("followup_reply_cue_patterns"),
                DEFAULT_FOLLOWUP_REPLY_CUE_PATTERNS,
            ),
        )
        self._last_active_reply_at: dict[str, float] = {}
        self._last_active_judge_attempt_at: dict[str, float] = {}
        self._judge_backoff_until: dict[str, float] = {}
        self._last_directed_group_at: dict[str, float] = {}
        self._last_directed_sender_at: dict[str, float] = {}
        self._last_followup_target_at: dict[str, float] = {}

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
            self._record_followup_target(event)
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
            self._record_followup_target(event)
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
        followup_allowed, followup_reason = self._recent_followup_reply_reason(
            event,
            text,
        )
        if (
            not followup_allowed
            and followup_reason == "no_followup_reply_cue"
            and self.followup_llm_judge_enabled
        ):
            followup_decision = await self._followup_decide(event, text)
            if followup_decision == "REPLY":
                followup_allowed = True
                followup_reason = self._recent_followup_reply_reason(
                    event,
                    text,
                    require_cue=False,
                    reason_prefix="followup_llm_judge",
                )[1]
        if followup_allowed:
            cooling_down, cooldown_reason = self._is_active_reply_cooldown_active(event)
            if cooling_down:
                logger.debug("%s active skip: %s", PLUGIN_TAG, cooldown_reason)
                return
            request = await self._build_active_reply_request(
                event,
                text,
                followup_reason,
            )
            if request is None:
                return
            yield request
            _stop_event_silently(event)
            return
        if not self._has_active_reply_cue(text):
            logger.debug("%s active skip: no_active_reply_cue", PLUGIN_TAG)
            return

        cooling_down, cooldown_reason = self._is_active_reply_cooldown_active(event)
        if cooling_down:
            logger.debug("%s active skip: %s", PLUGIN_TAG, cooldown_reason)
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

        request = await self._build_active_reply_request(
            event,
            text,
            "active_llm_judge",
        )
        if request is None:
            return

        yield request
        _stop_event_silently(event)

    async def _build_active_reply_request(
        self,
        event: AstrMessageEvent,
        text: str,
        reason: str,
    ) -> ProviderRequest | None:
        conversation = await self._get_or_create_conversation(event)
        if conversation is None:
            return None

        cooldown_key = event.unified_msg_origin
        event.set_extra(EXTRA_DECISION, "REPLY")
        event.set_extra(EXTRA_REASON, reason)
        event.set_extra(EXTRA_MODE, "active_reply")
        self._last_active_reply_at[cooldown_key] = monotonic()
        self._record_followup_target(event)

        logger.info(
            "%s active reply: group=%s sender=%s reason=%s text=%s",
            PLUGIN_TAG,
            event.get_group_id(),
            event.get_sender_id(),
            reason,
            _clip(text),
        )

        return event.request_llm(
            prompt=text,
            session_id=event.session_id,
            image_urls=await self._collect_image_urls(event),
            conversation=conversation,
        )

    @filter.on_llm_request(priority=80)
    async def decorate_llm_request(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ) -> None:
        is_smart_reply = event.get_extra(EXTRA_DECISION) == "REPLY"
        is_native_directed = self._has_native_directed_signal(event)
        if not is_smart_reply and not is_native_directed and not self.natural_chat_style_enabled:
            return

        if is_smart_reply or is_native_directed:
            self._remove_direct_send_tool(req)

        sender_name = event.get_sender_name() or "未知昵称"
        sender_id = event.get_sender_id() or "未知ID"
        reason = event.get_extra(
            EXTRA_REASON,
            "smart_mention" if is_smart_reply else "native_directed",
        )
        mode = event.get_extra(
            EXTRA_MODE,
            "mention" if is_smart_reply else "native_directed",
        )
        trigger = (
            "群聊智能主动回复"
            if mode == "active_reply"
            else f"群聊提到{self._mention_keyword_label()}"
        )

        if is_smart_reply or is_native_directed:
            note_body = (
                f"本轮消息触发方式: {trigger}。"
                f"判断原因: {reason}。"
                f"当前发言人昵称/ID: {sender_name}/{sender_id}。"
                "请自然回应当前场景；"
                "不要解释触发机制，不要特意强调对方是不是主人。"
                f"{self._natural_chat_style_reminder(mode)}"
            )
        else:
            note_body = (
                f"当前发言人昵称/ID: {sender_name}/{sender_id}。"
                "请自然回应当前场景；不要主动说明内部规则。"
                f"{self._natural_chat_style_reminder('plain_llm')}"
            )

        note = f"<system_reminder>{note_body}</system_reminder>"
        req.system_prompt = (req.system_prompt or "") + "\n" + note

    def _natural_chat_style_reminder(self, mode: str) -> str:
        if not self.natural_chat_style_enabled:
            return ""

        reminder = (
            "按实时群聊的自然对话来回：日常接话按语气、停顿和信息密度自行判断是否拆成短段，"
            f"确实需要分段时最多 {self.natural_chat_max_sentences} 个很短的聊天段落/短句，"
            "不要为了凑数量而拆分；像真人顺手回几句，不要写成长篇正式问答。"
            "遇到列表、步骤、总结、配置说明时，收束成一段紧凑的结构化回答。"
            "日常聊天不要写标题、小标题、加粗标题或 Markdown 报告格式。"
            "不要每句都抢答，只在当前话题需要时简短接话。"
        )
        if not self.action_output_enabled:
            reminder += (
                "不要输出括号动作描写、舞台旁白或身体动作描述，"
                "例如耳朵、尾巴、爪爪、歪头、捂嘴、后退等动作。"
            )
        if mode == "active_reply":
            reminder += "本轮是主动回复，更要轻量接话、不抢话。"
        return reminder

    @filter.on_llm_response(priority=80)
    async def clean_llm_response_actions(self, event: AstrMessageEvent, resp) -> None:
        if self.action_output_enabled:
            return

        text = getattr(resp, "completion_text", "") or ""
        cleaned = _strip_character_action_output(text)
        if self.natural_chat_style_enabled:
            cleaned = _strip_chatty_heading_output(cleaned)
        if self.natural_chat_style_enabled and self.natural_rewrite_use_model:
            cleaned = await self._rewrite_reply_naturally(event, cleaned)
        elif self.natural_chat_style_enabled:
            cleaned = _format_natural_chat_paragraphs(
                cleaned,
                self.natural_chat_max_sentences,
            )
        if cleaned == text:
            return

        resp.completion_text = cleaned or "嗯。"
        logger.info(
            "%s action output stripped: group=%s sender=%s",
            PLUGIN_TAG,
            _safe_event_value(event, "get_group_id", "unknown"),
            _safe_event_value(event, "get_sender_id", "unknown"),
        )

    def _custom_ai_ready(self) -> bool:
        return (
            self.custom_ai_enabled
            and bool(self.custom_ai_api_base)
            and bool(self.custom_ai_model)
        )

    def _get_current_provider(self, event: AstrMessageEvent):
        get_provider = getattr(self.context, "get_using_provider", None)
        if not callable(get_provider):
            return None
        return get_provider(event.unified_msg_origin)

    async def _call_internal_model(
        self,
        event: AstrMessageEvent,
        *,
        prompt: str,
        system_prompt: str,
        timeout: float,
    ) -> str | None:
        custom_exc: Exception | None = None
        if self._custom_ai_ready():
            try:
                text = await _post_openai_chat_completion(
                    api_base=self.custom_ai_api_base,
                    api_key=self.custom_ai_api_key,
                    model=self.custom_ai_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    timeout=timeout,
                )
                if text:
                    return text
            except Exception as exc:
                custom_exc = exc
                logger.warning(
                    "%s custom ai failed, fallback to current provider: %s",
                    PLUGIN_TAG,
                    _format_exception(exc),
                )

        provider = self._get_current_provider(event)
        if provider is None:
            if custom_exc is not None:
                raise custom_exc
            return None

        resp = await asyncio.wait_for(
            provider.text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                contexts=[],
                request_max_retries=1,
            ),
            timeout=timeout,
        )
        return (getattr(resp, "completion_text", "") or "").strip()

    async def _rewrite_reply_naturally(
        self,
        event: AstrMessageEvent,
        text: str,
    ) -> str:
        local_formatted = _format_natural_chat_paragraphs(text)

        prompt = (
            "请只调整下面回复的表达格式，不要改变原意，不要新增信息。\n"
            "要求：\n"
            "1. 删除括号动作描写、舞台旁白、身体动作描述。\n"
            "2. 如果是日常聊天，按语气和停顿自行判断是否拆成多个自然短段，每段之间用一个空行。\n"
            f"3. 不要为了凑数量而拆分；确实需要分段时最多 {self.natural_chat_max_sentences} 段。\n"
            "4. 如果是技术、配置、列表、代码或命令说明，保持结构清晰，不要乱拆。\n"
            "5. 日常聊天删掉标题、小标题、加粗标题和 Markdown 报告格式，像直接发消息。\n"
            "6. 只输出整理后的回复正文，不要解释。\n\n"
            f"原回复：\n{text}"
        )
        try:
            rewritten = await self._call_internal_model(
                event,
                prompt=prompt,
                system_prompt="你是回复格式整理器，只调整格式和删除括号动作描写，不改意思。",
                timeout=min(self.judge_timeout_sec, self.natural_rewrite_timeout_sec),
            )
        except Exception as exc:
            logger.debug(
                "%s natural rewrite failed: %s",
                PLUGIN_TAG,
                _format_exception(exc),
            )
            return local_formatted

        rewritten = (rewritten or "").strip()
        if not _is_usable_rewrite(text, rewritten):
            return local_formatted
        return rewritten

    @filter.on_decorating_result(priority=-80)
    async def send_natural_segments(self, event: AstrMessageEvent) -> None:
        if not self._should_take_over_segment_send(event):
            return

        result = event.get_result()
        if result is None or not getattr(result, "chain", None):
            return

        plain = self._single_plain_text(result.chain)
        if plain is None:
            return

        text = plain.strip()
        if len(text) < 45 or _is_technical_or_code_reply(text):
            return
        if _looks_like_casual_numbered_list(text):
            segments = _casual_numbered_list_segments(text, self.natural_chat_max_sentences)
        else:
            segments = await self._build_natural_segments(event, text)

        if len(segments) < 2:
            return

        event.clear_result()
        sent_count = 0
        try:
            for index, segment in enumerate(segments):
                if index > 0 and self.smart_segment_interval_sec > 0:
                    await asyncio.sleep(
                        random.uniform(
                            self.smart_segment_interval_sec * 0.7,
                            self.smart_segment_interval_sec * 1.3,
                        ),
                    )
                await event.send(result.derive([Plain(segment)]))
                sent_count += 1
        except Exception as exc:
            logger.warning(
                "%s smart segmented send failed after %s/%s segments: %s",
                PLUGIN_TAG,
                sent_count,
                len(segments),
                _format_exception(exc),
            )
            return

        logger.info(
            "%s smart segmented send: group=%s sender=%s segments=%s",
            PLUGIN_TAG,
            _safe_event_value(event, "get_group_id", "unknown"),
            _safe_event_value(event, "get_sender_id", "unknown"),
            len(segments),
        )

    def _should_take_over_segment_send(self, event: AstrMessageEvent) -> bool:
        if not self.natural_chat_style_enabled or not self.smart_segment_enabled:
            return False
        get_platform_name = getattr(event, "get_platform_name", None)
        if callable(get_platform_name):
            try:
                if get_platform_name() in SEGMENT_UNSUPPORTED_PLATFORMS:
                    return False
            except Exception:
                pass

        result = event.get_result()
        if result is None or not _safe_is_model_result(result):
            return False

        if self.smart_segment_respect_astrbot and self._astrbot_segmented_reply_enabled(event):
            return False
        return True

    def _astrbot_segmented_reply_enabled(self, event: AstrMessageEvent) -> bool:
        get_config = getattr(self.context, "get_config", None)
        if not callable(get_config):
            return False
        try:
            cfg = get_config(event.unified_msg_origin)
        except Exception:
            return False
        try:
            return bool(cfg.get("platform_settings", {}).get("segmented_reply", {}).get("enable"))
        except Exception:
            return False

    def _single_plain_text(self, chain: list) -> str | None:
        plain_parts = []
        for comp in chain:
            if not isinstance(comp, Plain):
                return None
            plain_parts.append(comp.text or "")
        text = "".join(plain_parts).strip()
        return text or None

    async def _build_natural_segments(
        self,
        event: AstrMessageEvent,
        text: str,
    ) -> list[str]:
        local_segments = _natural_local_segments(text, self.natural_chat_max_sentences)
        if not self.smart_segment_use_model:
            return local_segments

        prompt = (
            "请把下面这条聊天回复切成更自然的多条即时聊天消息。\n"
            "只调整分段，不改原意，不新增信息，不改变称呼和语气。\n"
            "去掉 Markdown 强调星号、标题、小标题、项目符号外壳和动作描写符号，让每条消息像直接聊天发送。\n"
            "由你根据真实聊天语气、停顿和信息密度判断应该分成几条；不要固定段数，也不要为了拆而拆。\n"
            "如果它更适合一条消息，返回 split=false。\n"
            f"为避免刷屏，确实需要拆分时最多 {self.natural_chat_max_sentences} 条。\n\n"
            f"原回复：\n{text}"
        )
        try:
            raw = await self._call_internal_model(
                event,
                prompt=prompt,
                system_prompt=(
                    "你是聊天消息分段器。必须只输出 JSON，格式为 "
                    '{"split": true, "segments": ["第一段", "第二段"]}。'
                    "segments 数量由自然语气决定，不固定；更适合一条时输出 "
                    '{"split": false, "segments": []}。'
                    "不要输出解释、Markdown、星号强调、标题、小标题、动作描写或代码块。"
                ),
                timeout=min(self.judge_timeout_sec, self.smart_segment_model_timeout_sec),
            )
        except Exception as exc:
            logger.debug(
                "%s smart segment failed: %s",
                PLUGIN_TAG,
                _format_exception(exc),
            )
            return local_segments

        raw = (raw or "").strip()
        model_segments = _normalise_model_segments(
            text,
            raw,
            self.natural_chat_max_sentences,
        )
        if model_segments is None:
            return local_segments
        return model_segments

    def _remove_direct_send_tool(self, req: ProviderRequest) -> None:
        if req.func_tool is None:
            return
        req.func_tool.remove_tool("send_message_to_user")

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

    def _is_active_reply_cooldown_active(
        self,
        event: AstrMessageEvent,
        *,
        now: float | None = None,
    ) -> tuple[bool, str]:
        if self.active_reply_cooldown_sec <= 0:
            return False, "allowed"
        now = monotonic() if now is None else now
        key = event.unified_msg_origin
        elapsed = now - self._last_active_reply_at.get(key, 0)
        if elapsed < self.active_reply_cooldown_sec:
            return (
                True,
                f"cooldown:{elapsed:.1f}/{self.active_reply_cooldown_sec:.1f}s",
            )
        return False, "allowed"

    def _has_active_reply_cue(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.active_reply_cue_patterns)

    def _has_followup_reply_cue(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.followup_reply_cue_patterns)

    def _record_followup_target(
        self,
        event: AstrMessageEvent,
        *,
        now: float | None = None,
    ) -> None:
        if self.followup_reply_window_sec <= 0:
            return
        now = monotonic() if now is None else now
        self._last_followup_target_at[self._followup_reply_key(event)] = now

    def _recent_followup_reply_reason(
        self,
        event: AstrMessageEvent,
        text: str,
        *,
        now: float | None = None,
        require_cue: bool = True,
        reason_prefix: str = "followup_window",
    ) -> tuple[bool, str]:
        if self.followup_reply_window_sec <= 0:
            return False, "followup_disabled"
        if require_cue and not self._has_followup_reply_cue(text):
            return False, "no_followup_reply_cue"

        now = monotonic() if now is None else now
        key = self._followup_reply_key(event)
        last_target_at = self._last_followup_target_at.get(key)
        if last_target_at is None:
            return False, "no_followup_target"

        elapsed = now - last_target_at
        if elapsed <= self.followup_reply_window_sec:
            return (
                True,
                f"{reason_prefix}:{elapsed:.1f}/{self.followup_reply_window_sec:.1f}s",
            )
        return False, f"followup_expired:{elapsed:.1f}/{self.followup_reply_window_sec:.1f}s"

    def _followup_reply_key(self, event: AstrMessageEvent) -> str:
        return (
            f"{event.unified_msg_origin}:bot:{event.get_self_id()}:"
            f"sender:{event.get_sender_id()}"
        )

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
            answer = await self._call_internal_model(
                event,
                prompt=prompt,
                system_prompt="你只输出 REPLY 或 SKIP。",
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

        answer = (answer or "").strip().upper()
        if "REPLY" in answer and "SKIP" not in answer:
            return "REPLY"
        if "SKIP" in answer and "REPLY" not in answer:
            return "SKIP"
        return None

    async def _followup_decide(self, event: AstrMessageEvent, text: str) -> str | None:
        bot_label = self._primary_mention_keyword()
        recent_context = self._recent_group_context(event)
        context_block = (
            f"最近群聊上下文:\n{recent_context}\n\n" if recent_context else ""
        )
        prompt = (
            f"你是群聊机器人“{bot_label}”的连续对话判定器。"
            f"同一发言人刚和{bot_label}对话过，现在没有再次点名。"
            f"请判断这条消息是不是仍在接着对{bot_label}说。\n"
            "输出 REPLY 的情况：追问、补充说明、纠正上一句、表达对上一轮回复的反应、"
            "短句但明显是在等机器人继续接话。\n"
            "输出 SKIP 的情况：转而和群里其他人聊天、普通感叹或表情、开启了新话题但没有邀请机器人、"
            "接话会显得突兀或抢话。\n"
            "只能输出 REPLY 或 SKIP，不要输出其他内容。\n\n"
            f"群号: {event.get_group_id()}\n"
            f"发言人ID: {event.get_sender_id()}\n"
            f"发言人昵称: {event.get_sender_name()}\n"
            f"{context_block}"
            f"当前消息: {text}\n"
        )

        try:
            answer = await self._call_internal_model(
                event,
                prompt=prompt,
                system_prompt="你只输出 REPLY 或 SKIP。",
                timeout=self.judge_timeout_sec,
            )
        except Exception as exc:
            self._record_judge_failure(event, "followup", exc)
            logger.warning(
                "%s followup judge failed: %s",
                PLUGIN_TAG,
                _format_exception(exc),
            )
            return None

        answer = (answer or "").strip().upper()
        if "REPLY" in answer and "SKIP" not in answer:
            return "REPLY"
        if "SKIP" in answer and "REPLY" not in answer:
            return "SKIP"
        return None

    async def _active_decide(self, event: AstrMessageEvent, text: str) -> str | None:
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
            answer = await self._call_internal_model(
                event,
                prompt=prompt,
                system_prompt="你只输出 REPLY 或 SKIP。",
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

        answer = (answer or "").strip().upper()
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


def _safe_event_value(event: AstrMessageEvent, method_name: str, fallback: str) -> str:
    method = getattr(event, method_name, None)
    if not callable(method):
        return fallback
    try:
        value = method()
    except Exception:
        return fallback
    if value is None:
        return fallback
    return str(value)


def _is_usable_rewrite(original: str, rewritten: str) -> bool:
    if not rewritten:
        return False
    if len(rewritten) > max(len(original) * 2, len(original) + 80):
        return False
    lowered = rewritten.lower()
    if lowered.startswith(("整理后的", "以下是", "好的", "可以，")):
        return False
    return True


def _safe_is_model_result(result) -> bool:
    method = getattr(result, "is_model_result", None)
    if callable(method):
        try:
            return bool(method())
        except Exception:
            return False
    method = getattr(result, "is_llm_result", None)
    if callable(method):
        try:
            return bool(method())
        except Exception:
            return False
    return False


def _stop_event_silently(event: AstrMessageEvent) -> None:
    if hasattr(event, "_force_stopped"):
        event._force_stopped = True
        return
    event.stop_event()
