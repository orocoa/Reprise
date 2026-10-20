# 用 AI agent 打开 Reprise

从 GitHub 下载完整 skill ZIP，交给本机 agent 打开，由 agent 使用当前项目或用户给出的路径直接打开。Reprise 无须安装成 App，也不依赖 Codex 账号、SDK 或专用浏览器工具。

## 下载与使用

- [通用 skill ZIP](https://github.com/orocoa/Reprise/releases/latest/download/reprise-skill.zip)：Codex、TRAE，以及支持本地脚本的 Agent Skills 客户端。
- [WorkBuddy skill ZIP](https://github.com/orocoa/Reprise/releases/latest/download/reprise-workbuddy.zip)：相同程序，附带 WorkBuddy 发布平台要求的描述与作者字段。
- [GitHub Releases](https://github.com/orocoa/Reprise/releases)：选择指定版本，校验 `SHA256SUMS.txt`。

解压后保留完整的 `reprise/` 目录，包括 `SKILL.md`、`scripts/` 和 `assets/`。只复制 `SKILL.md` 无法运行。本地需要 **Python 3.9+、Git、浏览器**，系统支持 macOS/Linux；Windows 请在 WSL 中运行，并使用可访问 WSL 本机服务的浏览器。

对 agent 说：

> 使用这个目录里的 Reprise skill，先检查环境，再打开当前工作区的 Git 项目。目录是「这里填写解压后的 reprise 路径」。

或者：

> 用 Reprise 打开「这里填写我的 Git 项目路径」，让我看历史和预览。

agent 执行 `scripts/reprise.py doctor` 后打开同一个 CLI。没有浏览器启动权限时加 `--no-browser`，把 JSON 中的 URL 交给用户。浏览器打开后，查看历史、比较文件、运行旧版和恢复均由本机 Reprise 服务处理，后续浏览无需持续调用 agent。

## 各客户端入口

| 客户端 | 安装 / 打开方式 | 验证范围 |
| --- | --- | --- |
| Codex | 将完整 `reprise/` 放到 `~/.agents/skills/` 或项目的 `.agents/skills/`，再调用 `$reprise`；已有同名技能时先选择单一版本，避免重复入口 | 通用格式、相对路径、独立运行包和本地 CLI；当前开发由 Codex 完成 |
| TRAE CN | 完整目录放到项目 `.trae/skills/reprise/` 或全局 `~/.trae-cn/skills/reprise/`，在对话中要求使用 Reprise；也可启用 `.agents/skills` 发现 | 对照官方规范；对应目录的独立运行包与 CLI 已测，客户端内调用待测 |
| WorkBuddy | 使用 `reprise-workbuddy.zip` 的技能导入入口，或解压后把 `SKILL.md` 路径交给本地 agent；保留全部资源 | 对照 Open Platform 必填字段；独立包与 CLI 已测，平台 ZIP 解析及客户端内调用待测 |
| 其他本地 agent | 读取完整目录的 `SKILL.md`，用本地命令工具执行脚本；原生技能目录按客户端说明选择 | 通用 Python CLI，不保证每个客户端的原生安装机制 |

规范相同不代表执行环境相同。只有云端容器的 agent 无法直接访问用户电脑上的项目，需要本地执行功能及文件权限。如果某客户端导入只保存指令，须把完整目录保留在本机并告诉 agent 实际脚本路径。

规范来源（2026-10-20）：[Agent Skills](https://agentskills.io/specification)、[Codex](https://learn.chatgpt.com/docs/build-skills)、[TRAE](https://docs.trae.cn/ide_skills)、[WorkBuddy](https://open.workbuddy.cn/en/docs/skill)。WorkBuddy ZIP 只有前置元数据有差异，其余代码和资源共用同一构建源。

## 项目里的完整流程

1. 在目标项目目录中要求 agent 打开 Reprise，或直接提供仓库路径。支持普通仓库、裸仓库和 worktree；无须在界面再次选择。导入不安装或执行代码。
2. 选择提交查看文件和父子关系。空仓库显示空状态；缺失的历史对象和资源明确提示。
3. 静态网页选择识别入口，保存配置后运行独立副本。其他类型需核对并保存命令配方；命令以当前用户权限执行。预览可新标签打开或手动嵌入。自动截图和录屏另需 Node/Playwright。
4. 点击「恢复 / 导出」。恢复要求一个尚不存在、位于源仓库外的新目录；下载 ZIP 无须填写目录。两者按完整 SHA 读取并校验 Git blob，保留执行权限及安全的内部符号链接。
5. 结果是**文件快照**，不含 `.git` 历史；子模块不会自动下载，LFS 指针不会伪装成真实大文件。任务提供路径或下载链接，取消或失败的输出和记录继续保留。

默认资料目录在 macOS `~/Library/Application Support/Reprise`、Linux `$XDG_DATA_HOME/reprise`（未设置时 `~/.local/share/reprise`）。`--data` 可指定其他外部目录。项目、说明、配方和证据保存在本机，更新 skill 不替换这些资料。关闭标签页不会停止服务；需要时执行 `shutdown`，自定义资料目录必须一致。

## 不使用 agent

在解压后的目录运行，同样不需要 pip 安装：

```sh
python3 /path/to/reprise/scripts/reprise.py doctor
python3 /path/to/reprise/scripts/reprise.py open .
python3 /path/to/reprise/scripts/reprise.py open /path/to/my-project
python3 /path/to/reprise/scripts/reprise.py shutdown
```

完整 GitHub 源码也能运行 `python3 run.py open` 或 `python3 skills/reprise/scripts/reprise.py open`。只复制 skill 子目录的第三方安装器会缺少运行代码，请使用自包含 release ZIP。

维护者从同一源码生成两个包，不维护两套运行代码：

```sh
python3 scripts/build_skill.py --output work/releases/reprise-skill.zip
python3 scripts/build_skill.py --profile workbuddy --output work/releases/reprise-workbuddy.zip
```

打包只收集 skill 源、`src/reprise/`、`web/` 和许可文件，生成逐文件 SHA-256 manifest；不包含项目、注册表、证据、密钥、模型配置或 `work/`。已有目标不覆盖，请用新路径。`doctor` 检查环境及全部清单文件。
