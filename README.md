# macs

**实验性 / 学习向**的多 Agent 编码助手（图编排）。本地 CLI，对外接缝只有 `run` / `resume`。

> 这不是能替你写生产代码的工具。它是一份对照实现：用来理解多 Agent 编码协作会撞上什么问题、常见怎么处理。  
> **先读理论笔记，再对照代码与一次真实 run。**

## 学习入口（先看这里）

理论在 [`docs/learning/`](docs/learning/)：按「问题 → 方案 → 我们怎么做 → 代码在哪」组织。

建议从这几篇开始：

1. [为什么多 Agent 会失控](docs/learning/01-为什么多Agent会失控.md)
2. [通信](docs/learning/02-通信.md)
3. [图编排](docs/learning/03-图编排.md)
4. [冲突](docs/learning/04-冲突.md)

总目录与阅读顺序见 [docs/learning/README.md](docs/learning/README.md)。

## 它适合学什么

- **Graph Engineering**：固定组织角色（org graph）+ 本次任务规划（work graph）+ 显式执行拓扑，而不是多 Agent 自由群聊
- **可测试的 Agent 系统**：唯一对外接缝 + 可替换 `LlmPort`，整套测试离线、确定性、秒级跑完
- **人机协作闸门**：设计冻结与最终接受两道硬闸；`resume` 可暂停恢复；auto 只换批准者，不改状态机
- **确定性规则 + LLM**：冲突先程序检出，再 LLM 提案，高风险仍交人
- **混合隔离**：只读可共享，写必须进独立 git worktree

产品规格与拆票过程保留在 [`.scratch/multi-agent-coding-assistant/`](.scratch/multi-agent-coding-assistant/)（那是「做成什么」，不是理论主入口）。

## 它现在能做什么 / 不能做什么

| 能 | 不能（当前 v1） |
|---|---|
| 自然语言目标 → 拆模块 → 契约 → 并行模块设计 → 冲突报告 → 冻结设计 | 读懂并增量修改已有大型代码库 |
| 两道人闸暂停 / 恢复；可选 `--auto` | 多轮「改到测试全绿」的 agent loop |
| 隔离 worktree 里写真实 Python 源码（一跳 LLM） | 自动合并多任务分支进 main |
| Review 跑仓库可选 `macs_check` + 按 API owner 打回 | 深度 diff 审查或功能级重写 |
| `runs/<id>/` 产物 + `events.jsonl` 审计 | 丰富冲突本体（软语义不一致等大多检不出） |
| 模块扇出上限 2；无 `API_KEY` 时用离线 heuristic | 无限模块 / 自由改写组织图 |

## 安装

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## LLM 配置

| 环境变量 | 是否必需 | 默认值 |
|---|---|---|
| `API_KEY` | 使用真实 LLM 时需要 | —（未设置则用离线 heuristic） |
| `BASE_URL` | 否 | `https://api.deepseek.com` |
| `MODEL` | 否 | `deepseek-v4-pro` |
| `MACS_AUTO_APPROVE` | 否 | 未设置（交互式人闸） |

```bash
export API_KEY=sk-...
# 可选：BASE_URL / MODEL

macs run "做个猜数字游戏" --repo ./some-repo
```

## 用法

```bash
# 开始一次 run（停在设计冻结闸）
macs run "add auth [modules: auth, api]" --repo /path/to/repo

# 批准设计 → 实现/审查 → 停在合入闸
macs resume <run_id> --repo /path/to/repo --approve

# 批准合入闸 → completed（不会自动合入 main）
macs resume <run_id> --repo /path/to/repo --approve

# 演示 / CI：两道闸自动批准
macs run "ship [modules: app]" --repo /path/to/repo --auto
# 或：MACS_AUTO_APPROVE=1 macs run "..." --repo /path/to/repo

# Ticket-01 桩图（立刻 completed，仍会写 events.jsonl）
macs run "ping" --repo /path/to/repo --stub-graph
```

**注意：** `--auto` / `MACS_AUTO_APPROVE` 会跳过人对设计与合入的审查。重要仓库请用交互模式。

普通本地文件夹即可；实现阶段需要 worktree 时会自动 `git init`。设计冻结批准后，Implementer 会调 LLM 在隔离 worktree 里写真实 Python（不是占位 markdown）。

### 离线 heuristic 的 goal 提示（测试 / 演示）

- `[modules: a, b, c]` — 规划模块（上限 2；多余截断）
- `[conflict:api]` — 强制模块间 Login API shape 冲突
- `[check-owner: auth]` — 检查失败时用于路由的契约 API owner
  （没有匹配的实现任务模块 → 失败；不会 queue-first 回退）
- 仓库可选 `macs_check` 脚本 — Reviewer 用其退出码

产物目录：`<repo>/runs/<run-id>/`。审计日志：`events.jsonl`（阶段、人闸、`human`/`auto` 决议、写出文件、审查、终态）。

## 开发

```bash
uv pip install -e ".[dev]"
pytest
# 可选：mypy -p macs
```

仓库里还有实验性子项目 [llm-playground](llm-playground/)（本地 OpenAI 兼容聊天 UI）。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
