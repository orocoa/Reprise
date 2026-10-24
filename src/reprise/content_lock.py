"""Reentrant, cross-process gate for the owned content store, including reads."""
from contextlib import contextmanager
from pathlib import Path
import threading

from .storage import locked

_guard = threading.Lock()
_gates = {}


@contextmanager
def content_access(directory):
    if Path(directory).is_symlink():
        raise ValueError('内容库目录不能是符号链接。')
    if not Path(directory).parent.is_dir():
        raise ValueError('内容库数据目录不存在。')
    key = str(Path(directory).absolute())
    with _guard:
        gate, local = _gates.setdefault(key, (threading.RLock(), threading.local()))
    with gate:
        if getattr(local, 'depth', 0):
            local.depth += 1
            try:
                yield
            finally:
                local.depth -= 1
        else:
            # The gate lives outside content so a read of a missing library
            # cannot accidentally recreate that library directory.
            with locked(Path(directory).parent / '.content-access.lock'):
                local.depth = 1
                try:
                    yield
                finally:
                    local.depth = 0
