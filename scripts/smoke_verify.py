"""verify.sh 的端到端冒烟：健康 → 资产 → 提问 → trace 回读 → 契约校验 → 云就绪度。

只回答两件事：链路通不通、trace 合不合法。阈值判断留在 scripts/verify.sh。
任何一项不符预期就打印原因并退出 1。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("MEDPAL_LLM", "offline")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from medpal_core.contracts.trace import load_schema  # noqa: E402
from medpal_core.contracts.trace.validator import validate  # noqa: E402

QUESTION = "上腹隐痛伴反酸，下一步做什么检查？"
FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL {name} {detail}")


def main() -> int:
    c = TestClient(app)

    schema = load_schema()
    check("schema 可加载", bool(schema.get("properties")))

    h = c.get("/health")
    check("/health 200", h.status_code == 200, h.text[:200])

    a = c.get("/v1/assets")
    check("/v1/assets 200", a.status_code == 200, a.text[:200])

    ask = c.post("/v1/ask", json={"question": QUESTION, "top_k": 8, "max_hops": 2})
    body = ask.json() if ask.status_code == 200 else {}
    check("/v1/ask 200", ask.status_code == 200, ask.text[:200])
    tid = str(body.get("trace_id", ""))
    check("有 trace_id", tid.startswith("TR-"), tid)
    conclusion = body.get("conclusion") or {}
    check("结论里有科室", bool(conclusion.get("dept")), str(conclusion)[:160])
    check("至少一条推理路径", len(body.get("paths") or []) >= 1)

    tr = c.get("/v1/traces/" + (tid or "TR-19700101-0000"))
    trace = tr.json() if tr.status_code == 200 else {}
    check("/v1/traces 200", tr.status_code == 200, tr.text[:200])
    errs = validate(trace, schema)
    check("trace 过 schema + 语义校验", not errs, "; ".join(errs[:3]))
    steps = trace.get("steps") or []
    check("步骤 >= 5", len(steps) >= 5, str(len(steps)))
    check(
        "trace 自带完整率",
        isinstance(trace.get("trace_completeness"), (int, float)),
        str(trace.get("trace_completeness")),
    )
    check("trace 自带拒答标记", isinstance(trace.get("refusal"), bool))

    cloud = c.get("/v1/cloud")
    cb = cloud.json() if cloud.status_code == 200 else {}
    check("/v1/cloud 200", cloud.status_code == 200, cloud.text[:200])
    ready = cb.get("ready") or {}
    check("cloud 报四项就绪度", {"obs", "gaussdb", "modelarts", "koosearch"} <= set(ready))

    if FAILS:
        print(f"smoke: {len(FAILS)} 项失败")
        return 1
    print("smoke: 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
