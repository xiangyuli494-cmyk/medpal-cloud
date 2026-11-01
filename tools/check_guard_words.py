"""禁用语检查：医疗类应用最容易出事的地方是「把演示说成承诺」。

扫描 README / docs / data/samples / apps/web，命中 tools/guard_words.txt 里任何一条就红。
代码与测试文件不扫（那里出现这些词往往是在写反例）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TARGETS = ["README.md", "docs", "data/samples", "apps/web"]
RULES = Path("tools/guard_words.txt")


def load_rules(path: Path = RULES) -> list:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _files(root: Path, target: str):
    p = root / target
    if p.is_file():
        yield p
    elif p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in {".md", ".html", ".txt", ".json"}:
                yield f


def check(root: Path = Path(".")) -> list:
    root = root.resolve()
    rules = load_rules(root / RULES)
    hits = []
    for target in TARGETS:
        for f in _files(root, target):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                for r in rules:
                    if r in line:
                        hits.append((str(f.relative_to(root)), line_no, r))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    hits = check(Path(args.root))
    for where, line, rule in hits:
        print(f"{where}:{line} 命中禁用语 {rule!r}")
    print("禁用语检查:", "通过" if not hits else f"失败 ({len(hits)} 处)")
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
