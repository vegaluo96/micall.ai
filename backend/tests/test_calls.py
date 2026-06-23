"""通话记录账号级软删除（用户端删除=隐藏，跨设备一致；后台统计仍计入）。"""
import unittest

from micall.memory.repository import InMemoryRepository


class TestCallSoftDelete(unittest.TestCase):
    def _repo(self) -> InMemoryRepository:
        r = InMemoryRepository()
        r.add_call("u1", "lin_wan", "chat", 30, "ended")
        r.add_call("u1", "lin_wan", "chat", 20, "ended")
        return r

    def test_list_calls_have_ids(self):
        r = self._repo()
        calls = r.list_calls("u1")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("id" in c for c in calls))

    def test_hide_filters_user_list_but_keeps_admin_stats(self):
        r = self._repo()
        target = r.list_calls("u1")[0]["id"]
        self.assertEqual(r.hide_calls("u1", [target]), 1)
        remaining = r.list_calls("u1")
        self.assertEqual(len(remaining), 1)                    # 用户端少一条
        self.assertNotIn(target, [c["id"] for c in remaining])
        self.assertEqual(len(r.list_all_calls()), 2)           # 后台「通话」仍计入隐藏的

    def test_hide_is_per_account(self):
        # 别的用户删不动我的记录
        r = self._repo()
        target = r.list_calls("u1")[0]["id"]
        self.assertEqual(r.hide_calls("u2", [target]), 0)
        self.assertEqual(len(r.list_calls("u1")), 2)

    def test_hide_empty_or_bad_ids(self):
        r = self._repo()
        self.assertEqual(r.hide_calls("u1", []), 0)
        self.assertEqual(r.hide_calls("u1", ["nope"]), 0)
        self.assertEqual(len(r.list_calls("u1")), 2)


if __name__ == "__main__":
    unittest.main()
