"""模型层：默认离线可跑，配置了就接 ModelArts Studio / 盘古（OpenAI 兼容）。"""

from .base import LLM, FakeLLM, build_llm
from .openai_compatible import OpenAICompatibleLLM

__all__ = ["FakeLLM", "LLM", "build_llm", "OpenAICompatibleLLM"]
