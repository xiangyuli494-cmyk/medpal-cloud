"""后端切换：占位符改写、按列名取行、就绪度端点——不接真库也要能验。"""

from __future__ import annotations

from medpal_core.providers.huawei.gaussdb import GaussConn, _sql


class _FakeCursor:
    def __init__(self):
        self.calls = []
        self.rows = [{"a": 1}]

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self

    def executemany(self, sql, seq):
        self.calls.append((sql, list(seq)))
        return self

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def close(self):
        pass


def test_sqlite_placeholder_is_rewritten():
    assert _sql("SELECT 1 FROM t WHERE a = ? AND b = ?") == "SELECT 1 FROM t WHERE a = %s AND b = %s"


def test_wrapped_conn_translates_and_keeps_column_access():
    raw = _FakeConn()
    conn = GaussConn(raw)
    row = conn.execute("SELECT a FROM t WHERE id = ?", ("x",)).fetchone()
    assert raw.cur.calls[-1][0] == "SELECT a FROM t WHERE id = %s"
    assert row["a"] == 1
    assert conn.backend == "gaussdb"


def test_health_reports_real_backend(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/health").json()
    assert body["storage"] == "sqlite"
    assert body["llm_ready"] is False


def test_cloud_endpoint_lists_missing_env(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/v1/cloud").json()
    assert body["ok"] is True
    assert body["ready"]["gaussdb"] is False
    assert "MEDPAL_DB_DSN" in body["missing"]["gaussdb"]
    assert "HUAWEI_GAUSSDB_DSN" in body["missing"]["gaussdb"]
    assert body["storage_backend"] == "sqlite"

def test_cloud_endpoint_missing_names_medpal_llm(seeded):
    """缺模型时要点名 MEDPAL_LLM_* —— 文档让人填这个名，报错就必须报这个名。"""
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/v1/cloud").json()
    assert body["ready"]["modelarts"] is False
    assert "MEDPAL_LLM_BASE_URL" in body["missing"]["modelarts"]
    assert "MEDPAL_LLM_MODEL" in body["missing"]["modelarts"]


def test_cloud_endpoint_sees_maas_env(seeded, monkeypatch):
    """回归：只填 MEDPAL_LLM_* 时 /v1/cloud 必须报 modelarts 就绪（曾假阴性）。"""
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    monkeypatch.setenv("MEDPAL_LLM_MODEL", "deepseek-v3")
    body = TestClient(app).get("/v1/cloud").json()
    assert body["ready"]["modelarts"] is True
    assert "modelarts" not in body["missing"]


def test_health_llm_ready_needs_base_url(seeded, monkeypatch):
    """只说 provider=modelarts 但没填端点不算就绪 —— 不能对评委撒谎。"""
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("MEDPAL_LLM", "modelarts")
    monkeypatch.delenv("MEDPAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("HUAWEI_MODEL_ENDPOINT", raising=False)
    assert TestClient(app).get("/health").json()["llm_ready"] is False

    monkeypatch.setenv("MEDPAL_LLM_BASE_URL", "https://api.modelarts-maas.com/v1")
    assert TestClient(app).get("/health").json()["llm_ready"] is True
