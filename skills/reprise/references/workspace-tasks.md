# Reprise 工作台任务 / Workspace tasks

本文件对应 Reprise 0.8.0 的源码 Skill；直接/快捷键留稿、继续修改指令与已有 Git 图谱均保留。

## 主流程

1. Agent 按 [环境说明](environment.md) 完成已获授权的接入，打开工作台。只打开不保存、不导入当前目录。
2. 复用当前明确的网页项目。用户可说“本轮修改前后都帮我留稿”，委托当前 Agent 在这两个节点调用既有保存能力；不启动后台监控。
3. 首次保存说明范围，名称可以留空按时间补齐。静态网页可尝试直接出图；其他项目先审阅运行计划。文件与画面分别报告。
4. 首次只问一次这个项目以后是否需要画面，并在配置或截图完成前持久化答案。失败不重置答案，之后持续沿用。已有明确偏好的项目可点击「保存一稿」或 Ctrl/⌘ + S 直接留稿；命名保存用 Ctrl/⌘ + Shift + S，名称框提交用 Ctrl/⌘ + Enter。
5. 在画廊按画面、名称和时间选稿，需要时比较。取回整稿或所选文件到新目录，并核对实际回执。
6. 整稿结果提供「复制给 Agent 继续修改」；指令包含实际新目录和完整版本。粘贴给编辑 Agent 后，先核对副本，再按用户下一条要求修改。部分文件和 ZIP 导出不作为完整网页继续入口。

## 已有 Git 历史与版本图

用户要查看已有分叉与合并时，用 `open /known/repository --lang zh --no-browser` 打开 Git 项目，不替用户创建提交。工作台的「版本关系」保留真实 Git 节点与有序父边；「画面」显示这些版本各自已有的截图。筛选、收藏、紧凑关系图和选中只改变浏览状态，不改历史。缺图时明确显示缺失，按需核对运行配置并采集所选准确版本。

`preview-preferences`、`snapshot` 和首次保存画面的长期偏好用于普通文件夹项目，不用于 Git 历史项目。同一个源目录可分别查看 Git 历史与保存当前文件稿；两者的版本身份独立，不能把文件夹保存顺序说成源 Git 分叉。

For existing Git branches and merges, open the repository path. Keep its picture and relationship views, exact-SHA media, ordered parents and read-only source. Folder checkpoints and their screenshot preferences are a separate project kind; do not call folder-only commands on a Git-history project.

## 有需要再管理

设置中可修改保存与画面偏好；任务和预览服务按需展开。高级管理保留历史版本、备份迁移、旧副本导入、运行环境、存储占用、完整性和显示方式。原 Git 只读、媒体精确版本、独立副本、明确命令批准、删除/释放确认等边界继续适用。[高级参考](advanced-workflows-0.8.md) · [旧副本导入](folder-imports.md)

通用功能扩展冻结。本阶段只优化当前保存、画面、取回与继续修改的实际阻塞，不新增云同步、全盘清理、后台快照或另一套 AI 设置。

## English

Use the known local project. An explicit request to save with pictures before and after this edit authorizes those two checkpoints in this task, not background recording. First use explains scope; blank names use the time. Only a persisted first answer enables later reuse of explicitly confirmed settings. Direct/keyboard saving follows that preference and reports file/image outcomes separately.

Choose a version by its own image, compare when useful, then recover a new copy. Whole-draft results provide copyable instructions containing the actual folder and exact version. Paste them into the editing agent and verify the copy before the next requested edit. Partial-file recovery and ZIP export do not claim a complete editable webpage. General expansion is frozen; advanced tools remain available on demand.

<details>
<summary>历史工作台说明 / Historical workspace reference</summary>

# Reprise 0.8.0 · LOCAL CANDIDATE · 工作台任务 / Workspace tasks

仅本地候选，未公开发布。基础任务不需要 AI Key。保存、恢复和预览是分别执行的动作。

## 普通资料

1. 继续修改同一个工作文件夹，用顶部「保存版本」命名一稿。截图偏好选过后不再重复展示；可在项目设置更改四种偏好。
2. 选择版本，默认先看「文件变化」。点文件名看 A/B 完整文本（每侧最多 64 KB），文件旁「恢复文件」直接取该版；被删除的文件从 A 恢复。
3. 在「比较版本」选择 A/B，明确需要哪一侧；「恢复 A 的文件」和「恢复 B 的文件」各自绑定其版本，完整文件不受预览截断影响。
4. 填尚不存在的新目录。结果显示版本、范围、位置与实际校验口径；可打开所在位置或复制路径。返回会保留原版本、比较选择与文件上下文。
5. 「全部文件」可搜索未变化的文件。存储数字在「版本信息与存储」内展开；它们不是实际释放量。

## 网页项目

识别到网页入口、已有运行配置或该版本的真实视觉素材时，会突出预览。运行仍需要保存过的配置，使用独立副本；保存文件本身不会运行项目。截图只属于其绑定版本，缺图不借用别版。手工截图明确标为提供者指定归属。

项目设置的「版本内容的显示方式」可选自动、文件优先、预览优先。该选择只改变显示顺序，按浏览器与项目记住，不改变文件或运行授权。运行、采集和 AI 位于相关预览入口与高级设置。历史版本管理处理已保存历史；旧目录候选与成本是另一份报告。

## English

1. Keep editing one working folder. **Save version** records a named draft. A remembered screenshot preference is reused; change it in Project settings.
2. Ordinary documents start with **File changes**. Open a file for A/B text, or use its recovery button. Deleted files recover from A. Text display is limited to 64 KB per side; recovery retrieves the complete selected file.
3. **Compare versions** binds A and B explicitly. Choose **Recover file from A/B**, then enter a new destination. Existing outputs and the working folder are preserved.
4. The result states the version, scope, location and actual verification performed. Folder snapshots are read back; Git outputs report object-hash verification. **Show in folder** reveals only a completed recorded output. Return keeps the original comparison and file context.
5. **All files** includes unchanged files. **Version details and storage** expands optional facts. Byte counts do not claim physical space reclaimed.

Website previews use detected entry points, saved recipes or exact-version evidence, with an explicit per-project presentation override. Running requires an approved recipe and an independent copy. Missing screenshots are never borrowed from another version. Language switching preserves user titles, file contents, recovery destinations and the selected comparison pair.

Capacity and reuse retain the 0.7.4 contract: metadata preflight creates no full snapshots; an existing internal full recovery may be freshly checked and reused. First-time recovery copies still cost space. No automatic removal or publishing is part of these tasks.

</details>
