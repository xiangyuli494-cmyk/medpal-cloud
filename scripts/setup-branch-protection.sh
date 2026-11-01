#!/usr/bin/env bash
# 给 main 加保护：PR + 1 人 approve + CI 必绿 + 禁止直推/强推/删分支。
# 用法：bash scripts/setup-branch-protection.sh [OWNER/REPO] [--restrict] [--codeowner]
#   --restrict   只有队长能 push（公开仓 / Team 计划可用；免费私仓会返回 422）
#   --codeowner  要求 CODEOWNERS 里的人 approve。**先把 T1_HANDLE/T2_HANDLE/T3_HANDLE 换成真账号再开**，
#                否则 t1 自己的 PR 找不到可批准的 code owner，会永久卡在门禁上。
# token 来源：$GITHUB_TOKEN → gh auth token → git credential（GCM 缓存），三者取到即可，无需装 gh。
set -euo pipefail

REPO=""
FLAG_RESTRICT=0
FLAG_CODEOWNER=0
for a in "${@:-}"; do
  case "$a" in
    --restrict)  FLAG_RESTRICT=1 ;;
    --codeowner) FLAG_CODEOWNER=1 ;;
    "")          ;;
    *)           REPO="$a" ;;
  esac
done
REPO="${REPO:-xiangyuli494-cmyk/medpal-trace}"
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ] && command -v gh >/dev/null 2>&1; then
  TOKEN="$(gh auth token 2>/dev/null || true)"
fi
if [ -z "$TOKEN" ]; then
  TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')"
fi
[ -n "$TOKEN" ] || { echo "没有 GitHub token：export GITHUB_TOKEN=... 后重试"; exit 1; }

CAPTAIN="${CAPTAIN:-$OWNER}"
API="https://api.github.com/repos/$OWNER/$NAME"

echo "仓库 $REPO | 队长 $CAPTAIN | 限制推送 $([ $FLAG_RESTRICT = 1 ] && echo 是 || echo 否) | code owner 审批 $([ $FLAG_CODEOWNER = 1 ] && echo 是 || echo 否)"

BODY="$(RESTRICT="$FLAG_RESTRICT" CODEOWNER="$FLAG_CODEOWNER" CAPTAIN="$CAPTAIN" python - <<'PY'
import json, os
d = {
    "required_status_checks": {
        "strict": True,
        "contexts": ["test (3.11)", "test (3.12)", "meta", "size"],
    },
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "required_approving_review_count": 1,
        "require_last_push_approval": True,
    },
    "required_conversation_resolution": True,
    "allow_force_pushes": False,
    "allow_deletions": False,
    # PUT 接口要求这个键必须存在；没有就是 null（= 不限制推送人）
    "restrictions": None,
}
if os.environ.get("CODEOWNER") == "1":
    d["required_pull_request_reviews"]["require_code_owner_reviews"] = True
if os.environ.get("RESTRICT") == "1":
    d["restrictions"] = {"users": [os.environ["CAPTAIN"]], "teams": [], "apps": []}
print(json.dumps(d))
PY
)"

OUT="$PWD/.protect.out"
CODE="$(printf '%s' "$BODY" | curl -sS -o "$OUT" -w '%{http_code}' -X PUT "$API/branches/main/protection" \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" --data-binary @-)"
if [ "$CODE" = "422" ] && [ "$FLAG_RESTRICT" = "1" ] && grep -q "organization repositories" "$OUT" 2>/dev/null; then
  echo "！个人仓库不支持 Restrict who can push（只有 org 仓库有），自动退回「不加白名单」重试。"
  echo "！等价做法：t2/t3 不给 write 权限，走 fork + PR，merge 仍然只有队长能做。"
  FLAG_RESTRICT=0
  BODY="$(printf '%s' "$BODY" | python -c "import json,sys; d=json.load(sys.stdin); d['restrictions'] = None; print(json.dumps(d))")"
  CODE="$(printf '%s' "$BODY" | curl -sS -o "$OUT" -w '%{http_code}' -X PUT "$API/branches/main/protection" \
    -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" --data-binary @-)"
fi

if [ "$CODE" != "204" ] && [ "$CODE" != "200" ]; then
  echo "PUT 失败 HTTP $CODE"
  python -c "import json;d=json.load(open('$OUT'));print(d.get('message'));print((d.get('errors') or [''])[0])" 2>/dev/null || cat "$OUT"
  exit 1
fi

curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$API/branches/main/protection" | PYTHONIOENCODING=utf-8 python -c "
import sys, json
d = json.load(sys.stdin)
pr = d.get('required_pull_request_reviews') or {}
checks = d.get('required_status_checks', {}).get('contexts', []) or []
print('approve 数     :', pr.get('required_approving_review_count'))
print('撤销旧 approve :', pr.get('dismiss_stale_reviews'))
print('code owner 审  :', pr.get('require_code_owner_reviews', False))
print('必绿检查       :', ', '.join(checks))
print('严格模式       :', d.get('required_status_checks', {}).get('strict'))
print('管理员同样受限 :', d.get('enforce_admins', {}).get('enabled'))
print('禁止强推       :', not d.get('allow_force_pushes', {}).get('enabled'))
print('禁止删分支     :', not d.get('allow_deletions', {}).get('enabled'))
r = d.get('restrictions')
print('推送白名单     :', [u['login'] for u in (r or {}).get('users', [])] or '未开启')
"

echo "完成。验证保护是否生效：git push origin HEAD:main  ->  protected branch hook declined"
