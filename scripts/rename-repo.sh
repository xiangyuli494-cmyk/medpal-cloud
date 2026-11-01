#!/usr/bin/env bash
# 一条命令换仓库名：GitHub 改名 + 本地 remote + 全仓字符串 + 提交推送 + 保护临时开关。
# 用法：bash scripts/rename-repo.sh <new-name>      例：bash scripts/rename-repo.sh medpal-atlas
# 名字规则：小写字母/数字/短横线，2-100 字符，不能以短横线开头。
set -euo pipefail

NEW="${1:-}"
[ -n "$NEW" ] || { echo "用法：bash scripts/rename-repo.sh <new-name>"; exit 1; }
printf '%s' "$NEW" | grep -Eq '^[a-z0-9][a-z0-9-]{1,99}$' || { echo "名字不合法：$NEW（小写字母/数字/短横线）"; exit 1; }

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ] && command -v gh >/dev/null 2>&1; then TOKEN="$(gh auth token 2>/dev/null || true)"; fi
if [ -z "$TOKEN" ]; then
  TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')"
fi
[ -n "$TOKEN" ] || { echo "没有 GitHub token：export GITHUB_TOKEN=... 后重试"; exit 1; }

REMOTE="$(git remote get-url origin)"
OLD="$(printf '%s' "$REMOTE" | sed -E 's#.*/([^/]+?)(\.git)?$#\1#')"
OWNER="$(printf '%s' "$REMOTE" | sed -E 's#.*[:/]([^/]+)/[^/]+$#\1#')"
[ "$OLD" = "$NEW" ] && { echo "已经是 $NEW 了"; exit 0; }
API="https://api.github.com/repos/$OWNER/$OLD"
echo "改名：$OWNER/$OLD  ->  $OWNER/$NEW"

# 1) GitHub 侧改名（旧 URL 会自动 301 到新 URL）
CODE="$(curl -sS -o .rename.out -w '%{http_code}' -X PATCH -H "Authorization: Bearer $TOKEN" \
  --data-binary "{\"name\":\"$NEW\"}" "$API")"
if [ "$CODE" != "200" ]; then echo "改名失败 HTTP $CODE"; cat .rename.out; rm -f .rename.out; exit 1; fi
rm -f .rename.out

# 2) 本地 remote 指到新地址
git remote set-url origin "https://github.com/$OWNER/$NEW.git"

# 3) 全仓字符串替换（跳过 .git 与二进制）
grep -rl --exclude-dir=.git --exclude='*.png' --exclude='*.jpg' --exclude='*.pdf' "$OLD" . 2>/dev/null \
  | while read -r f; do
      python - "$f" "$OLD" "$NEW" <<'PY'
import io, sys
p, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
data = io.open(p, encoding="utf-8", newline="").read()
io.open(p, "w", encoding="utf-8", newline="").write(data.replace(old, new))
PY
    done
# 写入工具可能保留原 mtime，git 会误判「未修改」，所以统一刷新时间戳
find . -path ./.git -prune -o -type f -print0 | xargs -0 touch

# 4) 提交（main 有保护时先临时拆，推完立刻打回）
BASE_API="https://api.github.com/repos/$OWNER/$NEW"
curl -sS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE_API/branches/main/protection" || true
git add -A
git commit -q -m "chore: 仓库改名 $NEW" || echo "没有内容变化，跳过提交"
GIT_TERMINAL_PROMPT=0 git push origin main
for S in scripts/setup-branch-protection.sh; do
  [ -f "$S" ] && bash "$S" "$OWNER/$NEW" | tail -n 6
done

echo
echo "完成。本地目录名不会自动改，手动执行："
echo "  cd .. && mv $(basename "$PWD") $NEW && cd $NEW"
