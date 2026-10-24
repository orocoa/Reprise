"""Validate immutable desktop resources and build a private process environment."""
import json
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import zipfile


EXECUTABLES = ('python', 'git', 'node', 'browser')
DIRECTORIES = ('playwright', 'git_exec')
SYSTEM_PATH = ('/usr/bin', '/bin', '/usr/sbin', '/sbin')


def _inside(root, path):
    resolved = path.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise ValueError('Desktop component escapes Resources: ' + str(path))
    return resolved


def _manifest(resources, *, metadata=False):
    root = Path(resources).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Desktop Resources is not a directory')
    path = _inside(root, root / 'runtime' / 'manifest.json')
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Desktop runtime manifest is unavailable or too large')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or type(value.get('schema')) is not int or
            value['schema'] != 1 or not isinstance(value.get('paths'), dict)):
        raise ValueError('Unsupported desktop runtime manifest')
    return root, value if metadata else value['paths']


def video_recording_available(resources):
    """Read one bounded manifest without probing every bundled runtime file."""
    _, value = _manifest(resources, metadata=True)
    capabilities = value.get('capabilities', {})
    if not isinstance(capabilities, dict):
        raise ValueError('Invalid desktop runtime capabilities')
    available = capabilities.get('video_recording', True)
    if type(available) is not bool:
        raise ValueError('Invalid desktop video recording capability')
    # Older bundles without a declaration retain their existing behavior.
    return available


def _component(root, paths, name, directory=False):
    value = paths.get(name)
    if (not isinstance(value, str) or not value or '\0' in value or
            '\\' in value or Path(value).is_absolute() or
            any(part in ('.', '..', '') for part in value.split('/'))):
        raise ValueError('Invalid desktop component path: ' + name)
    resolved = _inside(root, root / value)
    if directory:
        if not resolved.is_dir():
            raise ValueError('Desktop component is not a directory: ' + name)
    elif not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError('Desktop executable is missing or not executable: ' + name)
    # Preserve the declared binary name (for example bin/python3 -> python3.12).
    return str(root / value)


def bundle_paths(resources):
    root, entries = _manifest(resources)
    paths = {name: _component(root, entries, name) for name in EXECUTABLES}
    if 'npm' in entries:
        paths['npm'] = _component(root, entries, 'npm')
    paths.update({name: _component(root, entries, name, directory=True)
                  for name in DIRECTORIES})
    if 'browser_cache' in entries:
        paths['browser_cache'] = _component(
            root, entries, 'browser_cache', directory=True)
    package = _inside(root, Path(paths['playwright']) / 'package.json')
    if not package.is_file():
        raise ValueError('Desktop Playwright package.json is missing')
    # A valid directory entry must not conceal an escaping dependency symlink.
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            candidate = Path(current) / name
            if candidate.is_symlink():
                _inside(root, candidate)
    return root, paths


def git_exec_path(resources):
    """Derive Git's helper path again; never preserve a caller's GIT_EXEC_PATH."""
    root, entries = _manifest(resources)
    return _component(root, entries, 'git_exec', directory=True)


def configure(resources, base_env=None):
    """Return an environment without changing os.environ or any user settings."""
    root, paths = bundle_paths(resources)
    inherited = os.environ if base_env is None else base_env
    blocked = ('PYTHON', 'NODE_', 'GIT_', 'DYLD_', 'LD_', 'PLAYWRIGHT_')
    env = {key: value for key, value in inherited.items()
           if not key.startswith(blocked) and key not in
           ('ELECTRON_RUN_AS_NODE', 'VIRTUAL_ENV', 'CONDA_PREFIX')}
    bins = [str(Path(paths[name]).parent) for name in ('git', 'node', 'python')]
    env.update({
        'PATH': os.pathsep.join(dict.fromkeys([*bins, *SYSTEM_PATH])),
        'REPRISE_BUNDLE_RESOURCES': str(root),
        'REPRISE_NODE': paths['node'],
        'REPRISE_PLAYWRIGHT': paths['playwright'],
        'REPRISE_BROWSER': paths['browser'],
        'GIT_EXEC_PATH': paths['git_exec'],
        'PYTHONDONTWRITEBYTECODE': '1',
        'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD': '1',
    })
    if 'browser_cache' in paths:
        env['PLAYWRIGHT_BROWSERS_PATH'] = paths['browser_cache']
    return env


