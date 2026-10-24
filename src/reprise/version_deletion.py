"""Explicit, planned deletion of owned snapshots, never external repositories.

Build and verify a replacement object store before switching it into service.
Each surviving complete tree is a shallow root, with its original full commit
SHA and ordered parent headers unchanged. All folder readers share the gate.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time
from types import SimpleNamespace

from .cancellation import check
from .content_lock import content_access
from .folders import FolderStore
from .git import Repository
from .integrity import verify_project, _Boundary
from .storage import now, read_json, write_json
from .packing import PACK_CONFIG, PACK_OPTIONS, stream_pack


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_store(path):
    # Establish a durable replacement before removing the old copy. This is
    # still not a claim of tested power-loss behavior on every filesystem.
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            fd = os.open(Path(root) / name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        _sync_directory(root)


def sizes(path):
    if Path(path).is_symlink() or not Path(path).is_dir():
        raise ValueError('内容库目录缺失或为符号链接。')
    logical = allocated = 0
    for root, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            node = Path(root) / name
            value = node.lstat()
            if node.is_symlink():
                raise ValueError('内容库存储路径含符号链接；未执行删除。')
            if node.is_file():
                if value.st_nlink != 1:
                    raise ValueError('内容库含外部硬链接；未执行删除。')
                logical += value.st_size
                allocated += value.st_blocks * 512
    return logical, allocated


def _plan_identity(plan):
    return hashlib.sha256(json.dumps({key: value for key, value in plan.items() if key != 'id'},
                                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:32]


def store_layout(path):
    """Allocation/layout changes matter even when the set of Git objects is unchanged."""
    sizes(path)
    return [(p.relative_to(path).as_posix(), s.st_size, s.st_blocks, s.st_mtime_ns, s.st_ino)
            for p in sorted(Path(path).rglob('*')) if p.is_file()
            for s in [p.stat()]]


class VersionDeletion:
    def __init__(self, directory, projects):
        self.directory = Path(directory) / 'version-deletions'
        self.projects, self.store = projects, projects.folders

    def _state(self):
        _Boundary(self.store.path, None).common()
        sizes(self.store.path)
        config = (self.store.path / 'config').read_bytes()
        if len(config) > 1024 * 1024 or re.search(br'(?im)^\s*\[\s*(?:include|includeif|extensions|remote)\b', config):
            raise ValueError('内容库有外部配置或扩展，无法确认本地回收范围。')
        # Incomplete swaps block further mutations. They never initialize an
        # empty replacement and never automatically purge retained diagnostics.
        pending = read_json(self.store.directory / 'delete-transaction.json')
        if pending and pending.get('state') not in ('complete', 'rolled_back'):
            raise ValueError('上次版本删除尚未完成；保留库和事务回执，须先处理该事务。')
        records = {r['id']: r for r in self.projects.records() if r.get('kind') == 'folder'}
        catalog = {key: self.store.versions(key) for key in records}
        stored = self.store.catalog()
        if stored is not None and set(stored) - set(records):
            raise ValueError('内容库有未注册项目；不能确认共享内容的全部引用。')
        refs = Repository(self.store.path).refs()
        expected = {}
        for key, versions in catalog.items():
            if versions:
                expected['refs/heads/folders/' + key] = versions[0]
            if stored is not None:
                expected.update(('refs/reprise/snapshots/' + key + '/' + s, s) for s in versions)
        if {r['name']: r['sha'] for r in refs} != expected:
            raise ValueError('内容库引用与快照目录不一致或有未知引用；未执行删除。')
        if (self.store.path / 'logs').exists() and any(p.is_file() for p in (self.store.path / 'logs').rglob('*')):
            raise ValueError('内容库存在额外 reflog 引用；未执行删除。')
        manifests, commits = {}, {}
        for key, versions in catalog.items():
            repository = self.store.repository(records[key])
            for sha in versions:
                manifests[(key, sha)] = repository.manifest(sha)
                commits[(key, sha)] = repository._history(sha, 1, 0, [], True)['commits'][0]
        repository = Repository(self.store.path)
        known = self._closure(repository, [s for values in catalog.values() for s in values])
        all_objects = dict(row.split() for row in repository._run(
            'cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype)').decode().splitlines())
        # Failed-save diagnostics and previously unreferenced objects are not
        # implicitly selected by this operation. Preserve their closures too.
        protected = set(all_objects) - known
        for oid in tuple(protected):
            if all_objects[oid] in ('commit', 'tree'):
                protected.update(repository._run('rev-list', '--objects', '--no-object-names', oid).decode().splitlines())
        fingerprint = hashlib.sha256(json.dumps([catalog, refs, manifests and [
            [key, sha, value] for (key, sha), value in sorted(manifests.items())], all_objects,
            hashlib.sha256(config).hexdigest(), store_layout(self.store.path),
            PACK_OPTIONS, PACK_CONFIG, self.store.run('--version')], sort_keys=True).encode()).hexdigest()
        return records, catalog, manifests, commits, fingerprint, protected, all_objects

    @staticmethod
    def _closure(repository, shas, cancel=None):
        result = set(shas)
        for sha in shas:
            check(cancel)
            result.add(repository._run('rev-parse', sha + '^{tree}').decode().strip())
            rows = repository._run('ls-tree', '-r', '-t', '-z', sha).split(b'\0')
            result.update(row.split(b'\t', 1)[0].split()[2].decode() for row in rows if row)
        return result

    def plan(self, identifier, shas):
        record = self.projects.record(identifier)
        if record.get('kind') != 'folder':
            raise ValueError('只能删除 Reprise 受管文件夹版本；外部 Git 和旧归档保持只读。')
        if (not isinstance(shas, list) or not 1 <= len(shas) <= 200 or
                any(not isinstance(s, str) or not re.fullmatch('[0-9a-f]{40}', s) for s in shas)):
            raise ValueError('请选择 1–200 个完整 SHA 的已保存版本。')
        with content_access(self.store.directory):
            records, catalog, manifests, commits, fingerprint, protected, all_objects = self._state()
            selected = list(dict.fromkeys(shas))
            if any(s not in catalog[identifier] for s in selected):
                raise ValueError('所选版本已删除或不属于该项目。')
            selected_keys = {(identifier, s) for s in selected}
            retained_oids = protected | {e['oid'] for key, m in manifests.items() if key not in selected_keys
                                        for e in m['entries'].values() if 'oid' in e}
            unique, shared, unique_objects, shared_objects, versions = [], [], {}, {}, []
            for sha in selected:
                manifest = manifests[(identifier, sha)]
                files = [(p, e) for p, e in manifest['entries'].items() if 'oid' in e]
                versions.append({'sha': sha, 'title': commits[(identifier, sha)]['subject'],
                                 'files': len(files), 'logical_bytes': sum(e['size'] for _, e in files)})
                for path, entry in files:
                    item = {'sha': sha, 'path': path, 'size': entry['size']}
                    if entry['oid'] in retained_oids:
                        shared.append(item); shared_objects[entry['oid']] = entry['size']
                    else:
                        unique.append(item); unique_objects[entry['oid']] = entry['size']
            result = {'id': secrets.token_hex(16), 'created_at': now(), 'project_id': identifier,
                      'fingerprint': fingerprint, 'selected_shas': selected, 'selected_versions': versions,
                      'unique_files': unique[:100], 'unique_file_count': len(unique),
                      'shared_files': shared[:100], 'shared_file_count': len(shared),
                      'unique_content_bytes': sum(unique_objects.values()),
                      'shared_content_bytes': sum(shared_objects.values()),
                      'estimated_reclaim_bytes': sum(unique_objects.values()),
                      'estimate_kind': 'unique_uncompressed_content', 'history_state_loss': True,
                      'retained_versions': sum(map(len, catalog.values())) - len(selected),
                      'project_versions_before': len(catalog[identifier]),
                      'project_versions_retained': len(catalog[identifier]) - len(selected),
                      'other_versions_retained': sum(len(v) for k, v in catalog.items() if k != identifier),
                      'other_projects_protected': len([k for k, v in catalog.items() if k != identifier and v]),
                      'source_files_removed': False, 'blockers': [],
                      'diagnostic_objects_protected': len(protected),
                      'warnings': ['删除会永久失去这些版本的文件组合、路径和元数据，即使独占内容为零。',
                                   '独占内容为未压缩逻辑量；实际回收受压缩、索引和文件系统影响。',
                                   '原文件夹、已有恢复副本、截图、运行目录和日志均保留，未计入回收。',
                                   '同一磁盘的历史不能替代异地或其他介质备份。']}
            result['id'] = _plan_identity(result)
            write_json(self.directory / (result['id'] + '.plan.json'), result, private=True)
            return result

    def _load_plan(self, identifier, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch('[0-9a-f]{32}', plan_id):
            raise ValueError('删除计划标识无效。')
        plan = read_json(self.directory / (plan_id + '.plan.json'), required=True)
        if plan.get('restored_review_required'):
            raise ValueError('此计划来自备份中的历史状态；请在当前库重新预检。')
        if plan.get('id') != plan_id or _plan_identity(plan) != plan_id:
            raise ValueError('删除计划内容已改变；请重新预检。')
        if plan['project_id'] != identifier:
            raise ValueError('删除计划不属于此项目。')
        return plan

    @staticmethod
    def _retained(catalog, plan):
        selected = set(plan['selected_shas'])
        return {key: [s for s in values if key != plan['project_id'] or s not in selected]
                for key, values in catalog.items()}

    @staticmethod
    def _metadata(replacement, retained, protected, all_objects):
        if any(not isinstance(key, str) or not re.fullmatch('[0-9a-f]{20}', key) or
               any(not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha) for sha in versions)
               for key, versions in retained.items()):
            raise ValueError('替换库项目标识或版本 SHA 无效；未写入引用。')
        write_json(replacement.path / 'reprise-snapshots.json', retained, private=True)
        boundaries = [sha for values in retained.values() for sha in values]
        boundaries += [oid for oid in protected if all_objects.get(oid) == 'commit']
        if boundaries:
            (replacement.path / 'shallow').write_text('\n'.join(sorted(set(boundaries))) + '\n')
        # Loose-ref bytes are identical in measurement and the real new store.
        # This is an unregistered replacement only; fsck verifies real builds.
        for key, versions in retained.items():
            refs = [('refs/heads/folders/' + key, versions[0])] if versions else []
            refs += [('refs/reprise/snapshots/' + key + '/' + sha, sha) for sha in versions]
            for name, sha in refs:
                path = replacement.path / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(sha + '\n')

    def _build_replacement(self, staging, records, retained, protected, all_objects, cancel=None):
        """Build and verify, without installing or removing the original store."""
        check(cancel)
        staging.mkdir(parents=True, mode=0o700, exist_ok=False)
        replacement = FolderStore(staging)
        replacement.ensure()
        objects = protected | self._closure(Repository(self.store.path),
                    [s for values in retained.values() for s in values], cancel)
        if objects:
            self.store.run('pack-objects', *PACK_OPTIONS, str(replacement.path / 'objects/pack/pack'),
                           input=('\n'.join(sorted(objects)) + '\n').encode(), config=PACK_CONFIG)
        check(cancel)
        self._metadata(replacement, retained, protected, all_objects)
        replacement.run('fsck', '--full', '--strict')
        proxy = SimpleNamespace(folders=replacement, record=lambda key: records[key])
        for key, versions in retained.items():
            for sha in versions:
                check(cancel)
                verify_project(proxy, key, sha)
        sizes(replacement.path)
        return replacement

    def _measure_replacement(self, directory, retained, protected, all_objects, cancel=None):
        check(cancel)
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        replacement = FolderStore(directory)
        replacement.ensure()
        objects = protected | self._closure(Repository(self.store.path),
                    [s for values in retained.values() for s in values], cancel)
        packed = stream_pack(self.store, objects, directory / 'stream', cancel)
        self._metadata(replacement, retained, protected, all_objects)
        metadata, metadata_allocated = sizes(replacement.path)
        space = os.statvfs(directory)
        block = space.f_frsize or space.f_bsize
        rounded = lambda value: ((value + block - 1) // block) * block if value else 0
        return dict(packed,
            store_bytes_min=metadata + packed['pack_bytes'] + packed['index_bytes_min'],
            store_bytes_max=metadata + packed['pack_bytes'] + packed['index_bytes_max'],
            allocated_bytes_min=metadata_allocated + rounded(packed['pack_bytes']) + rounded(packed['index_bytes_min']),
            allocated_bytes_max=metadata_allocated + rounded(packed['pack_bytes']) + rounded(packed['index_bytes_max']),
            metadata_bytes=metadata, allocation_unit_bytes=block)

    def estimate(self, identifier, plan_id, cancel=None):
        """Stream a baseline and two selected-set packs, without deleting anything."""
        plan = self._load_plan(identifier, plan_id)
        started = time.monotonic()
        with content_access(self.store.directory):
            check(cancel)
            pending = read_json(self.store.directory / 'snapshot-transaction.json')
            if pending and pending.get('state') not in ('complete', 'rolled_back'):
                raise ValueError('保存事务尚未恢复一致；请先查看历史，之后重新预检。')
            records, catalog, _, _, fingerprint, protected, all_objects = self._state()
            if plan['fingerprint'] != fingerprint:
                raise ValueError('内容库已改变，估算计划已失效；请重新预检。')
            before, allocated = sizes(self.store.path)
            free_before = shutil.disk_usage(self.store.directory).free
            # Streaming retains OIDs and metadata, not full compressed libraries.
            # A conservative budget for three sets of refs and diagnostic files.
            budget = 1024 * 1024 + len(all_objects) * 512
            if free_before < budget + 8 * 1024 * 1024:
                raise ValueError('可用空间不足以保留估算记录；原内容库未修改。')
            identifier_estimate = secrets.token_hex(16)
            parent = self.directory / 'estimates'
            if self.directory.is_symlink() or parent.is_symlink():
                raise ValueError('估算记录路径不能是符号链接。')
            directory = parent / identifier_estimate
            directory.mkdir(parents=True, mode=0o700, exist_ok=False)
            try:
                retained = self._retained(catalog, plan)
                baseline = self._measure_replacement(directory / 'baseline', catalog, protected, all_objects, cancel)
                runs = [self._measure_replacement(directory / ('selection-%d' % n), retained,
                                                  protected, all_objects, cancel) for n in (1, 2)]
                check(cancel)
                if self._state()[4] != fingerprint:
                    raise ValueError('估算期间内容库发生变化；结果作废，请重新预检。')
                lower = before - max(r['store_bytes_max'] for r in runs)
                upper = before - min(r['store_bytes_min'] for r in runs)
                result = dict(id=identifier_estimate, plan_id=plan_id, project_id=identifier,
                    status='complete', completed_at=now(), fingerprint=fingerprint,
                    method='streamed-pack-and-v2-index', git_version=self.store.run('--version'),
                    pack_options=PACK_OPTIONS, pack_config=PACK_CONFIG,
                    selected_shas=plan['selected_shas'], unique_content_bytes=plan['unique_content_bytes'],
                    current_store_bytes=before, current_allocated_bytes=allocated,
                    estimated_store_reduction_min_bytes=lower, estimated_store_reduction_max_bytes=upper,
                    estimated_allocated_reduction_min_bytes=allocated - max(r['allocated_bytes_max'] for r in runs),
                    estimated_allocated_reduction_max_bytes=allocated - min(r['allocated_bytes_min'] for r in runs),
                    baseline_compaction_min_bytes=before - baseline['store_bytes_max'],
                    baseline_compaction_max_bytes=before - baseline['store_bytes_min'],
                    selection_incremental_min_bytes=baseline['store_bytes_min'] - max(r['store_bytes_max'] for r in runs),
                    selection_incremental_max_bytes=baseline['store_bytes_max'] - min(r['store_bytes_min'] for r in runs),
                    observed_repeat_spread_bytes=max(r['store_bytes_min'] for r in runs) - min(r['store_bytes_min'] for r in runs),
                    runs=runs, baseline=baseline, source_store_unchanged=True,
                    actual_deletion_error_bytes=None, physical_free_delta_estimate_bytes=None,
                    physical_free_delta_error_bytes=None, full_simulation_pack_saved=False,
                    artifact_directory=str(directory), report_path=str(directory / 'report.json'),
                    seconds=round(time.monotonic() - started, 3),
                    limitations=['The range is a packing/index model, not a statistical confidence interval.',
                                 'A repeat spread of zero is not zero error against an actual deletion.',
                                 'Allocation models round regular pack and index files to the current filesystem unit; directories, shared blocks, snapshots and filesystem compression are not modeled.',
                                 'Volume free-space change and error against actual deletion remain unknown.',
                                 'Above a 2 GiB pack, v2 index large-offset entries use conservative bounds.',
                                 'Diagnostic records remain saved; jobs and plan records are additional uncounted overhead.',
                                 'Packing uses one thread and a 64 MiB delta window, not a total memory guarantee.',
                                 'Every source library, original file, snapshot and environment remains saved.'])
                # Account for the retained report itself; converge its serialized length.
                for _ in range(6):
                    old = result.get('retained_artifact_bytes')
                    write_json(directory / 'report.json', result, private=True)
                    cost, blocks = sizes(directory)
                    result.update(retained_artifact_bytes=cost, retained_artifact_allocated_bytes=blocks,
                                  modeled_net_reduction_after_records_min_bytes=lower-cost,
                                  modeled_net_reduction_after_records_max_bytes=upper-cost)
                    if old == cost:
                        break
                write_json(directory / 'report.json', result, private=True)
                return result
            except Exception as error:
                write_json(directory / 'failure.json', dict(error=str(error), plan_id=plan_id,
                           completed_at=now(), artifacts_retained=True), private=True)
                raise

    def execute(self, identifier, plan_id, confirm=False):
        if confirm is not True:
            raise ValueError('请明确确认所选版本删除影响后再执行。')
        plan = self._load_plan(identifier, plan_id)
        receipt_path = self.directory / (plan_id + '.receipt.json')
        with content_access(self.store.directory):
            transaction_path = self.store.directory / 'delete-transaction.json'
            interrupted = read_json(transaction_path)
            previous = read_json(receipt_path)
            if previous and previous.get('status') == 'verified':
                if interrupted and interrupted.get('id') == plan_id and interrupted.get('state') != 'complete':
                    interrupted['state'] = 'complete'
                    write_json(transaction_path, interrupted, private=True)
                return previous
            if interrupted and interrupted.get('id') == plan_id and interrupted.get('state') not in ('complete', 'rolled_back'):
                retired = self.store.directory / ('retired-' + plan_id + '.git')
                if interrupted['retired'] != str(retired):
                    raise ValueError('事务路径不一致，未继续删除。')
                if interrupted['state'] in ('installed', 'reclaiming'):
                    return self._finish(plan, interrupted, transaction_path)
                # An interruption between renames has no durable install
                # receipt. Restore the old store before accepting a new plan.
                replacement_path = self.directory / (plan_id + '.staging/content/objects.git')
                if retired.exists():
                    if self.store.path.exists():
                        if replacement_path.exists():
                            raise ValueError('事务目录状态不明确；保留全部目录，未继续。')
                        os.replace(self.store.path, replacement_path)
                    os.replace(retired, self.store.path)
                interrupted['state'] = 'rolled_back'
                write_json(transaction_path, interrupted, private=True)
                raise ValueError('已恢复中断前的完整内容库；请重新预检。原诊断保留。')
            records, catalog, manifests, _, fingerprint, protected, all_objects = self._state()
            if fingerprint != plan['fingerprint']:
                raise ValueError('内容库已改变，删除计划已失效；请重新预检。')
            retained = self._retained(catalog, plan)
            # Preflight checks all surviving snapshots, including other projects.
            for key, versions in retained.items():
                for sha in versions:
                    verify_project(self.projects, key, sha)
            before, before_allocated = sizes(self.store.path)
            free_before = shutil.disk_usage(self.store.directory).free
            staging = self.directory / (plan_id + '.staging')
            if staging.exists():
                raise ValueError('此计划已有未完成诊断目录；请重新预检，原诊断保留。')
            replacement = self._build_replacement(staging, records, retained, protected, all_objects)
            _sync_store(replacement.path)
            retired = self.store.directory / ('retired-' + plan_id + '.git')
            transaction = {'id': plan_id, 'state': 'prepared', 'replacement': str(replacement.path),
                           'retired': str(retired), 'selected_shas': plan['selected_shas'],
                           'receipt_path': str(receipt_path), 'created_at': now(),
                           'retained': retained, 'store_bytes_before': before,
                           'allocated_bytes_before': before_allocated, 'volume_free_before': free_before}
            write_json(transaction_path, transaction, private=True)
            _sync_directory(transaction_path.parent)
            installed = False
            try:
                os.replace(self.store.path, retired)
                os.replace(replacement.path, self.store.path)
                installed = True
                _sync_directory(self.store.directory)
                transaction['state'] = 'installed'
                write_json(transaction_path, transaction, private=True)
                _sync_directory(transaction_path.parent)
                self.store.run('fsck', '--full', '--strict')
                for key, versions in retained.items():
                    for sha in versions:
                        verify_project(self.projects, key, sha)
            except BaseException:
                if retired.exists():
                    if installed:
                        os.replace(self.store.path, replacement.path)
                    os.replace(retired, self.store.path)
                transaction['state'] = 'rolled_back'
                write_json(transaction_path, transaction, private=True)
                raise
            return self._finish(plan, transaction, transaction_path)

    def _finish(self, plan, transaction, transaction_path):
        """Recheck and resume only this explicitly confirmed transaction."""
        if self.store.catalog() != transaction['retained']:
            raise ValueError('已安装快照目录与事务不一致；未回收旧库。')
        self.store.run('fsck', '--full', '--strict')
        _sync_store(self.store.path)
        count = 0
        for key, versions in transaction['retained'].items():
            for sha in versions:
                verify_project(self.projects, key, sha)
                count += 1
        retired = self.store.directory / ('retired-' + plan['id'] + '.git')
        if retired.exists():
            sizes(retired)
            transaction['state'] = 'reclaiming'
            write_json(transaction_path, transaction, private=True)
            _sync_directory(transaction_path.parent)
            shutil.rmtree(retired)
            _sync_directory(self.store.directory)
        self.store.run('fsck', '--full', '--strict')
        after, after_allocated = sizes(self.store.path)
        result = {'id': plan['id'], 'status': 'verified', 'completed_at': now(),
                  'project_id': plan['project_id'], 'selected_shas': plan['selected_shas'],
                  'deleted_versions': len(plan['selected_shas']), 'retained_versions_verified': count,
                  'unique_content_bytes': plan['unique_content_bytes'],
                  'store_bytes_before': transaction['store_bytes_before'], 'store_bytes_after': after,
                  'store_bytes_reclaimed': transaction['store_bytes_before'] - after,
                  'allocated_bytes_reclaimed': transaction['allocated_bytes_before'] - after_allocated,
                  'volume_free_delta': shutil.disk_usage(self.store.directory).free - transaction['volume_free_before'],
                  'verification': {'ok': True, 'fsck': True, 'retained_contents': True},
                  'receipt_path': transaction['receipt_path'], 'source_files_removed': False,
                  'evidence_and_runtime_preserved': True}
        write_json(transaction['receipt_path'], result, private=True)
        _sync_directory(Path(transaction['receipt_path']).parent)
        transaction['state'] = 'complete'
        write_json(transaction_path, transaction, private=True)
        _sync_directory(transaction_path.parent)
        return result
