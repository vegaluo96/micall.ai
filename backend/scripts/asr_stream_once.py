"""实时流式 ASR 联调 —— 把一个音频文件按 100ms 帧「实时」喂给 DashScope 流式 ASR，
打印中间/最终结果 + 关键时延（首个中间结果、end-of-turn 判句）。先跑 --debug 看原始事件锁协议。

与 asr_once.py（整段录音识别 HTTP）不同：这条走 WebSocket 原生协议，边说边出字，
内置静音判句即 end-of-turn —— 真实通话「用户说完→AI 多快开始想」就由它决定。

依赖：websockets；ffmpeg（把任意音频转 pcm16/16k/mono，模拟麦克风上行帧）。
用法：
  cd backend; set -a; . config/micall.env; set +a
  # 没有 sample.mp3 先合一个：PYTHONPATH=src python3 scripts/tts_once.py "你好，我今天心情还不错。" sample.mp3
  PYTHONPATH=src python3 scripts/asr_stream_once.py sample.mp3 --debug --realtime
默认连新加坡区通用端点；账号若是业务空间专属域名，用 --ws 覆盖：
  PYTHONPATH=src python3 scripts/asr_stream_once.py sample.mp3 --debug \
    --ws wss://ws-你的工作空间.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference/
鉴权用 MICALL_ASR_API_KEY（与文件识别同一个国际站 key）。
"""
import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from micall.config import NodeConfig  # noqa: E402
from micall.providers.realtime_asr import DEFAULT_WS_INTL, RealtimeBailianASR  # noqa: E402

SR = 16000
FRAME_MS = 100
FRAME_BYTES = SR * 2 * FRAME_MS // 1000  # 16k×2字节×0.1s = 3200


def _pcm16_mono_16k(path: str) -> bytes:
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le",
           "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SR), "-"]
    try:
        return subprocess.run(cmd, capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise SystemExit("需要 ffmpeg：sudo apt install -y ffmpeg")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"ffmpeg 转码失败：{e.stderr.decode('utf-8', 'ignore')[:300]}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default="sample.mp3")
    ap.add_argument("--ws", default=os.environ.get("MICALL_ASR_WS_ENDPOINT", DEFAULT_WS_INTL))
    ap.add_argument("--model", default="paraformer-realtime-v2")
    ap.add_argument("--debug", action="store_true", help="打印每个原始服务端事件（锁协议）")
    ap.add_argument("--realtime", action="store_true",
                    help="逐帧 sleep 100ms 模拟真实语速（更贴近线上判句行为）")
    args = ap.parse_args()

    key = os.environ.get("MICALL_ASR_API_KEY", "")
    if not key:
        raise SystemExit("没有 MICALL_ASR_API_KEY。先：set -a; . config/micall.env; set +a")
    if not Path(args.audio).exists():
        raise SystemExit(f"找不到 {args.audio}。先用 tts_once 合一个 sample.mp3。")
    if Path(args.audio).stat().st_size == 0:
        raise SystemExit(f"{args.audio} 是 0 字节空文件。先用 tts_once 重新合一个非空 sample.mp3。")

    pcm = _pcm16_mono_16k(args.audio)
    nframes = (len(pcm) + FRAME_BYTES - 1) // FRAME_BYTES
    print(f"WS={args.ws}  model={args.model}")
    print(f"音频→pcm16/16k/mono：{len(pcm)} bytes ≈ {len(pcm) / (SR * 2):.1f}s · "
          f"{nframes} 帧×{FRAME_MS}ms · realtime={args.realtime}\n")

    node = NodeConfig(
        name="asr", provider="bailian_realtime", endpoint="", api_key=key,
        params={"ws_endpoint": args.ws, "realtime_model": args.model, "sample_rate": SR},
    )
    t0 = time.perf_counter()

    def on_event(evt: dict) -> None:
        if args.debug:
            ev = (evt.get("header") or {}).get("event", "?")
            import json as _j
            print(f"  «{ev}» {_j.dumps(evt, ensure_ascii=False)[:240]}")

    asr = RealtimeBailianASR(node, on_event=on_event)

    async def _frames():
        for i in range(nframes):
            yield pcm[i * FRAME_BYTES:(i + 1) * FRAME_BYTES]
            if args.realtime:
                await asyncio.sleep(FRAME_MS / 1000)

    first_partial: float | None = None
    finals: list[str] = []
    last_partial = ""
    try:
        async for text, is_final in asr.stream(_frames()):
            now = (time.perf_counter() - t0) * 1000
            if first_partial is None:
                first_partial = now
            if is_final:
                finals.append(text)
                print(f"  [final  {now:6.0f}ms] {text}")
            else:
                last_partial = text
                if args.debug:
                    print(f"  [partial {now:6.0f}ms] {text}")
    except Exception as e:
        print(f"\n⚠ 失败：{e!r}")
        print("  排查：① 该 key/区是否开通流式 ASR（paraformer-realtime-v2）"
              "② 专属域名要用 --ws ③ 看上面 --debug 的 task-failed 原因。")
        return

    end_ms = (time.perf_counter() - t0) * 1000
    print(f"\n📝 最终：{' '.join(finals) or last_partial!r}")
    if first_partial is not None:
        print(f"⏱ 首个中间结果 {first_partial:.0f}ms · 全程 {end_ms:.0f}ms")
    print("（--realtime 下「全程」≈ 音频时长 + 尾段判句；真实通话关心的是用户停顿后多快出 final。）")


if __name__ == "__main__":
    asyncio.run(main())
