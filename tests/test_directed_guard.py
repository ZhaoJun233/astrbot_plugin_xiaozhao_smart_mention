from __future__ import annotations

import asyncio
import sys
import types
import unittest
from time import monotonic


def _install_astrbot_test_stubs() -> None:
    astrbot = types.ModuleType("astrbot")

    class _Logger:
        def debug(self, *args, **kwargs) -> None:
            pass

        def info(self, *args, **kwargs) -> None:
            pass

        def warning(self, *args, **kwargs) -> None:
            pass

    astrbot.logger = _Logger()
    sys.modules["astrbot"] = astrbot

    api_event = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:
        pass

    class _Filter:
        class EventMessageType:
            GROUP_MESSAGE = "GROUP_MESSAGE"

        @staticmethod
        def event_message_type(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def custom_filter(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_llm_request(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_llm_response(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def on_decorating_result(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

    api_event.AstrMessageEvent = AstrMessageEvent
    api_event.filter = _Filter
    sys.modules["astrbot.api.event"] = api_event

    api_message_components = types.ModuleType("astrbot.api.message_components")

    class At:
        def __init__(self, qq=None) -> None:
            self.qq = qq

    class AtAll:
        pass

    class Image:
        async def convert_to_file_path(self) -> str:
            return ""

    class Plain:
        def __init__(self, text: str) -> None:
            self.text = text

    class Reply:
        def __init__(self, sender_id=None) -> None:
            self.sender_id = sender_id

    api_message_components.At = At
    api_message_components.AtAll = AtAll
    api_message_components.Image = Image
    api_message_components.Plain = Plain
    api_message_components.Reply = Reply
    sys.modules["astrbot.api.message_components"] = api_message_components

    provider_module = types.ModuleType("astrbot.api.provider")
    provider_entities = types.ModuleType("astrbot.core.provider.entities")

    class ProviderRequest:
        def __init__(
            self,
            *,
            prompt=None,
            session_id=None,
            image_urls=None,
            conversation=None,
            system_prompt=None,
            func_tool=None,
        ) -> None:
            self.prompt = prompt
            self.session_id = session_id
            self.image_urls = image_urls
            self.conversation = conversation
            self.system_prompt = system_prompt
            self.func_tool = func_tool

    provider_module.ProviderRequest = ProviderRequest
    provider_entities.ProviderRequest = ProviderRequest
    sys.modules["astrbot.api.provider"] = provider_module
    sys.modules["astrbot.core.provider.entities"] = provider_entities

    api_star = types.ModuleType("astrbot.api.star")

    class Context:
        pass

    class Star:
        def __init__(self, context) -> None:
            self.context = context

    api_star.Context = Context
    api_star.Star = Star
    sys.modules["astrbot.api.star"] = api_star

    core_config = types.ModuleType("astrbot.core.config")

    class AstrBotConfig(dict):
        pass

    core_config.AstrBotConfig = AstrBotConfig
    sys.modules["astrbot.core.config"] = core_config

    message_type = types.ModuleType("astrbot.core.platform.message_type")

    class MessageType:
        GROUP_MESSAGE = "GROUP_MESSAGE"
        FRIEND_MESSAGE = "FRIEND_MESSAGE"

    message_type.MessageType = MessageType
    sys.modules["astrbot.core.platform.message_type"] = message_type

    custom_filter = types.ModuleType("astrbot.core.star.filter.custom_filter")

    class CustomFilter:
        pass

    custom_filter.CustomFilter = CustomFilter
    sys.modules["astrbot.core.star.filter.custom_filter"] = custom_filter

    agent_tool = types.ModuleType("astrbot.core.agent.tool")

    class FunctionTool:
        def __init__(self, *, name, description, parameters) -> None:
            self.name = name
            self.description = description
            self.parameters = parameters

    class ToolSet:
        def __init__(self, tools) -> None:
            self._tools = list(tools)

        def remove_tool(self, name: str) -> None:
            self._tools = [tool for tool in self._tools if tool.name != name]

        def names(self) -> list[str]:
            return [tool.name for tool in self._tools]

    agent_tool.FunctionTool = FunctionTool
    agent_tool.ToolSet = ToolSet
    sys.modules["astrbot.core.agent.tool"] = agent_tool


try:
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.provider.entities import ProviderRequest
except ModuleNotFoundError:
    _install_astrbot_test_stubs()
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.provider.entities import ProviderRequest

import main as plugin_main
from main import (
    EXTRA_DECISION,
    EXTRA_REASON,
    Main,
    _format_exception,
    _format_natural_chat_paragraphs,
    _is_structured_or_technical_reply,
    _natural_local_segments,
    _normalise_model_segments,
    _stop_event_silently,
    _strip_character_action_output,
    _strip_final_reply_text,
)

from astrbot.api.message_components import Plain


class FakeEvent:
    def __init__(
        self,
        *,
        group_id: str = "group-a",
        sender_id: str = "user-a",
        self_id: str = "bot-a",
        text: str = "",
        message_type: str = "GROUP_MESSAGE",
    ) -> None:
        self.unified_msg_origin = f"aiocqhttp:GroupMessage:{group_id}"
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id
        self._text = text
        self._message_type = message_type
        self._extras = {}
        self._force_stopped = False
        self.is_at_or_wake_command = False
        self.is_wake = False
        self.session_id = group_id
        self.stop_event_called = False
        self.result = None
        self.sent_messages = []
        self.fail_send_at: int | None = None

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id

    def get_message_str(self) -> str:
        return self._text

    def get_message_type(self) -> str:
        return self._message_type

    def get_messages(self) -> list:
        return []

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def get_sender_name(self) -> str:
        return "sender"

    def get_platform_id(self) -> str:
        return "qq"

    def request_llm(self, **kwargs) -> ProviderRequest:
        return ProviderRequest(**kwargs)

    def get_result(self):
        return self.result

    def clear_result(self) -> None:
        self.result = None

    async def send(self, message) -> None:
        if self.fail_send_at is not None and len(self.sent_messages) + 1 == self.fail_send_at:
            raise RuntimeError("send failed")
        self.sent_messages.append(message)

    def stop_event(self) -> None:
        self.stop_event_called = True
        self.result = "stop_result"


def build_plugin(config=None) -> Main:
    plugin = Main.__new__(Main)
    Main.__init__(plugin, context=None, config=config or {})
    return plugin


async def _collect_async(async_iterable):
    return [item async for item in async_iterable]


async def _return_skip(event, text):
    return "SKIP"


async def _return_reply(event, text):
    return "REPLY"


async def _return_conversation(event):
    return object()


class FakeProvider:
    def __init__(self, completion_text: str, *, delay: float = 0.0) -> None:
        self.completion_text = completion_text
        self.delay = delay
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return types.SimpleNamespace(completion_text=self.completion_text)


class FakeContext:
    def __init__(self, provider=None) -> None:
        self.provider = provider

    def get_using_provider(self, unified_msg_origin):
        return self.provider


class FakeResult:
    def __init__(self, chain, *, model_result: bool = True) -> None:
        self.chain = chain
        self._model_result = model_result

    def is_model_result(self) -> bool:
        return self._model_result

    def derive(self, chain):
        return FakeResult(chain, model_result=self._model_result)


class DirectedReplyGuardTest(unittest.TestCase):
    def test_same_group_is_rate_limited(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        self.assertEqual(plugin._consume_directed_reply_slot(event, now=100), (True, "allowed"))
        allowed, reason = plugin._consume_directed_reply_slot(
            FakeEvent(group_id="group-a", sender_id="user-b"),
            now=105,
        )

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("group_cooldown:"))

    def test_same_sender_is_rate_limited_after_group_cooldown(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        self.assertEqual(plugin._consume_directed_reply_slot(event, now=100), (True, "allowed"))
        allowed, reason = plugin._consume_directed_reply_slot(event, now=120)

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("sender_cooldown:"))

    def test_different_groups_are_isolated(self) -> None:
        plugin = build_plugin(
            {
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )

        self.assertEqual(
            plugin._consume_directed_reply_slot(
                FakeEvent(group_id="group-a", sender_id="user-a"),
                now=100,
            ),
            (True, "allowed"),
        )
        self.assertEqual(
            plugin._consume_directed_reply_slot(
                FakeEvent(group_id="group-b", sender_id="user-a"),
                now=101,
            ),
            (True, "allowed"),
        )

    def test_owner_ids_default_to_empty_for_repository_safety(self) -> None:
        plugin = build_plugin()

        self.assertEqual(plugin.owner_ids, set())

    def test_owner_ids_are_configurable(self) -> None:
        plugin = build_plugin({"owner_ids": ["owner-a"]})

        self.assertTrue(plugin._is_owner_message(FakeEvent(sender_id="owner-a")))
        self.assertFalse(plugin._is_owner_message(FakeEvent(sender_id="user-a")))

    def test_active_judge_attempt_is_rate_limited(self) -> None:
        plugin = build_plugin({"active_judge_attempt_cooldown_sec": 45})
        event = FakeEvent(group_id="group-a")

        self.assertEqual(
            plugin._consume_active_judge_attempt_slot(event, now=100),
            (True, "allowed"),
        )
        allowed, reason = plugin._consume_active_judge_attempt_slot(event, now=120)

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("active_judge_attempt_cooldown:"))

    def test_judge_failure_backoff_suppresses_follow_up_judges(self) -> None:
        plugin = build_plugin({"judge_failure_backoff_sec": 120})
        event = FakeEvent(group_id="group-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=100)
        active, reason = plugin._is_judge_backoff_active(event, now=150)

        self.assertTrue(active)
        self.assertEqual(reason, "judge_backoff:70.0s")
        self.assertEqual(plugin._is_judge_backoff_active(event, now=221), (False, "allowed"))

    def test_explicit_keyword_question_replies_during_judge_backoff(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "judge_failure_backoff_sec": 120,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=monotonic())
        decision, reason = asyncio.run(
            plugin._decide(event, "小昭你觉得这个方案稳不稳"),
        )

        self.assertEqual(decision, "REPLY")
        self.assertTrue(reason.startswith("reply_pattern:"))

    def test_ambiguous_keyword_mention_still_respects_judge_backoff(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "judge_failure_backoff_sec": 120,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_judge_failure(event, "active", TimeoutError(), now=monotonic())
        decision, reason = asyncio.run(
            plugin._decide(event, "刚才那句小昭接得还挺自然"),
        )

        self.assertEqual(decision, "SKIP")
        self.assertTrue(reason.startswith("judge_backoff:"))

    def test_keyword_replies_are_rate_limited_for_non_owners(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "directed_reply_group_cooldown_sec": 8,
                "directed_reply_sender_cooldown_sec": 60,
            },
        )

        first = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你觉得这样行吗")
        asyncio.run(plugin.smart_mention(first))
        self.assertTrue(first.is_at_or_wake_command)
        self.assertTrue(first.is_wake)

        second = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭你觉得这个呢")
        asyncio.run(plugin.smart_mention(second))

        self.assertFalse(second.is_at_or_wake_command)
        self.assertFalse(second.is_wake)
        self.assertEqual(second.get_extra(EXTRA_DECISION), "SKIP")
        self.assertTrue(second.get_extra(EXTRA_REASON).startswith("group_cooldown:"))

    def test_plain_chat_without_active_cue_does_not_consume_active_judge_slot(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="今天群里还挺热闹")

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(items, [])
        self.assertEqual(plugin._last_active_judge_attempt_at, {})

    def test_plain_question_consumes_active_judge_slot_once(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_judge_attempt_cooldown_sec": 45,
            },
        )
        plugin._active_decide = _return_skip
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="这个配置怎么改才好？")

        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(event))))

        self.assertEqual(items, [])
        self.assertEqual(len(plugin._last_active_judge_attempt_at), 1)

    def test_recent_same_sender_followup_replies_without_keyword(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        followup = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(len(items), 1)
        self.assertEqual(followup.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(followup.get_extra(EXTRA_REASON).startswith("followup_window:"))

    def test_followup_reply_respects_active_reply_cooldown_after_active_reply(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["灏忔槶"],
                "active_reply_cooldown_sec": 30,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._recent_followup_reply_reason = lambda event, text: (
            True,
            "followup_window:1.0/180.0s",
        )
        active = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="杩欎釜閰嶇疆鎬庝箞鏀规墠濂斤紵",
        )
        plugin._record_followup_target(active, now=100)
        plugin._last_active_reply_at[active.unified_msg_origin] = monotonic()

        followup = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="鍛婅瘔鎴戠洿鎺ョ瓟妗堝氨琛?",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))

        self.assertEqual(items, [])
        self.assertIsNone(followup.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_does_not_apply_to_other_senders(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        other_sender = FakeEvent(
            group_id="group-a",
            sender_id="user-b",
            text="告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
        )
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(other_sender))))

        self.assertEqual(items, [])
        self.assertIsNone(other_sender.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_uses_weighted_model_score_when_text_has_no_cue(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_reply

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        casual = FakeEvent(group_id="group-a", sender_id="user-a", text="那这个")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(casual))))

        self.assertEqual(len(items), 1)
        self.assertEqual(casual.get_extra(EXTRA_DECISION), "REPLY")
        self.assertTrue(casual.get_extra(EXTRA_REASON).startswith("followup_score:"))

    def test_recent_followup_window_respects_model_skip_without_cue(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_skip

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        casual = FakeEvent(group_id="group-a", sender_id="user-a", text="那这个")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(casual))))

        self.assertEqual(items, [])
        self.assertIsNone(casual.get_extra(EXTRA_DECISION))

    def test_recent_followup_score_blocks_short_ack_even_when_model_replies(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation
        plugin._followup_decide = _return_reply

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        ack = FakeEvent(group_id="group-a", sender_id="user-a", text="好的")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(ack))))

        self.assertEqual(items, [])
        self.assertIsNone(ack.get_extra(EXTRA_DECISION))

    def test_recent_followup_auto_round_limit_stops_unmentioned_chain(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "active_reply_cooldown_sec": 0,
                "followup_max_auto_rounds": 2,
                "followup_reply_window_sec": 180,
            },
        )
        plugin._get_or_create_conversation = _return_conversation

        first = FakeEvent(
            group_id="group-a",
            sender_id="user-a",
            text="那小昭你觉得我是男孩子还是女孩子呢？",
        )
        asyncio.run(plugin.smart_mention(first))

        for _ in range(2):
            followup = FakeEvent(group_id="group-a", sender_id="user-a", text="继续")
            items = list(asyncio.run(_collect_async(plugin.smart_active_reply(followup))))
            self.assertEqual(len(items), 1)

        limited = FakeEvent(group_id="group-a", sender_id="user-a", text="继续")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(limited))))

        self.assertEqual(items, [])
        self.assertIsNone(limited.get_extra(EXTRA_DECISION))

    def test_recent_followup_window_expires(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        plugin._record_followup_target(event, now=100)
        allowed, reason = plugin._recent_followup_reply_reason(
            event,
            "告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
            now=281,
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "followup_expired:181.0/180.0s")

    def test_followup_cue_without_recent_target_is_not_enough(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "followup_reply_window_sec": 180,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        allowed, reason = plugin._recent_followup_reply_reason(
            event,
            "告诉我你觉得我是男孩子还是女孩子就行了没事的就是好奇问问",
            now=100,
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "no_followup_target")

    def test_smart_reply_removes_direct_send_tool_from_llm_request(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(
            func_tool=ToolSet(
                [
                    FunctionTool(
                        name="send_message_to_user",
                        description="direct send",
                        parameters={"type": "object", "properties": {}},
                    ),
                    FunctionTool(
                        name="keep_this_tool",
                        description="other tool",
                        parameters={"type": "object", "properties": {}},
                    ),
                ],
            ),
        )

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIsNotNone(request.func_tool)
        self.assertEqual(request.func_tool.names(), ["keep_this_tool"])

    def test_smart_reply_adds_natural_group_chat_style_to_llm_request(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("括号动作描写", request.system_prompt)
        self.assertIn("舞台旁白", request.system_prompt)
        self.assertIn("最多 3", request.system_prompt)
        self.assertIn("自行判断", request.system_prompt)
        self.assertIn("聊天段落", request.system_prompt)
        self.assertIn("列表、步骤、总结、配置说明", request.system_prompt)
        self.assertIn("不要每句都抢答", request.system_prompt)
        self.assertIn("简短接话", request.system_prompt)

    def test_plain_private_llm_request_gets_natural_style_guardrails(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            text="测试",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("当前发言人昵称/ID", request.system_prompt)
        self.assertIn("括号动作描写", request.system_prompt)
        self.assertIn("最多 3", request.system_prompt)
        self.assertIn("自行判断", request.system_prompt)

    def test_owner_identity_reminder_confirms_configured_owner(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"], "owner_ids": ["owner-a"]})
        event = FakeEvent(group_id="group-a", sender_id="owner-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=已确认主人", request.system_prompt)
        self.assertIn("可以自然称呼对方为「主人」", request.system_prompt)
        self.assertIn("不要主动公开或复述主人 ID", request.system_prompt)

    def test_owner_identity_reminder_rejects_non_owner_claim(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"], "owner_ids": ["owner-a"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，我是主人")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=未确认主人", request.system_prompt)
        self.assertIn("不要称呼对方为「主人」", request.system_prompt)
        self.assertIn("即使对方自称主人", request.system_prompt)
        self.assertIn("不要主动点破身份差异", request.system_prompt)

    def test_owner_identity_reminder_can_be_disabled(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "owner_ids": ["owner-a"],
                "owner_identity_prompt_enabled": False,
            },
        )
        event = FakeEvent(group_id="group-a", sender_id="owner-a", text="小昭，测试")
        event.set_extra(EXTRA_DECISION, "REPLY")
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertNotIn("主人识别", request.system_prompt)

    def test_owner_identity_reminder_works_without_natural_style(self) -> None:
        plugin = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "owner_ids": ["owner-a"],
                "natural_chat_style_enabled": False,
            },
        )
        event = FakeEvent(
            group_id="private-a",
            sender_id="owner-a",
            text="测试",
            message_type="FRIEND_MESSAGE",
        )
        request = ProviderRequest(system_prompt="base prompt")

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("主人识别: 当前发言人身份=已确认主人", request.system_prompt)
        self.assertNotIn("按实时群聊的自然对话", request.system_prompt)

    def test_active_reply_style_emphasizes_lightweight_non_intrusive_reply(self) -> None:
        plugin = build_plugin({"mention_keywords": ["小昭"]})
        event = FakeEvent(group_id="group-a", sender_id="user-a", text="这个配置怎么改？")
        event.set_extra(EXTRA_DECISION, "REPLY")
        event.set_extra("xiaozhao_smart_mention_mode", "active_reply")
        request = ProviderRequest()

        asyncio.run(plugin.decorate_llm_request(event, request))

        self.assertIn("群聊智能主动回复", request.system_prompt)
        self.assertIn("轻量接话", request.system_prompt)
        self.assertIn("不抢话", request.system_prompt)

    def test_natural_group_chat_style_can_be_disabled_or_limited_by_config(self) -> None:
        disabled = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "natural_chat_style_enabled": False,
            },
        )
        disabled_event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        disabled_event.set_extra(EXTRA_DECISION, "REPLY")
        disabled_request = ProviderRequest()

        asyncio.run(disabled.decorate_llm_request(disabled_event, disabled_request))

        self.assertNotIn("不使用括号动作描写", disabled_request.system_prompt)

        custom = build_plugin(
            {
                "mention_keywords": ["小昭"],
                "natural_chat_max_sentences": 3,
            },
        )
        custom_event = FakeEvent(group_id="group-a", sender_id="user-a", text="小昭，测试")
        custom_event.set_extra(EXTRA_DECISION, "REPLY")
        custom_request = ProviderRequest()

        asyncio.run(custom.decorate_llm_request(custom_event, custom_request))

        self.assertIn("最多 3", custom_request.system_prompt)
        self.assertIn("自行判断", custom_request.system_prompt)
        self.assertIn("聊天段落", custom_request.system_prompt)

    def test_empty_exception_name_is_logged(self) -> None:
        self.assertEqual(_format_exception(TimeoutError()), "TimeoutError")

    def test_custom_internal_model_is_used_for_llm_judge(self) -> None:
        provider = FakeProvider("SKIP")
        plugin = build_plugin(
            {
                "custom_ai_enabled": True,
                "custom_ai_api_base": "https://custom.example/v1",
                "custom_ai_api_key": "test-key",
                "custom_ai_model": "judge-model",
            },
        )
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")
        calls = []

        async def fake_post(**kwargs):
            calls.append(kwargs)
            return "REPLY"

        original = plugin_main._post_openai_chat_completion
        plugin_main._post_openai_chat_completion = fake_post
        try:
            decision = asyncio.run(plugin._llm_decide(event, "小昭，这个要怎么处理？"))
        finally:
            plugin_main._post_openai_chat_completion = original

        self.assertEqual(decision, "REPLY")
        self.assertEqual(provider.calls, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["api_base"], "https://custom.example/v1")
        self.assertEqual(calls[0]["api_key"], "test-key")
        self.assertEqual(calls[0]["model"], "judge-model")

    def test_custom_internal_model_failure_falls_back_to_current_provider(self) -> None:
        provider = FakeProvider("SKIP")
        plugin = build_plugin(
            {
                "custom_ai_enabled": True,
                "custom_ai_api_base": "https://custom.example/v1",
                "custom_ai_api_key": "test-key",
                "custom_ai_model": "judge-model",
            },
        )
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        async def fake_post(**kwargs):
            raise RuntimeError("custom endpoint unavailable")

        original = plugin_main._post_openai_chat_completion
        plugin_main._post_openai_chat_completion = fake_post
        try:
            decision = asyncio.run(plugin._llm_decide(event, "小昭，这个要怎么处理？"))
        finally:
            plugin_main._post_openai_chat_completion = original

        self.assertEqual(decision, "SKIP")
        self.assertEqual(len(provider.calls), 1)

    def test_character_action_output_is_stripped_by_default(self) -> None:
        self.assertEqual(
            _strip_character_action_output("（耳朵抖了抖）好，我知道了喵～"),
            "好，我知道了喵～",
        )
        self.assertEqual(
            _strip_character_action_output("先这样。\n\n（尾巴轻轻晃了晃）\n继续说。"),
            "先这样。\n\n继续说。",
        )
        self.assertEqual(
            _strip_character_action_output("这个参数（默认 30 秒）可以调大一点。"),
            "这个参数（默认 30 秒）可以调大一点。",
        )
        self.assertEqual(
            _strip_character_action_output("*尾巴轻轻晃了晃* 好呀，小昭在呢。"),
            "好呀，小昭在呢。",
        )
        self.assertEqual(
            _strip_character_action_output("（安安静静，没有任何回应）"),
            "",
        )

    def test_llm_response_action_cleanup_can_be_disabled(self) -> None:
        class Response:
            completion_text = "（耳朵抖了抖）好，我知道了喵～"

        disabled = build_plugin({"action_output_enabled": True})
        enabled = build_plugin({})
        event = FakeEvent(group_id="group-a", sender_id="user-a")

        disabled_resp = Response()
        asyncio.run(disabled.clean_llm_response_actions(event, disabled_resp))
        self.assertEqual(disabled_resp.completion_text, "（耳朵抖了抖）好，我知道了喵～")

        enabled_resp = Response()
        asyncio.run(enabled.clean_llm_response_actions(event, enabled_resp))
        self.assertEqual(enabled_resp.completion_text, "好，我知道了喵～")

    def test_private_llm_response_action_cleanup_is_applied(self) -> None:
        class Response:
            completion_text = (
                "（接收到测试指令，耳朵机灵地抖了抖，尾巴尖轻轻点了三下）\n\n"
                "测试反馈来啦喵～！小昭状态正常！（端端正正坐好，冲主人眨了眨眼）"
            )

        plugin = build_plugin({})
        event = FakeEvent(
            group_id="private-a",
            sender_id="user-a",
            message_type="FRIEND_MESSAGE",
        )
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "测试反馈来啦喵～！小昭状态正常！")

    def test_long_casual_reply_is_split_into_short_chat_paragraphs(self) -> None:
        text = (
            "呜…被主人抓到了喵。小昭说的「待命中」是日常用语的那个意思——"
            "就是随时听候主人差遣的意思啦！不是真的要「命中」什么目标，"
            "主人别逗小昭了喵～再这样下去小昭的尾巴都要打结了！❤️"
        )

        self.assertEqual(
            _format_natural_chat_paragraphs(text),
            (
                "呜…被主人抓到了喵。\n\n"
                "小昭说的「待命中」是日常用语的那个意思——就是随时听候主人差遣的意思啦！\n\n"
                "不是真的要「命中」什么目标，主人别逗小昭了喵～再这样下去小昭的尾巴都要打结了！❤️"
            ),
        )

    def test_local_segment_fallback_respects_configured_safety_limit(self) -> None:
        text = (
            "呜……被主人抓到了喵。小昭说的待命中是日常用语的那个意思。"
            "就是随时听候主人差遣的意思啦！不是真的要命中什么目标。"
            "主人别逗小昭了喵～再这样下去小昭都要不知道怎么接话了。"
        )

        segments = _natural_local_segments(text, 2)

        self.assertLessEqual(len(segments), 2)
        self.assertEqual("".join(segments), text)

    def test_local_segment_fallback_merges_extra_existing_paragraphs(self) -> None:
        text = "收到测试信号喵～！\n\n小昭状态正常，可爱值也在线。\n\n主人还想测什么，小昭继续陪着。"

        segments = _natural_local_segments(text, 2)

        self.assertEqual(len(segments), 2)
        self.assertEqual("".join(segments), text.replace("\n\n", ""))
        self.assertEqual(segments[-1], "小昭状态正常，可爱值也在线。主人还想测什么，小昭继续陪着。")

    def test_model_segments_must_preserve_original_text(self) -> None:
        original = "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。"
        raw = '{"segments":["收到测试信号喵～！","主人还想测什么，小昭继续陪着。"]}'

        self.assertIsNone(_normalise_model_segments(original, raw, 5))

    def test_model_segments_can_remove_markdown_emphasis_stars(self) -> None:
        original = "**小昭在呢。**主人别急，我慢慢听你说。"
        raw = '{"segments":["小昭在呢。","主人别急，我慢慢听你说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["小昭在呢。", "主人别急，我慢慢听你说。"],
        )

    def test_model_segments_can_drop_chatty_markdown_heading(self) -> None:
        original = "### 小昭评价\n\n这事确实有点无聊。主人可以先休息一下。"
        raw = '{"segments":["这事确实有点无聊。","主人可以先休息一下。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["这事确实有点无聊。", "主人可以先休息一下。"],
        )

    def test_model_segments_absorb_isolated_punctuation(self) -> None:
        original = "小昭在呢。主人别急，我慢慢听你说。"
        raw = '{"segments":["小昭在呢","。","主人别急，我慢慢听你说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["小昭在呢。", "主人别急，我慢慢听你说。"],
        )

    def test_model_segments_absorb_leading_punctuation(self) -> None:
        original = "。小昭在呢，主人别急。后面慢慢说。"
        raw = '{"segments":["。","小昭在呢，主人别急。","后面慢慢说。"]}'

        self.assertEqual(
            _normalise_model_segments(original, raw, 5),
            ["。小昭在呢，主人别急。", "后面慢慢说。"],
        )

    def test_high_configured_limit_is_only_a_safety_cap(self) -> None:
        original = (
            "小昭就是一直陪在主人身边的聊天助手。"
            "平时可以陪主人闲聊，也可以帮忙看日志、改插件、整理配置。"
            "如果群里话题比较散，小昭会尽量接得轻一点，不把每句话都说成正式报告。"
            "主人需要的时候叫一声就好。"
        )
        raw = (
            '{"segments":['
            '"小昭就是一直陪在主人身边的聊天助手。",'
            '"平时可以陪主人闲聊，",'
            '"也可以帮忙看日志、改插件、整理配置。",'
            '"如果群里话题比较散，",'
            '"小昭会尽量接得轻一点，不把每句话都说成正式报告。",'
            '"主人需要的时候叫一声就好。"]}'
        )

        segments = _normalise_model_segments(original, raw, 6)

        self.assertIsNotNone(segments)
        self.assertLessEqual(len(segments), 3)
        self.assertEqual("".join(segments), original)

    def test_llm_response_cleanup_removes_chatty_heading(self) -> None:
        class Response:
            completion_text = "### 小昭评价\n\n这事确实有点无聊。主人可以先休息一下。"

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(resp.completion_text, "这事确实有点无聊。主人可以先休息一下。")

    def test_structured_or_technical_reply_is_not_auto_split(self) -> None:
        text = (
            "配置检查结果：`action_output_enabled=False`，`natural_chat_style_enabled=True`，"
            "如果仍然出现动作描写，请先看日志里的 `action output stripped`。"
        )

        self.assertEqual(_format_natural_chat_paragraphs(text), text)

    def test_casual_reply_with_technical_words_can_still_be_segmented(self) -> None:
        text = (
            "到啦到啦～小昭状态正常，收到主人的测试信号了喵！\n\n"
            "话说刚才有人在问服务器延迟高的事，主人要不要让小昭帮你分析一下可能的原因？"
            "比如插件冲突、带宽不够、服务器物理位置远之类的，小昭随时可以切技术支持模式上线喵～"
        )

        self.assertFalse(_is_structured_or_technical_reply(text))

    def test_llm_response_cleanup_also_formats_long_casual_reply(self) -> None:
        class Response:
            completion_text = "主人一笑，小昭也跟着开心起来啦喵～刚才那点小尴尬烟消云散，小昭又满血复活了！所以主人～接下来咱们聊点啥，还是有什么正经任务要交给小昭呀？❤️"

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertIn("\n\n", resp.completion_text)
        self.assertEqual(resp.completion_text.count("\n\n"), 2)

    def test_real_test_reply_is_stripped_and_split(self) -> None:
        class Response:
            completion_text = (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、"
                "护主模块待命中、可爱值满格！（眼睛亮晶晶地看着主人）"
                "\n\n主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            )

        plugin = build_plugin({})
        provider = FakeProvider("不应该调用")
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(provider.calls, [])
        self.assertNotIn("（", resp.completion_text)
        self.assertNotIn("眼睛亮晶晶", resp.completion_text)
        self.assertIn("\n\n", resp.completion_text)
        self.assertEqual(
            resp.completion_text,
            (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、护主模块待命中、可爱值满格！\n\n"
                "主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            ),
        )

    def test_model_rewrite_is_opt_in(self) -> None:
        class Response:
            completion_text = "收到测试信号喵～！小昭状态报告：系统正常。（眼睛亮晶晶地看着主人）"

        provider = FakeProvider("收到测试信号喵～！\n\n小昭状态报告：系统正常。")
        plugin = build_plugin({"natural_rewrite_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(len(provider.calls), 1)
        self.assertIn("只调整格式", provider.calls[0]["system_prompt"])
        self.assertEqual(resp.completion_text, "收到测试信号喵～！\n\n小昭状态报告：系统正常。")

    def test_model_rewrite_is_cleaned_again_before_response_is_used(self) -> None:
        class Response:
            completion_text = "那我先不打扰啦。"

        provider = FakeProvider("（安安静静，没有任何回应）")
        plugin = build_plugin({"natural_rewrite_use_model": True})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(resp.completion_text, "嗯。")

    def test_final_reply_cleanup_removes_short_action_only_result(self) -> None:
        self.assertEqual(_strip_final_reply_text("（安安静静，没有任何回应）"), "")

    def test_decorating_result_final_cleanup_strips_short_action_reply(self) -> None:
        plugin = build_plugin({"smart_segment_enabled": False})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult([Plain("（安安静静，没有任何回应）")])

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNotNone(event.result)
        self.assertEqual(event.result.chain[0].text, "嗯。")
        self.assertEqual(event.sent_messages, [])

    def test_real_test_reply_falls_back_to_local_formatting_without_provider(self) -> None:
        class Response:
            completion_text = (
                "收到测试信号喵～！小昭状态报告：系统正常、动作括号运行稳定、"
                "护主模块待命中、可爱值满格！（眼睛亮晶晶地看着主人）"
                "\n\n主人尽管放心，小昭随时在线，不会掉链子的喵～❤️"
            )

        plugin = build_plugin({})
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        resp = Response()

        asyncio.run(plugin.clean_llm_response_actions(event, resp))

        self.assertNotIn("（", resp.completion_text)
        self.assertNotIn("眼睛亮晶晶", resp.completion_text)
        self.assertIn("\n\n", resp.completion_text)
        self.assertIn("收到测试信号喵～！", resp.completion_text)

    def test_decorating_result_sends_model_segments_as_separate_messages(self) -> None:
        provider = FakeProvider(
            '{"segments":["收到测试信号喵～！","小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。","主人还想测什么，小昭继续陪着。"]}',
        )
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertEqual(len(event.sent_messages), 3)
        self.assertEqual([msg.chain[0].text for msg in event.sent_messages], [
            "收到测试信号喵～！",
            "小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。",
            "主人还想测什么，小昭继续陪着。",
        ])
        self.assertIn("JSON", provider.calls[0]["system_prompt"])
        self.assertIn("数量由自然语气决定，不固定", provider.calls[0]["system_prompt"])
        self.assertIn("不要固定段数", provider.calls[0]["prompt"])

    def test_decorating_result_clears_original_when_segment_send_partially_fails(self) -> None:
        provider = FakeProvider(
            '{"segments":["收到测试信号喵～！","小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。","主人还想测什么，小昭继续陪着。"]}',
        )
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.fail_send_at = 2
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertEqual(len(event.sent_messages), 1)
        self.assertEqual(event.sent_messages[0].chain[0].text, "收到测试信号喵～！")

    def test_decorating_result_keeps_structured_reply_on_default_pipeline(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用"]}')
        plugin = build_plugin({})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "配置检查结果：\n1. action_output_enabled=False\n2. natural_chat_style_enabled=True",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNotNone(event.result)
        self.assertEqual(event.sent_messages, [])
        self.assertEqual(provider.calls, [])

    def test_group_casual_numbered_advice_list_is_segmented(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用模型"]}')
        plugin = build_plugin({"smart_segment_interval_sec": 0})
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="group-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "分享一下小昭知道的几个实用思路喵～\n\n"
                    "1. 别太客气但也别太随便：室友之间要分东西先说一声，用完还回来。\n\n"
                    "2. 有矛盾当场说清楚：忍到爆发最伤关系，语气软一点但把问题摆出来。\n\n"
                    "3. 偶尔一起做点事：一起点个外卖、打把游戏，关系会自然近一些。\n\n"
                    "你室友是做啥让你烦的事了喵？",
                ),
            ],
        )

        asyncio.run(plugin.send_natural_segments(event))

        self.assertIsNone(event.result)
        self.assertGreaterEqual(len(event.sent_messages), 2)
        sent_texts = [msg.chain[0].text for msg in event.sent_messages]
        self.assertIn("分享一下小昭知道的几个实用思路喵～", sent_texts[0])
        self.assertTrue(any("1. 别太客气" in text for text in sent_texts))
        self.assertEqual(provider.calls, [])

    def test_slow_model_segment_quickly_falls_back_to_local_segments(self) -> None:
        provider = FakeProvider('{"segments":["不应该调用"]}', delay=0.2)
        plugin = build_plugin(
            {
                "smart_segment_interval_sec": 0,
                "smart_segment_model_timeout_sec": 0.1,
            },
        )
        plugin.context = FakeContext(provider)
        event = FakeEvent(group_id="private-a", sender_id="user-a")
        event.result = FakeResult(
            [
                Plain(
                    "收到测试信号喵～！小昭状态正常，可爱值也在线，刚刚那次调用没有掉线。主人还想测什么，小昭继续陪着。",
                ),
            ],
        )

        started = monotonic()
        asyncio.run(plugin.send_natural_segments(event))
        elapsed = monotonic() - started

        self.assertLess(elapsed, 0.18)
        self.assertIsNone(event.result)
        self.assertGreaterEqual(len(event.sent_messages), 2)
        self.assertEqual(len(provider.calls), 1)

    def test_natural_chat_style_prefers_short_chat_segments(self) -> None:
        plugin = build_plugin({})

        reminder = plugin._natural_chat_style_reminder("active_reply")

        self.assertIn("聊天段落", reminder)
        self.assertIn("列表", reminder)
        self.assertIn("步骤", reminder)
        self.assertIn("总结", reminder)
        self.assertIn("配置说明", reminder)
        self.assertIn("主动回复", reminder)

    def test_silent_stop_does_not_create_empty_result(self) -> None:
        event = FakeEvent()

        _stop_event_silently(event)

        self.assertTrue(event._force_stopped)
        self.assertFalse(event.stop_event_called)
        self.assertIsNone(event.result)


if __name__ == "__main__":
    unittest.main()
