"""check_obs.py 的离线部分：只验读 env 与脱敏，不连网。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("check_obs", ROOT / "scripts/check_obs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_env_parses_comments_and_quotes(tmp_path, monkeypatch):
    p = tmp_path / ".env.local"
    p.write_text('# secret\nHUAWEI_AK=abc\nHUAWEI_SK="q q"\n\nBADLINE\n', encoding="utf-8")
    monkeypatch.delenv("HUAWEI_AK", raising=False)
    monkeypatch.delenv("HUAWEI_SK", raising=False)
    cfg = _mod().load_env(p)
    assert cfg["HUAWEI_AK"] == "abc"
    assert cfg["HUAWEI_SK"] == "q q"
    assert "BADLINE" not in cfg


def test_real_env_overrides_file(tmp_path, monkeypatch):
    p = tmp_path / ".env.local"
    p.write_text("HUAWEI_AK=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("HUAWEI_AK", "fromenv")
    assert _mod().load_env(p)["HUAWEI_AK"] == "fromenv"


def test_mask_never_leaks_secret():
    m = _mod()
    assert m.mask("") == "(空)"
    masked = m.mask("abcdefghijklmnop")
    assert masked.startswith("abcd")
    assert "ijklm" not in masked


def test_missing_config_returns_3(tmp_path, monkeypatch):
    for k in ("HUAWEI_AK", "HUAWEI_SK", "HUAWEI_OBS_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    assert _mod().main(["--env", str(tmp_path / "none.env")]) == 3
