# macs

Multi-agent coding assistant (graph-orchestrated). Local CLI / library `run` + `resume` seams.

## Install

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Usage

```bash
# Start a run (pauses at design-freeze gate)
macs run "add auth [modules: auth, api]" --repo /path/to/repo

# Approve design freeze → implement/review → pauses at merge gate
macs resume <run_id> --repo /path/to/repo --approve

# Approve merge gate → completed (does not auto-merge main)
macs resume <run_id> --repo /path/to/repo --approve

# Ticket-01 stub graph (immediate completed)
macs run "ping" --repo /path/to/repo --stub-graph
```

Goal cues for demos/tests:

- `[modules: a, b, c]` — planned modules (v1 fan-out cap = 2; extras truncated)
- `[conflict:api]` — force conflicting Login API shapes across modules
- `[check-owner: auth]` — contract API owner used when routing failed checks
- Repo optional `macs_check` script — reviewer exit code

Artifacts live under `<repo>/runs/<run-id>/`.
