# Version deletion and preview resources

Use the registered project and exact version already identified in the conversation. A cleanup request does not authorize deleting other projects, original source folders, recovery copies, global caches or old Skill runtimes.

| User goal | Existing operation and result |
| --- | --- |
| Reduce memory from a preview | In the running preview click **停止预览 / Stop preview**, or use the same runtime's stop control in settings. Closing the preview dialog only returns to history; it does not stop a webpage that may still be open in another tab. `runtimes` lists owned records; `stop RUNTIME_ID` stops a selected one through identity-checked cleanup. |
| Stop the whole workbench | `shutdown` for the verified data directory stops its service and owned previews. Saved drafts, screenshots and files remain. Do not signal raw PIDs or stop another data directory. |
| Keep a draft but free generated dependencies | Select the version → **删除 / Delete** → **仅清理环境 / Clear environment only** → review → confirm. Available only for a registered, successfully built environment. Stop active previews first using the offered control. Modified or unverified outputs block release. Later runs may need network access to rebuild dependencies. |
| Delete a saved folder draft and its managed attachments | Select the version → **删除 / Delete** → review the full scope → confirm. This removes the saved state plus that version's owned runtime copies and exact-version media. Retained versions are verified; original folders, external backups and recovered copies remain. |
| Remove a read-only Git/archive entry | The same UI explicitly offers **从 Reprise 移除 / Remove from Reprise**. It removes local membership and owned attachments; original Git commits/archive bytes remain. It does not reclaim source-repository space. |

For joint deletion of folder snapshots, use `version-delete-plan PROJECT --sha FULL_SHA` (repeat `--sha` for a selected set), then `version-delete PROJECT --plan PLAN_ID --confirm` within the user's explicit selection. This CLI path deletes saved content but retains screenshots and runtime attachments; do not claim it has the UI's broader scope. See [advanced workflows](advanced-workflows-0.8.md) for transaction recovery, joint-reference accounting and environment CLI commands.

Use `storage` only when disk accounting is requested. It is an explicit scan of Reprise's data directory, not a background scan of the computer. Logical bytes, allocated blocks and free volume space have different meanings; none proves exclusive physical space freed on APFS. Stopping a process releases its process resources, not saved files. Do not call disk cleanup “RAM optimization” or promise a measured memory/CPU improvement without measuring it.

If the plan changes, re-plan before execution. If cleanup reports partial failure, retain the receipt and report what actually completed; do not retry broadly or call the result complete. A missing screenshot never authorizes borrowing another version's image.
