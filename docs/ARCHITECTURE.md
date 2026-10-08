# 通用 Git 项目架构

## 目标与边界

Git 项目能被读取，与项目能够运行，是两个不同的能力。Reprise 先让任何可读的本地 Git 仓库进入统一数据模型，再根据该提交的文件证据确定运行和采集能力。项目名称、目录、路由和命令均不进入核心源码。

Git 是版本内容的来源；项目注册表记录本机路径和人工配置；运行目录是某一 SHA 的独立副本；证据是带来源的不可混用记录。列表相邻项不代表父子关系。

## 模块结构

```text
run.py / cli.py ─┐
                ├─ service.py ─ projects.py ─ git.py ─ 原仓库（只读）
web/ ↔ server.py┘       │              ├─ detection.py
                       │              └─ recipes.py
                       ├─ jobs.py ─ runtime.py ─ 独立历史副本 + 日志
                       │             └─ static_server.py / 明确批准的 argv
                       ├─ capture.py ─ browser_worker.mjs ─ 截图 / 录像 / 诊断
                       ├─ evidence.py ─ 人工资料 / 历史资料导入
                       └─ ai.py ─ 可选提案 → 校验 → 人工保存配置
```

### 1. Git 对象层

`Repository` 使用系统 Git 的 `rev-parse`、`for-each-ref`、`log`、`ls-tree`、`diff-tree`、`cat-file`、`status` 等命令，通过 argv 和 NUL 分隔传递结果。支持普通工作仓库、裸仓库、linked worktree、未提交的空仓库、detached HEAD、SHA-1 / SHA-256 仓库。对路径使用 filesystem surrogateescape，避免空格、Tab、换行破坏解析。

每个提交保留完整 SHA、真实 parents、作者、时间及引用。默认 diff 使用真实第一父节点；合并提交可选择其他父节点；根提交与空树比较。浅克隆缺失父对象时仍显示提交和现有证据，并指出差异不可读。历史实时从 Git 读取，不再依赖预生成的 61 项目录。

还原直接读取 Git blob，验证对象内容，写入新建的托管目录。不 checkout 源工作区，不修改源 index，不运行仓库 hooks / smudge 过滤器，不自动 fetch。子模块保留 gitlink 信息；LFS 指针明确标记。危险路径、越界符号链接、不可表示的文件和超限输出必须失败并说明，不能悄悄替换内容。

### 2. 项目注册与能力识别

`ProjectStore` 只保存稳定项目 ID、规范化路径、显示名称和人工配方。HEAD 和 history 随时重新读 Git。识别缓存以仓库路径 + 精确 SHA 为键。`detection.py` 读取提交内的 manifests 和 HTML，返回识别信号、置信度、候选根目录、警告和能力。

无须能够识别框架，才能浏览仓库。未知类型仍有 history/diff/manual 能力。识别到框架也不代表它当前可运行；只有实际配方和运行结果能说明运行能力。Canvas 是绘图技术，单独出现不能证明项目是游戏。

配方优先级：当前完整 SHA 的人工配置 > 当前提交的 `.reprise.json` > 自动静态识别。提交里的命令型配方是未批准输入，必须在工作台核对保存。历史版本可以有不同入口和配置；执行任务前锁定 SHA 与规范化配方副本，避免排队期间 HEAD 或配置变化改写请求。

### 3. 运行适配与生命周期

运行适配器目前有 `static-web`、`command-web`、`manual`。适配器读取同一配方契约，持有独立副本、进程身份、就绪状态和日志。静态网页使用专用 loopback HTTP 服务，支持视频 Range、WASM MIME 和跨来源隔离头。命令型适配器按 install → build → start 执行 argv，端口由系统分配并传入 `{port}` / `PORT`。

运行进程使用新 session，停止时校验 PID 与启动身份。API 与项目预览使用不同来源，项目脚本得不到管理 API 的跨源读取权限。停止保留文件；没有自动清理、自动提交、自动推送流程。线程池限制任务并发，同项目由持久锁防止 CLI 与服务并行覆盖；服务重启识别已中断任务。

