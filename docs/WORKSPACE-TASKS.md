# Reprise 0.8.0 · LOCAL CANDIDATE · 工作台任务 / Workspace tasks

仅本地候选，未公开发布。基础任务不需要 AI Key。“保存一稿”可以同时保存文件并尝试静态网页截图；两者分别报告结果，恢复另行执行。安装前提见 [快速开始](QUICKSTART.md)。

## 保存网页稿件与取回

1. 继续修改同一个工作文件夹，用顶部「保存一稿」命名一稿。普通非网页资料只保存文件，不要求选择截图策略；已有截图偏好继续沿用，可在项目设置更改。
2. 文件夹项目默认显示稿件画面列表；缺图明确显示，仍可选择版本、查看文件变化与全部文件。点变化文件看逐行增删与两侧行号，可跳到上一处或下一处变化，未变上下文按需展开。过大、二进制、读取不完整或结果截断时会说明限制，不冒充完整比较；需要全文时可取回文件。文件旁「恢复文件」直接取该版；被删除的文件从 A 恢复。
3. 在「比较版本」选择 A/B，明确需要哪一侧；「恢复 A 的文件」和「恢复 B 的文件」各自绑定其版本，完整文件不受预览截断影响。
4. 恢复默认建议原项目同级、位于 Reprise 数据目录之外的新文件夹，完整稿件可重新加入并继续留稿。上级目录不存在或不可写时展开「更改位置」，需填写尚不存在的新目录，不回退到数据目录。结果显示版本、范围、位置与实际校验口径；可打开所在位置或复制路径。返回会保留原版本、比较选择与文件上下文。
5. 「全部文件」可搜索未变化的文件。存储数字在「版本信息与存储」内展开；它们不是实际释放量。

## 网页项目

“保存一稿”默认尝试为入口明确、本地素材齐全的静态网页保存画面：先保存该版配置，再在独立副本里截图，只允许本机网络，不执行安装或构建命令。已有“无需截图”“自行提供”或“按已确认配置自动截图”偏好继续沿用。多个独立入口、远程素材、识别或截图失败等情况会提示进一步设置，文件版本仍已保存。截图只属于其绑定版本，缺图不借用别版。手工截图明确标为提供者指定归属。

项目设置的「版本内容的显示方式」可选自动、文件优先、预览优先。该选择只改变显示顺序，按浏览器与项目记住，不改变文件或运行授权。运行、采集和 AI 位于相关预览入口与高级设置。历史版本管理处理已保存历史；旧目录候选与成本是另一份报告。

## 已有 Git 项目

在「项目」的高级导入中选择「读取已有 Git 提交（只读）」。此入口继续显示真实 Git 提交与关系，不用文件夹留稿代替 Git 历史，也不把未提交修改当作历史版本。运行仍需保存该确切版本的配置；比较、预览与恢复不改写原仓库。

## English

1. Keep editing one working folder. **Save a draft** records a named draft. Ordinary non-web files need no screenshot choice. Existing screenshot preferences are reused and can be changed in Project settings.
2. Folder projects start with a visual draft list. Missing images stay visible as missing; file changes and all files remain available. Open a changed file for line additions and removals, both line numbers, and previous/next change navigation. Unchanged context expands on demand. Large, binary, or incomplete inputs and truncated results show their limits; recover a file to inspect it in full. Deleted files recover from A; recovery retrieves the complete selected file.
3. **Compare versions** binds A and B explicitly. Choose **Recover file from A/B**. The suggested destination is a new sibling of the source project, outside Reprise data; a full recovered draft can be added and edited as a project. If the parent is missing or unwritable, **Change location** opens for a new path, without falling back to the data directory. Existing outputs and the working folder are preserved.
4. The result states the version, scope, location and actual verification performed. Folder snapshots are read back; Git outputs report object-hash verification. **Show in folder** reveals only a completed recorded output. Return keeps the original comparison and file context.
5. **All files** includes unchanged files. **Version details and storage** expands optional facts. Byte counts do not claim physical space reclaimed.

**Save a draft** attempts static website capture by default, saving exact-version settings before capture in an independent copy. It allows local network access and runs no install or build commands. Existing no-screenshot, manual, or approved automatic preferences are respected. Ambiguous entries, remote assets, failed detection or capture require further setup while the files remain saved. Missing screenshots are never borrowed from another version. The portable macOS candidate includes the capture runtime. Source execution needs separately prepared Node, Playwright, and Chromium in addition to Python/Git.

Advanced import still offers **Read existing Git commits (read-only)**. It retains the Git history view and real relationships; uncommitted edits do not become historical revisions. Running requires saved settings for the exact revision. The per-project presentation preference changes display order without granting execution permission. Language switching preserves user titles, file contents, recovery destinations and the selected comparison pair.

Capacity and reuse retain the 0.7.4 contract: metadata preflight creates no full snapshots; an existing internal full recovery may be freshly checked and reused. First-time recovery copies still cost space. No automatic removal or publishing is part of these tasks.
