"""本体层：入库 -> 建三元组 -> 多跳可达 -> 版本快照与差分。"""

from __future__ import annotations

from medpal_core.assets.card import ingest_file
from medpal_core.ontology import store
from medpal_core.ontology import version as onto_version


def _seed_triple(conn, aid, anchor):
    return store.add_triple(conn, {
        "head": {"id": "E-a", "type": "symptom", "label": "上腹隐痛"},
        "rel": "提示",
        "tail": {"id": "E-b", "type": "disease", "label": "消化性溃疡"},
        "confidence": 0.9,
        "provenance": {"asset_id": aid, "anchor_id": anchor},
    })


def test_ingest_then_query_path(conn, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("# 路径\n上腹隐痛提示消化性溃疡。\n", encoding="utf-8")
    card = ingest_file(conn, f)
    assert card["ok"]
    anchor = card["anchors"][1]["anchor_id"]
    assert anchor.startswith(card["asset_id"])

    conn.execute("INSERT INTO triple (triple_id, head_id, head_type, head_label, rel, tail_id,"
                 " tail_type, tail_label, confidence, asset_id, anchor_id, standard_json, status,"
                 " version_added) VALUES ('T-00000001','E-a','symptom','上腹隐痛','提示','E-b',"
                 "'disease','消化性溃疡',0.9,?,?,'{}','active','v0.9')", (card["asset_id"], anchor))
    conn.commit()

    out = store.kg_query(conn, ["上腹隐痛"], max_hops=1)
    assert out["ok"]
    assert out["paths"][0]["steps"][0]["triple_id"] == "T-00000001"
    assert out["paths"][0]["provenance"][0]["anchor_id"] == anchor


def test_add_triple_dedup_keeps_higher_confidence(conn):
    aid, anchor = "AST-2026-aaaaaa", "AST-2026-aaaaaa#s1.p1.c1"
    assert _seed_triple(conn, aid, anchor)
    assert _seed_triple(conn, aid, anchor) is None
    row = conn.execute("SELECT confidence FROM triple WHERE rel='提示'").fetchone()
    assert row["confidence"] == 0.9


def test_snapshot_and_diff(conn):
    _seed_triple(conn, "AST-2026-bbbbbb", "AST-2026-bbbbbb#s1.p1.c1")
    snap = onto_version.snapshot(conn, "v0.9", "首版")
    assert snap["triple_count"] == 1
    assert onto_version.current_version(conn)["version"] == "v0.9"

    conn.execute("UPDATE triple SET status='deprecated'")
    conn.commit()
    onto_version.snapshot(conn, "v1.0", "下线一条")
    d = onto_version.diff_versions(conn, "v0.9", "v1.0")
    assert d["old"] == "v0.9" and d["new"] == "v1.0"
    assert d["removed"] and not d["added"]
