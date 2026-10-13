"""Small durable local stores; atomic replace and cross-process update locking."""
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import secrets


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_json(path, default=None, *, required=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('状态文件不能是符号链接。')
    if not required and not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('状态文件不能是符号链接。')
    temporary = path.parent / ('.' + path.name + '.' + secrets.token_hex(8))
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


@contextlib.contextmanager
def locked(path, *, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('锁文件不能是符号链接。')
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
