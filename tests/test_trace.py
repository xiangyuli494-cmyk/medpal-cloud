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
