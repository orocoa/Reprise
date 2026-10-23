# Reprise · 倒带

**Find the right version of your project. Compare changes, preview it, and restore it to a new folder.**

[简体中文](README.zh-CN.md) · [Try the sample](docs/QUICKSTART.md) · [Download v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) · [FAQ](docs/FAQ.md)

[![CI](https://github.com/orocoa/Reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)

Reprise is a **local Git history browser** for people iterating on websites and small projects. Browse real commits, compare files, preview configured revisions in separate copies, and recover a chosen snapshot without replacing your working files. The core needs **Python 3.9+ and Git**; AI is optional.

![Reprise workbench showing two real commits and changed files from the generated static-web sample](docs/preview-ui.png)

The screenshot uses the repository's generated `static-web` sample. Previews must be generated or imported for the exact revision; they are not automatically available for every commit.

## Start with a task

| Your task | What you can do in the public v0.4.1 release |
| --- | --- |
| “Which version had the page I wanted?” | Browse real commits, inspect files and available revision-bound previews. |
| “What changed between these two versions?” | Compare commits and changed files in the workbench. |
| “Can I open that old page?” | Save a suitable runtime configuration, then run a separate copy. Dependencies and external services may still be needed. |
| “Can I get that version back?” | Restore a snapshot to a new folder or export a ZIP, with Git-blob verification. The result does not contain `.git` history. |

**Release scope, checked 2026-10-24:** the public download is **v0.4.1**. Ordinary-folder snapshots, shared content storage, version-deletion impact reports and managed-environment release/rebuild are in a **local development candidate**, not in this download. See the [roadmap and release boundaries](docs/ROADMAP.md).

## Try it with sample files

Use a new destination for the clone. Run the next command only after the previous command succeeds. This source-based demo needs Python 3.9+ and Git 2.28+ and creates its own sample repositories.

```sh
git clone --branch v0.4.1 --depth 1 https://github.com/orocoa/Reprise.git reprise-first-run
cd reprise-first-run
python3 scripts/create_demo_projects.py --output work/first-run/projects
python3 run.py --data work/first-run/data open work/first-run/projects/static-web --lang en
```

Select a commit, compare its files, then restore it to a new directory outside the sample repository. The [step-by-step guide](docs/QUICKSTART.md) explains preview setup, verification and how to stop the service. It keeps generated samples, restored files and diagnostics in place.

## Use it with a local agent

Download the complete [portable skill ZIP](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-skill.zip) or [WorkBuddy ZIP](https://github.com/orocoa/Reprise/releases/download/v0.4.1/reprise-workbuddy.zip). Keep the full `reprise/` directory, including its scripts and assets. A skill-capable local agent can open an existing Git project through the same Python core; no pip installation is needed for the portable package.

Ask it to open the project's history, identify a revision, compare files, or restore that revision to a new folder. Preview commands need a saved configuration. Client-specific setup and verification limits are in the [agent skill guide](docs/AGENT-SKILL.md).

Prefer a CLI installation? [Installation and usage](docs/QUICKSTART.md#install-the-cli-optional) includes the source and installed-command options.

## Local data and execution

- Imported Git repositories are read-only. Reprise does not create commits or reset your source repository as an import or preview side effect.
- Core history and diff operations do not require AI or cloud upload. Optional AI services and an external agent have their own data flows. Local application data is not encrypted by Reprise.
- Running an old project executes approved commands as your user. A separate copy is **not a security sandbox**; dependencies may use the network. `network: local` limits the capture browser, not install or build commands.
- Restore verifies file content for the selected revision. That does not prove the application runs or that an independent backup exists. Back up source repositories separately.
- Sample files, runtime copies, captures and failed diagnostics are retained. The public release is not a disk cleaner or memory optimizer.

Default data locations: `~/Library/Application Support/Reprise` on macOS; `$XDG_DATA_HOME/reprise` on Linux, or `~/.local/share/reprise` when unset. Keep data outside imported repositories and stop the service with the same `--data` directory before upgrading or backing up.

## Help shape the next release

Tell us **what you tried, where it stopped, and what you used before**. Failed attempts are useful; private files and unredacted logs are not needed. [Report a bug or a real use case](https://github.com/orocoa/Reprise/issues/new/choose) · [Contribute](CONTRIBUTING.md).

If Reprise is useful to you, a Star helps you find it again. Feedback about a completed task helps decide what to build next.

[Full Chinese user guide](docs/USER-GUIDE.zh-CN.md) · [Recipes](docs/RECIPES.md) · [Architecture](docs/ARCHITECTURE.md) · [Validation](docs/VALIDATION.md) · [Release checklist](docs/RELEASE-CHECKLIST.md)

Maintained by [orocoa](https://github.com/orocoa). Code: [MIT](LICENSE). Fonts, icons and imported media retain their own terms; see [third-party notices](THIRD-PARTY-NOTICES.md).
