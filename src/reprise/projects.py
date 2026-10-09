"""Project registration and revision-specific recipe resolution, without execution."""
import hashlib
import json
from pathlib import Path
import threading

from .git import Repository
from .detection import detect
from .recipes import validate_recipe
from .storage import now, read_json, write_json, locked
from .ai import validate_notes


class ProjectStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.file = self.directory / 'projects.json'
        self.lockfile = self.directory / 'projects.lock'
        self.lock = threading.RLock()
        self.cache = {}

    def records(self):
        return read_json(self.file, {'schema': 1, 'projects': []})['projects']

    def record(self, identifier):
        for project in self.records():
            if project['id'] == identifier:
                return project
        raise KeyError('找不到这个项目。')

    def repository(self, identifier):
        return Repository(self.record(identifier)['path'], status_directory=self.directory / 'git-status')

    def add(self, path, name=None):
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ValueError('请填写本地 Git 仓库路径。')
        repository = Repository(Path(path).expanduser(), status_directory=self.directory / 'git-status')
        info = repository.info()
        canonical = info['path']
        source = Path(canonical).resolve()
        if self.directory == source or source in self.directory.parents:
            raise ValueError('Reprise data must be outside the imported repository')
        identifier = hashlib.sha256(canonical.encode('utf-8', 'surrogateescape')).hexdigest()[:20]
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 120):
            raise ValueError('项目名称须为 1–120 个字符。')
        with self.lock, locked(self.lockfile):
            records = self.records()
            old = next((p for p in records if p['id'] == identifier), None)
            if old is None:
                old = {'id': identifier, 'name': (name or Path(canonical).name).strip(), 'path': canonical, 'created_at': now()}
                records.append(old)
                write_json(self.file, {'schema': 1, 'projects': records})
        return self.get(identifier)

    def detected(self, repository, sha):
        if not sha:
            return {'kind': 'empty', 'label': '空仓库', 'confidence': 'certain', 'signals': [], 'capabilities': {'history': True, 'diff': True, 'run': False, 'capture': False, 'manual': True}, 'recipe': None, 'warnings': ['还没有提交；首次提交后刷新即可读取。'], 'candidates': []}
        key = (repository.info()['path'], sha)
        with self.lock:
            if key not in self.cache:
                if len(self.cache) >= 128:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = detect(repository, sha)
            # Consumers may annotate a response, never mutate the cached detection.
            return json.loads(json.dumps(self.cache[key]))

    def resolve_recipe(self, record, repository, sha, detection=None):
        entry = record.get('version_recipes', {}).get(sha, {})
        if entry.get('recipe') is not None:
            return {'recipe': validate_recipe(entry['recipe']), 'recipe_source': 'version', 'recipe_approved': True, 'recipe_error': None}
        if sha:
            try:
                exists = any(item['path'] == '.reprise.json' and item['type'] == 'blob' for item in repository.tree(sha))
                if exists:
                    recipe = validate_recipe(json.loads(repository.blob(sha, '.reprise.json', max_bytes=262144)))
                    return {'recipe': recipe, 'recipe_source': 'repository', 'recipe_approved': False, 'recipe_error': None}
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                return {'recipe': None, 'recipe_source': 'repository', 'recipe_approved': False, 'recipe_error': '提交中的 .reprise.json 无效：' + str(error)}
        detection = detection or self.detected(repository, sha)
        recipe = detection.get('recipe')
        if recipe is not None:
            recipe = validate_recipe(recipe)
        return {'recipe': recipe, 'recipe_source': 'detected' if recipe else 'none', 'recipe_approved': False, 'recipe_error': None}

    def get(self, identifier, sha=None):
        record = self.record(identifier)
        repository = Repository(record['path'], status_directory=self.directory / 'git-status')
        info = repository.info()
        resolved = repository.resolve(sha) if sha else info['head']
        detection = self.detected(repository, resolved)
        return {**record, 'legacy_recipe': record.get('recipe'), 'repository': info, 'head': info['head'], 'revision': resolved, 'detected': detection, **self.resolve_recipe(record, repository, resolved, detection)}

    def list(self):
        projects = []
        for record in self.records():
            try:
                projects.append(self.get(record['id']))
            except (ValueError, OSError) as error:
                projects.append({**record, 'unavailable': True, 'error': str(error), 'head': None})
        return projects

    def save_recipe(self, identifier, value, sha='HEAD'):
        normalized = validate_recipe(value) if value is not None else None
        revision = self.repository(identifier).resolve(sha)
        with self.lock, locked(self.lockfile):
            records = self.records()
            record = next((p for p in records if p['id'] == identifier), None)
            if record is None:
                raise KeyError('找不到这个项目。')
            entry = {'recipe': normalized, 'saved_at': now()}
            record.setdefault('version_recipes', {})[revision] = entry
            record.setdefault('recipe_history', []).append({'sha': revision, **entry})
            write_json(self.file, {'schema': 1, 'projects': records})
        return self.get(identifier, revision)

    def save_notes(self, identifier, value, sha='HEAD'):
        notes = validate_notes(value)
        revision = self.repository(identifier).resolve(sha)
        with self.lock, locked(self.lockfile):
            records = self.records()
            record = next((p for p in records if p['id'] == identifier), None)
            if record is None:
                raise KeyError('Unknown project')
            entry = {'localizations': notes, 'saved_at': now()}
            record.setdefault('version_notes', {})[revision] = entry
            record.setdefault('notes_history', []).append({'sha': revision, **entry})
            write_json(self.file, {'schema': 1, 'projects': records})
        return entry

    def save_histories(self, identifier, histories, catalog=None):
        """Explicitly associate related read-only archives; never invent Git edges."""
        if (not isinstance(histories, list) or len(histories) > 32 or
                any(not isinstance(item, str) or item == identifier for item in histories)):
            raise ValueError('历史来源必须是其他已注册项目的标识列表。')
        histories = list(dict.fromkeys(histories))
        if catalog is not None:
            if (not isinstance(catalog, list) or len(catalog) > 10000 or
                    any(not isinstance(sha, str) or len(sha) not in (40, 64) or
                        any(c not in '0123456789abcdef' for c in sha) for sha in catalog)):
                raise ValueError('历史目录必须包含完整 SHA。')
            catalog = list(dict.fromkeys(catalog))
        from .workspace import snapshot
        from types import SimpleNamespace
        snapshot(SimpleNamespace(projects=self), identifier, histories,
                 set(catalog) if catalog is not None else None)
        with self.lock, locked(self.lockfile):
            records = self.records()
            record = next((p for p in records if p['id'] == identifier), None)
            if record is None:
                raise KeyError('找不到这个项目。')
            record['history_project_ids'] = histories
            record['history_catalog'] = catalog
            write_json(self.file, {'schema': 1, 'projects': records})
        return self.get(identifier)
