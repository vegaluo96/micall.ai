"""热路径性能优化的回归测试：
  ① Embedding 进程级连接池复用（少一次到新加坡的握手 → 每轮召回更快）。
  ② 麦克风上行队列有界 + 丢最旧（防积压「越聊越延迟」、永远喂最新音频）。
"""
import asyncio
import unittest

import micall.providers.bailian_embedding as be
from micall.session.state import Phase
from tests.test_orchestrator import _make_session


@unittest.skipUnless(be.httpx is not None, "httpx 未安装（仅运行时依赖）")
class TestEmbeddingSharedClient(unittest.TestCase):
    def test_shared_client_reused(self):
        be._SHARED_CLIENT = None  # 干净起点
        c1 = be._shared_client()
        c2 = be._shared_client()
        try:
            self.assertIs(c1, c2)              # 同一进程级客户端 → 复用 keep-alive
            self.assertFalse(c1.is_closed)
        finally:
            asyncio.run(c1.aclose())
            be._SHARED_CLIENT = None

    def test_shared_client_rebuilt_after_close(self):
        be._SHARED_CLIENT = None
        c1 = be._shared_client()
        asyncio.run(c1.aclose())              # 关掉后下次取应新建（不会拿到已关客户端）
        c2 = be._shared_client()
        try:
            self.assertIsNot(c1, c2)
            self.assertFalse(c2.is_closed)
        finally:
            asyncio.run(c2.aclose())
            be._SHARED_CLIENT = None


class TestMicQueueBounded(unittest.TestCase):
    def _active_session(self):
        async def emit(ev):
            pass
        s = _make_session(emit)
        s.sm.to(Phase.CALLING)
        s.sm.to(Phase.LISTENING)   # active 才收上行帧
        return s

    def test_drops_oldest_keeps_latest(self):
        s = self._active_session()
        maxn = s._mic_q.maxsize
        self.assertEqual(maxn, 64)
        total = maxn + 36          # 灌超出上限：100 帧
        for i in range(total):
            s.push_audio(str(i).encode())
        # 队列被钳在上限，且保留的是「最新的 maxn 帧」（最旧的被丢）。
        self.assertEqual(s._mic_q.qsize(), maxn)
        head = s._mic_q.get_nowait()                 # 队首 = 最旧的「未被丢」帧
        self.assertEqual(head, str(total - maxn).encode())   # = b"36"
        # 一路取到底，确认队尾是最后灌进去的那帧（最新音频没被丢）。
        last = head
        while s._mic_q.qsize():
            last = s._mic_q.get_nowait()
        self.assertEqual(last, str(total - 1).encode())      # = b"99"

    def test_sentinel_insertable_when_full(self):
        s = self._active_session()
        for i in range(s._mic_q.maxsize):
            s.push_audio(str(i).encode())
        self.assertTrue(s._mic_q.full())
        asyncio.run(s.end(emit_ended=False))   # 满队列下挂断：哨兵 None 仍要塞得进（收尾不丢）
        # 收尾后队列里能取到哨兵 None（中间帧可能被腾位丢弃，但 None 一定在）。
        seen_none = False
        while s._mic_q.qsize():
            if s._mic_q.get_nowait() is None:
                seen_none = True
        self.assertTrue(seen_none)


if __name__ == "__main__":
    unittest.main()
