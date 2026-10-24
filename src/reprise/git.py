"""Read-only, repository-independent access to Git's object database.

No checkout, archive filters, hooks, package managers, or fetches are used. Paths
are transported with NUL delimiters and decoded with filesystem surrogateescape.
"""
from __future__ import annotations

import os
import hashlib
import posixpath
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .storage import locked


MAX_OUTPUT = 32 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024 * 1024

# No includes, command drivers, hooks, fsmonitor, or repository-location settings
# enter the isolated status repository. These scalar settings preserve native Git
# comparisons (including CRLF and working-tree-encoding) and ignore/rename rules.
_STATUS_CONFIG = frozenset('''core.filemode core.ignorecase core.precomposeunicode
    core.symlinks core.trustctime core.checkstat core.ignorestat core.autocrlf
    core.eol core.safecrlf core.checkroundtripencoding core.attributesfile
    core.excludesfile core.protecthfs core.protectntfs core.sparsecheckout
    core.sparsecheckoutcone index.sparse status.renames status.renamelimit
    diff.renames diff.renamelimit'''.split())


def _decode(value: bytes) -> str:
    return value.decode('utf-8', 'surrogateescape')


def _environment():
    # Explicit repository selection must not inherit another caller's Git index,
    # object directory, config injection, or worktree environment.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
               GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               LC_ALL='C')
    if env.get('REPRISE_BUNDLE_RESOURCES'):
        from .desktop_bundle import git_exec_path
        env['GIT_EXEC_PATH'] = git_exec_path(env['REPRISE_BUNDLE_RESOURCES'])
    return env


def _safe_path(path: str) -> str:
    if not isinstance(path, str) or not path or '\0' in path or path.startswith('/'):
        raise ValueError('Expected a relative Git file path')
    parts = path.split('/')
    if any(p in ('', '.', '..') or p.casefold() == '.git' for p in parts):
        raise ValueError('Unsafe Git path: %r' % path)
    return path


