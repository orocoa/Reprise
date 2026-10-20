"""Open a repository in a verified own loopback service, without source writes."""
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
from .processes import process_identity
from .storage import read_json
from . import __version__


def _request(record, path, body=None, token=None, method=None):
    url = urllib.parse.urlsplit(record['url'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.path not in ('', '/'):
        raise ValueError('Saved server URL is not a local Reprise address')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers.update({'X-Reprise-Token': token, 'Origin': record['url'].rstrip('/')})
    request = urllib.request.Request(record['url'].rstrip('/') + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None, method=method)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def verified_server(directory):
    record = read_json(Path(directory) / 'server.json')
    if not record:
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
    return {**record, 'version': health.get('version')}


def open_repository(directory, path='.', port=0, browser=True, language=None,
                    history_repositories=(), history_catalog=None):
    canonical = Repository(path).info()['path']
    directory = Path(directory).expanduser().resolve()
    source = Path(canonical).resolve()
    if directory == source or source in directory.parents:
        raise ValueError('Reprise data must be outside the imported repository')
    directory.mkdir(parents=True, exist_ok=True)
    record = verified_server(directory)
    reused = bool(record)
    if record and record.get('version') != __version__:
        raise ValueError('Another Reprise version is running (%s). Run reprise --data %s shutdown, then open again; saved data is retained.' %
                         (record.get('version', 'unknown'), shlex.quote(str(directory))))
    if not record:
        entry = Path(__file__).with_name('server_entry.py').resolve()
        logpath = directory / 'server.log'
        if logpath.is_symlink():
            raise ValueError('Server log cannot be a symlink')
        fd = os.open(str(logpath), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'ab') as log:
            process = subprocess.Popen([sys.executable, '-I', '-S', str(entry), '--data', str(directory),
                                        'serve', '--port', str(port), '--fallback-port'],
                                       cwd=str(entry.parent), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
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
    bootstrap = _request(record, '/api/bootstrap?include_projects=0')
    project = _request(record, '/api/projects', {'path': canonical}, bootstrap['token'])
    if history_repositories or history_catalog is not None:
        histories = [_request(record, '/api/projects', {'path': str(Path(path).expanduser().resolve())},
                              bootstrap['token'])['id'] for path in history_repositories]
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
    url = record['url'] + '?' + urllib.parse.urlencode(query) + '#versions'
    if browser:
        webbrowser.open(url)
    return {'url': url, 'project_id': project['id'], 'path': canonical, 'pid': record['pid'],
            'reused': reused, 'stop_command': 'reprise --data ' + shlex.quote(str(directory)) + ' shutdown'}


def shutdown(directory):
    record = verified_server(directory)
    if not record:
        return {'stopped': True, 'already_exited': True}
    bootstrap = _request(record, '/api/bootstrap?include_projects=0')
    result = _request(record, '/api/shutdown', {}, bootstrap['token'])
    deadline = time.monotonic() + 10
    while process_identity(record['pid']) == record['identity'] and time.monotonic() < deadline:
        time.sleep(.08)
    if process_identity(record['pid']) == record['identity']:
        raise ValueError('Server shutdown has not been confirmed')
    return result
