"""真实快脑 LLM provider 骨架 —— apiyi 聚合网关（DeepSeek-V4-Flash），OpenAI 兼容 SSE。

endpoint/key 全部来自 NodeConfig（铁律2）。先全走 apiyi；若 TTFT 抖动/不透传 prefix
caching（§1.7 apiyi 风险），只改配置切直连 DeepSeek，本文件逻辑不动。

依赖 httpx（requirements.txt）；未安装时构造即报错，工厂会在节点未配置时回退 StubLLM，
所以骨架运行/测试不触发本文件。
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Sequence

from ..config import NodeConfig
from .base import LLMProvider, Message

try:  # 真实接入才需要；缺失不影响骨架/测试
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


def _chat_endpoint(ep: str) -> str:
    """容错归一：很多人把 apiyi/OpenAI 文档里的 base_url（.../v1）当 endpoint 填，少了
    /chat/completions → 404。这里自动补全：已是 chat/completions 原样；以 /v1 结尾则补全。"""
    ep = (ep or "").strip().rstrip("/")
    if ep.endswith("/chat/completions"):
        return ep
    if ep.endswith("/v1"):
        return ep + "/chat/completions"
    return ep


_SHARED_CLIENT: "httpx.AsyncClient | None" = None


def _shared_client() -> "httpx.AsyncClient":
    """进程级共享 HTTP 连接池：跨轮/跨通话复用 keep-alive，省掉每轮一次 TCP+TLS 握手 → TTFT 更快。"""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    return _SHARED_CLIENT


class ApiyiLLM(LLMProvider):
    def __init__(self, node: NodeConfig) -> None:
        if httpx is None:  # pragma: no cover
            raise RuntimeError("ApiyiLLM 需要 httpx：pip install -r requirements.txt")
        if not node.configured:
            raise RuntimeError(f"节点 {node.name} 未配置 endpoint/api_key（铁律2）")
        self._node = node
        self._endpoint = _chat_endpoint(node.endpoint)
        self._model = node.params.get("model", "deepseek-v4-flash")

    async def stream(
        self, messages: Sequence[Message], *, temperature: float = 0.8, max_tokens: int = 256
    ) -> AsyncIterator[str]:  # pragma: no cover  （需真实网络/密钥，不在测试路径）
        payload = {
            "model": self._model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._node.api_key}",
            "Content-Type": "application/json",
        }
        # OpenAI 兼容 SSE：逐行 data: {json}，token 在 choices[0].delta.content。
        async with _shared_client().stream(
            "POST", self._endpoint, headers=headers, json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, ValueError):
                    continue
                if delta:
                    yield delta
