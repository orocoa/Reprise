---
name: reprise
description: "倒带 / Reprise：保存本地网页稿、按画面找旧版、浏览已有 Git 版本关系并取出新副本。Use to open Reprise, save webpage drafts, browse their pictures or real Git relationships, and recover a chosen version."
license: MIT
metadata:
  version: "0.8.3"
---

# Reprise · 倒带

Help a webpage designer **save a draft → recognize an earlier version by its picture → recover a new copy and keep editing**. Reuse the folder and project already established in the conversation. Ask for the folder only when missing or ambiguous.

## Start

Use this Skill’s absolute `scripts/reprise.py` path as `REPRISE`. The source package includes its local core and web assets. Core: Python 3.9+ and Git on macOS/Linux or WSL. Pictures also need Node, Node Playwright and a browser. For installation or missing tools, read [environment.md](references/environment.md); reuse verified host tools before installing official dependencies outside the webpage source. No extra AI key or model setup is needed.

Run `python3 "$REPRISE" doctor` after installation or a runtime change; it checks core/package integrity, not picture readiness. Open the actual returned URL in the user’s selected or available browser. Pass the conversation’s language explicitly with `--lang zh` or `--lang en`.

| Intent / 用户目标 | Command / 行动 |
|---|---|
| Open visual history / 打开工作台、按画面找过去 | `python3 "$REPRISE" open --workbench --lang zh --no-browser` (use `en` for English). |
| Save the current webpage / 保存网页这一稿 | `python3 "$REPRISE" save /known/webpage` (optional `--title "Short name"`). |
| Save a registered folder again / 再留一稿 | `python3 "$REPRISE" snapshot PROJECT` (optional `--title "Short name"`). |
| Find saved versions / 查询旧稿 | `python3 "$REPRISE" history PROJECT` |
| Recover a copy / 取出所选稿 | `python3 "$REPRISE" restore PROJECT --sha FULL_SHA --to /new/sibling-folder` |

“打开倒带” or a bare Skill selection only opens the workbench; it does not save or import the terminal’s current directory. `projects` lists registered names/IDs when the current project is unknown. If the same folder has both records, use `kind: folder` for drafts and `kind: git` for read-only history; resolve the ID rather than asking the designer to distinguish identical names. Names can be automatic; do not require another naming decision before each save.

## Save: ask once, then reuse

For a folder project, read `preview-preferences PROJECT` before saving. When genuinely unconfigured, ask once: **“这个项目以后留稿时，需要一起保存画面吗？选择会按项目记住，可随时更改。”** An existing explicit project choice answers this question across chats, restarts and capture failures.

- **Yes:** first `save`/`snapshot` adds `--preview auto --preview-pending`. This persists yes before configuration/capture completes; it does not approve detected project commands.
- **No:** first save adds `--preview none`.
- **Later:** omit preview overrides. The core reuses the saved choice and approved template. Do not re-ask after failure.

For missing configuration, an explicit one-time override, or a changed choice, read [capture-preferences.md](references/capture-preferences.md). Commands must be explicitly reviewed and saved for the exact version before execution in a separate copy. Keep saved files and retry their picture against the same SHA.

For “本轮修改前后都帮我留稿”, save before the first source edit and after the requested work finishes. This is two checkpoints in this task, not a watcher. If the file checkpoint fails, diagnose before overwriting it unless the user chooses to proceed without that checkpoint. A picture failure alone does not undo saved files.

Read `result.saved`, `result.sha` and `result.preview.status` separately. A ready picture requires `complete` and real media belonging to that SHA. `unchanged: true` reuses the existing draft and title; do not announce a new draft. Report the result briefly, keeping diagnostics on demand.

## Find and continue

Keep the agreed **画面 / 版本关系** interface: picture thumbnails and one compact relationship graph. Select the exact draft, compare when useful, and recover into a new folder outside the source and Reprise data directory. Report the actual destination, scope and readback result; whole-draft recovery supplies copyable continuation instructions. Verify the copy before the next requested edit. Partial files and ZIP export do not imply a complete runnable webpage.

For existing Git branches/merges, use `python3 "$REPRISE" open /known/repository --lang zh --no-browser`. This is a read-only Git project, separate from folder checkpoints. Folder save order never impersonates source branches. Images belong to exact versions; never fill a missing picture from another revision. Do not checkout, reset, commit or install into an imported source.

For detailed comparison/recovery, read [workbench tasks](references/workspace-tasks.md). Only for requested legacy import, backup, migration, deletion or environment maintenance, read [advanced workflows](references/advanced-workflows-0.8.md) or [folder imports](references/folder-imports.md). Preserve existing files, media, runtimes and failed diagnostics. General feature expansion is frozen; do not turn a draft task into cleanup or another AI setup.
