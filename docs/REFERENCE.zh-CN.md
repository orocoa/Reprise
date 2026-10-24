# Reprise 完整参考

> 本页保留 2026-10-24 README 的完整功能与命令说明，阅读入口已移到[简明首页](../README.md)和[快速上手](QUICKSTART.md)。正文从源码根目录运行命令。除特别标明的公开 v0.4.1 外，功能说明属于尚未公开发布的 0.7.0 本地候选版。旧版安装命令仅用于取得该公开版本，不会取得候选版的新功能。

本地 0.7.0 候选版新增完整的版本整理流程：选版 → 看截图或运行 → 核对删除损失与共同引用 → 明确删除 → 核验保留版本与实际存储变化。运行环境可另行预检、释放并在需要时重建。原文件夹保持原样。

默认先体验保留三稿的工作台：`python3 scripts/prepare_lifecycle_demo.py --to /new/path/reprise-interactive`。在候选源码根目录执行，并选择尚不存在的目标路径；脚本会准备三个可运行版本，保留全部版本与环境，不读取真实项目。

完成后按 `summary.json` 中的 `open_command` 打开，查看、比较并预检删除影响，保留样本供继续操作。详细操作和边界见 [版本生命周期](VERSION-LIFECYCLE.md)。此候选版尚未公开发布。

