// 实时语音的音频管线（纯逻辑层，不走 DC 模板）。媒体走二进制帧，控制走 JSON（见 signaling.ts）。
//   • MicCapture：麦克风 MediaStream → 16kHz PCM16 帧（上行喂后端 ASR）。
//   • AudioPlayer：后端下行的 PCM16 @ 24kHz 音频块 → Web Audio 播放（H5/iOS 稳，无需 MSE）。
// 采样率与后端约定一致：上行 16k（ASR session），下行 24k（config tts.sample_rate）。
//
// 公放回声的成熟解法（豆包/Siri/各家语音助手在缺硬件 AEC 时的通用做法）= **半双工**：
// AI 的声音正在外放时，麦克风干脆不上行——AI 自然「听不见自己」，从源头杜绝回声被 ASR
// 当成用户说话（自己断/凭空冒话/重复「你好」）。浏览器 echoCancellation 只在桌面/安卓 Chrome
// 可靠，移动端外放（尤其 iOS Safari）的 AEC 只有走 WebRTC 通信模式才生效——纯 WebSocket+WebAudio
// 拿不到，故用「按真实播放状态门控麦克风」这条确定性方案兜底（见 AudioPlayer.isPlaying）。

const MIC_RATE = 16000;
const TTS_RATE = 24000;

type Ctor = { new (): AudioContext };
function audioCtx(): AudioContext {
  const C = (window.AudioContext || (window as unknown as { webkitAudioContext: Ctor }).webkitAudioContext) as Ctor;
  return new C();
}

function clamp16(s: number): number {
  s = Math.max(-1, Math.min(1, s));
  return s < 0 ? s * 0x8000 : s * 0x7fff;
}

function downsampleToInt16(input: Float32Array, inRate: number, outRate: number): ArrayBuffer {
  if (inRate <= outRate) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) out[i] = clamp16(input[i]);
    return out.buffer;
  }
  const ratio = inRate / outRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) out[i] = clamp16(input[Math.floor(i * ratio)]);
  return out.buffer;
}

/** 麦克风 → 16kHz PCM16 帧。用 ScriptProcessor（广泛支持、含 iOS；无需独立 worklet 文件）。
 *  纯采集，不做内部门控：是否上行由上层按真实播放状态决定（半双工，见 MiCallLogic.startMicUplink）。
 *  这样「AI 在外放→不上行」是一条确定性规则，而不是靠 RMS 阈值猜回声（外放回声常比真人还响，猜不准）。 */
export class MicCapture {
  private ctx: AudioContext | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private node: ScriptProcessorNode | null = null;

  constructor(
    private stream: MediaStream,
    private onFrame: (pcm: ArrayBuffer) => void,
  ) {}

  start(): void {
    if (this.ctx) return;
    this.ctx = audioCtx();
    this.src = this.ctx.createMediaStreamSource(this.stream);
    const FRAME = 4096;
    this.node = this.ctx.createScriptProcessor(FRAME, 1, 1);
    const inRate = this.ctx.sampleRate;
    this.node.onaudioprocess = (e: AudioProcessingEvent) => {
      const input = e.inputBuffer.getChannelData(0);
      const pcm = downsampleToInt16(input, inRate, MIC_RATE);
      if (pcm.byteLength) this.onFrame(pcm);
    };
    this.src.connect(this.node);
    this.node.connect(this.ctx.destination); // 触发 onaudioprocess；不写 output → 静默，无回授
    if (this.ctx.state === "suspended") void this.ctx.resume();
  }

  stop(): void {
    if (this.node) this.node.onaudioprocess = null;
    try { this.node?.disconnect(); } catch { /* noop */ }
    try { this.src?.disconnect(); } catch { /* noop */ }
    try { void this.ctx?.close(); } catch { /* noop */ }
    this.node = this.src = this.ctx = null;
  }
}

