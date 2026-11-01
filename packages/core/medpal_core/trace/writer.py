"""决策链写入：trace 落库 + 报告落盘 + 溯源完整率。

每一步的证据引用都要能被核对：三元组给 T-xxxxxxxx，文档证据给 AST-xxx#anchor。
核对不到的进 unresolved，判分器据此扣分——这是「可溯源」不是口号的唯一证据。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from ..ontology.version import current_version
from ..storage.db import CST, now, report_dir


def _evidence_exists(conn, ref):
    ref = str(ref)
    if ref.startswith("T-"):
        return (
            conn.execute("SELECT 1 FROM triple WHERE triple_id = ?", (ref,)).fetchone() is not None
        )
    if "#" in ref:
        aid = ref.split("#")[0]
        row = conn.execute("SELECT anchors_json FROM asset WHERE asset_id = ?", (aid,)).fetchone()
        if not row:
            return False
        return any(a.get("anchor_id") == ref for a in json.loads(row["anchors_json"] or "[]"))
    return conn.execute("SELECT 1 FROM asset WHERE asset_id = ?", (ref,)).fetchone() is not None


def _ref_str(e):
    """证据引用统一成字符串：三元组直接给 id，文档证据给 "asset_id#anchor_id"。
    kg_query 的 provenance 是 {asset_id, anchor_id} 结构，写决策链前必须先摊平，
    否则报告里无法逐条核对，也会在 join 时报 TypeError。"""
    if isinstance(e, dict):
        if e.get("triple_id"):
            return str(e["triple_id"])
        if e.get("anchor_id"):
            return (
                str(e["anchor_id"])
                if not e.get("asset_id")
                else "{}#{}".format(e["asset_id"], str(e["anchor_id"]).split("#")[-1])
            )
        return str(e)
    return str(e)


def write_trace(conn, question, steps, agent_version="v1.0", elapsed_ms=0, gaps=None):
    tid = "TR-" + datetime.now(CST).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()
    cur = current_version(conn)
    onto = cur["version"] if cur else "v0.9"
    conn.execute(
        "INSERT INTO trace "
        "(trace_id,question,agent_version,ontology_version,steps_json,gaps_json,"
        "elapsed_ms,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            tid,
            question,
            agent_version,
            onto,
            json.dumps(steps, ensure_ascii=False),
            json.dumps(gaps or [], ensure_ascii=False),
            int(elapsed_ms),
            now(),
        ),
    )
    conn.commit()

    cited = []
    for s in steps:
        for e in s.get("evidence", []) or []:
            ref = _ref_str(e)
            if ref not in cited:
                cited.append(ref)
    unresolved = [e for e in cited if not _evidence_exists(conn, e)]
    # 没有可引证据时（拒答题）溯源完整率记为 1.0：结论是「超出覆盖范围」，
    # 本身不依赖证据，不构成不可追溯。报告里会显式写「证据数 0」以示区分。
    completeness = round(1 - len(unresolved) / len(cited), 3) if cited else 1.0

    report_dir().mkdir(parents=True, exist_ok=True)
    report = report_dir() / (tid + ".md")
    lines = [
        "# 决策链报告 " + tid,
        "",
        "- 问题：" + question,
        "- 智能体版本：" + agent_version,
        "- 本体版本：" + onto,
        "- 生成时间：" + now(),
        "- 证据数：" + str(len(cited)) + ("（无引用，拒答类结论）" if not cited else ""),
        "- 溯源完整率：" + str(completeness),
        "",
        "## 决策链",
        "",
        "| # | 操作 | 输入 | 输出 | 证据 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in steps:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                s.get("i"),
                s.get("op"),
                str(s.get("in", "")),
                str(s.get("out", "")),
                ", ".join(_ref_str(e) for e in (s.get("evidence", []) or [])) or "—",
            )
        )
    lines += ["", "## 证据清单", ""]
    for e in cited:
        lines.append("- " + e + (" ✅" if e not in unresolved else " ❌ 未找到"))
    if gaps:
        lines += ["", "## 缺口", ""] + ["- " + g for g in gaps]
    report.write_text("\n".join(lines), encoding="utf-8")

    return {
        "ok": True,
        "trace_id": tid,
        "version": onto,
        "report_path": str(report),
        "evidence_count": len(cited),
        "trace_completeness": completeness,
        "unresolved": unresolved,
    }


def get_trace(conn, trace_id):
    row = conn.execute("SELECT * FROM trace WHERE trace_id = ?", (trace_id,)).fetchone()
    if not row:
        return None
    return {
        "trace_id": row["trace_id"],
        "question": row["question"],
        "agent_version": row["agent_version"],
        "ontology_version": row["ontology_version"],
        "steps": json.loads(row["steps_json"]),
        "gaps": json.loads(row["gaps_json"]),
        "elapsed_ms": row["elapsed_ms"],
        "created_at": row["created_at"],
    }
