"""Read-only accounting of regular-file metadata inside one local data tree.

No registry or file body is read. Directory descriptors and O_NOFOLLOW keep a
replaced child symlink from redirecting traversal outside the selected tree.
"""
import os
from pathlib import Path
import stat

from .cancellation import check


_CATEGORIES = (
    ('content', '内容库'),
    ('recoveries', '恢复副本与导出'),
    ('runtimes', '运行副本'),
    ('environments', '可重建环境'),
    ('evidence', '截图与运行证据'),
    ('state', '登记与其他状态'),
    ('other', '其他'),
)
_STATE_NAMES = frozenset(('ai', 'jobs', 'organization', 'git-status',
                          'named-archives', 'projects.json', 'projects.lock', 'version-deletions', 'folder-imports'))
_MAX_DEPTH = 128
_MAX_LINK_IDENTITIES = 100000
_SAFE_TRAVERSAL = (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
                   and os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
                   and os.scandir in os.supports_fd)


def storage_report(directory, cancel=None):
    """Return schema 1 metadata accounting, without creating even a missing root.

    File counts count directory entries; byte counts count each regular-file
    (device, inode) once. Hard links spanning categories belong to the earliest
    category in _CATEGORIES, independently of traversal order. Unreadable or
    skipped entries make the result partial. Cancellation propagates to jobs.
    """
    root = Path(directory).expanduser().absolute()
    categories = [dict(key=key, label=label, files=0, directories=0, symlinks=0,
                       logical_bytes=0, allocated_bytes=0)
                  for key, label in _CATEGORIES]
    report = dict(schema=1, storage_path=str(root), status='complete',
                  files=0, directories=0, symlinks=0, logical_bytes=0,
                  allocated_bytes=0, filesystem_free_bytes=None,
                  reclaimable_bytes=None, hardlink_aliases=0,
                  categories=categories, warnings=[], limitations=[
                      '只统计明确数据目录中的普通文件元数据；不读取文件正文、登记内容或外部源目录。',
                      '文件数按路径计数；逻辑字节与分配块按设备和 inode 对硬链接去重，跨类别归到固定优先类别。',
                      '字节数不含目录及符号链接自身的元数据；目录数不含数据根目录。',
                      '分配块为 st_blocks × 512 的估计；APFS 克隆、压缩和共享块不能据此推算独占空间。',
                      '可释放量未知；文件系统可用空间来自当前卷，既不是本目录占用，也不是预计回收量。',
                      '扫描非原子；运行期间文件可能变化，报告不提供某个瞬间的一致快照。',
                      '不跟随符号链接，跳过不同设备的嵌套挂载；不能识别同设备的绑定挂载。',
                      '不保存完整路径清单；最多保留 100000 个硬链接身份和 128 层目录，超限返回部分结果。',
                  ])
    warnings = {}
    allocated_totals = [0] * len(categories)
    unknown_allocations = [0] * len(categories)

    def warn(code, message, partial=True):
        if code not in warnings:
            warnings[code] = dict(code=code, message=message, count=0)
            report['warnings'].append(warnings[code])
        warnings[code]['count'] += 1
        if partial:
            report['status'] = 'partial'

    def finish():
        for index, item in enumerate(categories):
            item['allocated_bytes'] = (None if unknown_allocations[index]
                                       else allocated_totals[index])
        for key in ('files', 'directories', 'symlinks', 'logical_bytes'):
            report[key] = sum(item[key] for item in categories)
        allocated = [item['allocated_bytes'] for item in categories]
        report['allocated_bytes'] = (None if any(value is None for value in allocated)
                                     else sum(allocated))
        return report

    def blocks(info):
        value = getattr(info, 'st_blocks', None)
        if value is None:
            warn('allocation_unavailable', '部分平台未提供文件分配块；对应分配空间保持未知。', partial=False)
            return None
        return value * 512

    def add_bytes(index, logical, allocated, sign=1):
        item = categories[index]
        item['logical_bytes'] += sign * logical
        if allocated is None:
            unknown_allocations[index] += sign
        else:
            allocated_totals[index] += sign * allocated

    check(cancel)
    try:
        initial = os.lstat(root)
    except FileNotFoundError:
        warn('missing_directory', '数据目录不存在；没有创建目录。')
        return finish()
    except OSError:
        warn('root_unreadable', '无法读取数据目录元数据。')
        return finish()
    if stat.S_ISLNK(initial.st_mode):
        raise ValueError('数据目录不能是符号链接。')
    if not stat.S_ISDIR(initial.st_mode):
        raise ValueError('数据路径必须是目录。')
    if not _SAFE_TRAVERSAL:
        warn('safe_traversal_unavailable', '当前平台缺少安全的目录描述符遍历能力，未扫描目录。')
        return finish()

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    try:
        root_fd = os.open(root, flags)
    except OSError:
        warn('root_unreadable', '数据目录无法安全打开，可能已变化或没有读取权限。')
        return finish()
    # Only hard-linked files need an identity table. Both this table and open
    # directory depth have explicit limits; wide directories are streamed.
    links = {}
    stack = []
    try:
        try:
            actual = os.fstat(root_fd)
        except OSError:
            warn('root_unreadable', '无法读取已打开数据目录的元数据。')
            return finish()
        if (initial.st_dev, initial.st_ino) != (actual.st_dev, actual.st_ino):
            warn('root_changed', '数据目录在打开期间已变化，未继续扫描。')
            return finish()
        try:
            space = os.fstatvfs(root_fd)
            report['filesystem_free_bytes'] = space.f_bavail * (space.f_frsize or space.f_bsize)
        except OSError:
            warn('filesystem_space_unavailable', '无法读取当前卷的文件系统可用空间。')
        try:
            stack.append((root_fd, os.scandir(root_fd), None))
        except OSError:
            warn('directory_unreadable', '数据目录无法列举，未扫描其中的文件。')
            return finish()
        while stack:
            check(cancel)
            parent_fd, entries, category = stack[-1]
            try:
                entry = next(entries)
            except StopIteration:
                entries.close()
                stack.pop()
                if parent_fd != root_fd:
                    os.close(parent_fd)
                continue
            except OSError:
                warn('directory_unreadable', '部分目录无法完整列举；结果只含已读取的条目。')
                entries.close()
                stack.pop()
                if parent_fd != root_fd:
                    os.close(parent_fd)
                continue
            index = category
            if index is None:
                index = next((i for i, (key, _) in enumerate(_CATEGORIES[:-2]) if entry.name == key),
                             len(_CATEGORIES) - 2 if entry.name in _STATE_NAMES else len(_CATEGORIES) - 1)
            item = categories[index]
            try:
                info = os.stat(entry.name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError:
                warn('metadata_unreadable', '部分条目元数据无法读取；未计入这些条目。')
                continue
            if stat.S_ISLNK(info.st_mode):
                item['symlinks'] += 1
            elif stat.S_ISREG(info.st_mode):
                item['files'] += 1
                if info.st_dev != actual.st_dev:
                    warn('nested_mount_skipped', '跳过不同设备的嵌套挂载；不统计挂载条目内部或内容字节。')
                    continue
                identity = (info.st_dev, info.st_ino)
                allocated = blocks(info)
                previous = links.get(identity)
                if previous is not None:
                    report['hardlink_aliases'] += 1
                    owner, logical, previous_blocks = previous
                    if (info.st_size, allocated) != (logical, previous_blocks):
                        warn('file_changed', '同一硬链接文件的元数据在扫描期间变化；字节采用首次观测。')
                    if index < owner:
                        add_bytes(owner, logical, previous_blocks, -1)
                        add_bytes(index, logical, previous_blocks)
                        links[identity] = (index, logical, previous_blocks)
                    continue
                if info.st_nlink > 1:
                    if len(links) >= _MAX_LINK_IDENTITIES:
                        warn('hardlink_limit_reached', '硬链接身份数量达到安全上限，扫描提前结束；字节只含已统计部分。')
                        return finish()
                    links[identity] = (index, info.st_size, allocated)
                add_bytes(index, info.st_size, allocated)
            elif stat.S_ISDIR(info.st_mode):
                item['directories'] += 1
                if info.st_dev != actual.st_dev:
                    warn('nested_mount_skipped', '跳过不同设备的嵌套挂载；不统计挂载条目内部或内容字节。')
                    continue
                if len(stack) >= _MAX_DEPTH:
                    warn('depth_limit_reached', '目录深度达到安全上限；未继续读取更深层级。')
                    continue
                child_fd = None
                try:
                    child_fd = os.open(entry.name, flags, dir_fd=parent_fd)
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        warn('directory_changed', '部分目录在打开期间变化；未读取替换后的目录。')
                        os.close(child_fd)
                        continue
                    child_entries = os.scandir(child_fd)
                except OSError:
                    if child_fd is not None:
                        os.close(child_fd)
                    warn('directory_unreadable', '部分目录无法安全打开或列举；未统计其中的文件。')
                    continue
                stack.append((child_fd, child_entries, index))
            else:
                warn('special_file_skipped', '跳过非常规文件；这些条目不计入普通文件占用。')
    finally:
        for descriptor, entries, _ in reversed(stack):
            entries.close()
            if descriptor != root_fd:
                os.close(descriptor)
        os.close(root_fd)
    return finish()
