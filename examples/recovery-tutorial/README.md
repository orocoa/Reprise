# 三稿恢复示例 / Three-draft recovery sample

这个示例创建一个没有个人资料、外部图片或网络字体的网页文件夹，保存“初稿、第二稿、当前稿”三个版本。推荐带预览运行，这样打开 Reprise 时能看到每一稿的真实截图：

```sh
python3 /path/to/recovery-tutorial/prepare.py \
  --entry /path/to/reprise/scripts/reprise.py \
  --to /path/to/new-recovery-sample \
  --with-previews
```

如果安装的是 CLI，把 `--entry ...` 换成 `--cli /path/to/venv/bin/reprise`。`--to` 必须是尚不存在的新目录。示例只会操作这个新目录里的材料；不会执行恢复或删除，也不会给源文件夹初始化 Git。

`--with-previews` 明确允许 Reprise 在本机临时启动每个已保存版本的静态网页，并启动无头浏览器截图。脚本先保存全部三稿，再通过现有 `recipe` 和 `capture` 命令，为每一稿的**完整 SHA** 保存静态网页配方并采集。配方不包含安装、构建或自定义启动命令，页面只访问本机地址。

截图需要已可用的 Node.js、Playwright 和 Chromium。脚本不安装依赖。如果它们不在默认位置，可先设置 Reprise 支持的路径：

```sh
export REPRISE_NODE=/absolute/path/to/node
export REPRISE_PLAYWRIGHT=/absolute/path/to/playwright/index.mjs
export REPRISE_BROWSER=/absolute/path/to/chromium
```

脚本自身只用 Python 标准库。无需截图时省略 `--with-previews`：原先的保存行为不变，不启动网页或浏览器；仍可以在 Reprise 中查看 `index.html` 内容、比较文件并恢复。

## 运行后

查看新目录里的 `summary.json`：

- `file_versions` 表示文件保存是否完成；`versions` 保留三稿名称、完整 SHA 和网页文件摘要。
- `previews` 单独记录图片结果，状态为 `not_requested`、`complete`、`partial` 或 `failed`。只有经过 SHA 和图片摘要核对的自动采集图才计为成功。被中断的运行可能保留 `pending` 或 `running` 状态。
- `open_command` 打开这个示例；浏览版本、选择初稿、比较 `index.html`，再恢复到新目录。`restore_command` 是可供手动执行的等效命令，脚本不会替你执行。
- `commands/` 保留每条保存、配方和采集命令的参数、退出码、标准输出和错误；失败记录不会删除。`data/` 保留 Reprise 的证据、浏览器日志和工作记录。`expected/` 保留三份原始 HTML，便于核对。

如果截图有任何失败，脚本会先写好汇总，再以退出码 `1` 提示“文件已保存，预览未齐”。不必重新保存三稿，也不要复用原目录重跑整个脚本：先修复已有浏览器依赖，再按失败的 `commands/capture-N.json` 中的 `command` 重试；若配方保存失败，先重试对应的 `recipe-N.json`。重试后的新结果在 Reprise 中查看，原 `summary.json` 是首次运行的记录，不会自动更新。

## English

Run the command above with `--with-previews` to save three synthetic website drafts and capture each exact saved revision through Reprise's existing recipe and capture CLI. Use either an extracted Skill entry (`--entry`) or an installed executable (`--cli`). The destination must be new.

The optional flag explicitly allows local static serving and headless browser capture. Existing Node.js, Playwright and Chromium are required; no packages are installed. Without the flag, only file versions are saved, preserving the original standard-library-only workflow.

`summary.json` reports `file_versions` separately from `previews`. All three drafts are saved before capture begins. Every command and failure is retained in `commands/`; evidence and browser diagnostics stay in `data/`. A partial or failed capture exits with code `1` while keeping the saved versions intact. After fixing dependencies, replay the recorded failing command, not the entire preparation script. The original summary remains a record of the first run. No restoration or deletion is performed by this script.
