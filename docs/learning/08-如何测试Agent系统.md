# 08 — 如何测试 Agent 系统（骨架）

## 要回答的问题

为什么多数 Agent demo 很难写测试？应该测 prompt 文笔，还是测系统外部行为？

## 计划覆盖

- 唯一接缝：`run` / `resume`
- `LlmPort` 可替换与离线 heuristic
- 好测试断言产物与状态，不断言私有实现细节

## 对照代码（写正文时展开）

- `tests/test_run_seam.py`
- `src/macs/ports.py`、`src/macs/heuristic_llm.py`

状态：骨架。
