"""测试夹具：每个用例独立的临时 data 目录，互不污染。

路径全部走环境变量（MEDPAL_DATA_DIR / MEDPAL_DB / MEDPAL_REPORT_DIR），
所以测试不会碰到仓库里的 data/，也不会互相看到对方的库。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "samples" / "peptic_ulcer_pathway.md"


@pytest.fixture()
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDPAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MEDPAL_DB", str(tmp_path / "medpal.db"))
    monkeypatch.setenv("MEDPAL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("MEDPAL_LLM", "offline")
    monkeypatch.delenv("MEDPAL_LEXICON", raising=False)
    return tmp_path


@pytest.fixture()
def conn(data_root):
    from medpal_core.storage import connect

    c = connect()
    yield c
    c.close()


@pytest.fixture()
def seeded(data_root):
    """灌完样本与演示三元组后返回连接，供端到端用例使用。"""
    from app.seed import seed
    from medpal_core.storage import connect

    out = seed(SAMPLE, REPO / "data" / "ontology" / "seed.jsonl", "v1.0")
    assert out["ok"], out
    c = connect()
    yield c
    c.close()
