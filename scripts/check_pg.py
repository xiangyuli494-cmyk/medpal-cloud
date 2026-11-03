"""PG 自检：连库 -> 建表 -> 写资产/三元组/版本 -> 读回 -> 清理。

不是单元测试，是「换连接串」这一步的验收入口：sqlite 与 PG 的方言差异
（? 与 %s、tuple 与 dict、INSERT OR REPLACE 与 ON CONFLICT）在这里一次性暴露。
退出码：0 通；2 缺驱动；3 缺配置；4 连不上；5 方言不兼容。

用法：
    python scripts/check_pg.py
    python scripts/check_pg.py --dsn "postgresql://root:pw@192.168.0.51:5432/postgres"
    python scripts/check_pg.py --keep
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from check_obs import load_env, mask  # noqa: E402

DSN_KEYS = ("MEDPAL_DB_DSN", "HUAWEI_GAUSSDB_DSN", "MEDPAL_GAUSSDB_DSN")
ASSET_ID = "AST-PGTEST-000001"
VERSION = "v-pgtest"


def pick_dsn(env, override):
    if override:
        return override
    for key in DSN_KEYS:
        val = os.environ.get(key) or env.get(key)
        if val:
            return val
    return ""


def describe(dsn):
    u = urlsplit(dsn)
    return {
        "host": u.hostname or "(空)",
        "port": u.port or 5432,
        "db": (u.path or "/postgres").lstrip("/") or "postgres",
        "user": unquote(u.username or ""),
        "has_pw": bool(u.password),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PG 连通与方言自检")
    ap.add_argument("--env", default=str(ROOT / ".env.local"))
    ap.add_argument("--dsn", default="")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    print(f"1) 配置 {args.env}")
    env = load_env(Path(args.env))
    dsn = pick_dsn(env, args.dsn)
    if not dsn:
        print("   [X] 缺连接串：设置 MEDPAL_DB_DSN（或 HUAWEI_GAUSSDB_DSN）")
        print("       形如 postgresql://用户名:密码@内网地址:5432/postgres")
        return 3
    info = describe(dsn)
    print("   host = {}   port = {}".format(info["host"], info["port"]))
    print("   db   = {}   user = {}".format(info["db"], mask(info["user"])))
    print("   password = {}".format("***" if info["has_pw"] else "(空)"))

    print("2) 驱动")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            print("   [X] 未装驱动：pip install \"psycopg[binary]\"")
            return 2
    print("   [OK] psycopg 可用")

    from medpal_core.ontology import store
    from medpal_core.ontology.version import snapshot
    from medpal_core.providers.huawei import gaussdb
    from medpal_core.storage.db import data_dir

    print("3) 连接")
    try:
        conn = gaussdb.connect(dsn)
        row = conn.execute("SELECT version() AS v").fetchone()
        ver = row["v"] if isinstance(row, dict) else row[0]
    except Exception as exc:
        print(f"   [X] 连不上：{exc}")
        return 4
    print(f"   [OK] {str(ver)[:70]}")

    try:
        print("4) 建表（SCHEMA 方言翻转）")
        gaussdb.prepare(conn)
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()
        names = sorted((r["table_name"] if isinstance(r, dict) else r[0]) for r in rows)
        print("   [OK] 表：{}".format(", ".join(names)))

        print("5) 写资产（UPSERT 两次，验 ON CONFLICT）")
        store.upsert_asset(conn, {"asset_id": ASSET_ID, "title": "PG 自检资产", "modality": "text"})
        store.upsert_asset(
            conn, {"asset_id": ASSET_ID, "title": "PG 自检资产 v2", "modality": "text"}
        )
        got = store.get_asset(conn, ASSET_ID)
        assert got and got["title"] == "PG 自检资产 v2", f"UPSERT 没覆盖：{got}"
        print("   [OK] 覆盖后 title = {}".format(got["title"]))

        print("6) 写三元组")
        tid = store.add_triple(
            conn,
            {
                "head": {"id": "S-PG1", "type": "symptom", "label": "自检症状"},
                "rel": "located_in",
                "tail": {"id": "D-PG1", "type": "department", "label": "自检科室"},
                "confidence": 0.9,
                "provenance": {"asset_id": ASSET_ID, "anchor_id": ASSET_ID + "#p1"},
            },
        )
        print("   [OK] triple_id = {}".format(tid or "(重复命中，已抬 confidence)"))

        print("7) 版本快照（第二个 UPSERT）")
        snap = snapshot(conn, VERSION, note="check_pg")
        print(
            "   [OK] {} triple_count={} hash={}".format(
                snap["version"], snap["triple_count"], snap["manifest_hash"]
            )
        )

        print("8) 读回")
        assets = store.list_assets(conn, limit=50)
        hit = [a for a in assets if a["asset_id"] == ASSET_ID]
        assert hit, "list_assets 读不到刚写的资产"
        print(f"   [OK] list_assets 命中，当前共 {len(assets)} 条")
    except Exception as exc:
        print(f"   [X] SQL 方言不兼容：{type(exc).__name__}: {exc}")
        print(f"       {traceback.format_exc().strip().splitlines()[-1]}")
        try:
            conn.close()
        except Exception:
            pass
        return 5

    if args.keep:
        print("9) 清理   跳过（--keep）")
        conn.close()
        print("\nPG READY: {}:{}/{}（保留测试数据）".format(info["host"], info["port"], info["db"]))
        return 0

    print("9) 清理测试数据")
    try:
        conn.execute("DELETE FROM triple WHERE asset_id = ?", (ASSET_ID,))
        conn.execute("DELETE FROM asset WHERE asset_id = ?", (ASSET_ID,))
        conn.execute("DELETE FROM version WHERE version = ?", (VERSION,))
        conn.commit()
    except Exception as exc:
        print(f"   [X] 清理失败：{exc}（手动删 {ASSET_ID}）")
        conn.close()
        return 5
    snap_file = data_dir() / ("ontology_" + VERSION + ".jsonl")
    if snap_file.is_file():
        snap_file.unlink()
    conn.close()
    print("   [OK] 已删 {} / {} / {} 与快照文件".format(ASSET_ID, "v-pgtest 三元组", VERSION))
    print("\nPG READY: {}:{}/{}".format(info["host"], info["port"], info["db"]))
    print("把这行贴进 docs/cloud-resources.md 的 RDS 行当验收证据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
