"""Same-recipe, exact-revision browser evidence. AI is never on this path."""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import uuid
from pathlib import Path

from .recipes import recipe_hash, validate_recipe
from .runtime import process_identity, read_json, utcnow, write_json

RUNNER_VERSION = 'reprise-playwright-v2'


def content_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def cache_artifacts_valid(record, folder):
    try:
        for item in record['items']:
            path = Path(item['path']).resolve()
            path.relative_to(folder.resolve())
            if not item.get('content_sha256') or content_sha256(path) != item['content_sha256']:
                return False
        return True
    except (OSError, ValueError, KeyError):
        return False



def stop_owned_group(state):
    pid, identity = state.get('pid'), state.get('process_identity')
    if not pid or not identity:
        return False
    try:
        if process_identity(pid) == identity and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
            return True
    except ProcessLookupError:
        pass
    return False


def stop_browser_from_record(path):
    try:
        return stop_owned_group(read_json(path))
    except (OSError, ValueError):
        return False



class CaptureService:
    def __init__(self, data_dir, runtime_manager):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.directory = self.data_dir / 'evidence'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.runtime_manager = runtime_manager
        self._lock = threading.Lock()

    def list(self, project_id, sha=None):
        records = []
        for path in self.directory.glob('*/record.json'):
            try:
                record = read_json(path)
                if record.get('project_id') == project_id and (sha is None or record.get('sha') == sha):
                    records.append(record)
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda record: record.get('created_at', ''), reverse=True)

    def capture(self, repository, project_id, sha, recipe, base=None, approved=False):
        recipe = validate_recipe(recipe)
        if recipe['adapter'] == 'manual':
            raise ValueError('Manual adapter: attach a screenshot, video or other artifact to this Git version')
        if recipe['adapter'] == 'command-web' and approved is not True:
            raise ValueError('Save and approve the command recipe before automatic capture')
        target = repository.resolve(sha)
        base = repository.resolve(base) if base is not None else None
        digest = recipe_hash(recipe)
        key = hashlib.sha256(json.dumps([project_id, target, base, digest, RUNNER_VERSION], separators=(',', ':')).encode()).hexdigest()
        # Serial capture avoids duplicate jobs and overloading local browsers. The
        # server runs this on its own job thread; browsing Git remains responsive.
        with self._lock:
            for old in self.list(project_id, target):
                if old.get('cache_key') == key and old.get('status') == 'complete' and old.get('items'):
                    if cache_artifacts_valid(old, self.directory / old['id']):
                        return dict(old, cached=True)
            eid = uuid.uuid4().hex
            folder = self.directory / eid
            folder.mkdir()
            record = {'id': eid, 'project_id': project_id, 'sha': target, 'base': base, 'recipe_hash': digest,
                      'recipe': recipe, 'runner_version': RUNNER_VERSION, 'cache_key': key,
                      'status': 'running', 'source': 'automatic', 'ai_used': False, 'created_at': utcnow(),
                      'items': [], 'errors': [], 'warnings': [], 'runtimes': [], 'cached': False}
            path = folder / 'record.json'
            write_json(path, record)
            node = os.environ.get('REPRISE_NODE') or shutil.which('node')
            if not node:
                record['errors'].append({'error': 'Node.js is unavailable. Install Node.js and Playwright/Chromium or set REPRISE_NODE. You can still attach manual evidence.'})
            else:
                sides = [('before', base)] if base else []
                sides.append(('after', target))
                for side, revision in sides:
                    runtime = None
                    try:
                        runtime = self.runtime_manager.start(repository, revision, recipe, approved=approved)
                        record['runtimes'].append({'id': runtime['id'], 'side': side, 'sha': revision, 'path': runtime['path'], 'log_path': runtime['log_path']})
                        result_path = folder / ('%s-result.json' % side)
                        input_path = folder / ('%s-input.json' % side)
                        write_json(input_path, {'url': runtime['url'], 'recipe': recipe, 'sha': revision,
                                               'side': side, 'output_dir': str(folder), 'result_path': str(result_path),
                                               'browser_process_path': str(folder / ('%s-browser-process.json' % side))})
                        timeout = 60 + sum(recipe['readiness']['timeout_ms'] / 1000 * (8 + (45 if c['full_page'] else 0)) +
                                          sum(step.get('ms', 0) / 1000 for step in c['steps']) + c.get('record_ms', 1000) / 1000
                                          for c in recipe['captures'])
                        with (folder / ('%s-browser.log' % side)).open('wb') as log:
                            process = subprocess.Popen([node, str(Path(__file__).with_name('browser_worker.mjs')), str(input_path)],
                                                       cwd=str(Path(__file__).resolve().parents[2]), stdout=log, stderr=subprocess.STDOUT,
                                                       start_new_session=True, stdin=subprocess.DEVNULL, env=dict(os.environ))
                            identity = process_identity(process.pid)
                            write_json(folder / ('%s-worker.json' % side), {'pid': process.pid, 'process_identity': identity, 'created_at': utcnow()})
                            try:
                                process.wait(timeout=min(timeout, max(1, int(os.environ.get('REPRISE_CAPTURE_TIMEOUT', '3600')))))
                            except subprocess.TimeoutExpired:
                                # Playwright launches Chromium in a separate process group.
                                # Track and verify both groups; never signal by process name.
                                stop_browser_from_record(folder / ('%s-browser-process.json' % side))
                                stop_owned_group({'pid': process.pid, 'process_identity': identity})
                                process.wait(timeout=5)
                                raise RuntimeError('Browser capture timed out; owned browser and worker process groups were stopped. See %s-browser.log.' % side)
                            finally:
                                stop_browser_from_record(folder / ('%s-browser-process.json' % side))
                            result = process
                        if not result_path.is_file():
                            raise RuntimeError('Browser worker failed (exit %s). See %s-browser.log. Check Node.js, Playwright and Chromium installation.' % (result.returncode, side))
                        captured = read_json(result_path)
                        for item in captured.get('items', []):
                            try:
                                media_path = Path(item['path']).resolve()
                                media_path.relative_to(folder.resolve())
                                item['content_sha256'] = content_sha256(media_path)
                                item['size_bytes'] = media_path.stat().st_size
                                record['items'].append(item)
                            except (OSError, ValueError, KeyError) as error:
                                record['errors'].append({'side': side, 'error': 'Could not verify captured artifact: %s' % error})
                        record['errors'].extend(captured.get('errors', []))
                        record['warnings'].extend(captured.get('warnings', []))
                        if captured.get('browser_version'):
                            record['browser_version'] = captured['browser_version']
                        if result.returncode:
                            record['errors'].append({'side': side, 'error': 'Browser worker exited with code %s' % result.returncode})
                    except Exception as error:
                        record['errors'].append({'side': side, 'sha': revision, 'error': str(error)})
                    finally:
                        if runtime:
                            try:
                                self.runtime_manager.stop(runtime['id'])
                            except Exception as error:
                                record['errors'].append({'side': side, 'error': 'Runtime cleanup failed: %s' % error})
                    write_json(path, record)
            record['finished_at'] = utcnow()
            record['status'] = ('partial' if record['items'] else 'failed') if record['errors'] else 'complete'
            if not record['items'] and not record['errors']:
                record['status'] = 'failed'
                record['errors'].append({'error': 'The browser produced no evidence'})
            write_json(path, record)
            return record
