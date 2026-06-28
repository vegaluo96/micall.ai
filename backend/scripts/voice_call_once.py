"""真实语音通话联调（不依赖前端 UI）—— 把音频文件当麦克风「实时」流给后端，
收 ASR/AI 字幕 + 下行 TTS 音频存文件。一把验证后端语音闭环：ASR → LLM → TTS。

需后端在跑（asr/llm/tts 已配 key），本机有 websockets + ffmpeg。
用法：
  cd backend
  # 没有样本就先合一句：PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3
  PYTHONPATH=src python3 scripts/voice_call_once.py sample.mp3 reply.mp3
然后把 reply.mp3 下载试听——那是 AI 真实生成 + 合成的回话。
"""
import asyncio
import json
import struct
import subprocess
import sys
from pathlib import Path

SR = 16000
FRAME_MS = 100
FRAME_BYTES = SR * 2 * FRAME_MS // 1000  # 16k×2字节×0.1s = 3200
TTS_RATE = 24000  # 下行 TTS 是 PCM16 单声道 @ 24k（与 config tts.sample_rate 一致）


def _wav(pcm: bytes, rate: int = TTS_RATE, ch: int = 1, bits: int = 16) -> bytes:
    n = len(pcm)
    return (b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE" + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits)
            + b"data" + struct.pack("<I", n) + pcm)


def _pcm16(path: str) -> bytes:
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le",
           "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SR), "-"]
    try:
        return subprocess.run(cmd, capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise SystemExit("需要 ffmpeg：sudo apt install -y ffmpeg")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"ffmpeg 转码失败：{e.stderr.decode('utf-8', 'ignore')[:300]}")


async def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "sample.mp3"
    out = sys.argv[2] if len(sys.argv) > 2 else "reply.wav"  # 下行是 PCM → 存成 WAV 可直接试听
    if not Path(src).exists():
        raise SystemExit(f"找不到 {src}。先用 tts_once 合一个 sample.mp3。")
    pcm = _pcm16(src)
    pcm = pcm + b"\x00\x00" * int(SR * 1.2)  # 尾部补 1.2s 静音 → server_vad 判到"说完"才结句
    from websockets.asyncio.client import connect

    audio = bytearray()
    got_ai = False
    print(f"麦克风音频 {src} → pcm16/16k/mono {len(pcm)} bytes（{len(pcm) / (SR * 2):.1f}s）\n")
    async with connect("ws://127.0.0.1:8787/realtime/signal", max_size=None) as ws:
        await ws.send(json.dumps(
            {"type": "start_call", "character_id": "vega", "scenario": "chat"}))

        async def sender() -> None:
            await asyncio.sleep(0.4)  # 等 connected
            n = (len(pcm) + FRAME_BYTES - 1) // FRAME_BYTES
            for i in range(n):
                await ws.send(pcm[i * FRAME_BYTES:(i + 1) * FRAME_BYTES])
                await asyncio.sleep(FRAME_MS / 1000)  # 实时节奏喂帧（贴近真实判句）

        send_task = asyncio.create_task(sender())
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)  # 静默 8s 即收尾
                if isinstance(raw, (bytes, bytearray)):
                    audio += raw
                    continue
                ev = json.loads(raw)
                t = ev.get("type")
                if t == "subtitle":
                    who = "你" if ev.get("role") == "user" else "林晚"
                    tag = "（识别中）" if ev.get("partial") else ""
                    print(f"  {who}{tag}: {ev['text']}")
                    if ev.get("role") == "ai":
                        got_ai = True
                elif t == "emotion":
                    print(f"  [情绪] {ev['tag']}")
                elif t == "call_failed":
                    print(f"  ⚠ 接通失败：{ev.get('reason')}")
                    break
        except asyncio.TimeoutError:
            pass  # 8s 无新事件 → 一轮结束
        finally:
            send_task.cancel()
            try:
                await send_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await ws.send(json.dumps({"type": "end_call"}))
            except Exception:
                pass

    if audio:
        Path(out).write_bytes(_wav(bytes(audio)))  # PCM → WAV
        print(f"\n✅ AI 回复语音已存 {out}（PCM {len(audio)} bytes）。下载试听 —— 这是真实闭环产物。")
    elif got_ai:
        print("\n⚠ 收到 AI 文字但没拿到下行音频。看后端日志：TTS 是否配好 / audio_emit 是否触发。")
    else:
        print("\n⚠ 没收到 AI 回复 —— 多半 ASR 没识别出文本。后端 journalctl 看 task A / task-failed。")


if __name__ == "__main__":
    asyncio.run(main())
