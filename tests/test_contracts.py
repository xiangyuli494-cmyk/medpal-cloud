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


def test_frozen_v1_digest():
    """C1：契约冻结 —— 动 schema 必须同时升版本并改这里。"""
    import hashlib
    import json
    import pathlib

    path = (pathlib.Path(__file__).resolve().parents[1]
            / "packages/core/medpal_core/contracts/trace/schema.json")
    # 按 LF 规范化后计算：.gitattributes 是 * text=auto eol=lf，全新克隆的工作树本来就是 LF；
    # 只有历史 checkout 可能残留 CRLF（5934 字节），那时磁盘字节数 != git blob 字节数。
    # 所以断言只看规范化值，不看磁盘字节。
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    assert len(raw) == 5752
    assert hashlib.sha256(raw).hexdigest() == (
        "b778690b133ef5b1c25725a79988a2af2744b1b188298dbfde34b4ba8af4f53c"
    )

    schema = json.loads(raw.decode("utf-8"))
    assert set(schema["required"]) == {
        "schema", "trace_id", "question", "agent_version",
        "ontology_version", "steps", "gaps", "trace_completeness",
    }
    text = json.dumps(schema, ensure_ascii=False)
    for op in ("retrieve", "entity_extract", "std_align",
               "kg_query", "conflict_check", "conclude"):
        assert f'"{op}"' in text
