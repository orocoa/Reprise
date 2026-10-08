# Reprise module contract (v1)

Canonical source lives in this repository. Python 3.9+, standard library server/Git core; optional Node + Playwright for browser capture. All source repositories are read-only. Import never runs project code. State is outside source repositories under a configurable data directory (platform application data by default; `--data` overrides). Original demo and artifacts are retained.

## Git module — `src/reprise/git.py`
`Repository(path)` validates and normalizes normal/bare/worktree Git repositories; raises ValueError for invalid input.
- `.info()` -> {path, git_dir, work_tree|null, bare, shallow, head|null, branch|null, object_format}
- `.history(ref='--all', limit=50, offset=0)` -> {commits:[{sha, parents:[], subject, author, authored_at, committed_at, refs:[]}], has_more, next_offset}
- `.refs()` -> [{name, sha, kind}]
- `.resolve(revision)` -> full commit SHA, validates input, supports SHA/ref, rejects options.
- `.tree(revision)` -> [{path, mode, type, oid, size}], Git paths roundtrip with filesystem encoding where practical.
- `.blob(revision, path, max_bytes=1048576)` -> bytes, size bounded.
- `.diff(target, base=None)` -> {target, base|null, parents:[], files:[{status,path,old_path?}], counts:{...}}; omitted base uses first actual parent; root uses empty tree; accept explicit other parent.
- `.status()` -> {available, dirty, changes:[{path,status}], ...}; bare unavailable; unborn supported.
- `.materialize(revision, destination)` -> metadata; destination must not exist, blob extraction without source mutation or filter execution, no path traversal/external symlink access, explicit submodule/LFS limitations. Keep partial output if failure.

## Detection — `src/reprise/detection.py`
`detect(repository, revision='HEAD')` -> {kind, label, confidence, signals:[], capabilities:{history,diff,run,capture,manual}, recipe:object|null, warnings:[], candidates:[]}. Scan committed tree/manifests, deterministic, no process or network. Static built HTML can get validated `static-web` recipe automatically. Source frameworks/native/game/CLI get recognition and configuration requirement, never fabricated screenshots or unapproved build/install execution. Multiple roots returned as candidates; no assumed universal framework start command.

## Runtime & capture — `src/reprise/runtime.py`, `recipes.py`, `capture.py`
`validate_recipe(dict)` -> normalized dict or ValueError.
Recipe v1: {schema:1, adapter:'static-web'|'command-web'|'manual', root:'.', commands:{install?:[[argv]],build?:[[argv]],start?:[argv]}, readiness:{path:'/',selector?:str,timeout_ms:15000}, captures:[{id,route:'/',viewport:{width:1440,height:900,scale:2},full_page:bool,wait_for?:str,record_ms?:1000,steps:[{action:'click'|'press'|'fill'|'wait', selector?:str,key?:str,value?:str,ms?:number}],record?:bool}], network:'local'|'allow'}.
Commands use argv and `{port}` substitution, no shell. Local host PORT/HOST env; explicit recipe save grants command execution on later Run/Capture only. Static import/detect never executes code. Recipe resolution user override > committed `.reprise.json` (requires explicit save before command execution) > detected static recipe. Runtime must not read source worktree as historical state.
`RuntimeManager(data_dir)`:
- `.start(repository, sha, recipe, approved=False)` -> {id,sha,url,path,adapter,...}. Stored durable metadata/logs, owned process identity, materialize into unique data_dir/runtimes directory.
- `.stop(runtime_id)` -> state; stop only owned process/group; no files deleted.
- `.list()` -> states with live status.
`CaptureService(data_dir, runtime_manager)`:
- `.capture(repository, project_id, sha, recipe, base=None, approved=False)` -> evidence record {id,project_id,sha,base,recipe_hash,status,items:[{capture_id,side,sha,path,media_type,width,height,...}],errors:[],...}; automatic uses same recipe/scenario for both sides, key includes project+SHA+base+recipe+runner version. Must release runtime after capture, preserve artifacts and failed logs. No AI required. No browser installed -> actionable error/manual fallback. Provider path from environment/normal dependency resolution, not machine hardcode.
- `.list(project_id, sha=None)` -> evidence records.
`base` null => single-side capture; explicit SHA => paired compare. Independent screenshots + optional video, readiness fonts/images/app selector, report missing assets rather than claim successful capture.

## HTTP API used by web frontend
All endpoints prefix /api; JSON. GET /bootstrap -> {token,projects,runtimes,jobs,ai:{...}}. Mutations `X-Reprise-Token` same-origin, JSON. Errors {error}.
GET /projects -> {projects}; POST /projects {path,name?} -> project.
Project: {id,name,path,repository:info,head,detected:detectResult,recipe,recipe_source,recipe_approved,created_at}.
GET /projects/:id -> project; GET /projects/:id/history?ref=...&offset=0&limit=50 -> history.
GET /projects/:id/refs -> {refs}; GET /projects/:id/status -> repository status.
GET /projects/:id/versions/:sha -> {commit,diff,detection,recipe,recipe_source,recipe_approved,evidence:[]}.
GET /projects/:id/diff?target=sha&base=sha -> diff.
PUT /projects/:id/recipe {recipe} -> project (explicit user configuration).
POST /projects/:id/run {sha} -> job; POST /projects/:id/capture {sha,base?:sha} -> job.
POST /runtimes/:id/stop {} -> runtime; GET /jobs/:id -> {id,status:'queued'|'running'|'complete'|'failed',result?,error?}.
GET /projects/:id/evidence?sha=... -> {evidence}.
POST /projects/:id/evidence/manual {sha,path,kind:'image'|'video'|'file',title,base?,capture_id?} -> evidence (copy local artifact into owned storage, do not move original; bind exact revision, mark manual/unverified).
Evidence file URL in returned `items[].url`, open native media dialog with fit/100%/200% and controls.
GET /ai -> public settings/state. PUT /ai {enabled,provider:'compatible',endpoint,model,api_key?} -> state; settings private 0600, no secret returned. POST /projects/:id/ai/suggest {sha} -> job with structured recipe proposal, never apply/run automatically.
GET /health -> {ok:true,version}.
