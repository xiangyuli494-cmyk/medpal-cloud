"""FastAPI 依赖：一条请求一个 SQLite 连接，退出时关掉。"""

from __future__ import annotations

from medpal_core.config import settings
from medpal_core.storage import connect


def get_conn():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def get_settings():
    return settings()
