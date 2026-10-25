# 工作台任务 / Workbench tasks

Reprise 0.8.0。[快速开始](QUICKSTART.md) · [功能范围](FEATURES.md)

## 保存与继续修改

1. 复用当前明确的网页目录。首次为文件夹项目留稿时，询问一次以后是否保存画面，并在截图或配置完成前记住答案。之后沿用；可在设置更改。
2. 用「保存一稿」或 Ctrl/⌘ + S 留稿；名称可留空按时间补齐。Ctrl/⌘ + Shift + S 打开命名保存，Ctrl/⌘ + Enter 提交。Agent 可按“本轮修改前后都留稿”的委托编排两次调用，不启动后台监控。
3. 分别检查文件与画面结果。失败保留已保存文件、项目选择和日志；补齐配置后给同一准确版本重试画面，不创建重复稿。
4. 按画面选稿或比较任意两版。点「取出这一稿」，默认使用源目录同级的新文件夹。整稿完成回执提供可复制的继续修改指令；让编辑 Agent 先核对副本，再继续修改。

文件未变化时沿用旧稿及原名称。局部文件恢复和 ZIP 导出不声称已得到完整可运行网页。

## 版本图片与 Git 路线

「画面」与「版本关系」是同一批准确版本的两种浏览方式。切换保留选中稿件和定位；缺图明确显示，不借用别版图片。图片放大、收藏、搜索、固定紧凑的关系图与中英文切换保留上下文。

已有 Git 项目可由 Agent 用 `open /known/repository --lang zh --no-browser` 打开，也可在项目导入中选择只读 Git。图中的节点来自完整提交 SHA，每条父边和合并父序来自 Git。筛选仍保留关系上下文；线条交叉本身不表示合并。[图规则与边界](GIT-GRAPH.md)

Git 历史项目使用已有提交；文件夹留稿保存当前文件。截图长期偏好与 `snapshot` 只用于文件夹项目，不应用到 Git 历史项目。Reprise 不替用户执行提交、checkout 或 reset。

## 文件比较与按需管理

在「比较版本」选择 A/B，可交换方向；变化文件提供两侧行号、增删和恢复入口。被删除文件从 A 恢复。大文件、二进制、截断或未完整读取时说明限制，恢复仍按所选版本取完整文件。新恢复目录不得覆盖源或已有输出。

设置保留任务与预览服务，以及折叠的高级管理：历史版本、独立备份迁移、旧副本导入、环境、存储和完整性。删除历史和释放环境都需具体影响预览与明确确认；不会自动删除源文件。源码运行命令先核对并保存，随后只在独立副本执行。

## English

Save the known folder before and after the requested edit. Ask once whether future saves should include pictures; persist the answer before capture/setup completes. Later saves reuse it. Blank names use the time; unchanged files retain their existing draft/title. Files and pictures have separate outcomes.

Use **Pictures** or **Revision relationships** to inspect exact versions. Switching keeps the selected draft in view. Images can be enlarged; search, bookmarks, the fixed compact relationship view and language changes keep context. Missing images are never borrowed.

Open existing Git history with `open /known/repository --lang en --no-browser`. Nodes and ordered parents come from real commits. Folder snapshots and their capture preferences remain a separate project kind. Imported source repositories stay read-only.

Compare A/B, recover complete drafts or selected files into a new folder, and inspect the actual verification result. Whole-draft recovery provides continuation instructions with the real path and full version. Partial recovery and ZIP exports do not imply a runnable webpage.

Advanced management retains saved-version impact/review, backup/migration, old-copy imports, runtime environments, storage and integrity. Deletion/release uses explicit confirmation. Approved project commands execute in separate copies. General expansion remains frozen.
