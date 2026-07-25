# macs

**实验性 / 学习向**的多 Agent 编码助手（图编排）。本地 CLI，对外接缝只有 `run` / `resume`。

> 这不是能替你写生产代码的工具。它是一份约 2500 行的参考实现，用来理解：多 Agent 编码系统该怎么分角色、怎么传信息、怎么存状态、怎么解冲突、怎么做人闸。

## 它适合学什么

- **Graph Engineering**：固定组织角色（org graph）+ 本次任务规划（work graph）+ 显式执行拓扑，而不是多 Agent 自由群聊
- **可测试的 Agent 系统**：唯一对外接缝 + 可替换 `LlmPort`，整套测试离线、确定性、秒级跑完
- **人机协作闸门**：设计冻结与最终接受两道硬闸；`resume` 可暂停恢复；auto 只换批准者，不改状态机
- **确定性规则 + LLM**：冲突先程序检出，再 LLM 提案，高风险仍交人
- **混合隔离**：只读可共享，写必须进独立 git worktree

需求 → 拆票 → 实现 → 审查 的过程保留在 [`.scratch/multi-agent-coding-assistant/`](.scratch/multi-agent-coding-assistant/)。

## 它现在能做什么 / 不能做什么

| 能 | 不能（当前 v1） |
|---|---|
| 自然语言目标 → 拆模块 → 契约 → 并行模块设计 → 冲突报告 → 冻结设计 | 读懂并增量修改已有大型代码库 |
| 两道人闸暂停 / 恢复；可选 `--auto` | 多轮「改到测试全绿」的 agent loop |
| 隔离 worktree 里写真实 Python 源码（一跳 LLM） | 自动合并多任务分支进 main |
| Review 跑仓库可选 `macs_check` + 按 API owner 打回 | 深度 diff 审查或功能级重写 |
| `runs/<id>/` 产物 + `events.jsonl` 审计 | 丰富冲突本体（软语义不一致等大多检不出） |
| 模块扇出上限 2；无 `API_KEY` 时用离线 heuristic | 无限模块 / 自由改写组织图 |

## Install

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## LLM configuration

| Variable | Required | Default |
|---|---|---|
| `API_KEY` | for real LLM | — (unset → offline heuristic) |
| `BASE_URL` | no | `https://api.deepseek.com` |
| `MODEL` | no | `deepseek-chat` |
| `MACS_AUTO_APPROVE` | no | unset (interactive gates) |

```bash
export API_KEY=sk-...
# optional: BASE_URL / MODEL

macs run "做个猜数字游戏" --repo ./some-repo
```

## Usage

```bash
# Start (pauses at design-freeze gate)
macs run "add auth [modules: auth, api]" --repo /path/to/repo

# Approve design → implement/review → pauses at merge gate
macs resume <run_id> --repo /path/to/repo --approve

# Approve merge → completed (does NOT auto-merge main)
macs resume <run_id> --repo /path/to/repo --approve

# Demo / CI only: auto-approve both gates
macs run "ship [modules: app]" --repo /path/to/repo --auto
# or: MACS_AUTO_APPROVE=1 macs run "..." --repo /path/to/repo

# Ticket-01 stub graph (immediate completed, still writes events.jsonl)
macs run "ping" --repo /path/to/repo --stub-graph
```

**Caution:** `--auto` / `MACS_AUTO_APPROVE` skips human review of design and merge. Prefer interactive mode for anything you care about.

Plain folders work; git is auto-initialized when implementers need worktrees. After design freeze, Implementers call the LLM to write real Python into isolated worktrees (not placeholder markdown).

### Offline heuristic goal cues (tests / demos)

- `[modules: a, b, c]` — planned modules (cap = 2; extras truncated)
- `[conflict:api]` — force conflicting Login API shapes across modules
- `[check-owner: auth]` — contract API owner for failed-check routing
  (no matching implementer module → fail; no queue-first fallback)
- Repo optional `macs_check` — reviewer exit code

Artifacts: `<repo>/runs/<run-id>/`. Audit trail: `events.jsonl` (phases, gates, `human`/`auto` decisions, files written, review, terminal status).

## Development

```bash
uv pip install -e ".[dev]"
pytest
# optional: mypy -p macs
```

## License

MIT — see [LICENSE](LICENSE).
