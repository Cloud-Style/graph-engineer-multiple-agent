# 领域文档

工程类 skill 在探索代码库时应如何阅读本仓库的领域文档。

## 探索之前先读这些

- 仓库根目录的 **`CONTEXT.md`**，或
- 若存在根目录 **`CONTEXT-MAP.md`** — 它指向每个上下文各自的 `CONTEXT.md`。读与当前主题相关的那些。
- **`docs/adr/`** — 读触及你即将改动区域的 ADR。多上下文仓库还要检查 `src/<context>/docs/adr/`。

若这些文件不存在，**静默继续**。不要把缺失当成错误；也不要上来就建议创建它们。`/domain-modeling` skill（经 `/grill-with-docs` 与 `/improve-codebase-architecture`）会在术语或决策真正落地时再懒创建。

## 文件结构

单上下文仓库（大多数仓库）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多上下文仓库（根目录存在 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 上下文级决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用词汇表里的用语

当你的输出命名某个领域概念（issue 标题、重构提案、假设、测试名），使用 `CONTEXT.md` 里定义的术语。不要滑向词汇表明确避免的同义词。

若需要的概念还不在词汇表里，这是一个信号——要么你在发明项目不用的说法（请重新考虑），要么存在真实缺口（记下来留给 `/domain-modeling`）。

## 标出 ADR 冲突

若你的输出与已有 ADR 矛盾，明确指出，而不是静默覆盖：

> _与 ADR-0007（event-sourced orders）冲突 — 但仍值得重开，因为…_
