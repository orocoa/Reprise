# Reprise · 倒带 — 本地 Git 历史浏览器

[English](README.md)

[![CI](https://github.com/orocoa/Reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)

给 Git 历史一个可浏览的读档界面：比较提交与文件，在**独立副本**中预览已配置的历史版本，并支持恢复 / 导出快照。核心浏览与对比只需 **Python 3.9+ 与 Git**，不依赖 AI。更新说明可手写，也可选择接入 AI。

<!-- 截图待补
![Reprise 界面 — 提交路线与文件对比](docs/preview-ui.png)
-->

> **待补截图：** 主工作台（彩色 Git 路线 + 文件对比或版本对比）。规格见本 PR 包 `ASSET_SPEC.md`。路径：`docs/preview-ui.png`。

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

## 能做什么 / 不做什么

| 能 | 不能当成 |
| --- | --- |
| 阅读**已有 Git 记录** | 云端同步 SaaS |
| 在配置好运行方式后，于**独立副本**预览 | 保证任意历史提交一定能构建成功 |
| 核心仅 Python + Git；AI 可选 | 静默改写你的主工作区 |

## 更多

[Skill 指南](docs/AGENT-SKILL.md) · [CI](https://github.com/orocoa/Reprise/actions) · [Issues](https://github.com/orocoa/Reprise/issues)

> 若需保留旧版单文件中的 0.4.x 功能长述，请合并前决定迁入本文后半或 `docs/`。
