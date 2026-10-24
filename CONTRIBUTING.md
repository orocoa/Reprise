# Contributing to Reprise

Useful contributions start with a real task: finding a version, understanding a change, recovering content, or reviewing duplicate copies. A report that explains why your existing method works better is as valuable as a feature request.

## Report a bug or a usage result

Use the [issue forms](https://github.com/orocoa/Reprise/issues/new/choose). Include the Reprise version or commit, your OS, what you expected, and what happened. Distinguish a release ZIP, installed Skill, and source checkout: they may contain different versions.

As checked on October 24, 2026, [v0.4.1](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) is the public release; the prepared tutorial and recording describe an unreleased **0.7.0 LOCAL CANDIDATE**. Include the candidate label and package name when applicable. Public `latest` and a local candidate are separate distributions.

Use [Bug report](https://github.com/orocoa/Reprise/issues/new?template=bug_report.yml) for a reproducible failure and [Usage feedback](https://github.com/orocoa/Reprise/issues/new?template=usage-feedback.yml) for what happened during a real task. Start with the [quickstart](docs/QUICKSTART.md) if you need an isolated example.

Prefer a small synthetic example. Do not post private files, credentials, personal paths, or unredacted logs. Full project listings and raw diagnostic bundles are not required. If you cannot share a safe example, describe the file types and steps in general terms.

For suspected data loss or unintended modification, preserve the affected source, Reprise data, and receipts. Avoid repeating the operation against the only copy. Report a safe summary; do not upload the affected data to a public issue.

For a usage report, tell us your original task, previous method, whether you completed it independently, and whether you actually chose Reprise for a later similar task. There is no need to provide a positive review or a Star.

## Propose a change

For substantial changes, explain the user task, current limitation, proposed behavior, and tradeoffs in an issue before a broad rewrite. Small fixes and documentation improvements can go directly to a pull request. Preserve existing files and unrelated changes.

For documentation, keep version status, prerequisites, commands, and expected results together. Preserve the detailed [Chinese](docs/REFERENCE.zh-CN.md) and [English](docs/REFERENCE.en.md) references when simplifying the home page. Do not publish local candidate links, platform claims, or demo outcomes without matching artifacts and validation.

Code lives in `src/reprise/`, browser UI in `web/`, and synthetic fixtures in `examples/`. Read [AGENTS.md](AGENTS.md) and [the architecture](docs/ARCHITECTURE.md) before changing behavior.

The core depends on Python 3.9+ and Git, with no third-party Python runtime packages. Browser capture adds optional Node/Playwright dependencies. Source-only development starts with:

```sh
python3 run.py --help
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

For graph or UI changes, run the relevant Node contracts:

```sh
npm run test:graph
npm run test:workspace
```

Graph geometry changes also require the opt-in browser graph regression described in [GIT-GRAPH.md](docs/GIT-GRAPH.md). For browser behavior, follow [the release checklist](docs/RELEASE-CHECKLIST.md) and run the relevant browser tests with available dependencies:

```sh
REPRISE_BROWSER_TESTS=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

State exactly what passed, failed, or was skipped, and the platform used. Store new QA artifacts under `work/test-artifacts/`; retain failed diagnostics. Never attach private user data or credentials to a public pull request.

## Contracts to preserve

- Imported source repositories are read-only. Import and preview must not commit, checkout, reset, fetch, install into the source, or execute its hooks or filters.
- Preserve full Git commit identity and every ordered parent edge. Folder snapshots and imported archive views retain their own provenance.
- Recovery writes to a new destination. Report missing content and unsupported metadata; do not substitute another version or claim an application runs merely because its files restore.
- AI proposals and imported command recipes require explicit saving before execution. Preserve user model and permission choices.
- Duplicate byte counts, file lengths, allocated blocks, and actual freed space are distinct. A selection list is not a deletion receipt.
- Keep local candidate capabilities, public release features, and validated platforms separate in documentation.

Contributions use the project's [MIT license](LICENSE); preserve third-party license notices. We review changes by correctness, task value, and maintenance cost. Adding more features or more dependencies is not a goal by itself.
