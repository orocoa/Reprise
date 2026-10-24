"""Version-bound, opt-in environments; only registered generated outputs can be released.

Source snapshots, failed attempts, logs and receipts are never removed here.
Commands remain approved local code, not a sandbox. Uncertain ownership,
changed contents, active processes or unavailable checks prevent release.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import stat
import subprocess
import time

from .cancellation import check
from .folders import signature
from .recipes import recipe_hash, validate_recipe
from .storage import locked, now, read_json, write_json

MAX_ENTRIES = 250000
MAX_BYTES = 128 * 1024 ** 3


@contextlib.contextmanager
def _directory(path):
    """Open every ancestor without following links, not only the last component."""
    path = Path(path).absolute()
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def _digest(stream, cancel=None):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        check(cancel)
        result.update(chunk)
    return result.hexdigest()


def _scan(root, omit=(), *, identities=False, cancel=None):
    """Descriptor-based inventory; symlinks are recorded, never followed."""
    result, total = {}, [0]
    def visit(fd, prefix, depth):
        check(cancel)
        if depth > 128:
            raise ValueError('Environment directory is too deep to verify safely')
        with os.scandir(fd) as stream:
            names = sorted(entry.name for entry in stream)
        for name in names:
            relative = name if not prefix else prefix + '/' + name
            if any(relative == path or relative.startswith(path + '/') for path in omit):
                continue
            if len(result) >= MAX_ENTRIES:
                raise ValueError('Environment exceeds the verification entry limit')
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            entry = {'mode': stat.S_IMODE(before.st_mode)}
            if before.st_uid != os.getuid() or getattr(before, 'st_flags', 0):
                raise ValueError('Environment contains unowned files or filesystem flags: ' + relative)
            if identities:
                entry['signature'] = signature(before)
            if stat.S_ISDIR(before.st_mode):
                entry['kind'] = 'dir'
                result[relative] = entry
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if signature(os.fstat(child)) != signature(before):
                        raise ValueError('Environment directory changed during verification')
                    visit(child, relative, depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(before.st_mode):
                if before.st_nlink != 1:
                    raise ValueError('Hard-linked environment files have uncertain shared ownership: ' + relative)
                total[0] += before.st_size
                if total[0] > MAX_BYTES:
                    raise ValueError('Environment exceeds the verification byte limit')
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(child, 'rb') as stream:
                    if not stat.S_ISREG(os.fstat(child).st_mode) or signature(os.fstat(child)) != signature(before):
                        raise ValueError('Environment file changed during verification')
                    digest = _digest(stream, cancel)
                    if signature(os.fstat(child)) != signature(before):
                        raise ValueError('Environment file changed during verification')
                entry.update(kind='file', size=before.st_size, sha256=digest)
                result[relative] = entry
            elif stat.S_ISLNK(before.st_mode):
                entry.update(kind='link', target=os.readlink(name, dir_fd=fd))
                result[relative] = entry
            else:
                raise ValueError('Environment contains a special file: ' + relative)
            if signature(os.stat(name, dir_fd=fd, follow_symlinks=False)) != signature(before):
                raise ValueError('Environment changed during verification')
    with _directory(root) as fd:
        initial = os.fstat(fd)
        if initial.st_uid != os.getuid() or getattr(initial, 'st_flags', 0):
            raise ValueError('Environment root ownership or flags cannot be verified')
        result[''] = {'kind': 'dir', 'mode': stat.S_IMODE(initial.st_mode)}
        if identities:
            result['']['signature'] = signature(initial)
        visit(fd, '', 0)
        if signature(os.fstat(fd)) != signature(initial):
            raise ValueError('Environment root changed during verification')
    return result


def _toolchains(tools, cancel=None):
    result = []
    for requested in tools:
        check(cancel)
        found = shutil.which(requested)
        if not found:
            raise ValueError('Required environment tool is unavailable: ' + requested)
        executable = Path(found).resolve(strict=True)
        response = subprocess.run([str(executable), '--version'], capture_output=True,
                                  timeout=20, text=True, cwd=str(executable.parent))
        if response.returncode:
            raise ValueError('Cannot verify environment tool version: ' + requested)
        with executable.open('rb') as stream:
            digest = _digest(stream, cancel)
        result.append({'requested': requested, 'path': str(executable),
                       'version': (response.stdout.strip() or response.stderr.strip())[:512],
                       'sha256': digest})
    return result


def _activity(workspace):
    executable = shutil.which('lsof') or ('/usr/sbin/lsof' if Path('/usr/sbin/lsof').is_file() else None)
    if not executable:
        raise ValueError('Cannot confirm workspace inactivity: lsof is unavailable')
    result = subprocess.run([executable, '-nP', '-Fpn', '-a', '-u', str(os.getuid()),
                             '+D', str(workspace)], capture_output=True, text=True, timeout=45)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise ValueError('Cannot confirm workspace inactivity: lsof did not complete cleanly')
    return sorted({int(line[1:]) for line in result.stdout.splitlines()
                   if line.startswith('p') and line[1:].isdigit()})


def _delete_output(path, expected, progress, cancel=None):
    """Unlink only entries matching the verified identity, using parent descriptors."""
    children = {}
    for relative in expected:
        if relative:
            parent, _, name = relative.rpartition('/')
            children.setdefault(parent, set()).add(name)
    def remove(fd, prefix):
        check(cancel)
        with os.scandir(fd) as stream:
            names = sorted(entry.name for entry in stream)
        if set(names) != children.get(prefix, set()):
            raise ValueError('Output changed before release; remaining files were retained')
        for name in names:
            check(cancel)
            relative = name if not prefix else prefix + '/' + name
            entry = expected[relative]
            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if signature(current) != entry['signature']:
                raise ValueError('Output identity changed before release: ' + relative)
            if entry['kind'] == 'dir':
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if signature(os.fstat(child)) != entry['signature']:
                        raise ValueError('Output directory was replaced before release')
                    remove(child, relative)
                finally:
                    os.close(child)
                current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if [current.st_dev, current.st_ino] != entry['signature'][:2]:
                    raise ValueError('Output directory was replaced during release')
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
                progress['removed_files'] += 1
                progress['removed_logical_bytes'] += entry.get('size', 0)
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            if signature(os.fstat(fd)) != expected['']['signature']:
                raise ValueError('Output root was replaced before release')
            remove(fd, '')
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if [current.st_dev, current.st_ino] != expected['']['signature'][:2]:
                raise ValueError('Output root was replaced during release')
            os.rmdir(path.name, dir_fd=parent)
        finally:
            os.close(fd)


class EnvironmentStore:
    def __init__(self, data_directory):
        self.directory = Path(data_directory).resolve() / 'environments'

    def _folder(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 64 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('Invalid environment identifier')
        folder = self.directory / identifier
        if self.directory.is_symlink() or folder.is_symlink():
            raise ValueError('Environment storage cannot be redirected through symlinks')
        return folder

    @contextlib.contextmanager
    def lease(self, identifier, create=False, cancel=None):
        folder = self._folder(identifier)
        if create:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        elif not folder.is_dir():
            raise ValueError('Unknown environment identifier')
        while True:
            check(cancel)
            guard = locked(folder / 'environment.lock', blocking=False)
            try:
                guard.__enter__()
                break
            except BlockingIOError:
                time.sleep(.05)
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

    def get(self, identifier):
        record = read_json(self._folder(identifier) / 'environment.json', required=True)
        if (not isinstance(record, dict) or record.get('environment_id') != identifier
                or _hash(record.get('identity')) != identifier):
            raise ValueError('Environment identity record is invalid')
        identity = record['identity']
        if not isinstance(identity, dict) or 'environment' not in validate_recipe(identity.get('recipe')):
            raise ValueError('Environment recipe binding is invalid')
        if identity.get('recipe_hash') != recipe_hash(identity['recipe']):
            raise ValueError('Environment recipe hash is invalid')
        if (any(record.get(key) != identity.get(key) for key in
                ('project_id', 'sha', 'recipe_hash', 'toolchain', 'input_hashes'))
                or record.get('outputs') != identity['recipe']['environment']['outputs']
                or record.get('environment_key') != identifier):
            raise ValueError('Environment record no longer matches its registered identity')
        self.workspace(record)
        return record

    def workspace(self, record):
        attempt = record.get('attempt_id', '')
        if not isinstance(attempt, str) or len(attempt) != 32 or any(c not in '0123456789abcdef' for c in attempt):
            raise ValueError('Invalid environment attempt')
        folder = self._folder(record['environment_id'])
        target = folder / 'attempts' / attempt / 'source'
        if str(target) != record.get('workspace'):
            raise ValueError('Environment workspace is outside its owned attempt')
        for path in (folder / 'attempts', target.parent, target):
            if path.is_symlink():
                raise ValueError('Environment workspace cannot be a symlink')
        return target

    def _save(self, record):
        write_json(self._folder(record['environment_id']) / 'environment.json', record, private=True)

    @staticmethod
    def summary(record):
        fields = ('environment_id', 'environment_key', 'project_id', 'sha', 'recipe_hash', 'workspace',
                  'outputs', 'toolchain', 'input_hashes', 'status', 'rebuild_verified', 'created_at',
                  'verified_at', 'last_used_at', 'error', 'output_bytes', 'attempt_id', 'attempts',
                  'source_files_removed', 'last_release', 'limitations')
        return {field: record[field] for field in fields if field in record}

    def list(self, project_id=None, sha=None):
        result = []
        for path in self.directory.glob('*/environment.json'):
            try:
                record = self.get(path.parent.name)
                if (project_id is None or record['project_id'] == project_id) and (sha is None or record['sha'] == sha):
                    result.append(self.summary(record))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda row: row.get('last_used_at', row['created_at']), reverse=True)

    def identity(self, repository, sha, recipe, project_id, cancel=None):
        if not isinstance(project_id, str) or not project_id or len(project_id) > 128:
            raise ValueError('Managed environments require a stable project_id')
        recipe = validate_recipe(recipe)
        policy = recipe['environment']
        sha = repository.resolve(sha)
        entries = {entry['path']: entry for entry in repository.tree(sha)}
        for output in policy['outputs']:
            if any(path == output or path.startswith(output + '/') for path in entries):
                raise ValueError('Generated output overlaps retained historical contents: ' + output)
        inputs = {}
        for name in policy['inputs']:
            check(cancel)
            entry = entries.get(name)
            if not entry or entry['type'] != 'blob' or entry['mode'] == '120000':
                raise ValueError('Environment input must be a saved regular file: ' + name)
            inputs[name] = hashlib.sha256(repository.blob(sha, name, max_bytes=8 * 1024 * 1024)).hexdigest()
        return {'project_id': project_id, 'sha': sha, 'recipe_hash': recipe_hash(recipe),
                'recipe': recipe, 'toolchain': _toolchains(policy['tools'], cancel),
                'input_hashes': inputs, 'platform': platform.system(), 'architecture': platform.machine()}

    @staticmethod
    def key(identity):
        return _hash(identity)

    def _manifests(self, record):
        path = self.workspace(record).parent / 'verification.json'
        value = read_json(path, required=True)
        if _hash(value) != record.get('verification_hash'):
            raise ValueError('Environment verification record changed or is missing')
        return value

    def _verify_contents(self, record, cancel=None, require_outputs=True):
        workspace = self.workspace(record)
        manifests = self._manifests(record)
        if _scan(workspace, record['outputs'], cancel=cancel) != manifests['source']:
            raise ValueError('Historical workspace contains changed or additional data; retained without modification')
        if require_outputs:
            for output in record['outputs']:
                if _scan(workspace / output, identities=True, cancel=cancel) != manifests['outputs'][output]:
                    raise ValueError('Generated output changed after verification: ' + output)
        return manifests

    def prepare(self, identity, repository, cancel=None):
        identifier = self.key(identity)
        folder = self._folder(identifier)
        previous = None
        if (folder / 'environment.json').exists():
            previous = self.get(identifier)
            if previous['status'] == 'ready' and previous.get('rebuild_verified'):
                try:
                    self._verify_contents(previous, cancel)
                    previous['last_used_at'] = now()
                    self._save(previous)
                    return {'record': previous, 'workspace': self.workspace(previous), 'reuse': True,
                            'materialization': previous['materialization']}
                except (OSError, ValueError) as error:
                    previous['error'] = str(error)
                    previous['status'] = 'failed'
                    self._save(previous)
        attempt = secrets.token_hex(16)
        workspace = folder / 'attempts' / attempt / 'source'
        workspace.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
        attempts = list(previous.get('attempts', [])) if previous else []
        if previous:
            attempts.append({'attempt_id': previous['attempt_id'], 'workspace': previous['workspace'],
                             'status': previous['status'], 'verified_at': previous.get('verified_at')})
        record = {'schema': 1, 'environment_id': identifier, 'environment_key': identifier, 'identity': identity,
                  'project_id': identity['project_id'], 'sha': identity['sha'], 'recipe_hash': identity['recipe_hash'],
                  'toolchain': identity['toolchain'], 'input_hashes': identity['input_hashes'],
                  'outputs': identity['recipe']['environment']['outputs'], 'workspace': str(workspace),
                  'attempt_id': attempt, 'attempts': attempts, 'created_at': now(), 'last_used_at': now(),
                  'status': 'preparing', 'rebuild_verified': False, 'source_files_removed': False,
                  'limitations': ['Only explicitly registered generated outputs can be released.',
                    'Source, logs, evidence, failed attempts and external/global caches are retained.',
                    'Declared toolchain and inputs are recorded and checked; system libraries, host variables, external services and network availability are not archived.',
                    'Commands are approved local code, not a sandbox. Modified or uncertain outputs are not released.']}
        self._save(record)
        try:
            materialization = repository.materialize(identity['sha'], workspace, cancel=cancel)
            for output in record['outputs']:
                path = workspace / output
                if os.path.lexists(path):
                    raise ValueError('Generated output already exists in historical snapshot: ' + output)
                if not path.parent.is_dir() or path.parent.resolve() != path.parent:
                    raise ValueError('Output parent must be a real directory in the saved snapshot: ' + output)
            baseline = _scan(workspace, cancel=cancel)
            record['materialization'] = materialization
            self._save(record)
            return {'record': record, 'workspace': workspace, 'reuse': False,
                    'source_baseline': baseline, 'materialization': materialization}
        except Exception as error:
            self.failed(record, error)
            raise

    def built(self, prepared, runtime_id, cancel=None):
        record = prepared['record']
        if prepared['reuse']:
            return
        workspace = self.workspace(record)
        if _scan(workspace, record['outputs'], cancel=cancel) != prepared['source_baseline']:
            raise ValueError('Install/build changed historical source or wrote undeclared data; all files retained')
        outputs = {name: _scan(workspace / name, identities=True, cancel=cancel) for name in record['outputs']}
        manifests = {'source': prepared['source_baseline'], 'outputs': outputs}
        write_json(workspace.parent / 'verification.json', manifests, private=True)
        record.update(verification_hash=_hash(manifests), build_runtime_id=runtime_id,
                      output_bytes=sum(entry.get('size', 0) for output in outputs.values() for entry in output.values()),
                      built_at=now())
        self._save(record)

    def ready(self, prepared, cancel=None):
        record = prepared['record']
        self._verify_contents(record, cancel)
        record.update(status='ready', rebuild_verified=True, verified_at=now(), last_used_at=now())
        record.pop('error', None)
        self._save(record)

    def failed(self, record, error):
        record.update(status='failed', rebuild_verified=False, error=str(error)[:1500], failed_at=now())
        self._save(record)

    def inspect_release(self, identifier, runtimes, cancel=None):
        record = self.get(identifier)
        blockers = []
        active = [row['id'] for row in runtimes if row.get('environment_id') == identifier and
                  (row.get('running') or row.get('status') in ('preparing', 'install', 'build', 'starting', 'cleanup_failed'))]
        if active:
            blockers.append('Environment has active or uncertain runtime processes')
        if record.get('status') != 'ready' or not record.get('rebuild_verified'):
            blockers.append('Environment has not completed a clean rebuild and successful start')
        workspace = self.workspace(record)
        external = []
        if not blockers:
            try:
                self._verify_contents(record, cancel)
                if _toolchains(record['identity']['recipe']['environment']['tools'], cancel) != record['toolchain']:
                    raise ValueError('Required toolchain changed; rebuild availability cannot be confirmed')
                external = _activity(workspace)
                if external:
                    blockers.append('Workspace is open in a process; stop it before release')
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                blockers.append(str(error))
        return {'environment_id': identifier, 'project_id': record['project_id'], 'sha': record['sha'],
                'releasable': not blockers, 'blockers': blockers, 'active_runtime_ids': active,
                'active_process_ids': external, 'outputs': record['outputs'],
                'output_bytes': record.get('output_bytes', 0), 'filesystem_free_bytes': shutil.disk_usage(self.directory).free,
                'reclaimable_bytes': None, 'source_files_removed': False, 'rebuild_verified': record.get('rebuild_verified', False)}

    def release(self, identifier, runtime_provider, cancel=None):
        with self.lease(identifier, cancel=cancel):
            record = self.get(identifier)
            if record['status'] == 'released':
                return dict(record['last_release'], already_released=True)
            preflight = self.inspect_release(identifier, runtime_provider(), cancel)
            if not preflight['releasable']:
                raise ValueError('Environment release refused: ' + '; '.join(preflight['blockers']))
            workspace = self.workspace(record)
            manifests = self._verify_contents(record, cancel)
            receipt = {'id': secrets.token_hex(16), 'environment_id': identifier, 'project_id': record['project_id'],
                       'sha': record['sha'], 'attempt_id': record['attempt_id'], 'status': 'releasing', 'created_at': now(),
                       'released_outputs': [], 'removed_files': 0, 'removed_logical_bytes': 0,
                       'source_files_removed': False, 'rebuild_required': True, 'reclaimable_bytes': None}
            receipt_path = self._folder(identifier) / 'releases' / (receipt['id'] + '.json')
            if receipt_path.parent.is_symlink():
                raise ValueError('Environment release receipts cannot be redirected through symlinks')
            receipt['receipt'] = str(receipt_path)
            write_json(receipt_path, receipt, private=True)
            before = shutil.disk_usage(self.directory).free
            record.update(status='releasing', rebuild_verified=False)
            self._save(record)
            try:
                for output in record['outputs']:
                    check(cancel)
                    _delete_output(workspace / output, manifests['outputs'][output], receipt, cancel)
                    receipt['released_outputs'].append(output)
                receipt.update(status='released', finished_at=now(),
                               filesystem_free_delta_bytes=shutil.disk_usage(self.directory).free - before)
                record.update(status='released', last_release=receipt, released_at=now())
                write_json(receipt_path, receipt, private=True)
                self._save(record)
                return receipt
            except Exception as error:
                receipt.update(status='partial', error=str(error), finished_at=now(),
                               filesystem_free_delta_bytes=shutil.disk_usage(self.directory).free - before)
                write_json(receipt_path, receipt, private=True)
                record.update(status='failed', error='Release incomplete; remaining files retained', last_release=receipt)
                self._save(record)
                raise
