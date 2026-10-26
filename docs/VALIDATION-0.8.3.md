# Reprise 0.8.3 验证范围

2026-10-26。本版修复 macOS 进程清理的环境读取竞争，并收敛 CI 触发。缩略图、版本关系图与数据格式沿用 [0.8.2](VALIDATION-0.8.2.md)。

## 原因与边界

进程表与环境标记来自不同时间的内核读取。Apple 的 [XNU `sysctl_procargsx`](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_sysctl.c) 从目标 VM map 复制参数与环境；exec/退出期间映射发生变化时可能返回 EIO。原实现把该错误直接传播，可能让一个已经退出的无关进程污染整个受管进程树的观察记录。

现在只在该调用返回 EIO 时重新确认 PID：已退出或确认为 zombie 才忽略环境读取；仍存活时在 0.5 秒窗口内重读，持续失败明确报告 `KERN_PROCARGS2`、PID 和 errno。没有放宽进程身份、会话、启动标记或发送信号前的校验，也没有把观察失败当作清理成功。

确定性回归先在原实现失败，再在修复后通过；包含真实 macOS zombie PID 配合过期的存活快照，并在环境读取边界注入内核错误。原生短进程/exec 压力探测没有自然击中 EIO，不能把注入场景称为自然重现了线上错误。

## CI 范围

自动全量检查覆盖 main 的功能变更和面向 main 的 PR，保留手动入口。标签和功能分支 push 不自动重复运行；main 仅 README、CHANGELOG、CONTRIBUTING 或 docs 变动时跳过全量检查。Skill 说明与 CI 本身的变动仍触发。新提交取消同一 PR/分支的旧运行，三平台矩阵、原有测试及失败诊断保留。

测试、安装包身份和托管检查结果记录于发布说明及附件清单。本机与合成资料验证仍不等同新机器安装或外部设计师采用。
