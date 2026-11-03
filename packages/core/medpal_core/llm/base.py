"""模型接口。

离线默认 FakeLLM：不给模型也能把整条决策链跑通、跑测试、跑评测 —— 这是评委能当场复现的前提。
接云上模型只改实现，pipeline 不动。
"""

from __future__ import annotations

from typing import Protocol

from ..config import settings


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str: ...


class FakeLLM:
    """确定性假模型：把用户输入原样作为「结论」返回，同时标明这是离线模式。"""

    name = "offline"

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        return "[offline] " + user.strip()[:400]


def build_llm(cfg=None) -> LLM:
    cfg = cfg or settings()
    if cfg.llm_provider in {"openai", "modelarts", "pangu", "huawei"}:
        from .openai_compatible import OpenAICompatibleLLM

        return OpenAICompatibleLLM(
            base_url=cfg.llm_base_url, api_key=cfg.llm_api_key, model=cfg.llm_model
        )
    return FakeLLM()
