"""Evidence ingestion and URLs; imported media never pretend to be automated capture."""
import hashlib
from pathlib import Path
import secrets
import shutil
import urllib.parse

from .http_files import media_type
from .storage import now, write_json


class EvidenceStore:
    def __init__(self, directory, captures):
        self.directory = Path(directory).resolve() / 'evidence'
        self.captures = captures

    def public(self, value):
        value = {**value, 'items': [dict(item) for item in value.get('items', [])]}
        for item in value['items']:
            if not item.get('path'):
                continue
            path = Path(item['path']).resolve()
            try:
                relative = path.relative_to(self.directory)
            except ValueError:
                item['error'] = '证据文件不在受管理的证据目录。'
                continue
            item['url'] = '/artifacts/' + urllib.parse.quote(str(relative), safe='/')
            if not path.is_file():
                item['missing'] = True
        return value

    def list(self, project_id, sha=None):
        return [self.public(item) for item in self.captures.list(project_id, sha)]

    def manual(self, repository, project_id, values):
        sha = repository.resolve(values.get('sha', 'HEAD'))
        base = repository.resolve(values['base']) if values.get('base') else None
        raw_path = values.get('path')
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError('请填写截图、录屏或其他证据的本地文件路径。')
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file() or not 0 < path.stat().st_size <= 512 * 1024 * 1024:
            raise ValueError('证据文件不存在、为空或超过 512 MB。')
        kind = values.get('kind', 'file')
        if kind not in ('image', 'video', 'file'):
            raise ValueError('证据类型无效。')
        mime = media_type(path)
        if kind == 'image' and mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
            raise ValueError('图片证据支持 PNG、JPEG、WebP 和 GIF。')
        if kind == 'video' and mime not in ('video/mp4', 'video/webm', 'video/quicktime'):
            raise ValueError('视频证据支持 MP4、WebM 和 MOV。')
        title = values.get('title') or path.name
        if not isinstance(title, str) or len(title) > 200:
            raise ValueError('证据名称太长。')
        identifier = secrets.token_hex(16)
        folder = self.directory / identifier
        folder.mkdir(parents=True)
        # Fixed destination avoids user file names becoming active URLs or header content.
        extension = { 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/gif': '.gif', 'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov' }.get(mime, '.bin')
        destination = folder / ('manual' + extension)
        shutil.copyfile(str(path), str(destination))
        digest = hashlib.sha256()
        with destination.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1048576), b''):
                digest.update(chunk)
        record = {'id': identifier, 'project_id': project_id, 'sha': sha, 'base': base, 'source': 'manual', 'status': 'complete', 'verification': 'user-supplied', 'created_at': now(), 'recipe_hash': None, 'errors': [], 'items': [{'capture_id': values.get('capture_id') or 'manual', 'title': title, 'side': 'target', 'sha': sha, 'path': str(destination), 'media_type': mime, 'kind': kind, 'original_path': str(path), 'content_sha256': digest.hexdigest(), 'bytes': destination.stat().st_size}], 'note': '人工提供的证据；提交归属由提供者指定，未经自动运行核验。'}
        write_json(folder / 'record.json', record)
        return self.public(record)
