#!/usr/bin/env bash
# check_image.sh — B5 镜像验收：build → 起容器 → /health 200 → seed → /v1/ask 冒烟 → 查大小 → 清理。
#
# 用法：
#   bash scripts/check_image.sh
#   IMAGE=medpal-trace:test PORT=18080 MAX_MB=600 bash scripts/check_image.sh
#   bash scripts/verify.sh --image                # 挂在一键验收里跑（可选步骤）
#
# 验收标准（B5）：docker build 成功；容器内 /health 返回 200；容器能 seed 并回答一次提问；
# 镜像 < 600MB。没有 Docker 或 daemon 没起来时，这一步是「没法验」而不是「验不过」——
# verify.sh 里会打印 SKIP，单独跑本脚本则给出可操作的提示。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

IMAGE="${IMAGE:-medpal-trace:0.1.0}"
CONTAINER="${CONTAINER:-medpal-image-check}"
PORT="${PORT:-18080}"
MAX_MB="${MAX_MB:-600}"
QUESTION="${QUESTION:-上腹隐痛伴反酸，下一步做什么检查？}"

if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker 不在 PATH，B5 必须在有 Docker 的机器跑" >&2
  exit 1
fi

# daemon 没起来时 docker build 只会甩一句 failed to connect to the docker API at npipe://...
# 这里先判一次，给一句能照着做的提示（Windows 上就是「先把 Docker Desktop 起来」）。
if ! docker info >/dev/null 2>&1; then
  echo "FAIL: Docker daemon 没起来（docker 命令在，但连不上 daemon）" >&2
  echo "      先把 Docker Desktop 启动起来并等状态变绿；Linux 上 sudo systemctl start docker" >&2
  exit 1
fi

# 解析 JSON 用宿主机的 Python；没有 python3 的 Windows 机器退回 PY 或常见安装路径。
PY_BIN="${PY:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python /e/Python/python.exe; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ]; then
  echo "FAIL: 找不到 Python，用来解析 /health 与 /v1/ask 的响应（可用 PY=... 指定）" >&2
  exit 1
fi

cleanup() {
  # -v 连匿名卷一起删：镜像声明了 VOLUME /app/data，只 rm 容器会留下悬空卷
  docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---- 1. build ----
echo "== docker build -t $IMAGE ."
docker build -t "$IMAGE" .

# ---- 2. 起容器 ----
echo "== docker run ($PORT -> 8000)"
cleanup
docker run -d --name "$CONTAINER" -p "$PORT:8000" "$IMAGE" >/dev/null

# ---- 3. 等 /health 就绪（墙钟 30 秒）----
echo -n "等 /health"
ready=0
deadline=$((SECONDS + 30))
while [ "$SECONDS" -lt "$deadline" ]; do
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  echo -n "."
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo " 超时"
  echo "--- 容器日志 ---" >&2
  docker logs "$CONTAINER" 2>&1 | tail -30 >&2
  echo "FAIL: /health 30 秒内没返回 200" >&2
  exit 1
fi
echo " ok"

# ---- 4. 验 /health 内容 ----
HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/health")
if ! "$PY_BIN" -c '
import json, sys
d = json.loads(sys.argv[1])
if d.get("ok") is not True:
    print("FAIL: /health ok 不是 true", file=sys.stderr)
    sys.exit(1)
print("  storage =", d.get("storage"))
' "$HEALTH"; then
  echo "FAIL: /health 内容不符合预期" >&2
  exit 1
fi

# ---- 5. 容器内 seed：没数据的容器 /health 也是 200，必须真的灌一次 ----
echo "== docker exec python -m app.seed"
if ! docker exec "$CONTAINER" python -m app.seed >/dev/null 2>&1; then
  echo "--- 容器日志 ---" >&2
  docker logs "$CONTAINER" 2>&1 | tail -20 >&2
  echo "FAIL: 容器内 seed 失败（数据目录不可写或样本缺失）" >&2
  exit 1
fi
HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/health")
ONTO=$("$PY_BIN" -c 'import json,sys; print(json.loads(sys.argv[1]).get("ontology_version") or "")' "$HEALTH")
ASSETS=$("$PY_BIN" -c 'import json,sys; print(json.loads(sys.argv[1]).get("assets") or 0)' "$HEALTH")
echo "  ontology_version = ${ONTO:-<空>}  assets = $ASSETS"
if [ -z "$ONTO" ] || [ "$ASSETS" -lt 1 ]; then
  echo "FAIL: seed 之后 /health 仍没有本体版本或资产（ontology_version=$ONTO assets=$ASSETS）" >&2
  exit 1
fi

# ---- 6. /v1/ask 冒烟：能 seed 不等于能答，答一条并回读 trace ----
echo "== /v1/ask 冒烟"
ASK=$(curl -fsS -m 30 -X POST "http://127.0.0.1:$PORT/v1/ask" \
  -H 'content-type: application/json' \
  -d "{\"question\": \"$QUESTION\"}")
TRACE_ID=$("$PY_BIN" -c 'import json,sys; print(json.loads(sys.argv[1]).get("trace_id") or "")' "$ASK")
if ! "$PY_BIN" -c '
import json, sys
d = json.loads(sys.argv[1])
if d.get("ok") is not True:
    print("FAIL: /v1/ask ok 不是 true", file=sys.stderr); sys.exit(1)
if not d.get("trace_id"):
    print("FAIL: /v1/ask 没返回 trace_id", file=sys.stderr); sys.exit(1)
if not d.get("paths"):
    print("FAIL: /v1/ask 决策链为空", file=sys.stderr); sys.exit(1)
print("  trace_id =", d["trace_id"], " steps =", len(d["paths"]),
      " completeness =", d.get("trace_completeness"))
' "$ASK"; then
  echo "FAIL: /v1/ask 冒烟不通过" >&2
  exit 1
fi
curl -fsS -m 10 "http://127.0.0.1:$PORT/v1/traces/$TRACE_ID" >/dev/null || {
  echo "FAIL: trace $TRACE_ID 回读失败" >&2
  exit 1
}
echo "  trace 回读 ok"

# ---- 7. 镜像大小 ----
SIZE_BYTES=$(docker image inspect "$IMAGE" --format '{{.Size}}')
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
echo "  镜像大小: ${SIZE_MB}MB（上限 ${MAX_MB}MB）"
if [ "$SIZE_MB" -gt "$MAX_MB" ]; then
  echo "FAIL: 镜像 ${SIZE_MB}MB 超过 ${MAX_MB}MB" >&2
  exit 1
fi

echo
echo "IMAGE READY: ${SIZE_MB}MB < ${MAX_MB}MB, /health 200, seed ok, /v1/ask ok"
