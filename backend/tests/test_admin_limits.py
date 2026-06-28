"""后台联网自检启发式 + 运行限流读写（global_defaults 真知柄，钳到安全区间）。"""
import json
import pathlib
import tempfile
import unittest

from micall.server import adminapi


class TestLooksLive(unittest.TestCase):
    def test_live_when_temp_and_source(self):
        self.assertTrue(adminapi._looks_live("上海现在 26°C，多云。来源 https://weather.com/shanghai"))
        self.assertTrue(adminapi._looks_live("当前气温约 28 度，数据来自中国天气网"))

    def test_not_live_when_model_admits_offline(self):
        self.assertFalse(adminapi._looks_live("作为AI，我无法获取实时天气信息。"))
        self.assertFalse(adminapi._looks_live("我的知识截止于训练数据，没有实时联网能力。"))

    def test_not_live_when_vague_no_number_no_source(self):
        self.assertFalse(adminapi._looks_live("上海这个季节通常比较温暖湿润。"))
        self.assertFalse(adminapi._looks_live(""))


class TestLimitsReadWrite(unittest.TestCase):
    def setUp(self):
        self._orig = adminapi.OVERRIDES_PATH
        self._tmp = pathlib.Path(tempfile.mkdtemp()) / "admin_overrides.json"
        adminapi.OVERRIDES_PATH = self._tmp

    def tearDown(self):
        adminapi.OVERRIDES_PATH = self._orig

    def test_read_shape(self):
        out = adminapi.read_limits_for_admin()
        for k in ("reply_max_tokens", "incall_max_turns", "budget_chars",
                  "world_refresh_hours", "guest_trial_seconds", "register_gift_minutes"):
            self.assertIn(k, out)
        self.assertIsInstance(out["reply_max_tokens"], int)

    def test_write_clamps_and_persists_global_defaults(self):
        adminapi.write_limits_from_admin({
            "reply_max_tokens": 5,          # 钳到下限 40（别截断正常两句）
            "incall_max_turns": 999,        # 钳到上限 60
            "world_refresh_hours": 0.1,     # 钳到下限 1.0
        })
        saved = json.loads(self._tmp.read_text("utf-8"))
        g = saved["global_defaults"]
        self.assertEqual(g["reply_max_tokens"], 40)
        self.assertEqual(g["incall_max_turns"], 60)
        self.assertEqual(g["world_refresh_hours"], 1.0)

    def test_write_only_touches_passed_keys(self):
        # 预置一份别的 override，确保只改传入键、不抹掉无关段
        self._tmp.write_text(json.dumps({"nodes": {"llm_fast": {"model": "x"}}}), "utf-8")
        adminapi.write_limits_from_admin({"reply_max_tokens": 300})
        saved = json.loads(self._tmp.read_text("utf-8"))
        self.assertEqual(saved["nodes"]["llm_fast"]["model"], "x")     # 无关段保留
        self.assertEqual(saved["global_defaults"]["reply_max_tokens"], 300)
        self.assertNotIn("incall_max_turns", saved["global_defaults"])  # 没传就不写


if __name__ == "__main__":
    unittest.main()
