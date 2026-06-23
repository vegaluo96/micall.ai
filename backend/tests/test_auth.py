"""C 端账号鉴权（注册/登录/会话/计费）—— docs/02 §5 + 铁律2。

不依赖网络/DB：用 InMemoryRepository 验证 auth 逻辑与仓储账号方法（PgRepository 同接口，线上联调）。
"""
import unittest

from micall.memory import InMemoryRepository
from micall.server import auth


class AuthFlowTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_password_hash_roundtrip(self):
        h = auth.hash_password("hunter2")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))
        self.assertNotIn("hunter2", h)                     # 明文不落库
        self.assertTrue(auth.verify_password("hunter2", h))
        self.assertFalse(auth.verify_password("wrong", h))

    def test_register_then_login(self):
        code, body = auth.register(self.repo, "a@b.com", "secret1")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["token"])
        self.assertEqual(body["user"]["email"], "a@b.com")
        self.assertEqual(body["user"]["remaining_seconds"], auth.REGISTER_GIFT_SECONDS)  # 送 60 分钟
        self.assertNotIn("password_hash", body["user"])     # 绝不外泄哈希

        code, lo = auth.login(self.repo, "a@b.com", "secret1")
        self.assertEqual(code, 200)
        self.assertEqual(lo["user"]["user_id"], body["user"]["user_id"])

    def test_register_rejects_bad_input_and_dup(self):
        self.assertEqual(auth.register(self.repo, "nope", "secret1")[0], 400)   # 邮箱格式
        self.assertEqual(auth.register(self.repo, "a@b.com", "123")[0], 400)    # 密码太短
        self.assertEqual(auth.register(self.repo, "a@b.com", "secret1")[0], 200)
        self.assertEqual(auth.register(self.repo, "A@B.com", "secret1")[0], 409)  # 邮箱去重（大小写不敏感）

    def test_login_wrong_password(self):
        auth.register(self.repo, "a@b.com", "secret1")
        self.assertEqual(auth.login(self.repo, "a@b.com", "nope")[0], 401)
        self.assertEqual(auth.login(self.repo, "ghost@b.com", "secret1")[0], 401)

    def test_guest_trial_per_ip(self):
        ip = "203.0.113.7"
        self.assertEqual(self.repo.guest_trial_remaining(ip, 60), 60)   # 新 IP 满额
        self.repo.consume_guest_trial(ip, 60)                            # 用满 1 分钟
        self.assertEqual(self.repo.guest_trial_remaining(ip, 60), 0)     # 刷新不再给
        self.repo.consume_guest_trial(ip, 30)
        self.assertEqual(self.repo.guest_trial_remaining(ip, 60), 0)     # 钳到 0
        self.assertEqual(self.repo.guest_trial_remaining("198.51.100.9", 60), 60)  # 别的 IP 独立

    def test_change_password(self):
        token = auth.register(self.repo, "a@b.com", "secret1")[1]["token"]
        self.assertEqual(auth.change_password(self.repo, token, "short")[0], 400)   # 太短
        self.assertEqual(auth.change_password(self.repo, "bad-token", "newsecret")[0], 401)
        self.assertEqual(auth.change_password(self.repo, token, "newsecret")[0], 200)
        self.assertEqual(auth.login(self.repo, "a@b.com", "secret1")[0], 401)        # 旧密码失效
        self.assertEqual(auth.login(self.repo, "a@b.com", "newsecret")[0], 200)      # 新密码可登录

    def test_me_and_logout(self):
        token = auth.register(self.repo, "a@b.com", "secret1")[1]["token"]
        code, me = auth.me(self.repo, token)
        self.assertEqual(code, 200)
        self.assertEqual(me["user"]["email"], "a@b.com")

        self.assertEqual(auth.logout(self.repo, token)[0], 200)
        self.assertEqual(auth.me(self.repo, token)[0], 401)        # 登出后 token 失效
        self.assertEqual(auth.me(self.repo, "garbage")[0], 401)

    def test_billing_balance(self):
        uid = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        self.assertEqual(self.repo.remaining_seconds(uid), 3600)
        self.assertEqual(self.repo.add_seconds(uid, -120, "call"), 3480)   # 扣 2 分钟
        self.assertEqual(self.repo.add_seconds(uid, 600, "recharge"), 4080)
        self.assertEqual(self.repo.add_seconds(uid, -99999, "call"), 0)    # 钳到 ≥0

    def test_calls_and_ledger_history(self):
        uid = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        self.repo.add_call(uid, "c0", "heart", 728, "ended")
        self.repo.add_call(uid, "c2", "chat", 261, "out_of_minutes")
        self.repo.add_seconds(uid, -120, "call")

        calls = self.repo.list_calls(uid)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["character_id"], "c2")            # 新→旧
        self.assertEqual(calls[0]["ended_reason"], "out_of_minutes")
        self.assertEqual(calls[1]["duration_seconds"], 728)

        bills = self.repo.list_ledger(uid)                          # 含注册赠送 + 扣费
        reasons = [b["reason"] for b in bills]
        self.assertIn("register_gift", reasons)
        self.assertEqual(bills[0]["reason"], "call")                # 最新在前
        self.assertEqual(bills[0]["delta_seconds"], -120)

        # 隔离：别的用户看不到这些记录
        other = auth.register(self.repo, "x@y.com", "secret1")[1]["user"]["user_id"]
        self.assertEqual(self.repo.list_calls(other), [])

    def test_admin_aggregates(self):
        u1 = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        u2 = auth.register(self.repo, "c@d.com", "secret1")[1]["user"]["user_id"]
        self.repo.add_call(u1, "c0", "heart", 600, "ended")    # 10 分钟
        self.repo.add_call(u1, "c0", "chat", 300, "ended")     # c0 ×2
        self.repo.add_call(u2, "c2", "chat", 120, "ended")

        stats = self.repo.admin_stats()
        self.assertEqual(stats["total_users"], 2)
        self.assertEqual(stats["calls_today"], 3)
        self.assertEqual(stats["total_minutes"], 17)           # (600+300+120)//60
        self.assertEqual(stats["month_revenue_cents"], 0)      # 无订单

        users = self.repo.list_all_users()
        self.assertEqual(len(users), 2)
        self.assertTrue(all("email" in u and "total_calls" in u for u in users))

        calls = self.repo.list_all_calls()
        self.assertEqual(len(calls), 3)
        self.assertIn(calls[0]["user_email"], ("a@b.com", "c@d.com"))   # 带上了邮箱

        top = self.repo.top_characters()
        self.assertEqual(top[0], {"character_id": "c0", "calls": 2})    # c0 通话最多

    def test_redeem_codes(self):
        uid = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        uid2 = auth.register(self.repo, "b@b.com", "secret1")[1]["user"]["user_id"]
        # 自定义码 WELCOME，值 10 分钟，可用 2 份
        ok, _ = self.repo.create_redeem_code("WELCOME", 600, 2)
        self.assertTrue(ok)
        self.assertFalse(self.repo.create_redeem_code("welcome", 600, 1)[0])   # 同码（大小写归一）不可重复创建

        ok1, bal1, _ = self.repo.redeem_code(uid, "welcome")           # 大小写不敏感
        self.assertTrue(ok1)
        self.assertEqual(bal1, 3600 + 600)

        ok_dup, _, msg_dup = self.repo.redeem_code(uid, "WELCOME")     # 同一人不能再用
        self.assertFalse(ok_dup)
        self.assertIn("已使用过", msg_dup)

        ok2, bal2, _ = self.repo.redeem_code(uid2, "WELCOME")          # 第二个人用第 2 份
        self.assertTrue(ok2)
        self.assertEqual(bal2, 3600 + 600)

        self.repo.create_user("u_z", "z@z.com", "h")
        ok3, _, msg3 = self.repo.redeem_code("u_z", "WELCOME")         # 第三个人 → 份数用完
        self.assertFalse(ok3)
        self.assertIn("用完", msg3)

        self.assertFalse(self.repo.redeem_code(uid, "NOPE")[0])        # 无效码

        listed = self.repo.list_redeem_codes()
        self.assertEqual(listed[0]["code"], "WELCOME")
        self.assertEqual(listed[0]["used_count"], 2)
        self.assertEqual(listed[0]["max_uses"], 2)

    def test_tickets(self):
        uid = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        tid = self.repo.add_ticket(uid, "功能异常", "通话有杂音")
        self.assertTrue(tid)

        mine = self.repo.list_user_tickets(uid)
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["status"], "open")
        self.assertEqual(mine[0]["reply"], "")

        allt = self.repo.list_all_tickets()
        self.assertEqual(allt[0]["user_email"], "a@b.com")             # 后台看得到提交人

        self.assertTrue(self.repo.reply_ticket(tid, "已优化降噪，补 30 分钟"))
        mine2 = self.repo.list_user_tickets(uid)
        self.assertEqual(mine2[0]["status"], "replied")                # 用户看到回复
        self.assertIn("降噪", mine2[0]["reply"])
        self.assertFalse(self.repo.reply_ticket(999999, "x"))          # 不存在

    def test_invites(self):
        inviter = auth.register(self.repo, "boss@b.com", "secret1")[1]["user"]["user_id"]
        code = self.repo.get_invite_code(inviter)
        self.assertTrue(code.startswith("MI"))
        self.assertEqual(self.repo.get_invite_code(inviter), code)     # 稳定，不重复生成

        # 被邀请人带码注册 → 双方各 +60 分钟
        code2, body = auth.register(self.repo, "new@b.com", "secret1", code)
        self.assertEqual(code2, 200)
        invitee = body["user"]["user_id"]
        self.assertEqual(self.repo.remaining_seconds(inviter), 3600 + 3600)   # 注册 + 邀请奖励
        self.assertEqual(self.repo.remaining_seconds(invitee), 3600 + 3600)

        st = self.repo.invite_stats(inviter)
        self.assertEqual(st["invited"], 1)
        self.assertEqual(st["reward_seconds"], 3600)

        # 同一被邀请人不能再被邀请；不能用自己的码
        self.assertFalse(self.repo.apply_invite(invitee, code, 3600)[0])
        self.assertFalse(self.repo.apply_invite(inviter, code, 3600)[0])
        self.assertFalse(self.repo.apply_invite("u_x", "MIBOGUS", 3600)[0])

        recs = self.repo.list_all_invites()
        self.assertEqual(recs[0]["inviter_email"], "boss@b.com")
        self.assertEqual(recs[0]["invitee_email"], "new@b.com")

    def test_usage_cost(self):
        uid = auth.register(self.repo, "a@b.com", "secret1")[1]["user"]["user_id"]
        self.repo.add_call(uid, "lin_wan", "heart", 600, "ended")     # 10 分钟通话
        self.repo.add_usage(uid, "llm_fast", 5000, 10000)             # 0.01 美元
        self.repo.add_usage(uid, "tts", 800, 16000)                   # 0.016 美元
        self.repo.add_usage(uid, "asr", 600, 60000)                   # 0.06 美元

        cs = self.repo.cost_summary()
        self.assertEqual(cs["today_micros"], 86000)                   # 合计 0.086 美元
        self.assertEqual(cs["month_micros"], 86000)
        self.assertEqual(cs["by_node"]["asr"], 60000)
        self.assertEqual(cs["per_100min_micros"], round(86000 / (10 / 100)))  # 按今日 10 分钟摊


if __name__ == "__main__":
    unittest.main()
