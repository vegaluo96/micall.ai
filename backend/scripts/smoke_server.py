"""端到端冒烟：真起 WS 信令服务器 + 客户端走一遍协议，验证骨架可替换前端 Mock。

需 websockets（requirements）。运行：cd backend && PYTHONPATH=src python3 scripts/smoke_server.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from micall.config import load_config  # noqa: E402
from micall.server import SignalingServer  # noqa: E402


async def main() -> int:
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    srv = SignalingServer(load_config())
    events: list[dict] = []
    async with serve(srv.handle, "127.0.0.1", 8799):
        async with connect("ws://127.0.0.1:8799/realtime/signal") as ws:
            await ws.send(json.dumps({"type": "start_call", "character_id": "vega", "scenario": "chat"}))
            await ws.send(json.dumps({"type": "text_input", "text": "今天有点累"}))
            # 收集到「≥2 句 AI 字幕 且 ≥1 个 billing（需跨过 1 秒计费心跳）」或总超时。
            deadline = asyncio.get_event_loop().time() + 3.5
            while asyncio.get_event_loop().time() < deadline:
                try:
                    ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5))
                except asyncio.TimeoutError:
                    break
                events.append(ev)
                ai = sum(1 for e in events if e["type"] == "subtitle" and e.get("role") == "ai")
                bill = sum(1 for e in events if e["type"] == "billing")
                if ai >= 2 and bill >= 1:
                    break
            await ws.send(json.dumps({"type": "end_call"}))
            try:
                events.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0)))
            except asyncio.TimeoutError:
                pass

    types = [e["type"] for e in events]
    ai = [e for e in events if e["type"] == "subtitle" and e.get("role") == "ai"]
    emo = [e for e in events if e["type"] == "emotion"]
    checks = {
        "connected": "connected" in types,
        "emotion piggyback": bool(emo) and emo[0].get("tag") == "tender",
        "ai subtitles (>=2 句切分)": len(ai) >= 2,
        "billing 推送": any(e["type"] == "billing" for e in events),
        "状态机驱动": {"thinking", "speaking", "listening"}.issubset(
            {e.get("phase") for e in events if e["type"] == "state"}
        ),
    }
    print("收到事件序列：", types)
    ok = True
    for name, passed in checks.items():
        print(f"  [{'✓' if passed else '✗'}] {name}")
        ok = ok and passed
    print("\nE2E", "通过 — 骨架可替换前端 Mock。" if ok else "失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
