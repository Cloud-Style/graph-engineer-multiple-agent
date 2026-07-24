# 07 — Run 事件审计日志

**What to build:** 每次 `run`/`resume` 在该 run 产物目录追加可读事件日志；记录规划节点完成、进人闸、人闸决议与 run 终态等，便于事后审计「都干过啥」。接缝测试能断言关键事件类型存在。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `runs/<run-id>/` 下存在追加写入的事件日志文件（如 JSONL）
- [x] 日志条目含时间戳、run_id、事件类型、简短摘要
- [x] 至少记录：规划阶段节点完成、进入人闸、人闸决议、run 终态
- [x] 同一 run 内追加写入，不因中途 resume 清空历史
- [x] `run`/`resume` 接缝测试断言日志存在且含关键事件类型
