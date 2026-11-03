"""决策流水线：问题 -> 证据 -> 本体多跳 -> 结论 -> 决策链落盘。

这一段是「AI 创新应用」的可见部分，但它只调 core 的公开函数，不含任何 SQL。
换句话说：换检索后端、换模型、换数据库，这里都不用改。
"""

from __future__ import annotations

import time

from medpal_core.assets.entity import default_lexicon
from medpal_core.contracts.models import Step
from medpal_core.ontology import store
from medpal_core.retrieval import BM25Retriever
from medpal_core.trace import write_trace

AGENT_VERSION = "v1.0-cloud"
SYSTEM_PROMPT = (
    "你是医疗数据资产推理助手。只能基于给定证据作答，"
    "每条结论都要能指回 asset_id#anchor_id 或 triple_id；证据不足时直接说缺口。"
)


INTENT_HINTS = (("检查", "exam"), ("检验", "exam"), ("化验", "exam"),
                 ("药", "drug"), ("用药", "drug"), ("科室", "dept"), ("挂哪个科", "dept"))


def _best_path(paths, question: str) -> dict:
    """按问句意图挑首选路径：问检查就优先给带 exam 节点的路径，而不是分数最高的那条。"""
    if not paths:
        return {}
    want = None
    for kw, node_type in INTENT_HINTS:
        if kw in (question or ""):
            want = node_type
            break
    if want:
        for p in paths:
            if any(s["head_type"] == want or s["tail_type"] == want for s in p.get("steps") or []):
                return p
    return paths[0]


def _statement(path: dict) -> str:
    steps = path.get("steps") or []
    if not steps:
        return ""
    parts = [steps[0]["head_label"]]
    for s in steps:
        parts.append("-[{}]->".format(s["rel"]))
        parts.append(s["tail_label"])
    return " ".join(parts)


def _collect(paths, node_type):
    out = []
    for p in paths:
        for s in p.get("steps") or []:
            if s["head_type"] == node_type and s["head_label"] not in out:
                out.append(s["head_label"])
            if s["tail_type"] == node_type and s["tail_label"] not in out:
                out.append(s["tail_label"])
    return out


def answer(conn, question: str, top_k: int = 8, max_hops: int = 2,
           retriever=None, lexicon=None, llm=None) -> dict:
    """跑完整条链，返回结论 + 证据 + 决策链摘要。不抛业务异常，失败也返回 ok=False。"""
    t0 = time.perf_counter()
    question = (question or "").strip()
    if not question:
        return {"ok": False, "reason": "empty_question"}

    lex = lexicon or default_lexicon()
    retriever = retriever or BM25Retriever(conn)

    hits = retriever.search(question, top_k=top_k)
    entities = lex.extract([question])
    kg = store.kg_query(conn, entities or [question], max_hops=max_hops, limit=top_k)

    steps = []
    i = 1
    hit_refs = [h.anchor_id for h in hits if h.anchor_id]
    steps.append(Step(i=i, op="retrieve", inputs=[question],
                      out={"backend": getattr(retriever, "name", "unknown"), "hits": len(hits)},
                      evidence=hit_refs, ref="EVIDENCE").to_dict())

    i += 1
    steps.append(Step(i=i, op="entity_extract", inputs=[question], out=entities,
                      evidence=hit_refs[:1], confidence=0.9 if entities else 0.3,
                      ref="EVIDENCE").to_dict())

    i += 1
    steps.append(Step(i=i, op="std_align", inputs=entities, out=kg.get("resolved") or [],
                      evidence=hit_refs[:1], ref="EVIDENCE").to_dict())

    first = _best_path(kg.get("paths") or [], question)
    kg_refs = [s["triple_id"] for s in first.get("steps") or []]
    i += 1
    steps.append(Step(i=i, op="kg_query", inputs=entities,
                      out={"hops": first.get("hops", 0), "paths": len(kg.get("paths") or []),
                           "resolved": kg.get("resolved") or [],
                           "unresolved": kg.get("unresolved") or []},
                      evidence=kg_refs, confidence=first.get("score"),
                      ref="TRAVERSE").to_dict())

    # 第 5 步：冲突检查——全库一致性体检，不只看本次推理用到的边。
    # 「同一个 head + 同一个 rel 指向两个不同 tail」时不能闷头选一个，
    # 必须把矛盾摆到 gaps 里：医疗场景选错比拒答危险。
    # 用 triples=kg_refs 过滤会漏报（本次路径不含冲突边），所以不传。
    conflicts = store.find_conflicts(conn, limit=top_k)
    c_items = conflicts.get("conflicts") or []
    c_refs = [tid for c in c_items for tid in c["triple_ids"]]
    i += 1
    steps.append(Step(i=i, op="conflict_check", inputs=entities,
                      out={"groups": conflicts.get("groups", 0), "conflicts": len(c_items),
                           "detail": c_items},
                      evidence=c_refs, confidence=0.0 if c_items else 1.0,
                      ref="TRAVERSE").to_dict())

    statement = _statement(first)
    dept = _collect(kg.get("paths") or [], "dept")
    exams = _collect(kg.get("paths") or [], "exam")
    drugs = _collect(kg.get("paths") or [], "drug")
    conclusion = {
        "statement": statement or "证据不足，无法给出结论",
        "dept": dept[0] if dept else "",
        "exams": exams,
        "drugs": drugs,
        "evidence_count": len(set(hit_refs) | set(kg_refs)),
        "conflicts": [{"head": c["head_label"], "rel": c["rel"],
                       "tails": [x["tail_label"] for x in c["tails"]]} for c in c_items],
    }
    narrative = ""
    if llm is not None:
        user = "证据：" + str([h.to_dict() for h in hits][:5]) + "\n结论草稿：" + str(conclusion)
        try:
            narrative = llm.complete(SYSTEM_PROMPT, user)
        except Exception as exc:  # 模型不可用不该让整条链失败
            narrative = ""
            conclusion["llm_error"] = str(exc)[:200]
    if narrative:
        conclusion["narrative"] = narrative

    i += 1
    steps.append(Step(i=i, op="conclude", inputs=entities, out=conclusion,
                      evidence=(kg_refs or hit_refs)[:3], ref="CONCLUDE").to_dict())

    gaps = list(kg.get("unresolved") or [])
    if not kg.get("ok"):
        gaps.append("本体里没有可用的推理路径，建议补充三元组或换问法")
    for c in c_items:
        gaps.append("冲突：{} -[{}]-> 同时指向 {}（{}），需人工确认".format(
            c["head_label"], c["rel"],
            " / ".join(x["tail_label"] for x in c["tails"]),
            " ".join(c["triple_ids"]),
        ))

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    wired = write_trace(conn, question, steps, agent_version=AGENT_VERSION,
                        elapsed_ms=elapsed_ms, gaps=gaps)
    return {
        "ok": bool(kg.get("ok")) or bool(hits),
        "trace_id": wired["trace_id"],
        "ontology_version": wired["version"],
        "report_path": wired["report_path"],
        "trace_completeness": wired["trace_completeness"],
        "evidence_count": wired["evidence_count"],
        "unresolved": wired["unresolved"],
        "conclusion": conclusion,
        "entities": entities,
        "hits": [h.to_dict() for h in hits],
        "paths": kg.get("paths") or [],
        "elapsed_ms": elapsed_ms,
        "gaps": gaps,
    }
