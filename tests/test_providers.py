"""云适配层：没配凭据时必须「诚实缺席」，而不是假装成功。"""

from __future__ import annotations

import pytest

from medpal_core.llm import FakeLLM, build_llm
from medpal_core.providers.huawei.config import HuaweiConfig
from medpal_core.providers.huawei.obs import OBSStore


def test_no_credentials_means_not_ready():
    cfg = HuaweiConfig()
    assert cfg.readiness() == {"obs": False, "gaussdb": False, "modelarts": False,
                              "koosearch": False}
    assert OBSStore(cfg).available() is False


def test_obs_without_sdk_raises_with_hint(monkeypatch):
    import sys

    from medpal_core.providers.huawei.config import ProviderNotConfigured

    monkeypatch.setitem(sys.modules, "obs", None)
    store = OBSStore(HuaweiConfig(ak="a", sk="b", obs_bucket="bucket"))
    assert store.available() is True
    with pytest.raises(ProviderNotConfigured):
        store._c()


def test_default_llm_is_offline():
    llm = build_llm()
    assert isinstance(llm, FakeLLM)
    assert llm.complete("s", "你好").startswith("[offline]")


def test_cloud_llm_requires_endpoint():
    from medpal_core.llm.openai_compatible import LLMCallError

    with pytest.raises(LLMCallError):
        build_llm(type("C", (), {"llm_provider": "openai", "llm_base_url": "",
                                 "llm_api_key": "", "llm_model": ""})())

def test_cloud_llm_accepts_maas_api_key(monkeypatch):
    """MaaS 用 API Key 而不是 AK/SK；两个变量名都要认，且优先 MEDPAL_LLM_*。"""
    from medpal_core.providers.huawei.modelarts import build_llm as build_maas

    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    monkeypatch.setenv("MEDPAL_LLM_MODEL", "deepseek-v3")
    monkeypatch.setenv("MEDPAL_LLM_API_KEY", "sk-from-maas")
    monkeypatch.setenv("HUAWEI_AK", "ak-should-not-be-used")
    llm = build_maas()
    assert llm.base_url == "https://api.modelarts-maas.com/v1"
    assert llm.model == "deepseek-v3"
    assert llm.api_key == "sk-from-maas"


def test_maas_falls_back_to_ak_when_api_key_absent(monkeypatch):
    from medpal_core.providers.huawei.modelarts import build_llm as build_maas

    monkeypatch.delenv("MEDPAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("HUAWEI_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    monkeypatch.setenv("MEDPAL_LLM_MODEL", "pangu-7b")
    monkeypatch.setenv("HUAWEI_AK", "ak-only")
    assert build_maas().api_key == "ak-only"


def test_readiness_honors_medpal_llm_env(monkeypatch):
    """回归：/v1/cloud 曾只认 HUAWEI_MODEL_*，填了 MEDPAL_LLM_* 仍报未就绪。"""
    from medpal_core.providers.huawei.config import load_config

    monkeypatch.delenv("HUAWEI_MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("HUAWEI_MODEL_NAME", raising=False)
    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    monkeypatch.setenv("MEDPAL_LLM_MODEL", "deepseek-v3")
    cfg = load_config()
    assert cfg.readiness()["modelarts"] is True
    assert cfg.model_endpoint == "https://api.modelarts-maas.com/v1"


def test_readiness_still_needs_both_endpoint_and_model(monkeypatch):
    from medpal_core.providers.huawei.config import load_config

    monkeypatch.delenv("HUAWEI_MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("HUAWEI_MODEL_NAME", raising=False)
    monkeypatch.delenv("MEDPAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    assert load_config().readiness()["modelarts"] is False
