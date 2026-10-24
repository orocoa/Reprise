"""Durable jobs, cancellation and per-record recovery without deleting evidence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import os
import fcntl
import hashlib
import threading

from .storage import now, read_json, write_json, locked
from .runtime import process_identity
from .cancellation import Cancellation, Cancelled

ACTIVE = ('queued', 'running', 'cancelling')
TERMINAL = ('complete', 'failed', 'cancelled')


class Jobs:
    def __init__(self, directory, workers=3):
        self.directory = Path(directory) / 'jobs'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='reprise')
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.busy = set()
        self.controls = {}
        self.stopping = threading.Event()
        self.recovery_errors = {}
        for path in self.directory.glob('*.json'):
            try:
                with locked(path.with_suffix('.lock')):
                    item = self._read(path)
                    if item['status'] in ACTIVE and (not item.get('owner_pid') or process_identity(item['owner_pid']) != item.get('owner_identity')):
                        item.update(status='failed', error='服务在任务完成前退出；输出和日志已保留，可以重试。', finished_at=now())
                        write_json(path, item)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.recovery_errors[path.name] = str(error)
        self.watcher = threading.Thread(target=self._watch_cancellations, daemon=True, name='reprise-cancellations')
        self.watcher.start()

    @staticmethod
    def _read(path):
        item = read_json(path)
        if not isinstance(item, dict) or item.get('id') != path.stem or item.get('status') not in ACTIVE + TERMINAL:
            raise ValueError('任务记录结构无效')
        if 'created_at' in item and not isinstance(item['created_at'], str):
            raise ValueError('任务时间格式无效')
        return item

    def _path(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 24 or any(c not in '0123456789abcdef' for c in identifier):
            raise KeyError('找不到任务。')
        return self.directory / (identifier + '.json')

    def _request_path(self, identifier):
        return self.directory / 'cancellations' / (identifier + '.json')

    def get(self, identifier):
        path = self._path(identifier)
        if not path.exists():
            raise KeyError('找不到任务。')
        try:
            return self._read(path)
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise ValueError('任务记录无法读取，原文件已保留：%s' % path.name) from error

    def list(self):
        items, errors = [], dict(self.recovery_errors)
        for path in self.directory.glob('*.json'):
            try:
                items.append(self._read(path))
                errors.pop(path.name, None)
            except (ValueError, OSError, KeyError, TypeError) as error:
                errors[path.name] = str(error)
        self.recovery_errors = errors
        ordered = sorted(items, key=lambda item: item.get('finished_at') or item.get('created_at', ''), reverse=True)
        return [item for item in ordered if item['status'] in ACTIVE] + [
            item for item in ordered if item['status'] in TERMINAL][:30]

    def warnings(self):
        return [{'file': name, 'message': '这份任务记录无法读取，已保留原文件，其他任务可继续使用。'} for name in sorted(self.recovery_errors)]

    def cancel(self, identifier):
        path = self._path(identifier)
        with locked(path.with_suffix('.lock')):
            item = self.get(identifier)
            if item['status'] in TERMINAL:
                return item
            if not item.get('cancellable'):
                raise ValueError('此任务不支持取消；运行和采集任务支持取消。')
            write_json(self._request_path(identifier), {'id': identifier, 'requested_at': now()})
            item.update(status='cancelling', cancel_requested_at=now())
            write_json(path, item)
        return item

    def _watch_cancellations(self):
        while True:
            with self.changed:
                # Idle services need no periodic filesystem checks or wakeups.
                self.changed.wait_for(lambda: self.stopping.is_set() or any(
                    c.get('future') and c['cancellable'] for c in self.controls.values()))
                if self.stopping.is_set():
                    return
                controls = [c for c in self.controls.values() if c['cancellable']]
            for control in controls:
                future = control.get('future')
                if future and control['cancel'].requested():
                    future.cancel()
            if self.stopping.wait(.1):
                return

    def submit(self, project_id, operation, callback, request=None, cancellable=False):
        with self.lock:
            if project_id in self.busy:
                raise ValueError('这个项目已有任务正在执行，请等待完成。')
            lockfile = self.directory / ('project-' + hashlib.sha256(project_id.encode()).hexdigest() + '.lock')
            stream = lockfile.open('a')
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                stream.close()
                raise ValueError('这个项目已有任务正在执行，请等待完成。')
            self.busy.add(project_id)
            item = {'id': secrets.token_hex(12), 'project_id': project_id, 'operation': operation, 'request': request or {}, 'status': 'queued', 'created_at': now(), 'owner_pid': os.getpid(), 'owner_identity': process_identity(os.getpid()), 'cancellable': cancellable}
            path = self._path(item['id'])
            cancel = Cancellation(self._request_path(item['id']))
            control = {'cancel': cancel, 'cancellable': cancellable}
            self.controls[item['id']] = control
            try:
                write_json(path, item)
            except Exception:
                self.controls.pop(item['id'], None)
                self.busy.discard(project_id)
                stream.close()
                raise

        def finish(result=None, error=None):
            try:
                with locked(path.with_suffix('.lock')):
                    # A directory registration already switched after verification.
                    # A later cancel request cannot undo that commit or report it absent.
                    committed = (error is None and isinstance(result, dict) and
                                 ((operation in ('relink', 'migrate') and result.get('relinked') is True) or
                                  (operation == 'snapshot' and result.get('saved') is True)))
                    if cancellable and cancel.requested() and committed:
                        item.update(status='complete', cancel_arrived_after_commit=True)
                    elif cancellable and cancel.requested():
                        cleanup_errors = cancel.cleanup()
                        item.update(status='failed' if cleanup_errors else 'cancelled', error='；'.join(cleanup_errors) if cleanup_errors else str(Cancelled()))
                    elif error:
                        item.update(status='failed', error=str(error)[:3000])
                        if operation in ('verify', 'backup-check', 'data-restore') and isinstance(getattr(error, 'report', None), dict):
                            result = error.report
                    elif isinstance(result, dict) and (result.get('status') == 'failed' or
                            (result.get('status') == 'partial' and operation != 'storage')):
                        item.update(status='failed', error=('采集未完整通过，请查看证据诊断与保留的日志。'
                            if operation == 'capture' else '任务未完整通过，请查看结果与保留的日志。'))
                    else:
                        item.update(status='complete')
                    if result is not None:
                        item['result'] = result
                    item['finished_at'] = now()
                    write_json(path, item)
            finally:
                with self.lock:
                    self.busy.discard(project_id)
                    self.controls.pop(item['id'], None)
                    stream.close()
                    self.changed.notify_all()

        def execute():
            result, error = None, None
            try:
                with locked(path.with_suffix('.lock')):
                    if cancellable:
                        cancel.check()
                    item.update(status='running', started_at=now())
                    write_json(path, item)
                result = callback(cancel) if cancellable else callback()
            except Exception as caught:
                error = caught
            finally:
                finish(result, error)

        try:
            future = self.executor.submit(execute)
        except Exception as error:
            finish(error=error)
            raise
        with self.changed:
            control['future'] = future
            self.changed.notify_all()
        future.add_done_callback(lambda completed: finish(error=Cancelled()) if completed.cancelled() else None)
        return self.get(item['id'])

    def close(self, cancel=False):
        if cancel:
            with self.lock:
                identifiers = list(self.controls)
            for identifier in identifiers:
                try:
                    if self.get(identifier).get('cancellable'):
                        self.cancel(identifier)
                except (KeyError, ValueError):
                    pass
        self.executor.shutdown(wait=True)
        self.stopping.set()
        with self.changed:
            self.changed.notify_all()
        self.watcher.join(timeout=2)
