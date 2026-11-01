"""检索层：证据召回。默认给一个零依赖的 BM25 实现，云端换 KooSearch 只换实现。"""

from .base import Hit, Retriever, build_retriever
from .bm25 import BM25Retriever

__all__ = ["Hit", "Retriever", "build_retriever", "BM25Retriever"]
