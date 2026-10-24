"""Read-only preparation for saving one local webpage revision's appearance.

This module never saves approval, starts a server, or creates evidence. A caller
must receive an explicit user action, save the returned recipe for ``sha``, then
use the ordinary capture service. ``ready`` means no known static-entry blocker,
not a successful capture or a guarantee about JavaScript and external services.
"""
from html.parser import HTMLParser
import posixpath
import re
from urllib.parse import quote, urlsplit

from .detection import detect
from .recipes import validate_recipe


_FULL_SHA = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')


class _RemoteAssets(HTMLParser):
    """Keep a quick capture local; remote assets need an explicit network choice."""

    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        values = []
        if tag in ('script', 'img', 'video', 'audio', 'source', 'iframe'):
            values.append(attrs.get('src', ''))
        if tag == 'link' and any(rel in attrs.get('rel', '').split()
                                 for rel in ('stylesheet', 'preload', 'modulepreload')):
            values.append(attrs.get('href', ''))
        values.append(attrs.get('poster', ''))
        for value in values:
            try:
                parsed = urlsplit(value)
            except ValueError:
                continue  # The detector separately records malformed local paths.
            if parsed.scheme in ('http', 'https') or parsed.netloc:
                self.paths.append(value)


def prepare_quick_preview(repository, sha, *, root=None):
    """Return a static-only proposal bound to an exact SHA-1 or SHA-256 revision.

    ``status`` is ``ready``, ``choose-entry`` or ``needs-configuration``. Only a
    ready result has ``recipe``. ``candidates`` lists the independently detected
    site roots, their entry files and known blockers. The optional ``root`` must
    be one of those roots: it represents a user's explicit choice, not a path to
    execute. Nested pages of one detected site do not become separate projects.

    Every response requires an explicit save before execution. No existing or
    imported recipe, approval, screenshot or mutable working file is reused.
    """
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha):
        raise ValueError('Quick preview requires a complete, exact version SHA.')
    if repository.resolve(sha) != sha:
        raise ValueError('The requested preview version does not match its SHA.')
    if root is not None and not isinstance(root, str):
        raise ValueError('Choose a detected webpage entry.')

    detected = detect(repository, sha)
    tree = {entry['path']: entry for entry in repository.tree(sha)}
    candidates = []
    proposals = {}
    for candidate in detected.get('candidates', []):
        recipe = candidate.get('recipe')
        if not recipe or recipe.get('adapter') != 'static-web' or candidate.get('nested_page'):
            continue
        site_root = candidate['root']
        entries = sorted(path for path, item in tree.items()
                         if item['type'] == 'blob'
                         and (posixpath.dirname(path) or '.') == site_root
                         and posixpath.basename(path).lower() == 'index.html')
        issues = []
        # A case-sensitive filesystem can contain both index.html and INDEX.HTML.
        # The detector groups these by root; do not silently choose one of them.
        if len(entries) != 1:
            issues.append('ambiguous-entry')
        entry = entries[0] if len(entries) == 1 else None
        missing = list(candidate.get('missing_assets', []))
        if missing:
            issues.append('missing-assets')
        remote_assets = []
        if entry:
            if tree[entry].get('mode') == '120000':
                issues.append('entry-is-symlink')
            else:
                try:
                    content = repository.blob(sha, entry, max_bytes=1048576).decode('utf-8')
                    if content.startswith('version https://git-lfs.github.com/spec/v1'):
                        issues.append('entry-is-lfs-pointer')
                    assets = _RemoteAssets()
                    assets.feed(content)
                    remote_assets = list(dict.fromkeys(assets.paths))
                    if remote_assets:
                        issues.append('remote-assets')
                except (ValueError, UnicodeError):
                    issues.append('entry-unreadable')
        if not issues:
            # Build a new bounded recipe instead of inheriting a repository or
            # another revision's execution settings. No install/build commands.
            route = '/' if posixpath.basename(entry) == 'index.html' else '/' + quote(posixpath.basename(entry))
            try:
                proposals[site_root] = validate_recipe({
                    'schema': 1, 'adapter': 'static-web', 'root': site_root,
                    'commands': {}, 'network': 'local',
                    'readiness': {'path': route, 'timeout_ms': 15000},
                    'captures': [{'id': 'main', 'route': route,
                                  'viewport': {'width': 1440, 'height': 900, 'scale': 2},
                                  'full_page': True, 'steps': []}],
                })
            except ValueError:
                issues.append('entry-path-needs-configuration')
        candidates.append({'root': site_root, 'entry': entry,
                           'available': not issues, 'issues': issues,
                           'missing_assets': missing, 'remote_assets': remote_assets})

    result = {'sha': sha, 'status': 'needs-configuration', 'reason': 'no-static-entry',
              'root': None, 'entry': None, 'recipe': None, 'candidates': candidates,
              'warnings': list(detected.get('warnings', [])), 'requires_save': True}
    if root is not None and not any(item['root'] == root for item in candidates):
        raise ValueError('The selected webpage entry is not present in this version.')
    if not candidates:
        return result
    if root is None and len(candidates) > 1:
        return {**result, 'status': 'choose-entry', 'reason': 'multiple-static-entries'}
    selected = next(item for item in candidates if item['root'] == root) if root is not None else candidates[0]
    result.update(root=selected['root'], entry=selected['entry'])
    if not selected['available']:
        result['reason'] = selected['issues'][0]
        return result
    result.update(status='ready', reason=None, recipe=proposals[selected['root']])
    return result
