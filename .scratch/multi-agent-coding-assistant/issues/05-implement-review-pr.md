# 05 — 实现 worktree + Review + PR 草稿

**What to build:** 人闸通过后，`run` 按任务扇出 Implementer：每个写任务使用隔离 git worktree/分支进行改动；Reviewer 审查 diff、跑夹具仓约定检查，失败则打回责任任务而非整体糊弄重写；最终落下 PR 草稿（或等价可审 diff 包）与元数据。混合隔离（只读可共享、写必隔离）生效。接缝测试覆盖快乐路径与检查失败路径。

**Blocked by:** 04 — 设计冻结人闸（暂停/恢复）

**Status:** ready-for-agent

- [ ] 每个写任务使用隔离 worktree/分支；Implementer 不互相改对方分支
- [ ] 只读探索可共享上下文，但不破坏写隔离约定
- [ ] Reviewer 执行约定检查；失败路由回责任实现任务；Reviewer 不做功能级大重写
- [ ] 产出 PR 草稿或等价可审 diff 包及元数据到 run 目录
- [ ] `run` 接缝测试覆盖：检查通过得到 PR 草稿；检查失败则未达成功完成态
