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
from .folders import FolderStore
from . import archives
from .maintenance import DataLease


class ProjectStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.file = self.directory / 'projects.json'
        self.lockfile = self.directory / 'projects.lock'
        self.lock = threading.RLock()
        self.cache = {}
        self.folders = FolderStore(self.directory)

    def records(self):
        return archives.overlay(read_json(self.file, {'schema': 1, 'projects': []})['projects'], self.directory)

    def identify(self, value):
        from .archive_names import key
        matches = [p for p in self.records() if value == p['id'] or key(value) in
                   {key(p['name']), *(key(a) for a in p.get('aliases', []))}]
        if not matches:
            raise KeyError('找不到项目，请从 projects 返回的名称或标识中选择。')
        if len(matches) != 1:
            raise ValueError('项目名称不明确，请从 projects 返回的名称或标识中选择。')
        return matches[0]['id']

    def summaries(self, *, include_path=False):
        fields = ('id', 'name', 'kind', 'aliases') + (('path',) if include_path else ())
        return [{k: p[k] for k in fields if k in p}
                for p in self.records()]

    def record(self, identifier):
        for project in self.records():
            if project['id'] == identifier:
                return project
        raise KeyError('找不到这个项目。')

    def repository(self, identifier):
        record = self.record(identifier)
        if record.get('kind') == 'folder':
            return self.folders.repository(record)
        if record.get('kind') == 'archive':
            group = next(g for g in archives.groups(self.directory) if g['id'] == record['archive_group'])
            return archives.ArchiveRepository(group, git_history=record.get('archive_git_history', False))
        return Repository(record['path'], status_directory=self.directory / 'git-status')

    @staticmethod
    def _source(path, kind=None, status_directory=None):
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            raise ValueError('请填写本地文件夹或 Git 仓库路径。')
        if kind not in (None, 'git', 'folder'):
            raise ValueError('项目类型必须为 git 或 folder。')
        source = Path(path).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('文件夹不存在：' + str(source))
        if kind == 'folder' and source.name.casefold() == '.git':
            raise ValueError('请选择项目文件夹，不能把 .git 元数据目录作为普通内容导入。')
        if kind != 'folder':
            try:
                repository = Repository(source, status_directory=status_directory)
                return str(repository.path), 'git', repository
            except ValueError:
                if kind == 'git' or (source / '.git').exists() or (source / '.git').is_symlink():
                    raise
        return str(source), 'folder', None

    @staticmethod
    def source(path, kind=None):
        canonical, kind, _ = ProjectStore._source(path, kind)
        return canonical, kind

    def add(self, path, name=None, kind=None, exclude=None):
        canonical, kind, repository = self._source(path, kind, self.directory / 'git-status')
        source = Path(canonical).resolve()
        if self.directory == source or source in self.directory.parents or self.directory in source.parents:
            raise ValueError('Reprise data must be outside the imported repository')
        identity = ('folder:' if kind == 'folder' else '') + canonical
        identifier = hashlib.sha256(identity.encode('utf-8', 'surrogateescape')).hexdigest()[:20]
        from .folders import exclusions
        rules = exclusions(exclude) if exclude is not None else None
        if rules and kind != 'folder':
            raise ValueError('排除规则用于保存普通文件夹版本；Git 历史按原始提交读取。')
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 120):
            raise ValueError('项目名称须为 1–120 个字符。')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with DataLease(self.directory), self.lock, locked(self.lockfile):
            self.directory.chmod(0o700)
            # Canonical path + kind aliases a stable identity after relocation.
            # A Git worktree can also be explicitly managed as a folder.
            # Never write archive overlay records back into projects.json.
            document = read_json(self.file, {'schema': 1, 'projects': []})
            records = document['projects']
            old = next((p for p in self.records() if Path(p['path']).resolve() == source
                        and p.get('kind', 'git') == kind), None)
            if old is None:
                old = next((p for p in records if p['id'] == identifier and p['path'] == canonical
                            and p.get('kind', 'git') == kind), None)
            if old is not None:
                identifier = old['id']
            elif any(p['id'] == identifier for p in records):
                raise ValueError('此路径原来的项目已重新关联到其他目录；请使用已有项目标识，不能重复使用其身份。')
            if old and rules is not None and rules != old.get('exclusions', []):
                raise ValueError('此文件夹已登记不同的排除范围，请保留已有范围。')
            if old is None:
                old = {'id': identifier, 'kind': kind, 'name': (name or Path(canonical).name).strip(), 'path': canonical, 'created_at': now()}
                if kind == 'folder':
                    old['exclusions'] = rules or []
                else:
                    from .relocation import git_anchor
                    old['git_identity_anchor'] = git_anchor(repository)
                records.append(old)
                write_json(self.file, {'schema': 1, 'projects': records}, private=True)
        return self.get(identifier, repository=repository if old.get('kind', 'git') == kind else None)

    def snapshot(self, identifier, title='', cancel=None):
        with DataLease(self.directory):
            record = self.record(identifier)
            if record.get('kind') != 'folder':
                raise ValueError('Git 项目使用已有提交历史；请在 Git 中明确提交改动。')
            return self.folders.snapshot(record, title, cancel)

    def save_preview_preferences(self, identifier, mode, recipe_sha=None, *, pending_recipe=False):
        """An explicit project choice; automatic capture reuses only saved settings."""
        if mode not in ('none', 'manual', 'remind', 'auto'):
            raise ValueError('截图偏好必须为 none、manual、remind 或 auto。')
        if not isinstance(pending_recipe, bool) or (pending_recipe and (mode != 'auto' or recipe_sha)):
            raise ValueError('待配置的截图选择仅用于 auto，不能同时指定配置版本。')
        with DataLease(self.directory), self.lock, locked(self.lockfile):
            document = read_json(self.file, {'schema': 1, 'projects': []})
            record = next((p for p in document['projects'] if p['id'] == identifier), None)
            if record is None or record.get('kind') != 'folder':
                raise ValueError('保存后的截图偏好用于普通文件夹项目。')
            preference = {'mode': mode, 'saved_at': now()}
            if mode == 'auto':
                if recipe_sha:
                    sha = self.repository(identifier).resolve(recipe_sha)
                    saved = record.get('version_recipes', {}).get(sha, {}).get('recipe')
                    if not saved or saved.get('adapter') == 'manual':
                        raise ValueError('请先核对并保存一个版本的运行与截图配置。')
                    preference.update(recipe=validate_recipe(saved), source_sha=sha)
                else:
                    previous = record.get('preview_preferences', {})
                    if previous.get('mode') == 'auto' and previous.get('recipe'):
                        preference.update(recipe=validate_recipe(previous['recipe']), source_sha=previous['source_sha'])
                    elif pending_recipe or (previous.get('mode') == 'auto' and previous.get('pending_recipe')):
                        # Persist the first answer even before an entry or
                        # approved command recipe is available. This is intent,
                        # never approval to execute detected project scripts.
                        preference['pending_recipe'] = True
                    else:
                        raise ValueError('自动截图需要明确选择已确认的配置版本。')
            record['preview_preferences'] = preference
            write_json(self.file, document, private=True)
            return preference

    def detected(self, repository, sha):
        if not sha:
            return {'kind': 'empty', 'label': '空仓库', 'confidence': 'certain', 'signals': [], 'capabilities': {'history': True, 'diff': True, 'run': False, 'capture': False, 'manual': True}, 'recipe': None, 'warnings': ['还没有提交；首次提交后刷新即可读取。'], 'candidates': []}
        key = (str(repository.path), sha)
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

    def get(self, identifier, sha=None, *, repository=None):
        record = self.record(identifier)
        repository = repository or self.repository(identifier)
        info = repository.info()
        resolved = repository.resolve(sha) if sha else info['head']
        archived = record.get('kind') == 'archive'
        detection = ({'kind': 'archive', 'label': '已归档文件', 'confidence': 'certain',
                      'signals': [], 'warnings': ['独立归档快照；原始文件和嵌套 Git 元数据在恢复时还原。'],
                      'capabilities': {'history': True, 'diff': True, 'run': False, 'capture': False, 'manual': True},
                      'recipe': None, 'candidates': []} if archived else self.detected(repository, resolved))
        if record.get('kind') == 'folder' and not resolved:
            detection = {**detection, 'label': '普通文件夹',
                         'warnings': ['点击「记录版本」保存当前文件夹，之后可比较和恢复。']}
        explicit_recipe = record.get('version_recipes', {}).get(resolved, {}).get('recipe')
        recipe = ({'recipe': None, 'recipe_source': 'none', 'recipe_approved': False, 'recipe_error': None}
                  if archived and explicit_recipe is None else self.resolve_recipe(record, repository, resolved, detection))
        return {**record, 'legacy_recipe': record.get('recipe'), 'repository': info, 'head': info['head'], 'revision': resolved, 'detected': detection, **recipe}

    def list(self):
        projects = []
        for record in self.records():
            try:
                projects.append(self.get(record['id']))
            except (ValueError, OSError) as error:
                projects.append({**record, 'unavailable': True, 'error': str(error), 'head': None})
        return projects

    def save_recipe(self, identifier, value, sha='HEAD'):
        with DataLease(self.directory):
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
                preference = record.get('preview_preferences', {})
                if (preference.get('mode') == 'auto' and preference.get('pending_recipe') and
                        normalized and normalized['adapter'] != 'manual'):
                    # The user already chose future capture. Only an explicitly
                    # saved recipe can complete that pending choice. A detection
                    # result or imported recipe never reaches this write path.
                    record['preview_preferences'] = {'mode': 'auto', 'recipe': normalized,
                                                     'source_sha': revision, 'saved_at': now()}
                write_json(self.file, {'schema': 1, 'projects': records}, private=True)
            return self.get(identifier, revision)

    def save_notes(self, identifier, value, sha='HEAD', *, author=None):
        with DataLease(self.directory):
            notes = validate_notes(value)
            if author is not None and (not isinstance(author, str) or len(author) > 120 or
                                       any(ord(c) < 32 for c in author)):
                raise ValueError('显示作者须为 120 字以内的单行文字。')
            revision = self.repository(identifier).resolve(sha)
            with self.lock, locked(self.lockfile):
                records = self.records()
                record = next((p for p in records if p['id'] == identifier), None)
                if record is None:
                    raise KeyError('Unknown project')
                entry = {'localizations': notes, 'saved_at': now()}
                previous = record.get('version_notes', {}).get(revision, {})
                if author is not None:
                    entry['author'] = author.strip()
                elif 'author' in previous:
                    entry['author'] = previous['author']
                record.setdefault('version_notes', {})[revision] = entry
                record.setdefault('notes_history', []).append({'sha': revision, **entry})
                write_json(self.file, {'schema': 1, 'projects': records}, private=True)
            return entry

    def save_histories(self, identifier, histories, catalog=None):
        """Explicitly associate related read-only archives; never invent Git edges."""
        with DataLease(self.directory):
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
                write_json(self.file, {'schema': 1, 'projects': records}, private=True)
            return self.get(identifier)
