from __future__ import annotations

import asyncio
import unittest
from time import monotonic

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
