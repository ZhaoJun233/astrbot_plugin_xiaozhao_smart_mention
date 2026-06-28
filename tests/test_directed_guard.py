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

    class Reply:
        def __init__(self, sender_id=None) -> None:
            self.sender_id = sender_id

    api_message_components.At = At
    api_message_components.AtAll = AtAll
    api_message_components.Image = Image
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

from main import (
    EXTRA_DECISION,
    EXTRA_REASON,
    Main,
    _format_exception,
    _stop_event_silently,
    _strip_character_action_output,
)


class FakeEvent:
    def __init__(
        self,
        *,
        group_id: str = "group-a",
        sender_id: str = "user-a",
        self_id: str = "bot-a",
        text: str = "",
    ) -> None:
        self.unified_msg_origin = f"aiocqhttp:GroupMessage:{group_id}"
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id
        self._text = text
        self._extras = {}
        self._force_stopped = False
        self.is_at_or_wake_command = False
        self.is_wake = False
        self.session_id = group_id
        self.stop_event_called = False
        self.result = None

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id

    def get_message_str(self) -> str:
        return self._text

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


async def _return_conversation(event):
    return object()


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

    def test_recent_followup_window_requires_followup_cue(self) -> None:
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

        casual = FakeEvent(group_id="group-a", sender_id="user-a", text="今天群里还挺热闹")
        items = list(asyncio.run(_collect_async(plugin.smart_active_reply(casual))))

        self.assertEqual(items, [])
        self.assertIsNone(casual.get_extra(EXTRA_DECISION))

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
        self.assertIn("1-3", request.system_prompt)
        self.assertIn("聊天段落", request.system_prompt)
        self.assertIn("列表、步骤、总结、配置说明", request.system_prompt)
        self.assertIn("不要每句都抢答", request.system_prompt)
        self.assertIn("简短接话", request.system_prompt)

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

        self.assertIn("1-3", custom_request.system_prompt)
        self.assertIn("聊天段落", custom_request.system_prompt)

    def test_empty_exception_name_is_logged(self) -> None:
        self.assertEqual(_format_exception(TimeoutError()), "TimeoutError")

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
