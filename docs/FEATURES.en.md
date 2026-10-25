# Reprise feature scope

2026-10-26 · Reprise 0.8.0 feature and maintenance scope.

Reprise helps people iterating on local webpages save a draft before changes, recognize it by appearance, and retrieve a new copy to keep editing.

## Default workflow

1. Give the complete Skill to your agent. It checks/reuses tools, fills missing dependencies through authorized official methods, then opens the workbench.
2. On first use, answer once whether this project should include images. The answer is persisted even before configuration is ready. Then ask: “Save a draft before and after this edit.” Files and pictures are reported separately.
3. Select a saved appearance, compare if needed, and recover a new copy. Paste the continuation instructions into the editing agent so it uses the recovered folder.

Unrecorded files cannot be recovered afterward. An image is not a backup of external services, dependencies or databases.

## Existing capabilities

| Level | Capability | Entry and boundary |
| --- | --- | --- |
| Main workflow | Install, open, stop | Skill and [setup](AGENT-SKILL.md#english). Opening does not import or save the working directory. |
| Main workflow | Save, name/time, visual history, favorites and search | Workbench. Names are optional; unchanged files reuse the existing draft/title. |
| Main workflow | Compare images/files, retrieve complete drafts or selected files, verify readback | Selected revisions. Images belong to their exact version; recovery uses a new folder. |
| Fewer repeat steps | Remember capture preference, time-based names, keyboard saving, continuation instructions | Explicit project preferences can be reused. The first save explains its scope. |
| Optional setup | Static captures, supported npm/Vite command plans, manual images | Save/image settings. Review and save commands before execution in a separate copy. Other frameworks use explicit settings. |
| Main workflow · Git projects | Git history/graph, related archives and detailed diffs | Imported Git remains read-only; folder snapshot order is not original Git history. |
| Advanced | Old folders/ZIP contents, cost previews, duplicate/original reports | Settings → Advanced management. [Folder imports](FOLDER-IMPORTS.md). Reports do not remove originals. |
| Advanced | Independent backup, new-library restore, migration and relinking | Settings → Advanced management. [Backup](BACKUP-AND-MIGRATION.md). |
| Advanced | Integrity, storage, explicit saved-version deletion, runtime checks/release | Settings → Advanced management. [Lifecycle](VERSION-LIFECYCLE.md). Existing confirmations and verification boundaries apply. |
| Retained compatibility | Legacy archives, historical CLI/packages, optional AI interfaces and native-shell prototypes | Developer references/adapters; excluded from first-use tasks and broader support claims. |

Existing files, packages, data, interfaces and diagnostics remain in place. Entry-point simplification does not remove their underlying capabilities.

## General expansion is frozen

Work now addresses observed installation, saving, capture, recognition, recovery, continuation and failure-feedback problems, plus necessary integrity and compatibility fixes.

Do not initiate cloud sync, collaboration, general disk cleaning, background snapshots, a Git write client, semantic merging, another AI chat/model setup or new framework-adapter plans without a new concrete user task.

Evaluate actual task completion and unprompted reuse when another opportunity occurs. Passing tests, views and Stars do not establish independent real-world use.
