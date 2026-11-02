"""存储基座：连接、schema、时间与数据目录。

只管「库在哪、表长什么样」，不含任何业务函数。
所有路径都能用环境变量覆盖（容器 / FunctionGraph 里改环境变量，不改代码）。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

SCHEMA = """
CREATE TABLE IF NOT EXISTS asset (
    asset_id       TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    modality       TEXT NOT NULL,
    source_json    TEXT,
    version_json   TEXT,
    sensitivity    TEXT DEFAULT 'public',
    structure_json TEXT,
    anchors_json   TEXT,
    entities_json  TEXT,
    kb_status      TEXT DEFAULT 'pending',
    ingested_by    TEXT,
    created_at     TEXT
);
CREATE TABLE IF NOT EXISTS triple (
    triple_id       TEXT PRIMARY KEY,
    head_id         TEXT NOT NULL,
    head_type       TEXT NOT NULL,
    head_label      TEXT NOT NULL,
    rel             TEXT NOT NULL,
    tail_id         TEXT NOT NULL,
    tail_type       TEXT NOT NULL,
    tail_label      TEXT NOT NULL,
    confidence      REAL DEFAULT 0.8,
    asset_id        TEXT,
    anchor_id       TEXT,
    standard_json   TEXT,
    status          TEXT DEFAULT 'active',
    version_added   TEXT,
    version_removed TEXT
);
CREATE INDEX IF NOT EXISTS idx_triple_head ON triple(head_id, status);
CREATE INDEX IF NOT EXISTS idx_triple_tail ON triple(tail_id, status);
CREATE TABLE IF NOT EXISTS version (
    version       TEXT PRIMARY KEY,
    created_at    TEXT,
    triple_count  INTEGER,
    manifest_hash TEXT,
    note          TEXT,
    is_current    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trace (
    trace_id         TEXT PRIMARY KEY,
    question         TEXT,
    agent_version    TEXT,
    ontology_version TEXT,
    steps_json       TEXT,
    gaps_json        TEXT,
    elapsed_ms       INTEGER,
    created_at       TEXT,
    sources_json     TEXT,
    conclusion_json  TEXT,
    completeness     REAL,
    refusal          INTEGER DEFAULT 0,
    unresolved_json  TEXT
);
CREATE TABLE IF NOT EXISTS alias (
    surface     TEXT PRIMARY KEY,
    code        TEXT,
    scheme      TEXT,
    entity_type TEXT,
    confidence  REAL DEFAULT 0.9
);
CREATE TABLE IF NOT EXISTS pending_diff (
    diff_id    TEXT PRIMARY KEY,
    status     TEXT DEFAULT 'pending',
    payload    TEXT,
    created_at TEXT
);
"""

def data_dir() -> Path:
    """原件快照、报告、sqlite 库的根目录。默认 <cwd>/data，可用 MEDPAL_DATA_DIR 覆盖。"""
    return Path(os.environ.get("MEDPAL_DATA_DIR") or (Path.cwd() / "data")).resolve()


def db_file() -> Path:
    """默认 <data>/medpal.db，可用 MEDPAL_DB 直接指向一个文件（测试用 tmp_path）。"""
    override = os.environ.get("MEDPAL_DB")
    return Path(override).resolve() if override else data_dir() / "medpal.db"


def report_dir() -> Path:
    """决策链报告落盘目录，可用 MEDPAL_REPORT_DIR 覆盖。"""
    override = os.environ.get("MEDPAL_REPORT_DIR")
    return Path(override).resolve() if override else data_dir() / "reports"


def now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")

# 老库补列：CREATE TABLE IF NOT EXISTS 不会给已存在的表加字段，
# 而 /v1/traces/{id} 要能直接当 schema 合法对象返回，缺列就没法回读完整率。
_TRACE_EXTRA_COLUMNS = {
    "sources_json": "TEXT",
    "conclusion_json": "TEXT",
    "completeness": "REAL",
    "refusal": "INTEGER DEFAULT 0",
    "unresolved_json": "TEXT",
}


def _migrate(conn) -> None:
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(trace)").fetchall()}
    except Exception:  # 非 sqlite 后端（gaussdb）不走这条补列路径
        return
    if not have:
        return
    added = [c for c in _TRACE_EXTRA_COLUMNS if c not in have]
    for col in added:
        conn.execute(f"ALTER TABLE trace ADD COLUMN {col} {_TRACE_EXTRA_COLUMNS[col]}")
    if added:
        conn.commit()


def connect(target=None):
    path = Path(target) if target else db_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def backend_name(conn) -> str:
    """连接的真实后端名（sqlite / gaussdb）。/health 用这个，不再写字面量。"""
    name = getattr(conn, "backend", "")
    if name:
        return name
    return {"sqlite3": "sqlite", "psycopg": "gaussdb", "psycopg2": "gaussdb"}.get(
        type(conn).__module__.split(".")[0], "unknown"
    )
