#!/usr/bin/env bash
# verify.sh --self-test 的配角：复制一份干净的仓库，注入一条 BND1 违规，
# 跑 verify --fast，断言它非 0 退出且在输出里点名 BND1。
# 正常情况下你不该单独调用它。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$1/selftest"
mkdir -p "$WORK"

tar -C "$ROOT" -cf - \
  --exclude=.git --exclude=__pycache__ --exclude='*.db' --exclude=reports \
  packages apps tools eval tests scripts data pyproject.toml Makefile \
  | tar -C "$WORK" -xf - || exit 2

# 塞进 TYPE_CHECKING 里：AST 能看见 import，运行时不会真的去导 apps。
cat >> "$WORK/packages/core/medpal_core/config.py" <<'EOF'

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # BND1 负向自测
    from apps.api import main as _self_test_violation  # noqa: F401
EOF

cd "$WORK" || exit 2
OUT="$(PY="$PY" bash scripts/verify.sh --fast 2>&1)"
RC=$?
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q 'BND1'; then
  exit 0
fi
printf '%s\n' "$OUT" | tail -20
exit 1
