# Reprise release boundaries and direction

Updated 2026-10-24. This is a scope statement, not a release-date commitment.

The goal is a local project workbench: **identify the right version, understand its changes, and recover or reopen it when needed**. The first audience is people repeatedly iterating on websites and small projects.

## Available publicly: v0.4.1

- Read existing Git history and ordered parent relationships.
- Compare commits and files.
- Preview configured revisions in separate runtime copies; attach media to exact revisions.
- Restore or export a selected snapshot with content verification.
- Use the same Python core through the CLI, local browser UI or portable agent skill.

[Download this release](https://github.com/orocoa/Reprise/releases/tag/v0.4.1) · [Reproduce the sample](QUICKSTART.md).

## Local development candidate: not in the public download

| Direction | Intended user outcome | What must be clear before release |
| --- | --- | --- |
| Ordinary-folder snapshots | Save a project version without initializing the source folder as a Git repository. | Explicit saves, exclusions, restoration fidelity and migration boundaries. |
| Shared exact content | Keep distinct versions while sharing identical stored file bytes. | File-level deduplication is not block-level deduplication or a guarantee of physical savings. |
| Version identification | Inspect files, revision-bound pictures or a running copy before making a decision. | Missing previews and failed runs remain visible; no cross-version substitution. |
| Managed-version deletion | See the lost version state, unique content and shared references before explicitly deleting selected managed snapshots. | Source Git history remains read-only; shared content, temporary space, interrupted operations and retained versions need verification. |
| Managed environments | Release verified generated dependencies/build outputs and rebuild them when requested. | Keep source, inputs and recipes; distinguish “previously rebuilt” from “can always rebuild.” External package availability is not guaranteed. |
| Backup and relocation | Move managed data with explicit coverage and verification. | A same-disk copy is not an independent backup; external source repositories have separate coverage. |

These items are being evaluated locally as a 0.7.0 candidate. They are not available by downloading v0.4.1 or cloning the current public branch. Internal checks do not establish independent user adoption or general reliability for every project size.

## Gates for a broader release

1. Match the downloadable package, source tag, README, screenshots and demo to the same version.
2. Reproduce save/identify/compare/restore workflows with synthetic projects, retain failure diagnostics and verify source files remain unchanged.
3. Test deletion impacts, shared references, interruption handling and retained-version restoration separately from read-only browsing.
4. Verify a supported environment build, explicit release and rebuild; document unsupported layouts and external dependencies.
5. Run the repository's regression, graph contracts and installation checks; report platform and browser coverage precisely.
6. Observe target users completing real tasks independently and returning when a similar task occurs. Use those results to choose the next scope.

## Outside the current direction

No whole-disk automatic cleanup, memory optimization, automatic deletion, cloud sync, silent Git writes, or promise that any old program can always run. Independent backups remain necessary.

If you have a task this direction should address, [describe your current method and the step that costs you time](https://github.com/orocoa/Reprise/issues/new/choose). Feature requests are useful when connected to a concrete task; a Star is not required.

[Back to README](../README.md)
