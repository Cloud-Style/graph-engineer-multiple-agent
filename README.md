# macs

Multi-agent coding assistant (graph-orchestrated). Local CLI / library `run` + `resume` seams.

## Install

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## LLM configuration

Set env vars before `macs run` / `macs resume`:

| Variable | Required | Default |
|---|---|---|
| `API_KEY` | for real LLM | — (if unset, uses offline heuristic) |
| `BASE_URL` | no | `https://api.deepseek.com` |
| `MODEL` | no | `deepseek-chat` |

```bash
export API_KEY=sk-...
# optional:
# export BASE_URL=https://api.deepseek.com
# export MODEL=deepseek-chat

macs run "做个猜数字游戏" --repo ./test-project
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

Plain local folders work; git is auto-initialized when implementers need worktrees.

Goal cues for demos/tests (mainly for offline heuristic):

- `[modules: a, b, c]` — planned modules (v1 fan-out cap = 2; extras truncated)
- `[conflict:api]` — force conflicting Login API shapes across modules
- `[check-owner: auth]` — contract API owner used when routing failed checks
  (if that owner matches no implementer module, the run fails — no queue-first fallback)
- Repo optional `macs_check` script — reviewer exit code

Artifacts live under `<repo>/runs/<run-id>/`.
