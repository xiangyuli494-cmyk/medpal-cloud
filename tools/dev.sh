#!/usr/bin/env bash
# 本地开发入口：装依赖、灌数据、起服务、跑检查。
# 用法：bash tools/dev.sh [install|seed|api|test|check|pr|eval|all]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python}"
export PYTHONIOENCODING=utf-8
export MEDPAL_DATA_DIR="${MEDPAL_DATA_DIR:-$ROOT/data}"

# Windows 的 Python 认分号 + 反斜杠，POSIX 认冒号 + 斜杠；
# 混用会得到 ModuleNotFoundError: No module named 'app'。
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    PC="$(cygpath -w "$ROOT/packages/core")"
    PA="$(cygpath -w "$ROOT/apps/api")"
    export PYTHONPATH="$PC;$PA"
    ;;
  *)
    export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"
    ;;
esac

case "${1:-all}" in
  install) "$PY" -m pip install -e ".[dev]" ;;
  seed)  "$PY" -m app.seed ;;
  api)   "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" ${RELOAD:---reload} ;;
  test)  "$PY" -m pytest -q ;;
  check) "$PY" tools/check_boundaries.py && "$PY" tools/check_guard_words.py ;;
  pr)    "$PY" -m ruff check . && "$PY" tools/check_boundaries.py \
           && "$PY" tools/check_guard_words.py && "$PY" -m pytest -q ;;
  eval)  "$PY" eval/run_eval.py ;;
  all)   "$PY" -m app.seed && "$PY" -m pytest -q && "$PY" tools/check_boundaries.py \
           && "$PY" tools/check_guard_words.py && "$PY" eval/run_eval.py ;;
  *)     echo "用法: bash tools/dev.sh [install|seed|api|test|check|pr|eval|all]"; exit 2 ;;
esac
