"""通话 phase 状态机（docs/03 §2 + docs/02 §1.3）。

枚举与前端一致，结构不变、触发源改为服务端：
  idle → calling → listening → thinking → speaking → ended
  打断：speaking → listening（硬跳转，跳过 thinking —— docs/03 §4 interrupted）
"""
from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    IDLE = "idle"
    CALLING = "calling"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ENDED = "ended"


# 合法转换。打断由 SPEAKING/THINKING → LISTENING 覆盖（跳过 thinking）。
_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.IDLE: {Phase.CALLING},
    Phase.CALLING: {Phase.LISTENING, Phase.ENDED},      # connected→listening / call_failed→ended
    Phase.LISTENING: {Phase.THINKING, Phase.ENDED},
    Phase.THINKING: {Phase.SPEAKING, Phase.LISTENING, Phase.ENDED},  # 可被打断回 listening
    Phase.SPEAKING: {Phase.LISTENING, Phase.THINKING, Phase.ENDED},  # 打断/说完→listening
    Phase.ENDED: {Phase.IDLE},                          # 重置
}


class IllegalTransition(Exception):
    pass


class CallStateMachine:
    def __init__(self) -> None:
        self.phase = Phase.IDLE

    def can(self, to: Phase) -> bool:
        return to in _TRANSITIONS[self.phase]

    def to(self, to: Phase) -> Phase:
        """执行转换；非法转换抛 IllegalTransition（暴露编排逻辑错误，不静默吞）。"""
        if not self.can(to):
            raise IllegalTransition(f"{self.phase.value} → {to.value} 非法")
        self.phase = to
        return self.phase

    @property
    def active(self) -> bool:
        """是否在一通进行中的电话内（calling..speaking）。"""
        return self.phase in (Phase.CALLING, Phase.LISTENING, Phase.THINKING, Phase.SPEAKING)
