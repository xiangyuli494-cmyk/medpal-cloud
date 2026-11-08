"""ModelArts Studio / 盘古：走 OpenAI 兼容协议，直接复用 llm.openai_compatible。"""

from __future__ import annotations

from ...llm.openai_compatible import OpenAICompatibleLLM
from .config import ProviderNotConfigured, load_config


def build_llm(cfg=None) -> OpenAICompatibleLLM:
    """把 HuaweiConfig 映射到 OpenAI 兼容客户端。

    优先级：MEDPAL_LLM_* > HUAWEI_MODEL_*（见 config.load_config）；
    api_key 取 MEDPAL_LLM_API_KEY > HUAWEI_MODEL_API_KEY > AK（MaaS 用 API Key 而非 AK/SK）。
    """
    cfg = cfg or load_config()
    missing = [n for n, v in (("BASE_URL", cfg.model_endpoint), ("MODEL", cfg.model_name)) if not v]
    if missing:
        raise ProviderNotConfigured("缺少 MEDPAL_LLM_" + " / MEDPAL_LLM_".join(missing))
    return OpenAICompatibleLLM(base_url=cfg.model_endpoint,
                               api_key=cfg.model_api_key or cfg.ak,
                               model=cfg.model_name)
