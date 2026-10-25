# Environment reuse and installation / 环境复用与安装

Read this when resolving the source Skill's tools, preparing an automatic picture, or a dependency is missing. The source Skill carries core/web source, not new interpreters. Use the host environment for this source distribution.

## Installation is an agent task / 由 Agent 完成接入

The main user request is: “帮我安装倒带 / Reprise，检查复用现有环境，缺少的依赖按官方方法安装，然后打开。” Resolve the real client Skill location and keep the entire extracted `reprise/` directory together. Preserve an existing installation before updating it. Continue authorized setup through installation and first open; do not stop at a command proposal when permission already covers it.

At completion, return the installed Skill entry, the verified absolute Python/`scripts/reprise.py` command, the workbench URL, and the actually checked capabilities. For an existing compatible environment, the core check/open commands are:

```sh
python3 /absolute/path/reprise/scripts/reprise.py doctor
python3 /absolute/path/reprise/scripts/reprise.py open --workbench --lang zh --no-browser
```

Resolve the interpreter as described below. The returned URL is the actual result; do not invent a fixed port. Files-only readiness and actual picture capture are separate outcomes. The manual commands are a reference for users who already manage their environment, not extra steps imposed on ordinary users.

## Reuse the host first / 先复用宿主

| Requested action | Required tools |
| --- | --- |
| Open the workbench, save files, read history, recover a copy | Python 3.9+ and working Git; a browser to view the UI. The Python core uses only the standard library. Ordinary-folder snapshots still use a Reprise-owned Git object store. |
| Automatic static HTML picture | The above, plus Node, the **Node/npm `playwright` library**, and matching Chromium or a tested existing Chrome executable. The current Playwright 1.62.1 requires Node 20+; prefer a currently supported LTS. Python's `pip install playwright` does not supply the Node module used here. |
| A command-based/Vite picture | The above plus the project's approved recipe and tools. The current narrow Vite plan calls npm, so a host's Node/pnpm alone does not establish that plan is runnable. |

If the developer already provides the required environment, use it. In Codex, use `load_workspace_dependencies` when available, and verify what it actually returns. Other hosts may not expose that tool. Do not assume an existing Node means Playwright, Chromium or npm is installed, and do not copy a maintainer's cache path into instructions.

For the source entry, invoke the verified Python executable and absolute `scripts/reprise.py`. Select Git through this command's PATH. For pictures, existing interfaces accept `REPRISE_NODE` (executable), `REPRISE_PLAYWRIGHT` (absolute installed Node module path) and `REPRISE_BROWSER` (optional existing browser executable). Put Node's directory on the same command PATH when project scripts need `node`; keep system tools available. Keep paths and variables scoped to the command/service, not shell startup files or global settings.

Resolve the requested tools before starting the workbench, and use the same environment for open/capture calls. A running service keeps its startup environment; a later caller's PATH does not update it. If a changed tool location requires reopening, use the normal verified shutdown/open flow for that service, retaining history and pictures. Do not hand-edit process records or kill a recorded PID directly.

The existing browser route starts an owned headless instance with a separate temporary context. It does not take over the user's open tabs, profile or login session. Compatibility still needs an actual capture. Do not set `REPRISE_BUNDLE_RESOURCES` for a source Skill.

## Missing tools / 缺少依赖

The agent should identify the missing component, present its concrete official installation method, target directory and download/execution scope, then carry it out within the user's existing authorization and the host's normal command approvals. Ask only for missing authorization or required administrator interaction. Do not make the user assemble environment variables by hand, add silent sudo/global installs, change model/security settings, or build a custom installer.

Reuse a working Python/Git rather than reinstalling them. If absent, choose the current supported method for the actual OS and architecture: [Python downloads](https://www.python.org/downloads/), [Git installation](https://git-scm.com/install/) and [Node downloads](https://nodejs.org/en/download). Python 3.9+ is the code compatibility floor, not advice to newly install an unsupported release. An installer needing administrator or native interaction is not a silent success.

For missing automatic-picture tools, use the Node library and Playwright's own browser installer, in a Reprise-dedicated tools/cache directory **outside every managed webpage source**. Do not scaffold a Playwright test project, use a global npm install, or modify a webpage's package files. A concrete plan for an already available compatible Node/npm is:

```sh
# REPRISE_TOOLS and REPRISE_BROWSER_CACHE are reviewed absolute, dedicated paths.
npm install --prefix "$REPRISE_TOOLS" --save-exact playwright@1.62.1
PLAYWRIGHT_BROWSERS_PATH="$REPRISE_BROWSER_CACHE" PLAYWRIGHT_SKIP_BROWSER_GC=1 \
  node "$REPRISE_TOOLS/node_modules/playwright/cli.js" install chromium
```

This is an installation proposal, not a claim it was run. Verify the resulting paths/versions, then pass the installed module as `REPRISE_PLAYWRIGHT` and the same `PLAYWRIGHT_BROWSERS_PATH` during Reprise execution. Preserve existing packages, caches and diagnostics; do not uninstall or clear them to retry. Chromium and the library must be compatible; Playwright's documented cache setting must be consistent between installation and use. See [Node library installation](https://playwright.dev/docs/library) and [browser installation/cache management](https://playwright.dev/docs/browsers#managing-browser-binaries).

Do not run Linux `--with-deps` or a system installer without the applicable host permission. If network, access or system trust blocks installation, retain the failure, explain the specific missing capability and continue independent file-saving work. Never clear quarantine or repeatedly execute an OS-blocked binary. No installation method guarantees access on every host.

## Diagnose the requested capability / 按能力诊断

Run the source entry's `doctor` for Python/Git/core and package integrity; it does not test Node, Playwright, browser launch, local listening or process observation. Report those as unchecked until the requested operation actually succeeds. A complete automatic picture needs `preview.status: complete`, real media and the exact saved SHA; an outer job completion or `doctor.ok` is insufficient.

File saving can succeed while a picture needs installation, configuration or command permission. Preserve its SHA and retry capture against it after the missing capability is available, rather than saving a duplicate. Existing process identity/boot checks and normal host approvals still apply; environment discovery does not bypass them. Project dependency installation/execution remains a separately approved recipe in Reprise's snapshot copy.
