"""check_llm.py 的离线部分：读 env、脱敏、缺配置、解析 OpenAI 兼容返回。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KEYS = (
    "MEDPAL_LLM_BASE_URL",
    "MEDPAL_LLM_MODEL",
    "MEDPAL_LLM_API_KEY",
    "HUAWEI_MODEL_ENDPOINT",
    "HUAWEI_MODEL_NAME",
    "HUAWEI_MODEL_API_KEY",
)


def _mod():
    spec = importlib.util.spec_from_file_location("check_llm", ROOT / "scripts" / "check_llm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clean(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


def test_missing_config_returns_3(tmp_path, monkeypatch):
    _clean(monkeypatch)
    assert _mod().main(["--env", str(tmp_path / "none.env")]) == 3


def test_medpal_name_wins_over_legacy(tmp_path, monkeypatch):
    _clean(monkeypatch)
    p = tmp_path / ".env.local"
    p.write_text("MEDPAL_LLM_MODEL=new\nHUAWEI_MODEL_NAME=old\n", encoding="utf-8")
    mod = _mod()
    assert mod.pick(mod.load_env(p), mod.MODEL_KEYS) == "new"


def test_legacy_name_still_works(tmp_path, monkeypatch):
    _clean(monkeypatch)
    p = tmp_path / ".env.local"
    p.write_text("HUAWEI_MODEL_NAME=old\n", encoding="utf-8")
    mod = _mod()
    assert mod.pick(mod.load_env(p), mod.MODEL_KEYS) == "old"


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def _env_with_model(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text(
        "MEDPAL_LLM_BASE_URL=https://example.invalid/v1\nMEDPAL_LLM_MODEL=demo-model\n",
        encoding="utf-8",
    )
    return p


def test_happy_path_returns_0(tmp_path, monkeypatch, capsys):
    _clean(monkeypatch)
    import httpx

    fake = _Resp({"choices": [{"message": {"content": "模型已就绪"}}]})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: fake)
    assert _mod().main(["--env", str(_env_with_model(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert "LLM READY: demo-model" in out


def test_bad_structure_returns_5(tmp_path, monkeypatch):
    _clean(monkeypatch)
    import httpx

    fake = _Resp({"unexpected": True})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: fake)
    assert _mod().main(["--env", str(_env_with_model(tmp_path))]) == 5


def test_http_error_returns_4(tmp_path, monkeypatch):
    _clean(monkeypatch)
    import httpx

    fake = _Resp({"error": "invalid api key"}, status=401)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: fake)
    assert _mod().main(["--env", str(_env_with_model(tmp_path))]) == 4
