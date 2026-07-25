"""Tests for LLM env selection and JSON fence stripping."""

from __future__ import annotations

import os

from macs.heuristic_llm import HeuristicLlmPort
from macs.openai_llm import OpenAICompatibleLlmPort, _strip_json_fence, llm_from_env


def test_strip_json_fence() -> None:
    assert _strip_json_fence('{"a":1}') == '{"a":1}'
    assert _strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_llm_from_env_falls_back_without_api_key(monkeypatch: object) -> None:
    monkeypatch.delenv("API_KEY", raising=False)  # type: ignore[attr-defined]
    llm = llm_from_env()
    assert isinstance(llm, HeuristicLlmPort)


def test_llm_from_env_uses_openai_compatible_when_key_set(monkeypatch: object) -> None:
    monkeypatch.setenv("API_KEY", "sk-test")  # type: ignore[attr-defined]
    monkeypatch.delenv("BASE_URL", raising=False)  # type: ignore[attr-defined]
    monkeypatch.delenv("MODEL", raising=False)  # type: ignore[attr-defined]
    llm = llm_from_env()
    assert isinstance(llm, OpenAICompatibleLlmPort)
    assert llm.api_key == "sk-test"
    assert llm.base_url == "https://api.deepseek.com"
    assert llm.model == "deepseek-v4-pro"
