"""协议层的数据形状。

这里只放「跨层传输的契约」，不放业务逻辑。
step 的字段名与 trace.schema.json 一一对应：i / op / in / out / evidence / confidence / ref。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OPS = (
    "parse",
    "ingest",
    "entity_extract",
    "std_align",
    "retrieve",
    "kg_query",
    "conflict_check",
    "conclude",
    "skill_export",
)


@dataclass
class Step:
    """决策链的一步。in 是 Python 保留字，落盘时映射成 "in"。"""

    i: int
    op: str
    out: Any = None
    inputs: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: float | None = None
    ref: str = ""

    def __post_init__(self) -> None:
        if self.op not in OPS:
            raise ValueError("未知 op: " + str(self.op))

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"i": int(self.i), "op": self.op, "out": self.out}
        if self.inputs:
            d["in"] = [str(x) for x in self.inputs]
        d["evidence"] = [str(x) for x in self.evidence]
        if self.confidence is not None:
            d["confidence"] = float(self.confidence)
        if self.ref:
            d["ref"] = self.ref
        return d


def build_trace(question: str, steps: list[Step], agent_version: str, ontology_version: str,
                elapsed_ms: int = 0, gaps: list[str] | None = None) -> dict:
    """组装 trace dict。存储层（store/writer）与校验器都吃这个形状。"""
    return {
        "schema": "medpal-trace/1",
        "question": question,
        "agent_version": agent_version,
        "ontology_version": ontology_version,
        "elapsed_ms": int(elapsed_ms),
        "steps": [s.to_dict() for s in steps],
        "gaps": list(gaps or []),
    }
