import os
import unittest

from micall.config import NODE_KEYS, load_config, resolve_runtime, resolve_voice


class TestConfig(unittest.TestCase):
    def test_load_defaults(self):
        c = load_config()
        self.assertEqual(set(c.nodes), set(NODE_KEYS))
        # 占位配置无密钥 → 节点未配置（回退 stub）。
        self.assertFalse(c.node("llm_fast").configured)

    def test_env_secret_injection(self):
        os.environ["MICALL_LLM_FAST_ENDPOINT"] = "https://api.example/v1/chat/completions"
        os.environ["MICALL_LLM_FAST_API_KEY"] = "sk-test"
        try:
            c = load_config()
            node = c.node("llm_fast")
            self.assertTrue(node.configured)
            self.assertEqual(node.endpoint, "https://api.example/v1/chat/completions")
            self.assertEqual(node.api_key, "sk-test")
        finally:
            del os.environ["MICALL_LLM_FAST_ENDPOINT"]
            del os.environ["MICALL_LLM_FAST_API_KEY"]

    def test_resolve_runtime_priority(self):
        g = {"tts_model": "global_tts", "memory_depth": 5, "reply_max_tokens": 256}
        out = resolve_runtime(g, {"tts_model": "char_tts"}, {"reply_max_tokens": 128})
        self.assertEqual(out["tts_model"], "char_tts")       # 角色 > 全局
        self.assertEqual(out["reply_max_tokens"], 128)       # 用户 > 全局
        self.assertEqual(out["memory_depth"], 5)             # 未覆盖 → 全局

    def test_resolve_runtime_skips_none(self):
        g = {"tts_model": "a", "memory_depth": 5}
        out = resolve_runtime(g, {"tts_model": None}, None)  # None 视为未设
        self.assertEqual(out["tts_model"], "a")

    def test_resolve_voice(self):
        self.assertEqual(resolve_voice("g", "c", "u"), "u")   # 用户自定义优先
        self.assertEqual(resolve_voice("g", "c", None), "c")  # 退角色默认
        self.assertEqual(resolve_voice("g", None, ""), "g")   # 退全局默认


if __name__ == "__main__":
    unittest.main()
