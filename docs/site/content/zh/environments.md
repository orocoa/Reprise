# 保留源码，按需释放和重建旧环境

**版本：0.8.7。先检查环境状态，明确选择后再释放生成产物。**

任务：知道一版项目运行需要什么，区分“写了安装命令”“曾成功构建启动”“现在正在运行”。只有登记且重新核验通过的生成产物，才进入另行明确释放的流程。

## 前提

先完成[首次体验](getting-started.md)。其中的静态网页样本不建立依赖环境；本页是另行选择的进阶操作。使用你明确加入且已有保存配方的项目，取得其 `DATA`、`PROJECT` 与完整 `FULL_SHA`；从 `environments PROJECT` 的实际输出取得 `ENVIRONMENT_ID`，没有记录时不能虚构标识继续释放。CLI 的 `run` 返回任务对象，成功结果在 `result` 中：`RUNTIME_ID` 使用 `result.id`，页面地址使用 `result.url`；最外层 `id` 是任务标识，不能传给 `stop`。环境标识也不能代替运行标识。

真实项目需要先审阅并明确保存 `command-web` 配方，包含实际安装/构建/启动命令和就绪条件。`environment.outputs` 声明生成目录，`inputs` 声明版本中的输入文件，`tools` 声明工具。历史源码中已经存在的目录不能冒充可丢弃输出。不要把数据库、上传文件或手工资料当缓存。

## 默认步骤：读状态与释放条件

```sh
python3 "$REPRISE_ENTRY" --data "DATA" environments PROJECT
python3 "$REPRISE_ENTRY" --data "DATA" environment-check ENVIRONMENT_ID
```

核对关联的项目、完整 SHA、输出目录、`rebuild_verified`、`releasable` 和 `blockers`。预检不会释放内容。`rebuild_verified` 说明此前完成过干净构建和成功启动；它不是无限期保证。

需要真实打开这一稿时，单独运行已保存配方：

```sh
python3 "$REPRISE_ENTRY" --data "DATA" run PROJECT --sha FULL_SHA
```

读取返回的真实 URL 与运行标识，访问页面，确认它属于选择的版本。结束后停止这个运行实例：

```sh
python3 "$REPRISE_ENTRY" --data "DATA" stop RUNTIME_ID
```

默认体验到这里结束，环境继续保留。

## 另行明确操作：释放，然后再尝试重建

只有你另外选择释放这个具体环境，且重新预检通过，才执行：

```sh
python3 "$REPRISE_ENTRY" --data "DATA" environment-release ENVIRONMENT_ID --confirm
```

它移除登记的生成目录，不删除源码、锁文件、配方、截图、日志、系统工具或全局包管理器缓存。以后需要这稿时，再执行同一项目与完整 SHA 的 `run`，让 Reprise 按保存条件重新构建并启动。

## 结果

查看环境记录与释放/运行回执，分别确认“已释放”“正在重建”“已成功启动”。再次启动后仍需实际打开页面并检查功能，不能把进程出现、HTTP 返回和浏览器交互混为同一验证。只释放环境不会删除历史版本。

样本中的 Python 环境不使用 pip 下载依赖，只能验证这个本地样本的流程，不代表 npm、私有仓库或任意工具链可重建。

## 失败与限制

活动进程、输出变化、历史源码变化、新增数据、工具版本变化、共享硬链接或无法完成 `lsof` 检查，都可能阻止释放。遇到阻止应读 `blockers`，保留文件，不能把检查关掉后当作成功。pnpm 等共享硬链接布局可能被保守拒绝。

命令以当前账户运行，可能联网、读写宿主资源；`network: local` 只限制浏览器采集，不是安装命令的沙箱。系统库、宿主变量、外部服务与未来包源没有完整归档。锁文件能记录依赖条件，但不能保证未来下载源一直存在。失败尝试和诊断会保留。

含外部解释器链接的 venv 可能不满足自包含备份边界。备份不会静默省略这些输出；应先理解备份检查结果，再决定是否另行释放已核验环境。

## 下一步

阅读[隐私与备份 FAQ](privacy-and-faq.md)，或回到[认版、比较与恢复](find-compare-restore.md)。[返回产品介绍](index.md) · [English](../en/environments.md)
