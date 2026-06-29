"""IP 归属地解析：内网/本机/非法 IP 给固定标签且不外呼；批量解析对这些也走纯本地。"""
import unittest

from micall.server import ip_geo


class TestIpGeo(unittest.TestCase):
    def test_local_and_private_labels(self):
        self.assertEqual(ip_geo.ip_location("127.0.0.1"), "本机")
        self.assertEqual(ip_geo.ip_location("::1"), "本机")
        self.assertEqual(ip_geo.ip_location("192.168.1.10"), "内网")
        self.assertEqual(ip_geo.ip_location("10.0.0.5"), "内网")
        self.assertEqual(ip_geo.ip_location("172.16.3.4"), "内网")

    def test_empty_and_invalid(self):
        self.assertEqual(ip_geo.ip_location(""), "")
        self.assertEqual(ip_geo.ip_location("   "), "")
        self.assertEqual(ip_geo.ip_location("not-an-ip"), "未知")

    def test_batch_resolves_specials_without_network(self):
        # 全是内网/本机/非法 → 不触发外呼，直接给标签。
        out = ip_geo.ip_locations(["127.0.0.1", "192.168.0.1", "", "bad", "127.0.0.1"])
        self.assertEqual(out["127.0.0.1"], "本机")
        self.assertEqual(out["192.168.0.1"], "内网")
        self.assertEqual(out["bad"], "未知")
        self.assertNotIn("", out)   # 空 IP 跳过


if __name__ == "__main__":
    unittest.main()
