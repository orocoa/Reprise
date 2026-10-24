#!/usr/bin/env python3
"""Prepare retained, interactive synthetic versions and local Python environments.

Creates a new destination only. No version or environment is deleted. Optional
screenshots use the installed Reprise capture tools and their REPRISE_* settings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SERVER = '''import os, socket
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
socket.getfqdn = lambda host: "localhost"
ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), SimpleHTTPRequestHandler).serve_forever()
'''
STYLE = '''*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1140px;margin:auto;padding:48px 64px}header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:24px;font-size:14px}header img{width:42px;height:42px}header strong{display:flex;align-items:center;gap:12px}small{letter-spacing:.08em}.hero{padding:66px 0 48px;display:grid;grid-template-columns:1.4fr 1fr;gap:50px;align-items:center}.label{font-size:14px;color:var(--accent);font-weight:650}h1{font-size:64px;letter-spacing:-.055em;line-height:1.1;margin:18px 0 22px}p{line-height:1.8}.intro{max-width:520px;font-size:18px;opacity:.78}.shape{min-height:230px;background:var(--accent);border-radius:var(--radius);display:flex;align-items:center;justify-content:center;color:var(--paper);font-size:76px;font-weight:750;letter-spacing:-.06em;transform:rotate(var(--angle))}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{padding:24px;border:1px solid var(--line);border-radius:14px;background:var(--card)}.card b{display:block;margin:14px 0 12px;font-size:19px}.card span{font-size:12px;color:var(--accent)}.card p{font-size:14px;margin:0;opacity:.75}footer{margin-top:36px;padding-top:22px;border-top:1px solid var(--line);font-size:13px;line-height:1.8;opacity:.7}@media(max-width:700px){main{padding:24px}.hero{grid-template-columns:1fr;padding:42px 0;gap:20px}h1{font-size:48px}.shape{min-height:160px}.cards{grid-template-columns:1fr}header small{display:none}}
'''
MARK = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="13" fill="#1e293b"/><path d="M14 31V17h9c10 0 10 14 0 14h-9m0-7h15" fill="none" stroke="#fff" stroke-width="3.5" stroke-linejoin="round"/></svg>\n'
VERSIONS = [
    {'title': '初稿', 'headline': '先把想法留下来。', 'description': '暖色与圆形组成第一版。尚未确定的标题、草图和说明，也值得有一个明确的保存点。',
     'paper': '#fbf3e8', 'ink': '#442c25', 'accent': '#a34030', 'line': '#dec9bb', 'card': '#fff9f0', 'radius': '50%', 'angle': '-7deg', 'symbol': '01', 'stage': '概念探索', 'note': '初稿独有：暖色圆形方案、最初的叙事与标题。'},
    {'title': '第二稿', 'headline': '把方向变得清楚。', 'description': '改成蓝色与有棱角的版式，把探索收束成更清楚的结构。这一版保留了独立的设计决定。',
     'paper': '#eef4ff', 'ink': '#172e58', 'accent': '#285fc9', 'line': '#c9d7ef', 'card': '#f8faff', 'radius': '22px', 'angle': '5deg', 'symbol': '02', 'stage': '结构调整', 'note': '第二稿独有：蓝色方形方案、修改后的信息结构。'},
    {'title': '当前稿', 'headline': '让每一步都可回看。', 'description': '绿色、稳定的结构与精简的内容组成当前版本。旧稿仍保留，可以先看清再决定取舍。',
     'paper': '#edf5ec', 'ink': '#203d2c', 'accent': '#33754b', 'line': '#c5d8c7', 'card': '#f7fbf4', 'radius': '90px 20px 90px 20px', 'angle': '0deg', 'symbol': '03', 'stage': '保留当前', 'note': '当前稿独有：绿色定稿方案、精简的内容与稳定结构。'},
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def inspect(path):
    return {str(item.relative_to(path)): {'sha256': hashlib.sha256(item.read_bytes()).hexdigest(),
            'mode': item.stat().st_mode, 'mtime_ns': item.stat().st_mtime_ns}
            for item in sorted(path.rglob('*')) if item.is_file()}


def page(version):
    variables = ';'.join('--%s:%s' % (key, version[key]) for key in
                         ('paper', 'ink', 'accent', 'line', 'card', 'radius', 'angle'))
    return ('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reprise 体验样本 · {title}</title><link rel="stylesheet" href="assets/shared.css">
<body style="{variables}"><main><header><strong><img src="assets/shared-mark.svg" alt="共享标记">版本生活实验室</strong><small>REPRISE / LOCAL DEMO</small></header>
<section class="hero"><div><div class="label">{title} · {stage}</div><h1>{headline}</h1><p class="intro">{description}</p></div><div class="shape">{symbol}</div></section>
<section class="cards"><article class="card"><span>01 / 认准版本</span><b>这是「{title}」</b><p>颜色、标题与内容都绑定这一份历史版本。可以回到 Reprise 切换版本，或查看保存的真实截图。</p></article>
<article class="card"><span>02 / 看清共享与独有</span><b>相同资源，只存一份内容</b><p>公共样式、标记和纹理在三个版本与另一项目间共享。本稿的页面、阶段说明和方案素材各不相同。</p></article>
<article class="card"><span>03 / 按需重建环境</span><b>源码留下，环境可重建</b><p>本页使用已实际构建的本地 Python 环境。停止运行后可预检、明确释放，再运行重建。</p></article></section>
<footer>合成体验样本 · 不含真实个人资料 · 无远端页面资源<br>准备过程保留全部版本、源文件、环境与截图；未执行版本删除或环境释放。</footer></main></body></html>'''.format(variables=variables, **version)).encode('utf-8')


def prepare(destination, entry, capture=False):
    destination = Path(destination).expanduser().absolute()
    entry = Path(entry).expanduser().resolve(strict=True)
    destination.mkdir(parents=True, exist_ok=False)
    source, other = destination / 'version-lab', destination / 'shared-resource-library'
    data, commands, inputs = destination / 'reprise-data', destination / 'commands', destination / 'inputs'
    for path in (source, other, commands, inputs):
        path.mkdir()
    versions, steps, active = [], [], []
    tick = time.monotonic()

    def call(label, *arguments):
        argv = [sys.executable, str(entry), '--data', str(data), *map(str, arguments)]
        started = time.monotonic()
        try:
            process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=240)
        except (subprocess.TimeoutExpired, OSError) as error:
            def decoded(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            write_json(commands / (label + '.json'), {'argv': argv, 'error': str(error),
                'stdout': decoded(getattr(error, 'stdout', None)), 'stderr': decoded(getattr(error, 'stderr', None))})
            raise
        write_json(commands / (label + '.json'), {'argv': argv, 'returncode': process.returncode,
            'stdout': process.stdout, 'stderr': process.stderr, 'elapsed_seconds': round(time.monotonic() - started, 3)})
        print(label, flush=True)
        steps.append(label)
        if process.returncode:
            raise RuntimeError('CLI failed at %s; diagnostics retained in %s' % (label, commands))
        value = json.loads(process.stdout)
        if isinstance(value, dict) and value.get('status') in ('failed', 'partial', 'cancelled'):
            raise RuntimeError('Incomplete CLI result at ' + label)
        result = value.get('result', value) if isinstance(value, dict) else value
        if isinstance(result, dict) and result.get('status') in ('failed', 'partial', 'cancelled'):
            raise RuntimeError('Incomplete operation result at ' + label)
        return result

    try:
        shared = {'assets/shared.css': STYLE.encode(), 'assets/shared-mark.svg': MARK.encode(),
                  'assets/shared-texture.bin': hashlib.shake_256(b'shared-visual-resource').digest(256 * 1024),
                  'server.py': SERVER.encode(), 'requirements.txt': b'# Local Python standard-library demo. No packages are downloaded.\n'}
        recipe = {'schema': 1, 'adapter': 'command-web', 'root': '.', 'network': 'local',
                  'commands': {'install': [[sys.executable, '-m', 'venv', '--without-pip', '.venv']],
                               'start': ['.venv/bin/python', 'server.py']},
                  'environment': {'outputs': ['.venv'], 'inputs': ['requirements.txt'], 'tools': [sys.executable]},
                  'readiness': {'path': '/', 'selector': 'h1', 'timeout_ms': 20000},
                  'captures': [{'id': 'main', 'route': '/', 'viewport': {'width': 1440, 'height': 1000, 'scale': 1},
                                'full_page': False, 'wait_for': 'h1'}]}
        recipe_path = destination / 'local-python-recipe.json'
        write_json(recipe_path, recipe)
        for number, version in enumerate(VERSIONS, 1):
            values = {**shared, 'index.html': page(version), '阶段专属说明.txt': (version['note'] + '\n').encode(),
                      'assets/iteration-material.bin': hashlib.shake_256(version['title'].encode()).digest(512 * 1024)}
            original = inputs / ('%02d-' % number + version['title'])
            original.mkdir()
            for name, value in values.items():
                for folder in (source, original):
                    target = folder / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(value)
            saved = call('save-%d' % number, 'save', source, '--name', '版本生活实验室', '--title', version['title'])
            # Save emits project_id on the outer job; recover it from the exact
            # command receipt without guessing a project from recency.
            raw = json.loads(json.loads((commands / ('save-%d.json' % number)).read_text())['stdout'])
            project = raw['project_id']
            versions.append({'title': version['title'], 'sha': saved['sha'], 'input_directory': str(original),
                             'page_sha256': hashlib.sha256(values['index.html']).hexdigest()})
        for name in ('assets/shared.css', 'assets/shared-mark.svg', 'assets/shared-texture.bin'):
            target = other / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(shared[name])
        other_saved = call('save-shared-project', 'save', other, '--name', '共享资源保留项目', '--title', '共享资源')
        other_raw = json.loads(json.loads((commands / 'save-shared-project.json').read_text())['stdout'])
        before = {'source': inspect(source), 'other': inspect(other), 'inputs': inspect(inputs)}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for number, version in enumerate(versions, 1):
            call('recipe-%d' % number, 'recipe', project, recipe_path, '--sha', version['sha'])
            runtime = call('run-%d' % number, 'run', project, '--sha', version['sha'])
            active.append(runtime['id'])
            if runtime['sha'] != version['sha'] or not runtime.get('environment_id'):
                raise RuntimeError('Runtime does not match the exact historical version and environment')
            with opener.open(runtime['url'], timeout=10) as response:
                served = response.read()
            (destination / ('served-%d.html' % number)).write_bytes(served)
            if hashlib.sha256(served).hexdigest() != version['page_sha256']:
                raise RuntimeError('Actual preview differs from the saved historical page')
            version.update(environment_id=runtime['environment_id'], runtime_id=runtime['id'],
                           http_readback_verified=True, screenshot_captured=False)
            if capture:
                evidence = call('capture-%d' % number, 'capture', project, '--sha', version['sha'])
                images = [item for item in evidence.get('items', []) if item.get('media_type', '').startswith('image/')]
                if evidence.get('sha') != version['sha'] or not images:
                    raise RuntimeError('Capture did not return an image for the exact historical version')
                for image in images:
                    if (image.get('sha') != version['sha'] or hashlib.sha256(Path(image['path']).read_bytes()).hexdigest()
                            != image.get('content_sha256')):
                        raise RuntimeError('Captured image identity or readback checksum differs')
                version.update(screenshot_captured=True, evidence_id=evidence['id'], screenshots=images)
            call('stop-%d' % number, 'stop', runtime['id'])
            active.remove(runtime['id'])
            preflight = call('environment-check-%d' % number, 'environment-check', runtime['environment_id'])
            if not preflight['rebuild_verified'] or not preflight['releasable']:
                raise RuntimeError('Prepared environment is not ready for an explicit later release')
            version['release_preflight'] = preflight
        environments = call('environments-ready', 'environments', project)['environments']
        if len(environments) != 3 or any(item['status'] != 'ready' or not item['rebuild_verified'] for item in environments):
            raise RuntimeError('All three environments must remain verified and ready')
        history = call('history-retained', 'history', project)
        if {item['sha'] for item in history['commits']} != {item['sha'] for item in versions}:
            raise RuntimeError('All three snapshots must remain available')
        if before != {'source': inspect(source), 'other': inspect(other), 'inputs': inspect(inputs)}:
            raise RuntimeError('Preparing previews modified retained source or input files')
        open_argv = [sys.executable, str(entry), '--data', str(data), 'open', str(source), '--folder', '--lang', 'zh']
        summary = {'schema': 1, 'status': 'ready', 'sample_only': True, 'data_directory': str(data),
                   'source_directory': str(source), 'project_id': project, 'versions': versions,
                   'other_project_id': other_raw['project_id'], 'other_project_sha': other_saved['sha'],
                   'open_argv': open_argv, 'open_command': shlex.join(open_argv), 'source_files_removed': False,
                   'source_content_and_metadata_unchanged': True, 'snapshots_deleted': 0, 'environments_released': 0,
                   'retained_environment_count': len(environments), 'steps': steps,
                   'elapsed_seconds': round(time.monotonic() - tick, 3),
                   'limitations': ['Synthetic local sample; every input, snapshot, environment and screenshot is retained.',
                     'Python venv is rebuilt without pip; no dependency registry or remote package download is tested.',
                     'Release readiness is checked now; actual release rechecks ownership, contents and process activity.',
                     'Version deletion later removes managed history only; this fixture intentionally keeps original input copies.']}
        write_json(destination / 'summary.json', summary)
        return summary
    except Exception as error:
        write_json(destination / 'failure.json', {'status': 'failed', 'error': str(error), 'steps': steps, 'versions': versions})
        raise
    finally:
        for rid in active:
            try:
                call('cleanup-stop-' + rid, 'stop', rid)
            except Exception as error:
                write_json(destination / ('cleanup-failed-' + rid + '.json'), {'runtime_id': rid, 'error': str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--to', required=True, help='New destination; an existing path is never reused or overwritten')
    parser.add_argument('--entry', default=str(ROOT / 'run.py'), help='Source or installed Skill CLI entry')
    parser.add_argument('--capture', action='store_true', help='Capture each exact version using configured Reprise browser tools')
    args = parser.parse_args()
    try:
        summary = prepare(args.to, args.entry, args.capture)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({key: summary[key] for key in ('status', 'data_directory', 'project_id', 'open_command', 'elapsed_seconds')},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
