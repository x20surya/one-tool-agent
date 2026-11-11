"""OpenAI-compatible LLM client using ONLY stdlib urllib.

Works with OpenAI, Groq, Together, and local Ollama (base URL containing
localhost/11434 needs no key). Returns None on any failure or when no key
is configured, so callers can fall back to extractive answers.
"""
from __future__ import annotations

import json
import urllib.request


class LLMClient:
    def __init__(self, base_url: str, api_key: str = "", model: str = "gpt-4o-mini",
                 timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key) or "localhost" in self.base_url or "11434" in self.base_url

    def complete(self, messages: list[dict], temperature: float = 0.2) -> str | None:
        if not self.available:
            return None
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key or 'ollama'}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None
