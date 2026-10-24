---
name: reprise
description: "倒带 / Reprise：打开本地网页工作台、保存这一稿、按画面找旧版并取出新副本。Use to open Reprise, save a local webpage draft, view its visual history, or recover a chosen version."
license: MIT
metadata:
  version: "0.8.0"
---

# Reprise · 倒带

Keep checkpoints of the local webpage the user is already making with their agent. Save the current files, show the matching picture when supported, and recover a selected draft into a new folder. Use the current conversation's agent; do not launch another built-in AI or change model settings.

面向正在用 AI 编程代理制作网页的人：保存当前稿、按画面找回旧稿、取出新副本。复用当前任务中已经明确的网页目录；不要每保存一次就重新让用户选文件夹。

## Language / 语言

Follow the user's explicit language choice; otherwise use the current conversation language (`zh` or `en`). A bare `$reprise` does not imply Chinese. Keep that language for receipts and explanations, and always pass `open ... --lang zh` or `--lang en` explicitly. Translate diagnostic meaning without changing paths, titles, SHA values, or original logs. CLI JSON and error text are not fully localized.

优先遵循用户明确选择，否则沿用当前对话的中文或英文。聊天和工作台使用同一明确语言；用户要求切换时立即切换，不改版本名和文件路径。

## Entry / 入口

The main delivery is this **source Skill and its scripts**, with the Python core and web assets under `assets/runtime/`. Use its **absolute** `scripts/reprise.py` path; the examples call it `REPRISE` and use `python3 "$REPRISE"`. Resolve a verified Python 3.9+ interpreter first: invoke its absolute path, or put its directory on this command's PATH so `python3` selects it. The entry locates its own core independently of the current directory; a source checkout can use its existing `src/`.

Core operations need **Python 3.9+ and Git** on macOS/Linux (Windows: WSL); ordinary-folder snapshots also use Git. No third-party Python packages are needed. Automatic pictures additionally need compatible **Node.js (20+ for the current Playwright 1.62.1), the npm Playwright module, and Chromium or a tested existing Chrome**. Static HTML capture does not require npm when those tools already exist; the narrow npm/Vite preview does.

先复用宿主 Agent 已有环境。In Codex, call `load_workspace_dependencies` **when that tool is available**, then verify the returned interpreter, Git, Node/module paths and a usable browser; do not assume it supplies every component. Otherwise inspect existing PATH tools. Keep resolved paths in the current command environment, never hardcode a developer's home path or edit global environment/model settings. Read [environment reuse and installation](references/environment.md) when resolving tools, preparing pictures, or a dependency is missing. The agent can carry out an authorized installation using a mature official method and the host's normal command approval; give the concrete plan and obtain only missing authorization. Do not silently use sudo, weaken security settings, or install tools into the managed webpage source.

Run `python3 "$REPRISE" doctor` before first use to check Python, Git, the core and packaged-file integrity. **This doctor does not prove screenshot readiness.** A real capture must return a complete picture bound to the saved SHA; a files-only save does not require browser setup. 核心检查、文件保存和画面采集分别回报，不把缺截图依赖说成文件未保存，也不要求用户自行拼环境变量。

## Save, see, recover / 保存、看过去、取出副本

Use only the project path or identity established by the user or this task. Ask for a folder only if it is absent or genuinely ambiguous. Keep the existing data directory; omit `--data` unless the task already uses an explicit one.

| Intent / 用户目标 | Command / 行动 |
|---|---|
| Save this webpage draft / 保存网页这一稿 | `python3 "$REPRISE" save /known/webpage --title "Draft title"` |
| Save another draft of a registered project / 已有项目再留一稿 | `python3 "$REPRISE" snapshot PROJECT --title "Draft title"` |
| Open visual history / 打开工作台、按画面找过去 | `python3 "$REPRISE" open --workbench --lang zh --no-browser` (use `en` for English); open the returned local URL in the user's chosen browser or the available browser tool. |
| Open the selected project / 打开指定项目 | `python3 "$REPRISE" open --project "Known name" --lang en --no-browser` (use `zh` for Chinese). |
| Find an exact version / 查询旧稿 | `python3 "$REPRISE" history --project "Known name"`; inspect only the requested range. |
| Take out a copy / 取出所选稿 | `python3 "$REPRISE" restore PROJECT --sha FULL_SHA --to /new/sibling-folder`; for one file add `--path relative/file`. |

For an unqualified “open Reprise” / “打开倒带”, or a bare Skill selection with no other task, open the workbench with an explicit language. Do not import the terminal's current directory merely because no project was named. Opening the UI is optional when the user only wants a save.

The Skill identifier is `reprise`; “倒带” is its Chinese product name and discovery wording. Use the host's actual Skill selector or an explicit natural-language request such as “用倒带打开工作台”. Do not register a second Chinese Skill, invent an `@` alias, or treat a display name as proof that a native mention works.

Choose screenshot behavior the same way for the first and every later save. For a registered project, reuse the known preference or read it with `python3 "$REPRISE" preview-preferences PROJECT`; do not infer a preference from a previous picture:

