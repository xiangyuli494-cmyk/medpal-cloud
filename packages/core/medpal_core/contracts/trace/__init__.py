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


def new_trace_id() -> str:
    """TR-YYYYMMDD-XXXX，后四位大写十六进制，与 schema 的正则一致。"""
    return "TR-" + datetime.now(CST).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()


def validate(trace: dict) -> list[str]:
    """返回错误列表，空列表表示合格。不抛异常，调用方自己决定是否中断。"""
    from .validator import validate as _validate

    return _validate(trace, load_schema())
