# 09 — Auto 模式 + 用法说明

**What to build:** 提供 `--auto` 与/或环境变量，使设计冻结闸与合入闸自动批准；默认仍 interactive；库 API 可测；单次 `run` 可到 `completed`；日志决议来源为 `auto`；文档说明用法与风险。

**Blocked by:** 07 — Run 事件审计日志；08 — Implementer 真写码

**Status:** done

- [x] CLI `--auto` 与/或 `MACS_AUTO_APPROVE` 任一开启即 auto；默认 interactive
- [x] `run(..., auto_approve=False)`（或等价）可从库测通
- [x] auto 下单次 `run`（夹具仓检查通过）达 `completed`，无需中途 `resume`
- [x] 事件日志人闸决议来源为 `auto`
- [x] 文档说明 auto / 日志用法，并提示重要仓优先 interactive
