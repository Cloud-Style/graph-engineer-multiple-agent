"""CLI entrypoints. Thin wrapper around the `run` library seam."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from macs.run import run


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

    args = parser.parse_args(argv)
    if args.command == "run":
        result = run(args.goal, repo_path=args.repo)
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "artifacts_dir": str(result.artifacts_dir),
                    "waiting_for_human": result.waiting_for_human,
                },
                ensure_ascii=False,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
