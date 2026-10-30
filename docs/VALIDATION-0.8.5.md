# Reprise 0.8.5 验证范围 / Validation scope

本版重写版本动作契约、运行预览控制器、弹窗生命周期和恢复位置策略；删除选择与计划复用相同作用定义。Git 对象、SHA/父边、内容存储与恢复读回机制保留。设计见 [版本操作模型](VERSION-ACTIONS.md)。

This release rewrites the version-action contract, preview controller, dialog lifecycle and recovery-location policy. Deletion choices and plans share operation effects. Git objects, full SHAs/parent edges, content storage and recovery readback retain their established integrity mechanisms.

## 本机验证 / Local validation

- 完整 Python/真实 Chromium 回归 624 项通过，无跳过；之后新增的配置并发校验和原生发布身份检查，连同恢复边界等 38 项专项通过。
- JavaScript 契约 131 项通过，覆盖其他弹窗覆盖、迟到结果、重复点击、关闭再打开、配置改变、精确媒体和父页面返回。
- Ego Lite 实测：独立副本运行旧稿并点击交互、关闭后无样式或元数据残留、内部资料归档打开对应画面并恢复读回、只移除合成归档的 Reprise 本机资料、原归档保持、空状态返回、中英及 390px 无横向溢出。
- Python/Chromium regression: 624 passed without skips. A further 38 focused checks cover the final recipe-concurrency, native-release identity and recovery-boundary changes.
- JavaScript: 131 passed, including stale results, duplicate/reopened submissions, recipe changes, exact media and parent return.
- Actual browser checks use isolated synthetic projects; they do not delete or modify user source data.

## 发布与安装 / Release and installation

最终发布包、来源提交和 SHA-256 见本版 GitHub Release 附件及 `SHA256SUMS.txt`。发布前核验源码外 wheel/sdist 的四条安装路径、标准/WorkBuddy Skill 清单及实际安装入口。原生窗口在 macOS 单独核验；其他客户端原生接入不由包结构检查替代。

The GitHub release and `SHA256SUMS.txt` identify the final source commit and download bytes. Release validation includes four fresh wheel/sdist install paths, standard/WorkBuddy package manifests and the installed entry. macOS native-window proof is separate from package integrity; other clients' native integration is not implied by structural checks.

## 数据与范围 / Data and limits

此前对真实 UiWeb 的 38 份保存画面、32 个网页运行及 33 个不同版本恢复已有逐版记录。本版会在最终安装物复核该项目的动作契约与代表性预览/恢复入口。这些记录分开保留，不能把旧构建验证当成本版完整运行记录。

Five large UiWeb archives previously passed manifest/path/size and content-object integrity checks; they were not all fully restored. Historical evidence is retained separately. No claim is made that every framework or arbitrary historical commit can run.

五份大归档此前通过清单、路径、大小与内容对象校验，没有逐份完整展开恢复；不据此承诺所有历史网页或框架均可运行。旧包、诊断、运行副本和原始资料保留，无自动清理或数据迁移。
