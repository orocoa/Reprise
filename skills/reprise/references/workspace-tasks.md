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
