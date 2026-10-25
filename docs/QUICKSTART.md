# 快速开始 / Quickstart

[中文](#中文) · [English](#english) · [首页](../README.md)

## 中文

### 1. 让 Agent 安装并打开

下载完整的 [Reprise-Skill.zip](https://github.com/orocoa/Reprise/releases/download/v0.8.0/Reprise-Skill.zip)，交给有本机文件与命令能力的 Agent：

> 帮我安装倒带 / Reprise。先复用已有环境，缺少的依赖按官方方法和正常授权安装，然后打开。

Agent 核对客户端真正支持的技能位置，保留整个包，检查 Python/Git 和截图所需的 Node/Playwright/浏览器，再完成已获授权的安装。普通用户不需要额外 AI Key 或手填环境变量；真正需要系统认证或缺少许可时按宿主流程处理。[安装参考](AGENT-SKILL.md)

### 2. 在当前网页对话里留稿

项目路径已经明确时说：

> 本轮修改前后都帮我留稿。

首次为这个网页项目留稿时，Agent 只问一次“以后每次留稿需要一起保存画面吗？”。回答“是”或“否”后，先把选择保存在项目中，之后留稿、重开或换聊天都会沿用，不再要求反复说“同时记住画面”。名称按任务简短生成；内容未变化时沿用已有稿及名称。

分别检查**文件已保存**和**画面已完成**。首张截图失败、缺依赖或配置未批准都不重置选择。入口明确的静态 HTML 可准备画面；需要运行项目命令时，只补充确认实际配置，确认后沿用。截图失败时补同一稿画面，不必重复留稿。用户可随时在设置修改长期选择。


### 3. 按画面取回，再继续改副本

选择 Reprise Skill，说“打开”。按画面选稿，需要时比较，再点「取出这一稿」，取到新文件夹。确认副本属于目标稿，当前项目仍保留新稿，然后让 Agent 使用副本目录继续修改。

**快捷操作：** 工作台首次保存名称可留空，自动按时间命名；已有明确截图偏好的项目可点「保存一稿」或 Ctrl/⌘ + S 直接保存，需要命名时用 Ctrl/⌘ + Shift + S。名称对话框可用 Ctrl/⌘ + Enter 提交。整稿取回后可点「复制给 Agent 继续修改」，粘贴到当前网页对话。部分文件取回不提供整稿继续指令。

必须在修改前主动保存；“打开”不保存或导入当前目录。退出时正常停止 Reprise，关闭浏览器标签不等于停服。[详细任务](WORKSPACE-TASKS.md) · [功能范围与冻结边界](FEATURES.md)

当前已有环境的 macOS＋Codex 实际任务通过；新机器补齐依赖、其他客户端原生接入仍未验证。文件可恢复不保证旧依赖、数据库或远程服务可运行。

<details>
<summary>熟悉环境的用户：直接命令</summary>

完整 Skill 使用绝对入口；先确认 Python 3.9+ 和 Git。自动截图另外需要 Node、Node 版 Playwright 与可用浏览器。

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang zh --no-browser
```

使用实际返回的本机 URL。doctor 检查核心与包完整性，不代表截图已经验证。完整开发仓库也可运行 `python3 run.py`。[依赖复用与安装命令](AGENT-SKILL.md)

</details>

## English

### 1. Ask your agent to install and open

Give the complete [Reprise Skill](https://github.com/orocoa/Reprise/releases/download/v0.8.0/Reprise-Skill.zip) to an agent with local file and command access:

> Install Reprise. Reuse existing tools, install missing dependencies through official methods and normal authorization, then open it.

The agent resolves the actual client Skill location, preserves the full package, checks Python/Git and Node/Playwright/browser capture tools, then completes authorized setup. Ordinary users need no extra AI key or manually assembled environment variables. Genuine credentials or missing permission use the host’s normal flow. [Setup reference](AGENT-SKILL.md#english)

### 2. Save in your webpage conversation

With the project already clear:

> Save a draft before and after this edit.

On the first save of a webpage project, the agent asks once whether future drafts should include images. Yes or no is stored with the project before capture/configuration finishes. Later saves, reopening and other chats reuse it; no repeated image request is needed. Names follow the task, and unchanged files reuse their existing draft/title.

Check **files saved** and **picture complete** separately. Missing dependencies, a failed picture or pending command approval does not reset the choice. Static HTML can prepare its image; command-based projects need reviewed settings first, then reuse them. Retry the picture against the same saved revision. Change the ongoing choice in settings anytime.


### 3. Recover by picture and edit the copy

Select the Reprise Skill and say “Open.” Recognize an earlier appearance, compare if needed, then choose **Recover this draft**. Check the new copy and keep the current project in place; point your editing agent at the recovered folder.

**Shortcuts:** blank names use the time; projects with an explicit capture preference support direct saving and Ctrl/⌘ + S. Ctrl/⌘ + Shift + S names a draft first; Ctrl/⌘ + Enter submits that dialog. Whole-draft recovery offers **Copy instructions to continue** for pasting into your webpage conversation. Partial-file recovery does not claim a complete editable project.

Save before edits overwrite the draft. Opening does not import or save a directory. Stop Reprise normally when finished; closing the tab does not stop the service. [Workbench tasks](WORKSPACE-TASKS.md) · [Feature scope](FEATURES.en.md)

Actual use passed in this existing macOS + Codex environment. Fresh-machine dependency setup and native use in other clients remain unverified. File recovery does not guarantee working old dependencies, databases or remote services.

Experienced users can run the complete Skill’s absolute entry with `doctor`, then `open --workbench --lang en --no-browser`. Use the actual returned URL. See [environment reuse and install commands](AGENT-SKILL.md).
