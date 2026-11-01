"""端到端：起服务 -> 问一句 -> 拿回结论和决策链。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def test_health(seeded):
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["ontology_version"] == "v1.0"
    assert body["assets"] >= 1
    assert body["llm"] == "offline"


def test_ask_returns_trace_and_conclusion(seeded):
    r = _client().post("/v1/ask", json={"question": "上腹隐痛伴反酸，做什么检查？"})
    assert r.status_code == 200
    body = r.json()
    assert body["trace_id"].startswith("TR-")
    assert body["trace_completeness"] == 1.0
    assert body["conclusion"]["statement"]
    assert "胃镜" in body["conclusion"]["exams"]


def test_trace_roundtrip(seeded):
    c = _client()
    tid = c.post("/v1/ask", json={"question": "上腹隐痛挂哪个科"}).json()["trace_id"]
    t = c.get("/v1/traces/" + tid).json()
    assert t["trace_id"] == tid
    assert [s["i"] for s in t["steps"]] == sorted(s["i"] for s in t["steps"])


def test_missing_trace_404(seeded):
    assert _client().get("/v1/traces/TR-19700101-0000").status_code == 404


def test_ingest_and_list(seeded, tmp_path):
    f = tmp_path / "extra.md"
    f.write_text("# 补充\n反酸烧心建议消化内科就诊。\n", encoding="utf-8")
    c = _client()
    r = c.post("/v1/assets", json={"path": str(f), "title": "补充材料"})
    assert r.status_code == 200 and r.json()["ok"]
    items = c.get("/v1/assets", params={"limit": 10}).json()["items"]
    assert any(i["title"] == "补充材料" for i in items)


def test_ingest_missing_file_400(seeded):
    r = _client().post("/v1/assets", json={"path": "no/such.md"})
    assert r.status_code == 400
