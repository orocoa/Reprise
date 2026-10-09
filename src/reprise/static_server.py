"""Isolated, loopback-only static preview server; no source code execution."""
import argparse
import mimetypes
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PreviewHandler(SimpleHTTPRequestHandler):
    def _serve(self, body=True):
        # Loopback binding alone does not reject a foreign Host that resolves
        # to this machine. Apply the same boundary as the management server.
        expected = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1 or hosts[0] not in expected:
            self.send_error(403, 'Host is not the local Reprise preview server.')
            return
        relative = unquote(urlsplit(self.path).path).lstrip('/')
        requested = (self.server.root / relative).resolve()
        try:
            requested.relative_to(self.server.root)
        except ValueError:
            self.send_error(403, 'Path leaves preview root')
            return
        if requested.is_dir():
            requested = requested / 'index.html'
        if not requested.is_file():
            self.send_error(404, 'File absent from this Git version')
            return
        # Resolve index symlinks as well as URL path symlinks.
        try:
            requested.resolve().relative_to(self.server.root)
        except ValueError:
            self.send_error(403, 'Path leaves preview root')
            return
        size = requested.stat().st_size
        start, end, status = 0, size - 1, 200
        header = self.headers.get('Range')
        if header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
            if not match or not any(match.groups()) or size == 0:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%s' % size)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            left, right = match.groups()
            if left:
                start, end = int(left), min(int(right) if right else size - 1, size - 1)
            else:
                start, end = max(0, size - int(right)), size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%s' % size)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        mime = mimetypes.guess_type(str(requested))[0] or 'application/octet-stream'
        if requested.suffix == '.wasm':
            mime = 'application/wasm'
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-cache')
        # Needed by threaded WebAssembly / SharedArrayBuffer game exports.
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status == 206:
            self.send_header('Content-Range', 'bytes %s-%s/%s' % (start, end, size))
        self.end_headers()
        if body:
            try:
                with requested.open('rb') as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        self._serve()

    def do_HEAD(self):
        self._serve(False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), PreviewHandler)
    server.root = Path(args.root).resolve()
    server.serve_forever()


if __name__ == '__main__':
    main()
