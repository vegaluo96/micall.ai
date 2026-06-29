"""同意留痕（合规）：record_consent 落库（版本+账号/游客+IP），base 默认 no-op 不报错。"""
import unittest

from micall.memory import InMemoryRepository


class TestConsent(unittest.TestCase):
    def test_inmemory_records_consent(self):
        r = InMemoryRepository()
        r.record_consent("cookie", "2026-06", user_id="u1", ip="203.0.113.5")
        r.record_consent("register", "2026-06", ip="203.0.113.6")   # 游客（无 user_id）
        rows = r._consents
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kind"], "cookie")
        self.assertEqual(rows[0]["user_id"], "u1")
        self.assertEqual(rows[0]["version"], "2026-06")
        self.assertEqual(rows[1]["user_id"], "")   # 游客留空


if __name__ == "__main__":
    unittest.main()
