"""本体读写：资产台账、三元组、多跳查询、标准对齐。

存储实现刻意只有 SQLite 一种（单文件、零外部依赖、能脱平台跑测试）。
上华为云时换的是 providers/huawei/gaussdb.py，本文件的函数签名不变。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

from ..storage.db import CST, now
from .version import current_version


def _row2card(row):
    return {
        "asset_id": row["asset_id"],
        "title": row["title"],
        "modality": row["modality"],
        "source": json.loads(row["source_json"] or "{}"),
        "version": json.loads(row["version_json"] or "{}"),
        "sensitivity": row["sensitivity"],
        "structure": json.loads(row["structure_json"] or "{}"),
        "anchors": json.loads(row["anchors_json"] or "[]"),
        "entities": json.loads(row["entities_json"] or "[]"),
        "kb": {"base": os.environ.get("MEDPAL_KB_BASE", "default"), "doc_id": row["asset_id"], "status": row["kb_status"]},
        "ingested_by": row["ingested_by"],
        "created_at": row["created_at"],
    }


def upsert_asset(conn, card):
    aid = card.get("asset_id") or (
        "AST-" + datetime.now(CST).strftime("%Y") + "-" + uuid.uuid4().hex[:6]
    )
    conn.execute(
        "INSERT INTO asset "
        "(asset_id,title,modality,source_json,version_json,sensitivity,"
        "structure_json,anchors_json,entities_json,kb_status,ingested_by,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(asset_id) DO UPDATE SET "
        "title=excluded.title,modality=excluded.modality,"
        "source_json=excluded.source_json,version_json=excluded.version_json,"
        "sensitivity=excluded.sensitivity,structure_json=excluded.structure_json,"
        "anchors_json=excluded.anchors_json,entities_json=excluded.entities_json,"
        "kb_status=excluded.kb_status,ingested_by=excluded.ingested_by,"
        "created_at=excluded.created_at",
        (
            aid,
            card.get("title", ""),
            card.get("modality", "text"),
            json.dumps(card.get("source", {}), ensure_ascii=False),
            json.dumps(card.get("version", {}), ensure_ascii=False),
            card.get("sensitivity", "public"),
            json.dumps(card.get("structure", {}), ensure_ascii=False),
            json.dumps(card.get("anchors", []), ensure_ascii=False),
            json.dumps(card.get("entities", []), ensure_ascii=False),
            card.get("kb_status", "pending"),
            card.get("ingested_by", ""),
            card.get("created_at") or now(),
        ),
    )
    conn.commit()
    return aid


def list_assets(conn, modality=None, entity=None, limit=100):
    sql = "SELECT * FROM asset WHERE 1=1"
    args = []
    if modality:
        sql += " AND modality = ?"
        args.append(modality)
    if entity:
        sql += " AND entities_json LIKE ?"
        args.append("%" + entity + "%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(int(limit))
    return [_row2card(r) for r in conn.execute(sql, args)]


def get_asset(conn, asset_id):
    row = conn.execute("SELECT * FROM asset WHERE asset_id = ?", (asset_id,)).fetchone()
    return _row2card(row) if row else None


def add_triple(conn, t, version="v0.9"):
    dup = conn.execute(
        "SELECT triple_id, confidence FROM triple "
        "WHERE head_id=? AND rel=? AND tail_id=? AND status='active'",
        (t["head"]["id"], t["rel"], t["tail"]["id"]),
    ).fetchone()
    if dup:
        conn.execute(
            "UPDATE triple SET confidence = ? WHERE triple_id = ?",
            (max(float(t.get("confidence", 0.8)), dup["confidence"]), dup["triple_id"]),
        )
        conn.commit()
        return None
    tid = t.get("triple_id") or ("T-" + uuid.uuid4().hex[:8])
    prov = t.get("provenance", {})
    conn.execute(
        "INSERT INTO triple "
        "(triple_id,head_id,head_type,head_label,rel,tail_id,tail_type,tail_label,"
        "confidence,asset_id,anchor_id,standard_json,status,version_added,version_removed) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
        (
            tid,
            t["head"]["id"],
            t["head"]["type"],
            t["head"]["label"],
            t["rel"],
            t["tail"]["id"],
            t["tail"]["type"],
            t["tail"]["label"],
            float(t.get("confidence", 0.8)),
            prov.get("asset_id"),
            prov.get("anchor_id"),
            json.dumps(t.get("standard", {}), ensure_ascii=False),
            "active",
            version,
        ),
    )
    conn.commit()
    return tid


def _triple_out(row):
    return {
        "triple_id": row["triple_id"],
        "head": {"id": row["head_id"], "type": row["head_type"], "label": row["head_label"]},
        "rel": row["rel"],
        "tail": {"id": row["tail_id"], "type": row["tail_type"], "label": row["tail_label"]},
        "confidence": row["confidence"],
        "provenance": {"asset_id": row["asset_id"], "anchor_id": row["anchor_id"]},
        "standard": json.loads(row["standard_json"] or "{}"),
        "version_added": row["version_added"],
    }


def neighbors(conn, node_ids, rel_filter=None):
    if not node_ids:
        return []
    marks = ",".join("?" * len(node_ids))
    sql = (
        "SELECT * FROM triple WHERE status='active' AND (head_id IN ("
        + marks
        + ") OR tail_id IN ("
        + marks
        + "))"
    )
    args = list(node_ids) + list(node_ids)
    if rel_filter:
        sql += " AND rel IN (" + ",".join("?" * len(rel_filter)) + ")"
        args += list(rel_filter)
    return conn.execute(sql, args).fetchall()


def find_conflicts(conn, triples=None, limit=50):
    """查「同一 head + 同一 rel 指向多个不同 tail」的冲突组。

    triples 给了就只查这些 triple_id 落在的分组（pipeline 用来查本次推理用到的边），
    否则全库扫。冲突不自动裁决——只把矛盾摆出来，让人看见。
    """
    rows = conn.execute(
        "SELECT triple_id,head_id,head_label,head_type,rel,tail_id,tail_label,"
        "tail_type,confidence,asset_id,anchor_id FROM triple WHERE status='active'"
    ).fetchall()
    wanted = set(triples or [])
    groups = {}
    for r in rows:
        groups.setdefault((r["head_id"], r["rel"]), []).append(r)

    conflicts = []
    for (head_id, rel), items in groups.items():
        if wanted and not any(i["triple_id"] in wanted for i in items):
            continue
        tails = {i["tail_id"] for i in items}
        if len(tails) < 2:
            continue
        conflicts.append({
            "head_id": head_id,
            "head_label": items[0]["head_label"],
            "head_type": items[0]["head_type"],
            "rel": rel,
            "tails": [
                {
                    "triple_id": i["triple_id"],
                    "tail_id": i["tail_id"],
                    "tail_label": i["tail_label"],
                    "tail_type": i["tail_type"],
                    "confidence": i["confidence"],
                    "provenance": {"asset_id": i["asset_id"], "anchor_id": i["anchor_id"]},
                }
                for i in items
            ],
            "triple_ids": [i["triple_id"] for i in items],
        })
    conflicts.sort(key=lambda c: (-len(c["tails"]), c["head_id"]))
    return {"ok": True, "groups": len(groups), "conflicts": conflicts[: int(limit)]}

def kg_query(conn, seeds, max_hops=2, rel_filter=None, limit=20):
    """从种子实体出发做多跳广度遍历，返回带 provenance 的路径。"""
    seeds = [s.strip() for s in seeds if s and s.strip()]
    if not seeds:
        return {"ok": False, "reason": "no_seed", "hint": "种子实体为空，先做实体归一"}
    resolved, unresolved = [], []
    for s in seeds:
        # 先过别名表（同义词/ICD 编码都在这里），再退回标签精确匹配；
        # 头部命中不了就试尾部，否则「消化内科」这类只出现在尾端的节点永远召不回。
        code = resolve_entity(conn, s) or s
        hit = conn.execute(
            "SELECT head_id FROM triple WHERE status='active' "
            "AND (head_id=? OR head_label=?) LIMIT 1",
            (code, s),
        ).fetchone()
        if not hit:
            hit = conn.execute(
                "SELECT tail_id FROM triple WHERE status='active' "
                "AND (tail_id=? OR tail_label=?) LIMIT 1",
                (code, s),
            ).fetchone()
        if hit:
            resolved.append(hit[0])
        else:
            unresolved.append(s)
        # 一个种子可能同时压着别名节点和标准节点（如「胃镜」→ EX-GASTRO），把能命中的都放进去
        if code != s:
            extra = conn.execute(
                "SELECT head_id FROM triple WHERE status='active' AND head_id=? LIMIT 1", (s,)
            ).fetchone()
            if extra and extra[0] not in resolved:
                resolved.append(extra[0])

    paths = []
    seen = set()
    for start in resolved:
        frontier = [[start]]
        for _hop in range(max(1, int(max_hops))):
            nxt = []
            for path in frontier:
                for row in neighbors(conn, [path[-1]], rel_filter):
                    other = row["tail_id"] if row["head_id"] == path[-1] else row["head_id"]
                    if other in path:
                        continue
                    key = (start, other, row["triple_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    new_path = path + [other]
                    nxt.append(new_path)
                    steps = []
                    for a, b in zip(new_path, new_path[1:], strict=False):
                        r = conn.execute(
                            "SELECT * FROM triple WHERE status='active' AND "
                            "((head_id=? AND tail_id=?) OR (head_id=? AND tail_id=?)) LIMIT 1",
                            (a, b, b, a),
                        ).fetchone()
                        if r:
                            # 下游（评测、Skill、报告）要直接读 rel / 两端，这里一次给全，
                            # 免得再按 edge 字符串反解析。
                            steps.append(
                                {
                                    "triple_id": r["triple_id"],
                                    "edge": r["head_label"]
                                    + " -["
                                    + r["rel"]
                                    + "]-> "
                                    + r["tail_label"],
                                    "rel": r["rel"],
                                    "head_id": r["head_id"],
                                    "head_label": r["head_label"],
                                    "head_type": r["head_type"],
                                    "tail_id": r["tail_id"],
                                    "tail_label": r["tail_label"],
                                    "tail_type": r["tail_type"],
                                    "provenance": {
                                        "asset_id": r["asset_id"],
                                        "anchor_id": r["anchor_id"],
                                    },
                                    "confidence": r["confidence"],
                                }
                            )
                    score = round(sum(s["confidence"] for s in steps) / max(1, len(steps)), 3)
                    paths.append(
                        {
                            "nodes": new_path,
                            "hops": len(new_path) - 1,
                            "steps": steps,
                            "provenance": [s["provenance"] for s in steps],
                            "score": score,
                        }
                    )
            frontier = nxt
            if not frontier:
                break
    paths.sort(key=lambda p: (-p["hops"], -p["score"]))
    cur = current_version(conn)
    return {
        "ok": bool(paths),
        "version": cur["version"] if cur else None,
        "resolved": resolved,
        "unresolved": unresolved,
        "paths": paths[: int(limit)],
        "reason": None if paths else "no_path",
    }


def align(conn, text):
    t = (text or "").strip()
    if not t:
        return {"ok": False, "reason": "empty_input"}
    row = conn.execute("SELECT * FROM alias WHERE surface = ?", (t,)).fetchone()
    how = "exact"
    if not row:
        row = conn.execute(
            "SELECT * FROM alias WHERE ? LIKE '%' || surface || '%' "
            "ORDER BY LENGTH(surface) DESC LIMIT 1",
            (t,),
        ).fetchone()
        how = "contains"
    if not row:
        return {
            "ok": False,
            "reason": "unmapped",
            "input": t,
            "hint": "加入待对齐队列，人工补 alias_map 后重跑",
        }
    return {
        "ok": True,
        "input": t,
        "match": how,
        "scheme": row["scheme"],
        "code": row["code"],
        "entity_type": row["entity_type"],
        "confidence": row["confidence"],
    }


def resolve_entity(conn, text):
    hit = conn.execute(
        "SELECT head_id FROM triple WHERE head_label = ? LIMIT 1", (text,)
    ).fetchone()
    if hit:
        return hit["head_id"]
    a = align(conn, text)
    return a.get("code") if a.get("ok") else None
