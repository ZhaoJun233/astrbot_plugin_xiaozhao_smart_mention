from __future__ import annotations

import unittest

from main import Main


class FakeEvent:
    def __init__(
        self,
        *,
        group_id: str = "group-a",
        sender_id: str = "user-a",
        self_id: str = "bot-a",
    ) -> None:
        self.unified_msg_origin = f"aiocqhttp:GroupMessage:{group_id}"
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id


def build_plugin(config=None) -> Main:
    plugin = Main.__new__(Main)
    Main.__init__(plugin, context=None, config=config or {})
    return plugin


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


if __name__ == "__main__":
    unittest.main()
