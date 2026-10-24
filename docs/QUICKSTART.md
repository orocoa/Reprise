# 快速开始 / Quickstart

[简体中文](#中文) · [English](#english) · [首页](../README.md)

## 中文

本页面向 [0.8.0 预览版源码 Skill](https://github.com/orocoa/Reprise/releases/tag/v0.8.0-rc.1)。下载完整的 [Reprise-Skill.zip](https://github.com/orocoa/Reprise/releases/download/v0.8.0-rc.1/Reprise-Skill.zip)。本机 Codex 安装与实际任务已通过；缺依赖的新机器和其他客户端原生接入仍未验证。

### 1. 交给 agent 接入

将主附件 `Reprise-Skill.zip` 交给有本机文件和命令执行能力的 agent：

> 帮我安装倒带 / Reprise 并打开。

由 agent 先检查复用已有环境，缺少时按官方方法和正常授权补齐。已有安装授权继续沿用，不额外要求每个包再确认一次；普通用户不需手填环境变量。真正缺少许可或需要系统认证时，按宿主流程处理，不能完成就说明阻塞。依赖和开发者细节见[接入说明](AGENT-SKILL.md)。

接好后，选择 **Reprise Skill**，说“打开”。首次空列表正常；打开不会保存或自动加入当前目录。保留完整包，不只复制 SKILL.md；已有技能不删除，由 agent 核对实际版本和入口。

### 2. 修改前留一稿

在项目路径已经明确的网页对话里说：

> 保存当前网页这一稿，叫“改颜色之前”，同时记住画面。

分别检查**文件是否保存、画面是否完成**。入口明确且素材在本机的静态 HTML 可以尝试出图；标准独立 npm/Vite 项目先保存文件，再给出待批准的安装/运行计划。确认后才在独立副本执行；项目依赖可能联网下载。准备 Reprise 的工具环境，不等于批准网页项目的安装脚本。单稿批准不自动批准未来每稿，Next 等其他配置仍需确认运行方式。

截图没完成时文件可能已保存；补这一稿的画面即可，不必重复留稿。文件未变化时可能复用已有稿及名称，以实际回报为准。

继续修改配色，再保存一稿“改颜色之后”和对应画面。Reprise 只记录主动保存过的稿件，不能补回保存前已覆盖的内容。

### 3. 按图取回

选择 Reprise Skill，说“打开”。认出“改颜色之前”，需要时比较两稿，再点「取出这一稿」，取到新文件夹。打开副本确认旧配色在，原项目仍保留新配色，然后继续改副本。

缺图时文件仍可取回，但不算完成“凭画面找回”。取回成功也不保证旧依赖或外部服务仍可运行。更多操作见[工作台任务](WORKSPACE-TASKS.md)。结束时让 agent 或工作台设置正常停止服务；只关浏览器标签不会停服。

<details>
<summary>开发者：已有基础环境与源码入口</summary>

基础操作需要 Python 3.9+ 与 Git，核心没有第三方 Python 依赖，无须为核心执行 pip install。3.9 是代码最低要求；新装请选择官方仍维护的 Python 版本。自动截图另需 Node、Node 版 Playwright 与可运行的 Chromium/已验证兼容浏览器。本项目锁定 Playwright 1.62.1，其要求 Node 20+；新装建议仍受支持的 LTS 22 或 24。

源码 Skill 的入口为：

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang zh --no-browser
```

`doctor` 检查 Python/Git、核心和包完整性，不代表截图链路已就绪。使用实际返回的本机 URL。完整开发仓库也可运行 `python3 scripts/start_workbench.py`；它与源码 Skill 使用同一核心。

已有 Reprise 开发仓库准备截图依赖时，在 Reprise 自己的目录运行 `npm install` 和 `npx playwright install chromium`，不要在受管网页源仓库里安装 Reprise 工具。依赖的官方来源、复用与安装范围见[接入说明](AGENT-SKILL.md)。

代码入口面向 macOS/Linux（Windows 使用 WSL），不声明原生 Windows 或所有宿主已实测。完整开发仓库可用 `examples/recovery-tutorial/prepare.py` 在新位置练习；较早 Python Skill / wheel 说明保留在[历史快速开始](REFERENCE-QUICKSTART-20261024.md)。

</details>

## English

This guide is for the [0.8.0 preview source Skill](https://github.com/orocoa/Reprise/releases/tag/v0.8.0-rc.1). Download the complete [Reprise-Skill.zip](https://github.com/orocoa/Reprise/releases/download/v0.8.0-rc.1/Reprise-Skill.zip). Installation and the actual task passed in this Mac’s Codex environment; fresh-machine dependency setup and native use in other clients remain unverified.

### 1. Ask your agent to set it up

Give the primary `Reprise-Skill.zip` attachment to an agent with local file and command access:

> Install Reprise and open it.

The agent checks and reuses available tools, then fills missing dependencies using official methods and normal authorization. Reuse existing installation authorization rather than asking again for every package. Ordinary users do not enter environment variables. Follow the host’s normal flow for genuinely missing permission or system authentication; report a blocker if setup cannot proceed. See [dependencies and developer details](AGENT-SKILL.md#english).

Once connected, select **Reprise** and say “Open.” An empty list is normal; opening does not save or automatically add the current directory. Keep the complete package, not just SKILL.md. Preserve existing Skills and have the agent verify the actual version and entry.

### 2. Save before changing the site

In a conversation where the website project is already clear, say:

> Save this website draft as “Before changing the colors”, including its screenshot.

Check **files saved** and **picture captured** separately. Static HTML with a clear entry and local assets can attempt capture. Supported standalone npm/Vite projects save files first, then return an install-and-run plan. Approved commands run in a separate copy and may download project dependencies. Preparing Reprise’s tools does not approve website-project scripts. Approval for one draft does not approve future drafts; Next and other configurations still need run settings.

If capture is incomplete, the files may already be saved. Complete the same draft’s picture instead of saving again. Unchanged files may reuse an existing draft and title; read the actual result.

Change the colors, then save “After changing the colors”, including its screenshot. Reprise records only drafts you choose to save; it cannot recover content overwritten before saving.

### 3. Recover by its picture

Select Reprise and say “Open.” Recognize “Before changing the colors”, compare drafts if needed, and use **Recover this draft** to retrieve it into a new folder. Confirm the old colors in the copy while the original project keeps the new colors, then edit the copy.

Without a picture, file recovery remains available but the visual task is incomplete. Successful recovery does not guarantee working old dependencies or external services. See [workbench tasks](WORKSPACE-TASKS.md#english). Stop normally through your agent or workbench settings; closing the browser tab alone does not stop the service.

<details>
<summary>Developers: an existing base environment and source entry</summary>

Core operations need Python 3.9+ and Git, with no third-party Python package or pip installation for the core. Version 3.9 is the code minimum; choose a maintained official Python version for a new installation. Automatic capture also needs Node, the Node Playwright library and runnable Chromium or a verified compatible browser. The project pins Playwright 1.62.1, which requires Node 20+; supported LTS 22 or 24 is recommended for new installations.

The source Skill entry is:

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang en --no-browser
```

`doctor` checks Python/Git, the core and package integrity; it does not establish screenshot readiness. Use the actual returned local URL. A full development checkout can also use `python3 scripts/start_workbench.py` with the same core.

In a Reprise development checkout, prepare capture tools with `npm install` and `npx playwright install chromium` from Reprise’s own directory, not the managed website source. See [official sources and setup scope](AGENT-SKILL.md#english).

The code entry targets macOS/Linux (Windows via WSL); this does not establish native Windows or all-host verification. The source checkout’s `examples/recovery-tutorial/prepare.py` can create a sample at a new location. Earlier Python Skill / wheel instructions remain in the [historical quickstart](REFERENCE-QUICKSTART-20261024.md).

</details>