def doctor(resources):
    """Run bundled version probes without starting a project or installing tools."""
    root, paths = bundle_paths(resources)
    env = configure(root)
    script = (
        "const p=process.argv[1];const m=require(p);"
        "if(!m.chromium)throw Error('Chromium adapter missing');"
        "console.log(require(require('node:path').join(p,'package.json')).version)"
    )
    commands = {
        'python': [paths['python'], '-I', '-S', '-B', '--version'],
        'git': [paths['git'], '--version'],
        'node': [paths['node'], '--version'],
        'playwright': [paths['node'], '-e', script, paths['playwright']],
        'browser': [paths['browser'], '--version'],
    }
    if 'npm' in paths:
        commands['npm'] = [paths['npm'], '--version']
    versions = {}
    for name, command in commands.items():
        try:
            completed = subprocess.run(
                command, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=20, check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError('Desktop %s check timed out' % name) from error
        version = completed.stdout.strip()
        if completed.returncode or not version or len(version) > 2000:
            raise ValueError('Desktop %s check failed: %s' %
                             (name, completed.stderr.strip()[:1000]))
        versions[name] = version
    return {'ok': True, 'resources': str(root), 'paths': paths, 'versions': versions}


def _same_skill_connection(target, source, files, pointer):
    """Compare only the known tree, without following links or rewriting it."""
    from .backup import _directory, _regular, _signature

    entries = {path.relative_to(source).parts: path for path in files}
    pointer_key = ('bundle-location.json',)
    entries[pointer_key] = None
    children = {(): set()}
    for parts in entries:
        for depth, name in enumerate(parts):
            children.setdefault(parts[:depth], set()).add(name)

    def same_children(descriptor, expected):
        seen = set()
        # Stop at the first unknown entry; never recurse through user content.
        with os.scandir(descriptor) as listing:
            for entry in listing:
                if entry.name not in expected or entry.name in seen:
                    return False
                seen.add(entry.name)
        return seen == expected

    try:
        with _directory(target) as root:
            directories = {(): root}
            signatures = {}
            try:
                for parts in sorted(children, key=len):
                    if parts:
                        directories[parts] = os.open(
                            parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directories[parts[:-1]])
                    descriptor = directories[parts]
                    value = os.fstat(descriptor)
                    if stat.S_IMODE(value.st_mode) != 0o755:
                        return False
                    signatures[parts] = _signature(value)
                    if not same_children(descriptor, children[parts]):
                        return False

                def matches(parts, original, size, mode):
                    descriptor = os.open(
                        parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0),
                        dir_fd=directories[parts[:-1]])
                    with os.fdopen(descriptor, 'rb') as current:
                        value = os.fstat(current.fileno())
                        if (not stat.S_ISREG(value.st_mode) or value.st_size != size or
                                stat.S_IMODE(value.st_mode) != mode):
                            return False
                        signature = _signature(value)
                        remaining = size
                        while remaining:
                            count = min(remaining, 65536)
                            expected = original.read(count)
                            if len(expected) != count or current.read(count) != expected:
                                return False
                            remaining -= count
                        if _signature(os.fstat(current.fileno())) != signature:
                            return False
                        signatures[parts] = signature
                        return True

                for parts, path in entries.items():
                    if path is None:
                        if not matches(parts, io.BytesIO(pointer), len(pointer), 0o644):
                            return False
                    else:
                        with _regular(path) as original:
                            value = os.fstat(original.fileno())
                            if not matches(parts, original, value.st_size, value.st_mode & 0o777):
                                return False
                            if _signature(os.fstat(original.fileno())) != _signature(value):
                                return False

                # Detect replacement or modification during the read, including
                # replacing an opened directory with a link or another directory.
                for parts, signature in signatures.items():
                    value = (os.fstat(root) if not parts else os.stat(
                        parts[-1], dir_fd=directories[parts[:-1]], follow_symlinks=False))
                    if _signature(value) != signature:
                        return False
                for parts, expected in children.items():
                    if not same_children(directories[parts], expected):
                        return False
                with _directory(target) as current_root:
                    return _signature(os.fstat(current_root)) == signatures[()]
            finally:
                for parts, descriptor in reversed(list(directories.items())):
                    if parts:
                        os.close(descriptor)
    except (OSError, ValueError):
        return False