class Repository:
    """A normal checkout, linked worktree, or bare Git repository."""

    def __init__(self, path, *, status_directory=None):
        supplied = Path(path).expanduser().resolve()
        if not supplied.is_dir():
            raise ValueError('Repository directory does not exist: %s' % supplied)
        self.path = supplied
        self.status_directory = Path(status_directory) if status_directory is not None else (
            Path(tempfile.gettempdir()) / ('reprise-git-status-%s' % os.getuid()))
        try:
            git_dir = self._run('rev-parse', '--absolute-git-dir')[:-1]
            self.git_dir = Path(os.fsdecode(git_dir)).resolve()
            self.bare = self._run('rev-parse', '--is-bare-repository').strip() == b'true'
            self.work_tree = None if self.bare else Path(os.fsdecode(
                self._run('rev-parse', '--show-toplevel')[:-1])).resolve()
            self.path = self.git_dir if self.bare else self.work_tree
        except (ValueError, OSError) as exc:
            raise ValueError('Not a readable Git repository: %s (%s)' % (supplied, exc)) from exc

    def _command(self, *args):
        return ['git', '--no-pager', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                '-c', 'core.untrackedCache=false', '-c', 'core.quotePath=false',
                '-c', 'diff.external=', '-c', 'log.showSignature=false', '-C', str(self.path), *args]

    def _run(self, *args, input=None, max_output=MAX_OUTPUT, timeout=45):
        """Bound memory/output and time, including for unusual Git metadata."""
        with tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(self._command(*args), stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=errors, env=_environment())
            except OSError as exc:
                raise ValueError('Git is unavailable: %s' % exc) from exc
            timed_out = threading.Event()
            def expire():
                timed_out.set()
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            timer = threading.Timer(timeout, expire)
            timer.daemon = True
            timer.start()
            try:
                if input is not None:
                    process.stdin.write(input)
                    process.stdin.close()
                output = process.stdout.read(max_output + 1)
                if len(output) > max_output:
                    process.kill()
                    raise ValueError('Git result exceeds the %d-byte safety limit' % max_output)
                code = process.wait()
                if timed_out.is_set():
                    raise ValueError('Git operation timed out')
                if code:
                    errors.seek(0)
                    detail = _decode(errors.read(8192)).strip()
                    raise ValueError(detail or 'Git operation failed')
                return output
            finally:
                timer.cancel()
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()

    def resolve(self, revision):
        if (not isinstance(revision, str) or not revision or revision.startswith('-')
                or '\0' in revision or any(ord(c) < 32 for c in revision)):
            raise ValueError('Expected a commit SHA or Git revision')
        value = self._run('rev-parse', '--verify', '--end-of-options', revision + '^{commit}', max_output=1024)
        sha = value.decode('ascii').strip()
        if len(sha) not in (40, 64) or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Revision did not resolve to a commit')
        return sha

    def info(self):
        try:
            head = self.resolve('HEAD')
        except ValueError:
            head = None
        try:
            branch = _decode(self._run('symbolic-ref', '--quiet', '--short', 'HEAD', max_output=4096)).strip()
        except ValueError:
            branch = None
        shallow = self._run('rev-parse', '--is-shallow-repository').strip() == b'true'
        object_format = _decode(self._run('rev-parse', '--show-object-format')).strip()
        try:
            partial = _decode(self._run('config', '--local', '--get', 'extensions.partialclone')).strip() or None
        except ValueError:
            partial = None
        warnings = []
        if shallow:
            warnings.append('Shallow history: some parent commits are unavailable; Reprise never fetches automatically.')
        if partial:
            warnings.append('Partial clone: missing objects may require an explicit Git fetch outside Reprise.')
        return dict(path=str(self.path), git_dir=str(self.git_dir), work_tree=str(self.work_tree) if self.work_tree else None,
                    bare=self.bare, shallow=shallow, head=head, branch=branch, object_format=object_format,
                    partial_clone=partial, warnings=warnings)

    def refs(self):
        data = self._run('for-each-ref', '--format=%(refname)%00%(objectname)%00%(objecttype)%00%(*objectname)%00%(*objecttype)')
        result = []
        for row in data.splitlines():
            name, oid, object_type, peeled, peeled_type = row.split(b'\0')
            name = _decode(name)
            kind = 'branch' if name.startswith('refs/heads/') else 'remote' if name.startswith('refs/remotes/') else 'tag' if name.startswith('refs/tags/') else 'other'
            target = peeled or oid
            target_type = peeled_type or object_type
            # Nested annotated tags need recursive peeling. Non-commit refs still
            # belong in the inventory, but cannot be used as version snapshots.
            if object_type == b'tag':
                try:
                    target = self.resolve(name).encode('ascii')
                    target_type = b'commit'
                except ValueError:
                    pass
            result.append(dict(name=name, sha=target.decode('ascii'), kind=kind,
                               object_sha=oid.decode('ascii'), target_type=target_type.decode('ascii')))
        return result

    def _parents(self, sha):
        data = self._run('cat-file', 'commit', sha, max_output=4 * 1024 * 1024)
        return [line[7:].decode('ascii') for line in data.split(b'\n\n', 1)[0].splitlines() if line.startswith(b'parent ')]

    def history(self, ref='--all', limit=50, offset=0):
        try:
            limit, offset = int(limit), int(offset)
        except (ValueError, TypeError):
            raise ValueError('History limit and offset must be integers')
        if not 1 <= limit <= 200 or not 0 <= offset <= 1000000:
            raise ValueError('History limit must be 1–200 and offset 0–1000000')
        return self._history(ref, limit, offset, self.refs())

    def history_tips(self, tips, limit=2000, *, refs=None, shallow=None):
        """Read each tip once, retaining the same per-tip history boundary.

        A global log limit would let busy branches hide another branch's history.
        Sharing decorations and de-duplicating full SHAs avoids that trade-off.
        """
        if not isinstance(tips, (list, tuple)) or len(tips) > 64:
            raise ValueError('Expected at most 64 history tips')
        if not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError('History tip limit must be 1–2000')
        refs = self.refs() if refs is None else refs
        if shallow is None:
            shallow = self._run('rev-parse', '--is-shallow-repository').strip() == b'true'
        commits, truncated = {}, []
        for tip in dict.fromkeys(tips):
            # Many refs point inside a history we already loaded. Reuse it only
            # when every ancestor is present and the per-tip budget is intact.
            # Missing boundaries or larger ancestry still use Git's own walker.
            pending, seen = [tip], set()
            while pending and len(seen) <= limit:
                sha = pending.pop()
                if sha in seen:
                    continue
                if sha not in commits:
                    break
                seen.add(sha)
                pending.extend(commits[sha]['parents'])
            else:
                if not pending and len(seen) <= limit:
                    continue
            page = self._history(tip, limit, 0, refs, shallow)
            commits.update((item['sha'], item) for item in page['commits'])
            if page['has_more']:
                truncated.append(tip)
        return {'commits': list(commits.values()), 'truncated_tips': truncated}

    def _history(self, ref, limit, offset, refs, shallow=None):
        selection = '--all' if ref == '--all' else self.resolve(ref)
        data = self._run('log', selection, '--topo-order', '-z', '--format=%H%x00%P%x00%s%x00%an%x00%aI%x00%cI',
                         '--max-count=%d' % (limit + 1), '--skip=%d' % offset, '--')
        fields = data.split(b'\0')
        if fields and fields[-1] == b'':
            fields.pop()
        if len(fields) % 6:
            raise ValueError('Unexpected Git log output')
        decorations = {}
        for ref_item in refs:
            decorations.setdefault(ref_item['sha'], []).append(ref_item['name'])
        result = []
        for n in range(0, len(fields), 6):
            sha, parents, subject, author, authored, committed = map(_decode, fields[n:n + 6])
            result.append(dict(sha=sha, parents=parents.split(), subject=subject, author=author,
                               authored_at=authored, committed_at=committed, refs=decorations.get(sha, [])))
        has_more = len(result) > limit
        result = result[:limit]
        # Git's revision walker hides shallow-boundary parents. Read commit
        # headers at these boundaries so parent identity is never fabricated.
        if result and (shallow if shallow is not None else
                       self._run('rev-parse', '--is-shallow-repository').strip() == b'true'):
            for item in result:
                if not item['parents']:
                    item['parents'] = self._parents(item['sha'])
        return dict(commits=result, has_more=has_more, next_offset=offset + len(result) if has_more else None)

    def tree(self, revision):
        sha = self.resolve(revision)
        data = self._run('ls-tree', '-r', '-z', '-l', '--full-tree', sha, '--')
        result = []
        for record in data.split(b'\0'):
            if not record:
                continue
            info, path = record.split(b'\t', 1)
            mode, kind, oid, size = info.split()
            result.append(dict(path=os.fsdecode(path), mode=mode.decode('ascii'), type=kind.decode('ascii'),
                               oid=oid.decode('ascii'), size=None if size == b'-' else int(size)))
        return result

    def blob(self, revision, path, max_bytes=1048576):
        sha = self.resolve(revision)
        path = _safe_path(path)
        if not isinstance(max_bytes, int) or not 0 <= max_bytes <= MAX_OUTPUT:
            raise ValueError('Blob limit must be between 0 and %d bytes' % MAX_OUTPUT)
        entry = self._run('ls-tree', '-r', '-z', '-l', '--full-tree', sha, '--', ':(literal)' + path)
        rows = [row for row in entry.split(b'\0') if row]
        if len(rows) != 1:
            raise ValueError('File not present at this revision: %s' % path)
        header, found = rows[0].split(b'\t', 1)
        mode, kind, oid, size = header.split()
        if os.fsdecode(found) != path or kind != b'blob':
            raise ValueError('Path is not a Git blob: %s' % path)
        if int(size) > max_bytes:
            raise ValueError('File exceeds the %d-byte read limit: %s' % (max_bytes, path))
        return self._run('cat-file', 'blob', oid.decode('ascii'), max_output=max_bytes)

    def diff(self, target, base=None):
        target = self.resolve(target)
        parents = self._parents(target)
        base = self.resolve(base) if base is not None else (parents[0] if parents else None)
        if base:
            # Verification gives an actionable error for unavailable shallow parents.
            base = self.resolve(base)
            data = self._run('diff', '--no-ext-diff', '--no-textconv', '--name-status', '-z', '-M', base, target, '--')
        else:
            data = self._run('diff-tree', '--root', '--no-commit-id', '--no-ext-diff', '--no-textconv',
                             '--name-status', '-z', '-r', '-M', target, '--')
        fields = data.split(b'\0')
        if fields and fields[-1] == b'':
            fields.pop()
        files, counts, n = [], {'added': 0, 'modified': 0, 'deleted': 0, 'renamed': 0, 'copied': 0, 'type_changed': 0, 'other': 0}, 0
        keys = {'A': 'added', 'M': 'modified', 'D': 'deleted', 'R': 'renamed', 'C': 'copied', 'T': 'type_changed'}
        while n < len(fields):
            status_text = fields[n].decode('ascii')
            n += 1
            if status_text[0] in ('R', 'C'):
                old, path = fields[n:n + 2]
                n += 2
                item = dict(status=status_text, path=os.fsdecode(path), old_path=os.fsdecode(old))
            else:
                item = dict(status=status_text, path=os.fsdecode(fields[n]))
                n += 1
            files.append(item)
            counts[keys.get(status_text[0], 'other')] += 1
        counts['total'] = len(files)
        return dict(target=target, base=base, parents=parents, files=files, counts=counts)

    def _git_path(self, name):
        value = self._run('rev-parse', '--git-path', name)[:-1]
        return (self.path / os.fsdecode(value)).resolve()

    def _status_view(self):
        # A per-driver override has a race: another driver can be added between
        # enumeration and `status`. Instead snapshot only safe config values and
        # execute status with a separate git-dir that cannot read source config.
        raw = self._run('config', '--null', '--list', '--includes')
        values, filters = {}, set()
        for entry in raw.split(b'\0'):
            key, separator, value = entry.partition(b'\n')
            name = _decode(key)
            if name in _STATUS_CONFIG:
                values[name] = _decode(value) if separator else None
            elif name.startswith('filter.'):
                filters.add(name[len('filter.'):].rsplit('.', 1)[0])
        object_format = self._run('rev-parse', '--show-object-format').strip()
        if object_format not in (b'sha1', b'sha256'):
            raise ValueError('Unsupported Git object format for status')
        config = '[core]\nrepositoryFormatVersion = %s\nbare = false\n' % (1 if object_format == b'sha256' else 0)
        if object_format == b'sha256':
            config += '[extensions]\nobjectFormat = sha256\n'
        for key, value in sorted(values.items()):
            section, name = key.split('.')
            config += '[%s]\n%s' % (section, name)
            if value is not None:
                escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t').replace('\b', '\\b')
                config += ' = "' + escaped + '"'
            config += '\n'
        try:
            head = self.resolve('HEAD').encode('ascii') + b'\n'
        except ValueError:
            # Unborn repositories have a valid symbolic HEAD but no referenced
            # commit. A corrupt/detached HEAD must still fail explicitly.
            reference = self._run('symbolic-ref', '--quiet', 'HEAD').strip()
            if self._run('for-each-ref', '--format=%(refname)', os.fsdecode(reference)).strip():
                raise ValueError('The repository HEAD cannot be read')
            head = b'ref: refs/heads/unborn\n'
        files = {'config': config.encode('utf-8', 'surrogateescape'), 'HEAD': head}
        index_path = self._git_path('index')
        index_mtime = None
        remaining = MAX_OUTPUT

        def copy_input(name, path):
            nonlocal remaining, index_mtime
            try:
                with path.open('rb') as stream:
                    stamp = os.fstat(stream.fileno())
                    content = stream.read(remaining + 1)
            except FileNotFoundError:
                return
            if len(content) > remaining:
                raise ValueError('Git status metadata exceeds the %d-byte safety limit' % MAX_OUTPUT)
            remaining -= len(content)
            files[name] = content
            if name == 'index':
                index_mtime = stamp.st_mtime_ns

        copy_input('index', index_path)
        # Split-index links are relative to the index directory. Copy all retained
        # shared indexes so a concurrent source-index replacement can only fail
        # closed, never cause Git to refresh a shared index in the source.
        for shared in sorted(index_path.parent.glob('sharedindex.*')):
            copy_input(shared.name, shared)
        for name in ('info/attributes', 'info/exclude', 'info/sparse-checkout'):
            copy_input(name, self._git_path(name))
        objects = self._git_path('objects')
        common = (self.path / os.fsdecode(self._run('rev-parse', '--git-common-dir')[:-1])).resolve()
        digest = hashlib.sha256()
        for value in (str(self.work_tree), str(objects), str(index_mtime)):
            encoded = os.fsencode(value)
            digest.update(len(encoded).to_bytes(8, 'big') + encoded)
        for name, value in sorted(files.items()):
            digest.update(name.encode('ascii') + b'\0' + len(value).to_bytes(8, 'big') + value)
        cache = self.status_directory.expanduser().resolve()
        for protected in (self.work_tree, self.git_dir, common, objects):
            if protected and (cache == protected or protected in cache.parents):
                raise ValueError('Status metadata must be outside the source repository')
        if self.status_directory.is_symlink():
            raise ValueError('Status metadata directory cannot be a symlink')
        cache.mkdir(parents=True, mode=0o700, exist_ok=True)
        stat = cache.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError('Status metadata directory must be private to the current user')
        view = cache / digest.hexdigest()
        with locked(cache / '.lock'):
            if not view.exists():
                pending = Path(tempfile.mkdtemp(prefix='.' + view.name + '-', dir=cache))
                for name, content in files.items():
                    destination = pending / name
                    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(content)
                if index_mtime is not None:
                    os.utime(pending / 'index', ns=(index_mtime, index_mtime))
                (pending / 'refs' / 'heads').mkdir(parents=True, mode=0o700)
                # Only raw objects/alternates are shared; no source configuration
                # or index is reachable as metadata of the isolated repository.
                (pending / 'objects').symlink_to(objects, target_is_directory=True)
                pending.rename(view)
            if view.is_symlink() or (view / 'commondir').exists() or (view / 'objects').resolve() != objects:
                raise ValueError('Retained Git status metadata has been altered')
            for name, content in files.items():
                candidate = view / name
                if candidate.is_symlink() or candidate.read_bytes() != content:
                    raise ValueError('Retained Git status metadata has been altered')
        return view, sorted(filters)

    def status(self):
        if self.bare:
            return dict(available=False, dirty=False, changes=[], reason='Bare repositories do not have a worktree')
        view, filters = self._status_view()
        data = self._run('--git-dir', str(view), '--work-tree', str(self.work_tree),
                         'status', '--porcelain=v1', '-z', '--untracked-files=normal', '--ignore-submodules=dirty')
        records = data.split(b'\0')
        changes, i = [], 0
        while i < len(records) and records[i]:
            record = records[i]
            status_text, path = record[:2].decode('ascii'), os.fsdecode(record[3:])
            change = dict(path=path, status=status_text)
            i += 1
            if 'R' in status_text or 'C' in status_text:
                change['old_path'] = os.fsdecode(records[i])
                i += 1
            changes.append(change)
        return dict(available=True, dirty=bool(changes), changes=changes,
                    submodule_worktree_changes_included=False,
                    filters_executed=False,
                    disabled_filters=filters, status_metadata=str(view),
                    note='Nested submodule worktree modifications are not scanned.' +
                    (' External clean/process filters are disabled; filtered worktree files are compared without their custom conversion and may appear modified.' if filters else ''))

    def materialize(self, revision, destination, cancel=None, paths=None, max_bytes=MAX_SNAPSHOT_BYTES):
        from .cancellation import check
        check(cancel)
        sha = self.resolve(revision)
        requested = Path(destination).expanduser()
        if os.path.lexists(requested):
            raise ValueError('Snapshot destination already exists; existing files are never overwritten')
        destination = requested.resolve()
        for protected in (self.work_tree, self.git_dir):
            if protected and (destination == protected or protected in destination.parents):
                raise ValueError('Snapshot destination must be outside the source repository')
        if os.path.lexists(destination):
            raise ValueError('Snapshot destination already exists; existing files are never overwritten')
        entries = self.tree(sha)
        if paths is not None:
            if not isinstance(paths, list) or not 1 <= len(paths) <= 200:
                raise ValueError('Select 1–200 relative file or directory paths')
            paths = list(dict.fromkeys(_safe_path(p) for p in paths))
            directories = set(self.empty_directories(sha))
            for selected in paths:
                if (selected not in directories and
                        not any(e['path'] == selected or e['path'].startswith(selected + '/') for e in entries)):
                    raise ValueError('Path not present at this revision: ' + selected)
            entries = [e for e in entries if any(e['path'] == p or e['path'].startswith(p + '/') for p in paths)]
        total = sum(item['size'] or 0 for item in entries)
        if max_bytes is not None and total > max_bytes:
            raise ValueError('Snapshot exceeds the %d-byte extraction limit' % max_bytes)
        ancestor = destination.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        if total > shutil.disk_usage(ancestor).free:
            raise ValueError('Not enough free space to recover the selected contents')
        for item in entries:
            _safe_path(item['path'])
        destination.mkdir(parents=True, exist_ok=False)
        warnings, submodules, lfs, symlinks = [], [], [], []
        files_written = 0
        object_format = self.info()['object_format']
        # A batch process reads immutable raw blobs, bypassing smudge/LFS filters.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(self._command('cat-file', '--batch'), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=errors, env=_environment())
            timeout = threading.Timer(300, process.kill)
            timeout.daemon = True
            timeout.start()
            try:
                for item in entries:
                    check(cancel)
                    path = destination.joinpath(*item['path'].split('/'))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if item['type'] == 'commit':
                        path.mkdir(exist_ok=False)
                        submodules.append(dict(path=item['path'], sha=item['oid']))
                        continue
                    if item['type'] != 'blob':
                        raise ValueError('Unsupported tree entry type: %s' % item['type'])
                    process.stdin.write(item['oid'].encode('ascii') + b'\n')
                    process.stdin.flush()
                    header = process.stdout.readline(256).split()
                    if len(header) != 3 or header[0].decode('ascii') != item['oid'] or header[1] != b'blob' or int(header[2]) != item['size']:
                        raise ValueError('Git blob unavailable: %s' % item['path'])
                    remaining = item['size']
                    object_hash = hashlib.new(object_format)
                    object_hash.update(('blob %d\0' % remaining).encode('ascii'))
                    if item['mode'] == '120000':
                        if remaining > 16384:
                            raise ValueError('Symlink target is too long: %s' % item['path'])
                        target = process.stdout.read(remaining)
                        if len(target) != remaining:
                            raise ValueError('Truncated symlink object')
                        object_hash.update(target)
                        symlinks.append((item['path'], os.fsdecode(target)))
                    else:
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                        with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
                            prefix = b''
                            while remaining:
                                check(cancel)
                                chunk = process.stdout.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise ValueError('Truncated Git object: %s' % item['path'])
                                if len(prefix) < 1024:
                                    prefix += chunk[:1024 - len(prefix)]
                                object_hash.update(chunk)
                                stream.write(chunk)
                                remaining -= len(chunk)
                        path.chmod(0o755 if item['mode'] == '100755' else 0o644)
                        if prefix.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
                            lfs.append(item['path'])
                        files_written += 1
                    if object_hash.hexdigest() != item['oid']:
                        raise ValueError('Git object integrity check failed: %s' % item['path'])
                    if process.stdout.read(1) != b'\n':
                        raise ValueError('Unexpected Git object boundary')
                # Validate all links before creating any. Safe relative links are
                # preserved, and unsafe links cannot become runnable file access.
                link_map = dict(symlinks)
                def validate_link(name, target, visited):
                    if not target or '\0' in target or target.startswith('/') or '\\' in target:
                        raise ValueError('Unsafe/external symlink: %s -> %r' % (name, target))
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                    if resolved == '..' or resolved.startswith('../'):
                        raise ValueError('Symlink escapes the snapshot: %s -> %r' % (name, target))
                    if name in visited:
                        raise ValueError('Cyclic symlink cannot be materialized: %s' % name)
                    visited = visited | {name}
                    parts = resolved.split('/')
                    for index in range(1, len(parts) + 1):
                        prefix = '/'.join(parts[:index])
                        if prefix in link_map:
                            suffix = '/'.join(parts[index:])
                            next_target = link_map[prefix] + ('/' + suffix if suffix else '')
                            validate_link(prefix, next_target, visited)
                            break
                for name, target in symlinks:
                    validate_link(name, target, set())
                for name, target in symlinks:
                    check(cancel)
                    os.symlink(target, destination.joinpath(*name.split('/')))
                    files_written += 1
                process.stdin.close()
                if process.wait(timeout=10):
                    errors.seek(0)
                    raise ValueError(_decode(errors.read(8192)) or 'Git materialization failed')
            finally:
                timeout.cancel()
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
                if not process.stdin.closed:
                    process.stdin.close()
        if submodules:
            warnings.append('Submodules are recorded by commit ID but not fetched or initialized; their directories are empty.')
        if lfs:
            warnings.append('Git LFS pointer files are preserved; external LFS objects are not fetched or substituted.')
        return dict(sha=sha, path=str(destination), files=files_written, bytes=total, warnings=warnings,
                    submodules=submodules, lfs_pointers=lfs, symlinks=[name for name, _ in symlinks],
                    method='git-object-database', filters_executed=False, object_hashes_verified=True)

    def empty_directories(self, revision):
        return []  # Ordinary Git trees cannot represent empty directories.
