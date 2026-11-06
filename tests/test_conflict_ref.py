"""conflict_check 的 ref 必须与 trace 契约映射一致。"""

from medpal_core.contracts import validate


def _trace(ref: str) -> dict:
    return {
        "schema": "medpal-trace/1",
        "trace_id": "TR-20261106-0001",
        "question": "上腹隐痛伴反酸，下一步做什么检查？",
        "agent_version": "v1.0",
        "ontology_version": "v1.0",
        "steps": [
            {
                "i": 1,
                "op": "conflict_check",
                "in": [],
                "out": {"groups": 0, "conflicts": 0},
                "evidence": ["T-0f5bfa1d"],
                "confidence": 1.0,
                "ref": ref,
            }
        ],
        "gaps": [],
        "trace_completeness": 1.0,
    }


def test_conflict_check_ref_returns_no_contract_mismatch():
    errs = validate(_trace("TRAVERSE"))
    assert any("应为 ref='EVIDENCE'" in e for e in errs)

    errs = validate(_trace("EVIDENCE"))
    assert not any("应为 ref='EVIDENCE'" in e for e in errs)
    assert errs == []