from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    db_path: str = "memory.db"
    cache_ttl_seconds: int = 900  # 15 minutes
    search_top_k: int = 5
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    serper_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            db_path=os.environ.get("ONE_TOOL_DB", "memory.db"),
            cache_ttl_seconds=int(os.environ.get("SEARCH_CACHE_TTL", "900")),
            llm_base_url=(
                os.environ.get("LLM_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or "https://api.openai.com/v1"
            ),
            llm_api_key=(
                os.environ.get("LLM_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("GROQ_API_KEY")
                or ""
            ),
            llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
            serper_api_key=os.environ.get("SERPER_API_KEY", ""),
        )
