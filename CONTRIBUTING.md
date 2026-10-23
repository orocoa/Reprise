# Contributing to Reprise

Start with a real task or a small reproducible problem. Reprise's public release is v0.4.1; development-only work is separated in the [roadmap](docs/ROADMAP.md). Include your release tag or commit and whether you used the CLI, skill or browser UI.

## Useful contributions

- Try the [sample](docs/QUICKSTART.md) and report the first confusing or blocked step.
- Improve English or Chinese instructions while keeping commands and release boundaries consistent.
- Reproduce a bug with synthetic files, especially wrong revision identity, altered source files, restoration mismatches or misleading success reports.
- Describe a repeated task: what you currently use, what takes time, and whether Reprise helped you finish it.

Use the [issue forms](https://github.com/orocoa/Reprise/issues/new/choose). Failed and abandoned attempts are welcome. Do not upload private projects, personal paths, credentials, full application data or unredacted logs. No positive review or Star is required.

## Before changing code

Read [AGENTS.md](AGENTS.md), [architecture](docs/ARCHITECTURE.md), and [Git graph contracts](docs/GIT-GRAPH.md) when relevant. Keep source repositories read-only; preserve full revision identities and ordered parent edges. Commands need explicitly saved recipes before execution. Keep unrelated changes and diagnostic artifacts.

The canonical Python code is in `src/reprise/`, the browser UI in `web/`, and synthetic fixtures in `examples/`. Run from source with `python3 run.py`; no third-party Python runtime package is required.

For code changes, run the regression suite and relevant contracts:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/graph-layout.test.cjs tests/workspace-cache.test.cjs tests/evidence-model.test.cjs
```

Browser regressions opt in with `REPRISE_BROWSER_TESTS=1`; use the documented Node/Playwright paths for your environment. Follow [release checks](docs/RELEASE-CHECKLIST.md) for geometry, runtime, packaging or release changes. A documentation-only contribution should validate commands, links and stated version scope.

## Pull requests

Explain the concrete problem, resulting behavior, checks run and remaining limits. Small focused changes are easier to assess. Do not attach private diagnostics or silently update generated evidence to another revision. For a new major feature, describe the task and proposed scope in an issue first.

Retain MIT and third-party license notices. Do not promise timelines, platform support or benchmark results without evidence.
