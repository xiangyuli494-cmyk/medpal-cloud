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
    assert "HUAWEI_GAUSSDB_DSN" in body["missing"]["gaussdb"]
    assert body["storage_backend"] == "sqlite"
