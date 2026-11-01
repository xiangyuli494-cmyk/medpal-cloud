"""ModelArts Studio / 盘古：走 OpenAI 兼容协议，直接复用 llm.openai_compatible。"""

from __future__ import annotations

from ...llm.openai_compatible import OpenAICompatibleLLM
from .config import ProviderNotConfigured, load_config


def build_llm(cfg=None) -> OpenAICompatibleLLM:
    cfg = cfg or load_config()
    if not (cfg.model_endpoint and cfg.model_name):
        raise ProviderNotConfigured("缺少 HUAWEI_MODEL_ENDPOINT / HUAWEI_MODEL_NAME")
    return OpenAICompatibleLLM(base_url=cfg.model_endpoint, api_key=cfg.ak, model=cfg.model_name)
