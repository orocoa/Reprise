# Reprise

本机 Git 项目与版本工作台。项目接入、Git 读取、运行和证据采集各自独立；不需要 AI 即可读取版本、运行已配置的网页、采集截图与录像。

## 启动

需要 Python 3.9+ 和 Git，当前支持 macOS / Linux。Git 读取与 Web 工作台使用 Python 标准库。

```sh
python3 run.py serve --port 51582
```

打开 `http://127.0.0.1:51582/`，点击「导入项目」，填写任意本地 Git 工作仓库、裸仓库或 worktree 路径。导入只读取仓库。默认应用数据放在 macOS 的 `~/Library/Application Support/Reprise` 或 Linux 的 `$XDG_DATA_HOME/reprise`；可用 `--data` / `REPRISE_DATA` 指定，需在被预览的源仓库之外。

```sh
python3 run.py --data /path/to/reprise-data import /path/to/project
python3 run.py history /path/to/project --limit 20
python3 run.py detect /path/to/project --ref HEAD
```

源码也支持 `python3 -m pip install -e .`，之后使用 `reprise` 命令。所有创建的副本、失败日志、证据均保留，停止服务不会删除它们。不要将带有 AI 密钥的应用数据目录提交到 Git。

## 自动截图：无需 AI

安装可选浏览器依赖（仅在需要采集时）：

```sh
npm install
npx playwright install chromium
```

随后在工作台选择版本，点击「自动采集预览」。也可以指定已有运行环境：

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

选择一个项目后，点击「选择两个版本」，填写 SHA、分支或标签作为基准 A 和目标 B。可交换比较方向；文件变化按所选两版计算，旧的其他基准截图单独折叠，避免混用。自动采集分别运行两版，但使用相同的观察场景。

「项目配置」现在只保存到当前提交，其他版本需分别确认。旧的项目级配置仍保留为草稿，可在配置对话框载入。运行/采集任务提供「取消任务」；取消会停止自有进程并保留副本、日志与部分产物。命令行可用 `reprise --data /path/to/data cancel JOB_ID`，前台运行/采集也可按 Ctrl+C。

损坏的单条任务记录会显示提示并保留原文件，其他任务和工作台继续可用。

## AI 的位置

AI 默认关闭。设置里填入兼容 Chat Completions 的 HTTPS 端点、模型原名与密钥；本机端点可用 HTTP。只有点击「AI 建议配置」才发送当前提交中有限的清单文件、路径及变更文件名，不发送未提交文件或整个仓库。模型保持用户指定值，不自动替换。

返回的 JSON 经过配方和文件依据校验，只成为待审核提案。用户可编辑并保存到项目配置，然后仍由确定性的运行/采集系统执行。AI 没有直接执行命令、提交 Git、删除副本或伪造证据的接口。密钥存储为权限 `0600` 的本地设置，API 不返回密钥。未配置、模型失败或输出无效不会阻塞核心功能。

## 配方和扩展

- [架构与数据流](docs/ARCHITECTURE.md)
- [配方与采集说明](docs/RECIPES.md)
- [边界、迁移及验证](docs/VALIDATION.md)
- [模块与 HTTP 接口](docs/implementation-contract.md)
- `examples/`：静态站点、可操作 Canvas 游戏、Python CLI、命令型网页配方。
- `python3 scripts/create_demo_projects.py`：在 `work/` 新建三组独立 Git 示例，各含两次提交；不会改已有项目。

## 验证

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
REPRISE_BROWSER_TESTS=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

第二条需要浏览器依赖，可结合上面的环境变量。真实浏览器测试把截图、录像、运行副本和诊断保留在 `work/test-artifacts/`。
