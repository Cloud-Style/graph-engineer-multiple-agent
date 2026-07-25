# 问题跟踪：本地 Markdown

本仓库的 issues 与规格（你可能叫它 PRD）以 markdown 文件形式放在 `.scratch/` 下。

## 约定

- 一个功能一个目录：`.scratch/<feature-slug>/`
- 规格文件是 `.scratch/<feature-slug>/spec.md`
- 实现票据是每个票一个文件：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 编号——不要写成单个合并大票文件
- 分诊状态写在每个 issue 文件顶部附近的 `Status:` 行（角色字符串见 `triage-labels.md`）
- 评论与对话历史追加在文件底部的 `## Comments` 标题下

## 当 skill 说「发布到 issue tracker」时

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在则创建）。

## 当 skill 说「拉取相关票据」时

读取引用路径上的文件。用户通常会直接给出路径或 issue 编号。

## Wayfinding 操作

供 `/wayfinder` 使用。**map** 是一份文件，每个票对应一个 **child** 文件。

- **Map**：`.scratch/<effort>/map.md` — Notes / Decisions-so-far / Fog 正文。
- **Child ticket**：`.scratch/<effort>/issues/NN-<slug>.md`，从 `01` 编号，问题写在正文。`Type:` 行记录票类型（`research` / `prototype` / `grilling` / `task`）；`Status:` 行记录 `claimed` / `resolved`。
- **Blocking**：顶部附近的 `Blocked by: NN, NN` 行。列出的文件全部为 `resolved` 时，该票才算解锁。
- **Frontier**：扫描 `.scratch/<effort>/issues/`，找开放、未阻塞、未认领的文件；按编号最先者优先。
- **Claim**：开始工作前把 `Status:` 设为 `claimed` 并保存。
- **Resolve**：在 `## Answer` 下追加答案，把 `Status:` 设为 `resolved`，再把上下文指针（摘要 + 链接）追加到 `map.md` 的 Decisions-so-far。
