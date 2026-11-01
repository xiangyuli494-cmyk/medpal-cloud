"""运行期配置：环境变量只在这一个文件里读，其他模块依赖本模块的函数。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


@dataclass(frozen=True)
class Settings:
    """与存储路径无关的那部分配置。路径见 storage.db。"""

    llm_provider: str = "offline"  # offline | openai  （openai 兼容 ModelArts Studio / 盘古）
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    max_hops: int = 2
    top_k: int = 8
    lexicon_path: str = ""


def settings() -> Settings:
    return Settings(
        llm_provider=env("MEDPAL_LLM", "offline"),
        llm_model=env("MEDPAL_LLM_MODEL"),
        llm_base_url=env("MEDPAL_LLM_BASE_URL"),
        llm_api_key=env("MEDPAL_LLM_API_KEY"),
        max_hops=int(env("MEDPAL_MAX_HOPS", "2")),
        top_k=int(env("MEDPAL_TOP_K", "8")),
        lexicon_path=env("MEDPAL_LEXICON"),
    )
