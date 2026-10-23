# Reprise · 倒带

**认准项目的旧版本，看懂变化，再把需要的一版取回。**

[English](README.md) · [样本上手（英文）](docs/QUICKSTART.md) · [下载 v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) · [常见问题（英文）](docs/FAQ.md)

[![CI](https://github.com/orocoa/Reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)

Reprise 是面向网页和小项目迭代的**本地 Git 历史浏览器**。查看真实提交、比较文件，在独立副本中预览已配置的历史版本，并将选定快照恢复到新目录，保留当前工作文件。核心需要 **Python 3.9+ 和 Git**；AI 可选。

![Reprise 工作台：生成的 static-web 样本包含两次真实提交与文件变化](docs/preview-ui.png)

截图来自仓库生成的 `static-web` 样本。预览需要另行生成或导入，并绑定准确版本；并非每次提交都自动有截图。

## 从一个具体任务开始

| 你想做什么 | 公开 v0.4.1 能做什么 |
| --- | --- |
| “我要找的网页效果在哪一版？” | 浏览真实提交，查看文件和已有的版本预览。 |
| “这两版究竟改了什么？” | 在工作台比较提交和文件差异。 |
| “旧版还能打开吗？” | 保存合适的运行配置后，在独立副本里运行；可能仍需依赖与外部服务。 |
| “我想把那一版取回来。” | 恢复到新目录或导出 ZIP，并核对 Git blob；结果不包含 `.git` 历史。 |

**版本范围，核验于 2026-10-24：** 当前公开下载为 **v0.4.1**。普通文件夹快照、共享内容存储、版本删除影响说明、受管环境释放与重建正在**本地候选版**中开发，尚不包含在公开下载里。详见[路线图与发行边界（英文）](docs/ROADMAP.md)。

## 先用样本体验

克隆目标须是新目录，每条命令成功后再执行下一条。这个源码演示需要 Python 3.9+ 和 Git 2.28+，会自行创建样本 Git 仓库。

```sh
git clone --branch v0.4.1 --depth 1 https://github.com/orocoa/Reprise.git reprise-first-run
cd reprise-first-run
python3 scripts/create_demo_projects.py --output work/first-run/projects
python3 run.py --data work/first-run/data open work/first-run/projects/static-web --lang zh
```

选中一次提交、比较文件，再把它恢复到样本仓库外的新目录。完整的[操作步骤（英文）](docs/QUICKSTART.md)说明预览配置、内容核对和服务停止；生成的样本、恢复文件和诊断都会保留。

关闭标签页不会停止服务。在上述源码目录执行：

```sh
python3 run.py --data work/first-run/data shutdown
```

## 通过本地 agent 使用

下载完整的[通用 Skill ZIP](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-skill.zip) 或 [WorkBuddy ZIP](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-workbuddy.zip)。保留整个 `reprise/` 目录，包括脚本与资源。本地 agent 通过同一个 Python 核心打开已有 Git 项目；便携包无需 pip 安装。

让 agent 打开项目历史、定位版本、比较文件，或将某版恢复到新目录。预览命令需要先保存运行配置。各客户端安装方式与验证范围见 [Skill 指南](docs/AGENT-SKILL.md)。

## 本地数据与执行范围

- 导入的 Git 仓库保持只读，不会因导入或预览而替你提交、重置源仓库。
- 核心历史与比较不需要 AI 或云端上传；可选 AI 服务和外部 agent 有各自的数据流。Reprise 不加密本地应用数据。
- 旧项目运行命令以当前用户权限执行。独立副本**不是安全沙箱**，安装依赖可能联网；`network: local` 只限制采集浏览器。
- 恢复核对的是选定版本的文件内容，不代表程序已经运行，也不代表已有独立备份。源 Git 仓库应另行备份。
- 样本、运行副本、截图和失败诊断会保留。公开版本不是磁盘清理器或内存优化工具。

默认数据目录：macOS 为 `~/Library/Application Support/Reprise`；Linux 为 `$XDG_DATA_HOME/reprise`，未设置时使用 `~/.local/share/reprise`。数据目录须在导入仓库外；升级或备份前用同一个 `--data` 目录停止服务。

## 帮助决定下一步

欢迎描述**想完成什么、卡在哪里、原来怎么做**。失败和放弃的经历同样有用，不必上传私人文件或完整日志。[反馈问题与真实使用](https://github.com/orocoa/Reprise/issues/new/choose) · [参与项目（英文）](CONTRIBUTING.md)。

如果它对你有帮助，欢迎 Star 收藏；实际完成任务后的反馈更能帮助我们决定下一步。

[完整中文使用指南](docs/USER-GUIDE.zh-CN.md) · [配方与采集](docs/RECIPES.md) · [架构](docs/ARCHITECTURE.md) · [验证范围](docs/VALIDATION.md) · [发布验收](docs/RELEASE-CHECKLIST.md)

由 [orocoa](https://github.com/orocoa) 维护。代码采用 [MIT](LICENSE) 许可；字体、图标和导入媒体保留各自许可，见[第三方说明](THIRD-PARTY-NOTICES.md)。
