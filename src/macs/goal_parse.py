"""Parse test/demo cues from a natural-language goal."""

from __future__ import annotations

import re


def modules_from_goal(goal: str) -> list[str]:
    """Extract module names from ``[modules: a, b]`` or default to ``app``."""
    match = re.search(r"\[modules:\s*([^\]]+)\]", goal, flags=re.IGNORECASE)
    if not match:
        return ["app"]
    parts = [p.strip() for p in match.group(1).split(",") if p.strip()]
    return parts or ["app"]


def wants_api_conflict(goal: str) -> bool:
    return "[conflict:api]" in goal.lower()


def wants_failing_checks(goal: str) -> bool:
    return "[fail-checks]" in goal.lower()
