"""决策链：证据能核对到 -> 完整率 1.0；编造引用 -> 必须被扣分。"""

from __future__ import annotations

from medpal_core.assets.card import ingest_file
from medpal_core.ontology import store
from medpal_core.trace import get_trace, write_trace


def _asset(conn, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("# 路径\n上腹隐痛提示消化性溃疡。\n", encoding="utf-8")
    return ingest_file(conn, f)


def test_good_evidence_scores_one(conn, tmp_path):
    card = _asset(conn, tmp_path)
    ref = card["anchors"][1]["anchor_id"]
    out = write_trace(conn, "问", [{"i": 1, "op": "retrieve", "in": ["问"], "out": {},
                                    "evidence": [ref]}])
    assert out["trace_completeness"] == 1.0
    assert out["report_path"].endswith(".md")


def test_fake_anchor_is_flagged(conn, tmp_path):
    card = _asset(conn, tmp_path)
    bogus = card["asset_id"] + "#s9.p9.c9"
    out = write_trace(conn, "问", [{"i": 1, "op": "retrieve", "in": ["问"], "out": {},
                                    "evidence": [bogus]}])
    assert out["trace_completeness"] == 0.0
    assert out["unresolved"] == [bogus]


def test_triple_evidence_resolves(conn, tmp_path):
    card = _asset(conn, tmp_path)
    ref = card["anchors"][1]["anchor_id"]
    tid = store.add_triple(conn, {
        "head": {"id": "E-a", "type": "symptom", "label": "上腹隐痛"}, "rel": "提示",
        "tail": {"id": "E-b", "type": "disease", "label": "消化性溃疡"},
        "provenance": {"asset_id": card["asset_id"], "anchor_id": ref}})
    out = write_trace(conn, "问", [{"i": 1, "op": "kg_query", "out": {}, "evidence": [tid]}])
    assert out["trace_completeness"] == 1.0
    assert get_trace(conn, out["trace_id"])["trace_id"] == out["trace_id"]


def test_no_evidence_counts_as_complete(conn):
    out = write_trace(conn, "拒答题", [{"i": 1, "op": "conclude", "out": {"s": "证据不足"},
                                       "evidence": []}])
    assert out["trace_completeness"] == 1.0
    assert out["evidence_count"] == 0
    assert out["refusal"] is True


def test_report_includes_repro_commands(conn, tmp_path, monkeypatch):
    """C6：报告末尾必须有可照抄的 curl，否则「可复现」只是一句形容词。"""
    monkeypatch.setenv("MEDPAL_BASE_URL", "https://medpal.example.com")
    card = _asset(conn, tmp_path)
    ref = card["anchors"][1]["anchor_id"]
    out = write_trace(conn, "上腹隐痛怎么办？", [{"i": 1, "op": "retrieve", "in": ["上腹隐痛怎么办？"],
                                                "out": {}, "evidence": [ref]}])
    text = open(out["report_path"], encoding="utf-8").read()
    assert "## 复现命令" in text
    assert "curl -s -X POST \"https://medpal.example.com/v1/ask\"" in text
    assert "/v1/traces/TR-XXXX" in text
    assert out["trace_id"] in text


def test_repro_payload_survives_quotes(conn, tmp_path):
    """问句里带单引号不能把 curl 的 -d 参数截断。"""
    card = _asset(conn, tmp_path)
    ref = card["anchors"][1]["anchor_id"]
    q = "它说'没事'，可信吗？"
    out = write_trace(conn, q, [{"i": 1, "op": "retrieve", "in": [q], "out": {}, "evidence": [ref]}])
    text = open(out["report_path"], encoding="utf-8").read()
    line = [ln for ln in text.splitlines() if ln.strip().startswith("-d ")][0]
    assert line.count("'") % 2 == 0, line
