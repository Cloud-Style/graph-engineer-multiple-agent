"""Public `run` seam for the multi-agent coding assistant."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from macs.ports import GraphRunner, LlmPort, RecordingLlmPort, RunContext, StubGraphRunner


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    artifacts_dir: Path
    waiting_for_human: bool


def run(
    goal: str,
    *,
    repo_path: Path | None = None,
    llm: LlmPort | None = None,
    graph_runner: GraphRunner | None = None,
) -> RunResult:
    """Execute one assistant run against a target repository.

    Defaults to the current working directory. Callers may inject LLM and
    graph ports (tests use stubs that never call a real model).
    """
    target = (repo_path or Path.cwd()).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"repo_path is not a directory: {target}")

    run_id = uuid.uuid4().hex
    artifacts_dir = target / "runs" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=False)

    active_llm: LlmPort = llm if llm is not None else RecordingLlmPort()
    active_graph: GraphRunner = (
        graph_runner if graph_runner is not None else StubGraphRunner()
    )

    ctx = RunContext(
        run_id=run_id,
        goal=goal,
        repo_path=target,
        artifacts_dir=artifacts_dir,
    )
    active_graph.execute(ctx, active_llm)

    status_path = artifacts_dir / "status.json"
    status = "completed"
    waiting = False
    if status_path.is_file():
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        status = str(payload.get("status", status))
        waiting = bool(payload.get("waiting_for_human", waiting))

    return RunResult(
        run_id=run_id,
        status=status,
        artifacts_dir=artifacts_dir,
        waiting_for_human=waiting,
    )
