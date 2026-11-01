"""检索器接口。

为什么先定接口再写实现：赛题1 要证明「底座可复用」，那么换检索后端（BM25 -> KooSearch）
时上层 pipeline 一行不改，这件事只能靠 Protocol 说清楚。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Hit:
    asset_id: str
    anchor_id: str
    text: str
    score: float

    def to_dict(self) -> dict:
        return {"asset_id": self.asset_id, "anchor_id": self.anchor_id,
                "text": self.text, "score": round(self.score, 4)}


class Retriever(Protocol):
    name: str

    def search(self, query: str, top_k: int = 8) -> list: ...


def build_retriever(conn, kind: str = "bm25") -> Retriever:
    if kind == "bm25":
        from .bm25 import BM25Retriever

        return BM25Retriever(conn)
    if kind == "koosearch":
        from ..providers.huawei.koosearch import KooSearchRetriever

        return KooSearchRetriever()
    raise ValueError("未知检索后端: " + kind)
