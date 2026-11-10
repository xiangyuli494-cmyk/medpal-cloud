#!/usr/bin/env python3
"""cloud_accept.py — 云资源「全开一小时」一键验收 + 证据归档。

一次跑完 B6 / B7 / C5 / B8 / 端到端 / B9，并把每一步原始输出落进证据目录，
跑完你只做一件事：去控制台删资源。

用法（仓库根目录，先把环境变量导进当前 shell）：
    export MEDPAL_DB_DSN="postgresql://user:pass@host:5432/medpal"
    export HUAWEI_AK=... HUAWEI_SK=... HUAWEI_OBS_BUCKET=... HUAWEI_REGION=cn-north-4
    export HUAWEI_KOOSEARCH_ENDPOINT=https://...
    export MEDPAL_LLM=openai MEDPAL_LLM_BASE_URL=... MEDPAL_LLM_MODEL=... MEDPAL_LLM_API_KEY=...
    python scripts/cloud_accept.py

可选：--only pg,obs,koo,llm,api,load   --skip load   --port 8010   --evidence-dir DIR
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _env() -> dict:
    env = dict(os.environ)
    parts = [str(ROOT / "packages" / "core"), str(ROOT / "apps" / "api")]
    old = env.get("PYTHONPATH", "")
    if old:
        parts.append(old)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("MEDPAL_DATA_DIR", str(ROOT / "data"))
    return env


def _run(step_id: str, title: str, cmd: list, ev: Path, timeout: int = 300) -> dict:
    print("\n== " + step_id + "  " + title)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), env=_env(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
        code = p.returncode
    except subprocess.TimeoutExpired as exc:
        out = f"TIMEOUT after {timeout}s\n{exc}"
        code = 124
    ms = int((time.perf_counter() - t0) * 1000)
    (ev / (step_id + ".log")).write_text(out, encoding="utf-8")
    print(out.strip()[-1500:])
    ok = code == 0
    print(("[OK]" if ok else "[FAIL]").ljust(4) + f" {step_id}  {ms / 1000.0:.1f}s")
    return {"id": step_id, "title": title, "ok": ok, "exit": code, "ms": ms,
            "log": str(ev / (step_id + ".log"))}


def _start_api(ev: Path, port: int, timeout: float):
    """起真 API 并等 /health 通；返回 (proc, base, health, out_lines)。

    服务在 main() 里起一次、跑完 api 与 load 再停 —— 压测要打的就是同一个进程。
    """
    import httpx

    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "apps" / "api"),
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace")
    base = f"http://127.0.0.1:{port}"
    out_lines: list[str] = []
    health = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(base + "/health", timeout=3.0, trust_env=False)
            if r.status_code == 200:
                health = r.json()
                break
        except Exception:
            pass
        time.sleep(1.0)
    return proc, base, health, out_lines


def _stop_api(proc, out_lines: list, log: Path) -> None:
    proc.terminate()
    try:
        tail = proc.communicate(timeout=10)[0] or ""
    except Exception:
        proc.kill()
        tail = ""
    log.write_text("\n".join(out_lines) + "\n\n[server]\n" + tail, encoding="utf-8")


def _api_step(ev: Path, base: str, health, out_lines: list) -> dict:
    """验 /health 走的是期望后端，再跑一次 ask->trace 闭环。服务由 main() 起好。"""
    import httpx

    print("\n== api  端到端：/health -> /v1/cloud -> /v1/ask -> /v1/traces")
    log = ev / "api.log"
    # (名称, 是否通过, 细节, 是否必过)。必过项失败才算这一步失败；
    # 槽位就绪度（obs/llm/koosearch）只是「这次有没有配」，不该让整步判红。
    checks: list[tuple[str, bool, str, bool]] = []
    if health is None:
        checks.append(("服务起来", False, "/health 一直没通", True))
    else:
        checks.append(("服务起来", True, "", True))
        out_lines.append("health = " + json.dumps(health, ensure_ascii=False))
        expect_backend = ("gaussdb" if (os.environ.get("MEDPAL_DB_DSN")
                          or os.environ.get("HUAWEI_GAUSSDB_DSN")) else "sqlite")
        checks.append(("storage=" + expect_backend,
                       health.get("storage") == expect_backend,
                       "实际 storage=" + str(health.get("storage")), True))
        checks.append(("llm_ready", bool(health.get("llm_ready")),
                       "llm=" + str(health.get("llm")) + " model=" + str(health.get("llm_model")),
                       False))
        try:
            cloud = httpx.get(base + "/v1/cloud", timeout=10.0, trust_env=False).json()
        except Exception as exc:
            cloud = {}
            out_lines.append("cloud = ERROR " + repr(exc))
        out_lines.append("cloud = " + json.dumps(cloud, ensure_ascii=False))
        ready = cloud.get("ready") or {}
        for k in ("obs", "gaussdb", "modelarts", "koosearch"):
            if k in ready:
                checks.append(("cloud.ready." + k, bool(ready[k]),
                               "missing=" + json.dumps(cloud.get("missing", {}).get(k, []),
                                                       ensure_ascii=False), False))
        ask = httpx.post(base + "/v1/ask",
                         json={"question": "上腹隐痛伴反酸，下一步该做什么检查？",
                               "top_k": 8, "max_hops": 2}, timeout=60.0, trust_env=False)
        ok_ask = ask.status_code == 200
        checks.append(("/v1/ask 200", ok_ask, ask.text[:200] if not ok_ask else "", True))
        if ok_ask:
            body = ask.json()
            tid = body.get("trace_id")
            conc = body.get("conclusion") or {}
            out_lines.append("ask = " + json.dumps(
                {"trace_id": tid,
                 "statement": conc.get("statement"),
                 "dept": conc.get("dept"), "exams": conc.get("exams"),
                 "drugs": conc.get("drugs"),
                 "evidence_count": body.get("evidence_count"),
                 "trace_completeness": body.get("trace_completeness"),
                 "elapsed_ms": body.get("elapsed_ms")},
                ensure_ascii=False))
            has_assets = bool((health or {}).get("assets"))
            checks.append(("有结论", bool(conc.get("statement")),
                           "" if conc.get("statement") else "statement 为空（库里没数据？）",
                           has_assets))
            tr = httpx.get(base + "/v1/traces/" + str(tid), timeout=30.0, trust_env=False)
            ok_tr = tr.status_code == 200 and bool(tr.json().get("steps"))
            checks.append(("trace 可回读", ok_tr, "" if ok_tr else tr.text[:200], True))
            if ok_tr:
                out_lines.append("steps = " + str(len(tr.json().get("steps") or [])))

    for name, ok, detail, must in checks:
        tag = "[OK]" if ok else ("[FAIL]" if must else "[WARN]")
        print(tag.ljust(6) + " " + name + ("  " + detail if detail else ""))
    musts = [c for c in checks if c[3]]
    all_ok = all(c[1] for c in musts) and bool(musts)
    return {"id": "api", "title": "端到端 /health + cloud + ask + trace",
            "ok": all_ok, "exit": 0 if all_ok else 1, "ms": 0,
            "log": str(log), "base_url": base,
            "checks": [{"name": n, "ok": o, "detail": d, "must": m}
                       for n, o, d, m in checks]}




def _seed_step(ev: Path) -> dict:
    """往当前后端灌演示数据（8 条三元组 + 1 份样本），api 步靠它才有非空结论。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "packages" / "core") + os.pathsep + str(ROOT / "apps" / "api")
    env.setdefault("MEDPAL_DATA_DIR", str(ROOT / "data"))
    env["PYTHONIOENCODING"] = "utf-8"
    log = ev / "seed.log"
    t0 = time.time()
    proc = subprocess.run([PY, "-m", "app.seed"], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    body = (proc.stdout or "") + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
    log.write_text(body, encoding="utf-8")
    ok = proc.returncode == 0
    print("== seed  演示数据")
    print("[OK]   已灌入" if ok else "[FAIL] seed 失败，看 seed.log")
    return {"id": "seed", "title": "灌演示数据（样本 + 8 条三元组）", "ok": ok,
            "exit": proc.returncode, "ms": (time.time() - t0) * 1000, "log": str(log)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="云资源一键验收")
    ap.add_argument("--only", default="", help="只跑这几步，逗号分隔：pg,obs,koo,llm,api,load")
    ap.add_argument("--skip", default="", help="跳过这几步")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--load-concurrency", type=int, default=8)
    ap.add_argument("--load-requests", type=int, default=40)
    # 本地离线 LLM 也要 ~2.4s；默认门槛按「真模型在线」放宽到 6s，验收时按需收紧。
    ap.add_argument("--p95-ms", type=float, default=6000.0)
    ap.add_argument("--evidence-dir", default="")
    ap.add_argument("--allow-remote-drop", action="store_true",
                    help="真机一次性实例：允许 check_pg 在远端库上 DROP 测试表")
    ap.add_argument("--reset", action="store_true",
                    help="跑 pg 步前先清空上次留下的测试表（重跑必须加）")
    ap.add_argument("--seed", action="store_true",
                    help="api 步前先灌演示数据；pg+api 同时跑时会自动开（pg 步保留表）")
    args = ap.parse_args(argv)

    ev = Path(args.evidence_dir) if args.evidence_dir else (
        ROOT / "docs" / "cloud-evidence" / time.strftime("%Y%m%d-%H%M%S"))
    ev.mkdir(parents=True, exist_ok=True)
    want = [x.strip() for x in args.only.split(",") if x.strip()] or ["pg", "obs", "koo", "llm", "api", "load"]
    skip = {x.strip() for x in args.skip.split(",") if x.strip()}
    want = [w for w in want if w not in skip]

    print("evidence =", ev)
    print("steps    =", ",".join(want))
    print("python   =", PY)

    results: list[dict] = []
    def script(name: str) -> list:
        return [PY, str(ROOT / "scripts" / (name + ".py"))]

    if "pg" in want:
        pg_cmd = script("check_pg")
        if args.allow_remote_drop:
            pg_cmd.append("--allow-remote-drop")
        if args.reset:
            pg_cmd.append("--reset")
        if set(want) & {"api", "load"}:
            pg_cmd.append("--keep")
        results.append(_run("pg", "PG/GaussDB 方言层九步（B6）", pg_cmd, ev))
    if "obs" in want:
        results.append(_run("obs", "OBS 七步（B7）", script("check_obs"), ev))
    if "koo" in want:
        results.append(_run("koo", "KooSearch 四步（C5）", script("check_koo") + ["--strict"], ev, 180))
    if "llm" in want:
        results.append(_run("llm", "ModelArts 真调用（B8）", script("smoke_llm") + ["--strict"], ev, 180))

    # pg 步刚建好表 / 显式 --seed 时先灌演示数据，否则 api 步只能拿到空结论。
    if args.seed or ("pg" in want and ({"api", "load"} & set(want))):
        results.append(_seed_step(ev))

    # 服务只起一次：api 步验契约，load 步压的就是同一个进程。
    base_url = f"http://127.0.0.1:{args.port}"
    proc = None
    out_lines: list = []
    health = None
    if want and (set(want) & {"api", "load"}):
        proc, base_url, health, out_lines = _start_api(ev, args.port, 60.0)
    try:
        if "api" in want:
            results.append(_api_step(ev, base_url, health, out_lines))

        if "load" in want:
            cmd = script("loadtest") + ["--base-url", base_url,
                                        "-c", str(args.load_concurrency),
                                        "-n", str(args.load_requests),
                                        "--p95-ms", str(args.p95_ms),
                                        "--json", str(ev / "loadtest.json")]
            results.append(_run("load", "并发压测 P50/P95（B9）", cmd, ev, 600))
    finally:
        if proc is not None:
            _stop_api(proc, out_lines, ev / "api.log")

    ok_all = all(r["ok"] for r in results)
    rows = ["| 步骤 | 结果 | 用时 | 日志 |", "| --- | --- | --- | --- |"]
    for r in results:
        rows.append(f"| {r['id']} {r['title']} | "
                    f"{'PASS' if r['ok'] else 'FAIL'} | {r['ms'] / 1000.0:.1f}s | "
                    f"{Path(r['log']).name} |")
    load_json = ev / "loadtest.json"
    extra = ""
    if load_json.exists():
        d = json.loads(load_json.read_text(encoding="utf-8"))
        extra = (f"\n## 压测\n\n- 并发 {d['concurrency']} / 请求 {d['requests']} / "
                 f"RPS {d['rps']:.2f} / 错误 {d['errors']}\n"
                 f"- /v1/ask P50 {d['ask_ms']['p50']:.0f}ms  P95 {d['ask_ms']['p95']:.0f}ms  "
                 f"P99 {d['ask_ms']['p99']:.0f}ms\n"
                 f"- /v1/traces P50 {d['trace_ms']['p50']:.0f}ms  P95 {d['trace_ms']['p95']:.0f}ms\n")
    md = (f"# 云资源验收证据 {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n环境：{ev.name}\n\n"
          + "\n".join(rows) + "\n" + extra)
    (ev / "summary.md").write_text(md, encoding="utf-8")
    (ev / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                     encoding="utf-8")

    print("\n" + "=" * 60)
    print("\n".join(rows))
    print("=" * 60)
    print("OVERALL  " + ("PASS —— 可以删资源了" if ok_all else "FAIL —— 先看日志再删"))
    print("evidence =", ev)
    if not ok_all:
        print("失败步骤日志：")
        for r in results:
            if not r["ok"]:
                print("  -", r["log"])
    print("\n删资源清单（控制台）：GaussDB 实例 / OBS 桶（含 _selftest 与证据对象）/ "
          "KooSearch 集群 / ModelArts 在线服务 / NAT&EIP；删完回来看账单确认归零。")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
