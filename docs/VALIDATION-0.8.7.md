# Reprise 0.8.7 验证范围 / Validation scope

本版仅发布三处已观察到的修复：待确认截图配置的确认与状态、旧稿详情读取对比前图，以及截图页签计数。运行命令仍需明确审阅保存；版本、截图和资源释放保持原有范围。

## 已有本机证据

维护提交 `32204ee3fc74843975bbb198e4fa54300ea59634` 已完成独立合成项目的四条流程：保存新版本与对应截图；凭蓝色旧稿恢复到新目录并逐字节读回；明确删除一个样本版本并验证保留内容；停止预览、释放登记环境后重新构建，最后停止测试工作台。

632 项 Python/Chromium 完整回归通过，无跳过；该轮开始于最后的对比前图修复之前，相关的 37 项 Python 检查在其后重跑通过。最终 137 项 JavaScript 契约通过。仅包含一条前后对比记录的真实双稿另行采集，逐张核对图像散列，再用生产渲染函数确认旧稿只显示前图。未把这些结果合称为一次最终源码的全量检查。

## 0.8.7 发布检查

正式来源为干净提交 `64450b8b6c1b4e4396a4d79bf8823e04bc0c0888`。[远端 CI](https://github.com/orocoa/Reprise/actions/runs/41169281461) 三组全部通过：

- macOS/Python 3.9 + Chromium：633 项 Python 测试，无跳过，777.192 秒。
- Linux/Python 3.13 + Chromium：运行同一套 633 项，跳过 14 项 macOS 专属检查，253.115 秒。
- Linux/Python 3.9：运行同一套 633 项，按矩阵跳过 31 项平台或浏览器检查，205.522 秒。

各组均通过 137 项 JavaScript 契约、wheel/sdist 四条源码外全新安装、标准/WorkBuddy Skill 打包及诊断。最终发布包另在本机完成四条全新安装与 28 项针对提取 ZIP 的 JavaScript 契约；实际保存两稿并采集精确 SHA 图片、恢复读回与当前源文件保持不变、历史预览 HTTP 读回与明确停止均通过。仅一条前后对比采集记录的真实双稿也用最终包重新验证，旧稿详情及生产渲染函数只读取它自己的前图。

[公开 v0.8.7](https://github.com/orocoa/Reprise/releases/tag/v0.8.7) 的标准 ZIP、WorkBuddy ZIP、wheel 和 sdist 均来自上述同一提交；6 个附件已经匿名下载，与本地最终文件核对字节数与 SHA-256。完整身份见发布附件 `ARTIFACTS.json` 与 `SHA256SUMS.txt`。

- 标准 Skill ZIP SHA-256：`a1b5aed4df8bfe91efb54c8c5571f2b9771c29184acd146ad438c02fcd4e4874`
- runtime/web tree SHA-256：`0faddfe0b2950e9df8554f35b456e991f87ac980268fe7f26ba2674a30289d18`

本地 Skill 已安装同一正式载荷，doctor 报告 0.8.7、来源提交一致且完整性通过。原生 0.8.7 外壳已编译并登记，既有缓存入口指向新核心；未打开窗口或启动用户工作台。7 个旧运行时目录及其 717 个文件的字节散列核对一致，全部旧配置先行备份。

发布前后 352 个受保护文件（4,742,790 字节，包含版本内容、图片、项目登记和 named-archive registry）大小与 SHA-256 一致。104 条真实运行记录保留，存活与未知预览均为 0，工作台后台关闭。所有新增实操都在独立合成项目中，未对真实项目创建或删除版本、截图。

## 边界

实操使用本机合成网页和本地环境，不表示任意历史框架、外部服务或未来依赖来源都能重建；未做超大历史规模和完整辅助技术审计。停止进程与清理磁盘分别报告，不声称测量了系统净 RAM 收益。同盘版本不能代替独立备份。

This release contains three scoped fixes and no feature expansion. All three final remote jobs, fresh installs, extracted-package checks, real capture/recovery/lifecycle probes, anonymous downloads and installed-skill integrity checks passed. Historical user data and previous runtime payloads remain retained.
