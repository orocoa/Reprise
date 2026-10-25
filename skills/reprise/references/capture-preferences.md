# Capture choices and configuration / 截图选择与配置

Use this for first-use choice, configuration, overrides or capture failure. The choice is per registered project, shared by CLI and workbench, not dependent on a chat’s memory.

## First answer

Read `preview-preferences PROJECT` for an existing project. `not_configured: true` means the default `remind` result is not a user answer. For a new webpage project, ask once whether **future saves of this project** should include an image, unless an explicit project-level choice is already known. Plain file tasks need no image prompt. A request explicitly limited to one operation keeps that scope.

After yes:

```sh
python3 "$REPRISE" save /known/webpage --title "Before spacing changes" --preview auto --preview-pending
# Already registered:
python3 "$REPRISE" snapshot PROJECT --title "Before spacing changes" --preview auto --preview-pending
# Or remember the answer without creating a draft:
python3 "$REPRISE" preview-preferences PROJECT --mode auto --pending-recipe
```

After no, use `--preview none` on the first save/snapshot, or `preview-preferences PROJECT --mode none`. Future saves omit preview flags and reuse the stored choice. Do not ask again after restart, in another conversation, after a missing image, or after a cancelled one-time capture. A change to the ongoing choice must come from the user.

`pending_recipe: true` records **yes, configuration not ready**. It does not approve package scripts. A directly viewable static draft can prepare and explicitly save its bounded recipe, then capture. The first explicitly saved non-manual recipe completes that pending preference. It becomes the future template even if that first browser attempt fails; image completion is still reported separately. If the user has changed to no while a task was queued, saving its recipe must not re-enable future capture.

## Commands and entry points

For a command-based project, show the proposed installation and run commands, including scripts/configuration they execute, and explain that the confirmed settings will also be reused for this project’s future saves. Obtain only missing authorization. Save the reviewed recipe for the returned exact SHA **before** running capture:

```sh
python3 "$REPRISE" recipe PROJECT /approved-recipe.json --sha FULL_SHA
python3 "$REPRISE" capture PROJECT --sha FULL_SHA
```

Detection, `package.json`, imported `.reprise.json` and AI suggestions do not approve execution. Pending yes must remain pending if configuration or approval is absent. Do not install into the managed source. Static HTML support does not establish automatic support for every framework.

An existing configured automatic preference keeps its approved template. If new commands/entry points are needed, review that changed scope, save the new exact recipe, and, when approved for future reuse, update with `preview-preferences PROJECT --mode auto --recipe-sha FULL_SHA`. Ask about the changed configuration, not whether the user still wants images.

A restored library may report `restored_auto_requires_confirmation: true`: the previous image choice is known, while execution needs destination-host review. Keep those meanings separate.

## One-time overrides

- Explicit “capture this draft only” uses ordinary save/snapshot when an approved automatic template exists; otherwise use `--capture-static` for that one operation. This flag does not change the saved preference and cannot combine with `--preview`.
- Explicit “no image for this draft only” works with an existing files-only choice. The current CLI has no one-time skip for an already automatic project. Explain that specific limit before a command that would capture; do not invent a flag, silently change the ongoing preference, or execute contrary to the user’s instruction.
- Existing explicit `manual` / `remind` modes remain compatible until the user changes them. They are distinct from the unconfigured default.

## Results and retries

Inspect saved files and image status separately. Only a complete capture with actual media belonging to the same SHA is ready. `needs-approval`, `needs-configuration`, failed or cancelled capture leaves successfully saved files and the ongoing image choice intact.

Retry capture for the saved SHA after the blocker is resolved. Do not create a duplicate draft or reset the preference to ask the same question again. If unchanged files reuse a draft, retain its actual title; a new requested title alone does not create or rename it.
