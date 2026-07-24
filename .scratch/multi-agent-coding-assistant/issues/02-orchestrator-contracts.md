# 02 — 编排 + 契约垂直切片

**What to build:** 开发者输入自然语言目标后，`run` 会经由 Orchestrator 写出本次 work graph 摘要，并由 Contracts 产出带结构化字段的薄共享契约（边界、接口、实体、错误语义、非目标），全部落在该次 `runs/<run-id>/` 下；可用桩 LLM 通过接缝测试验证。

**Blocked by:** 01 — `run` 骨架与接缝测试

Status: done

- [x] Orchestrator 根据目标生成并落盘本次 work graph 摘要（含计划的模块/步骤与扇出上限意识）
- [x] Contracts 产出薄契约产物，含约定的结构化字段与非目标
- [x] Orchestrator 不撰写大段模块设计或生产代码；职责边界在产物上可分辨
- [x] 通过 `run` 接缝测试（桩 LLM）断言 work graph 摘要与契约文件存在且字段可被后续步骤消费
