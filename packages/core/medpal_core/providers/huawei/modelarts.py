"""ModelArts Studio / 盘古：走 OpenAI 兼容协议，直接复用 llm.openai_compatible。"""

from __future__ import annotations

from ...llm.openai_compatible import OpenAICompatibleLLM
from .config import ProviderNotConfigured, load_config


def build_llm(cfg=None) -> OpenAICompatibleLLM:
    """把 HuaweiConfig 映射到 OpenAI 兼容客户端。

    优先级：MEDPAL_LLM_* > HUAWEI_MODEL_*（见 config.load_config）；
    api_key 只认 MEDPAL_LLM_API_KEY / HUAWEI_MODEL_API_KEY。
    不再回落 HUAWEI_AK：MaaS 用独立 API Key 而不是 AK/SK，把 AK 当 Bearer 只会拿到
    401 ModelArts.81003，报错文本把人往「权限不足」上带，不如当场诚实缺席。
    """
    cfg = cfg or load_config()
    missing = [n for n, v in (("BASE_URL", cfg.model_endpoint), ("MODEL", cfg.model_name)) if not v]
    if missing:
        raise ProviderNotConfigured("缺少 MEDPAL_LLM_" + " / MEDPAL_LLM_".join(missing))
    if not cfg.model_api_key:
        raise ProviderNotConfigured(
            "缺少 MEDPAL_LLM_API_KEY（MaaS 用独立 API Key，不是 AK/SK；AK 当 Bearer 只会 401）"
        )
    return OpenAICompatibleLLM(base_url=cfg.model_endpoint,
                               api_key=cfg.model_api_key,
                               model=cfg.model_name)
