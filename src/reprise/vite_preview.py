"""Read-only preparation of a narrow npm/Vite preview, never execution approval.

Only a standalone package with a committed npm v2/v3 lock and an ordinary Vite
dev script gets a proposal. Arbitrary scripts and other package managers retain
the existing explicit recipe path. The caller must save the exact-SHA recipe
after the user approves its commands before requesting the ordinary capture.
"""
import json
import posixpath
import re

from .detection import IGNORED_PARTS
from .recipes import validate_recipe


_FULL_SHA = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')
_DEV_SCRIPT = re.compile(r'^vite(?:[ \t]+(?:dev|serve))?$')
_DEPENDENCIES = ('dependencies', 'devDependencies', 'optionalDependencies')
_LIFECYCLES = ('preinstall', 'install', 'postinstall', 'prepublish',
               'preprepare', 'prepare', 'postprepare', 'predev', 'dev', 'postdev')


def _join(root, name):
    return name if root == '.' else root + '/' + name


def prepare_vite_preview(repository, sha, *, root=None):
    """Return ``needs-approval`` with a recipe, or a non-executable diagnostic.

    The result is based solely on the specified complete immutable revision.
    ``requires_save`` and ``requires_command_approval`` always remain true.
    ``network`` on the recipe controls the browser only: npm and project code
    are approved local commands, not a network or filesystem sandbox.
    """
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha) or repository.resolve(sha) != sha:
        raise ValueError('Vite preview requires a complete, exact version SHA.')
    if root is not None and not isinstance(root, str):
        raise ValueError('Choose a detected Vite project root.')
    tree = {item['path']: item for item in repository.tree(sha)}
    manifests = sorted(path for path, item in tree.items()
                       if item['type'] == 'blob' and posixpath.basename(path) == 'package.json'
                       and not any(part in IGNORED_PARTS for part in path.split('/')))
    candidates, proposals = [], {}

    def read_json(path):
        if tree[path].get('mode') == '120000':
            raise ValueError('Manifest or lockfile is a symlink')
        value = json.loads(repository.blob(sha, path, max_bytes=8 * 1024 * 1024).decode('utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Manifest or lockfile must be an object')
        return value

    parsed = {}
    for path in manifests:
        try:
            parsed[posixpath.dirname(path) or '.'] = read_json(path)
        except (ValueError, UnicodeError):
            parsed[posixpath.dirname(path) or '.'] = None
    vite_roots = {site for site, data in parsed.items() if data and any(
        isinstance(data.get(key), dict) and 'vite' in data[key] for key in _DEPENDENCIES)}
    result = {'sha': sha, 'status': 'needs-configuration', 'reason': 'no-supported-vite-project',
              'root': None, 'entry': None, 'recipe': None, 'candidates': candidates,
              'warnings': [], 'requires_save': True, 'requires_command_approval': True}
    if not vite_roots:
        return result
    # Include sibling/root packages in the choice, so an example package is
    # never silently chosen as the whole imported project.
    for site, package in parsed.items():
        issues = []
        scripts = package.get('scripts', {}) if package else {}
        scripts = scripts if isinstance(scripts, dict) else {}
        entry, lock_path = _join(site, 'index.html'), _join(site, 'package-lock.json')
        if site not in vite_roots:
            issues.append('unsupported-package')
        if package and (package.get('workspaces') or any(
                parent != site and (parent == '.' or site.startswith(parent + '/'))
                and (data or {}).get('workspaces') for parent, data in parsed.items())):
            issues.append('workspace-needs-configuration')
        manager = package.get('packageManager', '') if package else ''
        if not isinstance(manager, str) or (manager and not manager.startswith('npm@')):
            issues.append('package-manager-needs-configuration')
        if any(_join(site, name) in tree for name in ('pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb', 'npm-shrinkwrap.json')):
            issues.append('package-manager-needs-configuration')
        if not isinstance(scripts.get('dev'), str) or not _DEV_SCRIPT.fullmatch(scripts['dev'].strip()):
            issues.append('dev-script-needs-configuration')
        if entry not in tree or tree[entry]['type'] != 'blob' or tree[entry].get('mode') == '120000':
            issues.append('missing-vite-html-entry')
        if lock_path not in tree:
            issues.append('missing-npm-lockfile')
        else:
            try:
                lock = read_json(lock_path)
                packages = lock.get('packages')
                if lock.get('lockfileVersion') not in (2, 3) or not isinstance(packages, dict):
                    raise ValueError('Use npm lockfile version 2 or 3')
                locked_root = packages.get('')
                if not isinstance(locked_root, dict) or not isinstance(packages.get('node_modules/vite'), dict):
                    raise ValueError('Lockfile does not include the root and Vite dependency')
                if any((package or {}).get(key, {}) != locked_root.get(key, {}) for key in _DEPENDENCIES):
                    raise ValueError('Manifest and lockfile dependencies differ')
                # Local, linked or Git dependencies can require files outside
                # the snapshot or host tooling. Keep this first-run path narrow.
                for name, record in packages.items():
                    if not isinstance(record, dict) or record.get('link'):
                        raise ValueError('Linked or invalid dependency')
                    resolved = record.get('resolved')
                    if name and (not isinstance(resolved, str) or not resolved.startswith('https://')):
                        raise ValueError('Dependency is not a locked HTTPS archive')
            except (ValueError, UnicodeError):
                issues.append('npm-lockfile-needs-configuration')
        if not issues:
            try:
                proposals[site] = validate_recipe({
                    'schema': 1, 'adapter': 'command-web', 'root': site,
                    'commands': {'install': [['npm', 'ci', '--include=dev', '--no-audit', '--no-fund']],
                                 'start': ['npm', 'run', 'dev', '--', '--host', '{host}',
                                           '--port', '{port}', '--strictPort']},
                    'readiness': {'path': '/', 'timeout_ms': 30000},
                    'captures': [{'id': 'main', 'route': '/', 'full_page': True,
                                  'viewport': {'width': 1440, 'height': 900, 'scale': 2}, 'steps': []}],
                    'network': 'local',
                })
            except ValueError:
                issues.append('project-path-needs-configuration')
        candidates.append({'root': site, 'entry': entry if entry in tree else None,
                           'framework': 'vite' if site in vite_roots else None,
                           'available': not issues, 'issues': list(dict.fromkeys(issues)),
                           'scripts': {key: scripts[key] for key in _LIFECYCLES if isinstance(scripts.get(key), str)}})
    if root is not None and root not in parsed:
        raise ValueError('The selected Vite project root is not present in this version.')
    if root is None and len(candidates) > 1:
        return {**result, 'status': 'choose-entry', 'reason': 'multiple-project-packages'}
    selected = next(item for item in candidates if item['root'] == root) if root is not None else candidates[0]
    result.update(root=selected['root'], entry=selected['entry'])
    if selected['issues']:
        result['reason'] = selected['issues'][0]
        return result
    result.update(status='needs-approval', reason='vite-command-approval', recipe=proposals[selected['root']],
                  execution={'working_copy': 'isolated-version-snapshot', 'installs_dependencies': True,
                             'installation_network': True, 'runs_package_scripts': True,
                             'runs_vite_config': True, 'command_sandbox': False,
                             'scripts': selected['scripts']},
                  warnings=['npm ci downloads locked dependencies and may run dependency and project lifecycle scripts.',
                            'npm run dev executes this version’s scripts, Vite configuration and plugins in a separate copy.',
                            'The local browser network setting does not restrict npm or project code.'])
    return result
