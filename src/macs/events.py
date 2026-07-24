"""Append-only run event log for post-hoc audit."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_event(
    artifacts_dir: Path,
    *,
    run_id: str,
    event_type: str,
    summary: str,
    **fields: Any,
) -> None:
    """Append one JSON line to ``events.jsonl`` under the run artifacts dir."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "type": event_type,
        "summary": summary,
    }
    payload.update(fields)
    path = artifacts_dir / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
