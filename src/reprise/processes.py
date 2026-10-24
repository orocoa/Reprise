"""Identity-checked cleanup of observed, owned POSIX process trees.

Inherited ownership markers identify forked/reparented/session-detached children
even after the launch parent exits. This manages approved local commands, not
hostile code containment: deliberately stripped markers may defeat attribution.
Ambiguous groups, failed observations and failed signals are never called stopped.
"""
import contextlib
import ctypes
import errno
import fcntl
import functools
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

OWNER_ENV = 'REPRISE_PROCESS_OWNER'
_OWNER_CACHE = {}
_OWNER_LOCK = threading.Lock()


def _owner_marker(pid):
    """Read only our inherited marker; never retain other process environment.

    The marker survives fork/reparent/setsid. It supplements the parent/session
    graph for ordinary daemonizing commands, not hostile code containment.
    """
    try:
        if sys.platform.startswith('linux'):
            raw = (Path('/proc') / str(pid) / 'environ').read_bytes()
            environment = raw.split(b'\0')
        elif sys.platform == 'darwin':
            libc = ctypes.CDLL(None, use_errno=True)
            mib = (ctypes.c_int * 3)(1, 49, int(pid))  # CTL_KERN, KERN_PROCARGS2
            size = ctypes.c_size_t(1024 * 1024)
            data = ctypes.create_string_buffer(size.value)
            if libc.sysctl(mib, 3, data, ctypes.byref(size), None, 0):
                code = ctypes.get_errno()
                if code in (errno.ESRCH, errno.EPERM, errno.EACCES, errno.EINVAL):
                    return None  # unrelated/protected processes are never signalled
                raise OSError(code, os.strerror(code))
            raw = ctypes.string_at(data, size.value)
            argc = int.from_bytes(raw[:4], sys.byteorder)
            offset = raw.find(b'\0', 4) + 1  # executable pathname
            while offset < len(raw) and raw[offset] == 0:
                offset += 1
            for _ in range(argc):
                end = raw.find(b'\0', offset)
                if end < 0:
                    return None
                offset = end + 1
            environment = raw[offset:].split(b'\0')
        else:
            raise ProcessObservationError('Unsupported process ownership platform')
        prefix = OWNER_ENV.encode() + b'='
        for item in environment:
            if item.startswith(prefix):
                value = item[len(prefix):].decode('ascii', errors='ignore')
                return value if len(value) == 32 and all(c in '0123456789abcdef' for c in value) else None
        return None
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


@functools.lru_cache(maxsize=4096)
def _identity_time(identity):
    if identity.startswith('linux:'):
        return int(identity.split(':', 1)[1])
    if identity.startswith('ps:'):
        return time.mktime(time.strptime(identity[3:], '%a %b %d %H:%M:%S %Y'))
    return None


def _marked_members(marker, table, fresh=False, root_identity=None):
    now = time.monotonic()
    found = {}
    with _OWNER_LOCK:
        if len(_OWNER_CACHE) > 10000:
            _OWNER_CACHE.clear()
        for pid, row in table.items():
            if row['zombie']:
                continue
            # Descendants cannot predate their launch root. Avoid inspecting
            # older unrelated applications, and keep startup/stop costs bounded.
            if root_identity and _identity_time(row['identity']) < _identity_time(root_identity):
                continue
            key = (pid, row['identity'])
            cached = _OWNER_CACHE.get(key)
            if fresh or cached is None or now - cached[0] > .5:
                cached = (now, _owner_marker(pid))
                _OWNER_CACHE[key] = cached
            if cached[1] == marker:
                # The environment and process table are separate kernel reads.
                # Recheck identity before attributing, then again before signals.
                current = _inspect_or_confirm_exit(pid)
                if current and current['identity'] == row['identity'] and current['uid'] == os.getuid():
                    found[pid] = current
    return found


class ProcessCleanupError(RuntimeError):
    pass


class ProcessObservationError(ProcessCleanupError):
    pass


