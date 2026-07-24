Status: ready-for-agent

# Spec 增量：真写码 Implementer + 可选全自动 + 可审计事件日志

> 本文件是对 `.scratch/multi-agent-coding-assistant/spec.md` 的增量，不废止原文。冲突时以本增量中「覆盖」条款为准；未提及处仍适用原文。

## Problem Statement

作为本地使用 macs 的开发者，我已经能跑通「规划 → 双人闸 → 多 worktree」编排，但 Implementer 只写占位 markdown，`completed` 并不等于做出可用代码。同时，每次都要人工过两道闸，不适合演示和回归；跑完后也难以审计「到底调用了谁、写了什么、闸门怎么过的」。我需要：实现阶段用真实 LLM 按冻结设计写源码；可选全自动跳过人闸；以及一份可读的事件日志便于事后审计。

## Solution

在保持既有 org/work graph 与 `run`/`resume` 接缝的前提下：

1. **Implementer** 在隔离 worktree 中调用可替换 LLM，根据 `frozen_design` / 任务上下文生成并提交**真实源码文件**（默认 Python），不再以 `macs_impl/*.md` 占位作为成功实现。
2. 提供 **auto 模式**（CLI 旗标与/或环境变量）：设计冻结闸与合入闸自动视为批准，使一次 `run`（或等价库调用）可在无人值守下跑到终态；默认仍为 interactive。
3. 每次 run 落盘 **事件日志**（append-only），按时间记录关键节点起止、人闸等待/决议、LLM 调用摘要、写出的文件路径、review/检查结果与错误，便于审计「都干过啥」。

测试仍只通过 `run`/`resume` 接缝断言外部行为（含 auto 与日志文件存在/关键事件），使用脚本化 LLM，不依赖真实网络模型。

## User Stories

1. 作为开发者，我想在批准设计后看到 worktree 里出现真实源码，以便确认系统真的在实现而不是写占位说明。
2. 作为开发者，我想 Implementer 按冻结设计与任务模块生成代码，以便实现与规划产物对齐。
3. 作为开发者，我想每个写任务仍在独立 worktree/分支中提交，以便并行实现不互相踩踏。
4. 作为开发者，我想默认仍停在两道人闸，以便方向错误或收工前我能介入。
5. 作为开发者，我想用 `--auto` 或环境变量一次跑完，以便演示和无人值守回归。
6. 作为开发者，我想 auto 模式下设计闸与合入闸都自动批准，以便不必多次 resume。
7. 作为开发者，我想 interactive 仍是默认，以免误开 auto 写出我不想要的代码。
8. 作为开发者，我想在 `runs/<run-id>/` 下看到事件日志文件，以便事后审计。
9. 作为开发者，我想日志记录 Orchestrator/Contracts/Designers/Reconciler 的完成，以便追溯规划阶段。
10. 作为开发者，我想日志记录进入/离开人闸及批准或驳回，以便知道谁（人或 auto）做了决定。
11. 作为开发者，我想日志记录 Implementer 写出的文件路径列表，以便核对落盘内容。
12. 作为开发者，我想日志记录 Reviewer 检查通过/失败及打回，以便诊断失败原因。
13. 作为开发者，我想日志带时间戳与 run_id，以便多 run 对照。
14. 作为开发者，我想日志追加写入、不因重规划无故清空历史（同一 run 内），以便审计完整。
15. 作为测试者，我想用脚本化 LLM 在接缝上验证「实现产出源码」，以便 CI 不调真实 API。
16. 作为测试者，我想用 auto 模式在接缝上一次跑到 completed，以便无人值守验收。
17. 作为测试者，我想断言日志中出现关键事件类型，以便锁住审计契约。
18. 作为开发者，我想真实 LLM 仍通过 `API_KEY`/`BASE_URL`/`MODEL` 配置，以便与现有规划阶段共用同一套密钥。
19. 作为开发者，我想 Implementer 在无可用代码响应时显式失败或留下可诊断错误，而不是假装成功写占位 md。
20. 作为开发者，我想 Reviewer 至少能感知实现目录中出现了源码文件，以便「有实现」可被检查（最小程度）。
21. 作为开发者，我想保留 stub-graph 调试路径，以便不跑全图时仍可测壳。
22. 作为开发者，我想 auto 驳回不适用（auto 只自动批准），拒绝仍留给 interactive。
23. 作为开发者，我想终态后再 resume 不重跑规划，以便审计日志与产物不被覆盖（已有行为，本增量须保持）。
24. 作为开发者，我想日志对人可读（如 JSONL 或带时间戳的文本行），以便不写专用工具也能打开看。
25. 作为运维，我想文档说明 auto 与日志的用法与风险，以便知道何时该用 interactive。

