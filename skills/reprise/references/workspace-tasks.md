# Reprise 工作台任务 / Workspace tasks

本文件对应 Reprise 0.8.3 的源码 Skill；直接/快捷键留稿、继续修改指令与已有 Git 图谱均保留。

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
