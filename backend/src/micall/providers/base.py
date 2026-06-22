"""供应商抽象接口（docs/02 §1.2：各节点可插拔，对应 Admin「接口配置」）。

实时三节点：ASR（流式转写）、LLM 快脑（流式 token）、TTS（流式音频）。
真实实现按节点 endpoint/key（铁律2）接 apiyi / 阿里百炼 / MiniMax；骨架与测试用 stub。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Sequence

# LLM 对话消息（OpenAI/DeepSeek 风格）。
Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


class LLMProvider(ABC):
    """快脑：流式吐 token（docs/02 §1.3 task B）。TTFT 是延迟主瓶颈（§1.7）。"""

    @abstractmethod
    def stream(
        self, messages: Sequence[Message], *, temperature: float = 0.8, max_tokens: int = 256
    ) -> AsyncIterator[str]:
        """逐 token 异步产出。实现为 `async def ... yield`。"""
        raise NotImplementedError


class TTSProvider(ABC):
    """发声：句子级流式合成（docs/02 §1.3 task C），带 emotion 与 voice_id。"""

    @abstractmethod
    def synthesize(
        self, text: str, *, voice_id: str, emotion: str = "", sample_rate: int = 24000
    ) -> AsyncIterator[bytes]:
        """逐音频块异步产出（PCM/编码块）。"""
        raise NotImplementedError


class ASRProvider(ABC):
    """感知：流式转写（docs/02 §1.3 task A）。产出 (text, is_final)。"""

    @abstractmethod
    def stream(self, frames: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
        """吃 20ms 音频帧流，产出 (partial_or_final_text, is_final)。"""
        raise NotImplementedError
