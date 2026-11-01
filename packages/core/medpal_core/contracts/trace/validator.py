"""trace 校验器：schema + 语义双检。

为什么 schema 不够：JSON Schema 只能拦类型，拦不住「听着像数组的元素」。
把 evidence 写成字符串 "T-0f5bfa1d"，writer 会按字符遍历，产出 9 条假证据、
溯源完整率照算 1.0、报告照写 —— 静默产垃圾。所以这里再做一遍语义检查。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"

# op 与 ref 同说一件事，写了就必须对得上。
REF_BY_OP = {
    "ingest": "STORE",
    "parse": "PARSE",
    "entity_extract": "EVIDENCE",
    "align_evidence": "EVIDENCE",
    "std_align": "EVIDENCE",
    "kg_query": "TRAVERSE",
    "retrieve": "EVIDENCE",
    "conflict_check": "EVIDENCE",
    "conclude": "CONCLUDE",
    "skill_export": "CONCLUDE",
}

TRACE_ID_RE = re.compile(r"^TR-[0-9]{8}-[0-9A-F]{4}$")
TRIPLE_RE = re.compile(r"^T-[0-9a-f]{8}$")
ASSET_ANCHOR_RE = re.compile(r"^AST-[A-Za-z0-9][A-Za-z0-9-]*#[^#\s]+$")
BARE_ASSET_RE = re.compile(r"^AST-[A-Za-z0-9][A-Za-z0-9-]*$")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def evidence_shape_errors(evidence) -> list:
    if isinstance(evidence, str):
        return ["evidence 是字符串，会被逐字符遍历；必须是数组，如 [\"T-xxxxxxxx\"]"]
    errs = []
    for e in evidence or []:
        if not isinstance(e, str):
            errs.append(f"evidence 元素必须是字符串，收到 {e!r}")
        elif TRIPLE_RE.match(e) or ASSET_ANCHOR_RE.match(e) or BARE_ASSET_RE.match(e):
            continue
        else:
            errs.append(f"evidence 元素格式非法：{e!r}")
    return errs


def validate(trace: dict, schema: dict | None = None) -> list:
    """返回错误列表，空列表 = 合格。"""
    schema = schema or load_schema()
    errs = []
    for e in sorted(Draft202012Validator(schema).iter_errors(trace),
                    key=lambda x: list(x.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append(f"{where}: {e.message}")

    steps = [s for s in (trace.get("steps") or []) if isinstance(s, dict)]
    for idx, s in enumerate(steps):
        for msg in evidence_shape_errors(s.get("evidence")):
            errs.append(f"steps/{idx}/evidence: {msg}")
        ref = s.get("ref")
        expect = REF_BY_OP.get(s.get("op", ""))
        if ref is not None and expect and ref != expect:
            errs.append(
                f"steps/{idx}/ref: op={s.get('op')!r} 应为 ref={expect!r}，实际 {ref!r}"
            )

    seq = [s.get("i") for s in steps]
    if all(isinstance(x, int) for x in seq):
        if seq != sorted(seq):
            errs.append(f"steps: i 必须递增，实际 {seq!r}")
        if len(seq) != len(set(seq)):
            errs.append(f"steps: i 有重复，实际 {seq!r}")
    return errs


def derive_sources(trace: dict, conn=None) -> list:
    """从 evidence 反推来源资产。不传 conn 时不猜三元组对应的资产。"""
    out = []
    for s in trace.get("steps") or []:
        for e in (s or {}).get("evidence") or []:
            if not isinstance(e, str):
                continue
            aid = None
            if "#" in e:
                head = e.split("#")[0]
                if BARE_ASSET_RE.match(head):
                    aid = head
            elif TRIPLE_RE.match(e) and conn is not None:
                row = conn.execute("SELECT asset_id FROM triple WHERE triple_id=?", (e,)).fetchone()
                if row:
                    aid = row["asset_id"]
            if aid and aid not in out:
                out.append(aid)
    return sorted(out)
