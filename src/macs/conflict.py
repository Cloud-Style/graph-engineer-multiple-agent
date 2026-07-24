"""Deterministic conflict detection across module designs."""

from __future__ import annotations

from typing import Any


def detect_conflicts(designs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conflict records for incompatible structured fields.

    Currently detects same API ``name`` with differing ``shape`` across modules.
    """
    by_api: dict[str, list[tuple[str, str]]] = {}
    for design in designs:
        module = str(design.get("module", ""))
        for api in design.get("apis", []):
            if not isinstance(api, dict):
                continue
            name = str(api.get("name", ""))
            shape = str(api.get("shape", ""))
            if not name:
                continue
            by_api.setdefault(name, []).append((module, shape))

    conflicts: list[dict[str, Any]] = []
    for name, entries in by_api.items():
        shapes = {shape for _, shape in entries}
        if len(shapes) <= 1:
            continue
        modules = sorted({module for module, _ in entries})
        conflicts.append(
            {
                "field": "apis",
                "name": name,
                "modules": modules,
                "detail": f"API {name!r} has conflicting shapes: {sorted(shapes)}",
            }
        )
    return conflicts
