import os
import unittest

from micall.config import NODE_KEYS, NodeConfig, as_float, as_int, load_config, resolve_runtime, resolve_voice


class TestSafeCoerce(unittest.TestCase):
    def test_as_int_parses_and_falls_back(self):
        self.assertEqual(as_int("16000", 8000), 16000)
        self.assertEqual(as_int(24000, 8000), 24000)
        self.assertEqual(as_int("24000.0", 8000), 24000)
        self.assertEqual(as_int("abc", 8000), 8000)   # 坏配置回退默认而非崩
        self.assertEqual(as_int("", 8000), 8000)
        self.assertEqual(as_int(None, 8000), 8000)

    def test_as_float_parses_and_falls_back(self):
        self.assertAlmostEqual(as_float("0.55", 0.5), 0.55)
        self.assertAlmostEqual(as_float("x", 0.5), 0.5)
        self.assertAlmostEqual(as_float(None, 0.5), 0.5)


class TestConfig(unittest.TestCase):
    def test_node_strips_header_unsafe_chars(self):
        # 复制粘贴常把 U+2028 行分隔符/不间断空格/零宽/换行带进 key → Authorization 头 ascii 编码崩。
        n = NodeConfig(name="t", endpoint=" https://api.x/v1  ",
                       api_key="sk-ab cd\xa0ef​gh\n")
        self.assertEqual(n.api_key, "sk-abcdefgh")
        self.assertEqual(n.endpoint, "https://api.x/v1")
        # 清洗后能正常进 latin-1/ascii 头，不再抛 UnicodeEncodeError。
        (f"Bearer {n.api_key}").encode("ascii")

    def test_chat_endpoint_normalizes_base_url(self):
        # 用户常把 apiyi/OpenAI 文档的 base_url(.../v1) 当 endpoint 填 → 少了 /chat/completions → 404。
        from micall.providers.apiyi_llm import _chat_endpoint
        self.assertEqual(_chat_endpoint("https://api.apiyi.com/v1"), "https://api.apiyi.com/v1/chat/completions")
        self.assertEqual(_chat_endpoint("https://api.apiyi.com/v1/"), "https://api.apiyi.com/v1/chat/completions")
        # 已是完整路径则原样保留。
        self.assertEqual(_chat_endpoint("https://api.apiyi.com/v1/chat/completions"), "https://api.apiyi.com/v1/chat/completions")

    def test_embed_endpoint_normalizes_base_url(self):
        from micall.providers.bailian_embedding import _embed_endpoint
        self.assertEqual(_embed_endpoint("https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
                         "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/embeddings")
        self.assertTrue(_embed_endpoint("https://x/compatible-mode/v1/embeddings").endswith("/embeddings"))

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
