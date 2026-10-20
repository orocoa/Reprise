# Reprise · 倒带 — Local Git History Browser

给 Git 历史一个可浏览的读档界面。翻更新说明和已有预览，找印象里的旧页面；沿真实版本路线查看分叉与合并，比较任意两版的页面资料与文件变化。配好对应的运行方式后，还能在独立副本里打开历史页面。

版本来自已有 Git 记录。预览需要生成或导入，并绑定对应版本；更新说明可手工编辑，也可选择接入 AI。核心只依赖 Python 标准库与 Git，浏览、比较和运行不需要 AI。

Reprise is a local Git history browser for comparing commits and files, previewing configured versions in separate copies, and restoring or exporting snapshots. Core history and diff workflows need Python and Git; they do not require an AI connection.

**Get started:** [Install the agent skill](docs/AGENT-SKILL.md) · [Command-line setup](#command-line-setup). Requires Python 3.9+ and Git. Previewing a historical page also requires that version's dependencies and an approved runtime configuration.

## 用 skill 打开（推荐）

从 GitHub 下载 [通用 skill](https://github.com/orocoa/Reprise/releases/latest/download/reprise-skill.zip) 或 [WorkBuddy skill](https://github.com/orocoa/Reprise/releases/latest/download/reprise-workbuddy.zip)，保留完整的 `reprise/` 目录，让本机 agent 按其中的 `SKILL.md` 打开。适用于 Codex、TRAE 等本地脚本入口；WorkBuddy 包增加其平台元数据。需要 Python 3.9+ 和 Git，无须 pip 安装或原生 App。

在目标项目里发命令，或告诉 agent 项目路径，即可直接打开历史、比较文件、配置独立预览，或把所选提交恢复到新目录 / 下载 ZIP。程序独立于 agent；[安装路径、兼容范围与完整流程](docs/AGENT-SKILL.md) 包含已测和待验证的部分。

<a id="command-line-setup"></a>

## 命令行启动（可选）

需要 Python 3.9+ 和 Git。macOS/Linux 的回归、浏览器与安装检查见 [GitHub Actions](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)。Git 读取与 Web 工作台使用 Python 标准库。

从 GitHub 获取并安装命令：

```sh
git clone https://github.com/orocoa/Reprise.git
python3 -m venv ~/.venvs/reprise
~/.venvs/reprise/bin/python -m pip install ./Reprise
source ~/.venvs/reprise/bin/activate
```

随后进入要查看的 Git 仓库，执行下面的命令。每个新终端先激活上面的环境；AI 或脚本也可以直接调用 `~/.venvs/reprise/bin/reprise`。

安装命令后，在平时执行 Git 的仓库目录中直接打开：

```sh
reprise .
# open 默认使用当前项目目录
reprise open
```

已有安装可更新 Reprise 的源码目录，再重装同一个环境。先用 `reprise shutdown` 停止旧服务，随后重新运行 `reprise .`；本机版本说明、配置与预览继续保留。

```sh
git -C /path/to/Reprise pull --ff-only
~/.venvs/reprise/bin/python -m pip install --upgrade /path/to/Reprise
```

它只读导入当前仓库，启动或复用本机 Reprise 服务，并打开该项目页面。数据目录在 macOS 的 `~/Library/Application Support/Reprise` 或 Linux 的 `$XDG_DATA_HOME/reprise`，需位于导入仓库之外。可以传入其他仓库路径；默认由系统分配空闲端口，显式指定但被占用的端口自动回退。AI 或脚本可以省略浏览器，读取 JSON 中的 URL、项目 ID 与停止命令：

```sh
reprise . --no-browser --lang en
reprise shutdown
```

`shutdown` 仅停止身份已核验的本机服务及其自有任务/预览，保留全部副本、日志和证据。不同 `--data` 目录互相独立；关闭时应传入相同 `--data`。原有手动常驻服务可先退出，再由命令入口管理。

当前开发阶段无需封装成 App。一次安装源码命令入口后，可在任意 Git 仓库中使用上面的指令：

```sh
python3 -m pip install -e /absolute/path/to/Reprise
```

未安装时，使用源码的绝对路径：

```sh
python3 /absolute/path/to/Reprise/run.py . --no-browser
```

也保留手动服务与独立的只读 Git 指令：

```sh
python3 run.py serve --port 51582
python3 run.py --data /path/to/reprise-data import /path/to/project
python3 run.py history /path/to/project --limit 20
python3 run.py detect /path/to/project --ref HEAD
```

0.4.0 提供真实 Git 彩色路线、详细视图与 32px 紧凑视图、收藏定位，以及「本次更新 / 版本预览 / 版本对比」。缺少预览时可直接进入添加资料；运行记录显示独立副本和日志目录，安装、构建与启动阶段使用任务取消，服务就绪后才提供打开与停止。项目名与正文统一使用 Inter，中文使用系统字体；按钮采用胶囊与圆形图标，编辑入口为无框铅笔。项目、提交、运行和媒体来自同一通用核心。支持中文/英文界面；Git 原始消息、路径、代码和手工资料标题保留原文。AI 提案一次生成中英标题、摘要及变化说明；显式保存后绑定完整 SHA，切换语言和重启不再请求模型。双语说明保存与运行配方批准是两个独立操作。

所有创建的副本、失败日志和证据均保留，停止服务不会删除它们。不要将带有 AI 密钥的应用数据目录提交到 Git。

### 安装发行包

收到 wheel 后，建议安装到独立 Python 环境；命令可在源码目录之外执行：

```sh
python3 -m venv /path/to/reprise-venv
/path/to/reprise-venv/bin/python -m pip install /path/to/reprise_local-0.3.1-py3-none-any.whl
/path/to/reprise-venv/bin/reprise /path/to/project
```

也支持允许用户安装的基础 Python 环境，使用模块入口可以避免命令目录未加入 PATH 的问题：

```sh
python3 -m pip install --user /path/to/reprise_local-0.3.1-py3-none-any.whl
python3 -m reprise /path/to/project
```

wheel 内含工作台网页和采集 worker，运行不依赖原源码位置；`web/` 是唯一的前端编辑源，构建时映射到包内资源。源码发行包另含 `run.py`、浏览器依赖清单、示例、迁移脚本及文档。Git 使用本机已安装的可执行程序；基础安装不需要 Node 或浏览器采集依赖。

## 自动截图：无需 AI

仅在需要自动采集时，准备 Node.js 并安装浏览器依赖。在源码目录中使用：

```sh
npm install
npx playwright install chromium
```

如果安装的是 wheel，可将浏览器依赖放在独立目录，显式指定模块位置：

```sh
npm install --prefix /path/to/reprise-browser playwright@1.62.1
node /path/to/reprise-browser/node_modules/playwright/cli.js install chromium
export REPRISE_PLAYWRIGHT=/path/to/reprise-browser/node_modules/playwright/index.mjs
```

在同一终端启动 `reprise`，使它继承此环境变量。Linux 上 Chromium 所需的系统库由宿主系统提供；安装说明及缺失诊断以所用 Playwright 版本为准。

随后在工作台选择版本，打开右上角设置中的「添加预览资料」，点击「生成此版本预览」。也可以指定已有运行环境：

- `REPRISE_NODE`：Node 可执行文件。
- `REPRISE_PLAYWRIGHT`：Playwright ESM 入口或包名。
- `REPRISE_BROWSER`：Chromium / Chrome 可执行文件；省略时用 Playwright 安装的 Chromium。

环境缺失会产生明确的失败记录，Git 功能继续可用。普通静态站点自动识别入口；项目已有 `.reprise.json` 可定义路由、视口、就绪选择器、点击、键盘、填表、截图和录像。当前默认图片使用 2× 像素。录屏采用浏览器视频尺寸，单独记录尺寸，不冒充图片分辨率。

需安装、构建或启动开发服务的项目，使用 `command-web` 配方，先核对并保存，再点击运行/采集。保存不执行命令，导入不安装依赖。命令以 argv 运行，无隐式 shell；这是本机代码执行，不是容器隔离。`network: local` 只限制**采集浏览器**到当前预览来源，不限制用户批准的安装/构建命令。

## 不同项目如何显示

| 项目 | Git 历史/差异 | 运行与预览 |
|---|---|---|
| 普通静态 HTML / 已提交的构建产物 | 原生读取 | 自动发现入口，直接截图 |
| Canvas / WebGL / 浏览器游戏 | 原生读取 | 网页配方；固定操作、截图、WebM 录屏 |
| React / Vite / Next / Python Web 等源码 | 原生读取 | 识别清单，配置安装、构建、启动及就绪条件 |
| monorepo / 多个网页入口 | 原生读取 | 显示候选根目录，由配方选择运行目标 |
| Unity / Godot / Unreal / 原生应用 | 原生读取 | 识别引擎；当前导入手工截图、录屏、构建文件；Web 导出可用网页配方 |
| CLI / 库 / 文档 / 未知类型 | 原生读取 | 文件变化始终可看；导入文本结果或其他人工证据 |

不能保证任意历史版本都能运行：它可能缺少构建依赖、LFS 大文件、子模块内容、私有 API 或当年的运行环境。系统保留真实 Git 事实，明确标出缺失条件，不用别的版本截图补空白。

## 比较任意版本与取消任务

从仓库启动后，在「版本对比」选择基准 A 和目标 B，即自动比较；中间的交换图标可交换方向。普通界面不显示 SHA、分支或标签。文件变化按所选两版计算，预览各自绑定完整版本标识，缺失时显示「没有预览」。

「本次更新」优先展示真实图片或视频；相同采集场景与真实父版本能成对显示，并放大变化区域。图片使用透明底、20px 圆角描边，点击放大图标查看原图。没有匹配视觉资料时才显示文件与代码变化。标题旁铅笔编辑名称和简介，更新说明旁铅笔只编辑更新内容。

右上角设置集中管理语言、AI、当前版本运行配置、添加预览、服务停止及任务进度。收藏可跨刷新保存，收藏定位时保留其他关系节点；紧凑与详细视图使用同一组真实版本。独立 Git 历史明确标注，无虚构父子连接。

需要关联同一项目的历史存档时，显式提供只读来源与可选目录：

```sh
reprise . --history /path/to/related/archive.git --history-catalog /path/to/catalog.json
```

存档必须与当前仓库有共同提交；完整 SHA 去重，目录可排除资料提交。历史关联存入本机数据，后续启动继续复用，不修改源仓库。

「项目配置」现在只保存到当前提交，其他版本需分别确认。旧的项目级配置仍保留为草稿，可在配置对话框载入。运行/采集任务提供「取消任务」；取消会停止自有进程并保留副本、日志与部分产物。命令行可用 `reprise --data /path/to/data cancel JOB_ID`，前台运行/采集也可按 Ctrl+C。

损坏的单条任务记录会显示提示并保留原文件，其他任务和工作台继续可用。

采集部分完成、失败或取消时，已有成果会更新到对应版本；在版本预览或设置中展开「查看采集诊断」，可查看具体原因和本机日志位置。普通文件使用独立链接，图片与视频进入媒体查看器。服务异常退出后，未完成的运行会显示中断状态；确认归属的残留进程可在设置中停止，无法核验的情况会保留记录并说明原因。

## AI 的位置

当前发行范围是本地命令行基础版。AI 兼容接口可选；Codex app-server 专用接入仍在计划中，未实现，不属于基础版发布条件。AI 可以直接调用 `reprise . --no-browser` 获取页面地址。

AI 默认关闭。设置里填入兼容 Chat Completions 的 HTTPS 端点、模型原名与密钥；本机端点可用 HTTP。只有点击「AI 建议配置」才发送当前提交中有限的清单文件、路径及变更文件名，不发送未提交文件或整个仓库。模型保持用户指定值，不自动替换。

返回的 JSON 经过配方和文件依据校验，只成为待审核提案。用户可编辑并保存到项目配置，然后仍由确定性的运行/采集系统执行。AI 没有直接执行命令、提交 Git、删除副本或伪造证据的接口。密钥存储为权限 `0600` 的本地设置，API 不返回密钥。未配置、模型失败或输出无效不会阻塞核心功能。

## 配方和扩展

- [架构与数据流](docs/ARCHITECTURE.md)
- [Git 版本关系图：功能、逻辑、实现与回归契约](docs/GIT-GRAPH.md)
- [配方与采集说明](docs/RECIPES.md)
- [边界、迁移及验证](docs/VALIDATION.md)
- [模块与 HTTP 接口](docs/implementation-contract.md)
- `examples/`：静态站点、可操作 Canvas 游戏、Python CLI、命令型网页配方。
- `python3 scripts/create_demo_projects.py`：在 `work/` 新建三组独立 Git 示例，各含两次提交；不会改已有项目。

## 验证

[发布验收范围](docs/RELEASE-CHECKLIST.md) 覆盖 macOS/Linux 回归、Git 图与缓存契约、浏览器和全新环境安装检查。每次发布以对应提交的 [CI 实际结果](https://github.com/orocoa/Reprise/actions/workflows/ci.yml) 为准。

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
REPRISE_BROWSER_TESTS=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

第二条需要浏览器依赖，可结合上面的环境变量。真实浏览器测试把截图、录像、运行副本和诊断保留在 `work/test-artifacts/`。

发行包检查使用已有 `setuptools>=61` 和 `wheel` 的基础 Python 解释器：

```sh
python3 scripts/check_distribution.py
```

检查过程不联网：先在保留的源码副本中构建 wheel 和源码包，再由源码包重建 wheel，分别装入全新 venv 和独立用户目录，从构建源码目录外启动，验证命令入口、网页内容及 API。报告、构建包、安装环境和失败日志均保存在 `work/test-artifacts/distribution-*/`。它不代替真实浏览器采集测试。

## 已确认的视觉档案

代码采用 [MIT 许可证](LICENSE)。字体与图标保留各自原许可，见 [第三方说明](THIRD-PARTY-NOTICES.md)；导入的仓库和人工媒体保留原权属。

[Reprise Paper Grid · 白纸线框](docs/visual-archives/reprise-paper-grid-2026-10-08/index.html) 保存了用户在 2026-10-08 确认的排版、VI、交互状态与动画，包括必要时竖线并入真实右边框的最终规则。档案保留原样源码、真实截图、动画片段、原始参考录屏、独立交互演示与通用复用示例；视觉规范见 [DESIGN.md](docs/visual-archives/reprise-paper-grid-2026-10-08/DESIGN.md)。

这是可用于其他项目的冻结基准。Reprise 后续采用其他视觉时保留此目录，不用新样式覆盖这次记录；跨项目可调用个人技能 `$reprise-paper-grid`。

## 数据备份与升级

先用同一数据目录执行 `reprise shutdown`，等它确认任务和预览已退出，再完整复制应用数据目录到一个新的备份位置。需保留 `projects.json`、任务、运行副本、所有媒体、配置和日志；其中可能含 API 密钥，备份应保持私有。源 Git 仓库需要另行备份，Reprise 数据不是仓库备份。

升级时替换或重新安装 Reprise 代码，继续指定原数据目录；不要覆盖或删除应用数据。还原时把备份复制到一个新的目录，再用 `reprise --data /path/to/restored-data .` 打开。项目路径在另一台电脑上可能不可用，此时按实际路径重新导入，不会自动移动源文件或伪造历史媒体。旧单语 AI 提案保留，重新请求才能得到双语提案；已有运行配方不自动执行。
