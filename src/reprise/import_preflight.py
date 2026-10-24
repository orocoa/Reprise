"""Read-only import cost planning. No source bodies, snapshots or restores."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from .cancellation import check
from .folders import inventory, signature
from .relocation import MAX_BYTES, MAX_ENTRIES
from .storage import now


def capacity_budget(expanded, entries):
    return 2 * expanded + expanded // 100 + entries * 16384 + 16 * 1024**2


def analyze(imports, value, cancel=None, *, specification=None):
    # Import locally: the existing importer owns validation and ZIP boundaries.
    from .folder_imports import zip_members
    specification = imports.validate(value) if specification is None else specification
    destination = imports.app.directory
    device = destination.stat().st_dev
    for name in ('content', 'content/objects.git', 'content/staging', 'recoveries', 'folder-imports'):
        managed = destination / name
        if managed.is_symlink():
            raise ValueError('受管数据目录不能通过符号链接。')
        if managed.exists() and managed.stat().st_dev != device:
            raise ValueError('受管数据目录不能包含跨设备挂载；请使用独立数据目录。')
    rows, identities, volumes = [], [], {}
    expanded, entry_count = 0, 0
    for version in specification['versions']:
        check(cancel)
        source = Path(version['path'])
        if any(p.is_symlink() for p in (source, *source.parents)):
            raise ValueError('预检路径不能通过符号链接。')
        before = source.lstat()
        if version['kind'] == 'zip':
            with zipfile.ZipFile(source) as archive:
                entries, logical = zip_members(archive)
            state = {'signature': signature(before)}
            # ZIP declared sizes are planning input, not readback evidence.
            count, excluded = len(entries), []
            allocated = before.st_blocks * 512 if hasattr(before, 'st_blocks') else None
            original = before.st_size
        else:
            entries, excluded = inventory(source, cancel, device=before.st_dev)
            logical = sum(e.get('size', 0) for e in entries.values() if e['kind'] != 'dir')
            allocated, known, original = 0, True, logical
            for name, entry in entries.items():
                check(cancel)
                stat = (source / name).lstat()
                if signature(stat) != entry['signature']:
                    raise ValueError('预检期间输入发生变化，请重新预检。')
                if stat.st_dev != before.st_dev:
                    raise ValueError('输入包含跨设备挂载；请按磁盘分开管理，未保存版本。')
                if entry['kind'] != 'dir':
                    known &= hasattr(stat, 'st_blocks')
                    allocated += getattr(stat, 'st_blocks', 0) * 512
            allocated = allocated if known else None
            state = {'signature': signature(before), 'entries': entries, 'excluded': excluded}
            count = len(entries)
            if count > MAX_ENTRIES or logical > MAX_BYTES:
                raise ValueError('输入超过目录条目或展开量上限，请分开管理。')
        if signature(source.lstat()) != signature(before):
            raise ValueError('预检期间输入发生变化，请重新预检。')
        expanded += logical
        entry_count += count
        device = str(before.st_dev)
        volume = volumes.setdefault(device, {'device': device, 'input_logical_bytes': 0,
                                           'input_allocated_bytes': 0})
        volume['input_logical_bytes'] += original
        volume['input_allocated_bytes'] = (volume['input_allocated_bytes'] + allocated
            if volume['input_allocated_bytes'] is not None and allocated is not None else None)
        rows.append({**version, 'keep': len(rows) == len(specification['versions']) - 1,
                     'expanded_logical_bytes': logical, 'original_logical_bytes': original,
                     'original_allocated_bytes': allocated, 'entries': count,
                     'excluded': excluded, 'source_device': device})
        # Bind each input without retaining every version's full inventory.
        state_hash = hashlib.sha256()
        for chunk in json.JSONEncoder(ensure_ascii=True, sort_keys=True).iterencode(state):
            state_hash.update(chunk.encode())
        identities.append(state_hash.hexdigest())
        del state, entries
    check(cancel)
    # This is a capacity planning budget, not a bound on filesystem allocation.
    # Payloads may not deduplicate; all readbacks remain. Include small-object,
    # manifest and compression overhead rather than just doubling file lengths.
    budget = capacity_budget(expanded, entry_count)
    free = shutil.disk_usage(destination).free
    identity = {'specification': specification, 'sources': identities,
                'data_directory': str(destination), 'data_device': destination.stat().st_dev}
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=True, sort_keys=True,
                                           separators=(',', ':')).encode()).hexdigest()
    return {'schema': 1, 'status': 'preview', 'created_at': now(),
            'fingerprint': fingerprint, 'name': specification['name'],
            'project_id': specification.get('project_id'), 'versions': rows,
            'keep_path': rows[-1]['path'], 'data_directory': str(destination),
            'data_device': str(destination.stat().st_dev), 'source_volumes': list(volumes.values()),
            'expanded_logical_bytes': expanded,
            'additional_content_logical_bytes_min': 0,
            'additional_content_logical_bytes_max': expanded,
            'additional_readback_logical_bytes_max': expanded,
            'capacity_budget_bytes': budget, 'filesystem_free_bytes': free,
            'capacity_available': free >= budget,
            'modeled_net_after_source_removal_bytes': None,
            'physical_free_delta_estimate_bytes': None,
            'readback_verified': False, 'source_safety_checked': False,
            'originals_removed': False, 'snapshots_created': False,
            'recovery_copies_created': False,
            'blockers': [] if free >= budget else ['可用空间低于本次保留模式的规划预算。'],
            'limitations': [
                '只读目录元数据和 ZIP 目录，不读取文件正文、不保存版本、不生成恢复副本。',
                '尚未比较内容指纹，新增内容范围为 0 到全部展开内容；实际共享量在保存后报告。',
                '保留全部已有文件与校验副本；预算包含最坏情况内容、完整读回及元数据预留，不是分配块保证。',
                '输入分配量按路径相加，硬链接、APFS 共享块和快照可能重复计量；不是可释放量。',
                '源目录和版本库可能位于不同卷，不能跨卷相减作为某一卷的净收益。',
                '空间与输入可能变化，执行前重新核对；不能用预检推导原件可删除或恢复已通过。',
                'ZIP 大小来自封装目录；内容损坏、CRC、原文件系统属性和实际恢复留待执行核验。']}
