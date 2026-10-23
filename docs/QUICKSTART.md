# Try Reprise with a sample Git project

This guide targets **v0.4.1**, the public release checked on 2026-10-24. It creates synthetic sample repositories; you do not need to import a private project. Allow time to clone the source and inspect two revisions. No fixed completion time is promised.

## 1. Prepare the source and sample

Requirements: macOS or Linux, Python 3.9+, Git 2.28+ for the sample generator, and a browser. Check `python3 --version` and `git --version`. The core uses Python's standard library and Git; a basic static preview does not require Node or an AI account. Automatic screenshot/video capture has separate dependencies.

Use a new clone directory. Run these commands in order, proceeding only when each succeeds:

```sh
git clone --branch v0.4.1 --depth 1 https://github.com/orocoa/Reprise.git reprise-first-run
cd reprise-first-run
python3 scripts/create_demo_projects.py --output work/first-run/projects
python3 run.py --data work/first-run/data open work/first-run/projects/static-web --lang en
```

The generator creates three new sample repositories. `static-web` contains two real commits with a changed headline and accent color. The generator refuses an existing output directory. The Reprise data directory is a sibling of the sample repositories, outside each imported source repository. Files and diagnostics stay in `work/first-run/`.

If automatic browser opening is unavailable, add `--no-browser` to the last command and open the URL returned by the command. Use that actual URL; the port is selected at runtime.

## 2. Identify and compare a revision

In the workbench, check the project name and select the first commit, `Initial static-web`. Inspect its files, then compare it with `Improve static-web`. The changed file is `index.html`; a two-commit sample is enough to inspect the headline and color change.

The history represents Git commits, not automatic screenshots. An empty preview means no media has been attached for that revision yet.

## 3. Preview the static page

Select a revision, switch to **Previews**, and click **Run this revision**. When the settings dialog opens, choose **. · Static website** under **Detected entry points**, then **Save revision settings**. Saving returns to the revision without executing it. Click **Run this revision** again to start its separate copy, then open the returned local preview. The bundled sample needs no install or build command.

For your own framework projects, inspect and save their install/build/start recipe first. Approved commands run with your user account and may access the network. A separate directory is not a sandbox, and a successful sample does not prove every historical project will run. See [recipes](RECIPES.md).

## 4. Restore and check the first version

With `Initial static-web` selected, use **Recover / Export**. Choose a destination that does not exist, outside the imported sample repository and the Reprise data directory; for example, an absolute path ending in `reprise-first-run/work/first-run/restored-first`.

Reprise checks the restored files against the selected Git revision. You can also compare the sample file directly from the source checkout:

```sh
git -C work/first-run/projects/static-web show HEAD~1:index.html > work/first-run/expected-first.html
cmp work/first-run/expected-first.html work/first-run/restored-first/index.html
```

A zero exit status from `cmp` confirms these two files contain the same bytes. That is evidence about this file and this revision, not application execution or disaster recovery. The restored snapshot does not contain `.git`; submodules and unavailable LFS objects are not silently filled in.

## 5. Stop the service

Closing the browser tab leaves the local service running. From the same source checkout, run:

```sh
python3 run.py --data work/first-run/data shutdown
```

Keep the sample and its diagnostics for review. To repeat from scratch, use a different new clone/output directory. Do not delete your working project to test recovery.

## Install the CLI (optional)

After cloning the pinned source, use a new virtual environment if you want the `reprise` command:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
```

Packaging may download build tools. The source entry `python3 run.py` avoids that installation step. From an existing Git repository, `reprise .` opens its history; `reprise shutdown` uses the default data directory. Always repeat any custom `--data` value when stopping the service.

For a portable agent installation, use the complete release ZIP and follow the [skill guide](AGENT-SKILL.md).

## If the sample stops

Keep the error and the generated files. [Report the step, release, operating system and a short redacted error](https://github.com/orocoa/Reprise/issues/new/choose). Do not upload private projects, credentials or complete application data. [FAQ](FAQ.md) · [Back to README](../README.md)
