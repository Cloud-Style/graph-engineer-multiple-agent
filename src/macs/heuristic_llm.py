"""Heuristic LLM port — no network; emits structured JSON by STAGE tag."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from macs.goal_parse import modules_from_goal, wants_api_conflict


def _goal_from_prompt(prompt: str) -> str:
    match = re.search(r"^GOAL=(.*)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else prompt


@dataclass
class HeuristicLlmPort:
    """Default offline LLM: stage-tagged prompts → structured planning JSON."""

    calls: int = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        goal = _goal_from_prompt(prompt)
        if "STAGE=orchestrator" in prompt:
            modules = modules_from_goal(goal)
            return json.dumps(
                {
                    "modules": modules,
                    "steps": [
                        "contracts",
                        "module_designers",
                        "reconciler",
                        "implementers",
                        "reviewer",
                    ],
                }
            )
        if "STAGE=contracts" in prompt:
            modules = modules_from_goal(goal)
            apis = [{"name": "Login", "owner": modules[0], "shape": "POST /login"}]
            return json.dumps(
                {
                    "boundaries": [f"module:{m}" for m in modules],
                    "apis": apis,
                    "entities": [{"name": "User", "fields": ["id", "email"]}],
                    "errors": [{"code": "AUTH_DENIED"}],
                    "dependency_direction": [],
                    "non_goals": ["rewrite unrelated packages"],
                    "modules": modules,
                }
            )
        if "STAGE=module_design" in prompt:
            match = re.search(r"^MODULE=(.*)$", prompt, flags=re.MULTILINE)
            module = match.group(1).strip() if match else "app"
            shape = "POST /login"
            if wants_api_conflict(goal) and module != modules_from_goal(goal)[0]:
                shape = "POST /signin"
            return json.dumps(
                {
                    "module": module,
                    "apis": [{"name": "Login", "shape": shape}],
                    "entities": [{"name": "User", "fields": ["id", "email"]}],
                    "errors": [{"code": "AUTH_DENIED"}],
                    "dependency_direction": [],
                }
            )
        if "STAGE=reconcile" in prompt:
            if "[escalate:conflict]" in goal.lower():
                return json.dumps(
                    {
                        "resolved": False,
                        "apis": [],
                        "notes": "unresolved — escalate to human",
                    }
                )
            return json.dumps(
                {
                    "resolved": True,
                    "apis": [{"name": "Login", "shape": "POST /login"}],
                    "notes": "Prefer canonical POST /login",
                }
            )
        return "{}"
