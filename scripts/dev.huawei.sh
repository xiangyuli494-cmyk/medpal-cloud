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
cd "$ROOT" || exit 1

# ---- Python 解释器回退（与 scripts/verify.sh 一致；额外验证能真的跑起来）----
_py_ok() {
  "$1" -c "import sys, threading" >/dev/null 2>&1
}
PY="${PY:-python}"
if ! command -v "$PY" >/dev/null 2>&1 || ! _py_ok "$PY"; then
  for cand in /e/Python/python.exe python3 /usr/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1 && _py_ok "$cand"; then PY="$cand"; break; fi
  done
fi
if ! command -v "$PY" >/dev/null 2>&1 || ! _py_ok "$PY"; then
  echo "FAIL: 找不到可用的 Python 解释器（试过 python / python3 / /usr/bin/python3），用 PY=... 指定" >&2
  exit 1
fi
export PY

PORT="${PORT:-8001}"
export PYTHONIOENCODING=utf-8

# ---- PYTHONPATH：Windows（Git Bash）用分号 + cygpath，POSIX 用冒号 ----
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    export PYTHONPATH="$(cygpath -w "$ROOT/packages/core");$(cygpath -w "$ROOT/apps/api")"
    ;;
  *)
    export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"
    ;;
esac

# ---- 加载 .env.huawei（不入库；先归一到 LF 再 source，避免 Windows CRLF 污染值）----
if [ -f .env.huawei ]; then
  set -a
  # shellcheck disable=SC1091
  . <(sed 's/\r$//' .env.huawei)
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
  echo "把变量写进 .env.huawei 后重跑（模板见 .env.huawei.example）" >&2
  exit 1
fi
echo "变量齐全：MEDPAL_DB_DSN=*** HUAWEI_AK=*** HUAWEI_SK=*** HUAWEI_OBS_BUCKET=${HUAWEI_OBS_BUCKET}"

if [ "${1:-}" = "--check" ]; then
  echo "仅检查变量，跳过 API 验证"
  exit 0
fi

# ---- 起 API（后台）----
# 端口预检：端口上若已有别的服务，后面的 curl 会打到它，造成假 PASS。
if curl -s -m 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  echo "FAIL: 端口 $PORT 已被占用，换 PORT=... 或先停掉占用进程" >&2
  exit 1
fi
echo "起 API 端口 $PORT ..."
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true' EXIT

# ---- 等 API 就绪：墙钟 30 秒，每次 curl 最多 2 秒 ----
READY_TIMEOUT=30
deadline=$((SECONDS + READY_TIMEOUT))
ready=0
while [ "$SECONDS" -lt "$deadline" ]; do
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "FAIL: API ${READY_TIMEOUT} 秒内没就绪" >&2
  exit 1
fi

# ---- 防假 PASS：确认端口上响应的是「自己起的」进程，不是别人占着端口 ----
kill -0 "$API_PID" 2>/dev/null || {
  echo "FAIL: 自己起的 API 已退出（端口被别的进程占了？）" >&2
  exit 1
}

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
