# Version operations / 版本操作

Reprise separates reading a version from running it, viewing its saved picture,
recovering files and removing its local data. A readable Git object does not
imply that a historical website has a runnable entry.

Reprise 分开处理读取版本、运行网页、查看已保存画面、恢复文件和移除本机资料。
能读取 Git 对象，不代表这一版网页已有可运行入口。

## Capability contract / 能力契约

`service.version()` returns `actions` for the exact project and full SHA.
`version_actions.py` is the sole source of operation meanings:

- `run`: an explicitly approved static/command recipe exists.
- `configure`: runtime settings need explicit review and saving.
- `saved`: a non-runnable archive has usable media for this exact project/SHA.
- `recover`: the archive has neither a runtime entry nor usable saved media.

`service.version()` 为确切项目和完整 SHA 返回 `actions`。
动作含义仅由 `version_actions.py` 定义：运行、核对配置、查看保存画面或取出资料。
缺失、越界或属于其他版本的画面不能成为可用预览。界面消费该契约，不再通过
项目类型与零散的配方、图片条件重复推断。

Deletion uses the same `delete-saved`, `remove-local`, and `clear-environment`
effects in capability choices and frozen plans. Original Git history and named
archives remain read-only. Environment cleanup is disabled when no managed
environment exists. Execution still repeats ownership, activity and plan checks.

删除选择与冻结计划共用“删除保存内容”“移除本机记录”“清理环境”三种作用。
原 Git 与命名归档保持只读；没有受管环境时禁用环境清理。真正执行仍复核
归属、进程活动和计划，不把界面能力契约当成执行授权。

## Preview and dialog ownership / 预览与弹窗归属

`live-run-preview.js` owns preview dispatch and in-flight submissions. A waiting
view belongs to one project, SHA, recipe hash, job and dialog generation. Closing
or replacing the dialog, changing versions, or changing the approved recipe
invalidates that view. Reopening a pending submission adopts its request instead
of launching a duplicate. A late error cannot replace another dialog.

`live-run-preview.js` 统一管理预览分发与待提交请求。等待画面绑定项目、完整 SHA、
配置散列、任务及弹窗代次。关闭、替换、切换版本或修改配置会使原画面失效；
重新打开时接续已有请求，不重复启动。迟到的错误也不能写入另一弹窗。

`dialog-controller.js` is the single open/replace/return/close lifecycle. It
clears view classes and metadata, stops old media, restores a complete parent
view when requested, and retains visible keyboard focus. Layout never makes a
closed runtime dialog visible.

`dialog-controller.js` 统一打开、替换、返回与关闭流程：清理样式与归属元数据、
暂停旧媒体、按需恢复完整父页面，并保留键盘焦点。布局不能使关闭的预览继续显示。

## Recovery destination policy / 恢复位置策略

`recovery_destination.py` separates exact identity validation, ordered root
selection and target validation. Ordinary projects use a new sibling folder.
Internal archives try an explicitly related project's parent, Documents, then
home. Missing, unwritable, linked or protected archive roots are skipped.
Suggestions do not create or reserve paths; recovery validates again before
exclusive creation and materialization.

`recovery_destination.py` 分开核验版本身份、选择候选根目录、校验新目标。
普通项目使用原项目的同级新目录；内部归档依次尝试明确关联项目的上级目录、
文稿目录、用户主目录。不可用、不可写、经过链接或落入保护范围的归档候选会跳过。
推荐过程不创建、不占用目录；实际恢复再次核验并独占创建。

## Preserved boundaries / 保留的边界

Git objects, full SHAs, ordered parent edges, content storage, capture metadata
and deletion transactions retain their established readers and integrity checks.
No database migration, source checkout, automatic command approval or cleanup
is introduced by this refactor.

Git 对象、完整 SHA、有序父边、内容存储、画面元数据与删除事务沿用已有读取和
完整性校验。本次重写不迁移用户数据库、不切换源仓库、不自动批准命令或清理资料。
