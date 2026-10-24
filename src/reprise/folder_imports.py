"""Import explicitly ordered folders / ZIP contents; restore, verify, then advise.

No deletion executor exists here. Original paths, recovery copies and failures
are retained. ZIP content recovery deliberately does not claim archive identity.
"""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import subprocess
import zipfile

from .cancellation import check
from .content_lock import content_access
from .folders import inventory, signature, _directory, _open_file
from .git import _safe_path
from .integrity import verify_project
from .organize import digest, git_protections, verify_restore
from .relocation import _scan, _overlap
from .storage import now, read_json, write_json, locked
from .storage_report import storage_report

MAX_BYTES = 128 * 1024**3
MAX_ENTRIES = 100000


def zip_members(archive):
    """Validate all names/types/budgets before publishing any file content."""
    rows, names, explicit, total = {}, {}, set(), 0
    for item in archive.infolist():
        original = item.orig_filename
        name = item.filename.rstrip('/')
        if (not name or '\x00' in original or '\\' in name or ':' in name or
                name != str(PurePosixPath(name)) or '.git' in [p.casefold() for p in name.split('/')]):
            raise ValueError('ZIP 包含不安全、歧义或 .git 路径；原包保留。')
        _safe_path(name)
        if name in explicit or (name.casefold() in names and names[name.casefold()] != name):
            raise ValueError('ZIP 存在重复或大小写冲突路径；不能明确恢复。')
        explicit.add(name)
        mode = item.external_attr >> 16 if item.create_system == 3 else 0
        kind = 'dir' if item.is_dir() else 'file'
        if (item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFDIR if kind == 'dir' else stat.S_IFREG) or
                mode & 0o7000 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise ValueError('ZIP 含加密、链接、特殊权限或不支持的压缩类型；原包保留。')
        for parent in reversed(PurePosixPath(name).parents):
            if str(parent) == '.':
                continue
            key = str(parent)
            if key in rows and rows[key]['kind'] != 'dir':
                raise ValueError('ZIP 文件与目录路径冲突。')
            if key.casefold() in names and names[key.casefold()] != key:
                raise ValueError('ZIP 存在大小写冲突目录。')
            names[key.casefold()] = key
            rows.setdefault(key, {'kind': 'dir', 'mode': 0o755, 'mtime_ns': 0, 'size': 0})
        if name in rows and rows[name]['kind'] != kind:
            raise ValueError('ZIP 文件与目录路径冲突。')
        try:
            stamp = int(datetime.datetime(*item.date_time, tzinfo=datetime.timezone.utc).timestamp() * 10**9)
        except (ValueError, OverflowError):
            raise ValueError('ZIP 时间信息无效。') from None
        names[name.casefold()] = name
        rows[name] = {'kind': kind, 'mode': mode & 0o777 or (0o755 if kind == 'dir' else 0o644),
                      'mtime_ns': stamp, 'size': item.file_size if kind == 'file' else 0,
                      'member': item}
        total += rows[name]['size']
        if len(rows) > MAX_ENTRIES or total > MAX_BYTES or item.file_size > max(1, item.compress_size) * 10000:
            raise ValueError('ZIP 超过条目、展开字节或压缩率上限；请分批人工审阅。')
    return rows, total


def in_use(path):
    executable = shutil.which('lsof')
    if not executable:
        return 'unknown'
    try:
        args = [executable, '-nP', '-t'] + (['+D', str(path)] if path.is_dir() else ['--', str(path)])
        process = subprocess.run(args, capture_output=True, timeout=20)
        if process.stderr.strip():
            return 'unknown'
        if process.returncode == 1 and not process.stdout.strip():
            return 'not-observed'
        return 'in-use' if process.returncode == 0 and process.stdout.strip() else 'unknown'
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'


