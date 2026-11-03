"""核心 SQL 必须两种后端都能跑：sqlite 私有的 INSERT OR REPLACE 一律拦下。

这个 bug 本地 sqlite 永远测不出来——只有真连 PG 才报语法错误，
所以用静态扫描把它钉死在 CI 里，别等上云才发现。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("INSERT OR REPLACE", "INSERT OR IGNORE", "REPLACE INTO")


def test_core_has_no_sqlite_only_upsert():
    core = ROOT / "packages" / "core"
    hits = []
    for path in core.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for kw in BANNED:
            if kw in text:
                hits.append(f"{path.relative_to(ROOT).as_posix()}: {kw}")
    assert not hits, "core 里有 sqlite 私有 SQL，PG 上会炸：\n" + "\n".join(hits)