def connect_skill(resources, destination, *, archive=None):
    """Create a thin Skill, or read-only reuse its exact generated connection."""
    from .backup import _directory, _regular

    root, _ = bundle_paths(resources)
    source = root / 'skills' / 'reprise'
    if source.is_symlink() or source.parent.is_symlink():
        raise ValueError('The bundled Skill directory cannot be a symbolic link')
    if not (source / 'SKILL.md').is_file() or not (source / 'scripts' / 'reprise').is_file():
        raise ValueError('The bundled Skill is incomplete')
    # Copy only the small Skill. A legacy assets/runtime is not a second install.
    files = []
    for name in ('SKILL.md', 'agents', 'references', 'scripts'):
        entry = source / name
        candidates = [entry, *entry.rglob('*')] if entry.is_dir() else [entry]
        for candidate in candidates:
            if not candidate.exists():
                continue
            if candidate.is_symlink():
                raise ValueError('The bundled Skill cannot contain symbolic links')
            if candidate.is_file():
                files.append(candidate)
            elif not candidate.is_dir():
                raise ValueError('The bundled Skill contains a special file')
    target = Path(os.path.abspath(Path(destination).expanduser()))
    if target == root or root in target.parents or target in root.parents:
        raise ValueError('Install the connected Skill outside the runtime bundle')
    archive_path = None
    if archive is not None:
        archive_path = Path(os.path.abspath(Path(archive).expanduser()))
        if (archive_path == root or root in archive_path.parents or
                archive_path == target or target in archive_path.parents):
            raise ValueError('Keep the Skill ZIP outside the runtime and connected Skill directories')
        if archive_path.suffix.lower() != '.zip':
            raise ValueError('The Skill upload archive must have a .zip extension')
        if archive_path.exists() or archive_path.is_symlink():
            raise ValueError('Skill ZIP already exists; nothing was overwritten')
        if any(parent.is_symlink() for parent in archive_path.parents):
            raise ValueError('Skill ZIP parents cannot be symbolic links')
    pointer = (json.dumps({'schema': 1, 'resources': str(root)},
                          ensure_ascii=True, indent=2) + '\n').encode('utf-8')
    reused = target.exists() or target.is_symlink()
    if reused and not _same_skill_connection(target, source, files, pointer):
        raise ValueError('Skill destination already exists and is not an identical connection; nothing was overwritten')
    if not reused:
        for ancestor in target.parents:
            if ancestor.is_symlink():
                raise ValueError('Skill destination parents cannot be symbolic links')
        ancestor, missing = target.parent, []
        while not ancestor.exists():
            missing.append(ancestor.name)
            ancestor = ancestor.parent
        with _directory(ancestor) as existing:
            parent = os.dup(existing)
            try:
                for component in reversed(missing):
                    try:
                        os.mkdir(component, mode=0o755, dir_fd=parent)
                    except FileExistsError:
                        pass
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=parent)
                    os.close(parent)
                    parent = child
                # A newly raced destination is still refused by the exclusive claim.
                os.mkdir(target.name, mode=0o755, dir_fd=parent)
                descriptor = os.open(target.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=parent)
                os.fchmod(descriptor, 0o755)
            finally:
                os.close(parent)
        directories = {(): descriptor}
        try:
            for path in files:
                relative = path.relative_to(source)
                parts = relative.parts
                for depth in range(1, len(parts)):
                    key = parts[:depth]
                    if key not in directories:
                        parent = directories[key[:-1]]
                        os.mkdir(key[-1], mode=0o755, dir_fd=parent)
                        directories[key] = os.open(
                            key[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
                        os.fchmod(directories[key], 0o755)
                with _regular(path) as original:
                    mode = os.fstat(original.fileno()).st_mode & 0o777
                    output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     mode, dir_fd=directories[parts[:-1]])
                    with os.fdopen(output, 'wb') as copied:
                        os.fchmod(copied.fileno(), mode)
                        while True:
                            chunk = original.read(1024 * 1024)
                            if not chunk:
                                break
                            copied.write(chunk)
            output = os.open('bundle-location.json',
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o644, dir_fd=descriptor)
            with os.fdopen(output, 'wb') as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(pointer)
        finally:
            for descriptor in reversed(list(directories.values())):
                os.close(descriptor)
    result = {'connected': True, 'destination': str(target), 'resources': str(root),
              'agent_settings_modified': False, 'reused': reused}
    if archive_path is not None:
        # Anchor the upload to this verified bundle and this call's pointer.
        # Re-reading the installed target after validation could export a
        # concurrent edit pointing to a different runtime than the receipt.
        with _directory(archive_path.parent) as parent:
            output = os.open(archive_path.name,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o644, dir_fd=parent)
        with os.fdopen(output, 'wb') as stream, zipfile.ZipFile(
                stream, 'w', zipfile.ZIP_DEFLATED) as package:
            for path in files:
                with _regular(path) as contents:
                    info = zipfile.ZipInfo('reprise/' + path.relative_to(source).as_posix())
                    info.create_system = 3
                    info.external_attr = (0o100000 | (os.fstat(contents.fileno()).st_mode & 0o777)) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    package.writestr(info, contents.read())
            info = zipfile.ZipInfo('reprise/bundle-location.json')
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, pointer)
        with _regular(archive_path) as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        result.update(archive=str(archive_path), archive_sha256=digest,
                      archive_profile='standard-connected-skill')
    return result
