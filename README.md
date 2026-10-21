# Reprise · 倒带 — Local Git History Browser

[简体中文](README.zh-CN.md)

[![CI](https://github.com/orocoa/Reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/orocoa/Reprise/actions/workflows/ci.yml)

Reprise is a **local Git history browser**: compare commits and files, preview configured versions in **isolated copies**, and restore or export snapshots. Core history and diff workflows need **Python 3.9+ and Git**; they do not require an AI connection. Release notes and previews can be edited by hand or optionally with AI.

<!-- Screenshot: add when ready
![Reprise UI — commit route and file diff](docs/preview-ui.png)
-->

> **Screenshot needed:** main workbench with colored Git route + file diff or version compare. Spec in `ASSET_SPEC.md` (this PR pack). Path: `docs/preview-ui.png`.

**Get started:** [Install the agent skill](docs/AGENT-SKILL.md) · [Releases](https://github.com/orocoa/Reprise/releases/latest) · CLI below.

## Install the skill (recommended)

Download the [portable skill ZIP](https://github.com/orocoa/Reprise/releases/latest/download/reprise-skill.zip) or [WorkBuddy skill ZIP](https://github.com/orocoa/Reprise/releases/latest/download/reprise-workbuddy.zip). Keep the full `reprise/` directory and let your local agent follow `SKILL.md`. Requires Python 3.9+ and Git; no pip install and no native app.

In the target project, ask the agent to open history, compare files, configure an isolated preview, or restore a commit to a new folder / ZIP. Details: [docs/AGENT-SKILL.md](docs/AGENT-SKILL.md).

## Command-line setup (optional)

```sh
git clone https://github.com/orocoa/Reprise.git
python3 -m venv ~/.venvs/reprise
~/.venvs/reprise/bin/python -m pip install ./Reprise
source ~/.venvs/reprise/bin/activate
```

In any Git repo:

```sh
reprise .
reprise . --no-browser --lang en
reprise shutdown
```

Data lives under `~/Library/Application Support/Reprise` (macOS) or `$XDG_DATA_HOME/reprise` (Linux), outside the imported repo.

## What it is / is not

| Is | Is not |
| --- | --- |
| A readable UI over **existing Git history** | A hosted SaaS or cloud sync product |
| Preview in **isolated copies** when runtime is configured | A guarantee that every historical commit will build |
| Python + Git core; AI optional | An agent that silently rewrites your main working tree |

## More

[Agent skill guide](docs/AGENT-SKILL.md) · [CI](https://github.com/orocoa/Reprise/actions) · [Issues](https://github.com/orocoa/Reprise/issues)

<!-- Optional: migrate longer feature notes from the previous monolingual README into docs/ -->
