# Reprise 0.8.6 验证范围 / Validation scope

本版只修复跨系统启动的历史进程记录识别，增加显式 `process_state` 并更新 Skill 说明。文件版本、Git 对象/父边、媒体绑定、恢复与删除的数据机制保持原边界。

## 已有本机证据 / Existing local evidence

功能候选 ce5d58e 已通过 632 项 Python/Chromium 测试（无跳过）、134 项 JavaScript 契约。新增六项测试覆盖 macOS/Linux 旧启动身份、日期显示变化、无效/未来/矛盾身份、不同 UID、运行列表及重复停止、未知状态的保守兼容。

本机的 45 条旧运行记录对应的已登记进程身份均未存活，45 个原预览端口全部关闭；它们是旧记录，不是 45 个活进程。结束登记未向这些 PID 发送信号。104 条运行记录和所有运行副本/日志保留；版本、媒体和项目登记的 351 个受保护文件核对一致。闲置工作台服务已停止。

## 0.8.6 发布检查 / Release checks

正式功能提交为 `b941b09a3be8ff61efe08004ace02248f9b44ebf`。[三组远端 CI](https://github.com/orocoa/Reprise/actions/runs/41164064684) 全部通过：macOS/Python 3.9 + Chromium 跑完 632 项 Python 测试，无跳过；Linux/Python 3.13 + Chromium 跑完同一套，跳过 14 项 macOS 专属检查；Linux/Python 3.9 跳过 31 项平台或浏览器检查，符合该组未启用浏览器的配置。各组 134 项 JavaScript 契约、wheel/sdist 四条源码外全新安装、便携 Skill 打包与诊断均通过。

最终版本另通过本机 24 项版本/入口检查。使用最终标准 Skill ZIP 实际完成两稿保存和精确 SHA 截图、恢复读回、当前源文件保持不变，以及历史静态预览 HTTP 读回和明确停止。受控旧启动记录使用仍存活的隔离探针 PID，停止后探针继续存活，原 ownership 文件逐字节保持一致。该测试未重启物理机器。

[公开 0.8.6](https://github.com/orocoa/Reprise/releases/tag/v0.8.6) 的标准 ZIP、WorkBuddy ZIP、wheel、sdist 均来自上述同一干净提交；6 个附件均已匿名下载，与本地最终文件逐字节散列核对。`ARTIFACTS.json` 与 `SHA256SUMS.txt` 提供完整身份。

- 标准 ZIP SHA-256：`03c0e11e20081ce3f6d9b2274b16a97aa6083564b4efade2832cf2f9d0776aab`
- runtime/web tree SHA-256：`b064c92e1e613a7c47f8aa8f3a87aa24d7f0ee238b0e92263963f5cca2d99642`

本地安装使用同一最终包，doctor 报告 0.8.6、来源提交一致且清单完整性通过。旧运行时、候选包、诊断和原生入口配置备份保留；原生 0.8.6 外壳已编译并登记，未打开窗口或启动服务。发布前后 352 个受保护文件（4,742,790 字节，包含内容、图片与项目登记）的大小和 SHA-256 一致；104 条运行记录保留，活动与无法确认的预览均为 0，工作台后台关闭。此前清理回执的 351 个文件属于其当时的取样范围，此次基线另包含 named-archives registry。

## 限制 / Limits

启动周期测试包含 macOS/Linux 的受控内核身份场景；不表示本轮重启了物理机器，也不证明所有跨机器迁移方式。损坏、未来或身份矛盾的记录仍不能当作已结束。没有系统级 RAM 清理、自动版本删除或后台快照；同盘版本不是独立备份。

The exact 0.8.6 payload passed all three remote jobs, fresh installation checks, final-package save/capture/recovery and lifecycle probes, anonymous public-download verification, and installed-skill integrity checks. Historical versions, pictures and diagnostics remain separate from process lifetime.
