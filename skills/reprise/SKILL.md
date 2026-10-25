---
name: reprise
description: "倒带 / Reprise：保存本地网页稿、按画面找旧版、浏览已有 Git 版本关系并取出新副本。Use to open Reprise, save webpage drafts, browse their pictures or real Git relationships, and recover a chosen version."
license: MIT
metadata:
  version: "0.8.0"
---

# Reprise · 倒带

Keep drafts of the local webpage the user is already making, or browse its existing Git history and pictures. Use this conversation’s agent and the fixed local core; do not launch another AI or change model settings. Reuse the established project folder and data directory. Ask for a folder only when missing or ambiguous.

## Entry and language / 入口与语言

The complete source Skill carries its core and web assets under `assets/runtime/`. Use the absolute `scripts/reprise.py` path, called `REPRISE` below. Resolve a verified Python 3.9+ interpreter and Git; the core has no third-party Python packages. Pictures additionally need compatible Node, Node Playwright and a usable browser. The current Playwright 1.62.1 needs Node 20+. Scope: macOS/Linux, Windows via WSL; do not claim all clients were tested.

For installation or missing tools, read [environment reuse and installation](references/environment.md). In Codex, use `load_workspace_dependencies` when available, verify what it returns, reuse tools first and complete authorized official installation. Keep tool paths scoped to the command/service, outside managed webpage sources. Ordinary users need no extra AI key or manually assembled environment variables.

Run `python3 "$REPRISE" doctor` before first use. It checks core tools and package integrity, not screenshot readiness. Report actual capabilities separately; do not reinstall working tools or change global model/security settings.

Follow the user’s explicit language, otherwise the conversation’s Chinese or English. Always pass `--lang zh` or `--lang en` when opening. A bare `$reprise` does not select a language. Preserve names, paths, SHA values and original logs; explain their diagnostic meaning in the chosen language.

| Intent / 用户目标 | Command / 行动 |
|---|---|
| Open visual history / 打开工作台、按画面找过去 | `python3 "$REPRISE" open --workbench --lang zh --no-browser` (use `en` for English); open the actual returned URL in the selected or available browser. |
| Open a known project / 打开指定项目 | `python3 "$REPRISE" open --project "Known name" --lang zh --no-browser` (use `en` for English). |
| Browse existing Git history / 查看已有 Git 路线 | `python3 "$REPRISE" open /known/repository --lang zh --no-browser` (use `en` for English). Read existing commits, branches and merges without creating a commit. |
| Save a known webpage / 保存网页这一稿 | `python3 "$REPRISE" save /known/webpage --title "Draft title"` |
| Save a registered folder / 已有文件夹项目再留一稿 | `python3 "$REPRISE" snapshot PROJECT --title "Draft title"` |
| Read a folder project’s image choice / 读取文件夹截图选择 | `python3 "$REPRISE" preview-preferences PROJECT` |
| Find a version / 查询旧稿 | `python3 "$REPRISE" history --project "Known name"` |
| Recover a selected copy / 取出所选稿 | `python3 "$REPRISE" restore PROJECT --sha FULL_SHA --to /new/sibling-folder`; add `--path relative/file` for a partial recovery. |

An unqualified “open Reprise” / “打开倒带”, or a bare Skill selection, only opens the workbench. It does not import or save the terminal’s current directory. The identifier is `reprise`; 倒带 is the product’s Chinese name, not evidence of a universal `@` alias. Use the client’s real selector or natural-language invocation.

Choose the entry from the user's task. Browsing existing Git history uses the repository project (`kind: git`); its graph preserves real full-SHA commits and ordered parent edges. Saving current files uses a separate folder project (`kind: folder`), even for a working directory that also has Git. Folder save order is not the source repository's branch history. Never commit on the user's behalf as a save/preview side effect. Keep both the picture view and version-relationship view available; pictures bind to the selected exact version.

## First image choice, then reuse / 首次问清，之后沿用

For a webpage **folder project**, read its saved screenshot preference before saving. If no project choice exists (`not_configured: true` or an unregistered folder project), ask **once**. These preference/save commands do not apply to a Git-history project; use its exact-version preview/capture workflow when requested.

> 这个项目以后每次留稿时，需要一起保存画面吗？选择一次后会一直沿用，可随时更改。
> Should future drafts of this project include an image? I’ll remember your choice; you can change it anytime.

