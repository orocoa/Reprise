"""Managed, retained Git snapshots and explicitly requested preview processes."""
import datetime
import json
import os
import shutil
import signal
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


def process_identity(pid):
    """PID plus kernel start identity; never trust a persisted PID on its own."""
    try:
        if Path('/proc/%s/stat' % int(pid)).exists():
            content = Path('/proc/%s/stat' % int(pid)).read_text()
            fields = content[content.rfind(')') + 2:].split()
            if fields[0] == 'Z':
                return None
            return 'linux:' + fields[19]
        result = subprocess.run(['ps', '-p', str(int(pid)), '-o', 'lstart=', '-o', 'stat='],
                                capture_output=True, text=True, timeout=3)
        content = result.stdout.strip()
        if result.returncode or not content:
            return None
        started, state = content.rsplit(None, 1)
        if state.startswith('Z'):
            return None
        return 'ps:' + started.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


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

    def _path(self, runtime_id):
        if not isinstance(runtime_id, str) or not runtime_id or any(c not in '0123456789abcdef-' for c in runtime_id):
            raise ValueError('Invalid runtime id')
        return self.directory / runtime_id / 'runtime.json'

    def _save(self, state):
        write_json(self._path(state['id']), state)

    def _alive(self, state):
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
                    state['running'] = self._alive(state)
                    if state['status'] == 'running' and not state['running']:
                        state['status'] = 'exited'
                    states.append(state)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(states, key=lambda item: item.get('created_at', ''), reverse=True)

    def _launch(self, argv, root, env, state, log):
        state.update({'argv': argv, 'phase_started_at': utcnow()})
        process = subprocess.Popen(argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self._processes[state['id']] = process
        state.update({'pid': process.pid, 'process_identity': process_identity(process.pid)})
        self._save(state)
        return process

    def _terminate(self, state):
        process = self._processes.get(state['id'])
        if not self._alive(state):
            if process is not None:
                process.poll()
            return False
        pid = state['pid']
        try:
            # Each launched process is a new session leader. Identity is checked again
            # immediately before signalling; no name-based or port-based kills.
            if process_identity(pid) != state['process_identity'] or os.getpgid(pid) != pid:
                return False
            os.killpg(pid, signal.SIGTERM)
            end = time.monotonic() + 3
            while time.monotonic() < end:
                if process is not None:
                    process.poll()
                if not self._alive(state):
                    if process is not None:
                        process.wait(timeout=3)
                    return True
                time.sleep(.05)
            if self._alive(state) and os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGKILL)
            if process is not None:
                process.wait(timeout=3)
            return True
        except (ProcessLookupError, subprocess.TimeoutExpired):
            return True

    def start(self, repository, sha, recipe, approved=False):
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
            materialized = repository.materialize(resolved, snapshot)
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
            env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get('PYTHONPATH', '')
            expand = lambda argv: [arg.replace('{port}', str(port)).replace('{host}', '127.0.0.1').replace('{root}', str(root)) for arg in argv]
            with open(state['log_path'], 'ab', buffering=0) as log:
                for phase in ('install', 'build'):
                    for command in recipe['commands'].get(phase, []):
                        state['status'] = phase
                        process = self._launch(expand(command), root, env, state, log)
                        try:
                            code = process.wait(timeout=int(os.environ.get('REPRISE_COMMAND_TIMEOUT', '600')))
                        except subprocess.TimeoutExpired:
                            self._terminate(state)
                            raise RuntimeError('%s timed out; see %s' % (phase, state['log_path']))
                        if code:
                            raise RuntimeError('%s exited with code %s; see %s' % (phase, code, state['log_path']))
                if recipe['adapter'] == 'static-web':
                    argv = [sys.executable, '-m', 'reprise.static_server', '--root', str(root), '--port', str(port)]
                else:
                    argv = expand(recipe['commands']['start'])
                state['status'] = 'starting'
                process = self._launch(argv, root, env, state, log)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.monotonic() + recipe['readiness']['timeout_ms'] / 1000
                last_error = 'no response'
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Preview process exited with code %s; see %s' % (process.returncode, state['log_path']))
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
            state.update({'status': 'running', 'running': True, 'started_at': utcnow()})
            self._save(state)
            return dict(state)
        except Exception as error:
            self._terminate(state)
            state.update({'status': 'failed', 'running': False, 'error': str(error), 'finished_at': utcnow()})
            self._save(state)
            raise

    def stop(self, runtime_id):
        with self._lock:
            path = self._path(runtime_id)
            if not path.is_file():
                raise ValueError('Unknown runtime id')
            state = read_json(path)
            alive = self._alive(state)
            terminated = self._terminate(state)
            state.update({'status': 'stopped' if terminated or state.get('status') != 'failed' else 'failed',
                          'running': False, 'stopped_at': utcnow()})
            if state.get('pid') and not alive and not terminated:
                state['stop_note'] = 'Owned process already exited; no process was signalled'
            self._save(state)
            return state
