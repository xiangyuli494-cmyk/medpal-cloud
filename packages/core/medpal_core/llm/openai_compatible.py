"""OpenAI 兼容客户端：ModelArts Studio / 盘古 / vLLM 都能直接指向这里。

不引 openai 包，只用 httpx，少一个依赖就少一个部署时的坑。
"""

from __future__ import annotations

import httpx


class LLMCallError(RuntimeError):
    pass


class OpenAICompatibleLLM:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        if not base_url or not model:
            raise LLMCallError("缺少 MEDPAL_LLM_BASE_URL / MEDPAL_LLM_MODEL，无法启用云端模型")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            r = httpx.post(self.base_url + "/chat/completions", json=payload,
                           headers=headers, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMCallError("模型调用失败: " + str(exc)) from exc
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMCallError("模型返回结构不符合 OpenAI 兼容格式: " + str(data)[:200]) from exc
