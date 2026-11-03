"""ModelArts Studio / 盘古：走 OpenAI 兼容协议，直接复用 llm.openai_compatible。

配置名统一到 MEDPAL_LLM_*（见 medpal_core.config.settings），
HUAWEI_MODEL_* 是早期名字，仍兼容。
"""

from __future__ import annotations

from ...config import settings
from ...llm.openai_compatible import OpenAICompatibleLLM
from .config import ProviderNotConfigured


def build_llm(cfg=None) -> OpenAICompatibleLLM:
    cfg = cfg or settings()
    if not (cfg.llm_base_url and cfg.llm_model):
        raise ProviderNotConfigured(
            "缺少 MEDPAL_LLM_BASE_URL / MEDPAL_LLM_MODEL"
            "（旧名 HUAWEI_MODEL_ENDPOINT / HUAWEI_MODEL_NAME 仍兼容）"
        )
    return OpenAICompatibleLLM(
        base_url=cfg.llm_base_url, api_key=cfg.llm_api_key, model=cfg.llm_model
    )
