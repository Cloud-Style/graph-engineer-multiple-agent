"""OpenAI-compatible LLM port (DeepSeek by default)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from openai import OpenAI

from macs.ports import LlmPort

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped, flags=re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return stripped


@dataclass
class OpenAICompatibleLlmPort:
    """Chat Completions against an OpenAI-compatible endpoint."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    calls: int = 0
    _client: OpenAI | None = field(default=None, init=False, repr=False)

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def complete(self, prompt: str) -> str:
        self.calls += 1
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a planning assistant for a multi-agent coding system. "
                        "Reply with ONE JSON object only. No markdown fences, no commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return _strip_json_fence(content)


def llm_from_env() -> LlmPort:
    """Prefer real LLM when ``API_KEY`` is set; otherwise offline heuristic."""
    api_key = os.environ.get("API_KEY", "").strip()
    if not api_key:
        from macs.heuristic_llm import HeuristicLlmPort

        return HeuristicLlmPort()
    base_url = os.environ.get("BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    model = os.environ.get("MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return OpenAICompatibleLlmPort(api_key=api_key, base_url=base_url, model=model)