[English](../README.en.md) · [上手演示](#用样本完成一次保存与恢复) · [反馈真实使用](https://github.com/orocoa/Reprise/issues/new/choose) · [参与项目](../CONTRIBUTING.md)

**把本地项目的版本、变化与恢复结果放在同一工作台，找对一版，再把它取回。**

适合需要反复回看网页版本、比较文件或取回创作资料的人。有 Git 时读取真实提交；普通文件夹可主动保存版本，源文件夹无需初始化 Git。恢复写入新目录，方便对照原文件。

> **版本范围（2026-10-24；公开版本核验于 10-23）**：本 README 对应 **0.7.0 本地开发候选版**。公开的 [v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) 提供 Git 历史工作台，尚不包含这里的普通文件夹、备份与迁移功能。下方样本演示需要包含 `scripts/demo_workflow.py` 的开发源码；公开 `latest` 下载不代表这些能力已经发布。

| 想完成的事 | 本地开发候选版 |
| --- | --- |
| 保存文件夹的一稿、二稿，再找出变化 | 主动快照、比较、完全相同内容共享存储 |
| 看懂已有 Git 历史，找到一版网页 | 真实提交与父子关系；预览须另行生成/导入并绑定版本 |
| 取回文件，并确认内容一致 | 恢复到新目录，逐项读回校验；文件恢复不等于程序可运行 |
| 看重复副本与占用，为整理做准备 | 只读整理预检、恢复核对后的候选与选择清单、数据目录占用账本；副本整理清单不执行源文件删除，已管理版本的显式删除另见生命周期说明 |
| 备份已管理数据，调整项目路径 | 备份检查、新目录恢复、重新关联与复制迁移；外部源 Git 等另列范围 |

没有自动保存、云端同步、全盘清理或内存优化。基础流程需要 **Python 3.9+ 和 Git**；当前宿主范围为 macOS/Linux，具体版本的平台验证见 [发布检查](RELEASE-CHECKLIST.md)。

## 用样本完成一次保存与恢复

预留约 5 分钟体验；这是教程目标，首次环境准备与实际耗时取决于你的电脑。在包含演示脚本的 0.7.0 候选源码根目录执行，目标路径必须尚不存在：

```sh
python3 scripts/demo_workflow.py --to "$HOME/reprise-first-demo"
```

脚本创建纯样本文件夹与独立数据目录，保存两版、比较差异、恢复第一版并核对字节，随后生成重复项和占用报告。全部演示文件留在指定目录，不读取你的真实项目，不启动服务，也不删除文件。再次体验请换一个新路径。

打开结果目录中的 `README-local.txt` 看步骤和结果，`summary.json` 保存版本标识与检查摘要。成功表示该样本流程通过；它不证明其他数据、跨设备备份或实际空间释放。如果想继续看工作台，按结果文件中的命令打开同一份样本数据。

已经有真实任务，可从 [Skill 的安装与使用](AGENT-SKILL.md) 进入。遇到阻塞，请在 [问题与使用反馈](https://github.com/orocoa/Reprise/issues/new/choose) 描述“想做什么、卡在哪里、原来怎么做”；无需上传私人文件、完整路径或日志。结果有帮助时，欢迎 Star 收藏。

## 完整功能与使用说明

面向电脑端的本地版本管理器：有 Git 更好，没有 Git 也能保存文件夹版本。保存内容、查看变化、识别重复副本，并把需要的版本恢复到新目录。Git 项目继续沿真实路线查看分叉与合并、浏览已有预览；配好运行方式后，也能在独立副本里打开历史页面。

版本来自已有 Git 记录或主动保存的文件夹快照。预览需要生成或导入，并绑定对应版本；更新说明可手工编辑，也可选择接入 AI。核心只依赖 Python 标准库与 Git，基础版本功能不需要 AI；普通文件夹无需建立 Git 仓库，当前仍需 Git 程序作为内部存储工具。

普通文件夹也可以使用：点击「项目 → 加入文件夹」，再点击「记录版本」。文件夹快照与 Git 提交共用版本浏览、文件比较和恢复界面；原文件夹不会被初始化成 Git 仓库。已有 Git 项目继续读取其真实历史，导入和预览不会替用户提交改动。

本体与 Skill 共用同一核心，旧的名称归档也接入统一恢复适配器。快速保存：`python3 run.py save /path/to/folder --title "第二稿"`。`organize PROJECT` 先完整恢复快照并逐项读回校验，再显示重复副本；选择保存为待执行清单，尚不删除文件。默认返回摘要，完整清单可用 `review PLAN --details` 查看。

[本地数据与隐私](PRIVACY.md)：基础版本操作不调用 AI、不自动上传；版本库保存原始内容且未加密。通过 AI 代理调用 Skill 时，工具输出可能进入模型上下文。可用 `privacy` 或工作台中的「本地数据与隐私」查看范围、排除规则和实际保存位置。

在「项目设置 → 存储与校验」查看本机数据目录的占用账本，或检查选中文件夹版本的清单与已存内容。CLI 使用 `python3 run.py storage` 和 `python3 run.py verify --project "资料" --ref FULL_SHA`。内容检查不生成恢复副本，不代表独立备份、实际恢复演练或其他历史版本也已通过；真实恢复继续逐文件读回核对。占用账本只扫描 Reprise 数据目录元数据，不统计外部源目录或外部恢复目标；文件分配块不等于 APFS 独占空间或实际可释放量。

相同文件内容在本机共享内容库中只保存一次，不同文件名、目录和版本各自保留。首次记录读取文件；以后根据文件身份、大小、权限和纳秒修改/变更时间筛选需要重新读取的内容，读取期间再次检查变动。版本页显示内容字节统计和重复文件组，可在「全部文件」搜索文件并恢复单个文件，也可恢复/导出整个版本。恢复只写新目录，不覆盖原文件。

当前保存位置是本机 Reprise 数据目录，**没有云端同步或自动删除源文件**；已管理版本只能在明确确认后删除；已记录版本不表示已经上传。原文件夹不可用时，仍可从本机内容库恢复。文件级去重仅合并完全相同的字节，不自动合并相似文章，也不解包重写原始 ZIP。恢复保留普通文件内容、权限、修改时间、扩展属性、安全相对符号链接和空目录；不声称完整还原ACL、文件系统标志和所有者。`.git` 元数据不进入普通文件夹快照，并明确列出排除项。普通文件夹恢复按块读取并检查可用空间；Git 导入保留原有单次恢复 4 GiB 的默认限制。文件夹版本清单上限为 32 MiB；超出时会明确要求拆分项目，不发布不完整版本。

```sh
python3 run.py open /path/to/documents --folder --no-browser
python3 run.py import /path/to/documents --folder
python3 run.py snapshot PROJECT_ID --title "第二稿"
python3 run.py restore PROJECT_ID --sha VERSION_SHA --path notes/draft.md --to /new/recovered-folder
```

## 用 skill 打开（推荐）

公开 v0.4.1 仅含 Git 历史工作台；从 GitHub 下载它的 [通用 skill](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-skill.zip) 或 [WorkBuddy skill](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-workbuddy.zip)，保留完整的 `reprise/` 目录，让本机 agent 按其中的 `SKILL.md` 打开。适用于 Codex、TRAE 等本地脚本入口；WorkBuddy 包增加其平台元数据。需要 Python 3.9+ 和 Git，无须 pip 安装或原生 App。

在目标项目里发命令，或告诉 agent 项目路径，即可直接打开历史、比较文件、配置独立预览，或把所选提交恢复到新目录 / 下载 ZIP。程序独立于 agent；[安装路径、兼容范围与完整流程](AGENT-SKILL.md) 包含已测和待验证的部分。

## 命令行启动（可选）

需要 Python 3.9+ 和 Git。macOS/Linux 的回归、浏览器与安装检查见 [GitHub Actions](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)。Git 读取与 Web 工作台使用 Python 标准库。

以下从 GitHub 获取公开源码，不代表取得 0.7.0 候选能力。已有候选源码时，使用收到的源码目录进行安装：

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

收到本地 0.7.0 候选 wheel 后，建议安装到独立 Python 环境；将示例路径替换为实际文件位置，命令可在源码目录之外执行：

```sh
python3 -m venv /path/to/reprise-venv
/path/to/reprise-venv/bin/python -m pip install /path/to/reprise_local-0.7.0-py3-none-any.whl
/path/to/reprise-venv/bin/reprise /path/to/project
```

也支持允许用户安装的基础 Python 环境，使用模块入口可以避免命令目录未加入 PATH 的问题：

```sh
python3 -m pip install --user /path/to/reprise_local-0.7.0-py3-none-any.whl
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

- [架构与数据流](ARCHITECTURE.md)
- [Git 版本关系图：功能、逻辑、实现与回归契约](GIT-GRAPH.md)
- [配方与采集说明](RECIPES.md)
- [边界、迁移及验证](VALIDATION.md)
- [模块与 HTTP 接口](implementation-contract.md)
- `examples/`：静态站点、可操作 Canvas 游戏、Python CLI、命令型网页配方。
- `python3 scripts/create_demo_projects.py`：在 `work/` 新建三组独立 Git 示例，各含两次提交；不会改已有项目。

## 验证

[发布验收范围](RELEASE-CHECKLIST.md) 覆盖 macOS/Linux 回归、Git 图与缓存契约、浏览器和全新环境安装检查。每次发布以对应提交的 [CI 实际结果](https://github.com/orocoa/Reprise/actions/workflows/ci.yml) 为准。

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
REPRISE_BROWSER_TESTS=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

第二条需要浏览器依赖，可结合上面的环境变量。真实浏览器测试把截图、录像、运行副本和诊断保留在 `work/test-artifacts/`。

### 开发测试：会删除合成版本

需要验证实际删除流程时，在新的隔离目标运行以下脚本。它生成合成项目，联合删除其中前两版，再恢复并核验保留版和共享项目；不是默认交互体验入口，不要用它替代上方保留三稿的准备脚本。

```sh
python3 scripts/demo_version_lifecycle.py --to /new/path/reprise-lifecycle-test
```

目标必须尚不存在。脚本不读取真实项目，原始输入、源文件夹、运行副本与每一步回执保留。HTTP 和恢复字节核对只证明该样本的结果，不代替浏览器截图、依赖重建或独立备份验证。

### 发行包检查

发行包检查使用已有 `setuptools>=61` 和 `wheel` 的基础 Python 解释器：

```sh
python3 scripts/check_distribution.py
```

检查过程不联网：先在保留的源码副本中构建 wheel 和源码包，再由源码包重建 wheel，分别装入全新 venv 和独立用户目录，从构建源码目录外启动，验证命令入口、网页内容及 API。报告、构建包、安装环境和失败日志均保存在 `work/test-artifacts/distribution-*/`。它不代替真实浏览器采集测试。

代码采用 [MIT 许可证](../LICENSE)。字体与图标保留各自原许可，见 [第三方说明](../THIRD-PARTY-NOTICES.md)；导入的仓库和人工媒体保留原权属。

## 数据备份与升级

0.6.0 本地候选版提供经过读回验证的备份与目录迁移：

```sh
python3 run.py --data /path/to/data shutdown
python3 run.py --data /path/to/data backup --to /new/backup
python3 run.py backup-check /new/backup
python3 run.py data-restore /new/backup --to /new/data
python3 run.py --data /new/data open /path/to/project --no-browser
python3 run.py relink --project "资料" --to /existing/new-location --check
python3 run.py relink --project "资料" --to /existing/new-location
python3 run.py migrate --project "资料" --to /new/location
```

项目设置中的「备份与目录迁移」提供离线备份命令、备份检查、新库恢复及目录重新关联。项目原位置不可用时，也可从「项目」中的目录维护入口选择登记项目。备份范围是 Reprise 已管理数据，外部 Git、未保存源文件和外部旧归档列为未纳入；备份未加密且可能含密钥，保持私有权限。同盘副本不能抵御同一磁盘故障。恢复新库会重定位已知内部路径并禁用复制的旧进程身份。

目录迁移复制当前文件，包括未保存内容；读回后才切换登记，原目录保留。项目标识和历史不随路径变化。已存文件夹版本或真实 Git 提交用于核对重新关联，缺少身份锚点时明确拒绝。旧归档继续走原兼容适配器，不能安全独立复制的 Git linked worktree 等须先按实际限制处理。范围和回执说明见 [备份与迁移](BACKUP-AND-MIGRATION.md)。

备份前用同一数据目录执行 `reprise shutdown`，确认任务和预览已退出，再用上方 `backup` 命令生成清单与读回回执。不能确认进程已退出、目标空间不足或内容缺失时会拒绝成功。源 Git 仓库需要另行备份；备份回执单列外部依赖。

升级时替换或重新安装 Reprise 代码，继续指定原数据目录；保留应用数据。还原使用 `data-restore` 到新目录，再显式用 `reprise --data /path/to/restored-data serve --port 0` 打开。项目路径在另一台电脑上不可用时，先对实际新路径执行 `relink PROJECT_ID --to /actual/path --check`，通过后再执行同一命令去掉 `--check`，保留项目标识和历史。没有源目录时，已保存的普通文件夹版本仍可恢复。旧单语 AI 提案保留，重新请求才能得到双语提案；已有运行配方不自动执行。