def source_state(path, kind, cancel=None):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('原路径已变成链接。')
    if kind == 'zip':
        with _directory(path.parent) as fd, _open_file(fd, path.name) as stream:
            value = os.fstat(stream.fileno())
            result = {'signature': signature(value), 'sha256': digest(stream, cancel),
                      'logical_bytes': value.st_size, 'allocated_bytes': value.st_blocks * 512 if hasattr(value, 'st_blocks') else None,
                      'hardlinks': value.st_nlink > 1, 'flags': bool(getattr(value, 'st_flags', 0))}
            if signature(os.fstat(stream.fileno())) != result['signature']:
                raise ValueError('ZIP 在读取期间发生变化。')
        if signature(path.lstat()) != result['signature']:
            raise ValueError('ZIP 路径在读取期间发生变化。')
        return result
    scan = _scan(path, cancel, skip_git=True, metadata=True)
    _, excluded = inventory(path, cancel)
    allocated, allocation_known, hardlinks, flags = 0, True, False, bool(getattr(path.stat(), 'st_flags', 0))
    for name, entry in scan['entries'].items():
        value = (path / name).lstat()
        if signature(value) != entry['signature']:
            raise ValueError('目录在读取期间发生变化。')
        if entry['kind'] != 'dir':
            allocated += getattr(value, 'st_blocks', 0) * 512
            allocation_known &= hasattr(value, 'st_blocks')
        hardlinks |= entry['kind'] == 'file' and value.st_nlink > 1
        flags |= bool(getattr(value, 'st_flags', 0))
    return {'scan': scan, 'excluded': excluded, 'logical_bytes': scan['logical_bytes'],
            'allocated_bytes': allocated if allocation_known else None, 'hardlinks': hardlinks, 'flags': flags}


