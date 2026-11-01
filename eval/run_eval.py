"""评测：把「答得对」和「说得清」拆成两个数，一起报。

指标：
  dept_acc      科室准确率（结论里的 dept 是否命中 gold）
  exam_recall   检查项召回（gold 里任一检查是否进了结论）
  completeness  溯源完整率均值（每条结论的证据能不能核对到）
  avg_steps     决策链平均步数
  avg_ms        端到端耗时

用法：
    python -m app.seed            # 先灌数据
    python eval/run_eval.py --json eval/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "core"))
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.pipeline import answer  # noqa: E402
from medpal_core.ontology import version as onto_version  # noqa: E402
from medpal_core.storage import connect  # noqa: E402


def load(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _score_completeness(out: dict) -> float:
    """评测口径：没有证据的答案不算「可追溯」，直接记 0。

    trace.writer 里「无引用 = 1.0」是为了不冤枉纯推理步；
    但评测问的是「这条结论有没有证据撑着」，两者不能混。
    """
    if not out.get("evidence_count"):
        return 0.0
    return float(out.get("trace_completeness") or 0.0)


def run(db_path: str = "") -> dict:
    conn = connect(db_path or None)
    try:
        rows = load(REPO / "eval" / "dataset" / "v1.jsonl")
        cases = []
        for row in rows:
            out = answer(conn, row["q"])
            conc = out.get("conclusion") or {}
            dept_ok = bool(row.get("dept")) and row["dept"] == conc.get("dept")
            exam_ok = (not row.get("exams")) or any(
                e in (conc.get("exams") or []) for e in row["exams"])
            cases.append({
                "q": row["q"],
                "dept_ok": dept_ok,
                "exam_ok": exam_ok,
                "trace_id": out.get("trace_id"),
                "completeness": _score_completeness(out),
                "steps": len(out.get("paths") or []),
                "elapsed_ms": out.get("elapsed_ms"),
            })
        n = max(1, len(cases))
        cur = onto_version.current_version(conn)
        return {
            "ontology_version": (cur or {}).get("version"),
            "n": len(cases),
            "dept_acc": round(sum(c["dept_ok"] for c in cases) / n, 3),
            "exam_recall": round(sum(c["exam_ok"] for c in cases) / n, 3),
            "completeness": round(sum(c["completeness"] or 0 for c in cases) / n, 3),
            "zero_evidence": sum(1 for c in cases if not c["completeness"]),
            "avg_steps": round(sum(c["steps"] for c in cases) / n, 2),
            "avg_ms": round(sum(c["elapsed_ms"] or 0 for c in cases) / n, 1),
            "cases": cases,
        }
    finally:
        conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)
    report = run(args.db)
    for c in report["cases"]:
        flag = "OK " if (c["dept_ok"] and c["exam_ok"]) else "MISS"
        print(f"{flag} {c['q'][:30]:<32} completeness={c['completeness']}  {c['elapsed_ms']}ms")
    print("-" * 60)
    print(
        f"dept_acc={report['dept_acc']}  exam_recall={report['exam_recall']}  "
        f"completeness={report['completeness']}  avg_steps={report['avg_steps']}  "
        f"avg_ms={report['avg_ms']}  (n={report['n']})"
    )
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print("写入", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
