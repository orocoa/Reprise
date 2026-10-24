# 历史快速开始 / Earlier quickstart

保留于 2026-10-24。以下是较早的 Python Skill 包、wheel 和三稿样本说明，不是当前便携包的首次接入路径。当前入口见[快速开始](QUICKSTART.md)；此处的旧包流程不证明 0.8 候选已公开发行。

Retained on October 24, 2026. These earlier Python Skill, wheel, and sample instructions are reference material. Use the [current quickstart](QUICKSTART.md) for the portable candidate. These instructions do not establish a public 0.8 release.

---

# Quickstart / 快速上手

[简体中文](#中文) · [English](#english) · [首页](../README.md)

## 中文

本页针对 **0.8.0 LOCAL CANDIDATE**，尚未公开发布。公开 [v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) 只有 Git 历史工作台；它不能运行这里的普通文件夹流程。

### 1. 检查完整 Skill 包

准备 Python 3.9+、Git 和浏览器。收到候选 ZIP 后完整解压，保留 `reprise/` 下的 `SKILL.md`、`scripts/` 和 `assets/`。以下 `/path/to` 是要替换的示例路径：

```sh
python3 /path/to/reprise/scripts/reprise.py doctor
```

检查通过后，可以把整个 Skill 目录放入本地 agent 支持的技能目录，或直接使用这个 Python 入口。完整的客户端兼容范围见 [Skill 指南](AGENT-SKILL.md)。绝对路径入口可从任何目录运行。

### 2. 先用独立样本练习

下载并解压[独立样本包](site/assets/recovery-sample.zip)。它包含 `recovery-sample/prepare.py`，不要求 Reprise 源码或 wheel。将下面两个脚本路径换成实际位置：

```sh
python3 /path/to/recovery-sample/prepare.py \
  --to "$HOME/reprise-recovery-demo" \
  --entry /path/to/reprise/scripts/reprise.py
```

目标必须尚不存在；重做时换一个新目标。脚本仅保存三版合成网页，不读取真实项目、不启动服务、不恢复或删除文件。复制生成的 `summary.json` 中的 `open_command` 打开同一份样本：

1. 选中「初稿」，确认标题、时间和 `index.html` 内容；预览缺失时以文件内容为准。
2. 在「版本对比」选择「初稿」和「当前稿」，检查文件变化。
3. 从「初稿」恢复 `index.html`，填写一个新目标目录。也可运行 `summary.json` 提供的 `restore_command`，它使用同一初稿标识。
4. 阅读恢复结果，打开恢复文件并与 `expected/draft-1.html` 核对；原 `source/index.html` 仍为当前稿。保留样本继续使用。

运行旧网页需要对应版本已保存的配方与依赖。样本成功只证明这份样本通过，不代表你的其他资料或独立备份已经验证。更多操作见[恢复教程](site/content/zh/find-compare-restore.md)。

### 3. 打开自己的文件夹或 Git 项目

普通文件夹：

```sh
python3 /path/to/reprise/scripts/reprise.py open /path/to/drafts --folder --no-browser
```

已有 Git 项目：

```sh
python3 /path/to/reprise/scripts/reprise.py open /path/to/project --no-browser
```

打开命令返回的本机 URL。普通文件夹需要主动「记录版本」才有历史；Git 项目读取已有提交，导入不会替你提交、切换分支或安装源项目依赖。

关闭浏览器标签不会停止服务。结束使用时：

```sh
python3 /path/to/reprise/scripts/reprise.py shutdown
```

如果启动时指定了 `--data /path/to/data`，关闭时也要使用同一个 `--data`。关闭停止身份已核验的服务及其自有任务，保存的数据会保留。

### 可选：wheel 或源码入口

收到 0.8.0 候选 wheel 时，可装入新建的独立环境，随后用 `reprise` 替换上面的 Python Skill 入口：

```sh
python3 -m venv /path/to/reprise-venv
/path/to/reprise-venv/bin/python -m pip install /path/to/reprise_local-0.8.0-py3-none-any.whl
/path/to/reprise-venv/bin/reprise --help
```

样本脚本可直接使用这个已安装命令；此时使用 `--cli`，不要使用 Skill 专用的 `--entry`：

```sh
python3 /path/to/recovery-sample/prepare.py --to "$HOME/reprise-recovery-demo" --cli /path/to/reprise-venv/bin/reprise
```

已有候选源码时，从源码根目录用 `python3 run.py` 替换 Skill 入口即可，无须 pip 安装。公开 GitHub 下载或 clone 的版本应单独核对，不能据此假定是 0.8.0 候选版。完整命令见[中文参考](REFERENCE.zh-CN.md)。

需要额外体验运行环境与版本生命周期时，候选源码另有 `python3 scripts/prepare_lifecycle_demo.py --to /new/path/reprise-interactive`，同样保留所有样本版本。这是开发源码的可选入口。

## English

This guide targets the unreleased **0.8.0 LOCAL CANDIDATE**. Public [v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) provides the Git history workspace and cannot perform these ordinary-folder workflows.

### 1. Check the complete Skill package

Install Python 3.9+ and Git, and have a browser available. Extract the supplied candidate ZIP and retain all of `reprise/`, including `SKILL.md`, `scripts/`, and `assets/`. Replace `/path/to` with your actual extraction path:

```sh
python3 /path/to/reprise/scripts/reprise.py doctor
```

After the check, place the complete directory in a supported local agent's Skill location, or use the Python entry directly. See [the Skill guide](AGENT-SKILL.md) for client compatibility. Commands with an absolute entry path work outside the source checkout.

### 2. Practice with isolated sample files

Download and extract the [standalone sample](site/assets/recovery-sample.zip). It contains `recovery-sample/prepare.py` and needs no Reprise source checkout or wheel. Replace both script paths with their actual locations:

```sh
python3 /path/to/recovery-sample/prepare.py \
  --to "$HOME/reprise-recovery-demo" \
  --entry /path/to/reprise/scripts/reprise.py
```

The destination must not exist; use a new one when repeating the walkthrough. The script only saves three synthetic website versions. It does not read real projects, start a service, restore, or delete files. Use the generated `summary.json` file's `open_command` to open the same sample:

1. Select the first draft (「初稿」) and check its saved time and `index.html`. If previews are missing, inspect the files.
2. Compare the first draft with the current draft (「当前稿」) and review changed files.
3. Recover `index.html` from the first draft to a new destination. Alternatively, use the supplied `restore_command` from `summary.json`; it identifies the same first draft.
4. Read the recovery result, open the recovered file, and compare it with `expected/draft-1.html`. The original `source/index.html` remains the current draft. Keep the sample for later use.

Running old websites requires their saved recipes and dependencies. A passing sample does not verify your other data or an independent backup. See the [recovery walkthrough](site/content/en/find-compare-restore.md).

### 3. Open your own folder or Git project

Ordinary folder:

```sh
python3 /path/to/reprise/scripts/reprise.py open /path/to/drafts --folder --no-browser
```

Existing Git project:

```sh
python3 /path/to/reprise/scripts/reprise.py open /path/to/project --no-browser
```

Open the returned local URL. Ordinary folders gain history when you explicitly save a version. Git projects use their existing commits; import does not commit, switch branches, or install dependencies into the source.

Closing a browser tab does not stop the service. When finished, run:

```sh
python3 /path/to/reprise/scripts/reprise.py shutdown
```

If you used `--data /path/to/data` to start, use the same option when stopping. This stops the verified service and its owned tasks while retaining saved data.

### Optional: wheel or source entry

Install a supplied candidate wheel into a new isolated environment, then use `reprise` in place of the Python Skill entry:

```sh
python3 -m venv /path/to/reprise-venv
/path/to/reprise-venv/bin/python -m pip install /path/to/reprise_local-0.8.0-py3-none-any.whl
/path/to/reprise-venv/bin/reprise --help
```

The sample script can use that installed command directly. Use `--cli` instead of the Skill's `--entry` option:

```sh
python3 /path/to/recovery-sample/prepare.py --to "$HOME/reprise-recovery-demo" --cli /path/to/reprise-venv/bin/reprise
```

With candidate source, use `python3 run.py` from its root instead of the Skill entry; no pip installation is needed. Check the version of public GitHub downloads or clones separately. They do not imply access to the 0.8.0 candidate. See the [complete reference](REFERENCE.en.md).

To additionally explore runtime environments and version lifecycle, candidate source includes `python3 scripts/prepare_lifecycle_demo.py --to /new/path/reprise-interactive`, which retains all sample versions. This is an optional source-only path.


0.8 工作台入口与 A/B 恢复步骤见[双语任务指南](WORKSPACE-TASKS.md)。保存后的截图偏好仍为 none/manual/remind/auto；已选择的不重复询问。

For the 0.8 workspace, see the [bilingual task guide](WORKSPACE-TASKS.md). A/B recovery is bound to the chosen side. Existing screenshot preferences are reused.
