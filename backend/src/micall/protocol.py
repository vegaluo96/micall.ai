"""信令协议 —— 严格对齐 docs/03 §4/§5 与前端 src/logic/signaling.ts。

控制通道（WS / WebRTC DataChannel）只传 JSON 控制事件；音频走 WebRTC 媒体通道
（媒体归媒体，控制归控制 —— docs/02 §1.1）。
  • 服务端 → 前端：ServerEvent（构造即 JSON-able dict，server 直接 json.dumps 下发）。
  • 前端 → 服务端：ClientMessage（parse_client_message 解析入站帧）。
字段与前端 ServerEvent / ClientMessage 联合类型逐一对齐。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class ServerEvent:
    """服务端 → 前端 控制下行。每个方法返回 JSON-able dict（{"type": ...}）。"""

    @staticmethod
    def connected() -> dict[str, Any]:
        return {"type": "connected"}  # calling → listening

    @staticmethod
    def state(phase: str) -> dict[str, Any]:
        return {"type": "state", "phase": phase}  # listening / thinking / speaking

    @staticmethod
    def interrupted() -> dict[str, Any]:
        return {"type": "interrupted"}  # speaking → listening（跳过 thinking）

    @staticmethod
    def subtitle(role: str, text: str, partial: bool = False) -> dict[str, Any]:
        ev: dict[str, Any] = {"type": "subtitle", "role": role, "text": text}
        if partial:
            ev["partial"] = True  # 前端 partial?: boolean（ASR partial 才带）
        return ev

    @staticmethod
    def emotion(tag: str) -> dict[str, Any]:
        return {"type": "emotion", "tag": tag}  # 驱动影像 crossfade（语音 emotion 已在服务端用）

    @staticmethod
    def billing(remaining_seconds: int, elapsed: int) -> dict[str, Any]:
        return {"type": "billing", "remaining_seconds": remaining_seconds, "elapsed": elapsed}

    @staticmethod
    def low_minutes(remaining_seconds: int) -> dict[str, Any]:
        return {"type": "low_minutes", "remaining_seconds": remaining_seconds}

    @staticmethod
    def out_of_minutes() -> dict[str, Any]:
        return {"type": "out_of_minutes"}

    @staticmethod
    def call_failed(reason: str) -> dict[str, Any]:
        return {"type": "call_failed", "reason": reason}

    @staticmethod
    def ended() -> dict[str, Any]:
        return {"type": "ended"}


# 合法的服务端事件 type（用于测试/校验与前端枚举对齐）。
SERVER_EVENT_TYPES = frozenset(
    {"connected", "state", "interrupted", "subtitle", "emotion", "billing",
     "low_minutes", "out_of_minutes", "call_failed", "ended"}
)


@dataclass
class ClientMessage:
    """前端 → 服务端 控制上行（docs/03 §5）。"""

    type: str
    character_id: str | None = None
    scenario: str | None = None
    on: bool | None = None
    scene: str | None = None
    text: str | None = None


CLIENT_MESSAGE_TYPES = frozenset(
    {"start_call", "end_call", "mute", "switch_character", "set_scene", "text_input",
     "reset_memory"}
)


def parse_client_message(raw: str | bytes | dict[str, Any]) -> ClientMessage | None:
    """解析入站控制帧。畸形/未知 type → None（server 静默丢弃，与前端容错一致）。"""
    try:
        d = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    t = d.get("type")
    if t not in CLIENT_MESSAGE_TYPES:
        return None
    return ClientMessage(
        type=t,
        character_id=d.get("character_id"),
        scenario=d.get("scenario"),
        on=d.get("on"),
        scene=d.get("scene"),
        text=d.get("text"),
    )
