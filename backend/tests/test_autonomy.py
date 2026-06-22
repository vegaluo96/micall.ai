import asyncio
import json
import unittest

from micall.context.models import AutonomousState, CharacterRuntime
from micall.memory import InMemoryRepository
from micall.offline import (
    AutonomyEngine,
    build_autonomy_prompt,
    describe_gap,
    parse_autonomous_state,
)
from micall.providers import StubLLM


class TestGap(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(describe_gap(2), "才几个小时")
        self.assertEqual(describe_gap(30), "一两天")
        self.assertEqual(describe_gap(72), "好几天")
        self.assertEqual(describe_gap(24 * 10), "一周多")


class TestPrompt(unittest.TestCase):
    def test_prompt_independence_and_gap(self):
        char = CharacterRuntime("lin_wan", "林晚", {"core_traits": ["温柔"]})
        msgs = build_autonomy_prompt(char, 24 * 8)
        sys = msgs[0]["content"]
        self.assertIn("林晚", sys)
        self.assertIn("独立", sys)          # 状态独立于用户需求
        self.assertIn("一周多", sys)         # 间隔粒度注入


class TestParse(unittest.TestCase):
    def test_parse_state(self):
        s = parse_autonomous_state('{"mood":"有点低落","recent_experience":"搬了家","energy":"有点累"}')
        self.assertEqual(s.mood, "有点低落")
        self.assertEqual(s.recent_experience, "搬了家")
        self.assertEqual(s.energy, "有点累")

    def test_parse_garbage(self):
        s = parse_autonomous_state("没有 JSON")
        self.assertEqual((s.mood, s.recent_experience, s.energy), ("", "", ""))


class TestEngine(unittest.TestCase):
    def test_advance_persists_per_character(self):
        repo = InMemoryRepository()
        state = {"mood": "话比平时多", "recent_experience": "看了场喜欢的演出", "energy": "还行"}
        engine = AutonomyEngine(StubLLM([json.dumps(state, ensure_ascii=False)]), repo)
        char = CharacterRuntime("lin_wan", "林晚", {"core_traits": ["温柔"]})

        out = asyncio.run(engine.advance(char, hours_since_last_call=72))
        self.assertEqual(out.recent_experience, "看了场喜欢的演出")
        # 持久化（per-character，独立于任何用户）
        self.assertEqual(repo.get_autonomous("lin_wan").mood, "话比平时多")
        # 不串到别的角色
        self.assertEqual(repo.get_autonomous("other"), AutonomousState())


if __name__ == "__main__":
    unittest.main()
