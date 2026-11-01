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


def test_obs_without_sdk_raises_with_hint():
    from medpal_core.providers.huawei.config import ProviderNotConfigured

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