class FolderImports:
    def __init__(self, app):
        self.app, self.projects = app, app.projects
        self.directory = app.directory / 'folder-imports'

    def plan_path(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('导入报告标识无效。')
        return self.directory / identifier / 'report.json'

    def get(self, identifier):
        return read_json(self.plan_path(identifier), required=True)

    def validate(self, value):
        if not isinstance(value, dict) or not isinstance(value.get('name'), str) or not 1 <= len(value['name'].strip()) <= 120:
            raise ValueError('请填写项目名称。')
        versions = value.get('versions')
        if not isinstance(versions, list) or not 2 <= len(versions) <= 32:
            raise ValueError('请按从旧到新顺序明确列出 2–32 个版本。')
        result, paths = [], []
        for entry in versions:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
                raise ValueError('每版须有路径和名称。')
            raw = Path(entry['path']).expanduser().absolute()
            if any(p.is_symlink() for p in (raw, *raw.parents)):
                raise ValueError('导入路径不能通过符号链接。')
            path = raw.resolve()
            kind = 'folder' if path.is_dir() else 'zip' if path.is_file() and path.suffix.lower() == '.zip' else None
            title = entry.get('title')
            if not kind or not isinstance(title, str) or not title.strip() or len(title) > 120 or '\0' in title:
                raise ValueError('每版须有有效目录或 ZIP 路径及 1–120 字版本名。')
            if kind == 'zip' and entry.get('zip_mode') != 'contents':
                raise ValueError('ZIP 须明确选择 zip_mode=contents；它不保留原始 ZIP 字节和封装元数据。')
            if _overlap(path, self.app.directory) or any(_overlap(path, p) for p in paths):
                raise ValueError('各输入与 Reprise 数据目录必须互不包含，且不能重复。')
            paths.append(path)
            result.append({'path': str(path), 'title': title.strip(), 'kind': kind})
        if result[-1]['kind'] != 'folder':
            raise ValueError('最后一项须为明确保留的当前工作文件夹；ZIP 不能作为工作目录。')
        target = value.get('project_id')
        if target is not None:
            record = self.projects.record(target)
            if record.get('kind') != 'folder' or record['path'] != result[-1]['path']:
                raise ValueError('追加目标必须是当前目录对应的已登记文件夹项目；不改写 Git 历史。')
        elif any(p.get('kind') == 'folder' and p['path'] == result[-1]['path'] for p in self.projects.records()):
            raise ValueError('当前目录已登记；请明确提供 project_id，追加保存而不改写已有历史。')
        return {'name': self.projects.record(target)['name'] if target else value['name'].strip(), 'versions': result, 'project_id': target}

    def start(self, value):
        specification = self.validate(value)
        preview = self.analyze(value)
        if value.get('preflight_fingerprint') and value['preflight_fingerprint'] != preview['fingerprint']:
            raise ValueError('输入或目标已在预检后变化；请重新预检，尚未保存版本。')
        if not preview['capacity_available']:
            raise ValueError('可用空间低于保留模式的规划预算；请改用有足够空间的数据目录，不会自动清理。')
        project = (self.projects.get(specification['project_id']) if specification['project_id'] else
                   self.projects.add(specification['versions'][-1]['path'], specification['name'], kind='folder'))
        report_id = secrets.token_hex(16)
        return self.app.jobs.submit(project['id'], 'import-folders',
            lambda cancel: self.create(project['id'], specification, cancel, report_id, preview),
            request={'version_count': len(specification['versions']), 'report_id': report_id, 'name': specification['name']}, cancellable=True)

    def analyze(self, value, cancel=None):
        from .import_preflight import analyze
        return analyze(self, value, cancel)

    def start_analysis(self, value):
        return self.app.jobs.submit('local-import-preflight', 'folder-import-preflight',
            lambda cancel: self.analyze(value, cancel),
            request={'name': value.get('name'), 'input': value}, cancellable=True)

    def _zip_snapshot(self, record, version, origin, cancel, expected_state=None, pre_publish=None):
        store = self.projects.folders
        store.ensure()
        repository = store.repository(record)
        old_sha = repository.info()['head']
        entries, added, read = {}, 0, 0
        path = Path(version['path'])
        with _directory(path.parent) as fd, _open_file(fd, path.name) as stream, zipfile.ZipFile(stream) as archive:
            rows, _ = zip_members(archive)
            for name, row in rows.items():
                check(cancel)
                entry = {key: item for key, item in row.items() if key != 'member'}
                entry['signature'] = [0, 0, (stat.S_IFDIR if row['kind'] == 'dir' else stat.S_IFREG) | row['mode'],
                                      row['size'], row['mtime_ns'], 0]
                if row['kind'] == 'file':
                    with archive.open(row['member']) as source:
                        oid, sha256, reused = store.blob(source, row['size'], cancel)
                    entry.update(oid=oid, sha256=sha256)
                    read += row['size']
                    added += 0 if reused else row['size']
                entries[name] = entry
        stats = {'files': sum(e['kind'] == 'file' for e in entries.values()),
                 'logical_bytes': sum(e['size'] for e in entries.values()),
                 'unique_bytes': sum({e['oid']: e['size'] for e in entries.values() if 'oid' in e}.values()),
                 'new_bytes': added, 'read_bytes': read, 'reused_files': 0}
        manifest = {'format': 'reprise-folder-v1', 'project_id': record['id'], 'source': version['path'],
                    'created_at': now(), 'entries': entries, 'excluded': [], 'exclusion_rules': [], 'stats': stats,
                    'root': {'mode': 0o700, 'mtime_ns': 0}, 'origin': origin}
        with locked(store.directory / 'write.lock'):
            if expected_state is not None and source_state(version['path'], 'zip', cancel) != expected_state:
                raise ValueError('ZIP 在预检核验后发生变化；未发布快照。')
            if pre_publish is not None:
                pre_publish()
            return store._commit_snapshot(record, repository, old_sha, version['title'], manifest, cancel)

    def create(self, identifier, specification, cancel=None, report_id=None, preview=None):
        key = report_id or secrets.token_hex(16)
        path = self.plan_path(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
        report = {'id': key, 'project_id': identifier, 'name': specification['name'], 'created_at': now(),
                  'status': 'running', 'versions': [], 'originals_removed': False, 'delete_executor_available': False,
                  'keep_path': specification['versions'][-1]['path'], 'report_path': str(path),
                  'preflight': preview,
                  'order_basis': 'user-specified import order; original chronology and Git ancestry unknown',
                  'physical_free_delta_estimate_bytes': None,
                  'limitations': ['只验证已存范围可恢复；不证明应用可运行或没有外部路径依赖。',
                    '分配块是文件元数据模型；APFS 克隆、快照、其他进程及目录块影响实际卷空闲，保持未知。',
                    'ZIP 内容模式不能恢复原 ZIP 字节、封装顺序、注释、签名或未保存的封装元数据。',
                    'ZIP 只流式拆解明确输入的最外层；嵌套压缩包仍按文件保存，时间按 ZIP 声明解释为 UTC，原文件系统元数据未知。',
                    '新增占用是本数据目录在任务期间的观测差，可能含并发任务；不是保证可回收的独占物理空间。',
                    '本库和校验副本在同一数据目录，不是独立介质备份；删除候选不是删除授权。']}
        write_json(path, report, private=True)
        try:
            with content_access(self.projects.folders.directory):
                if preview:
                    from .import_preflight import analyze
                    current = analyze(self, None, cancel, specification=specification)
                    if current['fingerprint'] != preview['fingerprint'] or not current['capacity_available']:
                        raise ValueError('排队期间输入或可用空间发生变化；请重新预检，尚未保存版本。')
                before_storage = storage_report(self.app.directory, cancel)
                states, expanded = [], 0
                for position, version in enumerate(specification['versions']):
                    check(cancel)
                    state = source_state(version['path'], version['kind'], cancel)
                    state_name = 'source-%s.json' % position
                    write_json(path.parent / state_name, state, private=True)
                    states.append(state_name)
                    if version['kind'] == 'zip':
                        with zipfile.ZipFile(version['path']) as archive:
                            _, size = zip_members(archive)
                        expanded += size
                    else:
                        expanded += state['logical_bytes']
                if shutil.disk_usage(self.app.directory).free < expanded * 2 + 16 * 1024**2:
                    raise ValueError('空间不足以保留版本库和完整恢复校验副本；未自动清除任何内容。')
                write_json(path.parent / 'source-states.json', states, private=True)
                if preview:
                    current = analyze(self, None, cancel, specification=specification)
                    if current['fingerprint'] != preview['fingerprint'] or not current['capacity_available']:
                        raise ValueError('读取正文期间输入或容量发生变化；未发布快照，请重新预检。')
                record = self.projects.record(identifier)
                for position, (version, state_name) in enumerate(zip(specification['versions'], states)):
                    check(cancel)
                    state = read_json(path.parent / state_name, required=True)
                    origin = {'kind': 'imported-' + version['kind'], 'batch_id': key, 'position': position + 1,
                              'source': version['path'], 'order_basis': report['order_basis']}
                    def publication_check():
                        from .import_preflight import capacity_budget
                        check(cancel)
                        remaining = (preview['versions'][position:] if preview else [])
                        budget = capacity_budget(sum(v['expanded_logical_bytes'] for v in remaining),
                                                 sum(v['entries'] for v in remaining))
                        if preview and shutil.disk_usage(self.app.directory).free < budget:
                            raise ValueError('发布前容量不足，未发布本版；已有版本与诊断保留。')
                    if version['kind'] == 'zip':
                        origin.update(zip_mode='contents', original_zip_sha256=state['sha256'], byte_identical_zip_recoverable=False,
                            metadata_basis='ZIP declared fields; timestamps interpreted as UTC; virtual file signatures')
                        result = self._zip_snapshot(record, version, origin, cancel, state, publication_check)
                    else:
                        result = self.projects.folders.snapshot({**record, 'path': version['path']}, version['title'], cancel, origin,
                                                              expected_state=state, pre_publish=publication_check)
                    repository = self.projects.repository(identifier)
                    if version['kind'] == 'folder':
                        saved = repository.manifest(result['sha'])
                        expected = state['scan']
                        if (saved['root'] != expected['root'] or set(saved['entries']) != set(expected['entries']) or
                                any(any(saved['entries'][name].get(field) != entry.get(field, 0 if field == 'size' else None)
                                    for field in ('kind', 'size', 'sha256', 'target', 'mode', 'mtime_ns', 'xattrs'))
                                    for name, entry in expected['entries'].items())):
                            raise ValueError('快照与导入前清单不一致；原件保留。')
                    recovery = self.app.recovery.verified_copy(repository, identifier, result['sha'], cancel)
                    if recovery is None:
                        recovery = self.app.recovery.create(repository, identifier, result['sha'], 'restore', cancel=cancel)
                    verification = recovery.get('verification') or verify_restore(repository, result['sha'], recovery['path'], cancel)
                    if source_state(version['path'], version['kind'], cancel) != state:
                        raise ValueError('导入期间原件发生变化；版本与恢复副本保留，未生成可删除结论。')
                    report['versions'].append({**version, 'sha': result['sha'], 'stats': result['stats'],
                        'recovery_path': recovery['path'], 'verification': verification,
                        'recovery_reused': recovery.get('reused', False),
                        'source_logical_bytes': state['logical_bytes'], 'source_allocated_bytes': state['allocated_bytes'],
                        'loss_on_source_removal': ('原 ZIP 字节与封装元数据；内部文件可按版本恢复。' if version['kind'] == 'zip'
                            else '原目录位置及未完整覆盖的所有者等元数据；已核验的文件内容与目录可恢复。')})
                    write_json(path, report, private=True)
                report['status'] = 'complete'
                report = self._assess(report, states, cancel)
                after = storage_report(self.app.directory, cancel)
                report['additional_managed_file_bytes'] = after['logical_bytes'] - before_storage['logical_bytes']
                report['additional_managed_allocated_bytes'] = (after['allocated_bytes'] - before_storage['allocated_bytes']
                    if after['allocated_bytes'] is not None and before_storage['allocated_bytes'] is not None else None)
                recoveries = [storage_report(Path(v['recovery_path']), cancel) for v in report['versions']]
                report['recovery_file_bytes'] = sum(r['logical_bytes'] for r in recoveries)
                report['recovery_copies_reused'] = sum(v['recovery_reused'] for v in report['versions'])
                report['recovery_copies_created'] = len(report['versions']) - report['recovery_copies_reused']
                report['recovery_allocated_bytes'] = (sum(r['allocated_bytes'] for r in recoveries)
                    if all(r['allocated_bytes'] is not None for r in recoveries) else None)
                report['modeled_net_after_source_removal_bytes'] = (report['candidate_allocated_bytes'] - report['additional_managed_allocated_bytes']
                    if report['candidate_costs_share_data_volume'] and report['additional_managed_allocated_bytes'] is not None else None)
                report['conditional_net_if_readbacks_also_removed_bytes'] = (report['modeled_net_after_source_removal_bytes'] + report['recovery_allocated_bytes']
                    if report['modeled_net_after_source_removal_bytes'] is not None and report['recovery_allocated_bytes'] is not None
                    and all(v.get('recovery_revalidated') for v in report['versions']) else None)
                report['readback_removal_requires_separate_decision'] = True
                report['accounting_scope'] = 'regular files before final report/job receipt; all recovery copies retained'
                report['finished_at'] = now()
                write_json(path, report, private=True)
                return report
        except BaseException as error:
            report.update(status='incomplete', error=str(error), finished_at=now())
            for version in report['versions']:
                version.update(removal_candidate=False, blockers=['批次未完整完成，不能使用此报告删除原件。'])
            write_json(path, report, private=True)
            raise

    def _assess(self, report, states, cancel):
        report = json.loads(json.dumps(report))
        if not isinstance(states, list) or len(states) != len(report['versions']):
            raise ValueError('原件检查清单不完整；未生成可删除结论。')
        protected = self.app.organization.protections()
        records = self.projects.records()
        for version, expected in zip(report['versions'], states):
            check(cancel)
            if isinstance(expected, str):
                if not re.fullmatch(r'source-[0-9]+\.json', expected):
                    raise ValueError('原件状态文件名无效。')
                expected = read_json(self.plan_path(report['id']).parent / expected, required=True)
            source = Path(version['path'])
            version['source_device'] = str((expected.get('signature') or expected['scan']['root_signature'])[0])
            blockers, readback_valid = [], False
            if str(source) == report['keep_path']:
                blockers.append('保留的当前工作文件夹。')
            if any(_overlap(source, Path(p)) for p in protected):
                blockers.append('与受保护的运行来源或副本重叠。')
            if any(p['id'] != report['project_id'] and _overlap(source, Path(p['path']).resolve()) for p in records):
                blockers.append('仍被其他已登记项目使用。')
            try:
                current = source_state(source, version['kind'], cancel)
                if current != expected:
                    blockers.append('原件在校验后发生变化，旧结论失效。')
                if current.get('hardlinks') or current.get('flags'):
                    blockers.append('存在硬链接或未完整保存的文件系统标志。')
                if current.get('allocated_bytes') is None:
                    blockers.append('平台未提供文件分配块信息，空间收益未知。')
                if version['kind'] == 'folder':
                    if any(e['signature'][0] != current['scan']['root_signature'][0] for e in current['scan']['entries'].values()):
                        blockers.append('目录含跨设备挂载；不能合并计算空间或移除整个原目录。')
                    tracked, roots = git_protections(source, current['scan']['entries'], current['excluded'])
                    if current['excluded'] or tracked or roots:
                        blockers.append('含未保存的 .git 或受 Git 管理的内容，不能删整个原目录。')
                usage = in_use(source)
                if usage != 'not-observed':
                    blockers.append('检测到使用中路径或无法完整检查进程占用。')
                repository = self.projects.repository(report['project_id'])
                verify_project(self.projects, report['project_id'], version['sha'], cancel)
                verify_restore(repository, version['sha'], version['recovery_path'], cancel)
                readback_valid = True
            except (OSError, ValueError, KeyError) as error:
                blockers.append('复核未通过：' + str(error))
            version.update(blockers=blockers, removal_candidate=not blockers,
                           recovery_revalidated=readback_valid,
                           assessment='verified-content-candidate' if not blockers else 'keep-or-review')
        report['candidate_logical_bytes'] = sum(v['source_logical_bytes'] for v in report['versions'] if v['removal_candidate'])
        report['candidate_allocated_bytes'] = sum(v['source_allocated_bytes'] for v in report['versions'] if v['removal_candidate'])
        data_device = str(self.app.directory.stat().st_dev)
        report['candidate_costs_share_data_volume'] = all(v['source_device'] == data_device
            for v in report['versions'] if v['removal_candidate'])
        report['reviewed_at'] = now()
        return report

    def review(self, identifier, cancel=None):
        report = self.get(identifier)
        if report['status'] not in ('complete', 'restored-review-required'):
            raise ValueError('导入批次未完整完成；原件保持。')
        states = read_json(self.plan_path(identifier).parent / 'source-states.json', required=True)
        with content_access(self.projects.folders.directory):
            result = self._assess(report, states, cancel)
            result['status'] = 'complete'
            if (result['candidate_costs_share_data_volume'] and not result.get('accounting_historical') and
                    result.get('additional_managed_allocated_bytes') is not None):
                result['modeled_net_after_source_removal_bytes'] = result['candidate_allocated_bytes'] - result['additional_managed_allocated_bytes']
                result['conditional_net_if_readbacks_also_removed_bytes'] = (result['modeled_net_after_source_removal_bytes'] + result['recovery_allocated_bytes']
                    if result.get('recovery_allocated_bytes') is not None and all(v.get('recovery_revalidated') for v in result['versions']) else None)
            else:
                result['modeled_net_after_source_removal_bytes'] = None
                result['conditional_net_if_readbacks_also_removed_bytes'] = None
            receipt = self.plan_path(identifier).parent / ('review-' + secrets.token_hex(8) + '.json')
            result['review_receipt'] = str(receipt)
            write_json(receipt, result, private=True)
            return result
