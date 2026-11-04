#!/usr/bin/env bash
# 合并门禁：只有 PR 的 head 提交拿到足够 approve 才允许合并。
# 用法：bash scripts/merge_pr.sh <PR号> [--dry-run]
#   自己的 PR 需要 2 个 APPROVED（两名队员各一个）；别人的 PR 需要 1 个 APPROVED。
# 设计原则：不提供 --force；要绕过只能手写 curl，那就必须在站会上说明并补追认记录。
# token 来源同 setup-branch-protection.sh：GITHUB_TOKEN → gh auth token → git credential。
set -eo pipefail
export PYTHONIOENCODING=utf-8

PR=""
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    "")        ;;
    *)         PR="$a" ;;
  esac
done
[ -n "$PR" ] || { echo "用法：bash scripts/merge_pr.sh <PR号> [--dry-run]"; exit 2; }

REPO="$MEDPAL_REPO"
[ -n "$REPO" ] || REPO="xiangyuli494-cmyk/medpal-trace"
OWNER="$(echo "$REPO" | cut -d/ -f1)"
NAME="$(echo "$REPO" | cut -d/ -f2)"
API="https://api.github.com/repos/$OWNER/$NAME"

TOKEN="$GITHUB_TOKEN"
if [ -z "$TOKEN" ] && command -v gh >/dev/null 2>&1; then
  TOKEN="$(gh auth token 2>/dev/null || true)"
fi
if [ -z "$TOKEN" ]; then
  TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')"
fi
[ -n "$TOKEN" ] || { echo "没有 GitHub token：export GITHUB_TOKEN=... 后重试"; exit 1; }

ME="$(curl -sS -H "Authorization: Bearer $TOKEN" https://api.github.com/user | python -c 'import sys,json;print(json.load(sys.stdin)["login"])')"

verdict="$(
PR="$PR" ME="$ME" TOKEN="$TOKEN" API="$API" python - <<'PY'
import json, os, urllib.request

pr_no, me, token, api = os.environ["PR"], os.environ["ME"], os.environ["TOKEN"], os.environ["API"]
H = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "merge-pr"}

def get(path):
    req = urllib.request.Request(api + path, headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

pr = get("/pulls/" + pr_no)
head = pr["head"]["sha"]
author = pr["user"]["login"]
state = pr["state"]
reviews = get("/pulls/%s/reviews" % pr_no)
approved = sorted({r["user"]["login"] for r in reviews if r["state"] == "APPROVED" and r["commit_id"] == head})
dismissed = sorted({r["user"]["login"] for r in reviews if r["state"] == "DISMISSED"})
need = 2 if author == me else 1
checks = get("/commits/%s/check-runs?per_page=100" % head)["check_runs"]
bad = [c["name"] + ":" + str(c["conclusion"]) for c in checks if c["conclusion"] not in ("success", "skipped", "neutral")]
ok = state == "open" and len(approved) >= need and not bad
print(json.dumps({"ok": ok, "pr": pr_no, "author": author, "head": head[:8],
                  "approved_on_head": approved, "need": need, "dismissed": dismissed,
                  "checks_bad": bad, "state": state}, ensure_ascii=False))
PY
)"

python - "$verdict" <<'PY'
import json, sys
v = json.loads(sys.argv[1])
print("PR #%s  author=%s  head=%s  需 approve=%d  实得=%s  已 dismiss=%s"
      % (v["pr"], v["author"], v["head"], v["need"],
         ",".join(v["approved_on_head"]) or "无", ",".join(v["dismissed"]) or "无"))
if v["checks_bad"]:
    print("未通过检查：", "; ".join(v["checks_bad"]))
if not v["ok"]:
    print("MERGE BLOCKED：state=%s，head 上有效 approve %d/%d，检查异常 %d 项。等 review，别手合。" % (v["state"], len(v["approved_on_head"]), v["need"], len(v["checks_bad"])))
    sys.exit(3)
print("MERGE ALLOWED")
PY

[ "$DRY" = 1 ] && { echo "--dry-run：不合并"; exit 0; }

curl -sS -X PUT -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API/pulls/$PR/merge" -d '{"merge_method":"squash"}' \
  | python -c 'import sys,json;d=json.load(sys.stdin);print("merged:",d.get("merged"),d.get("message",""))'