@functools.lru_cache(maxsize=1)
def boot_identity():
    if sys.platform.startswith('linux'):
        return 'linux:' + Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    result = subprocess.run(['/usr/sbin/sysctl', '-n', 'kern.boottime'],
                            capture_output=True, text=True, timeout=3)
    if result.returncode or not result.stdout.strip():
        raise ProcessCleanupError('Cannot establish the current boot identity')
    return 'darwin:' + result.stdout.strip()


def _linux_info(pid):
    path = Path('/proc') / str(pid)
    try:
        raw = (path / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return {'pid': int(pid), 'ppid': int(fields[1]), 'pgid': int(fields[2]),
                'sid': int(fields[3]), 'uid': path.stat().st_uid,
                'identity': 'linux:' + fields[19], 'zombie': fields[0] == 'Z'}
    except (FileNotFoundError, ProcessLookupError):
        return None


def _ps_rows(pid=None):
    argv = ['/bin/ps', '-p', str(pid)] if pid is not None else ['/bin/ps', '-ax']
    argv += ['-o', 'pid=', '-o', 'ppid=', '-o', 'pgid=', '-o', 'uid=',
             '-o', 'lstart=', '-o', 'stat=']
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=5,
                                env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.SubprocessError) as error:
        raise ProcessObservationError('Process inspection failed: %s' % error) from error
    if result.returncode:
        if pid is not None and result.returncode == 1 and not result.stderr.strip():
            return []
        raise ProcessObservationError('Cannot inspect process identities: ' + result.stderr.strip()[:300])
    rows = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 4)
        if len(fields) != 5:
            raise ProcessCleanupError('Unexpected process identity output')
        started, status = fields[4].rsplit(None, 1)
        identifier, ppid, pgid, uid = map(int, fields[:4])
        if uid != os.getuid():
            continue
        try:
            sid = os.getsid(identifier)
        except ProcessLookupError:
            if not status.startswith('Z'):
                continue
            sid = None  # macOS can retain ps zombie data after getsid stops working.
        rows.append({'pid': identifier, 'ppid': ppid, 'pgid': pgid, 'sid': sid,
                     'uid': uid, 'identity': 'ps:' + started.strip(),
                     'zombie': status.startswith('Z')})
    return rows


def _process_info(pid):
    if sys.platform.startswith('linux'):
        return _linux_info(pid)
    rows = _ps_rows(pid)
    return rows[0] if rows else None


def _inspect_or_confirm_exit(pid, timeout=.5):
    """Resolve the short macOS ps/getsid/zombie transition without guessing.

    A missing ps row is not proof of exit while kill(pid, 0) still succeeds.
    Re-read until a kernel identity is available or the PID is truly absent;
    never send a terminating signal or substitute a retained identity here.
    """
    deadline = time.monotonic() + timeout
    while True:
        current = _process_info(pid)
        if current is not None:
            return current
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        except OSError as error:
            raise ProcessObservationError('Cannot inspect owned PID %s: %s' % (pid, error)) from error
        if time.monotonic() >= deadline:
            raise ProcessObservationError('Cannot inspect a possibly living owned PID %s' % pid)
        time.sleep(.02)


def strict_process_identity(pid):
    """Return an identity or confirmed absence; never hide observation failure."""
    if type(pid) is not int or pid <= 0:
        raise ProcessObservationError('Invalid PID for process identity inspection')
    try:
        value = _inspect_or_confirm_exit(pid)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProcessObservationError('Process inspection failed: %s' % error) from error
    return value['identity'] if value and not value['zombie'] else None


def process_identity(pid):
    """Compatible with runtime and browser-worker identity strings."""
    try:
        value = _process_info(int(pid))
        return value['identity'] if value and not value['zombie'] else None
    except (OSError, ValueError, subprocess.SubprocessError, ProcessCleanupError):
        return None


