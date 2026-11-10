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


def test_trace_id_matches_schema_format(conn):
    """格式与 schema 正则锁死：改这一位就是改契约。"""
    import re

    out = write_trace(conn, "问", [])
    assert re.match(r"^TR-[0-9]{8}-[0-9A-F]{4}$", out["trace_id"]), out["trace_id"]


def test_trace_id_collision_is_retried(conn, monkeypatch):
    """后四位只有 65536 种：撞号必须自动换一个，而不是把 IntegrityError 抛给调用方。"""
    import types

    from medpal_core.contracts import trace as ct

    seq = iter(["AAAA", "AAAA", "AAAA", "BBBB"])
    monkeypatch.setattr(ct.uuid, "uuid4", lambda: types.SimpleNamespace(hex=next(seq)))

    first = write_trace(conn, "问", [])["trace_id"]
    second = write_trace(conn, "问", [])["trace_id"]

    assert first.endswith("-AAAA"), first
    assert second.endswith("-BBBB"), second
    assert first != second


def test_insert_retries_on_unique_violation(conn, monkeypatch):
    """#69 的兜底：查表放过去了、插入才撞（并发），必须换个 id 重插而不是抛给调用方。"""
    from medpal_core.trace import writer as w

    taken = "TR-20260101-AAAA"
    conn.execute(
        "INSERT INTO trace (trace_id,question,agent_version,ontology_version,steps_json,"
        "gaps_json,elapsed_ms,created_at,sources_json,conclusion_json,completeness,refusal,"
        "unresolved_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (taken, "占位", "v1.0", "v0.9", "[]", "[]", 0, "2026-01-01T00:00:00Z", "[]", "{}", 1.0, 1, "[]"),
    )
    conn.commit()

    seq = iter([taken, "TR-20260101-BBBB"])
    monkeypatch.setattr(w, "new_trace_id", lambda conn=None: next(seq))

    out = w.write_trace(conn, "问", [])

    assert out["trace_id"] == "TR-20260101-BBBB", out["trace_id"]
    assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 2


def test_unique_violation_classifier_ignores_other_integrity_errors():
    """只看类名不够：sqlite3 里 NOT NULL / CHECK 违反抛的也是 IntegrityError。
    判错的后果是真 bug 被重试 8 次后报「连续撞号」，把错误埋掉。"""
    from medpal_core.trace import writer as w

    class IntegrityError(Exception):  # 同名影子类，模拟 sqlite3.IntegrityError
        pass

    class UniqueViolation(Exception):  # 同名影子类，模拟 psycopg.errors.UniqueViolation
        pass

    assert w._is_unique_violation(IntegrityError("UNIQUE constraint failed: trace.trace_id"))
    assert not w._is_unique_violation(IntegrityError("NOT NULL constraint failed: trace.question"))
    assert not w._is_unique_violation(IntegrityError("CHECK constraint failed: refusal"))
    assert w._is_unique_violation(UniqueViolation("duplicate key value violates unique constraint"))


def test_insert_does_not_swallow_other_integrity_errors(conn, monkeypatch):
    """非撞号的错误必须原样抛出，而且回滚到保存点后连接还能用。"""
    import pytest

    from medpal_core.trace import writer as w

    taken = "TR-20260101-AAAA"
    conn.execute(
        "INSERT INTO trace (trace_id,question,agent_version,ontology_version,steps_json,"
        "gaps_json,elapsed_ms,created_at,sources_json,conclusion_json,completeness,refusal,"
        "unresolved_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (taken, "占位", "v1.0", "v0.9", "[]", "[]", 0, "2026-01-01T00:00:00Z", "[]", "{}", 1.0, 1, "[]"),
    )
    conn.commit()

    monkeypatch.setattr(w, "new_trace_id", lambda conn=None: taken)
    monkeypatch.setattr(w, "_is_unique_violation", lambda exc: False)

    with pytest.raises(Exception) as ei:
        w.write_trace(conn, "问", [])

    assert "UNIQUE" in str(ei.value)
    assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 1

    # 回滚过保存点，同一个连接必须还能继续写
    monkeypatch.undo()
    out = w.write_trace(conn, "问2", [])
    assert out["ok"] is True
    assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 2


def test_gives_up_loudly_when_id_space_exhausted(conn, monkeypatch):
    """撞号重试有上限：一直撞就抛 RuntimeError，而且不留半条数据。"""
    import pytest

    from medpal_core.trace import writer as w

    taken = "TR-20260101-AAAA"
    conn.execute(
        "INSERT INTO trace (trace_id,question,agent_version,ontology_version,steps_json,"
        "gaps_json,elapsed_ms,created_at,sources_json,conclusion_json,completeness,refusal,"
        "unresolved_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (taken, "占位", "v1.0", "v0.9", "[]", "[]", 0, "2026-01-01T00:00:00Z", "[]", "{}", 1.0, 1, "[]"),
    )
    conn.commit()

    monkeypatch.setattr(w, "new_trace_id", lambda conn=None: taken)

    with pytest.raises(RuntimeError) as ei:
        w.write_trace(conn, "问", [])

    assert "撞号" in str(ei.value)
    assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 1
