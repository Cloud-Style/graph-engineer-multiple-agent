"""LangGraph-backed macs pipeline (org/work graph for v1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from macs.conflict import detect_conflicts
from macs.constants import (
    GATE_DESIGN_FREEZE,
    GATE_MERGE,
    MAX_MODULE_FANOUT,
    MAX_REVIEW_REROUTES,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_REJECTED,
    STATUS_RUNNING,
    STATUS_WAITING,
)
from macs.goal_parse import wants_failing_checks
from macs.ports import LlmPort, RunContext, ToolPort
from macs.worktree import commit_file, create_task_worktree, ensure_git_repo


class PipelineState(TypedDict, total=False):
    goal: str
    repo_path: str
    artifacts_dir: str
    run_id: str
    phase: str
    decision: str
    work_graph: dict[str, Any]
    contract: dict[str, Any]
    designs: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    frozen_design: dict[str, Any]
    tasks: list[dict[str, Any]]
    review: dict[str, Any]
    pr: dict[str, Any]
    status: str
    waiting_for_human: bool
    gate: str
    error: str
    merged_to_main: bool
    review_attempts: int
    retry_task_ids: list[str]


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _llm_json(llm: LlmPort, prompt: str) -> dict[str, Any]:
    raw = llm.complete(prompt)
    data = json.loads(raw or "{}")
    if not isinstance(data, dict):
        raise ValueError("LLM stage must return a JSON object")
    return data


def _persist_status(artifacts: Path, state: PipelineState) -> None:
    _write_json(
        artifacts / "status.json",
        {
            "status": state.get("status", STATUS_WAITING),
            "waiting_for_human": bool(state.get("waiting_for_human", False)),
            "gate": state.get("gate"),
            "phase": state.get("phase"),
            "error": state.get("error"),
        },
    )
    _write_json(artifacts / "pipeline_state.json", dict(state))


class MacsGraphRunner:
    """Full v1 graph: design path → human gate → implement/review → merge gate."""

    def __init__(self) -> None:
        self.calls = 0
        self._llm: LlmPort | None = None
        self._tools: ToolPort | None = None

    def execute(self, ctx: RunContext, llm: LlmPort, tools: ToolPort) -> None:
        self.calls += 1
        self._llm = llm
        self._tools = tools
        artifacts = ctx.artifacts_dir
        state_path = artifacts / "pipeline_state.json"
        if state_path.is_file():
            loaded = _read_json(state_path)
            if not isinstance(loaded, dict):
                raise ValueError("pipeline_state.json must be an object")
            state = cast(PipelineState, loaded)
        else:
            state = cast(
                PipelineState,
                {
                    "goal": ctx.goal,
                    "repo_path": str(ctx.repo_path),
                    "artifacts_dir": str(artifacts),
                    "run_id": ctx.run_id,
                    "phase": "start",
                    "status": STATUS_WAITING,
                    "waiting_for_human": False,
                },
            )
        graph = self._build_graph()
        compiled: CompiledStateGraph[PipelineState] = graph.compile()
        final = cast(PipelineState, compiled.invoke(state))
        _persist_status(artifacts, final)

    def _build_graph(self) -> StateGraph[PipelineState]:
        graph: StateGraph[PipelineState] = StateGraph(PipelineState)
        graph.add_node("route", self._route)
        graph.add_node("orchestrator", self._orchestrator)
        graph.add_node("contracts", self._contracts)
        graph.add_node("module_designers", self._module_designers)
        graph.add_node("reconciler", self._reconciler)
        graph.add_node("await_design_freeze", self._await_design_freeze)
        graph.add_node("handle_design_decision", self._handle_design_decision)
        graph.add_node("implementers", self._implementers)
        graph.add_node("reviewer", self._reviewer)
        graph.add_node("await_merge", self._await_merge)
        graph.add_node("handle_merge_decision", self._handle_merge_decision)

        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            self._route_target,
            {
                "orchestrator": "orchestrator",
                "handle_design_decision": "handle_design_decision",
                "handle_merge_decision": "handle_merge_decision",
                "end": END,
            },
        )
        graph.add_edge("orchestrator", "contracts")
        graph.add_edge("contracts", "module_designers")
        graph.add_edge("module_designers", "reconciler")
        graph.add_edge("reconciler", "await_design_freeze")
        graph.add_edge("await_design_freeze", END)
        graph.add_conditional_edges(
            "handle_design_decision",
            self._after_design_decision,
            {"implementers": "implementers", "end": END},
        )
        graph.add_edge("implementers", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            self._after_review,
            {"await_merge": "await_merge", "implementers": "implementers", "end": END},
        )
        graph.add_edge("await_merge", END)
        graph.add_edge("handle_merge_decision", END)
        return graph

    def _route(self, state: PipelineState) -> PipelineState:
        return state

    def _route_target(
        self, state: PipelineState
    ) -> Literal["orchestrator", "handle_design_decision", "handle_merge_decision", "end"]:
        phase = state.get("phase", "start")
        if phase in {"start", "orchestrator"}:
            return "orchestrator"
        if phase == "design_freeze" and state.get("decision"):
            return "handle_design_decision"
        if phase == "merge" and state.get("decision"):
            return "handle_merge_decision"
        if phase in {"design_freeze", "merge"} and not state.get("decision"):
            return "end"
        return "orchestrator"

    def _orchestrator(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        planned = _llm_json(
            self._llm,
            f"STAGE=orchestrator\nGOAL={state['goal']}\n",
        )
        modules = list(planned.get("modules") or ["app"])
        truncated = modules[MAX_MODULE_FANOUT:]
        modules = modules[:MAX_MODULE_FANOUT]
        work_graph = {
            "goal": state["goal"],
            "modules": modules,
            "max_module_fanout": MAX_MODULE_FANOUT,
            "truncated_modules": truncated,
            "steps": planned.get("steps")
            or [
                "contracts",
                "module_designers",
                "reconciler",
                "implementers",
                "reviewer",
            ],
        }
        _write_json(artifacts / "work_graph.json", work_graph)
        return {**state, "work_graph": work_graph, "phase": "contracts"}

    def _contracts(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        contract = _llm_json(
            self._llm,
            f"STAGE=contracts\nGOAL={state['goal']}\n",
        )
        modules = list((state.get("work_graph") or {}).get("modules") or contract.get("modules") or ["app"])
        contract["modules"] = modules
        for key in ("boundaries", "apis", "entities", "errors", "dependency_direction", "non_goals"):
            contract.setdefault(key, [])
        _write_json(artifacts / "contract.json", contract)
        return {**state, "contract": contract, "phase": "module_designers"}

    def _module_designers(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        designs_dir = artifacts / "designs"
        designs_dir.mkdir(parents=True, exist_ok=True)
        modules = list((state.get("work_graph") or {}).get("modules") or ["app"])
        designs: list[dict[str, Any]] = []
        for module in modules:
            design = _llm_json(
                self._llm,
                f"STAGE=module_design\nMODULE={module}\nGOAL={state['goal']}\n",
            )
            design["module"] = module
            _write_json(designs_dir / f"{module}.json", design)
            designs.append(design)
        # Ensure no production code edits during design: only artifacts_dir writes.
        return {**state, "designs": designs, "phase": "reconciler"}

    def _reconciler(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        designs = list(state.get("designs") or [])
        conflicts = detect_conflicts(designs)
        _write_json(artifacts / "conflicts.json", {"conflicts": conflicts})
        frozen: dict[str, Any]
        if not conflicts:
            frozen = {
                "modules": [d.get("module") for d in designs],
                "designs": designs,
                "reconciled": False,
                "apis": [api for d in designs for api in d.get("apis", [])],
            }
        else:
            proposal = _llm_json(
                self._llm,
                "STAGE=reconcile\nGOAL={}\nCONFLICTS={}\n".format(
                    state["goal"],
                    json.dumps(conflicts),
                ),
            )
            frozen = {
                "modules": [d.get("module") for d in designs],
                "designs": designs,
                "reconciled": True,
                "conflicts": conflicts,
                "apis": proposal.get("apis")
                or (designs[0].get("apis") if designs else []),
                "notes": proposal.get("notes", ""),
            }
            if not proposal.get("resolved", True):
                frozen["needs_human"] = True
                frozen["escalated"] = True
        _write_json(artifacts / "frozen_design.json", frozen)
        tasks = [
            {
                "id": f"task-{idx+1}-{mod}",
                "module": mod,
                "summary": f"Implement module {mod} per frozen design",
            }
            for idx, mod in enumerate(frozen.get("modules") or [])
            if mod
        ]
        _write_json(artifacts / "tasks.json", {"tasks": tasks})
        return {
            **state,
            "conflicts": conflicts,
            "frozen_design": frozen,
            "tasks": tasks,
            "phase": "design_freeze",
        }

    def _await_design_freeze(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        updated: PipelineState = {
            **state,
            "status": STATUS_WAITING,
            "waiting_for_human": True,
            "gate": GATE_DESIGN_FREEZE,
            "phase": "design_freeze",
            "decision": "",
        }
        _persist_status(artifacts, updated)
        return updated

    def _handle_design_decision(self, state: PipelineState) -> PipelineState:
        decision = (state.get("decision") or "").lower()
        if decision == "reject":
            updated: PipelineState = {
                **state,
                "status": STATUS_REJECTED,
                "waiting_for_human": False,
                "gate": GATE_DESIGN_FREEZE,
                "phase": "rejected_design",
                "decision": "",
            }
            _persist_status(Path(state["artifacts_dir"]), updated)
            return updated
        if decision != "approve":
            updated = {
                **state,
                "status": STATUS_FAILED,
                "waiting_for_human": False,
                "error": f"unknown design decision: {decision!r}",
                "phase": "failed",
                "decision": "",
            }
            _persist_status(Path(state["artifacts_dir"]), updated)
            return updated
        return {**state, "decision": "", "phase": "implementers", "waiting_for_human": False}

    def _after_design_decision(self, state: PipelineState) -> Literal["implementers", "end"]:
        if state.get("phase") == "implementers":
            return "implementers"
        return "end"

    def _implementers(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        repo = Path(state["repo_path"])
        ensure_git_repo(repo)
        base_tasks = list(state.get("tasks") or [])
        retry_ids = {str(x) for x in (state.get("retry_task_ids") or [])}
        targets = (
            [t for t in base_tasks if str(t.get("id")) in retry_ids]
            if retry_ids
            else base_tasks
        )
        worktrees_root = artifacts / "worktrees"
        updated = {str(t.get("id")): dict(t) for t in base_tasks}
        attempt = int(state.get("review_attempts") or 0)
        for task in targets:
            task_id = str(task["id"])
            path, branch = create_task_worktree(
                repo,
                run_id=state["run_id"],
                task_id=task_id,
                worktrees_root=worktrees_root,
            )
            revision = int(task.get("revision") or 0) + 1
            body = (
                f"# {task.get('summary')}\n\n"
                f"Implemented in isolated worktree.\n"
                f"revision: {revision}\n"
            )
            if attempt > 0:
                body += f"Retry after reviewer routing (attempt {attempt}).\n"
            commit_file(
                path,
                f"macs_impl/{task.get('module', 'app')}.md",
                body,
                f"macs: {task_id}",
            )
            updated[task_id] = {
                **task,
                "worktree": str(path),
                "branch": branch,
                "revision": revision,
            }
        realized = [updated[str(t.get("id"))] for t in base_tasks]
        _write_json(artifacts / "implementations.json", {"tasks": realized})
        _write_json(
            artifacts / "read_only_context.json",
            {"note": "shared read-only exploration context", "goal": state["goal"]},
        )
        return {
            **state,
            "tasks": realized,
            "retry_task_ids": [],
            "phase": "reviewer",
            "status": STATUS_RUNNING,
            "waiting_for_human": False,
        }

    def _reviewer(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        repo = Path(state["repo_path"])
        check_script = repo / "macs_check"
        passed = True
        detail = "no macs_check script; default pass"
        if check_script.is_file():
            import subprocess

            proc = subprocess.run(
                ["bash", str(check_script)],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            passed = proc.returncode == 0
            detail = proc.stdout + proc.stderr
        elif wants_failing_checks(state["goal"]):
            passed = False
            detail = "goal requested failing checks"
        review: dict[str, Any] = {
            "passed": passed,
            "detail": detail,
            "rewrote_features": False,
        }
        if not passed:
            attempts = int(state.get("review_attempts") or 0)
            tasks = list(state.get("tasks") or [])
            # Repo-level macs_check has no per-module signal; v1 routes only the
            # first task (sorted pipeline order) so other worktrees stay untouched.
            repo_check_owner_task_ids = [str(tasks[0]["id"])] if tasks else []
            review["routed_back_to"] = repo_check_owner_task_ids
            review["repo_check_owner_task_ids"] = repo_check_owner_task_ids
            _write_json(artifacts / "review.json", review)
            if attempts < MAX_REVIEW_REROUTES and repo_check_owner_task_ids:
                return {
                    **state,
                    "review": review,
                    "review_attempts": attempts + 1,
                    "retry_task_ids": repo_check_owner_task_ids,
                    "phase": "implementers",
                    "status": STATUS_RUNNING,
                    "waiting_for_human": False,
                    "error": (
                        "review checks failed; routed back to "
                        "repo_check_owner_task_ids"
                    ),
                }
            updated: PipelineState = {
                **state,
                "review": review,
                "status": STATUS_FAILED,
                "waiting_for_human": False,
                "phase": "review_failed",
                "error": "review checks failed after implementer retry",
            }
            _persist_status(artifacts, updated)
            return updated
        _write_json(artifacts / "review.json", review)
        pr = {
            "title": f"macs: {state['goal'][:60]}",
            "branches": [str(t.get("branch")) for t in state.get("tasks") or []],
            "body": "Draft PR produced by macs reviewer gate.",
            "checks_passed": True,
            "review_passed": True,
        }
        _write_json(artifacts / "pr.json", pr)
        branch_list = cast(list[str], pr["branches"])
        (artifacts / "pr.md").write_text(
            f"# {pr['title']}\n\n{pr['body']}\n\nBranches: {', '.join(branch_list)}\n",
            encoding="utf-8",
        )
        return {**state, "review": review, "pr": pr, "phase": "merge"}

    def _after_review(
        self, state: PipelineState
    ) -> Literal["await_merge", "implementers", "end"]:
        if state.get("phase") == "merge":
            return "await_merge"
        if state.get("phase") == "implementers":
            return "implementers"
        return "end"

    def _await_merge(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        updated: PipelineState = {
            **state,
            "status": STATUS_WAITING,
            "waiting_for_human": True,
            "gate": GATE_MERGE,
            "phase": "merge",
            "decision": "",
        }
        _persist_status(artifacts, updated)
        return updated

    def _handle_merge_decision(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        decision = (state.get("decision") or "").lower()
        # Never auto-merge to main; approval only marks run success.
        if decision == "approve":
            pr = state.get("pr") or {}
            review = state.get("review") or {}
            if not (pr and review.get("passed") and pr.get("checks_passed")):
                updated: PipelineState = {
                    **state,
                    "status": STATUS_FAILED,
                    "waiting_for_human": False,
                    "error": "cannot complete without PR draft + passing review/checks",
                    "phase": "failed",
                    "decision": "",
                }
            else:
                updated = {
                    **state,
                    "status": STATUS_COMPLETED,
                    "waiting_for_human": False,
                    "gate": GATE_MERGE,
                    "phase": "completed",
                    "decision": "",
                    "merged_to_main": False,
                }
        elif decision == "reject":
            updated = {
                **state,
                "status": STATUS_REJECTED,
                "waiting_for_human": False,
                "gate": GATE_MERGE,
                "phase": "rejected_merge",
                "decision": "",
                "merged_to_main": False,
            }
        else:
            updated = {
                **state,
                "status": STATUS_FAILED,
                "waiting_for_human": False,
                "error": f"unknown merge decision: {decision!r}",
                "phase": "failed",
                "decision": "",
            }
        _persist_status(artifacts, updated)
        return updated
