# Reprise FAQ

Scope: public **v0.4.1**, checked 2026-10-24. Development-only features are listed in the [roadmap](ROADMAP.md). This page describes Reprise by [orocoa](https://github.com/orocoa), the local Git history browser in [orocoa/Reprise](https://github.com/orocoa/Reprise).

## What does Reprise do?

Reprise lets you browse existing Git history, compare commits and files, preview configured revisions in separate copies, and restore or export a selected snapshot. Its first use case is finding and recovering the right version while iterating on a website or small project.

## Can I use it without an AI account?

Yes. Core history, comparison and restoration use Python and Git. The CLI and local browser workbench run independently of an agent. Optional AI assistance and the portable skill are additional entry points, not requirements for basic operation.

## Can I save ordinary folders without Git?

Not in the public v0.4.1 release. That release reads existing Git repositories. Ordinary-folder snapshots are being developed locally and will need a matching release, tutorial and validation before they are advertised as available.

## Does it automatically save every edit?

No. The public history comes from Git commits already in the project. It cannot recover edits that were never recorded. It does not replace your editor's undo history, create commits on import, or continuously back up your disk.

## Can I preview any old website commit?

Only when the required source, assets, runtime configuration and dependencies are available. A static page may need only its HTML entry; a framework project may need install/build/start commands. Preview evidence is tied to an exact revision. Missing media or dependencies are reported instead of borrowed from another revision.

## Does previewing modify my current checkout?

Reprise imports the source repository read-only and prepares separate runtime copies. You must save a command recipe before running it. Those commands execute as your user, so isolation by directory does not prevent an arbitrary command from accessing other files or the network.

## What does restore verification prove?

Restoration checks supported files against the selected Git revision and writes to a new destination. It does not prove that the application starts, that external services are available, or that you have an independent backup. Exported snapshots do not include `.git` history. Submodules and unavailable LFS content have explicit limits in the [skill guide](AGENT-SKILL.md).

## Is my data uploaded or encrypted?

Core local history and diff operations do not require cloud upload. Reprise does not encrypt its local application data. An external AI agent may receive tool output, optional AI providers receive their configured inputs, and install/build commands may use the network. Keep application data private and exclude secrets from shared diagnostics.

## Can it delete old versions or free disk space?

The public v0.4.1 release is not a cleanup tool. Managed-version deletion and environment release/rebuild are development work. Even with shared content, deleting a version record and reclaiming physical disk space are different operations; a version may retain valuable structure even when it has no unique file bytes. Future space reports must distinguish unique content, storage overhead and observed filesystem changes.

## How is this different from Git, a Git client or backup software?

Git records history; Reprise reads it and adds a workbench for revision browsing, configured previews and recovery. A full Git client is a better fit when you need staging, committing, merging or pushing. Backup tools serve broader backup, retention and disaster-recovery needs. Reprise does not replace independent backups and makes no claim that its storage is smaller or faster than those tools.

## Which systems and agent clients work?

The core targets macOS and Linux with Python 3.9+ and Git. The sample generator needs Git 2.28+. Client installation and test coverage differ; consult the [client matrix](AGENT-SKILL.md#各客户端入口) and [release checklist](RELEASE-CHECKLIST.md). Native Windows support and universal agent-client compatibility are not promised.

## Why is the development demo different from the download?

The local candidate contains newer, unpublished work. Use the release tag, commit and entry point to identify what you have. The README pins public examples to v0.4.1; a successful local experiment is not evidence that those changes are in a downloadable release.

[Try the sample](QUICKSTART.md) · [Report a problem or use case](https://github.com/orocoa/Reprise/issues/new/choose) · [Back to README](../README.md)
