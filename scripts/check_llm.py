"""模型插槽自检：直连一次推理，验「用的是云上模型，不是 FakeLLM」。

不是单元测试，是「ModelArts Studio 开通之后」的验收入口，
和 check_obs.py / check_pg.py 同一套路子：脱敏 + 分级退出码。
退出码：0 通；2 缺 httpx；3 缺配置；4 网络或鉴权失败；5 返回结构不符。

用法：
    python scripts/check_llm.py
    python scripts/check_llm.py --base-url https://xxx/v1 --model DeepSeek-V3
    python scripts/check_llm.py --env .env.local
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_obs import load_env, mask  # noqa: E402

BASE_KEYS = ("MEDPAL_LLM_BASE_URL", "HUAWEI_MODEL_ENDPOINT")
MODEL_KEYS = ("MEDPAL_LLM_MODEL", "HUAWEI_MODEL_NAME")
KEY_KEYS = ("MEDPAL_LLM_API_KEY", "HUAWEI_MODEL_API_KEY")
PROMPT = "只回四个字：模型已就绪"


def pick(env: dict, keys: tuple, override: str = "") -> str:
    if override:
        return override
    for key in keys:
        val = os.environ.get(key) or env.get(key)
        if val:
            return val
    return ""


def chat(base_url: str, model: str, api_key: str, timeout: float = 30.0):
    import httpx

    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    started = time.time()
    resp = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    return resp, time.time() - started


def extract(resp) -> str:
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="模型插槽连通自检")
    ap.add_argument("--env", default=str(ROOT / ".env.local"))
    ap.add_argument("--base-url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--api-key", default="")
    args = ap.parse_args(argv)

    print(f"1) 配置 {args.env}")
    env = load_env(Path(args.env))
    base_url = pick(env, BASE_KEYS, args.base_url)
    model = pick(env, MODEL_KEYS, args.model)
    api_key = pick(env, KEY_KEYS, args.api_key)
    missing = []
    if not base_url:
        missing.append("MEDPAL_LLM_BASE_URL")
    if not model:
        missing.append("MEDPAL_LLM_MODEL")
    if missing:
        print("   [X] 缺配置：" + " / ".join(missing))
        print("       三行写进 .env.local：")
        print("       MEDPAL_LLM_BASE_URL=https://<推理端点>/v1")
        print("       MEDPAL_LLM_MODEL=<模型名>")
        print("       MEDPAL_LLM_API_KEY=<API Key>")
        return 3
    print("   base_url = " + base_url)
    print("   model    = " + model)
    print("   api_key  = " + (mask(api_key) if api_key else "(空)"))

    print("2) 驱动")
    try:
        import httpx  # noqa: F401
    except ImportError:
        print("   [X] 未装 httpx：pip install httpx")
        return 2
    print("   [OK] httpx 可用")

    print("3) 调用 /chat/completions（提示词：只回四个字）")
    try:
        resp, cost = chat(base_url, model, api_key)
    except Exception as exc:  # noqa: BLE001  网络层什么都可能抛
        print("   [X] 请求失败：" + str(exc)[:200])
        print("       常见原因：endpoint 少了 /v1、API Key 没开通该模型、区域不对")
        return 4
    print(f"   [OK] HTTP {resp.status_code}  耗时 {cost * 1000:.0f} ms")
    if resp.status_code >= 300:
        print("   [X] 服务端返回：" + resp.text[:300])
        return 4

    print("4) 解析返回")
    try:
        content = extract(resp)
    except Exception:  # noqa: BLE001  结构不符统一归 5
        print("   [X] 不是 OpenAI 兼容结构：" + resp.text[:200])
        return 5
    print("   [OK] " + content.strip().replace("\n", " ")[:120])
    print("")
    print(f"LLM READY: {model} @ {base_url}")
    print("把这行贴进 docs/cloud-resources.md 的 ModelArts 行当验收证据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
