import unittest

from micall.protocol import (
    SERVER_EVENT_TYPES,
    ServerEvent,
    parse_client_message,
)


class TestServerEvent(unittest.TestCase):
    def test_shapes_match_frontend(self):
        self.assertEqual(ServerEvent.connected(), {"type": "connected"})
        self.assertEqual(ServerEvent.state("listening"), {"type": "state", "phase": "listening"})
        self.assertEqual(ServerEvent.interrupted(), {"type": "interrupted"})
        self.assertEqual(ServerEvent.emotion("tender"), {"type": "emotion", "tag": "tender"})
        self.assertEqual(
            ServerEvent.billing(700, 12),
            {"type": "billing", "remaining_seconds": 700, "elapsed": 12},
        )
        self.assertEqual(ServerEvent.out_of_minutes(), {"type": "out_of_minutes"})
        self.assertEqual(ServerEvent.call_failed("network"), {"type": "call_failed", "reason": "network"})

    def test_subtitle_partial_optional(self):
        self.assertNotIn("partial", ServerEvent.subtitle("ai", "hi"))
        self.assertTrue(ServerEvent.subtitle("user", "hi", partial=True)["partial"])

    def test_subtitle_dur_optional(self):
        # dur(这句预估说出时长，秒)：给了才带，前端据此逐字揭开字幕跟住语音；0/缺省不带。
        self.assertNotIn("dur", ServerEvent.subtitle("ai", "hi"))
        self.assertNotIn("dur", ServerEvent.subtitle("ai", "hi", dur=0))
        self.assertEqual(ServerEvent.subtitle("ai", "hi", dur=1.234)["dur"], 1.23)

    def test_all_factories_in_enum(self):
        for ev in (
            ServerEvent.connected(), ServerEvent.state("speaking"), ServerEvent.interrupted(),
            ServerEvent.subtitle("ai", "x"), ServerEvent.emotion("t"), ServerEvent.billing(1, 1),
            ServerEvent.low_minutes(60), ServerEvent.out_of_minutes(),
            ServerEvent.call_failed("r"), ServerEvent.ended(),
        ):
            self.assertIn(ev["type"], SERVER_EVENT_TYPES)


class TestClientMessage(unittest.TestCase):
    def test_parse_valid(self):
        m = parse_client_message('{"type":"start_call","character_id":"lin_wan","scenario":"heart"}')
        self.assertEqual(m.type, "start_call")
        self.assertEqual(m.character_id, "lin_wan")
        self.assertEqual(m.scenario, "heart")

    def test_parse_dict_and_fields(self):
        m = parse_client_message({"type": "mute", "on": True})
        self.assertEqual(m.type, "mute")
        self.assertTrue(m.on)

    def test_parse_rejects_bad(self):
        self.assertIsNone(parse_client_message("not json"))
        self.assertIsNone(parse_client_message('{"type":"bogus"}'))
        self.assertIsNone(parse_client_message('{"no":"type"}'))
        self.assertIsNone(parse_client_message("[1,2,3]"))


if __name__ == "__main__":
    unittest.main()
