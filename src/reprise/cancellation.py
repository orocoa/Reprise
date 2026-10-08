"""Cooperative cancellation shared by jobs, snapshots, runners and capture."""
import contextlib
import subprocess
import time


class Cancelled(RuntimeError):
    def __init__(self):
        super().__init__('任务已取消；已有副本、日志和采集资料均保留。')


class Cancellation:
    def __init__(self, request_path):
        self.request_path = request_path
        self.cleanups = []

    def requested(self):
        return self.request_path.is_file()

    def check(self):
        if self.requested():
            raise Cancelled()

    def cleanup(self):
        errors = []
        for callback in reversed(self.cleanups):
            try:
                callback()
            except Exception as error:
                errors.append(str(error))
        return errors


def check(cancel):
    if cancel is not None:
        cancel.check()


def wait_process(process, timeout, cancel=None):
    deadline = time.monotonic() + timeout
    while True:
        check(cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            return process.wait(timeout=min(.15, remaining))
        except subprocess.TimeoutExpired:
            pass


@contextlib.contextmanager
def cancellable_lock(lock, cancel=None):
    while not lock.acquire(timeout=.1):
        check(cancel)
    try:
        check(cancel)
        yield
    finally:
        lock.release()
