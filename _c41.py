
import json, os, urllib.request
TOKEN = os.environ["GH_TOKEN"]
API = "https://api.github.com/repos/xiangyuli494-cmyk/medpal-trace"
def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
        "User-Agent": "x", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        print("!", method, e.code, e.read().decode()[:160]); return None
msg = "任务台账统一到 docs/05（按周 × 人 + 验收标准），打卡表与执行手册下线。"
call("POST", API + "/issues/41/comments", {"body": msg})
r = call("PATCH", API + "/issues/41", {"state": "closed", "state_reason": "not_planned"})
print("issue41:", r["state"] if r else "fail")
