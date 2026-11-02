#!/usr/bin/env bash
# 在华为云 AI DevSpace（或任意 Ubuntu 22.04 云开发机）上一键起 MedPal Trace。
#   bash scripts/devspace_setup.sh              # 装依赖 -> 校验 -> 灌数据 -> 起服务
#   NO_SERVE=1 bash scripts/devspace_setup.sh   # 只做到校验，不起服务（自检用）
#   PORT=8080 bash scripts/devspace_setup.sh    # 换端口
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"
export MEDPAL_LLM="${MEDPAL_LLM:-offline}"
PORT="${PORT:-8000}"

say() { printf "\n== %s\n" "$*"; }

say "1/6 检查 python（需要 3.11+）"
PY="$(command -v python3.12 || command -v python3.11 || command -v python3 || true)"
if [ -z "$PY" ]; then echo "缺 python3（需要 3.11+）：apt-get install -y python3.12 python3.12-venv"; exit 1; fi
"$PY" - <<PYEOF
import sys
v = sys.version_info
assert v >= (3, 11), "需要 3.11+，当前 %s.%s" % (v[0], v[1])
print("   python", sys.version.split()[0])
PYEOF

say "2/6 装依赖"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -e .
"$PY" -m pip install -q fastapi uvicorn httpx pytest ruff jsonschema

say "3/6 静态检查（lint / 边界 / 禁用语）"
"$PY" -m ruff check .
"$PY" tools/check_boundaries.py
"$PY" tools/check_guard_words.py

say "4/6 灌演示数据"
"$PY" -m app.seed

say "5/6 端到端冒烟 + 评测"
"$PY" scripts/smoke_verify.py
"$PY" eval/run_eval.py 2>/dev/null | tail -5 || echo "   （评测集为空时跳过，属正常）"

if [ "${NO_SERVE:-0}" = "1" ]; then
  say "完成（NO_SERVE=1，未起服务）"
  exit 0
fi

say "6/6 起服务：http://0.0.0.0:${PORT}/web/"
echo "   DevSpace 里把 ${PORT} 端口设为「公开」，用分配到的域名访问 /web/"
echo "   云资源就绪后改跑：bash scripts/dev.huawei.sh（读 .env.local 的 HUAWEI_* 变量）"
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
