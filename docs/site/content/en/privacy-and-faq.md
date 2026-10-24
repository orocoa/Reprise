# Reprise dependencies, privacy and FAQ

## Which tools are required?

Core operations need Python 3.9+ and Git. The Python core uses only the standard library. Automatic pictures also need Node, the Node Playwright library and a usable browser. Playwright 1.62.1 requires Node 20+; prefer supported Python and Node LTS releases. The agent checks/reuses tools and helps install missing dependencies through normal authorization; ordinary users do not assemble environment variables.

Reprise tools use a dedicated location. Approved website dependencies run in a separate copy. Neither setup writes tools into the managed website source.

## Does it record every edit?

No. Save deliberately before changing the site. Unsaved content cannot be retrieved later.

## Is my website uploaded?

Core version/workbench operations run locally. Agent tool outputs or files you ask the agent to read may enter its model context. A Skill does not promise that all information stays on the device.

The library is unencrypted and snapshots do not replace independent backups. Pictures may contain sensitive content; review them before sharing.

## Does a failed picture mean the files were lost?

File saving and capture are separate outcomes. Successfully saved files remain; retry the same draft’s picture. A different draft’s picture is never substituted.

## Were Codex, WorkBuddy and TRAE all tested?

Installation, discovery, actual draft/picture calls and browser recovery passed in this Mac’s Codex. Fresh-machine dependency setup, native selector/composer actions and native WorkBuddy/TRAE use remain unverified. Declared Linux/WSL source compatibility is not a test result from this run.

## How does it differ from Git or editor history?

Reprise connects a recognizable picture to saved files and a recovered copy. If editor checkpoints, Git or numbered folders with screenshots are already easier, another tool may not help.

## Does MIT mean no costs?

The source is MIT-licensed; dependencies retain their own licenses. Setup, storage, deliberate saving and maintenance still cost effort. Stars indicate interest rather than task completion or natural reuse.

[Overview](index.md) · [Set up and save](getting-started.md)