这些进程以当前本机用户权限运行。若要运行不可信仓库，需要后续容器/虚拟机 adapter；不能把“独立副本”叫作沙箱。现阶段明确的命令配置与执行动作承担授权边界。

### 4. 确定性采集与证据

采集输入是 `project_id + target SHA + base SHA + target recipe hash + effective base recipe hash + runner version`。两个版本分别使用各自的适配器、根目录、启动命令与就绪条件；路由、视口、操作、录屏和网络策略使用目标版本定义的同一组采集场景。基准配置缺失或未批准时拒绝执行并指出需配置的 SHA；缺资源保留诊断，不从其他版本回填。

浏览器从独立上下文启动，等待页面、fonts、图片 decode、媒体 metadata 与指定的 app-ready 选择器。全页采集先触发可见范围内的懒加载，再恢复位置；交互按有限步骤执行。PNG 保留像素尺寸；录像记录自己的宽高。HTTP 失败、脚本错误、缺图和阻断请求会降低记录状态，诊断截图不标成通过。

`network:local` 只允许当前运行实例来源，以及 data/blob；`allow` 是显式放宽的浏览器网络策略。捕获器不用 AI。成功缓存必须匹配全部采集输入且产物仍存在；失败和部分成功不会阻止重试。每次运行/失败的日志和产物独立保留。

人工证据复制到托管存储，明确标记 `source:manual / verification:user-supplied`，绑定用户指定的 SHA，并保留原路径和内容哈希。历史导入证据标为 legacy，保留原始采集元数据，不冒充新引擎重跑验证。只有具有相同场景/媒体类型/两侧 SHA 的资料才能被直观成对呈现。

### 5. 可选 AI 边界

模型适配器只接受有限的已提交清单、路径和差异元数据，只返回结构化提案。输出通过 `validate_recipe` 与文件依据检查，包含 provider/model、输入哈希和提示词版本。提案不会自动保存、执行或变成验证证据。连接配置在请求途中变化时，旧响应丢弃。当前实现兼容 Chat Completions 接口，可通过替换 provider adapter 接入其他供应商；旧原型里的 Codex 配置不被迁移或改写。

## 数据目录

```text
<application data>/
  projects.json                 项目注册 + version_recipes（完整 SHA）+ 配方保存历史
  jobs/<id>.json                任务和恢复状态
  runtimes/<id>/runtime.json    进程身份与配置哈希
  runtimes/<id>/source/         精确提交的独立副本
  runtimes/<id>/runtime.log     安装 / 构建 / 启动日志
  evidence/<id>/record.json     SHA、配方、来源、诊断、媒体元数据
  evidence/<id>/*               原始截图、录像、采集输入和日志
  ai/settings.json             本机私密连接配置
  ai/proposals/                 已校验但未自动执行的模型提案
```

应用数据应放在源仓库以外。读取 Git、刷新列表、切换项目不创建预览副本。只有运行、采集、人工导入等具体操作才写相应托管内容。

## 版本配置与取消任务

人工配置只对保存时解析出的完整 SHA 生效。`HEAD` 前进后不继承上一提交的批准。已有 `recipe` 字段原样保留并通过 `legacy_recipe` 暴露为草稿，不再跨版本自动生效；用户可在指定版本载入并保存。清除某版本覆盖配置使用 `recipe:null`，保留保存历史后回退到提交配置/识别。

运行与采集使用持久取消请求和协作式检查，状态为 queued → running → cancelling → cancelled（清理失败则 failed）。排队取消释放项目锁；运行中取消覆盖快照、安装/构建、服务就绪、采集锁等待及浏览器阶段。只停止具有匹配进程身份的自有进程；部分输出与日志保留。任务完成后取消为幂等操作，不停止已经交付的预览；此时使用运行实例的停止接口。CLI 与服务共享取消请求。

每份任务记录独立校验；损坏 JSON、结构、编码或读取错误通过 `job_warnings` 显示，跳过该条但保留原文件，不阻止其他任务和工作台启动。
