"""资产卡：把一次解析结果登记成可被引用的资产（asset_id + anchors）。"""

from __future__ import annotations

from pathlib import Path

from ..ontology import store as ontology_store
from ..storage.db import now
from . import parsers
from .entity import Lexicon, default_lexicon


def ingest_file(
    conn,
    path: str | Path,
    modality: str = "",
    title: str = "",
    source_type: str = "public_standard",
    ingested_by: str = "",
    lexicon: Lexicon | None = None,
) -> dict:
    """解析一份文件 -> Asset Card -> 入库。返回 {ok, asset_id, anchors, entities, blocks}。

    anchors 的 anchor_id 初始是「文件名#位置」，入账后统一改写成「asset_id#位置」，
    这样证据引用换机器、换库都还指得回同一段原文。
    """
    p = Path(path)
    if not p.exists():
        return {"ok": False, "reason": "file_not_found", "hint": "检查路径：" + str(path)}
    doc = parsers.parse(p)
    if doc is None:
        return {"ok": False, "reason": "no_parser",
                "hint": "该扩展名暂无解析器，请在 parsers.REGISTRY 注册", "suffix": p.suffix}
    if doc.metadata.get("error"):
        return {"ok": False, "reason": "parser_unavailable",
                "hint": doc.metadata["error"], "path": str(p)}

    lex = lexicon or default_lexicon()
    entities = lex.extract([b.text for b in doc.blocks])
    card = {
        "title": title or doc.title,
        "modality": modality or doc.modality,
        "source": {"type": source_type, "publisher": "", "path": str(p)},
        "version": {"value": "v1", "captured_at": now(), "supersedes": None},
        "sensitivity": "public" if source_type == "public_standard" else "synthetic",
        "structure": {
            "blocks": len(doc.blocks),
            "anchors": len(doc.anchors),
            "kinds": sorted({b.kind for b in doc.blocks}),
        },
        "anchors": doc.anchors,
        "entities": entities,
        "kb_status": "ready",
        "ingested_by": ingested_by,
    }
    asset_id = ontology_store.upsert_asset(conn, card)
    for a in card["anchors"]:
        a["anchor_id"] = a["anchor_id"].replace(p.stem, asset_id)
    card["asset_id"] = asset_id
    ontology_store.upsert_asset(conn, card)
    return {
        "ok": True,
        "asset_id": asset_id,
        "modality": card["modality"],
        "anchors": card["anchors"],
        "entity_hint": entities,
        "blocks": len(doc.blocks),
    }
