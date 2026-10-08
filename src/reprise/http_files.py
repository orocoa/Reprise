"""Read-only file responses with byte ranges and cache revalidation."""
import mimetypes
import re
from email.utils import formatdate, parsedate_to_datetime


def media_type(path):
    # Some retained historical captures have a PNG filename but JPEG bytes.
    with path.open('rb') as source:
        magic = source.read(16)
    if magic.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if magic.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    return mimetypes.guess_type(path)[0] or 'application/octet-stream'


def serve_file(handler, path, *, cache='no-cache', attachment=False):
    stat = path.stat()
    total = stat.st_size
    etag = '"%x-%x-%x"' % (stat.st_ino, stat.st_mtime_ns, total)
    modified = formatdate(stat.st_mtime, usegmt=True)
    if handler.headers.get('If-None-Match') in (etag, '*'):
        handler.send_response(304)
        handler.send_header('ETag', etag)
        handler.send_header('Cache-Control', cache)
        handler.end_headers()
        return
    start, end, status = 0, total - 1, 200
    header = handler.headers.get('Range', '')
    validator = handler.headers.get('If-Range')
    if validator and validator != etag:
        try:
            valid = parsedate_to_datetime(validator).timestamp() >= int(stat.st_mtime)
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            header = ''
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if match and any(match.groups()):
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), total - 1) if last else total - 1
        else:
            start = max(0, total - int(last))
        if total == 0 or start >= total or start > end or (not first and int(last) == 0):
            handler.send_response(416)
            handler.send_header('Content-Range', 'bytes */' + str(total))
            handler.send_header('Content-Length', '0')
            handler.end_headers()
            return
        status = 206
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/octet-stream' if attachment else media_type(path))
    handler.send_header('Content-Length', str(end - start + 1))
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('ETag', etag)
    handler.send_header('Last-Modified', modified)
    handler.send_header('Cache-Control', cache)
    if status == 206:
        handler.send_header('Content-Range', f'bytes {start}-{end}/{total}')
    if attachment:
        handler.send_header('Content-Disposition', 'attachment; filename="' + path.name + '"')
    handler.end_headers()
    if handler.command == 'HEAD':
        return
    try:
        with path.open('rb') as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(262144, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        # Switching versions or seeking intentionally cancels old requests.
        pass
