# Reprise contributor guide

- Canonical code: `src/reprise/`, browser UI: `web/`, fixtures/templates: `examples/`.
- Imported repositories are read-only. Never checkout, reset, commit, run filters/hooks, or install into source repositories as an import/preview side effect.
- Keep every existing source file, runtime, screenshot, video and failed diagnostic. New test artifacts belong in `work/test-artifacts/`; no automatic deletion features.
- No project-specific paths, titles, SHAs or route mappings in core code. Explicit migration scripts may consume paths supplied by the caller.
- Keep Git identity, detection, validated recipes, runtime processes, evidence and optional AI proposals separate; see `docs/ARCHITECTURE.md`.
- Imported/AI-produced command recipes must be explicitly saved before execution. AI suggestions never auto-apply. Do not change user model settings.
- All media binds to exact SHA and capture input. Missing historical assets are reported, never substituted from another revision.
- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`. Browser tests opt in with `REPRISE_BROWSER_TESTS=1` and optional environment paths.
- Source-only Python runs with `python3 run.py`; the core uses no third-party Python package.
- UI navigation must retain a clear return path. Prefer in-place +/− expansion for related details; keep switcher options visible when content is empty, provide an explicit empty state, and preserve the originating context when closing or collapsing.
