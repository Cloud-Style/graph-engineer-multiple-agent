"""Public `run` / `resume` seams for the multi-agent coding assistant."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from macs.constants import STATUS_COMPLETED, STATUS_WAITING
from macs.openai_llm import llm_from_env
from macs.pipeline import MacsGraphRunner
from macs.ports import (
    GraphRunner,
    LlmPort,
    RecordingToolPort,
    RunContext,
    StubGraphRunner,
    ToolPort,
)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    artifacts_dir: Path
    waiting_for_human: bool
    gate: str | None = None


def _result_from_artifacts(run_id: str, artifacts_dir: Path) -> RunResult:
    status = STATUS_COMPLETED
    waiting = False
    gate: str | None = None
    status_path = artifacts_dir / "status.json"
    if status_path.is_file():
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        status = str(payload.get("status", status))
        waiting = bool(payload.get("waiting_for_human", waiting))
        raw_gate = payload.get("gate")
        gate = str(raw_gate) if raw_gate else None
    return RunResult(
        run_id=run_id,
        status=status,
        artifacts_dir=artifacts_dir,
        waiting_for_human=waiting,
        gate=gate,
    )


def run(
    goal: str,
    *,
    repo_path: Path | None = None,
    llm: LlmPort | None = None,
    tools: ToolPort | None = None,
    graph_runner: GraphRunner | None = None,
) -> RunResult:
    """Execute one assistant run against a target repository.

    Defaults to the current working directory. Callers may inject LLM, tool,
    and graph ports (tests use stubs that never call a real model or tools).
    """
    target = (repo_path or Path.cwd()).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"repo_path is not a directory: {target}")

    run_id = uuid.uuid4().hex
    artifacts_dir = target / "runs" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=False)

    active_llm: LlmPort = llm if llm is not None else llm_from_env()
    active_tools: ToolPort = tools if tools is not None else RecordingToolPort()
    active_graph: GraphRunner = (
        graph_runner if graph_runner is not None else MacsGraphRunner()
    )

    ctx = RunContext(
        run_id=run_id,
        goal=goal,
        repo_path=target,
        artifacts_dir=artifacts_dir,
    )
    active_graph.execute(ctx, active_llm, active_tools)
    return _result_from_artifacts(run_id, artifacts_dir)


def resume(
    run_id: str,
    *,
    decision: Literal["approve", "reject"],
    repo_path: Path | None = None,
    llm: LlmPort | None = None,
    tools: ToolPort | None = None,
    graph_runner: GraphRunner | None = None,
) -> RunResult:
    """Resume a paused run after a human gate decision."""
    target = (repo_path or Path.cwd()).resolve()
    artifacts_dir = target / "runs" / run_id
    state_path = artifacts_dir / "pipeline_state.json"
    if not state_path.is_file():
        raise FileNotFoundError(f"no pipeline state for run {run_id}: {state_path}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["decision"] = decision
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    goal = str(state.get("goal") or "")
    active_llm: LlmPort = llm if llm is not None else llm_from_env()
    active_tools: ToolPort = tools if tools is not None else RecordingToolPort()
    active_graph: GraphRunner = (
        graph_runner if graph_runner is not None else MacsGraphRunner()
    )
    ctx = RunContext(
        run_id=run_id,
        goal=goal,
        repo_path=target,
        artifacts_dir=artifacts_dir,
    )
    active_graph.execute(ctx, active_llm, active_tools)
    return _result_from_artifacts(run_id, artifacts_dir)


# Re-export stub runner for ticket-01 style tests
__all__ = ["RunResult", "run", "resume", "StubGraphRunner", "STATUS_WAITING"]
