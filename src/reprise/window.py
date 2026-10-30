"""Open the existing macOS window shell against an already verified service."""
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.parse
import uuid

from .storage import locked
from . import __version__


def validate_url(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port
            or parts.username is not None or parts.password is not None or parts.path != '/'):
        raise ValueError('Reprise window requires a verified local service URL')


def window_binary(directory):
    bundled = Path(__file__).with_name('SourceWindow.swift')
    source = bundled if bundled.is_file() else Path(__file__).resolve().parents[2] / 'desktop/macos/SourceWindow.swift'
    icon_root = Path(__file__).parent
    if not (icon_root / 'Reprise.icns').is_file():
        icon_root = Path(__file__).resolve().parents[2] / 'skills/reprise/assets'
    icons = {name: (icon_root / name).read_bytes() for name in ('Reprise.icns', 'reprise-icon-1024.png')}
    fingerprint = hashlib.sha256(source.read_bytes() + platform.machine().encode() +
                                 __version__.encode() + b''.join(icons.values())).hexdigest()[:24]
    cache = Path(directory).expanduser().resolve() / 'windows' / fingerprint
    cache.mkdir(parents=True, exist_ok=True)
    contents = cache / 'Reprise.app' / 'Contents'
    binary = contents / 'MacOS' / 'Reprise'
    with locked(cache / 'build.lock'):
        if not binary.is_file():
            compiler = shutil.which('swiftc')
            if not compiler:
                raise ValueError('macOS Swift tools are unavailable; omit --window to use a browser')
            attempt = cache / ('build-' + uuid.uuid4().hex)
            attempt.mkdir()
            candidate = attempt / 'Reprise'
            process = subprocess.run([compiler, str(source), '-o', str(candidate),
                                      '-module-cache-path', str(cache / 'modules')],
                                     capture_output=True, text=True, timeout=120)
            (attempt / 'compiler.log').write_text(process.stdout + process.stderr)
            if process.returncode:
                raise ValueError('Reprise window could not compile; inspect ' + str(attempt / 'compiler.log'))
            binary.parent.mkdir(parents=True, exist_ok=True)
            with (contents / 'Info.plist').open('wb') as stream:
                plistlib.dump({'CFBundleExecutable': 'Reprise', 'CFBundleName': 'Reprise',
                              'CFBundleIdentifier': 'com.orocoa.reprise.window', 'CFBundlePackageType': 'APPL',
                              'CFBundleShortVersionString': __version__,
                              'CFBundleVersion': __version__.split('-')[0],
                              'CFBundleIconFile': 'Reprise.icns',
                              'NSHighResolutionCapable': True}, stream)
            shutil.copy2(candidate, binary)
        resources = contents / 'Resources'
        resources.mkdir(exist_ok=True)
        for name, data in icons.items():
            target = resources / name
            if not target.exists():
                target.write_bytes(data)
            elif target.read_bytes() != data:
                raise ValueError('Native icon differs from its window cache identity: ' + name)
    return binary


def open_window(directory, url, timeout=25):
    validate_url(url)
    if sys.platform != 'darwin':
        raise ValueError('Standalone Reprise windows currently require macOS; omit --window to use a browser')
    binary = window_binary(directory)
    resources = binary.parent.parent / 'Resources'
    resources.mkdir(parents=True, exist_ok=True)
    # Reopening from an app mention/Dock must start or verify the service,
    # rather than depend on a stale URL or the withdrawn bundled runtime.
    entry = Path(__file__).with_name('window_entry.py').resolve()
    config = {'schema': 1, 'python': str(Path(sys.executable).resolve()),
              'entry': str(entry), 'data': str(Path(directory).expanduser().resolve()),
              'project': dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)).get('project'),
              'language': dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)).get('lang', 'en')}
    (resources / 'source-launch.json').write_text(json.dumps(config, indent=2) + '\n')
    sessions = Path(directory).expanduser().resolve() / 'windows' / 'sessions'
    sessions.mkdir(parents=True, exist_ok=True)
    session = sessions / ('session-' + uuid.uuid4().hex)
    receipt = session.with_suffix('.json')
    logpath = session.with_suffix('.log')
    with logpath.open('xb') as log:
        process = subprocess.Popen([str(binary), '--url', url, '--ready-file', str(receipt)],
                                   cwd=str(binary.parent), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if receipt.is_file():
            result = json.loads(receipt.read_text())
            if result.get('status') == 'ready' and result.get('url') == url:
                return {'status': 'ready', 'backend': 'appkit', 'pid': process.pid,
                        'app_path': str(binary.parent.parent.parent), 'receipt': str(receipt)}
            raise ValueError('Reprise window failed: ' + str(result.get('error', 'Invalid window receipt')))
        if process.poll() is not None:
            raise ValueError('Reprise window exited; inspect ' + str(logpath))
        time.sleep(.05)
    raise ValueError('Reprise window readiness was not confirmed; inspect ' + str(logpath))
