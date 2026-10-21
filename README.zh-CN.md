# Reprise · 倒带 — 本地 Git 历史浏览器

[English](README.md)

[![CI](https://github.com/orocoa/Reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)

给 Git 历史一个可浏览的读档界面：比较提交与文件，在**独立副本**中预览已配置的历史版本，并支持恢复 / 导出快照。核心浏览与对比只需 **Python 3.9+ 与 Git**，不依赖 AI。更新说明可手写，也可选择接入 AI。

![Reprise 工作台：static-web 示例的真实提交历史与文件变化](docs/preview-ui.png)

截图来自本机运行的仓库自带 `static-web` 示例，包含两次真实 Git 提交。

**开始：** [安装 agent skill](docs/AGENT-SKILL.md) · [Releases](https://github.com/orocoa/Reprise/releases/latest) · 下方命令行。

## 用 skill 打开（推荐）

下载 [通用 skill](https://github.com/orocoa/Reprise/releases/latest/download/reprise-skill.zip) 或 [WorkBuddy skill](https://github.com/orocoa/Reprise/releases/latest/download/reprise-workbuddy.zip)，保留完整 `reprise/` 目录，让本机 agent 按 `SKILL.md` 打开。需要 Python 3.9+ 和 Git，无须 pip 或原生 App。

在目标项目里发命令即可打开历史、比较文件、配置独立预览，或恢复到新目录 / ZIP。完整说明：[docs/AGENT-SKILL.md](docs/AGENT-SKILL.md)。

## 命令行启动（可选）

```sh
git clone https://github.com/orocoa/Reprise.git
python3 -m venv ~/.venvs/reprise
~/.venvs/reprise/bin/python -m pip install ./Reprise
source ~/.venvs/reprise/bin/activate
```

进入要查看的 Git 仓库：

```sh
reprise .
reprise shutdown
```

数据目录：macOS `~/Library/Application Support/Reprise`，Linux `$XDG_DATA_HOME/reprise`（须在导入仓库之外）。

预览历史页面还需要对应版本的依赖与已保存的运行配置。导入仓库不会安装依赖或执行命令；批准的命令在本机运行，独立副本不等于容器隔离。`network: local` 只限制采集浏览器，不限制已批准的安装或构建命令。

备份或升级前，先用同一数据目录执行 `reprise shutdown`。完整保留应用数据，并另行备份源 Git 仓库；应用数据可能包含 API 密钥，应保持私有。现有副本、媒体、日志与失败采集记录均保留。

## 能做什么 / 不做什么

| 能 | 不能当成 |
| --- | --- |
| 阅读**已有 Git 记录** | 云端同步 SaaS |
| 在配置好运行方式后，于**独立副本**预览 | 保证任意历史提交一定能构建成功 |
| 核心仅 Python + Git；AI 可选 | 静默改写你的主工作区 |

## 更多

[完整使用指南](docs/USER-GUIDE.zh-CN.md)保留原 README 的详细内容，包括自动截图依赖、运行配置、取消任务、备份与升级说明。

[Skill 指南](docs/AGENT-SKILL.md) · [配方与采集](docs/RECIPES.md) · [架构](docs/ARCHITECTURE.md) · [验证边界](docs/VALIDATION.md) · [发布验收](docs/RELEASE-CHECKLIST.md) · [CI](https://github.com/orocoa/Reprise/actions) · [Issues](https://github.com/orocoa/Reprise/issues)

代码采用 [MIT 许可证](LICENSE)；字体、图标与导入媒体保留各自许可，见[第三方说明](THIRD-PARTY-NOTICES.md)。
