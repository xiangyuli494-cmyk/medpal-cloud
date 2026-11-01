#!/usr/bin/env bash
# 一键给 main 加保护：PR + 1 approval + CI 必绿 + 禁止直推/强推。
# 前置：gh auth login（有 repo 权限）、仓库已在 GitHub 上、CI 至少成功跑过一次（状态检查名才对得上）。
# 用法：bash scripts/setup-branch-protection.sh [OWNER/REPO] [--restrict]
#   --restrict  只有队长能 push/merge。免费私仓不支持该开关；公开仓或 Team 计划可用。
#               用不了时改走 fork 流程：队员只有读权限，从自己的 fork 提 PR，merge 只有队长能做。
set -euo pipefail

REPO="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
FLAG="${2:-}"
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
CAPTAIN="${CAPTAIN:-$(gh api user -q .login)}"

echo "仓库: $REPO    队长: $CAPTAIN    限制推送: ${FLAG:-否}"

BODY=$(cat <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["test (3.11)", "test (3.12)", "meta", "size"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
)

if [ "$FLAG" = "--restrict" ]; then
  BODY=$(printf '%s' "$BODY" | python -c "import json,sys; d=json.load(sys.stdin); d['restrictions']={'users':['$CAPTAIN'],'teams':[],'apps':[]}; print(json.dumps(d))")
fi

printf '%s' "$BODY" | gh api -X PUT "repos/$OWNER/$NAME/branches/main/protection" \
  -H "Accept: application/vnd.github+json" --input - > /dev/null

gh api "repos/$OWNER/$NAME/branches/main/protection" -q \
  '"PR 必须 " + (.required_pull_request_reviews.required_approving_review_count|tostring) + " 个 approve; 强推 " + (.allow_force_pushes.enabled|tostring) + "; 管理员受限 " + (.enforce_admins.enabled|tostring)'

echo "完成。直推 main 现在应当被拒：git push origin HEAD:main  ->  protected branch hook declined"
