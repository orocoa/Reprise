# Keep the source and rebuild an old environment when needed

**Version: 0.8.7. Inspect environment status first; release generated outputs only after explicit review.**

Your task is to understand what a version needs to run. A written install command, a previously successful build and start, and a currently running application are different states. Only registered generated outputs that pass a new check can enter a separate explicit release operation.

## Prerequisites

Complete [the first-run guide](getting-started.md). That static sample does not create a dependency environment; this page describes a separately chosen advanced operation. Use an explicitly added project with a saved recipe and obtain its `DATA`, `PROJECT`, and full `FULL_SHA`. Read `ENVIRONMENT_ID` from the actual `environments PROJECT` result; an absent record is not an identifier you can invent. The CLI `run` response is a job object, with the successful runtime under `result`: use `result.id` as `RUNTIME_ID` and `result.url` as the page address. The outer `id` is a job identifier and must not be passed to `stop`. Environment identifiers are different again.

A real project needs an explicitly reviewed and saved `command-web` recipe, with actual install/build/start commands and readiness conditions. `environment.outputs` names generated directories, `inputs` names versioned input files, and `tools` names required tools. A directory already present in the historical source cannot be treated as disposable output. Databases, uploaded files, and personal material are not caches.

## Default steps: inspect status and release conditions

```sh
python3 "$REPRISE_ENTRY" --data "DATA" environments PROJECT
python3 "$REPRISE_ENTRY" --data "DATA" environment-check ENVIRONMENT_ID
```

Inspect the project, full SHA, output directories, `rebuild_verified`, `releasable`, and `blockers`. The check releases nothing. `rebuild_verified` records a completed clean build and successful start; it is not a perpetual guarantee.

When you separately choose to open that version, run its saved recipe:

```sh
python3 "$REPRISE_ENTRY" --data "DATA" run PROJECT --sha FULL_SHA
```

Use the actual returned URL and runtime identifier. Open the page and confirm it belongs to the selected version. Stop that runtime when finished:

```sh
python3 "$REPRISE_ENTRY" --data "DATA" stop RUNTIME_ID
```

The default walkthrough ends here, with the environment retained.

## Separate explicit action: release, then attempt a rebuild

Only after separately choosing this specific environment and passing a fresh check, execute:

```sh
python3 "$REPRISE_ENTRY" --data "DATA" environment-release ENVIRONMENT_ID --confirm
```

This removes registered generated directories. Source, lockfiles, recipes, screenshots, logs, system tools, and global package-manager caches remain. When you need the version again, run the same project and full SHA to rebuild and start it under the saved conditions.

## Result

Read the environment record and release/run receipts to distinguish released, rebuilding, and successfully started states. After a new start, open the page and check its behavior. A process, an HTTP response, and a working browser interaction are distinct evidence. Releasing an environment does not delete a historical version.

The fixture's Python environment does not download dependencies with pip. It exercises this local workflow, not the availability of npm packages, private registries, or arbitrary toolchains.

## Failure and limits

Active processes, changed outputs, changed source, additional data, changed tools, shared hard links, or an unavailable `lsof` check can block release. Read `blockers` and retain the files; bypassing a check does not establish success. Shared hard-link layouts such as some pnpm environments may be conservatively rejected.

Commands execute as the current account and may access the network or host resources. `network: local` restricts browser capture, not package-manager commands. System libraries, host variables, external services, and future package sources are not fully archived. Lockfiles record dependency conditions but cannot guarantee a registry remains available. Failed attempts and diagnostics are retained.

A venv containing external interpreter links may fail the self-contained backup boundary. Backups do not silently omit these outputs. Understand the backup report before separately deciding whether to release a verified environment.

## Next step

Read [privacy and backup answers](privacy-and-faq.md), or return to [identify, compare, and recover](find-compare-restore.md). [Product overview](index.md) · [简体中文](../zh/environments.md)
