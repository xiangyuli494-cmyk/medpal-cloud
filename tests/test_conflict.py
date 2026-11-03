"""conflict_check：本体自相矛盾时必须点名，不能悄悄选一个。

为什么较真：同一 head + 同一 rel 指向两个不同 tail（例如「消化性溃疡 -[推荐用药]->
布洛芬」和「-> 奥美拉唑」）在医学场景里选错比拒答危险。这条链的第 5 步要把矛盾
写进 gaps，让人看见。
"""

from __future__ import annotations

from medpal_core.ontology import store

CONFLICT_Q = "上腹隐痛伴反酸，下一步做什么检查？"


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _triple(head_id, head_label, rel, tail_id, tail_label, tail_type="drug"):
    return {
        "head": {"id": head_id, "type": "disease", "label": head_label},
        "rel": rel,
        "tail": {"id": tail_id, "type": tail_type, "label": tail_label},
        "confidence": 0.8,
        "provenance": {"asset_id": "AST-2026-test0001", "anchor_id": "s1.p1.c1"},
    }


def test_find_conflicts_detects_two_tails(seeded):
    store.add_triple(seeded, _triple("D-ULCER", "消化性溃疡", "推荐用药", "DR-IBU", "布洛芬"))
    store.add_triple(seeded, _triple("D-ULCER", "消化性溃疡", "推荐用药", "DR-OME", "奥美拉唑"))

    out = store.find_conflicts(seeded, triples=None)
    assert out["ok"]
    hit = [c for c in out["conflicts"] if c["head_id"] == "D-ULCER"]
    assert hit, out
    labels = {t["tail_label"] for t in hit[0]["tails"]}
    assert labels == {"布洛芬", "奥美拉唑"}
    assert len(hit[0]["triple_ids"]) == 2


def test_same_rel_different_head_is_not_conflict(seeded):
    store.add_triple(seeded, _triple("D-A", "病A", "推荐用药", "DR-X", "药X"))
    store.add_triple(seeded, _triple("D-B", "病B", "推荐用药", "DR-Y", "药Y"))

    out = store.find_conflicts(seeded, triples=None)
    heads = {c["head_id"] for c in out["conflicts"]}
    assert "D-A" not in heads and "D-B" not in heads


def test_three_tails_sorted_first(seeded):
    for tail in ("DR-1", "DR-2", "DR-3"):
        store.add_triple(seeded, _triple("D-MULTI", "多药病", "推荐用药", tail, "药" + tail[-1]))
    store.add_triple(seeded, _triple("D-TWO", "两药病", "推荐用药", "DR-A", "药A"))
    store.add_triple(seeded, _triple("D-TWO", "两药病", "推荐用药", "DR-B", "药B"))

    out = store.find_conflicts(seeded, triples=None)
    assert out["conflicts"][0]["head_id"] == "D-MULTI"
    assert len(out["conflicts"][0]["tails"]) == 3


def test_pipeline_step_reports_conflict_in_gaps(seeded):
    store.add_triple(seeded, _triple("D-ULCER", "消化性溃疡", "推荐用药", "DR-IBU", "布洛芬"))
    store.add_triple(seeded, _triple("D-ULCER", "消化性溃疡", "推荐用药", "DR-OME", "奥美拉唑"))

    body = _client().post("/v1/ask", json={"question": CONFLICT_Q, "top_k": 8}).json()
    trace = _client().get("/v1/traces/" + body["trace_id"]).json()
    steps = {s["op"]: s for s in trace["steps"]}

    assert "conflict_check" in steps, [s["op"] for s in trace["steps"]]
    assert steps["conflict_check"]["i"] == 5
    assert steps["conflict_check"]["evidence"], "冲突步必须引用到具体三元组"
    assert any("冲突" in g for g in trace["gaps"]), trace["gaps"]


def test_pipeline_no_conflict_means_clean(seeded):
    body = _client().post("/v1/ask", json={"question": CONFLICT_Q, "top_k": 8}).json()
    trace = _client().get("/v1/traces/" + body["trace_id"]).json()
    steps = {s["op"]: s for s in trace["steps"]}

    assert steps["conflict_check"]["i"] == 5
    assert not steps["conflict_check"]["evidence"]
    assert not any("冲突" in g for g in trace["gaps"]), trace["gaps"]
