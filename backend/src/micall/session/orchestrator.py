"""会话编排（docs/02 §1.3 / §1.5）—— 一通电话 = 一个常驻协程，持有打断事件与发声队列。

骨架忠实再现状态机 / 句子级首句抢跑 / 情绪 piggyback / 打断熔断 / 服务端权威计费，用
stub providers 驱动，可单测。真实接入点（已标注）：
  • task A 感知：真实 VAD + 流式 ASR（百炼 Qwen3-ASR）喂帧 → end-of-turn → 触发 task B；
    骨架由 on_user_text（文字模式 / ASR final 文本）触发一轮。
  • task C 发声：真实经 WebRTC 媒体通道下行 push 音频；骨架用 stub TTS 计时长。
  • prefix caching / 分层注入（§1.7 降 TTFT）在 ContextAssembler 留接口。
媒体归媒体、控制归控制：本类只产出控制事件（ServerEvent），交 server 下发。
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..config import Config
from ..protocol import ServerEvent
from ..providers import LLMProvider, TTSProvider
from ..context.assembler import ContextAssembler
from .billing import BillingMeter
from .emotion import EmotionStripper
from .state import CallStateMachine, Phase

Emit = Callable[[dict], Awaitable[None]]

_SENTENCE_END = set("。！？!?\n")


def _first_sentence_end(s: str) -> int:
    for i, ch in enumerate(s):
        if ch in _SENTENCE_END:
            return i
    return -1


class CallSession:
    def __init__(
        self,
        *,
        config: Config,
        emit: Emit,
        llm: LLMProvider,
        tts: TTSProvider,
        assembler: ContextAssembler,
        character_id: str,
        scenario: str,
        remaining_seconds: int,
        voice_id: str,
    ) -> None:
        self.config = config
        self._emit_raw = emit
        self.llm = llm
        self.tts = tts
        self.assembler = assembler
        self.character_id = character_id
        self.scenario = scenario
        self.voice_id = voice_id

        self.sm = CallStateMachine()
        self.billing = BillingMeter(
            remaining_seconds,
            int(config.billing.get("low_minutes_threshold_seconds", 60)),
        )
        self._interrupt = asyncio.Event()
        self._billing_task: asyncio.Task | None = None
        self._turn_lock = asyncio.Lock()  # 串行化一轮生成，防并发触发
        self.history: list[dict] = []      # 对话滑窗（assistant 只记实际播出，§1.5）
        self.emotion_tag = "neutral"
        self._muted = False
        self._reply_max_tokens = int(config.global_defaults.get("reply_max_tokens", 256))

    # ── 下行封装：状态未结束才发（结束后丢弃迟到事件）──
    async def _emit(self, ev: dict) -> None:
        await self._emit_raw(ev)

    # ── 接通 ──
    async def start(self) -> None:
        if self.sm.phase != Phase.IDLE:
            return
        self.sm.to(Phase.CALLING)
        # 真实：建 WebRTC + ASR/LLM/TTS 就绪后接通；骨架立即接通。失败走 call_failed。
        await self._emit(ServerEvent.connected())
        self.sm.to(Phase.LISTENING)
        await self._emit(ServerEvent.state(Phase.LISTENING.value))
        self._billing_task = asyncio.create_task(self._billing_loop())

    # ── task B + C（骨架内联；真实拆成常驻协程经 tts_queue 解耦）──
    async def on_user_text(self, text: str) -> None:
        """文字模式输入 / ASR final 文本 → 触发一轮思考生成+发声。"""
        text = (text or "").strip()
        if not text or self.sm.phase in (Phase.IDLE, Phase.ENDED):
            return
        async with self._turn_lock:
            await self._generate_turn(text)

    async def _generate_turn(self, user_text: str) -> None:
        self._interrupt.clear()
        await self._emit(ServerEvent.subtitle("user", user_text))
        self.history.append({"role": "user", "content": user_text})

        self.sm.to(Phase.THINKING)
        await self._emit(ServerEvent.state(Phase.THINKING.value))

        messages = self.assembler.build(
            character_id=self.character_id, scenario=self.scenario, history=self.history
        )
        stripper = EmotionStripper()
        spoke: list[str] = []   # 实际播出的句子（ack 边界 → 进上下文，§1.5）
        buf = ""
        speaking = False
        emotion_sent = False

        async def open_speak() -> None:
            nonlocal speaking, emotion_sent
            if not speaking:
                self.sm.to(Phase.SPEAKING)
                await self._emit(ServerEvent.state(Phase.SPEAKING.value))
                speaking = True
            if not emotion_sent:
                self.emotion_tag = stripper.tag
                await self._emit(ServerEvent.emotion(stripper.tag))  # 一处产生，多处消费
                emotion_sent = True

        async for token in self.llm.stream(messages, max_tokens=self._reply_max_tokens):
            if self._interrupt.is_set():
                break
            buf += stripper.feed(token)
            while not self._interrupt.is_set():
                idx = _first_sentence_end(buf)
                if idx < 0:
                    break
                sentence, buf = buf[: idx + 1], buf[idx + 1:]
                if sentence.strip():
                    await open_speak()                       # 首句一出即抢跑（§1.7）
                    await self._speak(sentence, spoke)

        tail = (buf + stripper.flush()).strip()
        if tail and not self._interrupt.is_set():
            await open_speak()
            await self._speak(tail, spoke)

        # 实际播出的话进上下文；被打断则标注，让下轮能自然接住（§1.5 难点4）。
        if spoke:
            said = "".join(spoke)
            if self._interrupt.is_set():
                said += "……（被打断）"
            self.history.append({"role": "assistant", "content": said})
        self._trim_history()

        # 回 listening（打断路径已由 interrupt() 切 listening + emit interrupted）。
        if not self._interrupt.is_set() and self.sm.phase == Phase.SPEAKING:
            self.sm.to(Phase.LISTENING)
            await self._emit(ServerEvent.state(Phase.LISTENING.value))

    async def _speak(self, sentence: str, spoke: list[str]) -> None:
        """task C：一句的流式发声。真实经 WebRTC 下行；骨架消费 stub TTS 计时长。"""
        await self._emit(ServerEvent.subtitle("ai", sentence))
        async for _chunk in self.tts.synthesize(
            sentence, voice_id=self.voice_id, emotion=self.emotion_tag
        ):
            if self._interrupt.is_set():
                return  # 熔断：停下行 + 丢弃后续（清 tts_queue 的等价）
        spoke.append(sentence)  # 整句播完 → ack 边界

    # ── 打断（§1.5：停下行 → 清队列 → cancel → 半截话进上下文 → 回 listening）──
    async def interrupt(self) -> None:
        if self.sm.phase not in (Phase.THINKING, Phase.SPEAKING):
            return
        self._interrupt.set()                 # task B/C 在 token/句边界退出
        await self._emit(ServerEvent.interrupted())
        if self.sm.can(Phase.LISTENING):
            self.sm.to(Phase.LISTENING)

    # ── 计费循环（服务端权威，§5）──
    async def _billing_loop(self) -> None:
        try:
            while self.sm.active:
                await asyncio.sleep(1)
                for ev in self.billing.tick(1):
                    await self._emit(ev)
                if self.billing.exhausted:
                    await self.end(emit_ended=False)  # out_of_minutes 已发，前端走耗尽 UI
                    return
        except asyncio.CancelledError:
            pass

    def set_muted(self, on: bool) -> None:
        self._muted = on  # 前端本地也停麦；服务端记录（真实路径据此忽略上行帧）

    def set_scene(self, scene: str) -> None:
        self.scenario = scene  # 作为情境注入（assembler 下轮读取）；画面不变（固定背景）

    async def end(self, emit_ended: bool = True) -> None:
        self._interrupt.set()
        task = self._billing_task
        self._billing_task = None
        if task is not None:
            task.cancel()
            # 若 end 由计费循环自身（exhausted）触发，不能 await 自己 → 只标记取消。
            if task is not asyncio.current_task():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self.sm.phase != Phase.ENDED and self.sm.can(Phase.ENDED):
            self.sm.to(Phase.ENDED)
        if emit_ended:
            await self._emit(ServerEvent.ended())
        # 真实：触发离线理解引擎 worker（§3.3）回写事实层 + 更新画像。接入点：
        #   schedule_offline_understanding(self.character_id, user_id, self.history)

    def _trim_history(self, max_turns: int = 12) -> None:
        if len(self.history) > max_turns:
            self.history = self.history[-max_turns:]
