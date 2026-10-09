"""Loopback-only local API. Project content runs on a separate preview origin."""
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import secrets
import threading
import urllib.parse

from . import __version__
from .http_files import serve_file
from .service import Reprise
from .storage import now, write_json
from .processes import ProcessCleanupError
from .static_server import LoopbackHTTPServer
from . import workspace

WEB = Path(__file__).resolve().parent / 'web'
if not WEB.is_dir():
    # Source and editable installs use the canonical web/ directory. Wheels
    # contain the same files as package resources, independent of install scheme.
    WEB = Path(__file__).resolve().parents[2] / 'web'


class LocalServer(LoopbackHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, service):
        if address[0] != '127.0.0.1':
            raise ValueError('Reprise only binds to loopback')
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_hex(24)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'Reprise/' + __version__

    def log_message(self, *_):
        pass

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-src http://127.0.0.1:* http://localhost:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def send_json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=True).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        self.dispatch()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def dispatch(self):
        try:
            self._dispatch()
        except KeyError as error:
            self.send_json({'error': str(error).strip("'")}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except ProcessCleanupError as error:
            self.send_json({'error': '停止未确认；请查看运行记录并重试。' + str(error)[:2500]}, 409)
        except (ValueError, TypeError, OSError, json.JSONDecodeError) as error:
            self.send_json({'error': str(error)[:3000]}, 400)
        except Exception:
            self.send_json({'error': '服务处理失败；任务和已保存证据仍然保留。'}, 500)

    def _dispatch(self):
        host = self.headers.get('Host', '')
        expected = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        if len(self.headers.get_all('Host', [])) != 1 or host not in expected:
            return self.send_json({'error': 'Host is not the local Reprise server.'}, 403)
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        parts = [p for p in path.strip('/').split('/') if p]
        method = self.command
        reading = method in ('GET', 'HEAD')
        body = None
        if not reading:
            origin = self.headers.get('Origin')
            if self.headers.get('X-Reprise-Token') != self.server.token or (origin and origin not in {'http://' + h for h in expected}):
                return self.send_json({'error': '请在 Reprise 本机页面发起操作。'}, 403)
            if self.headers.get_content_type() != 'application/json':
                return self.send_json({'error': 'Expected application/json.'}, 415)
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 1024 * 1024:
                return self.send_json({'error': 'Request is too large.'}, 413)
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body, dict):
                raise ValueError('JSON body must be an object')
        app = self.server.service
        if path == '/api/health' and reading:
            return self.send_json({'ok': True, 'version': __version__, 'instance_id': self.server.instance_id})
        if path == '/api/shutdown' and method == 'POST':
            app.close()
            for runtime in app.runtimes.list():
                if runtime['running']:
                    app.runtimes.stop(runtime['id'])
            self.send_json({'stopped': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == '/api/bootstrap' and reading:
            if query.get('include_projects', ['1'])[0] == '0':
                projects = []  # Project metadata is loaded once, in the workspace snapshot.
            else:
                projects = [app.projects.get(query['project'][0])] if query.get('project', [''])[0] else app.projects.list()
            return self.send_json({'token': self.server.token, 'projects': projects, 'runtimes': app.runtime_list(), 'ai': app.ai.state(), 'data_directory': str(app.directory), 'version': __version__, 'jobs': app.jobs.list(), 'job_warnings': app.jobs.warnings()})
        if path == '/api/workspace/context' and reading:
            return self.send_json(workspace.context(app, query.get('project', [None])[0]))
        if path == '/api/workspace/snapshot' and reading:
            return self.send_json(workspace.project_snapshot(app, query['project'][0]))
        if path == '/api/workspace/diff' and reading:
            identifier = query['project'][0]
            record = app.projects.record(identifier)
            source, repository = workspace.comparison_repository(app, identifier,
                record.get('history_project_ids', []), query['base'][0], query['target'][0])
            return self.send_json({**repository.diff(query['target'][0], base=query['base'][0]),
                                   'source_project_id': source})
        if path == '/api/workspace/file' and reading:
            return self.send_json(workspace.file_comparison(app, query['project'][0],
                query['sha'][0], query['path'][0], query.get('base', [None])[0]))
        if path == '/api/projects':
            if reading:
                return self.send_json({'projects': app.projects.list()})
            if method == 'POST':
                return self.send_json(app.projects.add(body.get('path'), body.get('name')), 201)
        if path == '/api/ai':
            if reading:
                return self.send_json(app.ai.state())
            if method == 'PUT':
                return self.send_json(app.ai.save(body))
        if path == '/api/runtimes' and reading:
            return self.send_json({'runtimes': app.runtime_list()})
        if len(parts) == 3 and parts[:2] == ['api', 'jobs'] and reading:
            return self.send_json(app.jobs.get(parts[2]))
        if len(parts) == 4 and parts[:2] == ['api', 'jobs'] and parts[3] == 'cancel' and method == 'POST':
            return self.send_json(app.jobs.cancel(parts[2]), 202)
        if len(parts) == 4 and parts[:2] == ['api', 'runtimes'] and parts[3] == 'stop' and method == 'POST':
            return self.send_json(app.runtimes.stop(parts[2]))
        if len(parts) >= 3 and parts[:2] == ['api', 'projects']:
            identifier = parts[2]
            suffix = '/'.join(parts[3:])
            if not suffix and reading:
                return self.send_json(app.projects.get(identifier))
            repository = app.projects.repository(identifier)
            if suffix == 'history' and reading:
                return self.send_json(repository.history(query.get('ref', ['--all'])[0], limit=int(query.get('limit', ['50'])[0]), offset=int(query.get('offset', ['0'])[0])))
            if suffix == 'refs' and reading:
                return self.send_json({'refs': repository.refs()})
            if suffix == 'status' and reading:
                return self.send_json(repository.status())
            if suffix == 'diff' and reading:
                return self.send_json(repository.diff(query.get('target', ['HEAD'])[0], base=query.get('base', [None])[0]))
            if len(parts) == 5 and parts[3] == 'versions' and reading:
                return self.send_json(app.version(identifier, parts[4]))
            if suffix == 'recipe' and method == 'PUT':
                return self.send_json(app.projects.save_recipe(identifier, body.get('recipe'), body.get('sha', 'HEAD')))
            if suffix == 'notes' and method == 'PUT':
                return self.send_json(app.projects.save_notes(identifier, body.get('localizations'), body.get('sha', 'HEAD')))
            if suffix == 'histories' and method == 'PUT':
                return self.send_json(app.projects.save_histories(identifier,
                    body.get('history_project_ids'), body.get('catalog')))
            if suffix in ('run', 'capture', 'ai/suggest') and method == 'POST':
                return self.send_json(app.execute(identifier, suffix, body), 202)
            if suffix == 'evidence' and reading:
                sha = repository.resolve(query['sha'][0]) if query.get('sha') else None
                return self.send_json({'evidence': app.evidence.list(identifier, sha)})
            if suffix == 'evidence/manual' and method == 'POST':
                return self.send_json(app.evidence.manual(repository, identifier, body), 201)
        if reading and path.startswith('/artifacts/'):
            candidate = app.evidence.file(path[len('/artifacts/'):])
            attachment = candidate.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov')
            return serve_file(self, candidate, cache='private, max-age=31536000, immutable', attachment=attachment)
        if reading:
            candidate = (WEB / (path.lstrip('/') or 'index.html')).resolve()
            if (WEB.resolve() in candidate.parents and candidate.is_file() and
                    (candidate.suffix in ('.html', '.css', '.js', '.svg', '.ico', '.woff2', '.ttf', '.txt') or candidate.name.endswith('LICENSE'))):
                return serve_file(self, candidate)
        raise KeyError('找不到此页面或接口。')


def serve(directory, port=51582, fallback_port=False):
    import fcntl
    import os
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lockpath = directory / 'server.lock'
    if lockpath.is_symlink():
        raise ValueError('Server lock cannot be a symlink')
    lock = lockpath.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError('这个数据目录已有服务在运行，请使用已有服务或不同的 --data 目录。')
    app = Reprise(directory)
    try:
        server = LocalServer(('127.0.0.1', port), app)
    except OSError as error:
        import errno
        if not fallback_port or error.errno != errno.EADDRINUSE:
            app.close()
            lock.close()
            raise
        server = LocalServer(('127.0.0.1', 0), app)
    url = 'http://127.0.0.1:%d/' % server.server_port
    from .processes import process_identity
    write_json(directory / 'server.json', {'pid': os.getpid(), 'identity': process_identity(os.getpid()),
               'instance_id': server.instance_id, 'url': url, 'started_at': now(),
               'data_directory': str(directory), 'version': __version__}, private=True)
    print('Reprise ' + url + '\nData: ' + str(directory), flush=True)
    try:
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
        lock.close()
