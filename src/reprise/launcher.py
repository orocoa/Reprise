"""Open a repository in a verified own loopback service, without source writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

from .git import Repository
from .processes import ProcessCleanupError, ProcessObservationError, strict_process_identity as process_identity
from .storage import read_json
from . import __version__


def service_source_id():
    """Identify this installation's canonical location without publishing it."""
    resources = os.environ.get('REPRISE_BUNDLE_RESOURCES')
    location = Path(resources).expanduser().resolve() if resources else Path(__file__).resolve().parent
    kind = 'bundle' if resources else 'source'
    return hashlib.sha256(('reprise-service-source-v1\0' + kind + '\0' + str(location)).encode('utf-8')).hexdigest()


def _stop_command(directory):
    return shlex.join([sys.executable, '-I', '-S', '-B',
                      str(Path(__file__).with_name('server_entry.py').resolve()),
                      '--data', str(directory), 'shutdown'])


def _request(record, path, body=None, token=None, method=None, timeout=5):
    url = urllib.parse.urlsplit(record['url'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.path not in ('', '/'):
        raise ValueError('Saved server URL is not a local Reprise address')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers.update({'X-Reprise-Token': token, 'Origin': record['url'].rstrip('/')})
    request = urllib.request.Request(record['url'].rstrip('/') + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None, method=method)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def verified_server(directory):
    record = read_json(Path(directory) / 'server.json')
    if not record:
        return None
    if (isinstance(record, dict) and record.get('restored_process_authority_disabled') is True and
            record.get('pid') is None and record.get('identity') is None):
        return None
    if not isinstance(record, dict) or not isinstance(record.get('pid'), int) or record['pid'] <= 0:
        raise ValueError('Invalid saved server record')
    if process_identity(record['pid']) is None:
        return None
    if not record.get('identity') or process_identity(record['pid']) != record['identity']:
        raise ValueError('Saved server identity cannot be verified; restart the existing Reprise service')
    health = _request(record, '/api/health')
    if (not record.get('instance_id') or health.get('instance_id') != record['instance_id'] or
            Path(record['data_directory']).resolve() != Path(directory).resolve()):
        raise ValueError('The saved address does not belong to this Reprise service')
    # Health is tied to the verified instance; a saved record alone cannot
    # establish the origin of an older service that never reported one.
    return {**record, 'version': health.get('version'), 'source_id': health.get('source_id')}


def open_repository(directory, path='.', port=0, browser=True, language=None,
                    history_repositories=(), history_catalog=None, kind=None):
    from .projects import ProjectStore
    directory = Path(directory).expanduser().resolve()
    registered = next((p for p in ProjectStore(directory).records() if p['id'] == str(path)), None)
    identifier = None
    if registered and registered.get('kind') == 'folder':
        canonical, kind, identifier = registered['path'], 'folder', registered['id']
    else:
        canonical, kind = ProjectStore.source(registered['path'] if registered else str(path), kind)
    if kind == 'folder' and (history_repositories or history_catalog):
        raise ValueError('普通文件夹使用独立快照，不能关联为原 Git 提交历史。')
    source = Path(canonical).resolve()
    if directory == source or source in directory.parents or directory in source.parents:
        raise ValueError('Reprise data must be outside the imported repository')
    directory.mkdir(parents=True, exist_ok=True)
    from .maintenance import DataLease
    with DataLease(directory):
        return _open_registered(directory, canonical, port, browser, language, history_repositories, history_catalog, kind, identifier)


def _ensure_server(directory, port):
    """Start or reuse our verified service without importing any source path."""
    try:
        record = verified_server(directory)
        if not record and not process_identity(os.getpid()):
            raise ProcessObservationError('Cannot establish the calling process identity')
    except ProcessCleanupError as error:
        raise ProcessObservationError(
            '当前沙箱无法可靠观察进程，未启动新的 Reprise 服务。请在客户端为本次命令批准可观察的运行权限后重试，无需重复保存。 '
            'Process observation is unavailable in this sandbox; no new Reprise service was started. '
            'Approve observable execution for this command in your client and retry without saving again. '
            + str(error)) from error
    reused = bool(record)
    if not record:
        entry = Path(__file__).with_name('server_entry.py').resolve()
        logpath = directory / 'server.log'
        if logpath.is_symlink():
            raise ValueError('Server log cannot be a symlink')
        fd = os.open(str(logpath), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'ab') as log:
            process = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(entry), '--data', str(directory),
                                        'serve', '--port', str(port), '--fallback-port'],
                                       cwd=str(entry.parent), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    record = verified_server(directory)
                    if record:
                        break
                except (OSError, ValueError):
                    pass  # another opener may have acquired the single server lock
                if process.poll() is not None and record is None:
                    time.sleep(.1)
                else:
                    time.sleep(.08)
            if not record:
                raise ValueError('Reprise did not start; inspect ' + str(logpath))
        except BaseException as error:
            # This call still owns the Popen child; never signal a PID from a
            # saved record or a concurrent opener that won the service lock.
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError) as cleanup_error:
                raise error from cleanup_error
            raise
        # A concurrent opener may have won the server lock. Only the process
        # launched by this call grants the desktop window shutdown ownership.
        reused = record['pid'] != process.pid or process.poll() is not None
    # Also verify a service that won the single-server lock during startup.
    # Concurrent openers can belong to different installed package locations.
    if record.get('version') != __version__:
        raise ValueError('Another Reprise version is running (%s). Run %s, then open again; saved data is retained.' %
                         (record.get('version', 'unknown'), _stop_command(directory)))
    if record.get('source_id') != service_source_id():
        reason = ('Reprise is running from a different location' if record.get('source_id') else
                  'The running Reprise location cannot be verified')
        raise ValueError(reason + '. Run ' + _stop_command(directory) +
                         ', then open again; saved data is retained.')
    return record, reused


