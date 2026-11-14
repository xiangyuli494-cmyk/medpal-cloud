#!/usr/bin/env bash
# 一键验收（C3）：lint → 边界 → 禁用语 → 测试 → 灌数据 → 端到端冒烟 → 指标阈值。
# 正常状态打印 PASS 且退出码 0；任何一项失败打印原因且退出码 1。
#
# 用法：
#   bash scripts/verify.sh                    全量，默认阈值（n>=6，dept_acc>=0.80）
#   bash scripts/verify.sh --fast             跳过评测（本地改代码时秒级反馈）
#   MIN_N=30 MIN_DEPT_ACC=0.85 bash scripts/verify.sh     G1/G2 门槛用
#   bash scripts/verify.sh --self-test        负向自测：临时副本里塞一条 BND1 违规，必须 FAIL
#   bash scripts/verify.sh --image            额外跑 B5 镜像验收（build + /health + seed + /v1/ask）
#
# 换 Python：PY=/usr/bin/python3.12 bash scripts/verify.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

PY="${PY:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  for cand in /e/Python/python.exe python3 /usr/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
export PY

export PYTHONIOENCODING=utf-8
export MEDPAL_LLM="${MEDPAL_LLM:-offline}"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    export PYTHONPATH="$(cygpath -w "$ROOT/packages/core");$(cygpath -w "$ROOT/apps/api")"
    ;;
  *)
    export PYTHONPATH="$ROOT/packages/core:$ROOT/apps/api"
    ;;
esac

MODE="full"
IMAGE_CHECK=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --fast) MODE="fast" ;;
    --self-test) MODE="selftest" ;;
    --image) IMAGE_CHECK=1 ;;
    --help|-h)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：$1（可用 --fast / --self-test / --image / --help）"; exit 2 ;;
  esac
  shift
done

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t verify)"
trap 'rm -rf "$TMP"' EXIT
# 库和报告写到临时目录：验收不该污染 data/，也不该受本地残留数据影响。
export MEDPAL_DB="$TMP/verify.db"
export MEDPAL_REPORT_DIR="$TMP/reports"

MIN_N="${MIN_N:-6}"
MIN_DEPT_ACC="${MIN_DEPT_ACC:-0.80}"
FAILS=0

run() {
  local name="$1"; shift
  local log="$TMP/${name// /_}.log"
  if "$@" >"$log" 2>&1; then
    printf '     ok   %s\n' "$name"
  else
    printf '     FAIL %s\n' "$name"
    tail -12 "$log" | sed 's/^/          | /'
    FAILS=$((FAILS + 1))
  fi
}

echo "== verify.sh  ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "   python    : $PY"
echo "   pythonpath: $PYTHONPATH"

run "lint (ruff)"          "$PY" -m ruff check .
run "边界 BND1-BND3"       "$PY" tools/check_boundaries.py
run "禁用语"               "$PY" tools/check_guard_words.py
run "单元测试 (pytest)"    "$PY" -m pytest -q
run "灌演示数据 (seed)"    "$PY" -m app.seed
run "端到端冒烟 (smoke)"   "$PY" scripts/smoke_verify.py

# B5 镜像验收是可选步骤：默认不跑（一次 build 要十几秒到几分钟，还依赖 Docker）。
# 必须显式 --image，或者 VERIFY_IMAGE=1 bash scripts/verify.sh。
# 机器上没有 docker / daemon 没起来时打印 SKIP 而不是 FAIL —— 那是「没法验」，不是「验不过」。
if [ "$IMAGE_CHECK" = "1" ] || [ "${VERIFY_IMAGE:-0}" = "1" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    printf '     SKIP 镜像验收 (B5)  docker 不在 PATH\n'
  elif ! docker info >/dev/null 2>&1; then
    printf '     SKIP 镜像验收 (B5)  Docker daemon 没起来（先启动 Docker Desktop）\n'
  else
    run "镜像验收 (B5)" bash scripts/check_image.sh
  fi
fi

# 模型连通性：没配 key 时打印 SKIP 不算失败（本地/CI 常态），配了就必须真通。
# 想让没买模型也算失败，跑 VERIFY_STRICT_LLM=1 bash scripts/verify.sh。
LLM_ARGS=""
[ "${VERIFY_STRICT_LLM:-0}" = "1" ] && LLM_ARGS="--strict"
run "模型连通性 (smoke_llm)" "$PY" scripts/smoke_llm.py $LLM_ARGS

if [ "$MODE" != "fast" ]; then
  if "$PY" eval/run_eval.py --json "$TMP/eval.json" >"$TMP/eval.log" 2>&1; then
    if "$PY" - "$TMP/eval.json" "$MIN_N" "$MIN_DEPT_ACC" >"$TMP/gate.log" 2>&1 <<'PYEOF'
import json, sys
path, min_n, min_acc = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
r = json.load(open(path, encoding="utf-8"))
n, acc, zero = r["n"], r["dept_acc"], r.get("zero_evidence", 0)
print(f"n={n} dept_acc={acc} completeness={r['completeness']} zero_evidence={zero}")
bad = []
if n < min_n:
    bad.append(f"样本量 {n} < {min_n}")
if acc < min_acc:
    bad.append(f"dept_acc {acc} < {min_acc}")
if zero:
    bad.append(f"有 {zero} 条零证据用例")
if bad:
    print("门槛未过: " + "; ".join(bad))
    sys.exit(1)
PYEOF
    then
      printf '     ok   指标门槛  %s\n' "$(tail -1 "$TMP/gate.log")"
    else
      printf '     FAIL 指标门槛\n'
      sed 's/^/          | /' "$TMP/gate.log"
      FAILS=$((FAILS + 1))
    fi
  else
    printf '     FAIL 评测跑不起来\n'
    tail -10 "$TMP/eval.log" | sed 's/^/          | /'
    FAILS=$((FAILS + 1))
  fi
fi

if [ "$MODE" = "selftest" ]; then
  echo
  echo "== 负向自测：往 core 里塞一条 BND1 违规，verify --fast 必须以非 0 退出"
  SELFTEST_OK=0
  if bash scripts/_verify_broken.sh "$TMP"; then SELFTEST_OK=1; fi
  if [ "$FAILS" -eq 0 ] && [ "$SELFTEST_OK" -eq 1 ]; then
    echo "自测: 违规被抓住（退出码非 0）"
  else
    echo "自测: 违规没被抓住 —— verify.sh 不可信"
    FAILS=$((FAILS + 1))
  fi
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL ($FAILS 项)"
exit 1
