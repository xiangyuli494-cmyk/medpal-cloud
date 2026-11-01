"""零依赖 BM25：中文按字符 bigram 切，英文数字按词切。

够用来做「证据召回 + 引用锚点」，不需要 jieba，也不需要向量库；
上云后同一接口换 KooSearch，评测口径不变。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter

from .base import Hit

_ASCII = re.compile(r"[a-zA-Z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list:
    text = (text or "").lower()
    toks = _ASCII.findall(text)
    chars = _CJK.findall(text)
    toks.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    toks.extend(chars)
    return toks


class BM25Retriever:
    name = "bm25"

    def __init__(self, conn, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = []  # [(asset_id, anchor_id, text, Counter)]
        for row in conn.execute("SELECT asset_id, title, anchors_json FROM asset"):
            anchors = json.loads(row["anchors_json"] or "[]")
            for a in anchors:
                text = (a.get("text") or "") or row["title"]
                self.docs.append((row["asset_id"], a.get("anchor_id", ""), text,
                                  Counter(tokenize(text + " " + (row["title"] or "")))))
        self.n = len(self.docs)
        self.avgdl = (sum(sum(c.values()) for _, _, _, c in self.docs) / self.n) if self.n else 0.0
        df = Counter()
        for _, _, _, c in self.docs:
            df.update(set(c))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, top_k: int = 8) -> list:
        q = tokenize(query)
        if not q or not self.docs:
            return []
        scored = []
        for asset_id, anchor_id, text, counts in self.docs:
            dl = sum(counts.values()) or 1
            s = 0.0
            for t in q:
                f = counts.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if s > 0:
                scored.append(Hit(asset_id, anchor_id, text, s))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]
