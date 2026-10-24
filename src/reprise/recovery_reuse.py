"""Reuse only an exact, complete, freshly read-back internal recovery copy."""
from pathlib import Path
import secrets
import stat

from .cancellation import check
from .folders import inventory, signature
from .metadata import xattrs
from .organize import verify_restore
from .storage import now, read_json, write_json


def verified_copy(recoveries, repository, project, sha, cancel=None):
    root = recoveries.directory
    if root.is_symlink():
        raise ValueError('恢复资料目录不能是符号链接。')
    for receipt in sorted(root.glob('*/receipt.json')):
        check(cancel)
        if receipt.parent.is_symlink() or receipt.is_symlink():
            continue
        try:
            record = read_json(receipt, required=True)
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        if (record.get('project_id') != project or record.get('sha') != sha or
                record.get('status') != 'complete' or record.get('operation') != 'restore' or
                record.get('paths') is not None or record.get('id') != receipt.parent.name):
            continue
        target = receipt.parent / 'snapshot'
        # Never use an external export/restore destination or infer an identity
        # from a display name, adjacent version, or an untrusted stored path.
        if record.get('path') != str(target):
            continue
        checks = receipt.parent / 'reuse-checks'
        if checks.is_symlink() or (checks.exists() and not checks.is_dir()):
            continue
        diagnostic = {'at': now(), 'project_id': project, 'sha': sha,
                      'recovery_id': record['id'],
                      'recovery_relative_path': str(target.relative_to(root.parent))}
        try:
            before = target.lstat()
            if not stat.S_ISDIR(before.st_mode) or target.is_symlink():
                raise ValueError('已有恢复副本不是独立目录。')
            if before.st_dev != root.parent.stat().st_dev:
                raise ValueError('已有恢复副本位于其他设备，不能作为本库内部副本复用。')
            _, excluded = inventory(target, cancel)
            if excluded:
                raise ValueError('已有恢复副本出现额外排除内容。')
            verification = verify_restore(repository, sha, target, cancel)
            metadata = repository.manifest(sha).get('root', {})
            if (('mode' in metadata and stat.S_IMODE(before.st_mode) != metadata['mode']) or
                    ('mtime_ns' in metadata and before.st_mtime_ns != metadata['mtime_ns']) or
                    ('xattrs' in metadata and xattrs(target) != metadata['xattrs'])):
                raise ValueError('已有恢复目录的元数据不匹配。')
            if signature(target.lstat()) != signature(before):
                raise ValueError('复核期间恢复目录发生变化。')
            diagnostic.update(status='complete', verification=verification)
        except (OSError, ValueError, KeyError) as error:
            diagnostic.update(status='invalid', error=str(error))
            write_json(checks / (secrets.token_hex(16) + '.json'), diagnostic, private=True)
            continue
        path = checks / (secrets.token_hex(16) + '.json')
        write_json(path, diagnostic, private=True)
        return {**record, 'reused': True, 'reuse_check': path.stem, 'verification': verification}
    return None
