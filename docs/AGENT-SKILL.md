# 通过 agent 使用倒带 / Reprise

当前为 [Reprise 0.8.0](https://github.com/orocoa/Reprise/releases/tag/v0.8.0)。主附件 `Reprise-Skill.zip` 包含脚本、核心源码和工作台。

## 接入一次，之后说“打开”

将完整源码 Skill 包交给有本机文件和命令执行能力的 agent：

> 帮我接入倒带 / Reprise。先检查并复用已有环境，缺少的依赖按官方方法和当前授权安装，然后打开。

导入或复制时保留 `SKILL.md`、`scripts/`、`assets/` 和参考文件；脚本从包内定位固定核心，不要求你手工拼备份逻辑或填写环境变量。agent 核对客户端真正支持的 Skill 位置或导入面板，不猜路径、不覆盖已有技能。仅上传一份 SKILL.md 不足以运行。

接入后选择 **Reprise Skill**，说“打开”。只打开工作台，不导入或保存当前目录。要留一稿时再说“保存当前网页这一稿”，复用对话中已明确的项目。项目不明确时才询问位置。

Skill 标识为 `reprise`，“倒带”是中文产品名。显示名不等于注册了通用 `@倒带` / `@Reprise` 别名；选择方式由实际客户端决定。沿用对话中英文，不翻译用户标题和文件路径，也不配置另一套 AI Key 或模型。

## 少说几次，沿用项目

在当前网页目录已明确时，可以说“本轮修改前后都帮我留稿”。Agent 在开始修改前和本轮结束后各保存一次，名称按任务简短生成；只打开不会保存。已批准的安装继续完成，不因每个包重复询问；真正缺少许可时按宿主流程处理。

首次为网页项目留稿时，只问一次以后是否一起保存画面，并立即按项目保存答案。配置尚未就绪也保留选择；确认实际运行配置后，后续普通保存持续沿用。完整新副本取回后，使用回执中的实际目录继续编辑。截图偏好不等于后台自动记录每次修改。

工作台提供直接/快捷键留稿和可复制的继续修改指令。[完整范围](FEATURES.md)

## 看已有 Git 版本关系

明确要查看仓库历史时，用 `python3 /absolute/path/reprise/scripts/reprise.py open /known/repository --lang zh --no-browser`，并打开实际返回的 URL。工作台保留「画面」与「版本关系」，可按图片或真实 Git 分叉、合并选中旧版并取回副本。不会替用户提交或改变暂存区。

`save` 保存当前文件为文件夹稿件；`snapshot` 与 `preview-preferences` 只用于文件夹项目。不要对 Git 历史项目调用这两个命令。同一目录可分别查看已有 Git 历史与保存文件夹稿件，身份和来源独立。

## agent 先复用，再补缺项

| 任务 | 必需环境 | 检查边界 |
| --- | --- | --- |
| 打开工作台、保存、历史与恢复 | Python 3.9+、可运行的 Git；看工作台还需网页浏览器 | 普通文件夹也使用 Reprise 内部 Git 存储。Python 核心只用标准库，无须为核心 pip install。 |
| 自动网页截图 | 再加 Node、Node 版 Playwright 和匹配的 Chromium，或已实际验证的兼容浏览器 | 项目锁定 Playwright 1.62.1，要求 Node 20+；新装选择受支持的 LTS 22/24。不是 Python Playwright，也不需要创建 Playwright 测试项目。 |
| Vite 等需运行项目的画面 | 截图环境，加该网页自己的依赖和已确认配方 | 项目安装/运行命令另行明确批准，在独立副本执行；准备 Reprise 工具不等于批准网页脚本。 |

Python 3.9 是代码最低要求，不是新装推荐；选择官方仍维护的版本。agent 先检查宿主公开提供或当前可用的工具，核对版本和可运行性。比如某台 Codex 已有依赖，不代表所有 Codex、WorkBuddy 或 TRAE 都提供同一能力。

缺少时，agent 给出具体安装方案，在任务已有授权和宿主正常许可下继续，复用已有安装授权，不额外要求逐包确认；需要系统认证、管理员操作、网络或额外命令许可时，按真实流程处理。工具安装在 Reprise 自己的用户级位置，不写进受管网页源仓库，不默默改全局 shell、模型或权限设置。已核实的工具路径由 agent 用于当前命令，普通用户不需要手填环境变量。没有安装权限时说明缺项，基础文件操作仍可在其依赖齐全时进行。

官方来源（2026-10-24 核对）：[Python 下载](https://www.python.org/downloads/)、[Git 安装](https://git-scm.com/install/)、[Node 下载](https://nodejs.org/en/download)、[Playwright Node library](https://playwright.dev/docs/library)、[浏览器版本与安装](https://playwright.dev/docs/browsers)。选择已有成熟工具，不临时编写跨系统安装器；安装请求发出不等于已安装成功。

自动截图还需要宿主允许创建本地服务、启动并观察自己的子进程。Skill 不授予系统权限。若当前环境禁止必要检查，明确报告并停止相关操作；使用宿主针对本次命令的正常许可流程，不改模型、全局或临时线程权限，不重复保存来重试画面。

## 固定源码入口与结果

agent 使用已安装 Skill 的绝对 `scripts/reprise.py` 路径：

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang zh --no-browser
python3 /absolute/path/reprise/scripts/reprise.py save /known/webpage --title "改颜色之前" --capture-static
```

英文打开显式传 `--lang en`。只打开使用 `open --workbench`，不猜当前目录。`doctor` 检查 Python/Git、核心与包完整性，**不代表 Node、Playwright 或截图浏览器已经可用**；画面必须以实际采集结果判断。

普通“保存这一稿”沿用已有截图偏好，不自动加截图请求。明确要求本稿画面时，按包内 Skill 规则处理一次性采集；已批准 auto 继续用其模板。成功一次不会开启未来自动截图。

文件已保存与画面完成分别回报。缺图不借用另一稿；截图失败不重复保存同样文件。文件未变时可复用旧稿及标题，不能声称新名字已创建。恢复取到新目录，保留当前项目。完整参数和边界以实际包内 Skill 为准，操作细节见[工作台任务](WORKSPACE-TASKS.md)。

## 客户端接入与当前证据

| 客户端 | 官方机制 | 本候选的验证范围 |
| --- | --- | --- |
| Codex | 用户 `~/.agents/skills/reprise` 或项目 `.agents/skills/reprise`；CLI / IDE 支持 `/skills` 或 `$`，桌面以实际入口为准 | 最终 Skill 已安装到本机 Codex，发现接口确认单一入口启用；实际保存两稿及画面，并在工作台按图恢复。原生选择器/输入框及所有权限模式没有因此通过。 |
| TRAE CN | 用户 `~/.trae-cn/skills/reprise` 或项目 `.trae/skills/reprise`；支持面板导入与自然语言点名 | 本机 3.4.4 已安装，原生操作按用户安排延期。需核对导入后脚本与 assets 保留。 |
| WorkBuddy | 技能页“添加技能 → 上传技能”，再按实际对话入口调用 | 本机 5.8.3 已安装，原生操作延期；本地上传与市场提交是不同接口，不据格式声明保证完整运行。 |

来源：[OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)、[TRAE Skills](https://docs.trae.cn/ide_skills)、[WorkBuddy 技能](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[WorkBuddy 平台字段](https://open.workbuddy.cn/docs/skill)。OpenAI 文档将 ChatGPT 的 `@` 与 Codex CLI/IDE 的入口分别说明，不能泛化成每个桌面版本都支持同一别名。

本机源码 Skill 证明使用现成的 Codex Python/Git/Node/Playwright 和已有 Chrome，没有新装依赖或修改配置；它只证明这台机器的这组环境可用，不是全新 Mac 自动安装、跨客户端自动截图或外部用户独立成功。较早其他分发路线的诊断仅作历史记录，不作为本次接入步骤。

## English

Use one explicit request for this editing task: “Save a draft before and after this edit.” Reuse the known folder, approved image preference and short task-based names. The before/after save request is limited to this editing task. The image choice is asked once per project, persisted before capture/configuration finishes, and reused on later saves. This does not enable background recording. After a whole-draft recovery, use the actual new folder in the continuation instruction. Local source shortcuts and copyable continuation instructions are unreleased; public v0.8.0-rc.1 downloads remain unchanged. [Feature scope](FEATURES.en.md)


The **0.8.0 source Skill**, delivered as `Reprise-Skill.zip`, is the primary path: keep its scripts, fixed source core, web UI and resources together. Give the full Skill package to a local agent, ask it to check and reuse the environment, install missing tools using official methods and current authorization, then open Reprise. Import must retain `scripts/` and `assets/`; SKILL.md alone is insufficient. Preserve existing Skills and verify the actual client entry.

For existing Git history, use `open /known/repository --lang en --no-browser`. Its picture and relationship views preserve real commits, branches, merges and exact-version images. Folder saves are a separate project kind; `snapshot` and capture preferences apply only to folder projects. Neither entry creates a source Git commit.

After setup, select Reprise and say **“Open.”** Opening does not import or save the current directory. Save only when requested, using the established project. The identifier is `reprise`; the Chinese name does not register a universal `@` alias. Follow the conversation language without translating titles or paths, adding an AI key, or changing models.

| Task | Required environment | Limits |
| --- | --- | --- |
| Workbench, saving, history and recovery | Python 3.9+, runnable Git and a browser for the UI | Folder snapshots also use internal Git. The Python core uses the standard library and needs no pip package. |
| Automatic pictures | Node, the Node Playwright library and matching Chromium or a verified compatible browser | Playwright 1.62.1 requires Node 20+; supported LTS 22/24 is recommended for new installations. This is not Python Playwright or a test-project scaffold. |
| Build-based website pictures | Capture tools plus project dependencies and an approved recipe | Website scripts require separate approval and run in an independent copy. Tool setup does not approve project commands. |

Version 3.9 is the Python code minimum, not a fresh-install recommendation. The agent first verifies available host tools and versions. If anything is missing, it reuses existing installation authorization and uses official installers or mature supported methods through normal authorization, without demanding confirmation for every package, in a Reprise-specific location outside the managed website source. Ordinary users do not enter environment variables; the agent passes verified tool paths for the current command without changing global shell, model or permission settings. Authentication, administrator interaction, network and command access remain real limits. Not every agent can install tools. Installation requests are not proof of completion.

Official sources: [Python](https://www.python.org/downloads/), [Git](https://git-scm.com/install/), [Node](https://nodejs.org/en/download), [Playwright library](https://playwright.dev/docs/library) and [browser installation](https://playwright.dev/docs/browsers). Local services and subprocess identity checks also need normal host permission; if unavailable, report the boundary rather than changing settings or repeatedly saving/capturing.

Use the source Skill’s absolute entry:

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang en --no-browser
python3 /absolute/path/reprise/scripts/reprise.py save /known/webpage --title "Before changing the colors" --capture-static
```

`doctor` checks Python/Git, core and package integrity, not screenshot readiness. Ordinary saves retain the existing picture preference; explicit picture requests follow the packaged Skill’s rules. A successful capture does not enable future automatic capture. Report saved files and captured pictures separately, retain missing-picture status, and recover into a new folder. Unchanged files can reuse the existing title; do not claim a requested new title was created. See [workbench tasks](WORKSPACE-TASKS.md#english).

| Client | Documented mechanism | Candidate evidence |
| --- | --- | --- |
| Codex | User `~/.agents/skills/reprise` or project `.agents/skills/reprise`; CLI/IDE `/skills` or `$`; desktop uses its actual entry | The final Skill was installed and discovered as one enabled entry in this Mac’s Codex. Actual draft/picture calls and browser recovery passed. Native selector/composer actions and every permission profile are not established by this evidence. |
| TRAE CN | User `~/.trae-cn/skills/reprise` or project `.trae/skills/reprise`; panel import and natural-language invocation | Version 3.4.4 is installed here; native operations are deferred. Check that import retains scripts and assets. |
| WorkBuddy | Add/upload a local Skill, then invoke it through the actual conversation entry | Version 5.8.3 is installed here; native operations are deferred. Market metadata and local import are separate contracts. |

Client sources: [OpenAI](https://learn.chatgpt.com/docs/build-skills), [TRAE](https://docs.trae.cn/ide_skills), [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market) and [platform fields](https://open.workbuddy.cn/docs/skill). Do not infer a universal `@` prefix.

The host-source proof reused this Mac’s existing Codex Python/Git/Node/Playwright and Chrome, with no installation or configuration change. It does not establish fresh-Mac setup, automatic discovery in every agent, cross-client screenshots or independent adoption.
