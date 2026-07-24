"""Seam tests for the public `run` / `resume` entrypoints."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from macs.constants import GATE_DESIGN_FREEZE, GATE_MERGE, MAX_MODULE_FANOUT
from macs.heuristic_llm import HeuristicLlmPort
from macs.pipeline import MacsGraphRunner
from macs.ports import RecordingLlmPort, RecordingToolPort, StubGraphRunner
from macs.run import resume, run
from macs.worktree import ensure_git_repo


def test_run_creates_artifacts_and_returns_result(tmp_path: Path) -> None:
    repo = tmp_path / "fixture-repo"
    repo.mkdir()

    llm = RecordingLlmPort()
    tools = RecordingToolPort()
    graph = StubGraphRunner()

    result = run(
        goal="add a hello endpoint",
        repo_path=repo,
        llm=llm,
        tools=tools,
        graph_runner=graph,
    )

    assert result.run_id
    assert result.artifacts_dir == repo / "runs" / result.run_id
    assert result.artifacts_dir.is_dir()
    status = json.loads((result.artifacts_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stub_nodes"] == [
        "orchestrator",
        "contracts",
        "module_designers",
        "reconciler",
        "implementers",
        "reviewer",
    ]
    assert result.status == "completed"
    assert result.waiting_for_human is False
    assert graph.calls == 1
    assert llm.calls == 0
    assert tools.calls == []


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
            "--stub-graph",
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


def test_orchestrator_and_contracts_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = run(
        goal="add auth [modules: auth, api]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    art = result.artifacts_dir
    work_graph = json.loads((art / "work_graph.json").read_text(encoding="utf-8"))
    contract = json.loads((art / "contract.json").read_text(encoding="utf-8"))
    assert work_graph["modules"] == ["auth", "api"]
    assert work_graph["max_module_fanout"] == MAX_MODULE_FANOUT
    assert "boundaries" in contract and "apis" in contract and "non_goals" in contract
    assert contract["modules"] == ["auth", "api"]
    assert not (repo / "auth.py").exists()
    assert result.waiting_for_human is True
    assert result.gate == GATE_DESIGN_FREEZE


def test_module_fanout_cap_truncates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = run(
        goal="big [modules: a, b, c, d]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    work_graph = json.loads((result.artifacts_dir / "work_graph.json").read_text(encoding="utf-8"))
    assert work_graph["modules"] == ["a", "b"]
    assert work_graph["truncated_modules"] == ["c", "d"]


def test_reconciler_conflict_and_no_conflict_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    clean = run(
        goal="ok [modules: auth, api]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    clean_conflicts = json.loads(
        (clean.artifacts_dir / "conflicts.json").read_text(encoding="utf-8")
    )
    assert clean_conflicts["conflicts"] == []
    frozen = json.loads((clean.artifacts_dir / "frozen_design.json").read_text(encoding="utf-8"))
    assert frozen["reconciled"] is False

    conflicted = run(
        goal="bad [modules: auth, api] [conflict:api]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    report = json.loads(
        (conflicted.artifacts_dir / "conflicts.json").read_text(encoding="utf-8")
    )
    assert report["conflicts"], "conflicts must not be silently dropped"
    assert report["conflicts"][0]["field"] == "apis"
    assert "auth" in report["conflicts"][0]["modules"]
    frozen2 = json.loads(
        (conflicted.artifacts_dir / "frozen_design.json").read_text(encoding="utf-8")
    )
    assert frozen2["reconciled"] is True
    assert frozen2["conflicts"]

    escalated = run(
        goal="bad [modules: auth, api] [conflict:api] [escalate:conflict]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    frozen3 = json.loads(
        (escalated.artifacts_dir / "frozen_design.json").read_text(encoding="utf-8")
    )
    assert frozen3.get("needs_human") is True
    assert frozen3.get("escalated") is True
    assert escalated.gate == GATE_DESIGN_FREEZE

    missing_owner = run(
        goal="own [modules: app] [missing-owner]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    owner_report = json.loads(
        (missing_owner.artifacts_dir / "conflicts.json").read_text(encoding="utf-8")
    )
    assert any(
        c.get("field") == "apis"
        and "missing owner" in c.get("detail", "")
        and c.get("modules") == ["app"]
        for c in owner_report["conflicts"]
    )


def test_design_freeze_gate_approve_and_reject(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    paused = run(
        goal="feature [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert paused.waiting_for_human and paused.gate == GATE_DESIGN_FREEZE
    assert not (paused.artifacts_dir / "worktrees").exists()

    rejected = resume(
        paused.run_id,
        decision="reject",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert rejected.status == "rejected"
    assert rejected.waiting_for_human is False
    assert not (paused.artifacts_dir / "worktrees").exists()

    paused2 = run(
        goal="feature2 [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    approved = resume(
        paused2.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert (paused2.artifacts_dir / "worktrees").is_dir() or approved.gate == GATE_MERGE
    assert approved.waiting_for_human is True
    assert approved.gate == GATE_MERGE


def test_implement_review_pr_and_failing_checks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    (repo / "macs_check").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (repo / "macs_check").chmod(0o755)

    paused = run(
        goal="x [modules: auth, api]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    after = resume(
        paused.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert after.status == "failed"
    assert after.waiting_for_human is False
    review = json.loads((paused.artifacts_dir / "review.json").read_text(encoding="utf-8"))
    assert review["passed"] is False
    assert review.get("repo_check_owner_task_ids") == ["task-1-auth"]
    assert review.get("routed_back_to") == ["task-1-auth"]
    assert not (paused.artifacts_dir / "pr.json").exists()
    impl = json.loads(
        (paused.artifacts_dir / "implementations.json").read_text(encoding="utf-8")
    )
    assert len(impl["tasks"]) == 2
    by_id = {t["id"]: t for t in impl["tasks"]}
    assert by_id["task-1-auth"]["revision"] == 2
    assert by_id["task-2-api"]["revision"] == 1
    auth_md = Path(by_id["task-1-auth"]["worktree"]) / "macs_impl" / "auth.md"
    api_md = Path(by_id["task-2-api"]["worktree"]) / "macs_impl" / "api.md"
    assert "Retry after reviewer routing" in auth_md.read_text(encoding="utf-8")
    assert "Retry after reviewer routing" not in api_md.read_text(encoding="utf-8")

    repo2 = tmp_path / "repo2"
    ensure_git_repo(repo2)
    (repo2 / "macs_check").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (repo2 / "macs_check").chmod(0o755)
    paused2 = run(
        goal="y [modules: app]",
        repo_path=repo2,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    after2 = resume(
        paused2.run_id,
        decision="approve",
        repo_path=repo2,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert after2.gate == GATE_MERGE
    assert (paused2.artifacts_dir / "pr.json").is_file()
    impl = json.loads(
        (paused2.artifacts_dir / "implementations.json").read_text(encoding="utf-8")
    )
    assert impl["tasks"]
    assert Path(impl["tasks"][0]["worktree"]).is_dir()
    assert impl["tasks"][0]["branch"].startswith("macs/")


def test_final_merge_gate_defines_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    (repo / "macs_check").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (repo / "macs_check").chmod(0o755)

    paused = run(
        goal="ship [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    at_merge = resume(
        paused.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert at_merge.waiting_for_human and at_merge.gate == GATE_MERGE
    assert at_merge.status != "completed"

    rejected = resume(
        paused.run_id,
        decision="reject",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert rejected.status == "rejected"
    assert rejected.waiting_for_human is False

    # Fresh happy path to completed
    paused2 = run(
        goal="ship2 [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    at_merge2 = resume(
        paused2.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    done = resume(
        paused2.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert at_merge2.gate == GATE_MERGE
    assert done.status == "completed"
    assert done.waiting_for_human is False
    state = json.loads(
        (paused2.artifacts_dir / "pipeline_state.json").read_text(encoding="utf-8")
    )
    assert state.get("merged_to_main") is False
    assert (paused2.artifacts_dir / "pr.json").is_file()
    review = json.loads((paused2.artifacts_dir / "review.json").read_text(encoding="utf-8"))
    assert review["passed"] is True


def test_cannot_complete_without_pr_bundle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    (repo / "macs_check").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (repo / "macs_check").chmod(0o755)
    paused = run(
        goal="ship [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    at_merge = resume(
        paused.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert at_merge.gate == GATE_MERGE
    state_path = paused.artifacts_dir / "pipeline_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["pr"] = {}
    state["review"] = {"passed": False}
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    done = resume(
        paused.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert done.status == "failed"
    assert done.waiting_for_human is False


def _reach_merge_gate(repo: Path) -> tuple[str, Path]:
    paused = run(
        goal="piece [modules: app]",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    at_merge = resume(
        paused.run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert at_merge.gate == GATE_MERGE
    return paused.run_id, paused.artifacts_dir


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state.__setitem__("pr", {}),
        lambda state: state.__setitem__(
            "pr", {**(state.get("pr") or {}), "checks_passed": False}
        ),
        lambda state: state.__setitem__(
            "review", {**(state.get("review") or {}), "passed": False}
        ),
    ],
    ids=["missing_pr", "checks_failed", "review_failed"],
)
def test_success_requires_each_done_piece(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None]
) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    (repo / "macs_check").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (repo / "macs_check").chmod(0o755)
    run_id, art = _reach_merge_gate(repo)
    state_path = art / "pipeline_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mutate(state)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    result = resume(
        run_id,
        decision="approve",
        repo_path=repo,
        llm=HeuristicLlmPort(),
        graph_runner=MacsGraphRunner(),
    )
    assert result.status == "failed"
    assert result.waiting_for_human is False


def test_success_requires_second_gate_approval(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_git_repo(repo)
    (repo / "macs_check").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (repo / "macs_check").chmod(0o755)
    _run_id, art = _reach_merge_gate(repo)
    waiting = json.loads((art / "status.json").read_text(encoding="utf-8"))
    assert waiting["waiting_for_human"] is True
    assert waiting["status"] == "waiting_for_human"
    assert waiting["gate"] == GATE_MERGE
