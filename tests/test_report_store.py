"""B7：报告上 OBS。配了桶要真给出 obs:// 链接，没配要安静降级。

用假的桶顶替真 OBS：这里验的是「应用侧怎么用对象存储」，
不是 SDK 能不能连上华为云（那是 scripts/check_obs.py 的活）。

契约约束：trace body 被 schema 冻结（additionalProperties=false + test_frozen_v1_digest），
所以报告地址走响应头 X-Medpal-Report-Uri，正文与正文里的报告走 GET /v1/reports/{id}。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from medpal_core.contracts.trace import load_schema

QUESTION = "上腹隐痛伴反酸，下一步做什么检查？"


class FakeObs:
    """顶替 OBSStore：put 落进内存字典，exists 按字典回答。"""

    def __init__(self, available: bool = True, fail_on_put: bool = False):
        self.available_flag = available
        self.fail_on_put = fail_on_put
        self.puts: dict[str, bytes] = {}

    def available(self) -> bool:
        return self.available_flag

    def uri(self, key: str) -> str:
        return "obs://fake-bucket/" + key

    def put(self, local_path, key: str) -> str:
        if self.fail_on_put:
            raise RuntimeError("put boom")
        self.puts[key] = Path(local_path).read_bytes()
        return self.uri(key)

    def exists(self, key: str) -> bool:
        return key in self.puts


def _wired(fake):
    """把两个端点的报告仓库换成假桶，返回 TestClient 与清理函数。"""
    from app.deps import get_report_store
    from app.main import app
    from app.report_store import ReportStore

    app.dependency_overrides[get_report_store] = lambda: ReportStore(fake)
    return TestClient(app)


def _cleanup():
    from app.deps import get_report_store
    from app.main import app

    app.dependency_overrides.pop(get_report_store, None)


@pytest.fixture()
def wired(seeded):
    fake = FakeObs()
    client = _wired(fake)
    yield client, fake
    _cleanup()


def test_upload_skipped_without_obs(data_root):
    from app.report_store import ReportStore

    store = ReportStore(FakeObs(available=False))
    out = store.upload("TR-20261110-0001")
    assert out["uri"] is None
    assert out["reason"] == "obs_not_configured"
    assert store.uri("TR-20261110-0001") is None


def test_upload_failure_does_not_raise(data_root):
    from app.report_store import ReportStore, local_report_path

    path = local_report_path("TR-20261110-0002")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# x", encoding="utf-8")

    out = ReportStore(FakeObs(fail_on_put=True)).upload("TR-20261110-0002")
    assert out["uri"] is None
    assert out["reason"] == "upload_failed"
    assert "boom" in out["error"]


def test_upload_missing_local_report(data_root):
    from app.report_store import ReportStore

    out = ReportStore(FakeObs()).upload("TR-20261110-0003")
    assert out["reason"] == "report_not_found"


def test_ask_uploads_report(wired):
    client, fake = wired
    body = client.post("/v1/ask", json={"question": QUESTION}).json()

    tid = body["trace_id"]
    assert body["report_uri"] == "obs://fake-bucket/reports/" + tid + ".md"
    assert body["report_upload"]["key"] == "reports/" + tid + ".md"
    stored = fake.puts["reports/" + tid + ".md"].decode("utf-8")
    assert "# 决策链报告 " + tid in stored


def test_trace_header_carries_report_uri_and_body_stays_frozen(wired):
    client, _fake = wired
    body = client.post("/v1/ask", json={"question": QUESTION}).json()
    r = client.get("/v1/traces/" + body["trace_id"])

    assert r.headers["X-Medpal-Report-Uri"] == body["report_uri"]
    trace = r.json()
    assert "report_uri" not in trace, "契约冻结：body 里不许加字段"
    errors = [e.message for e in Draft202012Validator(load_schema()).iter_errors(trace)]
    assert not errors, errors


def test_reports_endpoint_returns_markdown(wired):
    client, _fake = wired
    body = client.post("/v1/ask", json={"question": QUESTION}).json()
    r = client.get("/v1/reports/" + body["trace_id"]).json()

    assert r["ok"] is True
    assert r["report_uri"] == body["report_uri"]
    assert body["trace_id"] in r["markdown"]
    assert "复现命令" in r["markdown"]


def test_reports_endpoint_404(wired):
    client, _fake = wired
    r = client.get("/v1/reports/TR-20261110-FFFF")
    assert r.status_code == 404
    assert r.json()["detail"]["reason"] == "trace_not_found"


def test_offline_degrades_quietly(seeded, monkeypatch):
    from app.deps import get_report_store
    from app.main import app
    from app.report_store import ReportStore

    for key in ("HUAWEI_AK", "HUAWEI_SK", "HUAWEI_OBS_BUCKET"):
        monkeypatch.delenv(key, raising=False)
    app.dependency_overrides[get_report_store] = lambda: ReportStore(FakeObs(available=False))
    try:
        client = TestClient(app)
        body = client.post("/v1/ask", json={"question": QUESTION}).json()
        assert body["report_uri"] is None
        assert body["report_upload"]["reason"] == "obs_not_configured"
        r = client.get("/v1/traces/" + body["trace_id"])
        assert "X-Medpal-Report-Uri" not in r.headers
        assert client.get("/v1/reports/" + body["trace_id"]).json()["report_uri"] is None
    finally:
        _cleanup()
