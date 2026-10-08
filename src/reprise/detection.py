"""Deterministic capability detection from committed files, never executable probes."""
from __future__ import annotations

import json
import posixpath
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


IGNORED_PARTS = {'node_modules', '.git', '.venv', 'venv', 'vendor', 'Pods'}
WEB_FRAMEWORKS = {'next', 'nuxt', 'vite', 'react', 'vue', 'svelte', '@angular/core',
                  'astro', 'gatsby', '@sveltejs/kit', 'webpack', 'parcel'}
GAME_LIBRARIES = {'phaser', 'kaboom', 'excalibur', 'melonjs', 'cocos'}
RENDER_LIBRARIES = {'pixi.js', 'three', 'babylonjs', '@babylonjs/core', 'playcanvas'}


def _parent(path):
    return posixpath.dirname(path) or '.'


def _join(root, path):
    return path if root == '.' else root + '/' + path


def _static_recipe(root):
    return {'schema': 1, 'adapter': 'static-web', 'root': root, 'commands': {},
            'readiness': {'path': '/', 'timeout_ms': 15000},
            'captures': [{'id': 'main', 'route': '/',
                          'viewport': {'width': 1440, 'height': 900, 'scale': 2},
                          'full_page': True, 'steps': []}], 'network': 'local'}


class _HTMLAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
        self.canvas = False
        self.base = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.canvas |= tag == 'canvas'
        if tag == 'base':
            self.base = attrs.get('href')
        if tag in ('script', 'img', 'video', 'audio', 'source', 'iframe') and attrs.get('src'):
            self.paths.append(attrs['src'])
        if tag == 'link' and attrs.get('href') and any(x in attrs.get('rel', '').split() for x in ('stylesheet', 'modulepreload', 'preload')):
            self.paths.append(attrs['href'])
        if attrs.get('poster'):
            self.paths.append(attrs['poster'])