def _uncached_process_table():
    if sys.platform.startswith('linux'):
        rows = []
        for path in Path('/proc').iterdir():
            if path.name.isdigit():
                try:
                    info = _linux_info(int(path.name))
                except PermissionError:
                    continue
                if info:
                    rows.append(info)
    else:
        rows = _ps_rows()
    return {row['pid']: row for row in rows if row['uid'] == os.getuid()}


_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT = {'at': 0, 'table': {}}


def _process_table():
    # Multiple runtime/capture observers share a short snapshot instead of
    # launching one whole-machine ps per tree per tick. Identity is checked
    # directly again before any signal; signals never trust this cache.
    with _SNAPSHOT_LOCK:
        if time.monotonic() - _SNAPSHOT['at'] > .04:
            _SNAPSHOT['table'] = _uncached_process_table()
            _SNAPSHOT['at'] = time.monotonic()
        return {pid: dict(row) for pid, row in _SNAPSHOT['table'].items()}


def _invalidate_snapshot():
    with _SNAPSHOT_LOCK:
        _SNAPSHOT['at'] = 0


def _write(path, value):
    if path.is_symlink():
        raise ProcessCleanupError('Process ownership record cannot be a symlink')
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    temporary.replace(path)


class OwnedProcessTree:
    def __init__(self, process, record_path, interval=.1, owner_marker=None):
        self._initialize(record_path, process, interval)
        try:
            root = _process_info(process.pid)
            if not root or root['pgid'] != process.pid or root['sid'] != process.pid:
                raise ProcessCleanupError('Cannot establish the new process session identity')
            self._boot = boot_identity()
            state = {'schema': 1, 'boot_identity': self._boot, 'root_pid': process.pid,
                     'root_identity': root['identity'], 'uid': os.getuid(),
                     'members': [root], 'status': 'tracking'}
            if owner_marker:
                state['owner_marker'] = owner_marker
            with self._locked():
                if self.record_path.exists():
                    raise ProcessCleanupError('Process ownership record already exists')
                _write(self.record_path, state)
            self.refresh()
        except Exception as error:
            # This Popen is still unreaped and was just created by the caller.
            # Do not poll/reap it before this fallback: its PID cannot be reused
            # while the child remains ours. Never target the caller's group.
            if process.returncode is None:
                try:
                    if os.getpgid(process.pid) == process.pid and process.pid != os.getpgrp():
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                except (OSError, subprocess.SubprocessError):
                    pass
            raise ProcessCleanupError('Could not establish process ownership: %s' % error) from error
        self._observer = threading.Thread(target=self._observe, name='reprise-process-observer', daemon=True)
        self._observer.start()

    def _initialize(self, record_path, process=None, interval=.1):
        self.record_path = Path(record_path)
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.process = process
        self.interval = max(.02, float(interval))
        self._mutex = threading.RLock()
        self._closed = threading.Event()
        self._observer = None
        self._boot = None

    @classmethod
    def from_record(cls, record_path):
        tree = cls.__new__(cls)
        tree._initialize(record_path)
        tree._boot = boot_identity()
        with tree._locked():
            tree._read()
        return tree

    @classmethod
    def adopt(cls, pid, expected_identity, record_path, interval=.1):
        """Register a legacy live session leader after checking its identity.

        Unlike __init__, a failed adoption never signals the supplied PID.
        """
        tree = cls.__new__(cls)
        tree._initialize(record_path, interval=interval)
        tree._boot = boot_identity()
        root = _process_info(int(pid))
        if (not root or root['zombie'] or root['identity'] != expected_identity or
                root['uid'] != os.getuid() or root['pgid'] != pid or root['sid'] != pid):
            raise ProcessCleanupError('Cannot adopt an exited or unverified process session')
        with tree._locked():
            if tree.record_path.exists():
                state = tree._read()
                if state['root_pid'] != pid or state['root_identity'] != expected_identity:
                    raise ProcessCleanupError('Existing ownership record belongs to another process')
            else:
                _write(tree.record_path, {'schema': 1, 'boot_identity': tree._boot,
                       'root_pid': pid, 'root_identity': expected_identity, 'uid': os.getuid(),
                       'members': [root], 'status': 'tracking'})
        tree.refresh()
        tree._observer = threading.Thread(target=tree._observe, name='reprise-process-observer', daemon=True)
        tree._observer.start()
        return tree

    @contextlib.contextmanager
    def _locked(self):
        with self._mutex:
            lock = self.record_path.with_name(self.record_path.name + '.lock')
            if lock.is_symlink():
                raise ProcessCleanupError('Process ownership lock cannot be a symlink')
            with lock.open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def _read(self):
        try:
            if self.record_path.is_symlink():
                raise ValueError('symlink')
            state = json.loads(self.record_path.read_text())
            if (state['schema'] != 1 or state['uid'] != os.getuid() or
                    state['boot_identity'] != self._boot or not isinstance(state['members'], list) or
                    not any(row['pid'] == state['root_pid'] and row['identity'] == state['root_identity']
                            for row in state['members'])):
                raise ValueError('identity mismatch')
            for member in state['members']:
                if type(member['pid']) is not int or member['pid'] <= 1 or not isinstance(member['identity'], str):
                    raise ValueError('invalid process member')
            if state.get('owner_marker') and (len(state['owner_marker']) != 32 or
                    any(c not in '0123456789abcdef' for c in state['owner_marker'])):
                raise ValueError('invalid ownership marker')
            return state
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ProcessCleanupError('Cannot verify the retained process ownership record: %s' % error) from error

    def _advance(self, state):
        if state['status'] == 'stopped':
            return [], state
        table = _process_table()
        marked = _marked_members(state['owner_marker'], table,
                                 fresh=state['status'] in ('stopping', 'unconfirmed'),
                                 root_identity=state['root_identity']) if state.get('owner_marker') else {}
        known = {member['pid']: member for member in state['members']}
        previous_groups = {(row['pgid'], row['sid']) for row in known.values() if not row.get('exited')}
        confirmed = dict(marked)
        for pid, previous in known.items():
            if previous.get('exited'):
                continue
            current = table.get(pid)
            if current is None:
                current = _inspect_or_confirm_exit(pid)
                if current is None:
                    previous['exited'] = True
                else:
                    table[pid] = current
            if current and current['identity'] != previous['identity']:
                raise ProcessCleanupError('Process identity changed for PID %s; no signal sent' % pid)
            if current:
                if current['zombie'] and current['sid'] is None:
                    current['sid'] = previous['sid']
                confirmed[pid] = current
        # A confirmed zombie also anchors its still-existing session until reaped.
        # This permits finding children between command exit and Popen.wait().
        while True:
            groups = {(row['pgid'], row['sid']) for row in confirmed.values()}
            found = {pid: row for pid, row in table.items() if pid not in confirmed and
                     (row['ppid'] in confirmed or (row['pgid'], row['sid']) in groups)}
            if not found:
                break
            confirmed.update(found)
        for pid, row in confirmed.items():
            known[pid] = row
        # A familiar numeric PGID alone is not proof after its last identified
        # member exited. Refuse to kill a possibly reused group.
        ambiguous = [row for pid, row in table.items() if not row['zombie'] and pid not in confirmed and
                     (row['pgid'], row['sid']) in previous_groups]
        if ambiguous:
            # ps is a sequence of kernel reads, not an atomic snapshot. A helper
            # shown as alive can already be gone by the time its leader is read.
            # Do not signal it; check that it really survives before failing.
            time.sleep(.03)
            for row in ambiguous:
                current = _inspect_or_confirm_exit(row['pid'])
                if current and not current['zombie']:
                    raise ProcessCleanupError('A process group has no surviving identity anchor; cleanup is unconfirmed '
                                              '(PID %s, group %s)' % (current['pid'], current['pgid']))
        state['members'] = list(known.values())
        return [row for row in confirmed.values() if not row['zombie']], state

    def _recover_observation(self, state, living):
        if not state.get('observation_error'):
            return
        if state.get('observation_error_kind') == 'inspection' and living:
            state.setdefault('observation_errors', []).append({
                'message': state.pop('observation_error'), 'recovered_at': time.time()})
            state.pop('observation_error_kind', None)
            state['status'] = 'tracking'
            return
        raise ProcessCleanupError(state['observation_error'])

    def refresh(self):
        with self._locked():
            state = self._read()
            before = json.dumps(state, sort_keys=True)
            try:
                living, state = self._advance(state)
                self._recover_observation(state, living)
                if json.dumps(state, sort_keys=True) != before:
                    _write(self.record_path, state)
                return bool(living)
            except Exception as error:
                state['observation_error'] = str(error)
                state['observation_error_kind'] = ('inspection' if isinstance(error, (ProcessObservationError, OSError, subprocess.SubprocessError))
                                                   else state.get('observation_error_kind', 'ownership'))
                state['status'] = 'unconfirmed'
                _write(self.record_path, state)
                raise ProcessCleanupError(str(error)) from error

    def _observe(self):
        while not self._closed.wait(self.interval):
            try:
                if not self.refresh():
                    return
            except Exception:
                return  # refresh retains the error; cleanup must report it.

    def running(self):
        return self.refresh()

    def poll(self):
        if self.process is None:
            self.refresh()
            return None
        # Do not reap a running-to-exited race after one snapshot. A zombie is
        # a stable kernel identity anchor; observe its children before reaping.
        if self.process.returncode is None:
            root = _process_info(self.process.pid)
            if root and not root['zombie']:
                self.refresh()
                return None
            _invalidate_snapshot()
        self.refresh()
        return self.process.poll()

    @property
    def args(self):
        return self.process.args if self.process is not None else None

    @property
    def returncode(self):
        return self.process.returncode if self.process is not None else None

    def wait(self, timeout=None):
        if self.process is None:
            raise ProcessCleanupError('A restored process tree has no waitable child')
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            value = self.poll()
            if value is not None:
                return value
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(.02 if deadline is None else min(.02, max(0, deadline - time.monotonic())))

    def _signal(self, state, sig):
        # The caller persisted this complete member snapshot before signalling.
        signalled = set()
        for member in state['members']:
            if member.get('exited'):
                continue
            current = _inspect_or_confirm_exit(member['pid'])
            if not current or current['zombie']:
                continue
            if current['identity'] != member['identity']:
                raise ProcessCleanupError('Process identity changed before signalling PID %s' % member['pid'])
            group = (current['pgid'], current['sid'])
            if group in signalled:
                continue
            if current['pgid'] <= 1 or current['pgid'] == os.getpgrp():
                raise ProcessCleanupError('Refusing to signal an unrelated process group')
            try:
                os.killpg(current['pgid'], sig)
                signalled.add(group)
            except ProcessLookupError:
                continue
            except OSError as error:
                raise ProcessCleanupError('Cannot signal owned process group: %s' % error) from error

    def terminate(self, timeout=3):
        self.close()
        signalled = False
        try:
            for sig, duration in ((signal.SIGTERM, max(0, timeout)), (signal.SIGKILL, 2)):
                _invalidate_snapshot()
                with self._locked():
                    state = self._read()
                    living, state = self._advance(state)
                    self._recover_observation(state, living)
                    if not living and state['status'] != 'stopped':
                        # ps/proc enumeration is not atomic with fork/exit. A
                        # second fresh ownership scan closes the reparent gap.
                        state['status'] = 'stopping'
                        time.sleep(.03)
                        _invalidate_snapshot()
                        living, state = self._advance(state)
                    if not living:
                        state['status'] = 'stopped'
                        _write(self.record_path, state)
                        if self.process is not None:
                            self.process.poll()
                        return signalled
                    state['status'] = 'stopping'
                    _write(self.record_path, state)
                    self._signal(state, sig)
                    signalled = True
                deadline = time.monotonic() + duration
                while time.monotonic() < deadline:
                    if not self.refresh():
                        break
                    time.sleep(min(self.interval, max(0, deadline - time.monotonic())))
            _invalidate_snapshot()
            with self._locked():
                state = self._read()
                living, state = self._advance(state)
                if not living and state['status'] != 'stopped':
                    state['status'] = 'stopping'
                    time.sleep(.03)
                    _invalidate_snapshot()
                    living, state = self._advance(state)
                if living:
                    raise ProcessCleanupError('Owned processes remain alive after SIGKILL: ' +
                                              ', '.join(str(row['pid']) for row in living))
                state['status'] = 'stopped'
                _write(self.record_path, state)
            if self.process is not None:
                self.process.poll()
            return signalled
        except Exception as error:
            try:
                with self._locked():
                    state = self._read()
                    state.update(status='unconfirmed', cleanup_error=str(error))
                    _write(self.record_path, state)
            except Exception:
                pass
            raise ProcessCleanupError('Process cleanup could not be confirmed: %s' % error) from error

    def close(self):
        self._closed.set()
        if self._observer is not None and self._observer is not threading.current_thread():
            self._observer.join(timeout=6)
            if self._observer.is_alive():
                raise ProcessCleanupError('Process observer did not stop')


