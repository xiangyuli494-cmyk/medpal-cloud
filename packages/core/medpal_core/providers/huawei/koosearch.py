"""KooSearch：云端检索。接口与 retrieval.base.Retriever 一致。"""

from __future__ import annotations

import httpx

from .config import ProviderNotConfigured, load_config


class KooSearchRetriever:
    name = "koosearch"

    def __init__(self, cfg=None, top_k: int = 8):
        self.cfg = cfg or load_config()
        self.top_k = top_k

    def available(self) -> bool:
        return self.cfg.readiness()["koosearch"]

    def search(self, query: str, top_k: int = 8) -> list:
        from ...retrieval.base import Hit

        if not self.available():
            raise ProviderNotConfigured("缺少 HUAWEI_KOOSEARCH_ENDPOINT")
        r = httpx.post(self.cfg.koosearch_endpoint, json={"query": query,
                                                          "top_k": top_k or self.top_k},
                       timeout=20.0)
        r.raise_for_status()
        out = []
        for i, item in enumerate(r.json().get("hits") or []):
            out.append(Hit(item.get("asset_id", ""), item.get("anchor_id", ""),
                           item.get("text", ""), float(item.get("score", 0.0)) or (top_k - i)))
        return out
