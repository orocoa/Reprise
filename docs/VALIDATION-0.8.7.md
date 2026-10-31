# Reprise 0.8.7 验证范围 / Validation scope

本版仅发布三处已观察到的修复：待确认截图配置的确认与状态、旧稿详情读取对比前图，以及截图页签计数。运行命令仍需明确审阅保存；版本、截图和资源释放保持原有范围。

## 已有本机证据

维护提交 `32204ee3fc74843975bbb198e4fa54300ea59634` 已完成独立合成项目的四条流程：保存新版本与对应截图；凭蓝色旧稿恢复到新目录并逐字节读回；明确删除一个样本版本并验证保留内容；停止预览、释放登记环境后重新构建，最后停止测试工作台。

632 项 Python/Chromium 完整回归通过，无跳过；该轮开始于最后的对比前图修复之前，相关的 37 项 Python 检查在其后重跑通过。最终 137 项 JavaScript 契约通过。仅包含一条前后对比记录的真实双稿另行采集，逐张核对图像散列，再用生产渲染函数确认旧稿只显示前图。未把这些结果合称为一次最终源码的全量检查。

## 0.8.7 发布检查

最终发布源提交需要通过 macOS/Python 3.9 + Chromium、Linux/Python 3.13 + Chromium、Linux/Python 3.9 核心三组远端 CI，以及每组的 JavaScript 契约、wheel/sdist 四条全新安装、便携 Skill 打包与诊断。最终来源、平台结果、下载散列及本地安装完整性在发布后补入本页。

升级保留旧运行时与入口配置备份，不为真实项目创建或删除版本、截图。默认不打开原生窗口或启动用户工作台。

## 边界

实操使用本机合成网页和本地环境，不表示任意历史框架、外部服务或未来依赖来源都能重建；未做超大历史规模和完整辅助技术审计。停止进程与清理磁盘分别报告，不声称测量了系统净 RAM 收益。同盘版本不能代替独立备份。

This release contains three scoped fixes and no feature expansion. The exact final payload, remote platform results, anonymous downloads and installed-skill integrity will be identified in the completed release evidence.
