"""OBS 连通自检：验 AK/SK/桶/region 四件套能不能真的读写。

不是单元测试，是「上云第一步」的手工验收入口：把 .env.local 里的凭据
和桶连起来，跑一次 put/get/delete，通不通一眼看到。
退出码：0 通；2 缺依赖；3 缺配置；4 云端报错。

用法：
    python scripts/check_obs.py
    python scripts/check_obs.py --env .env.local --keep
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEED = ("HUAWEI_AK", "HUAWEI_SK", "HUAWEI_OBS_BUCKET")
KEY = "_selftest/hello.txt"
BODY = "medpal-trace obs selftest\n"


def load_env(path: Path) -> dict[str, str]:
    """读 .env.local：KEY=VALUE，# 注释，值两边引号去掉。已存在的环境变量优先。"""
    data: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            data[k.strip()] = v
    for k in list(data) + list(NEED):
        if os.environ.get(k):
            data[k] = os.environ[k]
    return data


def mask(v: str) -> str:
    """脱敏打印：AK/SK 绝不整只打到终端，日志和录屏都可能外传。"""
    if not v:
        return "(空)"
    if len(v) <= 8:
        return v[:2] + "***"
    return v[:4] + "***" + v[-2:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="验华为云 OBS 四件套能否读写")
    ap.add_argument("--env", default=str(ROOT / ".env.local"))
    ap.add_argument("--keep", action="store_true", help="保留自检对象，便于去控制台看")
    ap.add_argument("--bucket", default="", help="临时覆盖 HUAWEI_OBS_BUCKET")
    args = ap.parse_args(argv)

    cfg = load_env(Path(args.env))
    if args.bucket:
        cfg["HUAWEI_OBS_BUCKET"] = args.bucket
    region = cfg.get("HUAWEI_REGION") or "cn-north-4"

    print("1) 配置 " + args.env)
    for k in NEED:
        print("   " + k + " = " + mask(cfg.get(k, "")))
    print("   HUAWEI_REGION = " + region)
    missing = [k for k in NEED if not cfg.get(k)]
    if missing:
        print("")
        print("[X] 缺配置：" + ", ".join(missing))
        print("    在 " + args.env + " 里补上这四行再跑一次。")
        return 3

    try:
        from obs import ObsClient  # type: ignore
    except ImportError:
        print("")
        print("[X] 缺依赖：pip install esdk-obs-python")
        return 2

    bucket = cfg["HUAWEI_OBS_BUCKET"]
    server = "https://obs." + region + ".myhuaweicloud.com"
    print("")
    print("2) 连接 " + server)
    print("   bucket = " + bucket)
    client = ObsClient(access_key_id=cfg["HUAWEI_AK"],
                       secret_access_key=cfg["HUAWEI_SK"], server=server)
    try:
        print("")
        print("3) 写入 " + KEY)
        resp = client.putContent(bucket, KEY, BODY.encode("utf-8"))
        if resp.status >= 300:
            print("   [X] put 失败 " + str(resp.status) + " " + str(getattr(resp, "reason", "")))
            print("       常见原因：桶名/区域不对、AK 无 OBS 权限、桶不是本账号的。")
            return 4
        print("   [OK] put " + str(resp.status))

        print("")
        print("4) 回读并比对")
        got = client.getObject(bucket, KEY)
        raw = got.body.buffer if hasattr(got.body, "buffer") else got.body
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        if got.status >= 300 or text != BODY:
            print("   [X] get 内容不一致 " + str(got.status))
            return 4
        print("   [OK] get " + str(got.status) + " 内容一致")

        if args.keep:
            print("")
            print("5) 保留对象（--keep），去控制台看 " + KEY)
        else:
            print("")
            print("5) 清理自检对象")
            client.deleteObject(bucket, KEY)
            print("   [OK] delete")
    finally:
        client.close()

    print("")
    print("OBS READY: obs://" + bucket + "/" + KEY + " @ " + region)
    print("把这行贴进 docs/cloud-resources.md 的 OBS 行当验收证据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