- “保存这一稿” / “save this draft” alone: use the save or snapshot command above without a screenshot override. Existing `auto` runs its approved template; `none`, `manual`, `remind`, or no saved preference retain their behavior.
- An explicit picture request for **this** draft, such as “保存并截图” / “save and capture this draft”: if an approved `auto` preference exists, use the same command without an override. Otherwise add `--capture-static` for this save, even if a previous save already captured a picture. This one-time request may override `none`, `manual`, or `remind` for this draft only.
- Change or enable a future screenshot preference only when the user requests that change. A successful picture does not authorize future automatic capture.
- If the user explicitly says **no picture for this save**, a project without `auto` can use the ordinary save. With existing `auto`, the current CLI has no one-time skip override: explain that limit before a command that would capture. Do not invent a flag or silently change the future preference; obtain the user's choice if changing that preference is needed.

`--capture-static` captures a **directly viewable local HTML draft**, or returns a plan when configuration / command approval is needed. It does not persist a preference; do not combine it with `--preview`. Vite/React and other command-based sites may need a saved recipe; HTML success does not establish that every framework works automatically.

保存命令同步等待任务结束，但**文件保存与截图是两个结果**。Read `result.sha`, `result.saved`, and `result.preview.status`, not only the exit code or the outer job's `status`:

- `result.saved: true` means the files were saved at `result.sha`. Only report the picture as ready when `result.preview.status` is `complete` and its evidence belongs to that exact SHA.
- `result.unchanged: true` means the existing draft was reused. A new `--title` does not create or rename that draft; read its existing history title and explain the reuse. Do not announce a new draft under the requested name or silently rename the existing one. A requested picture can still be captured for the reused SHA.
- `optional` or `not-requested` means no picture was captured by this save. Report the saved files without inventing a picture or changing the user's preference.
- `failed`, `cancelled`, `needs-approval`, or `needs-configuration` means the files can still be saved successfully. Explain the screenshot's actual `error` or `plan.reason`; do not save a duplicate draft merely to retry its picture.
- If process observation is denied by the client's sandbox, retain the failure and any successfully saved files. Use the client's supported approval for the specific open/capture command when available; never change model, sandbox or approval settings, treat an unknown process as exited, or repeatedly launch/save to work around the denial. Retry a picture against the saved SHA after permission is available. If approval is unavailable, report that boundary.
- For a Vite/React or other command-based project, reuse a reproducible recipe already explicitly saved for this SHA, or commands the user has approved in this task. If the approved recipe is not saved yet, use `recipe PROJECT /approved-recipe.json --sha FULL_SHA` before `capture PROJECT --sha FULL_SHA`. Keep existing recipe choices. Otherwise report “files saved; preview configuration needed” and obtain the missing command approval. Detection, `package.json` scripts, and AI suggestions do not authorize installation or execution.

For a supported Vite source project, a first capture request can return `needs-approval` with `plan.recipe`. Show the actual proposed installation and run commands, including dependency install scripts and execution of `vite.config`, before asking for missing approval. The plan is neither saved nor executed by detection. After approval, save that exact recipe for the returned `result.sha`, then capture the same SHA. If the user also approves reusing this recipe for future drafts, set `preview-preferences PROJECT --mode auto --recipe-sha FULL_SHA`; later saves should omit `--capture-static`, because that one-time static request overrides the saved automatic preference. Do not imply support for other frameworks from this narrow Vite path.

例如：中文回报“这一稿已保存，画面已采集”，或“文件已保存；这个 Vite 项目还需要确认运行配置才能生成画面”。English: “Draft saved and picture captured,” or “Files saved; this Vite project needs an approved run configuration before a picture can be captured.” Include the saved version and actual outcome; never imply a missing picture exists.

## Boundaries / 边界

- Imported source folders and Git repositories remain unchanged by preview/recovery. Never checkout, reset, commit, run hooks/filters, or install dependencies into an imported source as a side effect. Run approved recipes only through Reprise's separate runtime copy.
- Pictures bind to the exact SHA and capture input. Never substitute another draft's image when evidence is absent. A screenshot confirms what was captured, not general correctness or successful deployment.
- Recover into a **new** folder outside the source and the Reprise data directory, normally beside the source. Never overwrite the current draft. Report the recovery receipt, scope, and readback result; saved files are not a complete backup of external services or development environments.
- Keep originals, history, screenshots, logs, and failed diagnostics. “Save”, “rewind”, or “organize” does not authorize deletion. Reuse explicit existing authorization; do not add repetitive confirmation to an already approved save or capture.
- Reprise's core operations are local and do not enable AI automatically. The agent's tool outputs or opened files may enter that agent's model context. Use concise summaries by default; do not promise that all Skill data stays on the device or that the unencrypted library is a system sandbox.

## Optional advanced work / 按需深入

Only when the user requests older-folder imports, backup/migration, version deletion, storage estimates, environment release, or legacy archives, read [the retained advanced workflows](references/advanced-workflows-0.8.md). The current entry and webpage-saving workflow above take precedence; the detailed data and authorization boundaries still apply.

Read [folder imports](references/folder-imports.md) only for ordered folders/ZIP collections, and [workbench tasks](references/workspace-tasks.md) for detailed visual comparison/recovery tasks. Do not turn an ordinary webpage checkpoint into cleanup, migration, or a new project setup.
