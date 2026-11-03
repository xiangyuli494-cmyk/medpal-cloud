#!/usr/bin/env bash
# dev_pg.sh — 一键起本地 Postgres 16 + 跑方言层自检（B1 交付物）。
#
# 用法：
#   bash scripts/dev_pg.sh                  起容器 + 自检
#   bash scripts/dev_pg.sh --down           停并删容器
#   PG_PORT=5433 bash scripts/dev_pg.sh     换端口
#
# 验收标准（B1）：postgres:16 起得来；prepare() 建表成功；
# seed 8 条；kg_query 返回 8 条路径，与 SQLite 结果一致。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONTAINER="medpal-pg16"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASS="${PG_PASS:-postgres}"
PG_DB="medpal"
IMAGE="postgres:16"

PY="${PY:-python}"
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"

# ---- --down：停容器 ----
if [ "${1:-}" = "--down" ]; then
  echo "停容器 $CONTAINER ..."
  docker rm -f "$CONTAINER" 2>/dev/null || true
  echo "done"
  exit 0
fi

# ---- 前置检查 ----
if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker 不在 PATH，先装 Docker 或用 Podman" >&2
  exit 1
fi

# ---- 起容器（已存在就复用）----
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "复用已运行的容器 $CONTAINER"
else
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker rm -f "$CONTAINER" >/dev/null
  fi
  echo "起 $IMAGE（端口 $PG_PORT -> 5432）..."
  docker run -d --name "$CONTAINER" \
    -e POSTGRES_PASSWORD="$PG_PASS" \
    -e POSTGRES_USER="$PG_USER" \
    -p "$PG_PORT:5432" \
    "$IMAGE" >/dev/null
fi

# ---- 等 PG 就绪 ----
echo -n "等 PG 就绪"
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then
    echo " ok"
    break
  fi
  echo -n "."
  sleep 1
else
  echo " 超时"
  echo "FAIL: PG 30 秒内没就绪" >&2
  exit 1
fi

# ---- 建 medpal 库（坑4：PG15+ 需要属于用户的库）----
docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c "CREATE DATABASE $PG_DB;" 2>/dev/null \
  || echo "库 $PG_DB 已存在，跳过"

# ---- 装 psycopg（如果没装）----
if ! "$PY" -c "import psycopg" 2>/dev/null; then
  echo "装 psycopg[binary] ..."
  "$PY" -m pip install -q "psycopg[binary]" || {
    echo "FAIL: psycopg 装不上" >&2; exit 1; }
fi

# ---- 设 DSN + 跑自检 ----
export MEDPAL_DB_DSN="postgresql://$PG_USER:$PG_PASS@127.0.0.1:$PG_PORT/$PG_DB"
export MEDPAL_DB_BACKEND=postgres

echo "DSN=postgresql://$PG_USER:***@127.0.0.1:$PG_PORT/$PG_DB"
echo "== check_pg.py"
echo

if "$PY" scripts/check_pg.py; then
  echo
  echo "PASS: B1 验收通过（postgres:16 + prepare + seed 8 + kg_query 8 条路径一致）"
  exit 0
else
  echo
  echo "FAIL: check_pg.py 未通过" >&2
  exit 1
fi
