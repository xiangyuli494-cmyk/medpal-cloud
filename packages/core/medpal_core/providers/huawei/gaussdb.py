"""GaussDB：同一套业务 SQL，换连接串 + 两个方言差异（占位符、行工厂）。

差异只有两处，都在这层抹平：
- sqlite 用 ? 占位，psycopg 用 %s -> wrap() 的游标在执行前改写；
- sqlite3.Row 支持按列名取，psycopg 默认给 tuple -> connect() 设 dict_row。

业务代码（store.py / trace/writer.py）一行不改，这才是「换连接串」的意思。
"""

from __future__ import annotations

from .config import ProviderNotConfigured, load_config

BACKEND = "gaussdb"


def _driver():
    try:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg, dict_row
    except ImportError:
        try:
            import psycopg2

            return psycopg2, None
        except ImportError as exc:
            raise ProviderNotConfigured("未安装驱动：pip install psycopg[binary]") from exc


def _sql(sql: str) -> str:
    """把 sqlite 风格的 ? 占位改成 psycopg 的 %s。"""
    return sql.replace("?", "%s")


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(_sql(sql), params)
        return self

    def executemany(self, sql, seq):
        self._cur.executemany(_sql(sql), seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class GaussConn:
    """psycopg 连接的最小适配层：对外接口与 sqlite3.Connection 一致。"""

    backend = BACKEND

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return _Cursor(self._conn.cursor()).execute(sql, params)

    def executemany(self, sql, seq):
        return _Cursor(self._conn.cursor()).executemany(sql, seq)

    def executescript(self, script: str) -> None:
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            self.execute(stmt)

    def cursor(self):
        return _Cursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __getattr__(self, item):
        return getattr(self._conn, item)


def wrap(conn):
    return conn if isinstance(conn, GaussConn) else GaussConn(conn)


def connect(dsn: str = "", cfg=None):
    cfg = cfg or load_config()
    dsn = dsn or cfg.gaussdb_dsn
    if not dsn:
        # MEDPAL_DB_DSN 是通用名；HUAWEI_GAUSSDB_DSN 是历史名，两个都认。
        import os

        dsn = os.environ.get("MEDPAL_DB_DSN", "")
    if not dsn:
        raise ProviderNotConfigured("缺少 MEDPAL_DB_DSN（或 HUAWEI_GAUSSDB_DSN）")
    psycopg, dict_row = _driver()
    conn = psycopg.connect(dsn)
    conn.autocommit = True
    if dict_row is not None:
        conn.row_factory = dict_row
    return wrap(conn)


def prepare(conn) -> None:
    """把 storage.db.SCHEMA 的 sqlite 方言翻成 GaussDB 方言后建表。"""
    from ...storage.db import SCHEMA

    sql = (SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                .replace("AUTOINCREMENT", "")
                .replace("?", "%s"))
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        conn.execute(stmt)
