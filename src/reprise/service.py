"""Application orchestration; the web API and CLI share this same service."""
from pathlib import Path
import threading

from .capture import CaptureService
from .evidence import EvidenceStore
from .jobs import Jobs
from .recipes import recipe_hash
from .version_actions import version_actions
from .projects import ProjectStore
from .runtime import RuntimeManager, STARTING
from .recovery import RecoveryStore
from .organize import OrganizationStore


class Reprise:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.request_gate = threading.RLock()
        from .maintenance import DataLease
        self._data_lease = DataLease(self.directory)
        self._data_lease.__enter__()
        try:
            self.directory.chmod(0o700)
            self.projects = ProjectStore(self.directory)
            self.runtimes = RuntimeManager(self.directory)
            self.captures = CaptureService(self.directory, self.runtimes)
            self.evidence = EvidenceStore(self.directory, self.captures)
            self._ai = None
            self._ai_lock = threading.Lock()
            self.jobs = Jobs(self.directory)
            self.recovery = RecoveryStore(self.directory, self.projects)
            self.organization = OrganizationStore(self.directory, self.projects, self.recovery, self.runtimes)
            from .version_deletion import VersionDeletion
            self.version_deletions = VersionDeletion(self.directory, self.projects)
            from .folder_imports import FolderImports
            self.folder_imports = FolderImports(self)
        except BaseException:
            self._data_lease.__exit__(None, None, None)
            raise

    @property
    def ai(self):
        """Legacy explicit API only; ordinary draft work never loads AI settings."""
        with self._ai_lock:
            if self._ai is None:
                from .ai import AIService
                self._ai = AIService(self.directory)
            return self._ai

    def privacy(self):
        from .privacy import describe
        return describe(self.directory, self.projects, self.ai)

    def inspect_storage(self):
        from .storage_report import storage_report
        return self.jobs.submit('local-storage', 'storage',
            lambda cancel: storage_report(self.directory, cancel),
            cancellable=True)

    def transfer_info(self):
        import sys
        return {'data_directory': str(self.directory), 'backup_requires_offline': True,
                'backup_scope': 'Reprise managed data; external source repositories and legacy archives are not copied.',
                'backup_command_prefix': [sys.executable, '-I', '-S', '-B', str(Path(__file__).with_name('server_entry.py')),
                                          '--data', str(self.directory), 'backup'],
                'projects': self.projects.summaries()}

    def relocation_protections(self):
        roots = set()
        for runtime in self.runtimes.list():
            if runtime.get('running') or runtime.get('status') in STARTING + ('cleanup_failed',):
                roots.update(str(Path(runtime[k]).resolve()) for k in ('source', 'snapshot', 'directory', 'workspace')
                             if isinstance(runtime.get(k), str))
        return sorted(roots)

    def data_transfer(self, operation, body):
        from .backup import verify_backup, restore_backup
        source, destination = body.get('backup'), body.get('to')
        if not isinstance(source, str) or not source.strip():
            raise ValueError('请填写已完成备份的目录。')
        source = str(Path(source).expanduser().absolute())
        if operation == 'backup-check':
            callback = lambda cancel: verify_backup(source, cancel)
        elif operation == 'data-restore':
            if not isinstance(destination, str) or not destination.strip():
                raise ValueError('请选择新的数据目录。')
            target = Path(destination).expanduser().resolve()
            if target == self.directory or target in self.directory.parents or self.directory in target.parents:
                raise ValueError('新的数据目录与当前数据目录必须互不包含。')
            destination = str(self.recovery.destination(str(target)))
            callback = lambda cancel: restore_backup(source, destination, cancel)
        else:
            raise ValueError('不支持的数据目录操作。')
        return self.jobs.submit('local-transfer', operation, callback,
            request={'backup': source, 'to': destination}, cancellable=True)

    def version(self, identifier, revision):
        repository = self.projects.repository(identifier)
        project = self.projects.get(identifier, revision, repository=repository)
        sha = project['revision']
        commit = repository.history(sha, limit=1)['commits'][0]
        try:
            difference = repository.diff(sha)
        except ValueError as error:
            difference = {'available': False, 'error': str(error), 'target': sha, 'base': commit['parents'][0] if commit['parents'] else None, 'parents': commit['parents'], 'files': [], 'counts': {}}
        content = None
        if project.get('kind') == 'folder':
            manifest = repository.manifest(sha)
            content = {'stats': manifest['stats'], 'excluded': manifest['excluded'],
                       'source': manifest['source'], 'created_at': manifest['created_at'], 'origin': manifest.get('origin')}
        evidence = self.evidence.list(identifier, sha)
        return {
            'commit': commit, 'diff': difference, 'detection': project['detected'],
            'recipe': project['recipe'], 'recipe_source': project['recipe_source'],
            'recipe_hash': recipe_hash(project['recipe']) if project['recipe'] and project['recipe_approved'] else None,
            'recipe_approved': project['recipe_approved'], 'recipe_error': project.get('recipe_error'),
            'legacy_recipe': project.get('legacy_recipe'),
            'notes': project.get('version_notes', {}).get(sha), 'evidence': evidence,
            'content': content, 'actions': version_actions(project, evidence),
        }

    def version_delete_plan(self, identifier, shas):
        return self.version_deletions.plan(identifier, shas)

    def delete_versions(self, identifier, plan_id, confirm=False):
        return self.version_deletions.execute(identifier, plan_id, confirm)

    def execute(self, identifier, operation, body):
        if operation == 'version-estimate':
            self.projects.record(identifier)
            plan_id = body.get('plan_id')
            return self.jobs.submit(identifier, operation,
                lambda cancel: self.version_deletions.estimate(identifier, plan_id, cancel),
                request={'plan_id': plan_id}, cancellable=True)
        if operation == 'version-delete':
            self.projects.record(identifier)
            plan_id, confirm = body.get('plan_id'), body.get('confirm')
            return self.jobs.submit(identifier, operation,
                lambda: self.delete_versions(identifier, plan_id, confirm),
                request={'plan_id': plan_id, 'confirm': confirm})
        if operation in ('relink-check', 'relink', 'migrate'):
            from .relocation import inspect_relink, relink, migrate
            self.projects.record(identifier)
            target = body.get('to')
            if not isinstance(target, str) or not target.strip():
                raise ValueError('请填写新的项目目录。')
            target = str(Path(target).expanduser().absolute())
            protected = set(self.relocation_protections())
            action = {'relink-check': inspect_relink, 'relink': relink, 'migrate': migrate}[operation]
            return self.jobs.submit(identifier, operation,
                lambda cancel: action(self.projects, identifier, target, cancel,
                    protected_roots=sorted(protected | set(self.relocation_protections()))),
                request={'to': target}, cancellable=True)
        if operation == 'verify':
            from .folders import FolderRepository
            from .integrity import verify_project
            record = self.projects.record(identifier)
            if record.get('kind') != 'folder':
                raise ValueError('库完整性检查用于已保存的普通文件夹版本；Git 与旧归档请使用其恢复校验。')
            # Pin the requested revision before queuing, without creating a store
            # when an existing library is missing or damaged.
            sha = FolderRepository(self.projects.folders, record).resolve(body.get('sha', 'HEAD'))
            return self.jobs.submit(identifier, operation,
                lambda cancel: verify_project(self.projects, identifier, sha, cancel),
                request={'sha': sha}, cancellable=True)
        if operation == 'snapshot':
            record = self.projects.record(identifier)
            if record.get('kind') != 'folder':
                raise ValueError('只有普通文件夹使用记录版本；Git 项目保留原有提交流程。')
            title = body.get('title', '')
            preferences = body.get('preview_preferences')
            if preferences is not None:
                if not isinstance(preferences, dict):
                    raise ValueError('截图偏好格式无效。')
                self.projects.save_preview_preferences(identifier, preferences.get('mode'), preferences.get('recipe_sha'),
                                                      pending_recipe=preferences.get('pending_recipe', False))
            # Freeze the explicit template before queuing. Saving itself never
            # infers command approval from a newly imported or AI-produced recipe.
            preference = self.projects.record(identifier).get('preview_preferences', {'mode': 'remind'})
            capture_static = body.get('capture_static', False)
            if not isinstance(capture_static, bool):
                raise ValueError('capture_static must be a boolean.')
            if capture_static:
                preference = {'mode': 'quick'}
            return self.jobs.submit(identifier, operation,
                lambda cancel: self.save_with_preview(identifier, title, preference, cancel),
                request={'title': title}, cancellable=True)
        if operation == 'organize-check':
            from .folders import FolderRepository
            record = self.projects.record(identifier)
            if record.get('kind') != 'folder':
                raise ValueError('整理预检用于已保存的普通文件夹版本。')
            repository = FolderRepository(self.projects.folders, record)
            sha = repository.resolve(body.get('sha', 'HEAD'))
            # No project detection or recipe resolution: a preflight needs only
            # the saved manifest, even when source files are offline.
            return self.jobs.submit(identifier, operation,
                lambda cancel: self.organization.preview(identifier, sha, cancel),
                request={'sha': sha}, cancellable=True)
        # Resolve refs and recipe before queuing so new commits/config edits cannot
        # silently change what the user just requested.
        repository = self.projects.repository(identifier)
        project = self.projects.get(identifier, body.get('sha', 'HEAD'), repository=repository)
        sha, recipe, approved = project['revision'], project['recipe'], project['recipe_approved']
        base = None
        if not sha:
            raise ValueError('项目还没有提交。')
        if operation == 'organize':
            if project.get('kind') != 'folder':
                raise ValueError('请在普通文件夹的已保存版本中整理副本。')
            return self.jobs.submit(identifier, operation,
                lambda cancel: self.organization.create(identifier, sha, cancel),
                request={'sha': sha}, cancellable=True)
        if operation in ('restore', 'export'):
            paths = body.get('paths')
            if paths is not None:
                from .git import _safe_path
                if not isinstance(paths, list) or not 1 <= len(paths) <= 200:
                    raise ValueError('请选择 1–200 个文件或目录。')
                paths = list(dict.fromkeys(_safe_path(p) for p in paths))
            destination = str(self.recovery.destination(body['to'])) if body.get('to') else None
            if operation == 'restore' and not destination:
                raise ValueError('请选择新的恢复目录。')
            return self.jobs.submit(identifier, operation,
                lambda cancel: self.recovery.create(repository, identifier, sha, operation, destination, cancel, paths=paths),
                request={'sha': sha, 'to': destination, 'paths': paths}, cancellable=True)
        if operation in ('run', 'capture') and (not recipe or recipe['adapter'] == 'manual'):
            raise ValueError(project.get('recipe_error') or '这个项目需要运行配方；也可以先添加人工截图或录屏。')
        if operation in ('run', 'capture') and recipe['adapter'] == 'command-web' and not approved:
            raise ValueError('这个配方将执行项目命令，请先打开配方编辑器、核对并保存。')
        if operation in ('run', 'capture') and 'recipe_hash' in body and body['recipe_hash'] != recipe_hash(recipe):
            raise ValueError('运行配置已经变化，请刷新此版本并重新核对。')
        if operation == 'run':
            callback = lambda cancel: self.runtimes.start(repository, sha, recipe, approved=approved, cancel=cancel, project_id=identifier)
        elif operation == 'capture':
            base = repository.resolve(body['base']) if body.get('base') else None
            baseline = self.projects.get(identifier, base) if base else None
            if baseline and (not baseline['recipe'] or baseline['recipe']['adapter'] == 'manual' or (baseline['recipe']['adapter'] == 'command-web' and not baseline['recipe_approved'])):
                raise ValueError('请先选择比较基准版本 %s，为它保存并确认运行配置，然后返回当前比较。' % base[:8])
            callback = lambda cancel: self.evidence.public(self.captures.capture(repository, identifier, sha, recipe, base=base, approved=approved, base_recipe=baseline['recipe'] if baseline else None, base_approved=baseline['recipe_approved'] if baseline else False, cancel=cancel))
        elif operation == 'ai/suggest':
            diff = repository.diff(sha)
            tree = repository.tree(sha)
            paths = [item['path'] for item in tree[:294]]  # reserve six committed manifest paths
            # Fixed allowlist, bounded committed manifests; never .env, credentials,
            # uncommitted files or project instructions read from the worktree.
            manifest_names = {'package.json', 'pyproject.toml', 'Cargo.toml', 'project.godot', 'CMakeLists.txt', 'go.mod'}
            manifests = {}
            for item in tree:
                if Path(item['path']).name in manifest_names and len(manifests) < 6:
                    try:
                        manifests[item['path']] = repository.blob(sha, item['path'], max_bytes=16384).decode('utf-8')
                        if item['path'] not in paths:
                            paths.append(item['path'])
                    except (ValueError, UnicodeError):
                        continue
            commit = repository.history(sha, limit=1)['commits'][0]
            commit_brief = {'subject': commit['subject'][:2000], 'parents': commit['parents'][:8]}
            context = {'project_id': identifier, 'sha': sha, 'base': diff['base'], 'paths': paths, 'manifests': manifests, 'changed_files': diff['files'][:100], 'detection': project['detected'], 'commit': commit_brief}
            callback = lambda: self.ai.suggest(context)
        else:
            raise ValueError('不支持的任务操作。')
        request = {key: value for key, value in {'sha': sha, 'base': base}.items() if value is not None}
        if operation in ('run', 'capture') and 'recipe_hash' in body:
            request['recipe_hash'] = recipe_hash(recipe)
        return self.jobs.submit(identifier, operation, callback, request=request, cancellable=operation in ('run', 'capture'))

    def save_with_preview(self, identifier, title, preference, cancel):
        from .experience import save_draft
        return save_draft(self, identifier, title, preference, cancel)

    def runtime_list(self):
        projects = {record['path']: record['id'] for record in self.projects.records()}
        return [dict(runtime, project_id=projects.get(runtime.get('source'))) for runtime in self.runtimes.list()]

    def close(self):
        try:
            self.jobs.close(cancel=True)
        finally:
            if self._data_lease is not None:
                self._data_lease.__exit__(None, None, None)
                self._data_lease = None
