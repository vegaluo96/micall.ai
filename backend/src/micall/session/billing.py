"""服务端权威计费（docs/02 §5 + CLAUDE.md：绝不信前端计时）。

服务端按**实际通话时长**扣减 remaining，通过控制信令推前端显示。前端的 outOfMins /
低于1分钟提示等 UI 全保留，数字来源换成这里推送。纯逻辑、无副作用，便于测试。
"""
from __future__ import annotations

from ..protocol import ServerEvent


class BillingMeter:
    def __init__(self, remaining_seconds: int, low_threshold_seconds: int = 60) -> None:
        self.remaining = max(0, int(remaining_seconds))
        self.elapsed = 0
        self._low_threshold = low_threshold_seconds
        self._low_warned = False

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def tick(self, seconds: int = 1) -> list[dict]:
        """推进 `seconds` 秒，返回本次要下发的事件序列（billing，必要时附 low_minutes /
        out_of_minutes）。编排每秒调用一次。"""
        if self.exhausted:
            return []
        self.elapsed += seconds
        self.remaining = max(0, self.remaining - seconds)
        events: list[dict] = [ServerEvent.billing(self.remaining, self.elapsed)]
        if self.remaining <= self._low_threshold and not self._low_warned:
            self._low_warned = True
            events.append(ServerEvent.low_minutes(self.remaining))
        if self.remaining <= 0:
            events.append(ServerEvent.out_of_minutes())
        return events
