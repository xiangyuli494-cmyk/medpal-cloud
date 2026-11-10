#!/usr/bin/env python3
"""loadtest.py — 压测脚本（B9 交付物）。

并发打 /v1/ask（顺带回读 /v1/traces/{id}），输出 QPS、P50/P95/P99、错误率。

用法：
    python scripts/loadtest.py                        # 默认 8 并发 40 次，打 127.0.0.1:8000
    python scripts/loadtest.py -c 16 -n 200 --p95-ms 800 --json docs/cloud-evidence/load.json

判定：错误率必须为 0，P95 不超过 --p95-ms（默认 1200ms），否则退出码 1。
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

QUESTIONS = [
    "上腹隐痛伴反酸，下一步该做什么检查？",
    "胃溃疡该挂哪个科？",
    "幽门螺杆菌阳性用什么药？",
    "消化道出血需要做胃镜吗？",
    "长期服用布洛芬会有什么风险？",
]


def _pct(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[k], 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MedPal Trace 压测")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("-c", "--concurrency", type=int, default=8)
    ap.add_argument("-n", "--requests", type=int, default=40)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--p95-ms", type=float, default=1200.0)
    ap.add_argument("--json", dest="json_out", default="")
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")
    lat: list[float] = []
    lat_trace: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()

    def one(i: int) -> None:
        q = QUESTIONS[i % len(QUESTIONS)]
        t0 = time.perf_counter()
        try:
            # trust_env=False：Windows 的系统代理会让 httpx 把 127.0.0.1 也送进代理，
            # 拿回 502 空包（本机实测）。打本机必须绕开系统代理。
            with httpx.Client(timeout=args.timeout, trust_env=False) as c:
                r = c.post(base + "/v1/ask", json={"question": q, "top_k": 8, "max_hops": 2})
                ms = (time.perf_counter() - t0) * 1000.0
                if r.status_code != 200:
                    raise RuntimeError(f"ask {r.status_code}: {r.text[:200]}")
                tid = r.json().get("trace_id") or ""
                t1 = time.perf_counter()
                r2 = c.get(base + "/v1/traces/" + tid)
                ms2 = (time.perf_counter() - t1) * 1000.0
                if r2.status_code != 200:
                    raise RuntimeError(f"trace {r2.status_code}: {r2.text[:200]}")
            with lock:
                lat.append(ms)
                lat_trace.append(ms2)
        except Exception as exc:
            with lock:
                errors.append(f"req{i} {type(exc).__name__}: {str(exc)[:160]}")

    try:
        h = httpx.get(base + "/health", timeout=args.timeout, trust_env=False)
        health = h.json()
    except Exception as exc:
        print("FAIL  /health 打不通:", type(exc).__name__, str(exc)[:200])
        return 1
    print("target =", base)
    print("health =", json.dumps({"storage": health.get("storage"),
                                 "llm": health.get("llm"),
                                 "assets": health.get("assets"),
                                 "ontology_version": health.get("ontology_version")},
                                ensure_ascii=False))

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        list(pool.map(one, range(args.requests)))
    wall = time.perf_counter() - t0

    ok = len(lat)
    out = {
        "base_url": base,
        "concurrency": args.concurrency,
        "requests": args.requests,
        "ok": ok,
        "errors": len(errors),
        "wall_s": round(wall, 3),
        "rps": round(ok / wall, 2) if wall > 0 else 0.0,
        "ask_ms": {"p50": _pct(lat, 50), "p95": _pct(lat, 95), "p99": _pct(lat, 99),
                  "max": round(max(lat), 2) if lat else 0.0,
                  "mean": round(statistics.fmean(lat), 2) if lat else 0.0},
        "trace_ms": {"p50": _pct(lat_trace, 50), "p95": _pct(lat_trace, 95),
                     "p99": _pct(lat_trace, 99)},
        "error_samples": errors[:5],
        "health": health,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.json_out:
        from pathlib import Path
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("written =", p)

    bad = []
    if errors:
        bad.append(f"错误 {len(errors)} 个（错误率 {100.0 * len(errors) / max(1, args.requests):.1f}%）")
    if out["ask_ms"]["p95"] > args.p95_ms:
        bad.append(f"P95 {out['ask_ms']['p95']:.0f}ms 超过门槛 {args.p95_ms:.0f}ms")
    if bad:
        print("FAIL  " + "；".join(bad))
        return 1
    print(f"LOAD OK  rps={out['rps']:.2f}  p50={out['ask_ms']['p50']:.0f}ms  "
          f"p95={out['ask_ms']['p95']:.0f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
