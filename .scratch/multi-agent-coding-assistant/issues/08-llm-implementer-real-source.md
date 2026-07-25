# 08 — Implementer 真写码（LLM → 源码）

**What to build:** 设计冻结闸通过后，Implementer 按冻结设计调用 LLM，在隔离 worktree 写出并提交真实源码（非占位 markdown）；无效响应显式失败；写出文件路径进入事件日志。接缝用脚本化 LLM 验证 worktree 源码内容。

**Blocked by:** 07 — Run 事件审计日志

Status: done

- [x] Implementer 产出约定扩展名的源码文件并提交到任务 worktree，不以仅有占位 md 为成功
- [x] 脚本化 LLM 接缝测试：过设计闸后 worktree 源码内容匹配固定片段
- [x] LLM 失败或不可解析时任务失败，不得静默回退占位 md 并宣称成功
- [x] 事件日志含「写出文件」类事件及路径列表
- [x] Reviewer 最小可感知「有源码实现」（或检查仍能通过夹具路径）
