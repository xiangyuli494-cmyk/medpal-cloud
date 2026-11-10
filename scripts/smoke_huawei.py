#!/usr/bin/env python3
"""smoke_huawei.py — CI 里验华为云真机：GaussDB + OBS 两项（B4 交付物）。

无凭据时打印 SKIP 并退出 0（不把 CI 变红）；有凭据时两项都过才退出 0。
workflow 侧用 check-secrets job + huawei job 的 if 控制是否真的跑，本脚本的
SKIP 是兜底：即便被手动触发、缺变量也不会误报红。

用法：
    python scripts/smoke_huawei.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "core"))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))

# 并发 run（pull_request 与 push 各一次）会同时写同一个 key，拼上 run id 隔离
KEY = f"_selftest/smoke-{os.environ.get('GITHUB_RUN_ID', 'local')}.txt"
PAYLOAD = b"medpal smoke huawei\n"


def _env(name: str, *alts: str) -> str:
    for n in (name, *alts):
        v = os.environ.get(n)
        if v:
            return v
    return ""


def _gaussdb(dsn: str) -> str:
    from medpal_core.providers.huawei import gaussdb

    conn = gaussdb.connect(dsn)
    try:
        row = conn.execute("SELECT version()").fetchone()
        ver = row["version"] if row else "connected"
        try:
            cnt = conn.execute("SELECT count(*) AS n FROM triple").fetchone()["n"]
            return f"{ver}  triple={cnt}"
        except Exception as exc:
            # 只放过「表还没建」；权限、认证、方言错照抛，别被这行吞掉
            if type(exc).__name__ != "UndefinedTable":
                raise
            return f"{ver}  triple=(表未建)"
    finally:
        conn.close()


def _obs() -> str:
    from medpal_core.providers.huawei.config import load_config
    from medpal_core.providers.huawei.obs import OBSStore

    cfg = load_config()
    store = OBSStore(cfg)
    store.ensure_bucket()

    fd, tmp = tempfile.mkstemp(prefix="smoke_obs_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(PAYLOAD)
        store.put(tmp, KEY)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    got = store.get(KEY)
    want = hashlib.sha256(PAYLOAD).hexdigest()
    have = hashlib.sha256(got).hexdigest()
    store.delete(KEY)
    if want != have:
        raise RuntimeError(f"OBS sha256 不一致 want={want[:16]} got={have[:16]}")
    return f"sha256={have[:16]}…"


def main() -> int:
    dsn = _env("MEDPAL_DB_DSN", "HUAWEI_GAUSSDB_DSN")
    ak = _env("HUAWEI_AK")
    sk = _env("HUAWEI_SK")
    bucket = _env("HUAWEI_OBS_BUCKET")

    missing = [n for n, v in (("MEDPAL_DB_DSN", dsn), ("HUAWEI_AK", ak),
                              ("HUAWEI_SK", sk), ("HUAWEI_OBS_BUCKET", bucket)) if not v]
    if missing:
        print(f"SKIP: 缺 {' / '.join(missing)}，跳过真机 smoke")
        return 0

    print("== smoke_huawei.py")
    try:
        print(f"gaussdb  [OK] {_gaussdb(dsn)}")
    except Exception as exc:
        print(f"gaussdb  [FAIL] {exc}")
        return 1
    try:
        print(f"obs      [OK] {_obs()}")
    except Exception as exc:
        print(f"obs      [FAIL] {exc}")
        return 1

    print("\nHUAWEI SMOKE READY: gaussdb + obs 均通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
