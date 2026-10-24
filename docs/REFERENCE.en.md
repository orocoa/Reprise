# Reprise complete reference

> This page preserves the complete README reference from October 24, 2026. Start with the [concise overview](../README.en.md) or [quickstart](QUICKSTART.md). Run source commands from the source root. Unless explicitly marked public v0.4.1, features belong to the unreleased 0.7.0 local candidate. Public-release installation does not obtain candidate features.

The local 0.7.0 candidate adds a complete managed-version cleanup flow: select versions, inspect exact previews or run them, review lost history and shared content, explicitly delete, then verify retained versions and measured storage changes. Approved generated environments can be released separately and rebuilt on demand. Original source folders stay in place.

Start with the retained interactive sample: `python3 scripts/prepare_lifecycle_demo.py --to /new/path/reprise-interactive`. Run it from the candidate source root and choose a destination that does not exist. It prepares three runnable versions, keeps all versions and environments, and does not read your existing projects.

Use the `open_command` in `summary.json` to open the workbench, inspect and compare versions, and review deletion impacts while retaining the sample. See [lifecycle details](VERSION-LIFECYCLE.md). This candidate has not been publicly released.

[简体中文](../README.md) · [Try the sample](#try-a-complete-sample-workflow) · [Report your experience](https://github.com/orocoa/Reprise/issues/new/choose) · [Contribute](../CONTRIBUTING.md)

**Browse local project history, compare versions, and recover the one you need.**

Reprise brings versions, file changes, and recovery results into a local browser workspace. Use it when you repeatedly revisit a website revision or retrieve an earlier draft. It reads existing Git history and can save ordinary folder versions without initializing Git in your source folder.

## Development and public release

This source tree is the **0.7.0 local development candidate (October 24, 2026)**. The public [v0.4.1 release](https://github.com/orocoa/Reprise/releases/tag/v0.4.1), checked on October 23, provides the Git history workspace. Ordinary folder snapshots, managed-data backups, and relocation belong to the newer local candidate. They are not available merely by downloading the public `latest` release.

The sample below requires a development source tree containing `scripts/demo_workflow.py`. Release publication and platform validation are separate from local implementation; consult the [release checklist](RELEASE-CHECKLIST.md) and the actual release notes for your version.

## What it does

| Task | Current local candidate |
| --- | --- |
| Save drafts of an ordinary folder | Explicit snapshots, version comparison, shared storage for identical bytes |
| Browse a Git project's history | Real commits and parent edges; read-only source repository access |
| See how an earlier website looked | Version-bound imported or generated previews; configuration and dependencies may be needed |
| Recover a file or a full version | Write to a new location and read back the recovered content |
| Review duplicate copies | Read-only planning before recovery; recovery-verified candidates and an explicit selection list; no deletion |
| Remove selected managed versions | Review joint loss and shared references, explicitly delete, verify retained content and measured storage changes |
| Rebuild old environments | Approved opt-in recipes, verified generated outputs, explicit release, rebuild when run again |
| Understand storage | A ledger for the Reprise data directory; allocated blocks are not guaranteed reclaimable space |
| Back up managed data or move a project | Verified copies, new-directory data restoration, and checked relinking; external sources are reported separately |

Reprise does not provide automatic capture of every file edit, cloud sync, system cleanup, memory optimization, or a complete write-capable Git client. A restored source tree may still need dependencies, LFS objects, submodules, or external services to run.

## Try a complete sample workflow

Allow about five minutes for the sample, after the required tools are available. This is an onboarding target, not a measured guarantee. You need **Python 3.9+ and Git**. The current host scope is macOS/Linux; native Windows process support is not implemented.

From a development source tree, choose a destination that does not already exist:

```sh
python3 scripts/demo_workflow.py --to "$HOME/reprise-first-demo"
```

The script creates its own sample folder and separate data directory, saves two versions, compares them, restores the first version, and checks the recovered bytes. It also reports exact duplicates and managed storage. It does not read your existing projects, start a server, or remove files. All sample files and receipts remain under the destination. Use a new path for another run.

Read `README-local.txt` in the result directory for the workflow and the optional command to open that same sample in the browser. `summary.json` records version identities and checks. Passing this example demonstrates this sample only; it does not validate other files or an independent backup.

## Open a real project

From a source checkout:

```sh
python3 run.py open /path/to/project --no-browser
```

For an ordinary folder, request folder mode explicitly:

```sh
python3 run.py open /path/to/drafts --folder --no-browser
```

Open the local URL returned by the command. Ordinary folders gain history only when you explicitly save a version; existing Git projects retain their original commit history. Importing a repository does not commit, check out, reset, fetch, or install its code.

The service continues after closing its browser tab. When you want it stopped, use `python3 run.py shutdown`, with the same `--data` directory if you selected one. This stops the verified Reprise service and its owned tasks; saved data is retained.

## Use through a local agent

Reprise's Skill and CLI share one Python core. A complete Skill package includes instructions, scripts, and runtime assets; copying `SKILL.md` alone is insufficient. Run its `doctor` command first. See [agent installation and compatibility](AGENT-SKILL.md) for tested clients and installation paths.

You can ask a local agent:

> Use the Reprise skill to open this project, compare the versions I select, and recover the selected files to a new directory. Show the version identity, recovery receipt, and any missing content.

The agent needs local execution and access to your chosen files. A cloud-only agent cannot directly access your computer. Basic version operations do not require an AI service.

## Data and trust

- Core saving, hashing, comparison, and recovery run locally, with no automatic upload or telemetry. A local agent may place tool output or files it reads into its model context under that agent's data policy.
- Reprise stores original file contents and indexes. The local store is not encrypted. Excluding a path from future snapshots does not erase previously stored versions.
- A local snapshot is not an independent backup. Managed-data backups do not automatically include external Git repositories, unsaved source files, or external archives.
- Recovery writes to a new path. Duplicate candidates and selections do not delete originals or prove disk space has been reclaimed.
- Running a historical project requires an explicitly saved command recipe. It executes as local code, not inside a security sandbox. Previews must correspond to the exact version; missing evidence stays missing.

Read [privacy](PRIVACY.md), [backup and migration](BACKUP-AND-MIGRATION.md), and the [full usage guide in Chinese](REFERENCE.zh-CN.md#完整功能与使用说明) for boundaries and commands.

## Developer test: deletes synthetic versions

To exercise actual deletion, run this separate regression script in a new destination. It creates a main synthetic project and a project sharing content, jointly deletes the main project's first two versions, then restores and verifies the retained version and the sharing project. The retained interactive sample above remains the default walkthrough.

```sh
python3 scripts/demo_version_lifecycle.py --to /new/path/reprise-lifecycle-test
```

The destination must not already exist. The script does not read your existing projects; original inputs, source folders, runtime copies, and command receipts are retained. HTTP and restored-byte checks demonstrate only this sample, not browser screenshots, dependency rebuilding, or an independent backup.

## Help improve it

Tell us the task, how you normally do it, where Reprise helped or blocked you, and whether you used it again. Both successful and unsuccessful attempts are useful. [Submit a bug or usage report](https://github.com/orocoa/Reprise/issues/new/choose) without private files, credentials, personal paths, or unredacted logs. See [contributing](../CONTRIBUTING.md) for development checks.

If it helps with a real task, a Star makes it easier to find again. Reprise uses the [MIT license](../LICENSE); bundled assets retain their licenses in [third-party notices](../THIRD-PARTY-NOTICES.md).
