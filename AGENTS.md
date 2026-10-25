# Reprise contributor guide

- Canonical code: `src/reprise/`, browser UI: `web/`, fixtures/templates: `examples/`.
- Imported repositories are read-only. Never checkout, reset, commit, run filters/hooks, or install into source repositories as an import/preview side effect.
- Keep every existing source file, runtime, screenshot, video and failed diagnostic. New test artifacts belong in `work/test-artifacts/`; no automatic deletion features.
- No project-specific paths, titles, SHAs or route mappings in core code. Explicit migration scripts may consume paths supplied by the caller.
- Keep Git identity, detection, validated recipes, runtime processes, evidence and optional AI proposals separate; see `docs/ARCHITECTURE.md`.
- Imported/AI-produced command recipes must be explicitly saved before execution. AI suggestions never auto-apply. Do not change user model settings.
- All media binds to exact SHA and capture input. Missing historical assets are reported, never substituted from another revision.
- Git graph changes must follow `docs/GIT-GRAPH.md`: preserve full-SHA nodes and every ordered parent edge; lanes/colors are layout, not branch identity. Run the tracked graph contracts with Node available; geometry changes also require the opt-in browser graph regression. Never substitute handwritten demo lanes for the generic layout.
- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`. Browser tests opt in with `REPRISE_BROWSER_TESTS=1` and optional environment paths.
- Source-only Python runs with `python3 run.py`; the core uses no third-party Python package.
- UI navigation must retain a clear return path. Prefer in-place +/− expansion for related details; keep switcher options visible when content is empty, provide an explicit empty state, and preserve the originating context when closing or collapsing.

## Current product phase · 2026-10-25

- General feature expansion is frozen. Follow `docs/FEATURES.md` for the current capability inventory and boundaries.
- Prioritize agent-led setup, explicit checkpoint saves, exact-version images, real read-only Git relationships, safe retrieval and continuation in the recovered folder. Fix observed workflow, integrity and compatibility problems.
- Keep advanced and legacy capabilities available on demand; preserve existing files, data and diagnostics. Do not expand into cloud sync, broad cleaning, background snapshots, Git writes, semantic merging, another AI chat or new framework plans without a new concrete user request.
- A user's request for before/after checkpoints authorizes those calls in that task, not a background watcher. A successful capture alone does not authorize future command execution or preference changes.
- Release only the tested functional payload; distinguish package identity, actual verification and public release state.

- Screenshot choice is per project: ask once when genuinely unconfigured, persist yes/no before capture readiness, and reuse thereafter. Pending yes is intent, not execution approval; only explicitly saved configuration becomes its template. A failed picture does not reset the answer.
