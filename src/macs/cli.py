"""CLI entrypoints. Thin wrapper around the `run` / `resume` library seams."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from macs.run import resume, run


def _print_result(result: object) -> None:
    print(
        json.dumps(
            {
                "run_id": getattr(result, "run_id"),
                "status": getattr(result, "status"),
                "artifacts_dir": str(getattr(result, "artifacts_dir")),
                "waiting_for_human": getattr(result, "waiting_for_human"),
                "gate": getattr(result, "gate", None),
            },
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="macs", description="Multi-agent coding assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Start a run against a target repository")
    run_parser.add_argument("goal", help="Natural-language coding goal")
    run_parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Target repository path (default: current working directory)",
    )
    run_parser.add_argument(
        "--stub-graph",
        action="store_true",
        help="Use ticket-01 stub graph (immediate completed status)",
    )
    run_parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-approve design-freeze and merge gates (or set MACS_AUTO_APPROVE=1)",
    )

    resume_parser = sub.add_parser("resume", help="Resume a run paused at a human gate")
    resume_parser.add_argument("run_id", help="Run id under <repo>/runs/<run_id>")
    resume_parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Target repository path (default: current working directory)",
    )
    gate = resume_parser.add_mutually_exclusive_group(required=True)
    gate.add_argument("--approve", action="store_true")
    gate.add_argument("--reject", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "run":
        graph_runner = None
        if args.stub_graph:
            from macs.ports import StubGraphRunner

            graph_runner = StubGraphRunner()
        result = run(
            args.goal,
            repo_path=args.repo,
            graph_runner=graph_runner,
            auto_approve=True if args.auto else None,
        )
        _print_result(result)
        return 0
    if args.command == "resume":
        decision: Literal["approve", "reject"] = "approve" if args.approve else "reject"
        result = resume(args.run_id, decision=decision, repo_path=args.repo)
        _print_result(result)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
