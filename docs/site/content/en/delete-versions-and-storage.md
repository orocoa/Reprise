# Understand what removing an old version will lose

**Version: 0.8.6. The sample walkthrough can stop at planning; execution requires explicit review and confirmation.**

Distinguish deleting a saved state, removing a local entry, releasing generated dependencies and stopping a preview. Managed folder drafts can be deleted. External Git and archive entries can be removed from Reprise while their source history remains.

## Current interface and scope

Select a version, click **Delete**, review the scope and confirm. Folder-draft deletion removes its saved state, owned runtime copies and exact-version media. **Remove from Reprise** for Git/archive entries removes local membership and managed attachments while retaining source commits and original archives. Original folders, external backups and recovered copies remain. **Clear environment only** is available only for a registered, verified generated environment. Active previews must be stopped before reviewing the scope again.

Memory and disk are separate: **Stop preview** in the running-preview dialog ends that instance’s processes and retains saved files. **Back to version** only closes the dialog. **Stop Reprise** in settings stops that data directory’s service and previews. Releasing an environment removes verified generated dependencies and mainly affects disk usage; it is not proof of an overall RAM or speed improvement.

The joint CLI deletion below removes saved content while retaining pictures and runtime copies. Its scope differs from single-version attachment deletion in the interface.

## Prerequisites

Follow [identify and recover](find-compare-restore.md) to check the full SHAs. Replace `DATA`, `PROJECT`, and `FULL_SHA_*` with values from the same sample. Inspecting a plan does not authorize execution. The sample contains no personal project data.

## Default steps: compare impact and retain the versions

1. Open version management, select one draft, inspect that version's files and evidence, then return.
2. Read its full SHA, lost paths and metadata, unique content, still-shared content, and retained-version count.
3. Add a second draft and inspect the joint plan. Joint reclamation is not the sum of individual plans.
4. Stop at the impact explanation and leave deletion unconfirmed.

CLI inspection:

```sh
python3 "$REPRISE_ENTRY" --data "DATA" version-delete-plan PROJECT --sha FULL_SHA_A
python3 "$REPRISE_ENTRY" --data "DATA" version-delete-plan PROJECT --sha FULL_SHA_A --sha FULL_SHA_B
python3 "$REPRISE_ENTRY" --data "DATA" storage
```

Planning retains plan and state records but deletes no versions. `storage` inspects only the selected data directory, not your entire computer.

## Read the numbers correctly

| Field | What it describes | What it does not establish |
|---|---|---|
| `unique_content_bytes` | Raw content bytes exclusive to the selected set, counted once per content object | Guaranteed disk space freed |
| `shared_content_bytes` | Content still referenced by other versions, projects, or diagnostics | Bytes available to reclaim repeatedly |
| `store_bytes_reclaimed` | Change in regular-file lengths in the main object store; it can be negative | Net savings across the complete data directory |
| `allocated_bytes_reclaimed` | Change in allocated-block accounting | Exclusive physical storage under APFS block sharing |
| `volume_free_delta` | Difference between two observations of free volume space | A change caused only by this operation |

If `storage.reclaimable_bytes` is unknown, keep it unknown; do not substitute logical bytes. An environment check's `output_bytes` is not a guaranteed reclamation figure either.

Zero unique content does not mean zero loss. The version's names, metadata, directory arrangement, and complete historical state still disappear. Compression, indexes, temporary repacking space, retained receipts, and other processes affect storage measurements. This guide contains no unverified savings figure.

## Separate explicit action: execute deletion

Only after separately choosing to execute and accepting the reviewed history loss, use the real `PLAN_ID` returned by that plan:

```sh
python3 "$REPRISE_ENTRY" --data "DATA" version-delete PROJECT --plan PLAN_ID --confirm
```

This command deletes versions and **is not part of the default walkthrough**. It rechecks the plan and verifies retained content across the managed store before reclaiming the original object store. Original sources, existing recovered copies, screenshots, runtime copies, logs, and orphaned diagnostics remain. This is not secure erasure.

## Result, failures, and limits

The default result is a reviewable plan with the versions retained. After a separately authorized execution, inspect the deletion receipt, retained-content checks, and the distinct storage measurements. Restore a retained version to a new directory to check the content you need.

Changes to objects, references, or snapshots invalidate an earlier plan; generate a new one. An incomplete reclamation transaction can block saving and backups. Follow the reported recovery steps and retain diagnostics instead of deleting transaction directories. Insufficient space leaves the original store intact. The first deletion changes the managed-store format; older clients are incompatible, so subsequent access requires 0.7.0 or a compatible version. No multi-terabyte stress-test result is claimed.

## Next step

If the task is to release verified generated outputs temporarily, read [environment release and rebuilding](environments.md) before deciding to remove history. [Product overview](index.md) · [简体中文](../zh/delete-versions-and-storage.md)
