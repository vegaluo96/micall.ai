"""转写一个音频文件并多轮计时 —— 实测百炼 Qwen3-ASR 从香港的识别延迟。

单跑一次会被抖动骗，所以默认跑多轮取 p50/p95（跟 LLM spike 一个套路）。

用法（先把 ASR 的 endpoint/key 写进 micall.env 并 source）：
  cd backend
  set -a; . config/micall.env; set +a
  # 没有现成音频？先用 TTS 合一段当样本（顺便又测一遍 TTS）：
  #   PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3
  PYTHONPATH=src python3 scripts/asr_once.py sample.mp3 --label 北京

横向对比北京区 vs 新加坡区（香港跨境，新加坡通常更快，但要用国际站独立 key）：
  # ① 北京区（默认配置，用国内百炼 key）
  PYTHONPATH=src python3 scripts/asr_once.py sample.mp3 --label 北京
  # ② 新加坡区（临时覆盖 endpoint+key 再跑同一段音频）
  MICALL_ASR_ENDPOINT=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions \
  MICALL_ASR_API_KEY=<国际站key> \
  PYTHONPATH=src python3 scripts/asr_once.py sample.mp3 --label 新加坡
然后对比两份 p50/p95 汇总，取快的那区。
"""
import argparse
import asyncio
import statistics
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


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


async def _run_once(asr, audio: bytes, mime: str) -> tuple[float | None, float, str]:
    t0 = time.perf_counter()
    first: float | None = None
    final = ""
    if hasattr(asr, "transcribe"):
        agen = asr.transcribe(audio, mime=mime)
    else:  # 通用回退：包成一帧喂 stream()
        async def _one():
            yield audio

        agen = asr.stream(_one())
    async for text, is_final in agen:
        if first is None and text:
            first = (time.perf_counter() - t0) * 1000
        if is_final:
            final = text
    total = (time.perf_counter() - t0) * 1000
    return first, total, final


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default="sample.mp3", help="音频文件（mp3/wav…）")
    ap.add_argument("--rounds", type=int, default=5, help="测速轮数（取 p50/p95）")
    ap.add_argument("--label", default="", help="标签，便于区分北京/新加坡两次输出")
    args = ap.parse_args()

    path = Path(args.audio)
    if not path.exists():
        print(f"找不到音频文件 {path}。先用 TTS 合一段当样本：")
        print('  PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3')
        return
    mime = _MIME.get(path.suffix.lower(), "audio/mpeg")
    audio = path.read_bytes()
    if not audio:
        print(f"⚠ {path} 是 0 字节空文件。先用 tts_once 重新合一个非空 sample.mp3。")
        return

    cfg = load_config()
    node = cfg.node("asr")
    asr = make_asr(node)
    tag = f"【{args.label}】" if args.label else ""
    print(f"{tag}provider={type(asr).__name__}  model={node.params.get('model')}")
    print(f"endpoint={node.endpoint or '（未配置→stub）'}")
    print(f"音频 {path}（{len(audio)} bytes · {mime}）× {args.rounds} 轮\n")

    if type(asr).__name__ == "StubASR":
        print("⚠ ASR 节点未配置 endpoint/api_key（铁律2）。")
        print("  在 micall.env 写 MICALL_ASR_ENDPOINT / MICALL_ASR_API_KEY 后重跑。")
        return

    firsts: list[float] = []
    totals: list[float] = []
    sample_text = ""
    for i in range(args.rounds):
        try:
            first, total, final = await _run_once(asr, audio, mime)
        except Exception as e:  # 网络/鉴权/区不匹配
            print(f"  round {i + 1}: 失败 {e!r}")
            continue
        if first is not None:
            firsts.append(first)
        totals.append(total)
        sample_text = final or sample_text
        fm = f"{first:.0f}ms" if first is not None else "—"
        print(f"  round {i + 1}: 首字 {fm} · 整段 {total:.0f}ms")

    if not totals:
        print("\n所有轮次失败。常见：① endpoint 与 key 区不一致（北京 key 配了新加坡端点）"
              "② 模型名不对 ③ 音频格式不支持。")
        return

    print(f"\n📝 识别结果：{sample_text!r}")
    print("--- 基准 ---")
    if firsts:
        print(f"首字  p50={_pct(firsts, 0.5):.0f}ms  p95={_pct(firsts, 0.95):.0f}ms  "
              f"mean={statistics.mean(firsts):.0f}ms")
    print(f"整段  p50={_pct(totals, 0.5):.0f}ms  p95={_pct(totals, 0.95):.0f}ms  "
          f"mean={statistics.mean(totals):.0f}ms")

    p = _pct(totals, 0.5)
    if p > 2000:
        print("🔴 整段 p50 偏慢：跨境/区不优。香港优先试新加坡区端点对比。")
    elif p > 1200:
        print("🟡 临界：可用但偏高，建议和新加坡区对比取快的。")
    else:
        print("🟢 健康。")
    print("（整段录音识别延迟：含上传+处理。真·边说边出字的实时流式后续走 WS 协议另测。）")


if __name__ == "__main__":
    asyncio.run(main())
