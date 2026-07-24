"""Replaceable ports for LLM and graph execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RunContext:
    run_id: str
    goal: str
    repo_path: Path
    artifacts_dir: Path


class LlmPort(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a model completion for ``prompt``."""


class GraphRunner(Protocol):
    def execute(self, ctx: RunContext, llm: LlmPort) -> None:
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
class StubGraphRunner:
    """Ticket-01 stub: writes minimal status and does not call the LLM."""

    calls: int = 0

    def execute(self, ctx: RunContext, llm: LlmPort) -> None:
        del llm  # stub graph intentionally ignores the model
        self.calls += 1
        status_path = ctx.artifacts_dir / "status.json"
        status_path.write_text(
            '{"status":"completed","waiting_for_human":false}\n',
            encoding="utf-8",
        )
