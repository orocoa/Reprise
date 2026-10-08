"""Loopback-only local API. Project content runs on a separate preview origin."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sysconfig
import urllib.parse

from . import __version__
from .http_files import serve_file
from .service import Reprise
from .storage import now, write_json

WEB = Path(__file__).resolve().parents[2] / 'web'
if not WEB.is_dir():
    WEB = Path(sysconfig.get_path('data')) / 'share/reprise/web'


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, service):
        if address[0] != '127.0.0.1':
            raise ValueError('Reprise only binds to loopback')
        self.service = service
        self.token = secrets.token_urlsafe(32)
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
            self.wfile.write(data)

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
        except (ValueError, TypeError, OSError, json.JSONDecodeError) as error:
            self.send_json({'error': str(error)[:3000]}, 400)
        except Exception:
            self.send_json({'error': '服务处理失败；任务和已保存证据仍然保留。'}, 500)

    def _dispatch(self):
        host = self.headers.get('Host', '')
        expected = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        if host not in expected:
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
            return self.send_json({'ok': True, 'version': __version__})
        if path == '/api/bootstrap' and reading:
            return self.send_json({'token': self.server.token, 'projects': app.projects.list(), 'runtimes': app.runtime_list(), 'ai': app.ai.state(), 'data_directory': str(app.directory), 'version': __version__, 'jobs': app.jobs.list()})
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
                return self.send_json(app.projects.save_recipe(identifier, body.get('recipe')))
            if suffix in ('run', 'capture', 'ai/suggest') and method == 'POST':
                return self.send_json(app.execute(identifier, suffix, body), 202)
            if suffix == 'evidence' and reading:
                sha = repository.resolve(query['sha'][0]) if query.get('sha') else None
                return self.send_json({'evidence': app.evidence.list(identifier, sha)})
            if suffix == 'evidence/manual' and method == 'POST':
                return self.send_json(app.evidence.manual(repository, identifier, body), 201)
        if reading and path.startswith('/artifacts/'):
            root = (app.directory / 'evidence').resolve()
            candidate = (root / path[len('/artifacts/'):]).resolve()
            if root not in candidate.parents or not candidate.is_file() or candidate.name == 'record.json':
                raise KeyError('找不到证据文件。')
            attachment = candidate.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov')
            return serve_file(self, candidate, cache='private, max-age=31536000, immutable', attachment=attachment)
        if reading:
            candidate = (WEB / (path.lstrip('/') or 'index.html')).resolve()
            if WEB.resolve() in candidate.parents and candidate.is_file() and candidate.suffix in ('.html', '.css', '.js', '.svg', '.ico'):
                return serve_file(self, candidate)
        raise KeyError('找不到此页面或接口。')


def serve(directory, port=51582):
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
    server = LocalServer(('127.0.0.1', port), app)
    url = 'http://127.0.0.1:%d/' % server.server_port
    write_json(directory / 'server.json', {'pid': os.getpid(), 'url': url, 'started_at': now(), 'data_directory': str(directory), 'version': __version__})
    print('Reprise ' + url + '\nData: ' + str(directory), flush=True)
    try:
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
        lock.close()
