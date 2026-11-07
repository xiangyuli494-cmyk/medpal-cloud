"""一键灌数据：解析样本 -> 建三元组 -> 打本体快照。

用法（仓库根目录）：
    python -m app.seed --app-dir apps/api      # 也可 make seed
灌完 /health 会显示资产数与本体版本，随后就能 /v1/ask 提问。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from medpal_core.assets.card import ingest_file
from medpal_core.assets.entity import default_lexicon
from medpal_core.ontology import store
from medpal_core.ontology import version as onto_version
from medpal_core.storage import connect

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "data" / "samples"
SEED = REPO / "data" / "ontology" / "seed.jsonl"


def _pick_anchor(anchors, term: str):
    for a in anchors:
        if term and term in (a.get("text") or ""):
            return a
    return anchors[0] if anchors else None


def seed(sample: Path = SAMPLES / "peptic_ulcer_pathway.md", seed_file: Path = SEED,
         version: str = "v1.0", conn=None) -> dict:
    owns_conn = conn is None
    if owns_conn:
        conn = connect()
    try:
        card = ingest_file(conn, sample, title="消化性溃疡临床路径（合成样本）",
                           source_type="public_standard", ingested_by="seed",
                           lexicon=default_lexicon())
        if not card.get("ok"):
            return {"ok": False, "step": "ingest", "detail": card}
        anchors = card["anchors"]
        added, dedup = [], []
        for line in seed_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            anchor = _pick_anchor(anchors, t.pop("anchor_term", ""))
            t["provenance"] = {"asset_id": card["asset_id"],
                               "anchor_id": anchor["anchor_id"] if anchor else ""}
            tid = store.add_triple(conn, t, version="v0.9")
            (added if tid else dedup).append(tid or t["head"]["label"] + "-" + t["rel"])
        snap = onto_version.snapshot(conn, version, note="seed: 合成样本 + 8 条演示三元组")
        return {"ok": True, "asset_id": card["asset_id"], "anchors": len(anchors),
                "entities": card["entity_hint"], "triples_added": len(added),
                "triples_dedup": len(dedup), "snapshot": snap}
    finally:
        if owns_conn:
            conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="灌入演示数据并打本体快照")
    ap.add_argument("--sample", default=str(SAMPLES / "peptic_ulcer_pathway.md"))
    ap.add_argument("--seed-file", default=str(SEED))
    ap.add_argument("--version", default="v1.0")
    args = ap.parse_args(argv)
    out = seed(Path(args.sample), Path(args.seed_file), args.version)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
