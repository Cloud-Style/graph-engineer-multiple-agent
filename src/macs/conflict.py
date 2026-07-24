"""Deterministic conflict detection across module designs."""

from __future__ import annotations

from typing import Any


def detect_conflicts(designs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conflict records for incompatible structured fields.

    Detects:
    - same API ``name`` with differing ``shape`` (同名异义)
    - opposing dependency edges (双向依赖)
    - APIs whose ``owner`` is missing from the design module set (缺 owner)
    """
    modules = {str(d.get("module", "")) for d in designs if d.get("module")}
    conflicts: list[dict[str, Any]] = []

    by_api: dict[str, list[tuple[str, str]]] = {}
    for design in designs:
        module = str(design.get("module", ""))
        for api in design.get("apis", []):
            if not isinstance(api, dict):
                continue
            name = str(api.get("name", ""))
            shape = str(api.get("shape", ""))
            owner = str(api.get("owner") or module)
            if name and owner and owner not in modules:
                conflicts.append(
                    {
                        "field": "apis",
                        "name": name,
                        "modules": [module],
                        "detail": f"API {name!r} owner {owner!r} is not among modules {sorted(modules)}",
                    }
                )
            if not name:
                continue
            by_api.setdefault(name, []).append((module, shape))

    for name, entries in by_api.items():
        shapes = {shape for _, shape in entries}
        if len(shapes) <= 1:
            continue
        mods = sorted({module for module, _ in entries})
        conflicts.append(
            {
                "field": "apis",
                "name": name,
                "modules": mods,
                "detail": f"API {name!r} has conflicting shapes: {sorted(shapes)}",
            }
        )

    edges: set[tuple[str, str]] = set()
    for design in designs:
        module = str(design.get("module", ""))
        for dep in design.get("dependency_direction", []):
            if not isinstance(dep, dict):
                continue
            src = str(dep.get("from") or module)
            dst = str(dep.get("to") or "")
            if not src or not dst:
                continue
            edges.add((src, dst))
            if (dst, src) in edges:
                conflicts.append(
                    {
                        "field": "dependency_direction",
                        "name": f"{src}<->{dst}",
                        "modules": sorted({src, dst}),
                        "detail": f"bidirectional dependency between {src!r} and {dst!r}",
                    }
                )
    return conflicts
