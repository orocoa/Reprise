"""Nonblocking data-directory leases shared by normal use and offline upkeep.

Acquire a shared lease for the entire application/CLI operation. Offline backup
uses an exclusive lease and also holds the legacy server lock. No missing data
directory is created, no process is stopped, and locks are never symlinked.
"""
import fcntl
import os
from pathlib import Path
import stat


LEASE_FILE = '.data-lease.lock'


class DataLeaseError(ValueError):
    pass


class DataLease:
    def __init__(self, directory, exclusive=False):
        self.directory = Path(directory).expanduser().absolute()
        self.exclusive = exclusive
        self._fds = []

    def _acquire(self, name, operation):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        fd = None
        root_fd = os.open(self.directory.anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in self.directory.parts[1:]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
                os.close(root_fd)
                root_fd = child
            fd = os.open(name, flags, 0o600, dir_fd=root_fd)
            named = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise
        finally:
            os.close(root_fd)
        try:
            value = os.fstat(fd)
            if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1 or
                    stat.S_ISLNK(named.st_mode) or
                    (value.st_dev, value.st_ino) != (named.st_dev, named.st_ino)):
                raise DataLeaseError('数据锁无效或为符号链接；未开始维护。')
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
            self._fds.append(fd)
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        if self._fds:
            raise DataLeaseError('此数据租约已经持有，不能重复进入。')
        try:
            if self.directory.is_symlink() or not self.directory.is_dir():
                raise DataLeaseError('数据目录不存在或为符号链接；未创建数据目录。')
            self._acquire(LEASE_FILE, fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH)
            if self.exclusive:
                self._acquire('server.lock', fcntl.LOCK_EX)
            return self
        except (OSError, ValueError) as error:
            self.close()
            if isinstance(error, DataLeaseError):
                raise
            raise DataLeaseError('此数据目录正在使用或无法取得安全数据锁；请先停止 Reprise 及其任务，再重试。') from None

    def close(self):
        while self._fds:
            fd = self._fds.pop()
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def __exit__(self, *unused):
        self.close()


def data_lease(directory, exclusive=False):
    return DataLease(directory, exclusive=exclusive)
