"""边界检查：底座到底是不是「可复用」。

三条规则，任何一条挂了 CI 就红：
  B1  packages/core 不得 import 应用层（apps / app），依赖方向只能 apps -> core。
  B2  云厂商 SDK 只允许出现在 medpal_core/providers/ 下。
  B3  core 里不得出现行业词表里的术语 —— 领域知识必须待在 data/lexicon/medical.json。
      这条是「与行业无关」这句话的机器证明，不是文档口号。

用法：python tools/check_boundaries.py [--root .] [--json]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tokenize
from pathlib import Path

CORE = Path("packages/core/medpal_core")
PROVIDERS = CORE / "providers"
LEXICON = Path("data/lexicon/medical.json")
VENDOR_SDKS = {"obs", "psycopg", "psycopg2", "pymysql", "redis", "boto3", "openai", "zhipuai"}
APP_TOPS = {"apps", "app"}


def _py_files(root: Path, base: Path):
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p, p.relative_to(root)


def _code_only(path: Path) -> str:
    """去掉注释与字符串（含 docstring），只留下真正会被执行的标识符与符号。

    领域词出现在文档字符串里是「解释」，出现在代码里才是「耦合」——
    这条区分决定了 B3 检查是可用的还是只会逼人删注释。
    """
    keep = {tokenize.NAME, tokenize.OP, tokenize.NUMBER}
    out = []
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in keep:
                out.append(tok.string)
    return " ".join(out)


def _imports(tree: ast.AST):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.append(node.module)
    return out


def check(root: Path = Path(".")) -> list:
    root = root.resolve()
    violations = []
    core = root / CORE

    for path, rel in _py_files(root, core):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            violations.append(("B0", str(rel), "语法错误: " + str(exc)))
            continue
        for mod in _imports(tree):
            top = mod.split(".")[0]
            if top in APP_TOPS:
                violations.append(("B1", str(rel), "core 反向依赖应用层: " + mod))
            if top in VENDOR_SDKS and not str(rel).replace("\\", "/").startswith(PROVIDERS.as_posix()):
                violations.append(("B2", str(rel), "云/数据库 SDK 出现在 providers 之外: " + mod))

    lex_path = root / LEXICON
    if lex_path.exists():
        terms = json.loads(lex_path.read_text(encoding="utf-8")).get("terms") or []
        for path, rel in _py_files(root, core):
            try:
                text = _code_only(path)
            except (tokenize.TokenError, SyntaxError):
                continue
            for t in terms:
                if t in text:
                    violations.append(("B3", str(rel), "core 里出现行业术语: " + t))
    return violations


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    v = check(Path(args.root))
    if args.json:
        print(json.dumps({"ok": not v, "violations": v}, ensure_ascii=False, indent=2))
    else:
        for rule, where, msg in v:
            print(f"[{rule}] {where}: {msg}")
        print("边界检查:", "通过" if not v else f"失败 ({len(v)} 处)")
    return 0 if not v else 1


if __name__ == "__main__":
    sys.exit(main())