def detect(repository, revision='HEAD'):
    info = repository.info()
    if info['head'] is None and revision == 'HEAD':
        return {'kind': 'empty', 'label': 'Empty Git repository', 'confidence': 1,
                'signals': [], 'capabilities': {'history': True, 'diff': True, 'run': False, 'capture': False, 'manual': True},
                'recipe': None, 'warnings': ['Create a commit before selecting a historical version.'], 'candidates': []}
    sha = repository.resolve(revision)
    tree = repository.tree(sha)
    entries = {item['path']: item for item in tree}
    files = {path for path, item in entries.items() if item['type'] == 'blob'
             and not any(part in IGNORED_PARTS for part in path.split('/'))}
    warnings = list(info.get('warnings', []))
    candidates = []
    packages = {}
    def text(path, limit=1048576):
        try:
            return repository.blob(sha, path, max_bytes=limit).decode('utf-8', 'replace')
        except ValueError as exc:
            warnings.append('Could not inspect %s: %s' % (path, exc))
            return ''
    def candidate(root, kind, label, signal, confidence=.9, recipe=None):
        record = {'root': root, 'kind': kind, 'label': label, 'confidence': confidence,
                  'signals': [signal], 'recipe': recipe, 'requires_configuration': recipe is None}
        candidates.append(record)
        return record
    for path in sorted(files):
        name = posixpath.basename(path)
        root = _parent(path)
        if name == 'package.json':
            try:
                data = json.loads(text(path))
                if not isinstance(data, dict):
                    raise ValueError('manifest must be an object')
            except (ValueError, TypeError):
                warnings.append('Invalid package.json at %s; no commands inferred.' % path)
                continue
            dependencies = set()
            for key in ('dependencies', 'devDependencies', 'peerDependencies'):
                if isinstance(data.get(key), dict):
                    dependencies.update(data[key])
            scripts = data.get('scripts') if isinstance(data.get('scripts'), dict) else {}
            packages[root] = {'dependencies': dependencies, 'scripts': scripts}
            game = sorted(dependencies & GAME_LIBRARIES)
            frameworks = sorted(dependencies & WEB_FRAMEWORKS)
            if 'electron' in dependencies or '@tauri-apps/api' in dependencies:
                c = candidate(root, 'native-app', 'Desktop app (Electron / Tauri)', path)
            elif game:
                c = candidate(root, 'web-game', 'Browser game framework', path + ': ' + ', '.join(game))
            elif dependencies & RENDER_LIBRARIES:
                c = candidate(root, 'web-app', '3D / Canvas web project', path + ': ' + ', '.join(sorted(dependencies & RENDER_LIBRARIES)))
            elif frameworks:
                c = candidate(root, 'web-app', 'Web app (' + ', '.join(frameworks[:3]) + ')', path)
            elif data.get('bin'):
                c = candidate(root, 'cli', 'Node.js command-line app', path)
            elif any(key in scripts for key in ('dev', 'start', 'serve', 'build')):
                c = candidate(root, 'unknown', 'Node.js project with runnable scripts', path, .7)
            else:
                c = candidate(root, 'library', 'JavaScript / TypeScript package', path, .8)
            c['available_scripts'] = sorted(scripts)
            c['package_name'] = data.get('name') if isinstance(data.get('name'), str) else None
        elif name == 'project.godot':
            candidate(root, 'native-game', 'Godot game', path, 1)
        elif name.endswith('.uproject'):
            candidate(root, 'native-game', 'Unreal Engine game', path, 1)
        elif path.endswith('ProjectSettings/ProjectVersion.txt'):
            unity_root = path[:-len('/ProjectSettings/ProjectVersion.txt')] if '/ProjectSettings/' in path else '.'
            candidate(unity_root, 'native-game', 'Unity game', path, 1)
        elif name == 'Cargo.toml':
            content = text(path)
            game = bool(re.search(r'(?m)^\s*(bevy|ggez|macroquad|fyrox)\s*=', content))
            candidate(root, 'native-game' if game else 'native-app', 'Rust game' if game else 'Rust project', path)
        elif name == 'go.mod':
            candidate(root, 'cli', 'Go project', path, .8)
        elif name in ('pyproject.toml', 'setup.py', 'Pipfile', 'requirements.txt'):
            content = text(path)
            is_web = bool(re.search(r'(?i)\b(django|flask|fastapi|streamlit|gradio)\b', content))
            c = candidate(root, 'web-app' if is_web else 'cli', 'Python web app' if is_web else 'Python project', path, .8)
        elif name in ('pom.xml', 'build.gradle', 'build.gradle.kts'):
            candidate(root, 'native-app', 'JVM project', path, .8)
        elif name == 'Package.swift' or name.endswith(('.csproj', '.sln')) or '.xcodeproj/' in path:
            candidate(root, 'native-app', 'Native application / library', path, .8)
        elif name == 'composer.json':
            candidate(root, 'web-app', 'PHP project', path, .8)
        elif name == 'Gemfile':
            candidate(root, 'web-app', 'Ruby project', path, .7)
        elif name in ('CMakeLists.txt', 'Makefile'):
            candidate(root, 'native-app', 'Native build project', path, .6)
    html_assets = {}
    # Only existing committed HTML that does not need a source-code transform
    # qualifies for zero-configuration serving. Never guess npm/build commands.
    for path in sorted(files):
        if posixpath.basename(path).lower() != 'index.html':
            continue
        root = _parent(path)
        content = text(path)
        if not content:
            continue
        parser = _HTMLAssets()
        try:
            parser.feed(content)
        except Exception:
            warnings.append('Could not inspect HTML assets at ' + path)
            continue
        package = packages.get(root, {})
        deps = package.get('dependencies', set())
        scripts = package.get('scripts', {})
        needs_build = bool(deps & WEB_FRAMEWORKS or any(re.search(r'\b(vite|webpack|parcel|next|nuxt|astro)\b', str(v)) for v in scripts.values()))
        unresolved = []
        external = False
        for asset in parser.paths:
            try:
                parsed = urlsplit(asset)
            except ValueError:
                unresolved.append(asset)
                continue
            if parsed.scheme or parsed.netloc or asset.startswith('//'):
                external = external or parsed.scheme in ('http', 'https') or bool(parsed.netloc)
                continue
            ref = unquote(parsed.path)
            if not ref:
                continue
            if ref.endswith(('.ts', '.tsx', '.jsx', '.vue', '.svelte')) or '%PUBLIC_URL%' in ref or '{{' in ref or '<%' in ref:
                needs_build = True
            local = _join(root, ref.lstrip('/')) if ref.startswith('/') else posixpath.normpath(_join(root, ref))
            if local not in files:
                unresolved.append(asset)
        if parser.base and parser.base not in ('/', './', '.'):
            # Base URL semantics require an explicit route/root choice.
            needs_build = True
        if needs_build:
            if not any(c['root'] == root for c in candidates):
                candidate(root, 'web-app', 'Web source (build configuration needed)', path, .85)
            warnings.append('%s appears to require a build or serving configuration.' % path)
            continue
        if external:
            warnings.append('%s references remote assets; local-only capture may need a configured network policy.' % path)
        game = bool(deps & GAME_LIBRARIES)
        c = candidate(root, 'web-game' if game else 'static-web', 'Browser game framework' if game else 'Static website', path,
                      .9 if unresolved else .98, _static_recipe(root))
        c['missing_assets'] = unresolved[:20]
        html_assets[root] = (path, parser.paths)
        if parser.canvas:
            c['signals'].append('Canvas rendering found; project purpose is not inferred from this element.')
    if any(item['type'] == 'commit' for item in tree):
        warnings.append('Submodule commits are visible; their contents are not fetched or initialized automatically.')
    if '.gitattributes' in files and 'filter=lfs' in text('.gitattributes'):
        warnings.append('Git LFS is configured; historical snapshots preserve pointer files unless real assets are already committed.')
    # Consolidate duplicate ecosystem markers at a root without throwing away
    # distinct deployable subprojects (monorepos can expose multiple candidates).
    unique = {}
    for item in candidates:
        key = (item['root'], item['kind'], bool(item['recipe']))
        if key in unique:
            unique[key]['signals'].extend(x for x in item['signals'] if x not in unique[key]['signals'])
            unique[key]['confidence'] = max(unique[key]['confidence'], item['confidence'])
        else:
            unique[key] = item
    candidates = list(unique.values())
    candidates.sort(key=lambda c: (0 if c['root'] == '.' else 1, c['root'].count('/'), 0 if c['recipe'] else 1, c['root'], c['kind']))
    static_candidates = [c for c in candidates if c['recipe']]
    manifest_roots = {c['root'] for c in candidates if not c['recipe']}
    automatic = []
    for c in static_candidates:
        ancestors = [other for other in static_candidates if other is not c and
                     (other['root'] == '.' or c['root'].startswith(other['root'] + '/'))]
        if ancestors and c['root'] not in manifest_roots:
            c['nested_page'] = True
            continue
        automatic.append(c)
    # Multiple runnable roots are a real user choice. Do not silently open one
    # package of a monorepo or a documentation example as the whole project.
    # HTML directory and HTTP serving root differ for nested routes. Absolute
    # URLs belong to the enclosing deployed site; relative URLs remain page-local.
    for c in static_candidates:
        page_root = c['root']
        serving_root = page_root
        if c.get('nested_page'):
            enclosing = [a for a in automatic if a['root'] == '.' or page_root.startswith(a['root'] + '/')]
            if enclosing:
                serving_root = max(enclosing, key=lambda a: len(a['root']))['root']
        html_path, asset_paths = html_assets[page_root]
        missing = []
        for asset in asset_paths:
            try:
                parsed = urlsplit(asset)
            except ValueError:
                missing.append(asset)
                continue
            if parsed.scheme or parsed.netloc or asset.startswith('//'):
                continue
            ref = unquote(parsed.path)
            if not ref:
                continue
            local = _join(serving_root, ref.lstrip('/')) if ref.startswith('/') else _join(page_root, ref)
            local = posixpath.normpath(local)
            if local not in files and _join(local, 'index.html') not in files:
                missing.append(asset)
        c['missing_assets'] = missing[:20]
        c['serving_root'] = serving_root
        c['confidence'] = .9 if missing else .98
        if missing:
            warnings.append('%s references missing committed assets: %s' % (html_path, ', '.join(missing[:5])))
    chosen = automatic[0] if len(automatic) == 1 else next((c for c in candidates if c['root'] == '.'), candidates[0] if candidates else None)
    recipe = automatic[0]['recipe'] if len(automatic) == 1 else None
    if len(automatic) > 1:
        warnings.append('Multiple runnable roots found; select and save a recipe for the intended app.')
    if chosen:
        kind, label, confidence, signals = chosen['kind'], chosen['label'], chosen['confidence'], chosen['signals']
    elif any(posixpath.basename(p).lower().startswith('readme') for p in files):
        kind, label, confidence, signals = 'documentation', 'Documentation / unrecognized project', .5, ['README present']
    else:
        kind, label, confidence, signals = 'unknown', 'Unrecognized project type', 0, []
    if not recipe:
        warnings.append('Git history and file diffs are available. Configure a runner or attach manual evidence for visual previews.')
    return {'kind': kind, 'label': label, 'confidence': confidence, 'signals': signals,
            'capabilities': {'history': True, 'diff': True, 'run': bool(recipe), 'capture': bool(recipe), 'manual': True},
            'recipe': recipe, 'warnings': list(dict.fromkeys(warnings)), 'candidates': candidates, 'sha': sha}
