# 独立备份、目录迁移与重新关联

0.6.0 本地候选范围；本轮不公开发布，不自动移除源目录或旧数据库。

## 范围与流程

独立备份处理明确选择的 Reprise 数据目录：保存的普通文件夹内容库、登记、说明、配方、媒体、回执等。外部源 Git 仓库、普通文件夹当前未保存内容及外部旧归档不自动扫描或复制，报告必须单列这些依赖。备份保存在新目录，通过清单与逐文件读回核对后才标记完成。备份没有加密；若含已保存的 AI 密钥，保留私有权限且不向模型或日志输出密钥。

备份需要先停止该数据目录的 Reprise 管理服务和任务；独占租约防止备份过程中开启新服务或写入。不能为备份停止其他应用或网站。原目录和失败产物保留。备份可恢复到新的数据目录，随后显式用 `--data 新目录` 打开，作为数据目录迁移；不改默认路径或覆盖原库。同一磁盘上的校验副本不代表不同物理介质的故障隔离。

项目源目录迁移采用复制、读回校验、切换登记的顺序，原目录保留。重新关联只改变当前项目的来源路径，项目标识、名称、说明、配方和版本关系继续保留。候选路径必须以真实内容或 Git 身份核对，不以同名认定；已经属于另一项目的路径不能抢占。

普通文件夹原目录离线时，使用保存的版本核对候选；Git 使用可验证的历史锚点。缺少锚点时明确报告，不能通过猜测恢复关联。旧归档仍走原始名称适配器，不重写历史登记。不能安全完整复制的 linked worktree、外部 Git 对象依赖等要明确限制，不能宣称迁移后不再依赖旧位置。

## 使用方式

```sh
python3 run.py --data /path/to/reprise-data shutdown
python3 run.py --data /path/to/reprise-data backup --to /new/backup
python3 run.py backup-check /new/backup
python3 run.py data-restore /new/backup --to /new/reprise-data
python3 run.py --data /new/reprise-data serve --port 0

python3 run.py --data /path/to/reprise-data relink PROJECT_ID --to /existing/project --check
python3 run.py --data /path/to/reprise-data relink PROJECT_ID --to /existing/project
python3 run.py --data /path/to/reprise-data migrate PROJECT_ID --to /new/project
```

桌面入口在「项目设置 → 备份与目录迁移」。原目录不可用时也可从「项目 → 迁移或重新关联项目目录」选择已有项目。重新关联先检查，再显式确认。备份创建显示当前运行时和数据目录的实际离线命令；备份检查和恢复新库可在界面提交任务。恢复新库不会自动改变当前服务使用的数据目录。

## 明确限制

- 数据备份保存文件、目录、安全相对链接、权限、mtime 和扩展属性。没有加密或签名，不保留 owner、ACL、文件系统 flags、硬链接关系和稀疏布局；目录层级、单份 JSON 与清单均有安全上限。
- 项目复制迁移拒绝 ACL、特殊权限位、特殊文件与复杂 Git 外部对象依赖；单次最多 250000 项、128 GiB。普通 Git 保留历史、未提交及未跟踪文件；bare/linked worktree 使用经身份验证的重新关联，不执行自动完整复制。
- 不改写工程正文中的绝对路径或外部依赖配置。目录副本的文件校验通过，不代表原程序已经在新位置运行验证。
- 旧归档按原名称继续读取和恢复；位于数据目录内的归档随备份迁移，外置仓库和 view 列入外部依赖，不把本机快照宣称为可远程下载。
- 新库只重定位已知状态字段。原始用户说明、配方正文和未知 JSON 保持；原进程身份失效，运行与活动任务需要明确重新执行。

> Source-package note: internal acceptance notes and local evidence locations are omitted. This document does not substitute for validation of the exact candidate you installed.
