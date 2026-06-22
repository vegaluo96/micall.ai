"""转写一个音频文件并计时 —— 实测百炼 Qwen3-ASR 从香港的识别延迟。

用法（先把 ASR 的 endpoint/key 写进 micall.env 并 source）：
  cd backend
  set -a; . config/micall.env; set +a
  # 没有现成音频？先用 TTS 合一段当样本：
  #   PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3
  PYTHONPATH=src python3 scripts/asr_once.py sample.mp3

横向对比北京区 vs 新加坡区（香港跨境，新加坡通常更快，但要用国际站独立 key）：
  # 北京区（默认）
  PYTHONPATH=src python3 scripts/asr_once.py sample.mp3
  # 新加坡区（临时覆盖 endpoint+key 再跑）
  MICALL_ASR_ENDPOINT=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions \
  MICALL_ASR_API_KEY=<国际站key> PYTHONPATH=src python3 scripts/asr_once.py sample.mp3
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from micall.config import load_config  # noqa: E402
from micall.providers import make_asr  # noqa: E402

_MIME = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".pcm": "audio/wav",
}


async def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "sample.mp3")
    if not path.exists():
        print(f"找不到音频文件 {path}。先用 TTS 合一段当样本：")
        print('  PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3')
        return
    mime = _MIME.get(path.suffix.lower(), "audio/mpeg")
    audio = path.read_bytes()

    cfg = load_config()
    node = cfg.node("asr")
    asr = make_asr(node)
    print(f"provider={type(asr).__name__}  model={node.params.get('model')}")
    print(f"endpoint={node.endpoint or '（未配置→stub）'}")
    print(f"音频 {path}（{len(audio)} bytes · {mime}）\n")

    if type(asr).__name__ == "StubASR":
        print("⚠ ASR 节点未配置 endpoint/api_key（铁律2）。")
        print("  在 micall.env 写 MICALL_ASR_ENDPOINT / MICALL_ASR_API_KEY 后重跑。")
        return

    t0 = time.perf_counter()
    first_ms: float | None = None
    final = ""
    if hasattr(asr, "transcribe"):
        agen = asr.transcribe(audio, mime=mime)
    else:  # 通用回退：包成一帧喂 stream()
        async def _one():
            yield audio

        agen = asr.stream(_one())

    try:
        async for text, is_final in agen:
            if first_ms is None and text:
                first_ms = (time.perf_counter() - t0) * 1000
            if is_final:
                final = text
    except Exception as e:  # 网络/鉴权/区不匹配
        print(f"⚠ 识别失败：{e!r}")
        print("  常见：① endpoint 与 key 区不一致（北京 key 配了新加坡端点）② 模型名不对 ③ 音频格式不支持。")
        return

    total_ms = (time.perf_counter() - t0) * 1000
    print(f"📝 识别结果：{final!r}")
    if first_ms is not None:
        print(f"⏱ 首字 {first_ms:.0f}ms · 整段识别 {total_ms:.0f}ms")
    else:
        print(f"⏱ 整段 {total_ms:.0f}ms（没拿到中间字）")
    print("（这是「整段录音识别」延迟：含上传+处理。真·边说边出字的实时流式后续走 WS 协议另测。）")


if __name__ == "__main__":
    asyncio.run(main())
