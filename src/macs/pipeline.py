"""LangGraph-backed macs pipeline (org/work graph for v1)."""

from __future__ import annotations

import json
import re
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
from macs.events import append_event
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
    decision_source: str
    auto_approve: bool
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


def _task_ids_for_contract_owners(
    tasks: list[dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    """Map contract API owners to implementer task ids (ownership-based routing).

    Returns an empty list when no owner matches a task — callers must not
    silently fall back to the first queue item.
    """
    owners: list[str] = []
    seen: set[str] = set()
    for api in (contract or {}).get("apis") or []:
        if not isinstance(api, dict):
            continue
        owner = api.get("owner")
        if owner in (None, ""):
            continue
        name = str(owner)
        if name not in seen:
            seen.add(name)
            owners.append(name)
    by_module = {str(t.get("module")): str(t["id"]) for t in tasks if t.get("id")}
    return [by_module[m] for m in owners if m in by_module]


def _stage_from_prompt(prompt: str) -> str:
    match = re.search(r"^STAGE=(\S+)", prompt, flags=re.MULTILINE)
    return match.group(1) if match else "unknown"


def _emit(state: PipelineState, event_type: str, summary: str, **fields: Any) -> None:
    append_event(
        Path(state["artifacts_dir"]),
        run_id=str(state.get("run_id") or ""),
        event_type=event_type,
        summary=summary,
        **fields,
    )


def _fail_pipeline(state: PipelineState, error: str) -> PipelineState:
    updated: PipelineState = {
        **state,
        "status": STATUS_FAILED,
        "waiting_for_human": False,
        "phase": "failed",
        "error": error,
        "decision": "",
        "decision_source": "",
    }
    _persist_status(Path(state["artifacts_dir"]), updated)
    _emit(updated, "run_terminal", "run failed", status=STATUS_FAILED, error=error)
    return updated


def _llm_json(llm: LlmPort, prompt: str, state: PipelineState) -> dict[str, Any]:
    stage = _stage_from_prompt(prompt)
    try:
        raw = llm.complete(prompt)
    except Exception as exc:
        _emit(
            state,
            "llm_call",
            f"LLM {stage} raised",
            stage=stage,
            ok=False,
            error=str(exc),
        )
        raise
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        _emit(
            state,
            "llm_call",
            f"LLM {stage} returned invalid JSON",
            stage=stage,
            ok=False,
            error=str(exc),
            response_chars=len(raw or ""),
        )
        raise
    if not isinstance(data, dict):
        _emit(
            state,
            "llm_call",
            f"LLM {stage} returned non-object JSON",
            stage=stage,
            ok=False,
            response_chars=len(raw or ""),
        )
        raise ValueError("LLM stage must return a JSON object")
    _emit(
        state,
        "llm_call",
        f"LLM {stage} completed",
        stage=stage,
        ok=True,
        response_chars=len(raw or ""),
    )
    return data


def _parse_implement_files(payload: dict[str, Any]) -> list[tuple[str, str]]:
    files = payload.get("files")
    out: list[tuple[str, str]] = []
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if path in (None, "") or "content" not in item:
                continue
            out.append((str(path), str(item["content"])))
    elif isinstance(files, dict):
        out.extend((str(path), str(content)) for path, content in files.items())
    return out


def _worktree_has_py(worktree: Path) -> bool:
    return any(path.suffix == ".py" and path.is_file() for path in worktree.rglob("*.py"))


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
                    "auto_approve": ctx.auto_approve,
                },
            )
        graph = self._build_graph()
        compiled: CompiledStateGraph[PipelineState] = graph.compile()
        try:
            final = cast(PipelineState, compiled.invoke(state))
        except Exception as exc:
            _fail_pipeline(state, f"pipeline error: {exc}")
            return
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
        graph.add_conditional_edges(
            "implementers",
            self._after_implementers,
            {"reviewer": "reviewer", "end": END},
        )
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
        # Terminal / unknown phases must NOT fall through to re-planning.
        if phase in {
            "completed",
            "rejected_design",
            "rejected_merge",
            "review_failed",
            "failed",
        }:
            return "end"
        if phase in {"start", "orchestrator"}:
            return "orchestrator"
        if phase == "design_freeze" and state.get("decision"):
            return "handle_design_decision"
        if phase == "merge" and state.get("decision"):
            return "handle_merge_decision"
        if phase in {"design_freeze", "merge"} and not state.get("decision"):
            return "end"
        return "end"

    def _orchestrator(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        planned = _llm_json(
            self._llm,
            (
                "STAGE=orchestrator\n"
                f"GOAL={state['goal']}\n"
                "Return JSON: "
                '{"modules":["name",...],"steps":["contracts","module_designers",'
                '"reconciler","implementers","reviewer"]}. '
                "Pick 1-2 modules that fit the goal.\n"
            ),
            state,
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
        updated: PipelineState = {**state, "work_graph": work_graph, "phase": "contracts"}
        _emit(updated, "phase_completed", "orchestrator planned work graph", phase="orchestrator")
        return updated

    def _contracts(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
        artifacts = Path(state["artifacts_dir"])
        contract = _llm_json(
            self._llm,
            (
                "STAGE=contracts\n"
                f"GOAL={state['goal']}\n"
                "Return JSON with keys: boundaries (string[]), apis "
                '([{name,owner,shape}]), entities ([{name,fields}]), '
                "errors ([{code}]), dependency_direction ([{from,to}]), "
                "non_goals (string[]), modules (string[]). "
                "Keep it thin; owner must be one of the planned modules.\n"
            ),
            state,
        )
        modules = list((state.get("work_graph") or {}).get("modules") or contract.get("modules") or ["app"])
        contract["modules"] = modules
        for key in ("boundaries", "apis", "entities", "errors", "dependency_direction", "non_goals"):
            contract.setdefault(key, [])
        _write_json(artifacts / "contract.json", contract)
        updated: PipelineState = {**state, "contract": contract, "phase": "module_designers"}
        _emit(updated, "phase_completed", "contracts authored", phase="contracts")
        return updated

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
                (
                    "STAGE=module_design\n"
                    f"MODULE={module}\n"
                    f"GOAL={state['goal']}\n"
                    "Return JSON: "
                    '{"module":"...","apis":[{"name","owner","shape"}],'
                    '"entities":[{"name","fields"}],"errors":[{"code"}],'
                    '"dependency_direction":[{"from","to"}]}. '
                    f"Design only module {module!r}; set api.owner to that module.\n"
                ),
                state,
            )
            design["module"] = module
            _write_json(designs_dir / f"{module}.json", design)
            designs.append(design)
        # Ensure no production code edits during design: only artifacts_dir writes.
        updated: PipelineState = {**state, "designs": designs, "phase": "reconciler"}
        _emit(
            updated,
            "phase_completed",
            f"module designs written ({len(designs)})",
            phase="module_designers",
        )
        return updated

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
                (
                    "STAGE=reconcile\n"
                    f"GOAL={state['goal']}\n"
                    f"CONFLICTS={json.dumps(conflicts)}\n"
                    "Return JSON: "
                    '{"resolved":true|false,"apis":[{"name","owner","shape"}],'
                    '"notes":"..."}. Prefer resolving when possible.\n'
                ),
                state,
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
        updated: PipelineState = {
            **state,
            "conflicts": conflicts,
            "frozen_design": frozen,
            "tasks": tasks,
            "phase": "design_freeze",
        }
        _emit(
            updated,
            "phase_completed",
            "reconciler produced frozen design",
            phase="reconciler",
            conflict_count=len(conflicts),
        )
        return updated

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
        _emit(
            updated,
            "gate_entered",
            "waiting at design freeze gate",
            gate=GATE_DESIGN_FREEZE,
        )
        return updated

    def _handle_design_decision(self, state: PipelineState) -> PipelineState:
        decision = (state.get("decision") or "").lower()
        source = str(state.get("decision_source") or "human")
        _emit(
            state,
            "gate_decision",
            f"design freeze {decision}",
            gate=GATE_DESIGN_FREEZE,
            decision=decision,
            source=source,
        )
        if decision == "reject":
            updated: PipelineState = {
                **state,
                "status": STATUS_REJECTED,
                "waiting_for_human": False,
                "gate": GATE_DESIGN_FREEZE,
                "phase": "rejected_design",
                "decision": "",
                "decision_source": "",
            }
            _persist_status(Path(state["artifacts_dir"]), updated)
            _emit(updated, "run_terminal", "design rejected", status=STATUS_REJECTED)
            return updated
        if decision != "approve":
            updated = {
                **state,
                "status": STATUS_FAILED,
                "waiting_for_human": False,
                "error": f"unknown design decision: {decision!r}",
                "phase": "failed",
                "decision": "",
                "decision_source": "",
            }
            _persist_status(Path(state["artifacts_dir"]), updated)
            _emit(updated, "run_terminal", "failed at design gate", status=STATUS_FAILED)
            return updated
        return {
            **state,
            "decision": "",
            "decision_source": "",
            "phase": "implementers",
            "waiting_for_human": False,
        }

    def _after_design_decision(self, state: PipelineState) -> Literal["implementers", "end"]:
        if state.get("phase") == "implementers":
            return "implementers"
        return "end"

    def _after_implementers(self, state: PipelineState) -> Literal["reviewer", "end"]:
        if state.get("phase") == "failed":
            return "end"
        return "reviewer"

    def _implementers(self, state: PipelineState) -> PipelineState:
        assert self._llm is not None
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
        frozen = state.get("frozen_design") or {}
        for task in targets:
            task_id = str(task["id"])
            module = str(task.get("module") or "app")
            path, branch = create_task_worktree(
                repo,
                run_id=state["run_id"],
                task_id=task_id,
                worktrees_root=worktrees_root,
            )
            revision = int(task.get("revision") or 0) + 1
            try:
                payload = _llm_json(
                    self._llm,
                    (
                        "STAGE=implement\n"
                        f"MODULE={module}\n"
                        f"TASK_ID={task_id}\n"
                        f"REVISION={revision}\n"
                        f"GOAL={state['goal']}\n"
                        f"FROZEN_DESIGN={json.dumps(frozen, ensure_ascii=False)}\n"
                        "Return JSON: "
                        '{"files":[{"path":"relative/path.py","content":"..."}]}. '
                        "Write real Python source for this module only; "
                        "do not use placeholder markdown as the sole deliverable.\n"
                    ),
                    state,
                )
            except Exception as exc:
                return _fail_pipeline(
                    state,
                    f"implement LLM failed for {task_id}: {exc}",
                )
            files = _parse_implement_files(payload)
            usable = [(p, c) for p, c in files if str(c).strip()]
            py_files = [(p, c) for p, c in usable if p.endswith(".py")]
            if not py_files:
                return _fail_pipeline(
                    state,
                    (
                        f"implement produced no usable Python source for {task_id} "
                        "(refusing placeholder-only success)"
                    ),
                )
            written_paths: list[str] = []
            for rel, content in usable:
                commit_file(path, rel, content, f"macs: {task_id} {rel}")
                written_paths.append(rel)
            _emit(
                state,
                "files_written",
                f"implementer wrote {len(written_paths)} file(s) for {task_id}",
                task_id=task_id,
                module=module,
                paths=written_paths,
            )
            updated[task_id] = {
                **task,
                "worktree": str(path),
                "branch": branch,
                "revision": revision,
                "files": written_paths,
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
        source_files_present = any(
            _worktree_has_py(Path(str(t.get("worktree"))))
            for t in state.get("tasks") or []
            if t.get("worktree")
        )
        if not source_files_present:
            passed = False
            detail = (detail + "; " if detail else "") + "no Python source in worktrees"
        review: dict[str, Any] = {
            "passed": passed,
            "detail": detail,
            "rewrote_features": False,
            "source_files_present": source_files_present,
        }
        _emit(
            state,
            "review_result",
            "review checks passed" if passed else "review checks failed",
            passed=passed,
            source_files_present=source_files_present,
        )
        if not passed:
            attempts = int(state.get("review_attempts") or 0)
            tasks = list(state.get("tasks") or [])
            # Route to implementers whose modules own APIs in the contract
            # (not "first task in the queue").
            repo_check_owner_task_ids = _task_ids_for_contract_owners(
                tasks,
                state.get("contract"),
            )
            review["repo_check_owner_task_ids"] = repo_check_owner_task_ids
            _write_json(artifacts / "review.json", review)
            if not repo_check_owner_task_ids:
                updated: PipelineState = {
                    **state,
                    "review": review,
                    "status": STATUS_FAILED,
                    "waiting_for_human": False,
                    "phase": "review_failed",
                    "error": (
                        "review checks failed; no contract API owner maps to "
                        "an implementer task (refusing queue-first fallback)"
                    ),
                }
                _persist_status(artifacts, updated)
                _emit(
                    updated,
                    "run_terminal",
                    "review failed without owner mapping",
                    status=STATUS_FAILED,
                )
                return updated
            if attempts < MAX_REVIEW_REROUTES:
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
            updated = {
                **state,
                "review": review,
                "status": STATUS_FAILED,
                "waiting_for_human": False,
                "phase": "review_failed",
                "error": "review checks failed after implementer retry",
            }
            _persist_status(artifacts, updated)
            _emit(
                updated,
                "run_terminal",
                "review failed after implementer retry",
                status=STATUS_FAILED,
            )
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
        _emit(updated, "gate_entered", "waiting at merge gate", gate=GATE_MERGE)
        return updated

    def _handle_merge_decision(self, state: PipelineState) -> PipelineState:
        artifacts = Path(state["artifacts_dir"])
        decision = (state.get("decision") or "").lower()
        source = str(state.get("decision_source") or "human")
        _emit(
            state,
            "gate_decision",
            f"merge {decision}",
            gate=GATE_MERGE,
            decision=decision,
            source=source,
        )
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
                    "decision_source": "",
                }
            else:
                updated = {
                    **state,
                    "status": STATUS_COMPLETED,
                    "waiting_for_human": False,
                    "gate": GATE_MERGE,
                    "phase": "completed",
                    "decision": "",
                    "decision_source": "",
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
                "decision_source": "",
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
                "decision_source": "",
            }
        _persist_status(artifacts, updated)
        _emit(
            updated,
            "run_terminal",
            f"run ended with {updated.get('status')}",
            status=updated.get("status"),
        )
        return updated
