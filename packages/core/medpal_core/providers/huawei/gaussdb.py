"""GaussDB：与 storage.db 同一套 SQL，只是换连接串与驱动。

schema 完全一致（asset / triple / trace 三张表 + 两个索引），所以本地演示与云上运行
用的是同一段 SQL，不存在「演示一套、上线一套」。
"""

from __future__ import annotations

from .config import ProviderNotConfigured, load_config


def connect(dsn: str = "", cfg=None):
    cfg = cfg or load_config()
    dsn = dsn or cfg.gaussdb_dsn
    if not dsn:
        raise ProviderNotConfigured("缺少 HUAWEI_GAUSSDB_DSN")
    try:
        import psycopg  # type: ignore
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError as exc:
            raise ProviderNotConfigured("未安装驱动：pip install psycopg[binary]") from exc
    conn = psycopg.connect(dsn)
    conn.autocommit = True
    return conn


def prepare(conn) -> None:
    """把 storage.db.SCHEMA 的 sqlite 方言翻成 GaussDB 方言后建表。"""
    from ...storage.db import SCHEMA

    sql = (SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                .replace("AUTOINCREMENT", "")
                .replace("?", "%s"))
    with conn.cursor() as cur:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
