#!/usr/bin/env python3
"""Explicit bridge for the earlier catalog/previews format. No project-specific paths."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reprise.projects import ProjectStore
from reprise.http_files import media_type
from reprise.storage import now, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--catalog', required=True, help='JSON containing versions or a versions array')
    parser.add_argument('--media-root', required=True, help='Local folder containing original preview files')
    parser.add_argument('--name')
    args = parser.parse_args()
    data = Path(args.data).resolve()
    projects = ProjectStore(data)
    project = projects.add(args.repo, args.name)
    repository = projects.repository(project['id'])
    catalog = json.loads(Path(args.catalog).read_text())
    versions = catalog.get('versions', []) if isinstance(catalog, dict) else catalog
    media_root = Path(args.media_root).resolve()
    imported, skipped, failures = 0, 0, []
    for version in versions:
        try:
            sha = repository.resolve(version.get('sha') or version['id'])
        except ValueError as error:
            failures.append({'sha': version.get('sha'), 'error': str(error)})
            continue
        previews = version.get('previews', [])
        identifier = hashlib.sha256(('legacy-v1:' + project['id'] + sha + json.dumps(previews, sort_keys=True)).encode()).hexdigest()[:32]
        folder = data / 'evidence' / identifier
        if (folder / 'record.json').exists():
            skipped += 1
            continue
        folder.mkdir(parents=True, exist_ok=False)
        record = {'id': identifier, 'project_id': project['id'], 'sha': sha, 'base': version.get('base'), 'source': 'legacy', 'verification': 'retained-legacy-metadata', 'status': 'complete', 'created_at': now(), 'recipe_hash': None, 'items': [], 'errors': [], 'title': version.get('title'), 'legacy_metadata': {key: version.get(key) for key in ('title','summary','changes','ref','origin','verified')}, 'note': '从旧版导入的历史资料，保留原始采集来源，未由新采集引擎重新验证。'}
        seen = set()
        for index, preview in enumerate(previews):
            for field in ('url', 'full_url'):
                url = preview.get(field)
                if not url or url in seen:
                    continue
                seen.add(url)
                relative = unquote(urlsplit(url).path)
                # This bridge accepts local retained media, never remote downloads.
                if urlsplit(url).scheme or '..' in Path(relative).parts:
                    record['errors'].append({'error': 'External or invalid preview URL', 'url': url})
                    continue
                source = (media_root / Path(relative).name).resolve()
                if media_root not in source.parents or not source.is_file():
                    record['errors'].append({'error': 'Legacy media file missing', 'url': url})
                    continue
                name = '%03d-%s%s' % (index, field, source.suffix.lower())
                destination = folder / name
                shutil.copyfile(source, destination)
                original_sha = preview.get('captured_sha') or preview.get('sha') or sha
                title = preview.get('caption') or '历史预览'
                if field == 'full_url': title += ' · 全图'
                if original_sha != sha: title += ' · 沿用已有资料'
                record['items'].append({'capture_id': '%03d-%s' % (index, field), 'side': 'after', 'sha': original_sha, 'bound_sha': sha, 'path': str(destination), 'media_type': media_type(destination), 'title': title, 'width': preview.get('pixel_width'), 'height': preview.get('pixel_height'), 'original_path': str(source), 'legacy': preview, 'content_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
        record['status'] = ('partial' if record['items'] else 'failed') if record['errors'] or not record['items'] else 'complete'
        write_json(folder / 'record.json', record)
        imported += 1
    result = {'project_id': project['id'], 'imported': imported, 'already_present': skipped, 'unavailable_revisions': failures}
    write_json(data / 'legacy-import-receipt.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