def _open_url(record, reused, query, browser, *, project_id=None, path=None):
    url = record['url'] + ('?' + urllib.parse.urlencode(query) if query else '') + '#versions'
    if browser:
        webbrowser.open(url)
    return {'url': url, 'project_id': project_id, 'path': path, 'pid': record['pid'],
            'instance_id': record['instance_id'],
            'reused': reused, 'stop_command': _stop_command(record['data_directory'])}


def open_workbench(directory, port=0, browser=True, language=None):
    """Open the project chooser without inspecting or importing the cwd."""
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    from .maintenance import DataLease
    with DataLease(directory):
        record, reused = _ensure_server(directory, port)
        return _open_url(record, reused, {'lang': language} if language else {}, browser)


def _open_registered(directory, canonical, port, browser, language, history_repositories, history_catalog, kind, identifier=None):
    record, reused = _ensure_server(directory, port)
    bootstrap = _request(record, '/api/bootstrap?include_projects=0')
    # Import reads bounded Git metadata and manifests, which can legitimately
    # exceed the short health-check budget on a busy machine.
    project = (_request(record, '/api/projects/' + identifier, timeout=15) if identifier else
               _request(record, '/api/projects', {'path': canonical, 'kind': kind}, bootstrap['token'], timeout=15))
    if history_repositories or history_catalog is not None:
        histories = [_request(record, '/api/projects', {'path': str(Path(path).expanduser().resolve())},
                              bootstrap['token'], timeout=15)['id'] for path in history_repositories]
        if not history_repositories:
            histories = project.get('history_project_ids', [])
        entries = json.loads(Path(history_catalog).read_text()) if history_catalog else None
        if entries is not None and (not isinstance(entries, list) or
                any(not isinstance(entry, dict) or 'sha' not in entry for entry in entries)):
            raise ValueError('历史目录应为带 SHA 的版本记录数组。')
        project = _request(record, '/api/projects/' + project['id'] + '/histories',
            {'history_project_ids': histories, 'catalog': [entry['sha'] for entry in entries] if entries is not None else None},
            bootstrap['token'], method='PUT')
    query = {'project': project['id']}
    if language:
        query['lang'] = language
    return _open_url(record, reused, query, browser, project_id=project['id'], path=canonical)


def shutdown(directory, *, instance_id=None):
    record = verified_server(directory)
    if not record:
        return {'stopped': True, 'already_exited': True}
    if instance_id is not None and record['instance_id'] != instance_id:
        return {'stopped': False, 'reason': 'different-instance'}
    bootstrap = _request(record, '/api/bootstrap?include_projects=0')
    body = {'instance_id': instance_id} if instance_id is not None else {}
    result = _request(record, '/api/shutdown', body, bootstrap['token'])
    if not result.get('stopped'):
        return result
    deadline = time.monotonic() + 10
    while process_identity(record['pid']) == record['identity'] and time.monotonic() < deadline:
        time.sleep(.08)
    if process_identity(record['pid']) == record['identity']:
        raise ValueError('Server shutdown has not been confirmed')
    return result
