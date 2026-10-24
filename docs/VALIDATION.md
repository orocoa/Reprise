# Reproduce validation for this local candidate

Historical internal reports and screenshots are not included in this source package. Their omission does not assert that a new package has passed those historical checks.

Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` for the core regressions. Run `node --test tests/*.test.cjs` for the Node contracts. Browser tests opt in with `REPRISE_BROWSER_TESTS=1` and require an explicitly available browser/runtime.

Use `python3 scripts/check_distribution.py --local-candidate` for a new retained installation check when building from a Git source checkout. This command needs the documented offline Python build tools. A source archive alone has no Git identity.

See [release checks](RELEASE-CHECKLIST.md), [Git graph contracts](GIT-GRAPH.md), and [the source export policy](../SOURCE-EXPORT-POLICY.json). Report the actual platform, source hashes, passes, failures and skipped checks for each new run.
