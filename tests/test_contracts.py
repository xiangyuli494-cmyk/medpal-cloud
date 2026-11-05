"""协议层：schema 与语义双检，写错字段名/引用必须当场报错。"""

from __future__ import annotations

import pytest

from medpal_core.contracts import Step, build_trace, new_trace_id, validate
from medpal_core.contracts.trace.validator import REF_BY_OP


def _good():
    return {
        "schema": "medpal-trace/1",
        "trace_id": new_trace_id(),
        "question": "上腹隐痛做什么检查",
        "agent_version": "v1.0",
        "ontology_version": "v1.0",
        "steps": [{"i": 1, "op": "retrieve", "out": {"hits": 1},
                   "evidence": ["AST-2026-aaaaaa#s1.p1.c1"], "ref": "EVIDENCE"}],
        "gaps": [],
        "trace_completeness": 1.0,
    }


def test_valid_trace_passes():
    assert validate(_good()) == []


def test_evidence_as_string_is_rejected():
    t = _good()
    t["steps"][0]["evidence"] = "T-0f5bfa1d"
    errs = validate(t)
    assert any("逐字符遍历" in e for e in errs)


def test_ref_must_match_op():
    t = _good()
    t["steps"][0]["ref"] = "CONCLUDE"
    assert any("ref" in e for e in validate(t))


def test_steps_must_increase():
    t = _good()
    t["steps"].append({"i": 1, "op": "conclude", "out": {}, "evidence": []})
    assert any("递增" in e or "重复" in e for e in validate(t))


def test_step_dataclass_maps_inputs_to_in():
    d = Step(i=1, op="kg_query", out={}, inputs=["上腹隐痛"], evidence=[], confidence=0.9).to_dict()
    assert d["in"] == ["上腹隐痛"]
    assert "confidence" in d


def test_unknown_op_raises():
    with pytest.raises(ValueError):
        Step(i=1, op="magic")


def test_build_trace_shape():
    t = build_trace("q", [Step(i=1, op="conclude", out={})], "v1.0", "v1.0")
    assert t["schema"] == "medpal-trace/1"
    assert set(REF_BY_OP) >= {s["op"] for s in t["steps"]}
