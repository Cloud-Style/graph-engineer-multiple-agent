"""Seam tests for the public `run` entrypoint (ticket 01)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from macs.ports import RecordingLlmPort, StubGraphRunner
from macs.run import run


def test_run_creates_artifacts_and_returns_result(tmp_path: Path) -> None:
    repo = tmp_path / "fixture-repo"
    repo.mkdir()

    llm = RecordingLlmPort()
    graph = StubGraphRunner()

    result = run(
        goal="add a hello endpoint",
        repo_path=repo,
        llm=llm,
        graph_runner=graph,
    )

    assert result.run_id
    assert result.artifacts_dir == repo / "runs" / result.run_id
    assert result.artifacts_dir.is_dir()
    assert (result.artifacts_dir / "status.json").is_file()
    assert result.status == "completed"
    assert result.waiting_for_human is False
    assert graph.calls == 1
    assert llm.calls == 0  # stub graph does not need the model


def test_cli_run_against_repo_path(tmp_path: Path) -> None:
    repo = tmp_path / "cli-fixture"
    repo.mkdir()

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "macs",
            "run",
            "ship a tracer bullet",
            "--repo",
            str(repo),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "completed"
    assert payload["waiting_for_human"] is False
    artifacts = Path(payload["artifacts_dir"])
    assert artifacts.is_dir()
    assert (artifacts / "status.json").is_file()
    assert artifacts.parent == repo / "runs"