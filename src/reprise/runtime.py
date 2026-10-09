"""Managed, retained Git snapshots and explicitly requested preview processes."""
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .recipes import recipe_hash, validate_recipe
from .cancellation import Cancelled, check, wait_owned_process
from .processes import OwnedProcessTree, ProcessCleanupError, process_identity, launch_owned


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def runtime_environment():
    node = os.environ.get('REPRISE_NODE') or shutil.which('node')
    playwright = os.environ.get('REPRISE_PLAYWRIGHT')
    browser = os.environ.get('REPRISE_BROWSER')
    return {'python': sys.executable, 'node': node, 'playwright': playwright or 'playwright (Node module resolution)',
            'browser': browser or 'Playwright Chromium', 'node_available': bool(node),
            'capture_available': None if node else False,
            'note': 'Browser capture requires Node, Playwright and Chromium. Configure REPRISE_NODE, REPRISE_PLAYWRIGHT and REPRISE_BROWSER when not installed normally.'}


class RuntimeManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.directory = self.data_dir / 'runtimes'
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes = {}
        self._trees = {}

    def _path(self, runtime_id):
        if not isinstance(runtime_id, str) or not runtime_id or any(c not in '0123456789abcdef-' for c in runtime_id):
            raise ValueError('Invalid runtime id')
        return self.directory / runtime_id / 'runtime.json'

    def _save(self, state):
        write_json(self._path(state['id']), state)

    def _alive(self, state):
        if state.get('process_trees'):
            return any(self._tree(state, name).running() for name in state['process_trees'])
        proc = self._processes.get(state['id'])
        if proc is not None and proc.poll() is not None:
            return False
        return bool(state.get('pid') and state.get('process_identity') and
                    process_identity(state['pid']) == state['process_identity'])

    def list(self):
        states = []
        with self._lock:
            for path in self.directory.glob('*/runtime.json'):
                try:
                    state = read_json(path)
                    try:
                        state['running'] = self._alive(state)
                    except ProcessCleanupError as error:
                        state.update(status='cleanup_failed', running=True, cleanup_error=str(error))
                    if state['status'] == 'running' and not state['running']:
                        state['status'] = 'exited'
                    states.append(state)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(states, key=lambda item: item.get('created_at', ''), reverse=True)

    def _launch(self, argv, root, env, state, log):
        state.update({'argv': argv, 'phase_started_at': utcnow()})
        name = 'process-' + uuid.uuid4().hex + '.json'
        tree = launch_owned(argv, root, env, log, self._path(state['id']).parent / name)
        process = tree.process
        self._processes[state['id']] = process
        self._trees[(state['id'], name)] = tree
        try:
            metadata = read_json(tree.record_path)
            state.update({'pid': process.pid, 'process_identity': metadata['root_identity'], 'process_tree': name})
            state.setdefault('process_trees', []).append(name)
            self._save(state)
        except Exception:
            # Registration is already released; a metadata/storage failure must
            # not lose our only live handle before the caller can stop it.
            tree.terminate()
            raise
        return tree

    def _tree(self, state, name):
        if not isinstance(name, str) or Path(name).name != name or not name.startswith('process-') or not name.endswith('.json'):
            raise ProcessCleanupError('Invalid process ownership record path')
        path = self._path(state['id']).parent / name
        try:
            metadata = read_json(path)
        except (OSError, ValueError) as error:
            raise ProcessCleanupError('Cannot read process ownership record: %s' % error) from error
        if not isinstance(metadata, dict):
            raise ProcessCleanupError('Invalid process ownership record')
        if name == state.get('process_tree') and (metadata.get('root_pid') != state.get('pid') or
                                                 metadata.get('root_identity') != state.get('process_identity')):
            raise ProcessCleanupError('Runtime and process ownership identities differ; no process was signalled')
        return self._trees.get((state['id'], name)) or OwnedProcessTree.from_record(path)

    def _terminate(self, state):
        if not state.get('pid'):
            return False
        if not state.get('process_trees'):
            # Older records can be upgraded while their original session leader
            # is still verifiably alive. An exited leader cannot prove ownership
            # of an arbitrary numeric group and must not be blindly signalled.
            name = 'process-' + uuid.uuid4().hex + '.json'
            tree = OwnedProcessTree.adopt(state['pid'], state.get('process_identity'),
                                          self._path(state['id']).parent / name)
            self._trees[(state['id'], name)] = tree
            state.update(process_tree=name, process_trees=[name])
            self._save(state)
        terminated, errors = False, []
        for name in reversed(state['process_trees']):
            try:
                terminated = self._tree(state, name).terminate() or terminated
            except ProcessCleanupError as error:
                errors.append(str(error))
        if errors:
            raise ProcessCleanupError('; '.join(errors))
        process = self._processes.get(state['id'])
        if process is not None:
            process.poll()  # Reap our child even when a reloaded manager stopped it.
        return terminated

    def start(self, repository, sha, recipe, approved=False, cancel=None):
        check(cancel)
        recipe = validate_recipe(recipe)
        if recipe['adapter'] == 'manual':
            raise ValueError('This project uses manual evidence; configure a browser adapter to run it')
        if recipe['adapter'] == 'command-web' and approved is not True:
            raise ValueError('Save and approve this command recipe before Run or Capture executes project code')
        resolved = repository.resolve(sha)
        rid = uuid.uuid4().hex
        folder = self.directory / rid
        folder.mkdir()
        snapshot = folder / 'source'
        state = {'id': rid, 'sha': resolved, 'adapter': recipe['adapter'], 'recipe_hash': recipe_hash(recipe),
                 'path': str(snapshot), 'log_path': str(folder / 'runtime.log'), 'created_at': utcnow(),
                 'status': 'preparing', 'running': False, 'pid': None, 'process_identity': None,
                 'source': repository.info().get('path'), 'url': None, 'warnings': []}
        self._save(state)
        try:
            if cancel is not None:
                cancel.cleanups.append(lambda: self.stop(rid))
            materialized = repository.materialize(resolved, snapshot, cancel=cancel)
            check(cancel)
            if isinstance(materialized, dict):
                state['materialization'] = materialized
                state['warnings'] = materialized.get('warnings', [])
            root = (snapshot / recipe['root']).resolve()
            try:
                root.relative_to(snapshot.resolve())
            except ValueError:
                raise ValueError('Preview root leaves the historical snapshot')
            if not root.is_dir():
                raise ValueError('Preview root %s does not exist in this version' % recipe['root'])
            port = _free_port()
            state['url'] = 'http://127.0.0.1:%s/' % port
            state['root'] = str(root)
            state['port'] = port
            env = dict(os.environ, PORT=str(port), HOST='127.0.0.1', BROWSER='none', REPRISE_RUNTIME_ID=rid)
            expand = lambda argv: [arg.replace('{port}', str(port)).replace('{host}', '127.0.0.1').replace('{root}', str(root)) for arg in argv]
            with open(state['log_path'], 'ab', buffering=0) as log:
                for phase in ('install', 'build'):
                    for command in recipe['commands'].get(phase, []):
                        check(cancel)
                        state['status'] = phase
                        tree = self._launch(expand(command), root, env, state, log)
                        try:
                            code = wait_owned_process(tree, int(os.environ.get('REPRISE_COMMAND_TIMEOUT', '600')), cancel)
                        except subprocess.TimeoutExpired:
                            self._terminate(state)
                            raise RuntimeError('%s timed out; see %s' % (phase, state['log_path']))
                        tree.terminate()
                        if code:
                            raise RuntimeError('%s exited with code %s; see %s' % (phase, code, state['log_path']))
                if recipe['adapter'] == 'static-web':
                    # A repository is data, not an import location. Isolated mode
                    # excludes cwd/PYTHONPATH/user site; -S also excludes system
                    # site startup hooks. This trusted script uses only stdlib.
                    argv = [sys.executable, '-I', '-S', str(Path(__file__).with_name('static_server.py').resolve()),
                            '--root', str(root), '--port', str(port)]
                    launch_root = folder
                else:
                    argv = expand(recipe['commands']['start'])
                    launch_root = root
                state['status'] = 'starting'
                check(cancel)
                tree = self._launch(argv, launch_root, env, state, log)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.monotonic() + recipe['readiness']['timeout_ms'] / 1000
                last_error = 'no response'
                while time.monotonic() < deadline:
                    check(cancel)
                    if tree.poll() is not None:
                        raise RuntimeError('Preview process exited with code %s; see %s' % (tree.process.returncode, state['log_path']))
                    try:
                        target = state['url'].rstrip('/') + recipe['readiness']['path']
                        with opener.open(target, timeout=min(1, max(.1, deadline - time.monotonic()))) as response:
                            if response.status < 400:
                                break
                    except (urllib.error.URLError, OSError) as error:
                        last_error = str(error)
                    time.sleep(.08)
                else:
                    raise RuntimeError('Preview readiness failed at %s: %s; see %s' % (recipe['readiness']['path'], last_error, state['log_path']))
            check(cancel)
            state.update({'status': 'running', 'running': True, 'started_at': utcnow()})
            self._save(state)
            return dict(state)
        except Exception as error:
            try:
                self._terminate(state)
            except ProcessCleanupError as cleanup:
                state.update(status='cleanup_failed', running=True, error=str(error), cleanup_error=str(cleanup), finished_at=utcnow())
                self._save(state)
                raise cleanup from error
            if isinstance(error, ProcessCleanupError):
                state.update(status='cleanup_failed', running=True, error=str(error), cleanup_error=str(error), finished_at=utcnow())
                self._save(state)
                raise
            state.update({'status': 'cancelled' if isinstance(error, Cancelled) else 'failed', 'running': False, 'error': str(error), 'finished_at': utcnow()})
            self._save(state)
            raise

    def stop(self, runtime_id):
        with self._lock:
            path = self._path(runtime_id)
            if not path.is_file():
                raise ValueError('Unknown runtime id')
            state = read_json(path)
            if state.get('status') in ('preparing', 'install', 'build', 'starting'):
                raise ValueError('运行任务尚未完成；请使用取消任务，等待进程清理结果。')
            try:
                terminated = self._terminate(state)
            except ProcessCleanupError as error:
                state.update(status='cleanup_failed', running=True, cleanup_error=str(error))
                self._save(state)
                raise
            state.update({'status': state['status'] if state.get('status') in ('failed', 'cancelled') else 'stopped',
                          'running': False, 'stopped_at': utcnow()})
            state.pop('cleanup_error', None)
            if state.get('pid') and not terminated:
                state['stop_note'] = 'Owned process already exited; no process was signalled'
            self._save(state)
            return state
