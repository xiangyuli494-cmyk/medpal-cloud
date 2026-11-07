"""向 PostgreSQL 灌入样例资产与本体三元组。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for path in (REPO / "packages" / "core", REPO / "apps" / "api"):
    sys.path.insert(0, str(path))


def _dsn() -> str:
    return (
        os.environ.get("MEDPAL_DB_DSN", "").strip()
        or os.environ.get("HUAWEI_GAUSSDB_DSN", "").strip()
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="向 PostgreSQL 灌入样例资产与 8 条三元组")
    parser.add_argument("--version", default="v1.0")
    args = parser.parse_args(argv)

    dsn = _dsn()
    if not dsn:
        print("缺少 MEDPAL_DB_DSN 或 HUAWEI_GAUSSDB_DSN", file=sys.stderr)
        return 2

    from app.seed import seed
    from medpal_core.ontology.version import current_version
    from medpal_core.providers.huawei import gaussdb
    from medpal_core.storage.db import backend_name

    conn = gaussdb.connect(dsn)
    gaussdb.prepare(conn)
    try:
        out = seed(version=args.version, conn=conn)
        if not out.get("ok"):
            print(out, file=sys.stderr)
            return 1
        current = current_version(conn) or {}
        print(f"backend={backend_name(conn)}")
        print(f"ontology_version={current.get('version', args.version)}")
        print(f"triple_count={current.get('triple_count', 0)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())