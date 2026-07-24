"""Replaceable ports for LLM, tools, and graph execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RunContext:
    run_id: str
    goal: str
    repo_path: Path
    artifacts_dir: Path
    auto_approve: bool = False
    decision_source: str = "human"


class LlmPort(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a model completion for ``prompt``."""


class ToolPort(Protocol):
    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke a named tool; tests inject recording stubs instead of real tools."""


class GraphRunner(Protocol):
    def execute(self, ctx: RunContext, llm: LlmPort, tools: ToolPort) -> None:
        """Run the (possibly stubbed) orchestration graph for this run."""


@dataclass
class RecordingLlmPort:
    """Test double that records calls and never hits a network model."""

    responses: list[str] = field(default_factory=list)
    calls: int = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return ""


@dataclass
class RecordingToolPort:
    """Test double that records tool calls and never touches the real repo tools."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return ""


STUB_NODE_NAMES = (
    "orchestrator",
    "contracts",
    "module_designers",
    "reconciler",
    "implementers",
    "reviewer",
)


@dataclass
class StubGraphRunner:
    """Ticket-01 stub: records stub nodes, writes status, ignores LLM/tools."""

    calls: int = 0

    def execute(self, ctx: RunContext, llm: LlmPort, tools: ToolPort) -> None:
        del llm, tools
        self.calls += 1
        payload = {
            "status": "completed",
            "waiting_for_human": False,
            "stub_nodes": list(STUB_NODE_NAMES),
        }
        (ctx.artifacts_dir / "status.json").write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )
