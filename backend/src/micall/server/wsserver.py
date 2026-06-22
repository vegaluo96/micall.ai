"""WebSocket 信令服务器 —— 把会话编排接到前端（docs/03 控制通道）。

每个 WS 连接 = 一通电话。入站 ClientMessage 驱动 CallSession，出站 ServerEvent 下发。
前端把 VITE_SIGNALING_URL 指向 ws://host:port/path 即从 Mock 切到真实后端（铁律2，端点可配）。

注意：音频媒体走独立 WebRTC 通道（本服务只管控制信令）。真实部署在编排里接 Pipecat/
LiveKit 的媒体管线（task A 喂帧 / task C 下行），骨架用 stub 驱动同一套状态机与信令。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..config import Config, resolve_voice
from ..context import CharacterRuntime, ContextAssembler
from ..memory import InMemoryRepository, MemoryRepository
from ..protocol import ServerEvent, parse_client_message
from ..providers import make_llm, make_tts
from ..session import CallSession

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CHARACTERS_DIR = _REPO_ROOT / "asset-pipeline" / "characters"
_DEFAULT_REMAINING = 720  # 骨架默认通话余额（秒）；真实从 users 表读 remaining_seconds（§5）
_ANON = "anon"            # 骨架无鉴权；真实从登录态取 user_id


def _load_characters() -> dict[str, CharacterRuntime]:
    """加载资产管线产出的出厂角色 spec（铁律7：出厂、全用户共享）。"""
    out: dict[str, CharacterRuntime] = {}
    if _CHARACTERS_DIR.is_dir():
        for p in sorted(_CHARACTERS_DIR.glob("*.json")):
            try:
                spec = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            c = CharacterRuntime.from_spec(spec)
            if c.character_id:
                out[c.character_id] = c
    return out


class SignalingServer:
    def __init__(self, config: Config, repo: MemoryRepository | None = None) -> None:
        self.config = config
        self.repo = repo or InMemoryRepository()
        self.characters = _load_characters()

    def _character(self, character_id: str | None) -> CharacterRuntime:
        if character_id and character_id in self.characters:
            return self.characters[character_id]
        if self.characters:  # 未知 id：退回第一个出厂角色
            return next(iter(self.characters.values()))
        # 资产目录为空时的兜底占位角色，保证骨架可独立运行。
        return CharacterRuntime(
            character_id=character_id or "stub",
            name="林晚",
            persona={"core_traits": ["温柔", "会倾听"], "speaking_style": "轻声、慢"},
        )

    def _make_session(self, *, emit, character_id, scenario) -> CallSession:
        char = self._character(character_id)
        user_voice = self.repo.get_user_voice(_ANON, char.character_id)
        voice_id = resolve_voice(
            self.config.global_defaults.get("default_voice", ""), char.voice_id, user_voice
        )
        profile = self.repo.get_profile(_ANON, char.character_id)
        assembler = ContextAssembler(
            char,
            profile=profile,
            memory=self.repo,
            memory_top_k=int(self.config.global_defaults.get("memory_depth", 5)),
        )
        return CallSession(
            config=self.config,
            emit=emit,
            llm=make_llm(self.config.node("llm_fast")),
            tts=make_tts(self.config.node("tts")),
            assembler=assembler,
            character_id=char.character_id,
            scenario=scenario or "",
            remaining_seconds=_DEFAULT_REMAINING,
            voice_id=voice_id,
        )

    async def handle(self, websocket: Any) -> None:
        session: CallSession | None = None

        async def emit(ev: dict) -> None:
            await websocket.send(json.dumps(ev, ensure_ascii=False))

        try:
            async for raw in websocket:
                msg = parse_client_message(raw)
                if msg is None:
                    continue  # 畸形/未知帧静默丢弃（与前端容错一致）
                if msg.type == "start_call":
                    if session:
                        await session.end(emit_ended=False)
                    session = self._make_session(
                        emit=emit, character_id=msg.character_id, scenario=msg.scenario
                    )
                    await session.start()
                elif msg.type == "switch_character":
                    if session:
                        await session.end(emit_ended=False)  # 切角色 = 结束 + 新建（docs/03 §3）
                    session = self._make_session(
                        emit=emit, character_id=msg.character_id, scenario=msg.scenario
                    )
                    await session.start()
                elif msg.type == "end_call":
                    if session:
                        await session.end()
                        session = None
                elif msg.type == "text_input":
                    if session and msg.text:
                        await session.on_user_text(msg.text)
                elif msg.type == "mute":
                    if session:
                        session.set_muted(bool(msg.on))
                elif msg.type == "set_scene":
                    if session and msg.scene:
                        session.set_scene(msg.scene)
        except Exception:  # 连接异常：尽力清理会话
            pass
        finally:
            if session:
                await session.end(emit_ended=False)


async def serve_forever(config: Config) -> None:
    from websockets.asyncio.server import serve  # 延迟导入：仅运行服务才需 websockets

    server = SignalingServer(config)
    host = config.server.get("ws_host", "0.0.0.0")
    port = int(config.server.get("ws_port", 8787))
    path = config.server.get("path", "/realtime/signal")
    print(f"[micall] 信令服务器监听 ws://{host}:{port}{path}")
    async with serve(server.handle, host, port):
        await asyncio.Future()  # run forever
