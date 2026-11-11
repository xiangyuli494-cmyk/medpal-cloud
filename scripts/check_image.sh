#!/usr/bin/env bash
# check_image.sh — B5 镜像验收：build → 起容器 → curl /health → 查大小 → 清理。
#
# 用法：
#   bash scripts/check_image.sh
#   IMAGE=medpal-trace:test PORT=18080 MAX_MB=600 bash scripts/check_image.sh
#
# 验收标准（B5）：docker build 成功；容器内 /health 返回 200；镜像 < 600MB。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

IMAGE="${IMAGE:-medpal-trace:0.1.0}"
CONTAINER="${CONTAINER:-medpal-image-check}"
PORT="${PORT:-18080}"
MAX_MB="${MAX_MB:-600}"

if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker 不在 PATH，B5 必须在有 Docker 的机器跑" >&2
  exit 1
fi

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
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
curl -fsS "http://127.0.0.1:$PORT/health" | "${PY:-python3}" -c '
import json, sys
d = json.load(sys.stdin)
if d.get("ok") is not True:
    print("FAIL: /health ok 不是 true", file=sys.stderr)
    sys.exit(1)
print("  storage =", d.get("storage"))
print("  ontology_version =", d.get("ontology_version"))
' || {
  echo "FAIL: /health 内容不符合预期" >&2
  exit 1
}

# ---- 5. 镜像大小 ----
SIZE_BYTES=$(docker image inspect "$IMAGE" --format '{{.Size}}')
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
echo "  镜像大小: ${SIZE_MB}MB（上限 ${MAX_MB}MB）"
if [ "$SIZE_MB" -gt "$MAX_MB" ]; then
  echo "FAIL: 镜像 ${SIZE_MB}MB 超过 ${MAX_MB}MB" >&2
  exit 1
fi

echo
echo "IMAGE READY: ${SIZE_MB}MB < ${MAX_MB}MB, /health 200"