"""Explicit-action native folder selection, with no optional Python dependency.

Call ``choose_folder`` only after the user requests a picker. Capability checks
never start a process. All commands and AppleScript are fixed application text;
no path, prompt or other request field is interpolated into executable code.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading


_PICKER_LOCK = threading.Lock()
_MAC_SCRIPT = '''try
    set selectedFolder to choose folder with prompt "Choose your local project folder"
    return POSIX path of selectedFolder
on error number -128
    return ""
end try'''


def _backend():
    if sys.platform == 'darwin':
        executable = shutil.which('/usr/bin/osascript')
        return ('osascript', executable, None) if executable else (None, None, 'native-picker-unavailable')
    if sys.platform.startswith('linux'):
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            return None, None, 'desktop-session-unavailable'
        for name in ('zenity', 'kdialog'):
            executable = shutil.which(name)
            if executable:
                return name, executable, None
        return None, None, 'native-picker-unavailable'
    return None, None, 'unsupported-platform'


def capabilities():
    """Read-only availability; does not display a dialog or install software."""
    backend, executable, reason = _backend()
    return {'supported': bool(executable), 'backend': backend, 'reason': reason}


def choose_folder(*, timeout=120):
    """Open one native picker and return a selected existing absolute directory.

    Results contain ``status``, ``path``, ``backend`` and a machine-readable
    ``reason``. Status is selected, cancelled, unavailable, timeout or error.
    Cancellation and failure never select the current working directory. The
    caller owns authorization, project import and any subsequent data operation.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise ValueError('Folder picker timeout must be between 1 and 600 seconds.')
    backend, executable, reason = _backend()
    result = {'status': 'unavailable', 'path': None, 'backend': backend, 'reason': reason}
    if not executable:
        return result
    if not _PICKER_LOCK.acquire(blocking=False):
        return {**result, 'status': 'error', 'reason': 'picker-busy'}
    try:
        commands = {
            'osascript': [executable, '-e', _MAC_SCRIPT],
            'zenity': [executable, '--file-selection', '--directory', '--title=Choose your local project folder'],
            'kdialog': [executable, '--getexistingdirectory', os.path.expanduser('~'),
                        '--title', 'Choose your local project folder'],
        }
        try:
            completed = subprocess.run(commands[backend], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {**result, 'status': 'timeout', 'reason': 'picker-timed-out'}
        except OSError:
            return {**result, 'status': 'error', 'reason': 'picker-start-failed'}
        if ((backend in ('zenity', 'kdialog') and completed.returncode == 1)
                or (backend == 'osascript' and completed.returncode != 0
                    and b'(-128)' in completed.stderr)):
            return {**result, 'status': 'cancelled', 'reason': 'user-cancelled'}
        if backend == 'zenity' and completed.returncode == 5:
            return {**result, 'status': 'timeout', 'reason': 'picker-timed-out'}
        if completed.returncode:
            return {**result, 'status': 'error', 'reason': 'picker-failed'}
        # Remove only the tool's terminating newline; spaces and embedded
        # newlines are legitimate parts of a selected local folder name.
        output = completed.stdout[:-1] if completed.stdout.endswith(b'\n') else completed.stdout
        if not output:
            return {**result, 'status': 'cancelled', 'reason': 'user-cancelled'}
        selected = os.fsdecode(output)
        try:
            valid = '\x00' not in selected and Path(selected).is_absolute() and Path(selected).is_dir()
        except (OSError, ValueError):
            valid = False
        if not valid:
            return {**result, 'status': 'error', 'reason': 'selected-folder-unavailable'}
        return {**result, 'status': 'selected', 'path': selected, 'reason': None}
    finally:
        _PICKER_LOCK.release()