/** 下行 PCM16 @ 24kHz 音频块 → 排队播放。打断时 flush 停掉队列（barge-in）。 */
export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private playhead = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private logged = false;
  // 全双工关键：TTS 不直连 ctx.destination，而是经 MediaStream 走一个隐藏 <audio> 元素出声。
  // 浏览器会把"媒体元素的播放"纳入回声消除(AEC)的参考信号，移动端外放（尤其 iOS Safari，纯 WebAudio
  // 直连 destination 时 AEC 不生效）也能消回声 → 麦克风全程开着也不回授，支持边说边随时打断。
  private out: AudioNode | null = null;        // 实际接音频的节点（MediaStream 目标 或 退回 destination）
  private el: HTMLAudioElement | null = null;

  /** 必须在用户手势（点接听）里调一次，iOS 才允许出声。 */
  resume(): void {
    if (!this.ctx) {
      this.ctx = audioCtx();
      try {
        const dest = this.ctx.createMediaStreamDestination();
        const el = document.createElement("audio");
        el.autoplay = true;
        el.setAttribute("playsinline", "");       // iOS 不接管/不全屏
        (el as HTMLAudioElement & { playsInline?: boolean }).playsInline = true;
        el.srcObject = dest.stream;
        el.style.cssText = "position:fixed;left:0;top:0;width:0;height:0;opacity:0;pointer-events:none;";
        document.body.appendChild(el);            // 个别浏览器要求在 DOM 内才出声
        this.el = el;
        this.out = dest;                          // AEC 友好输出
      } catch {
        this.out = this.ctx.destination;          // 不支持 MediaStreamDestination：退回直连（仍可出声）
      }
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
    if (this.el) void this.el.play().catch(() => { /* 手势内调用，通常已可播 */ });
  }

  play(frame: ArrayBuffer): void {
    this.resume();
    if (!this.ctx || frame.byteLength < 2) return;
    if (!this.logged) {
      this.logged = true;
      console.info("[micall] 收到下行 TTS 音频，开始播放（首帧", frame.byteLength, "bytes）");
    }
    try {
      const n = frame.byteLength >> 1; // 偶数对齐：丢弃可能的半个样本，避免构造异常
      const pcm = new Int16Array(frame, 0, n);
      const f32 = new Float32Array(n);
      for (let i = 0; i < n; i++) f32[i] = pcm[i] / 0x8000;
      const buf = this.ctx.createBuffer(1, n, TTS_RATE);
      buf.getChannelData(0).set(f32);
      const node = this.ctx.createBufferSource();
      node.buffer = buf;
      node.connect(this.out || this.ctx.destination);
      const start = Math.max(this.ctx.currentTime + 0.02, this.playhead);
      node.start(start);
      this.playhead = start + buf.duration;
      this.sources.add(node);
      node.onended = () => this.sources.delete(node);
    } catch (e) {
      console.warn("[micall] 播放音频块失败", e);
    }
  }

  /** AI 音频此刻是否正在外放（含一小段衰减拖尾）。仅"半双工兜底模式"用它判断要不要暂停上行：
   *  playhead = 已排队音频播放到的终点；currentTime 还没追上 playhead+tail 就当作「还在响」。
   *  flush 后 playhead 归 0 → false；自然播完后 currentTime 越过终点 → false。 */
  isPlaying(tailMs = 250): boolean {
    if (!this.ctx || this.playhead <= 0) return false;
    return this.ctx.currentTime < this.playhead + tailMs / 1000;
  }

  /** 打断/挂断：停掉所有排队中的音频。 */
  flush(): void {
    for (const s of this.sources) { try { s.stop(); } catch { /* noop */ } }
    this.sources.clear();
    this.playhead = 0;
  }

  close(): void {
    this.flush();
    if (this.el) { try { this.el.pause(); this.el.srcObject = null; this.el.remove(); } catch { /* noop */ } this.el = null; }
    this.out = null;
    try { void this.ctx?.close(); } catch { /* noop */ }
    this.ctx = null;
  }
}
