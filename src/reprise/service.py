"""Application orchestration; the web API and CLI share this same service."""
from pathlib import Path

from .ai import AIService
from .capture import CaptureService
from .evidence import EvidenceStore
from .jobs import Jobs
from .projects import ProjectStore
from .runtime import RuntimeManager


class Reprise:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.projects = ProjectStore(self.directory)
        self.runtimes = RuntimeManager(self.directory)
        self.captures = CaptureService(self.directory, self.runtimes)
        self.evidence = EvidenceStore(self.directory, self.captures)
        self.ai = AIService(self.directory)
        self.jobs = Jobs(self.directory)

    def version(self, identifier, revision):
        repository = self.projects.repository(identifier)
        project = self.projects.get(identifier, revision, repository=repository)
        sha = project['revision']
        commit = repository.history(sha, limit=1)['commits'][0]
        try:
            difference = repository.diff(sha)
        except ValueError as error:
            difference = {'available': False, 'error': str(error), 'target': sha, 'base': commit['parents'][0] if commit['parents'] else None, 'parents': commit['parents'], 'files': [], 'counts': {}}
        return {'commit': commit, 'diff': difference, 'detection': project['detected'], 'recipe': project['recipe'], 'recipe_source': project['recipe_source'], 'recipe_approved': project['recipe_approved'], 'recipe_error': project.get('recipe_error'), 'legacy_recipe': project.get('legacy_recipe'), 'notes': project.get('version_notes', {}).get(sha), 'evidence': self.evidence.list(identifier, sha)}

    def execute(self, identifier, operation, body):
        # Resolve refs and recipe before queuing so new commits/config edits cannot
        # silently change what the user just requested.
        repository = self.projects.repository(identifier)
        project = self.projects.get(identifier, body.get('sha', 'HEAD'), repository=repository)
        sha, recipe, approved = project['revision'], project['recipe'], project['recipe_approved']
        base = None
        if not sha:
            raise ValueError('项目还没有提交。')
        if operation in ('run', 'capture') and (not recipe or recipe['adapter'] == 'manual'):
            raise ValueError(project.get('recipe_error') or '这个项目需要运行配方；也可以先添加人工截图或录屏。')
        if operation in ('run', 'capture') and recipe['adapter'] == 'command-web' and not approved:
            raise ValueError('这个配方将执行项目命令，请先打开配方编辑器、核对并保存。')
        if operation == 'run':
            callback = lambda cancel: self.runtimes.start(repository, sha, recipe, approved=approved, cancel=cancel)
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
        return self.jobs.submit(identifier, operation, callback, request={key: value for key, value in {'sha': sha, 'base': base}.items() if value is not None}, cancellable=operation in ('run', 'capture'))

    def runtime_list(self):
        projects = {record['path']: record['id'] for record in self.projects.records()}
        return [dict(runtime, project_id=projects.get(runtime.get('source'))) for runtime in self.runtimes.list()]

    def close(self):
        self.jobs.close(cancel=True)
