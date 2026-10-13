# 基础版发布验收

范围：本地 CLI 启动的 Git 版本工作区。核心只依赖 Python 3.9+ 和系统 Git；运行命令须明确批准，自动采集按需使用 Node/Playwright。Codex app-server、Windows、原生 App 和环境整包不在本次范围内。

## 必须有的证据

| 检查 | 验收内容 |
| --- | --- |
| 完整回归 | `PYTHONPATH=src python3 -m unittest discover -s tests -v`；发布检查提供 Node 和浏览器变量，并设置 `REPRISE_BROWSER_TESTS=1` |
| 图、缓存与证据契约 | `node --test tests/graph-layout.test.cjs tests/workspace-cache.test.cjs tests/evidence-model.test.cjs`；所有完整 SHA、有序父边、各分支边界、淘汰后的搜索及媒体归属保持正确 |
| 真实界面 | 中英首屏与切换、编辑/收藏持久化、32px 列表、任意两版比较、陈旧响应、精确版本媒体、空预览入口、媒体放大、失败/部分采集诊断与自动刷新、连续键盘导航、导入返回原设置位置、运行阶段刷新、运行/采集/停止、安装任务取消、副本路径与移动端溢出 |
| 安全与退出 | 源仓库字节/index 不变；同名 Python 包、Git filters、Host/Origin/token、文件越界、登记外产物、静态目录重定向、启动中断恢复及残留子进程回归 |
| 安装 | `python3 scripts/check_distribution.py`；源码外的全新 venv/user-site、直接 wheel 和 sdist 重建 wheel，网页与 worker 内容匹配 |
| 平台 | macOS 和 Linux 对应 CI 实际通过；只通过 macOS 时仅把 macOS 标为已验证，不以 CI 配置代替结果 |
| 发布内容 | 当前视觉定稿再跑受影响界面回归；最终安装物与其源码匹配；保留 MIT 和第三方许可，无本机应用数据/真实密钥进入发行物 |

已有多组 PersonalWeb demo 能证明常见使用流程可行，不能替代空仓库、浅历史、裸仓库、多父合并、损坏记录、跨进程取消和独立安装这些边界回归。所有新诊断放在 `work/test-artifacts/`，本机不自动删除；CI 的日志和产物按工作流保存 90 天，正式发布证据应另行归档。

## 架构结论与规模边界

Git 对象、项目配置、运行生命周期、采集证据与 AI 提案的职责已经分开，CLI 与 HTTP 共用服务层。当前无需引入前端框架、数据库或常驻 Node 服务。核心入口、资源路径、进程停止和只读 Git 约束由回归覆盖。

不承诺任意历史提交能运行，也不把独立副本称为安全沙箱。长期磁盘证据按设计保留。每个 tip 的加载范围有明确边界；当前图仍渲染全部已加载节点，极大历史与首次全文件搜索的成本随规模增长。若以后主要面向数万提交，再依据实测增加分段显示或索引，并保持完整版本和父边契约。

本次本机审计的基准、失败记录、最终回归和页面截图保存在 `work/test-artifacts/architecture-audit-20261009T234548/`，审核报告见同目录 `report.md`。该目录是诊断证据，不进入安装包。
