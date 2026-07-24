"""Shared constants for v1 macs runs."""

from __future__ import annotations

MAX_MODULE_FANOUT = 2
MAX_REVIEW_REROUTES = 1

GATE_DESIGN_FREEZE = "design_freeze"
GATE_MERGE = "merge"

STATUS_COMPLETED = "completed"
STATUS_WAITING = "waiting_for_human"
STATUS_RUNNING = "running"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"
