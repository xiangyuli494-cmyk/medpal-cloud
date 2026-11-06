#!/usr/bin/env bash
# dev.huawei.sh — 一键检查华为云配置并验证线上就绪度（B3 交付物）。
#
# 用法：
#   bash scripts/dev.huawei.sh              检查变量 + 起 API + 验 /v1/cloud /health
#   bash scripts/dev.huawei.sh --check      只检查变量，不起 API
#
# 验收标准（B3）：
#   缺变量时打印「缺 XXX」并退出码 1；
#   变量齐时 /v1/cloud 返回 ready.gaussdb=true，/health 的 storage 显示 gaussdb。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python}"
PORT="${PORT:-8001}"
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"

# ---- 加载 .env.huawei（不入库，存在就 source）----
if [ -f .env.huawei ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env.huawei
  set +a
  echo "已加载 .env.huawei"
fi

# ---- 依赖检查：必需变量 ----
missing=()
if [ -z "${MEDPAL_DB_DSN:-}" ] && [ -z "${HUAWEI_GAUSSDB_DSN:-}" ]; then
  missing+=("MEDPAL_DB_DSN")
fi
[ -n "${HUAWEI_AK:-}" ] || missing+=("HUAWEI_AK")
[ -n "${HUAWEI_SK:-}" ] || missing+=("HUAWEI_SK")
[ -n "${HUAWEI_OBS_BUCKET:-}" ] || missing+=("HUAWEI_OBS_BUCKET")

if [ ${#missing[@]} -gt 0 ]; then
  echo "缺 ${missing[*]}" >&2
  echo "把变量写进 .env.huawei 后重跑（模板见 .env.example）" >&2
  exit 1
fi
echo "变量齐全：MEDPAL_DB_DSN=*** HUAWEI_AK=*** HUAWEI_SK=*** HUAWEI_OBS_BUCKET=${HUAWEI_OBS_BUCKET}"

if [ "${1:-}" = "--check" ]; then
  echo "仅检查变量，跳过 API 验证"
  exit 0
fi

# ---- 起 API（后台）----
echo "起 API 端口 $PORT ..."
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true' EXIT

# ---- 等 API 就绪 ----
ready=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "FAIL: API 30 秒内没起" >&2
  exit 1
fi

# ---- 验证 /v1/cloud 与 /health ----
"$PY" - <<PY
import json
import sys
import urllib.request

base = "http://127.0.0.1:$PORT"


def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


cloud = get("/v1/cloud")
health = get("/health")
ready = cloud.get("ready") or {}
ok = True

print("== /v1/cloud")
print(f"  storage_backend={cloud.get('storage_backend')}")
print(f"  ready={ready}")
print(f"  missing={cloud.get('missing')}")

print("== /health")
print(f"  storage={health.get('storage')}")
print(f"  ontology_version={health.get('ontology_version')}")

if not ready.get("gaussdb"):
    print("FAIL: ready.gaussdb 不是 true", file=sys.stderr)
    ok = False
if health.get("storage") != "gaussdb":
    print("FAIL: /health storage 不是 gaussdb", file=sys.stderr)
    ok = False
if not ok:
    sys.exit(1)
print()
print("HUAWEI READY: ready.gaussdb=true, storage=gaussdb")
PY

echo
echo "PASS: B3 验收通过（变量齐 + /v1/cloud ready.gaussdb=true + /health storage=gaussdb）"