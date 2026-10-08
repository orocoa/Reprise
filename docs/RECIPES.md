# 配方与采集

配方可以保存在任意项目根目录的 `.reprise.json` 并提交，也可以在工作台的「项目配置」中作为本机覆盖配置保存。命令型配方即使在 Git 中存在，也须在工作台明确保存后才可执行。保存时复制规范化配置；运行开始后再修改配置不影响已排队任务。

## 静态网页：零 AI

```json
{
  "schema": 1,
  "adapter": "static-web",
  "root": "dist",
  "readiness": {"path": "/", "selector": "main[data-ready]", "timeout_ms": 15000},
  "network": "local",
  "captures": [
    {"id": "desktop", "route": "/", "viewport": {"width": 1440, "height": 900, "scale": 2}, "full_page": true, "steps": []},
    {"id": "phone", "route": "/", "viewport": {"width": 390, "height": 844, "scale": 2}, "full_page": false, "steps": []}
  ]
}
```

`root` 必须是提交中的相对目录。`selector` 应换成项目实际加载完成时出现的元素；没有可靠 app-ready 元素可省略，但异步数据或游戏初始化最好提供专门标记。固定选择器比“等几秒”更可重复。`scale` 是截图像素比例，不增加源图质量。

## 浏览器游戏与 demo

[可运行示例配方](../examples/web-game/.reprise.json) 定义开始按钮、方向键和录屏。支持步骤：

| action | 必需字段 | 用途 |
|---|---|---|
| `click` | `selector` | 启动游戏、切换面板 |
| `press` | `key`；可选 `selector` | 在画布或页面按键 |
| `fill` | `selector`, `value` | 输入固定数据 |
| `wait` | `ms` | 有界的动画等待 |

步骤不会执行任意 JavaScript。`wait_for` 可为每个场景单独指定就绪元素，`record:true` 采集操作录像，`record_ms` 控制操作后继续录制的时间。游戏的随机种子、存档、时间推进若影响结果，应在项目自己的测试入口中固定；当前引擎不假装能自动推断所有游戏玩法。

## 需要构建的网页

[command-web 示例](../examples/command-web.recipe.json) 展示 install/build/start。示例的命令仅适用于实际提供这些 scripts 的 npm 项目，不能直接用于所有框架。

每条命令是 argv 数组，启动时替换 `{port}`、`{host}`、`{root}`；环境也包含 `PORT` 和 `HOST=127.0.0.1`。启动命令必须以前台进程运行，不能自行脱离托管 session 后退出。安装/构建日志保留在该运行副本旁。默认每个安装/构建命令超时 600 秒，可通过 `REPRISE_COMMAND_TIMEOUT` 修改。

历史副本不含 `.git` 目录、工作区未提交内容、未跟踪依赖或过滤器下载的大文件。依赖 Git 元数据的构建应在配方/构建脚本中显式解决；不要引用另一版本的工作区作为历史版本。

## 原生游戏、桌面 App、CLI

```json
{"schema": 1, "adapter": "manual", "root": ".", "captures": [], "network": "local"}
```

在原工具中运行，保存截图/录屏/日志/构建文件，再在所选提交点击「导入已有资料」。该操作复制文件并标为人工证据；不会声称自动核验了原生程序。Unity / Godot 等的 Web 导出若已提交，可选择导出目录作为 `static-web` 根目录；未提交产物可通过经保存批准的构建配方生成。

## 对比、失败与重试

勾选「同时采集所选父版本」后，当前提交和所选真实父提交使用同一配方。路由不存在、资源未提交、安装失败、缺浏览器、初始化超时或网络被阻断，都有明确结果。`complete` 是自动检查通过；`partial` 含有诊断媒体；`failed` 没有完整的可用采集结果。诊断图保留，但不算成功预览。

截图缓存键包含项目、目标 SHA、基准 SHA、完整配方哈希和 runner 版本。只复用完整成功且文件存在的记录；改尺寸、操作、路由或任一 SHA 会产生新记录。录像同样保留场景和 SHA。

## 扩展新运行类型

新增能力时保持这些职责：

1. 在 `detection.py` 增加纯读取的识别信号，不能在识别时执行安装或代码。
2. 在 `recipes.py` 定义明确、可验证的配置字段，不能靠自由文本 shell 作为隐式协议。
3. 在 `runtime.py` 增加受管理的启动/就绪/停止逻辑，仍需记录源 SHA、配置哈希、目录、进程身份与日志。
4. 若产生非浏览器输出，沿用 `evidence/<id>/record.json` 证据契约，准确标记来源和验证方式。
5. 用一个不依赖既有示例项目的真实 fixture 测试，并验证原仓库内容与暂存区未改动。

当前适配器由本项目代码管理，尚不加载外部可执行插件。容器、原生窗口截图、远程机器和 CI 产物连接是可沿这些边界新增的能力，不是当前已经自动实现的功能。
