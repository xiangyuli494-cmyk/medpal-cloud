"""MedPal Core —— 赛题1 应用的底座。

三层：协议层（contracts） / 知识层（assets + ontology + retrieval） / 决策链（trace）。
依赖方向固定：apps/* -> medpal_core -> 标准库或厂商 SDK（仅 providers/ 下）。
medpal_core 反向 import apps 视为违规，由 tools/check_boundaries.py 在 CI 拦截。
"""

__version__ = "0.1.0"
