"""契约冻结后 /v1/traces/{id} 必须直接是 schema 合法对象。

为什么较真：前端、评测、报告三处都读这份 trace。谁少一个字段谁自己补，
口径立刻分叉（完整率 1.0 / 0.0 / 100% 那次的教训）。所以让端点自己吐合法对象。
"""

from __future__ import annotations

import sqlite3

from jsonschema import Draft202012Validator

from medpal_core.contracts.trace import load_schema

QUESTION = "上腹隐痛伴反酸，下一步做什么检查？"


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_trace_endpoint_is_schema_valid(seeded):
    client = _client()
    body = client.post("/v1/ask", json={"question": QUESTION, "top_k": 8, "max_hops": 2}).json()
    trace = client.get("/v1/traces/" + body["trace_id"]).json()

    assert trace["schema"] == "medpal-trace/1"
    errors = [e.message for e in Draft202012Validator(load_schema()).iter_errors(trace)]
    assert not errors, errors
    assert trace["trace_completeness"] == body["trace_completeness"]
    assert trace["refusal"] is False
    assert trace["sources"], "seed 之后至少有可回指的来源资产"
    assert trace["conclusion"].get("dept")


def test_trace_refusal_flag(seeded):
    client = _client()
    body = client.post("/v1/ask", json={"question": "火星土壤里有哪些矿物？"}).json()
    trace = client.get("/v1/traces/" + body["trace_id"]).json()
    assert trace["refusal"] == (body["evidence_count"] == 0)
    if trace["refusal"]:
        assert trace["trace_completeness"] == 1.0


def test_migrate_adds_trace_columns(data_root):
    """老库（没有完整率/来源列）连上来必须自动补列，否则回读直接 KeyError。"""
    db = data_root / "legacy.db"
    raw = sqlite3.connect(db)
    raw.execute(
        "CREATE TABLE trace (trace_id TEXT PRIMARY KEY, question TEXT, agent_version TEXT, "
        "ontology_version TEXT, steps_json TEXT, gaps_json TEXT, elapsed_ms INTEGER, created_at TEXT)"
    )
    raw.commit()
    raw.close()

    from medpal_core.storage import connect

    conn = connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trace)")}
    conn.close()
    assert {
        "sources_json",
        "conclusion_json",
        "completeness",
        "refusal",
        "unresolved_json",
    } <= cols
