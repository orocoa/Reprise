"""Bounded, cancellable pack measurement without saving or deleting a pack.

The same explicit policy is used to construct an actual replacement store.
SHA-1 pack checksums and header counts are checked while streaming. This is
not a substitute for the real replacement's fsck and retained-file readback.
"""
import hashlib
import os
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import time

from .cancellation import check
from .git import _environment

PACK_OPTIONS = ('--threads=1', '--compression=6', '--no-reuse-object',
                '--window=10', '--depth=50', '--window-memory=64m',
                '--index-version=2', '--no-write-bitmap-index')
PACK_CONFIG = (('pack.writeReverseIndex', 'false'), ('pack.writeBitmapHashCache', 'false'),
               ('pack.packSizeLimit', '0'))


def stream_pack(store, objects, directory, cancel=None):
    """Return compressed bytes and v2 index bounds; retain only small diagnostics."""
    check(cancel)
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    if not objects:
        return {'pack_bytes': 0, 'index_bytes_min': 0, 'index_bytes_max': 0,
                'objects': 0, 'pack_sha1': None, 'checksum_verified': True}
    inputs = directory / 'object-ids.txt'
    with inputs.open('x') as stream:
        for oid in sorted(objects):
            stream.write(oid + '\n')
    command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0']
    for key, value in PACK_CONFIG:
        command += ['-c', key + '=' + value]
    command += ['--git-dir=' + str(store.path), 'pack-objects', '--stdout', *PACK_OPTIONS]
    header, tail, total, digest = b'', b'', 0, hashlib.sha1()
    process = None
    try:
        with inputs.open('rb') as source, (directory / 'pack.stderr.log').open('xb') as errors:
            process = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=errors,
                                       env=_environment(), start_new_session=True)
            deadline = time.monotonic() + 300
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    check(cancel)
                    if time.monotonic() >= deadline:
                        raise ValueError('模拟打包超过 300 秒；原版本保留。')
                    for key, _ in selector.select(.1):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        header = (header + chunk)[:12]
                        joined = tail + chunk
                        if len(joined) > 20:
                            digest.update(joined[:-20])
                        tail = joined[-20:]
            code = process.wait(timeout=max(.1, deadline - time.monotonic()))
        if code:
            error = (directory / 'pack.stderr.log').read_bytes()[:8192].decode('utf-8', errors='replace')
            raise ValueError(error.strip() or '模拟打包失败。')
        check(cancel)
        if (len(header) != 12 or header[:4] != b'PACK' or
                struct.unpack('!II', header[4:]) != (2, len(objects)) or
                total < 32 or digest.digest() != tail):
            raise ValueError('模拟包的对象数量或校验和不一致，未给出空间估算。')
        # Index v2: header + fanout + SHA-1 IDs + CRCs + offsets + two hashes.
        # Offsets above 2 GiB need extra 64-bit entries. Without storing/parsing
        # every compressed object, keep a conservative structural bound there.
        minimum = 1072 + 28 * len(objects)
        extra = 8 * len(objects) if total >= 2 ** 31 else 0
        return {'pack_bytes': total, 'index_bytes_min': minimum,
                'index_bytes_max': minimum + extra, 'objects': len(objects),
                'pack_sha1': tail.hex(), 'checksum_verified': True}
    finally:
        if process is not None:
            if process.poll() is None:
                # Only the process group created above belongs to this operation.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