An existing explicit project-level choice already answers this question. Do not ask it again in another chat, after restart, after a failed picture, or before each save. Treat an expressly one-time request as one-time; it does not silently change the future preference. Pure file tasks do not need a screenshot question unless the user asks for images.

- **Yes:** first `save`/`snapshot` uses `--preview auto --preview-pending`. This persists the answer **before** capture/configuration finishes. Alternatively set `preview-preferences PROJECT --mode auto --pending-recipe` for an existing project. A pending choice is not permission to execute detected scripts.
- **No:** first `save`/`snapshot` uses `--preview none`, or set `preview-preferences PROJECT --mode none`. Later saves only save files.
- **Later saves:** omit `--preview`, `--capture-static` and other overrides; the core reuses the stored choice and approved template. Do not require the user to say “include its picture” or “remember this” every time.
- **Configuration needed:** keep the choice and saved SHA. Obtain only the missing entry, environment or actual command authorization. Explain that the first confirmed settings will be reused; save the exact recipe before capture. Do not re-ask whether the user wants pictures. A picture failure does not reset the choice.
- **Changing a choice:** act on the user’s request and persist the new project preference. Keep existing manual/reminder choices unless changed by the user.

Read [capture choices and configuration](references/capture-preferences.md) for first-use commands, one-time overrides, pending configuration, changed recipes and failure states. A restored library’s execution settings need the destination host’s confirmation; that does not erase the user’s earlier image choice.

## Save and continue / 留稿与继续修改

For “本轮修改前后都帮我留稿并带画面” / “save with pictures before and after this edit”, save before the first source edit and after the requested work is complete. Reuse the known folder, project choice and short task-based names. An explicit picture request can override files-only for these checkpoints; do not change the future project choice implicitly.

If the **files checkpoint** fails, retain the original and diagnose before overwriting it. Continue after it succeeds, or after the user explicitly chooses to edit without that checkpoint. Picture failure alone does not undo saved files. This is orchestration within the current task, not a watcher or a promise to intercept every edit/client. Do not save after every tiny tool action or on “open”.

Saving waits for the task, but files and pictures are separate results:

- Read `result.saved`, `result.sha`, and `result.preview.status`. Only `complete` with real media belonging to that exact SHA means a picture is ready; the outer job status or exit code is insufficient.
- `result.unchanged: true` reuses the existing draft and title. A new requested title does not create or rename that version. Explain reuse; do not announce a new named draft. A requested picture may still be captured against it.
- `not-requested` / `optional` means no picture was captured. `failed`, `cancelled`, `needs-configuration` or `needs-approval` can coexist with saved files. Keep the SHA and retry the picture against it; do not save duplicates just to retry.

After recovery, report the actual new folder, scope and readback result. For a complete draft, give continuation instructions the user can paste into their editing agent. Verify that copy, then use its folder for the next requested edit and save. Partial files are not a complete runnable webpage. Copying instructions does not message another chat or change its working directory.

## Boundaries and optional work / 边界与按需功能

- Imported source folders and Git repositories remain unchanged by preview/recovery. Never checkout/reset/commit, run filters/hooks or install into an imported source as a side effect. Approved project commands run through Reprise’s separate copy.
- Images bind to exact versions and capture inputs. Never substitute another draft’s picture. Manual images retain their supplied provenance. Capture is not proof of deployment or application correctness.
- Recover into a new folder outside the source and Reprise data directory. Never overwrite the current project. Preserve originals, history, screenshots, logs and failed diagnostics; saving or organizing does not authorize deletion.
- Process/access failures keep diagnostics and saved files. Use normal supported approval for the specific operation; do not alter permissions/model settings, assume an unknown process exited, or repeatedly relaunch to bypass denial.
- Core operations do not enable AI. Agent tool output/opened files may enter its model context. The unencrypted local library is not an independent backup or a system sandbox.

For detailed visual comparison/recovery, read [workbench tasks](references/workspace-tasks.md). Only for requested backup/migration, version deletion, storage, environment or legacy work, read [advanced workflows](references/advanced-workflows-0.8.md); for ordered folders/ZIPs, read [folder imports](references/folder-imports.md). Current entry and first-choice rules take precedence over historical reference text. General feature expansion is frozen; do not turn a draft task into cleanup or another product setup.
