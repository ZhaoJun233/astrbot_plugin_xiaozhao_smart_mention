from __future__ import annotations

import asyncio
import unittest
from time import monotonic

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import ProviderRequest
from main import EXTRA_DECISION, EXTRA_REASON, Main, _format_exception, _stop_event_silently


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

    def test_empty_exception_name_is_logged(self) -> None:
        self.assertEqual(_format_exception(TimeoutError()), "TimeoutError")

    def test_silent_stop_does_not_create_empty_result(self) -> None:
        event = FakeEvent()

        _stop_event_silently(event)

        self.assertTrue(event._force_stopped)
        self.assertFalse(event.stop_event_called)
        self.assertIsNone(event.result)


if __name__ == "__main__":
    unittest.main()
