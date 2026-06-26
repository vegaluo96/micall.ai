"""后台「角色管理」读写 —— 出厂 spec + overrides 合并、白名单字段、生效（docs/01 + 铁律7）。

不碰真实 overrides 文件：把 CHAR_OVERRIDES_PATH 指到临时文件。
"""
import tempfile
import unittest
from pathlib import Path

from micall.server import characters_admin as ca


class TestCharactersAdmin(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "character_overrides.json"
        self._orig = ca.CHAR_OVERRIDES_PATH
        ca.CHAR_OVERRIDES_PATH = self.tmp

    def tearDown(self):
        ca.CHAR_OVERRIDES_PATH = self._orig
        if self.tmp.exists():
            self.tmp.unlink()

    def test_read_lists_factory_characters(self):
        rows = ca.read_characters_for_admin()
        ids = {r["id"] for r in rows}
        self.assertIn("lin_wan", ids)
        lw = next(r for r in rows if r["id"] == "lin_wan")
        self.assertEqual(lw["name"], "林晚")
        self.assertIn("温柔", lw["traits"])        # 列表字段 join 成可编辑串

    def test_write_then_effective_and_read_reflect(self):
        ca.write_character_from_admin({
            "id": "lin_wan", "background_story": "改过的来历",
            "traits": "冷静、犀利", "voice_id": "male-qn-qingse",
            "speaking_style": "短句、克制",
        })
        eff = ca.effective_specs()["lin_wan"]
        self.assertEqual(eff["persona"]["background_story"], "改过的来历")
        self.assertEqual(eff["persona"]["core_traits"], ["冷静", "犀利"])  # 串拆回列表
        self.assertEqual(eff["persona"]["speaking_style"], "短句、克制")
        self.assertEqual(eff["voice"]["voice_id"], "male-qn-qingse")
        lw = next(r for r in ca.read_characters_for_admin() if r["id"] == "lin_wan")
        self.assertEqual(lw["voice_id"], "male-qn-qingse")
        self.assertEqual(lw["background_story"], "改过的来历")

    def test_partial_edit_keeps_other_fields(self):
        ca.write_character_from_admin({"id": "lin_wan", "voice_id": "female-yujie"})
        eff = ca.effective_specs()["lin_wan"]
        self.assertEqual(eff["voice"]["voice_id"], "female-yujie")
        self.assertEqual(eff["identity"]["name"], "林晚")          # 没动的字段保留
        self.assertTrue(eff["persona"].get("core_traits"))         # 出厂人设还在

    def test_identity_fields_persist_and_reach_prompt(self):
        # 用户实测：后台改年龄等「基础资料」对不上通话——过去 write 根本不存身份字段。
        ca.write_character_from_admin({
            "id": "lin_wan", "gender": "女", "age": "18",
            "nationality": "中国", "height": "156", "weight": "44", "birthday": "2006-01-01", "race": "东亚人",
        })
        eff = ca.effective_specs()["lin_wan"]
        self.assertEqual(eff["identity"]["age"], 18)              # 纯数字存成数字
        self.assertEqual(eff["identity"]["profile"]["height_cm"], 156)
        self.assertEqual(eff["identity"]["profile"]["birthday"], "2006-01-01")
        # 后台列表回显真值（而非写死 mock）
        lw = next(r for r in ca.read_characters_for_admin() if r["id"] == "lin_wan")
        self.assertEqual(lw["age"], 18)
        self.assertEqual(lw["height"], 156)
        # 真正落进通话系统提示词
        from micall.context import CharacterRuntime, ContextAssembler
        char = CharacterRuntime.from_spec(eff)
        sysmsg = ContextAssembler(char).build(
            character_id="lin_wan", scenario="", history=[{"role": "user", "content": "你多大"}])[0]["content"]
        self.assertIn("18岁", sysmsg)
        self.assertIn("身高156cm", sysmsg)

    def test_prompt_extra_persists_and_reaches_prompt(self):
        # 「本角色口吻提示」此前前端完全没接（admin/src 0 引用）；现已接通 state+表单+save。
        # 验证后端写入 → runtime_overrides.realtime_prompt_extra → 真正落进通话系统提示词。
        ca.write_character_from_admin({"id": "lin_wan", "prompt_extra": "多用短句，偶尔毒舌"})
        eff = ca.effective_specs()["lin_wan"]
        self.assertEqual(eff["runtime_overrides"]["realtime_prompt_extra"], "多用短句，偶尔毒舌")
        lw = next(r for r in ca.read_characters_for_admin() if r["id"] == "lin_wan")
        self.assertEqual(lw["prompt_extra"], "多用短句，偶尔毒舌")   # 后台列表回显
        from micall.context import CharacterRuntime, ContextAssembler
        char = CharacterRuntime.from_spec(eff)
        sysmsg = ContextAssembler(char).build(
            character_id="lin_wan", scenario="", history=[{"role": "user", "content": "在吗"}])[0]["content"]
        self.assertIn("多用短句，偶尔毒舌", sysmsg)

    def test_nonnumeric_age_is_rejected_not_stored(self):
        # num() 此前对 "abc" 原样返回 → 会把非数字落进 identity（提示词出现「年龄abc」）。现应跳过、保留出厂值。
        ca.write_character_from_admin({"id": "lin_wan", "age": "abc", "height": "拾陆"})
        eff = ca.effective_specs()["lin_wan"]
        self.assertNotEqual(eff["identity"].get("age"), "abc")
        self.assertNotEqual((eff["identity"].get("profile") or {}).get("height_cm"), "拾陆")

    def test_long_text_fields_are_capped(self):
        # 文本字段无上限会撑爆系统提示词；现按字段封顶（background_story 4000）。
        ca.write_character_from_admin({"id": "lin_wan", "background_story": "床" * 5000})
        eff = ca.effective_specs()["lin_wan"]
        self.assertEqual(len(eff["persona"]["background_story"]), 4000)

    def test_write_rejects_unknown_id(self):
        with self.assertRaises(ValueError):
            ca.write_character_from_admin({"id": "nope", "name": "x"})

    def test_factory_spec_on_disk_unchanged(self):
        ca.write_character_from_admin({"id": "lin_wan", "name": "改名"})
        self.assertEqual(ca.factory_specs()["lin_wan"]["identity"]["name"], "林晚")  # 出厂文件不动


class TestRuntimePicksUpOverride(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "character_overrides.json"
        self._orig = ca.CHAR_OVERRIDES_PATH
        ca.CHAR_OVERRIDES_PATH = self.tmp

    def tearDown(self):
        ca.CHAR_OVERRIDES_PATH = self._orig
        if self.tmp.exists():
            self.tmp.unlink()

    def test_load_characters_reflects_override(self):
        from micall.server.wsserver import _load_characters
        ca.write_character_from_admin({"id": "lin_wan", "voice_id": "audiobook_male_2"})
        chars = _load_characters()
        self.assertEqual(chars["lin_wan"].voice_id, "audiobook_male_2")  # 通话端拿到改后的音色


if __name__ == "__main__":
    unittest.main()
