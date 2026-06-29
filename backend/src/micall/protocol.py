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
    def subtitle(role: str, text: str, partial: bool = False, dur: float = 0.0) -> dict[str, Any]:
        ev: dict[str, Any] = {"type": "subtitle", "role": role, "text": text}
        if partial:
            ev["partial"] = True  # 前端 partial?: boolean（ASR partial 才带）
        if dur and dur > 0:
            ev["dur"] = round(dur, 2)  # 这句预估说出时长(秒)：前端据此在该时长内逐字揭开，让字幕跟住语音
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
    def asr_failed() -> dict[str, Any]:
        # 实时语音识别中断（断流/协议异常）：前端据此提示「语音中断，可用文字继续」并保持可发文字，不静默失声。
        return {"type": "asr_failed"}

    @staticmethod
    def call_failed(reason: str) -> dict[str, Any]:
        return {"type": "call_failed", "reason": reason}

    @staticmethod
    def ended() -> dict[str, Any]:
        return {"type": "ended"}


# 合法的服务端事件 type（用于测试/校验与前端枚举对齐）。
# rtc_answer / rtc_unavailable 由 wsserver/webrtc 直接发（不经本文件的构造器），但同属服务端下行，
# 计入枚举以便校验/测试覆盖 WebRTC 路径（前端 signaling.ts ServerEvent 含这两个）。
SERVER_EVENT_TYPES = frozenset(
    {"connected", "state", "interrupted", "subtitle", "emotion", "billing",
     "low_minutes", "out_of_minutes", "asr_failed", "call_failed", "ended",
     "rtc_answer", "rtc_unavailable"}
)


@dataclass
class ClientMessage:
    """前端 → 服务端 控制上行（docs/03 §5）。"""

    type: str
    character_id: str | None = None
    scenario: str | None = None
    scenario_prompt: str | None = None   # 场景的完整情境指令（喂 LLM）；scenario 仅作记录/统计的短标签
    on: bool | None = None
    scene: str | None = None
    text: str | None = None
    lang: str | None = None              # 用户选的对话语言（中文/English/日本語…）；非中文则让 AI 改用该语言说


# 注：WebRTC 信令上行 rtc_offer / rtc_ice / rtc_close 不在此列——它们字段形态与 ClientMessage 不同，
# 由 wsserver 在 parse_client_message 之前旁路分发（见 wsserver.handle）。此集合只管「会话控制」上行。
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
        scenario_prompt=d.get("scenario_prompt"),
        on=d.get("on"),
        scene=d.get("scene"),
        text=d.get("text"),
        lang=d.get("lang"),
    )
