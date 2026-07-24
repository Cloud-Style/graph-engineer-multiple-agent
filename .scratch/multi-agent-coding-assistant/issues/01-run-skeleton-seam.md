# 01 — `run` 骨架与接缝测试

**What to build:** 开发者能对目标仓库调用 `run`（CLI 与库同一行为），得到 `runs/<run-id>/` 目录和结构化 `RunResult`；LLM/工具端口可替换。用夹具仓 + 全桩节点跑通唯一对外接缝测试，证明编排壳可测，哪怕角色逻辑尚未实现。

**Blocked by:** None — can start immediately.

Status: done

- [x] 提供库入口 `run` 与薄 CLI 包装，默认目标仓为当前工作目录（可指定路径）
- [x] 每次调用生成唯一 `run-id`，并在 `runs/<run-id>/` 落下可检查的最小产物/状态痕迹
- [x] `RunResult` 至少暴露：run-id、状态、产物位置、是否在等人闸
- [x] LLM/工具端口可替换；接缝测试使用夹具仓与桩实现，不发起真实模型网络调用
- [x] 至少一条通过 `run` 接缝的自动化测试证明「调用 → 产物/结果」端到端成立