## Implementation Decisions

- **增量范围**：改动集中在 Implementer 行为、人闸自动批准策略、run 级事件日志；不改变六类 org 角色与双闸语义（auto 只是自动投批准票）。
- **对外接缝不变**：唯一验收接缝仍为 `run` / `resume`（含 CLI）。
- **Implementer**：
  - 对每个实现任务，向 `LlmPort` 请求「按冻结设计生成该模块源码」；期望响应为可解析结构（例如文件路径 → 文件内容的映射，或明确约定的 JSON）。
  - 将文件写入该任务的隔离 worktree 并提交；路径应落在模块相关源码位置（约定以 Python 为主，如包内模块文件），**禁止**把「仅有占位 markdown」当作成功实现。
  - 脚本化/测试 LLM 可返回固定小文件内容；生产路径使用与规划相同的 `llm_from_env()`。
  - LLM 失败或响应无法解析时：任务失败并写入日志与状态错误，不得静默回退到旧占位 md 并宣称成功。
- **Auto 模式**：
  - 开启方式：CLI `--auto` 与/或环境变量（如 `MACS_AUTO_APPROVE=1`）；两者任一开启即 auto。
  - 行为：到达 `design_freeze` / `merge` 时自动注入批准并继续，直到 `completed`、`rejected_*`（仅人工驳回路径）、或失败终态。
  - 默认 interactive：无旗标/无环境变量时保持两道人闸。
  - 库 API：`run(..., auto_approve: bool = False)`（或等价参数）需可测。
- **事件日志**：
  - 每个 run 一份追加日志，位于该 run 产物目录下（如 `events.jsonl`）。
  - 每条事件至少含：时间戳、run_id、事件类型、简短摘要；按需含模块/任务 id、文件路径列表、闸门名、决议来源（`human`|`auto`）、错误信息。
  - 关键事件类型（可扩展，名称稳定即可）：规划阶段节点完成、进入人闸、人闸决议、实现写出文件、review 结果、run 终态。
  - 日志面向人与简单工具可读；不要求单独查询 UI。
- **与既有决策的关系**：产物仍以 `runs/<run-id>/` 为准；完成定义在 auto 下仍为「PR 草稿 + 检查通过 + Reviewer 未阻断 +（自动）合入闸批准」；仍不自动合入 main。
- **保持**：终态 resume 不得重跑 Orchestrator；检查失败仍按契约 API owner 打回，不得 queue-first 静默回退。

## Testing Decisions

- 好测试只断言 `run`/`resume` 外部行为与产物，不断言 prompt 文本或私有辅助函数。
- 接缝仍唯一：`run` / `resume`。
- 新增/强化用例（脚本化 LLM，不联网）：
  - interactive：过设计闸后 worktree 中存在约定扩展名的源码文件，且内容匹配脚本化 LLM 提供的固定片段。
  - `--auto` 或等价参数：单次 `run` 即达 `completed`（夹具仓检查通过），且无需中途 `resume`。
  - 事件日志存在，并包含人闸决议（`auto` 或 `human`）与至少一次「写出文件」类事件。
  - 实现 LLM 返回无效载荷时，run 不以「仅占位 md」成功完成。
- 先例：现有 `tests/test_run_seam.py`、`tests/test_openai_llm.py` 的接缝/端口风格。

## Out of Scope

- IDE/GitHub 托管触发、自动合入 main、自由多 Agent 群聊。
- 完整 agent loop 工具链（搜索全仓、反复跑测试直到绿）——本增量只需「按设计生成并提交源码」的一跳实现；多轮修到绿可另开票。
- 事件日志的远程采集、ELK、专用审计 UI。
- 扩展冲突检测本体（实体同名异义、跨设计命名对齐等）——可另票；本增量不阻塞。
- 保证真实模型生成代码一次可运行或架构优美；接缝用脚本化 LLM 锁行为，模型质量不在验收范围。

## Further Notes

- 词汇沿用既有：org graph、work graph、冻结设计、人闸、run 产物、混合隔离、PR 草稿；本增量新增：**auto 模式**、**事件日志（审计）**、**真写码 Implementer**。
- 风险：auto + 弱 `macs_check` 时等于弱验收；文档须提示生产/重要仓库优先 interactive。
- 建议实现顺序：事件日志埋点 → Implementer 真写码（脚本化 LLM 接缝先绿）→ auto 批准旁路 → README。
- 发布位置：`.scratch/multi-agent-coding-assistant/spec-llm-implementer-auto-audit.md`；后续 `/to-tickets` 可拆为实现票。
