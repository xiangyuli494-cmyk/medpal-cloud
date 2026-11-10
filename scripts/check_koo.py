#!/usr/bin/env python3
"""check_koo.py — KooSearch 云端检索自检（C5 交付物）。

四步：环境变量 -> provider 就绪 -> 真发一次检索 -> 命中结构合规。
和 check_pg.py / check_obs.py 同风格：全绿打印 KOO READY 退出 0，失败退出 1。

用法（仓库根目录）：
    PYTHONPATH=packages/core:apps/api HUAWEI_KOOSEARCH_ENDPOINT=https://... \
      python scripts/check_koo.py
    python scripts/check_koo.py --strict     # 没配也判失败（答辩前用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

QUERY = "消化性溃疡 上腹痛 该做什么检查"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KooSearch 检索自检")
    ap.add_argument("--strict", action="store_true", help="未配置也判失败")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args(argv)

    from medpal_core.providers.huawei.config import load_config
    from medpal_core.providers.huawei.koosearch import KooSearchRetriever

    cfg = load_config()
    ready = cfg.readiness()
    print("endpoint =", cfg.koosearch_endpoint or "(空)")
    print("region   =", cfg.region)

    if not ready["koosearch"]:
        msg = "SKIP  HUAWEI_KOOSEARCH_ENDPOINT 未配置"
        if args.strict:
            print("FAIL  " + msg + "，--strict 下按失败处理")
            return 1
        print(msg)
        return 0

    r = KooSearchRetriever(cfg)
    if not r.available():
        print("FAIL  provider 说未就绪，但环境变量看似齐全 —— 检查 load_config 的判定")
        return 1
    print("STEP1 [OK] provider 就绪")

    try:
        hits = r.search(QUERY, top_k=args.top_k)
    except Exception as exc:
        print("FAIL  检索调用失败:", type(exc).__name__, str(exc)[:300])
        return 1
    print(f"STEP2 [OK] 检索返回 {len(hits)} 条")

    if not hits:
        print("WARN  0 命中：端点通但索引里没有这批文档（先灌 data/ 下的样例再验）")
        print("KOO READY (0 hits)")
        return 0

    bad = []
    for i, h in enumerate(hits):
        if not getattr(h, "text", ""):
            bad.append((i, "text 为空"))
        if not getattr(h, "anchor_id", ""):
            bad.append((i, "anchor_id 为空（溯源会断）"))
    if bad:
        print("FAIL  命中结构不合规:", json.dumps(bad, ensure_ascii=False))
        return 1
    print("STEP3 [OK] 命中结构合规（anchor_id 可用于溯源）")
    print("sample =", json.dumps({"asset_id": hits[0].asset_id,
                                  "anchor_id": hits[0].anchor_id,
                                  "score": hits[0].score,
                                  "text": (hits[0].text or "")[:60]},
                                 ensure_ascii=False))
    print("KOO READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