def stop_owned_tree(record_path, timeout=3):
    tree = OwnedProcessTree.from_record(record_path)
    try:
        return tree.terminate(timeout=timeout)
    finally:
        tree.close()


def owned_tree_running(record_path):
    tree = OwnedProcessTree.from_record(record_path)
    try:
        return tree.running()
    finally:
        tree.close()


# An isolated, short-lived exec gate gives the parent time to register ownership
# even for commands such as true. It exits on EOF and becomes the requested
# command via exec; there is no long-lived supervisor or shell.
_EXEC_GATE = '''import json,os,sys
fd=int(sys.argv[1])
permission=os.read(fd,1)
os.close(fd)
if permission != b"1": os._exit(125)
argv=json.loads(sys.argv[2])
try: os.execvpe(argv[0],argv,os.environ)
except OSError as error:
 print("Cannot execute requested command: "+str(error),file=sys.stderr,flush=True)
 os._exit(127)
'''


def launch_owned(argv, cwd, env, log, record_path, interval=.1):
    """Launch an argv command only after a retained ownership record exists.

    Use tree.poll()/tree.wait() instead of its raw Popen when waiting for a
    command: these inspect an exited parent's remaining children before reaping.
    """
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(value, str) for value in argv):
        raise ValueError('Expected a nonempty argv sequence')
    # Fail before creating even the exec gate when this environment cannot
    # support retained ownership and cleanup. A later denial still fails closed.
    try:
        boot_identity()
        identity = strict_process_identity(os.getpid())
        observer = _uncached_process_table().get(os.getpid())
        if not identity or not observer or observer['identity'] != identity:
            raise ProcessObservationError('Cannot verify this process in the owned-user process table')
    except (OSError, subprocess.SubprocessError, ProcessCleanupError) as error:
        raise ProcessObservationError(
            '当前沙箱无法可靠观察进程，未启动命令。请在客户端为本次命令批准可观察的运行权限后重试预览，无需重复保存。 '
            'Process observation is unavailable in this sandbox; command was not started. '
            'Approve observable execution for this command in your client and retry the preview, not the save. '
            + str(error)) from error
    reader, writer = os.pipe()
    process = tree = None
    marker = uuid.uuid4().hex
    env = dict(env, **{OWNER_ENV: marker})
    try:
        process = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', _EXEC_GATE,
                                    str(reader), json.dumps(list(argv))],
                                   cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, pass_fds=(reader,))
        os.close(reader)
        reader = None
        tree = OwnedProcessTree(process, record_path, interval=interval, owner_marker=marker)
        os.write(writer, b'1')
        return tree
    except Exception:
        if tree is not None:
            tree.terminate(timeout=.1)
        elif process is not None and process.returncode is None:
            # Registration failed before release: the gate never executes argv.
            try:
                process.kill()
                process.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
        raise
    finally:
        if reader is not None:
            os.close(reader)
        os.close(writer)
