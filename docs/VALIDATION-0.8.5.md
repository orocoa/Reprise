# Reprise 0.8.5 验证范围 / Validation scope

最终功能来源：`32a55077b85bf77d175d015b04694af1d5683e36`，工作树干净。版本动作、预览/弹窗与恢复位置重写保留；补审减少静态预览持续监控，确认停止后释放缓存句柄，并增加直接停止入口。[目标与技术审查](PRODUCT-AUDIT-20261031.md) · [动作模型](VERSION-ACTIONS.md)。

## 最终本机验证 / Final local checks

- Python/真实 Chromium 完整回归：626 项通过，无跳过，775.107 秒。
- JavaScript 契约：134 项通过，覆盖重复/迟到预览、版本和配方归属、停止失败、较新弹窗保护、缓存与真实 Git 父边。
- 静态历史网页可访问、范围请求与源文件不变；持续观察停止后运行状态及重载管理器停止仍核验身份。命令型网页子进程观察、取消、进程身份变化和退出恢复保持回归覆盖。
- Ego Lite：中英旧稿交互预览、直接停止并移除 iframe；合成版本实际删除、保留版本校验与源字节保持；390px 无横向溢出；页面异常/错误日志为空。浏览器只操作隔离合成项目，没有删除真实用户资料。
- 五秒、两个静态预览的同脚本空闲样本：36 次进程表扫描/两个持续观察线程变为零；父进程和已退出辅助进程合计 CPU 时间约 1.342 秒变为 0.000035 秒。这是单机短样本，不是整机或任意项目的性能/RAM 保证。

Final source: 626 Python/Chromium checks passed without skips, plus 134 JavaScript contracts. Ego Lite exercised exact historical preview, explicit stop, synthetic deletion, source preservation, both languages and a 390px layout. Command-based child-process ownership remains tested.

## 安装与交付 / Installation and payload

四条源码外全新安装路径通过：wheel → venv/user-site，sdist → rebuilt wheel → venv/user-site；核对网页、worker 与原生窗口资源字节。标准及 WorkBuddy Skill 清单核验通过；本地 Skill 已同步同一最终功能载荷，doctor 校验 121 个文件且无错误。macOS 原生窗口返回 ready，既有 45 个用户预览保留。WorkBuddy 包结构可用不代表平台审核或所有客户端集成通过。

标准包 SHA-256：`31429f459250f71b4a0f2fadaedb594df1b21354d31f17f42a39a305c08a69b9`。运行源码树 SHA-256：`99c93afab96f85a53b697a6e1a330acababd979d7702b4b0091c0f33470422d5`。下载身份另见 Release 的 ARTIFACTS.json 和 SHA256SUMS.txt，不能仅凭版本号判断。

最终包实际保存两稿、分别采集精确 SHA 的画面，旧稿交互与停止成功，恢复读回且当前源文件保持。新采集画面与已保留公开素材字节相同，重新逐字节核对后复用文件，元数据绑定本次真实版本与包散列。旧截图、原始采集和失败诊断保留，没有以相邻版本补图。

## 平台证据 / Platform evidence

最终平台检查：[PR #4 checks](https://github.com/orocoa/Reprise/pull/4/checks)。测试隔离修复只禁止合成 Git 写入后的自动维护，不改变功能载荷；完整源字节比较继续保留。矩阵包含 Linux/Python 3.9、Linux/Python 3.13/Chromium 和 macOS/Python 3.9/Chromium；发布以该检查实际成功为准。Linux 3.9 的浏览器项目按矩阵设计跳过，不能把它称为全平台浏览器验证。Windows、全新物理机器和其他原生客户端未由这些结果证明。

先前候选曾通过本机 624 项与之后 38 项专项、131 项 JavaScript；其 macOS CI 曾因测试脚本等待跨 CDP Promise 被回收而失败。最终脚本改为触发后等待已渲染选择器，32a 候选的两个 Linux 检查通过，macOS 唯一失败是合成 Git 提交后的后台 maintenance.lock 在源字节采样之间变化；仅修改测试样本的命令/本地配置，未更改产品 Git 读取层或用户配置。保留两次原失败记录。旧候选结果不替代最终平台检查。

## 真实资料与限制 / Real data and limits

此前 UiWeb 的 38 个动作、两个代表性网页和六个归档入口已有逐项记录；完整 32 个网页运行与 33 个不同版本恢复来自更早验证。最终安装复核保持项目入口与既有运行实例。不同构建的这些证据分开保留，不声称每个真实版本都在最终包重新运行。

五份大归档此前通过清单、路径、大小与内容对象校验，没有逐份完整展开恢复。所有框架、任意历史提交、外部服务和未来依赖可用性均不在保证范围；无多 TB 删除压力结论。同盘版本不是独立备份，停止进程、释放生成依赖、删除保存状态和移除只读历史条目是不同操作。
