"""云端模型连通性冒烟：有 key 就打一次真调用，没 key 就明确说「跳过」并退出 0。

用法（仓库根目录）：
    PYTHONPATH=packages/core:apps/api python scripts/smoke_llm.py
    MEDPAL_LLM=modelarts MEDPAL_LLM_BASE_URL=https://api.modelarts-maas.com/v1 \
      MEDPAL_LLM_MODEL=deepseek-v3 MEDPAL_LLM_API_KEY=sk-xxx python scripts/smoke_llm.py --strict

两种模式：
    默认   —— 没配模型时打印 SKIP 并退出 0（本地跑 verify 不该因为没买模型而红）
    --strict —— 没配模型也算失败（答辩前「模型到底通没通」用它）

它能证明两件事，正是答辩要说清的：
    1) base_url 是活的 —— 401/403 说明域名和鉴权层正常，只差有效 key；
    2) 有效时 narrative 真的来自云上模型，而不是 FakeLLM 的 [offline] 前缀。
"""

from __future__ import annotations

import argparse
import sys

from medpal_core.config import settings
from medpal_core.llm import FakeLLM, build_llm

PROBE_SYSTEM = "你只回答一个词。"
PROBE_USER = "回复：ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="云端模型连通性冒烟")
    ap.add_argument("--strict", action="store_true", help="没配模型也判失败")
    ap.add_argument("--timeout", type=float, default=30.0, help="单次调用超时秒数")
    args = ap.parse_args(argv)

    cfg = settings()
    print("provider =", cfg.llm_provider)
    print("base_url =", cfg.llm_base_url or "(空)")
    print("model    =", cfg.llm_model or "(空)")
    print("api_key  =", "已配置" if cfg.llm_api_key else "(空)")

    if cfg.llm_provider == "offline" or not cfg.llm_base_url or not cfg.llm_model:
        msg = "SKIP  模型未配置（MEDPAL_LLM / MEDPAL_LLM_BASE_URL / MEDPAL_LLM_MODEL）"
        if args.strict:
            print("FAIL  " + msg + "，--strict 下按失败处理")
            return 1
        print(msg)
        return 0

    try:
        llm = build_llm()
    except Exception as exc:
        print("FAIL  构建模型客户端失败:", type(exc).__name__, str(exc)[:200])
        return 1
    if isinstance(llm, FakeLLM):
        print("FAIL  provider 说是云端，实际拿到 FakeLLM —— 配置没生效")
        return 1

    llm.timeout = args.timeout
    try:
        out = llm.complete(PROBE_SYSTEM, PROBE_USER)
    except Exception as exc:
        text = str(exc)
        print("FAIL  调用失败:", type(exc).__name__, text[:300])
        hint = ""
        if "401" in text or "403" in text:
            hint = "鉴权被拒：域名是通的，换一个有效 MEDPAL_LLM_API_KEY 即可"
        elif "400" in text:
            hint = "请求被拒：多半是 MEDPAL_LLM_MODEL 不在该端点的可用模型列表里"
        elif "Timeout" in text or "timed out" in text.lower():
            hint = "超时：本机到 api.modelarts-maas.com 需要走出口（代理 127.0.0.1:7892）"
        if hint:
            print("      " + hint)
        return 1

    if not out.strip():
        print("FAIL  模型返回空内容")
        return 1
    print("OK    云端模型可用；返回片段:", out.strip().replace(chr(10), " ")[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())