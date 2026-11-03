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

    # 必须把 SDK 真的挡掉：本机装了 esdk-obs-python 时，原写法会直接连上云端，
    # 测试结果取决于环境——CI 绿本地红，这种测试比没有还糟。
    monkeypatch.setitem(sys.modules, "obs", None)
    store = OBSStore(HuaweiConfig(ak="a", sk="b", obs_bucket="bucket"))
    assert store.available() is True
    with pytest.raises(ProviderNotConfigured) as ei:
        store._c()
    assert "esdk-obs-python" in str(ei.value)


def test_default_llm_is_offline():
    llm = build_llm()
    assert isinstance(llm, FakeLLM)
    assert llm.complete("s", "你好").startswith("[offline]")


def test_cloud_llm_requires_endpoint():
    from medpal_core.llm.openai_compatible import LLMCallError

    with pytest.raises(LLMCallError):
        build_llm(type("C", (), {"llm_provider": "openai", "llm_base_url": "",
                                 "llm_api_key": "", "llm_model": ""})())
