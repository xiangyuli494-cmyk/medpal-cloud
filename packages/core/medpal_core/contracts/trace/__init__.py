"""trace 契约：schema 文件 + 校验器 + id 生成。

schema 是可执行的事实来源（schema.json），文档说了不算，机器验过才算。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from ...storage.db import CST

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def new_trace_id(conn=None) -> str:
    """TR-YYYYMMDD-XXXX，后四位大写十六进制，与 schema 的正则一致。

    后四位只有 65536 种取值：同一天写满 300 条，撞号概率已过半（生日问题）。
    CI 上实测真撞过（sqlite3.IntegrityError: UNIQUE constraint failed: trace.trace_id），
    所以传了 conn 就先查表、撞了换一个 —— 格式不变，schema 正则不动。
    """
    day = datetime.now(CST).strftime("%Y%m%d")
    for _ in range(16):
        tid = "TR-" + day + "-" + uuid.uuid4().hex[:4].upper()
        if conn is None:
            return tid
        row = conn.execute("SELECT 1 FROM trace WHERE trace_id = ?", (tid,)).fetchone()
        if row is None:
            return tid
    raise RuntimeError("当天 trace_id 空间耗尽：" + day)


def validate(trace: dict) -> list[str]:
    """返回错误列表，空列表表示合格。不抛异常，调用方自己决定是否中断。"""
    from .validator import validate as _validate

    return _validate(trace, load_schema())
