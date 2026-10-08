"""Durable, bounded jobs with one execution job per project."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import os
import fcntl
import hashlib
import threading

from .storage import now, read_json, write_json
from .runtime import process_identity


class Jobs:
    def __init__(self, directory, workers=3):
        self.directory = Path(directory) / 'jobs'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='reprise')
        self.lock = threading.RLock()
        self.busy = set()
        for path in self.directory.glob('*.json'):
            item = read_json(path)
            if item['status'] in ('queued', 'running') and (not item.get('owner_pid') or process_identity(item['owner_pid']) != item.get('owner_identity')):
                item.update(status='failed', error='服务在任务完成前退出；输出和日志已保留，可以重试。', finished_at=now())
                write_json(path, item)

    def get(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 24 or any(c not in '0123456789abcdef' for c in identifier):
            raise KeyError('找不到任务。')
        result = read_json(self.directory / (identifier + '.json'))
        if result is None:
            raise KeyError('找不到任务。')
        return result

    def list(self):
        items = []
        for path in self.directory.glob('*.json'):
            try:
                items.append(read_json(path))
            except (ValueError, OSError):
                continue
        return sorted(items, key=lambda item: item.get('created_at', ''), reverse=True)[:30]

    def submit(self, project_id, operation, callback, request=None):
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
            item = {'id': secrets.token_hex(12), 'project_id': project_id, 'operation': operation, 'request': request or {}, 'status': 'queued', 'created_at': now(), 'owner_pid': os.getpid(), 'owner_identity': process_identity(os.getpid())}
            path = self.directory / (item['id'] + '.json')
            write_json(path, item)

        def execute():
            try:
                item.update(status='running', started_at=now())
                write_json(path, item)
                result = callback()
                if isinstance(result, dict) and result.get('status') in ('failed', 'partial'):
                    item.update(status='failed', result=result, error='采集未完整通过，请查看证据诊断与保留的日志。')
                else:
                    item.update(status='complete', result=result)
            except Exception as error:
                item.update(status='failed', error=str(error)[:3000])
            finally:
                item['finished_at'] = now()
                write_json(path, item)
                with self.lock:
                    self.busy.discard(project_id)
                    stream.close()
        self.executor.submit(execute)
        return dict(item)

    def close(self):
        self.executor.shutdown(wait=True)
