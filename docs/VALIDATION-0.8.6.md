# Reprise 0.8.6 验证范围 / Validation scope

本版只修复跨系统启动的历史进程记录识别，增加显式 `process_state` 并更新 Skill 说明。文件版本、Git 对象/父边、媒体绑定、恢复与删除的数据机制保持原边界。

## 已有本机证据 / Existing local evidence

功能候选 ce5d58e 已通过 632 项 Python/Chromium 测试（无跳过）、134 项 JavaScript 契约。新增六项测试覆盖 macOS/Linux 旧启动身份、日期显示变化、无效/未来/矛盾身份、不同 UID、运行列表及重复停止、未知状态的保守兼容。

本机的 45 条旧运行记录对应的已登记进程身份均未存活，45 个原预览端口全部关闭；它们是旧记录，不是 45 个活进程。结束登记未向这些 PID 发送信号。104 条运行记录和所有运行副本/日志保留；版本、媒体和项目登记的 351 个受保护文件核对一致。闲置工作台服务已停止。

## 0.8.6 发布检查 / Release checks

最终 0.8.6 源提交须完成 macOS/Python 3.9、Linux/Python 3.9 与 3.13 的远端矩阵，及 wheel/sdist 四条源码外全新安装。平台结果、最终来源与包散列在发布完成后补入本页。Linux 3.9 依矩阵只运行核心检查；另两组启用 Chromium。

最终 Skill 使用清单和 provenance.json 核验，不以版本号代替身份。升级保留旧运行时、候选包与诊断，不创建用户项目的新版本或截图，不启动后台服务。

## 限制 / Limits

启动周期测试包含 macOS/Linux 的受控内核身份场景；不表示本轮重启了物理机器，也不证明所有跨机器迁移方式。损坏、未来或身份矛盾的记录仍不能当作已结束。没有系统级 RAM 清理、自动版本删除或后台快照；同盘版本不是独立备份。

The previous candidate passed local checks. Final release evidence will identify the exact 0.8.6 payload, platform matrix, fresh installation paths and public download checks. Historical versions, pictures and diagnostics remain separate from process lifetime.
