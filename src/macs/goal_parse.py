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


def wants_missing_owner(goal: str) -> bool:
    return "[missing-owner]" in goal.lower()


def wants_escalate_conflict(goal: str) -> bool:
    return "[escalate:conflict]" in goal.lower()


def check_owner_from_goal(goal: str) -> str | None:
    """Optional ``[check-owner: module]`` — contract API owner for check routing."""
    match = re.search(r"\[check-owner:\s*([^\]]+)\]", goal, flags=re.IGNORECASE)
    if not match:
        return None
    owner = match.group(1).strip()
    return owner or None
