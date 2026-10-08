"""Shared-scenario, exact-revision browser evidence. AI is never on this path."""
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
from .cancellation import Cancelled, check, wait_process, cancellable_lock

RUNNER_VERSION = 'reprise-playwright-v3'


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


def stop_worker(process, identity, browser_record):
    if process.poll() is None and process_identity(process.pid) == identity and os.getpgid(process.pid) == process.pid:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            stop_owned_group({'pid': process.pid, 'process_identity': identity})
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
    stop_browser_from_record(browser_record)



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

    def capture(self, repository, project_id, sha, recipe, base=None, approved=False, base_recipe=None, base_approved=False, cancel=None):
        check(cancel)
        recipe = validate_recipe(recipe)
        if recipe['adapter'] == 'manual':
            raise ValueError('Manual adapter: attach a screenshot, video or other artifact to this Git version')
        if recipe['adapter'] == 'command-web' and approved is not True:
            raise ValueError('Save and approve the command recipe before automatic capture')
        target = repository.resolve(sha)
        base = repository.resolve(base) if base is not None else None
        if base:
            if base_recipe is None:
                base_recipe, base_approved = recipe, approved
            base_recipe = validate_recipe(base_recipe)
            if base_recipe['adapter'] == 'manual' or (base_recipe['adapter'] == 'command-web' and not base_approved):
                raise ValueError('请先为比较基准版本保存并确认运行配置。')
            # Execution is revision-specific; observation scenarios stay identical.
            base_recipe = {**base_recipe, 'captures': recipe['captures'], 'network': recipe['network']}
        digest = recipe_hash(recipe)
        base_digest = recipe_hash(base_recipe) if base else None
        key = hashlib.sha256(json.dumps([project_id, target, base, digest, base_digest, RUNNER_VERSION], separators=(',', ':')).encode()).hexdigest()
        # Serial capture avoids duplicate jobs and overloading local browsers. The
        # server runs this on its own job thread; browsing Git remains responsive.
        with cancellable_lock(self._lock, cancel):
            for old in self.list(project_id, target):
                if old.get('cache_key') == key and old.get('status') == 'complete' and old.get('items'):
                    if cache_artifacts_valid(old, self.directory / old['id']):
                        return dict(old, cached=True)
            eid = uuid.uuid4().hex
            folder = self.directory / eid
            folder.mkdir()
            record = {'id': eid, 'project_id': project_id, 'sha': target, 'base': base, 'recipe_hash': digest,
                      'recipe': recipe, 'base_recipe': base_recipe, 'base_recipe_hash': base_digest, 'runner_version': RUNNER_VERSION, 'cache_key': key,
                      'status': 'running', 'source': 'automatic', 'ai_used': False, 'created_at': utcnow(),
                      'items': [], 'errors': [], 'warnings': [], 'runtimes': [], 'cached': False}
            path = folder / 'record.json'
            write_json(path, record)
            node = os.environ.get('REPRISE_NODE') or shutil.which('node')
            if not node:
                record['errors'].append({'error': 'Node.js is unavailable. Install Node.js and Playwright/Chromium or set REPRISE_NODE. You can still attach manual evidence.'})
            else:
                sides = [('before', base, base_recipe, base_approved)] if base else []
                sides.append(('after', target, recipe, approved))
                for side, revision, side_recipe, side_approved in sides:
                    runtime = None
                    try:
                        check(cancel)
                        runtime = self.runtime_manager.start(repository, revision, side_recipe, approved=side_approved, cancel=cancel)
                        record['runtimes'].append({'id': runtime['id'], 'side': side, 'sha': revision, 'path': runtime['path'], 'log_path': runtime['log_path']})
                        result_path = folder / ('%s-result.json' % side)
                        input_path = folder / ('%s-input.json' % side)
                        write_json(input_path, {'url': runtime['url'], 'recipe': side_recipe, 'sha': revision,
                                               'side': side, 'output_dir': str(folder), 'result_path': str(result_path),
                                               'browser_process_path': str(folder / ('%s-browser-process.json' % side))})
                        timeout = 60 + sum(side_recipe['readiness']['timeout_ms'] / 1000 * (8 + (45 if c['full_page'] else 0)) +
                                          sum(step.get('ms', 0) / 1000 for step in c['steps']) + c.get('record_ms', 1000) / 1000
                                          for c in recipe['captures'])
                        with (folder / ('%s-browser.log' % side)).open('wb') as log:
                            process = subprocess.Popen([node, str(Path(__file__).with_name('browser_worker.mjs')), str(input_path)],
                                                       cwd=str(Path(__file__).resolve().parents[2]), stdout=log, stderr=subprocess.STDOUT,
                                                       start_new_session=True, stdin=subprocess.DEVNULL, env=dict(os.environ))
                            identity = process_identity(process.pid)
                            write_json(folder / ('%s-worker.json' % side), {'pid': process.pid, 'process_identity': identity, 'created_at': utcnow()})
                            try:
                                wait_process(process, min(timeout, max(1, int(os.environ.get('REPRISE_CAPTURE_TIMEOUT', '3600')))), cancel)
                            except Cancelled:
                                stop_worker(process, identity, folder / ('%s-browser-process.json' % side))
                            except subprocess.TimeoutExpired:
                                # Playwright launches Chromium in a separate process group.
                                # Track and verify both groups; never signal by process name.
                                stop_worker(process, identity, folder / ('%s-browser-process.json' % side))
                                raise RuntimeError('Browser capture timed out; owned browser and worker process groups were stopped. See %s-browser.log.' % side)
                            finally:
                                stop_browser_from_record(folder / ('%s-browser-process.json' % side))
                            result = process
                        if not result_path.is_file():
                            check(cancel)
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
                        check(cancel)
                    except Cancelled as error:
                        record['errors'].append({'side': side, 'sha': revision, 'error': str(error)})
                        break
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
            if cancel is not None and cancel.requested():
                record['status'] = 'cancelled'
            if not record['items'] and not record['errors'] and record['status'] != 'cancelled':
                record['status'] = 'failed'
                record['errors'].append({'error': 'The browser produced no evidence'})
            write_json(path, record)
            return record
