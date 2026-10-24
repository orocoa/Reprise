#!/usr/bin/env python3
"""Build the bilingual Reprise docs without third-party packages or network calls.

The renderer deliberately supports this site's small Markdown subset, not every
CommonMark extension. Raw HTML is escaped. Existing output is never replaced.
"""
import argparse
import hashlib
import html
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from urllib.parse import quote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SLUGS = ('index', 'getting-started', 'find-compare-restore', 'privacy-and-faq')
NAV = {
    'zh': ('产品介绍', '首次使用', '按图取回', '隐私与常见问题'),
    'en': ('Overview', 'First use', 'Recover by picture', 'Privacy and FAQ'),
}
PRIVATE = re.compile(r'/Users/|/home/[A-Za-z0-9_.-]+/|[A-Za-z]:\\Users\\|CODEX_THREAD_ID|thread://|work/test-artifacts/|\bsk-[A-Za-z0-9_-]{20,}')
SHA = re.compile(r'^[a-f0-9]{64}$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def public_text(value, label):
    require(isinstance(value, str), label + ' must be text')
    require(not PRIVATE.search(value), label + ' contains a private path, receipt location, or credential-like token')
    return value


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def public_https(value, label, origin=False):
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and bool(parsed.hostname), label + ' must be an explicit public HTTPS URL')
    require(not parsed.username and not parsed.password and not parsed.fragment, label + ' must not contain credentials or fragments')
    host = parsed.hostname.lower()
    require(not (host in {'localhost', 'example.com', 'example.org', 'example.net'} or host.endswith(('.localhost', '.local', '.invalid', '.test', '.example'))), label + ' must not use a placeholder or local host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    require(address is None or address.is_global, label + ' must not use a private IP')
    require(not origin or (parsed.path in ('', '/') and not parsed.query), 'origin must contain only scheme and host; use --base-path for /Reprise/')
    return value.rstrip('/') if origin else value


def asset_path(source, value):
    public_text(value, 'asset path')
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and relative.parts[0] == 'assets' and '..' not in relative.parts, 'assets must be relative paths below assets/')
    target = source.joinpath(*relative.parts)
    require(target.is_file() and not target.is_symlink(), 'asset is missing or is a symlink: ' + value)
    require(source.resolve() in target.resolve().parents, 'asset escapes site source')
    return target


def load_demo(source, version, production):
    demo = json.loads((source / 'recovery-demo.json').read_text(encoding='utf-8'))
    require(demo.get('schema') == 1 and demo.get('status') in ('pending', 'verified'), 'invalid recovery-demo schema/status')
    require(demo.get('version') == version, 'recovery demo version differs from content')
    for asset in demo.get('assets', []):
        require(asset.get('kind') in ('image', 'video', 'download'), 'asset kind must be image, video, or download')
        path = asset_path(source, asset.get('path', ''))
        expected = asset.get('sha256')
        if expected:
            require(SHA.fullmatch(expected) and digest(path) == expected, 'asset hash does not match: ' + asset['path'])
        for key in ('alt', 'caption'):
            labels = asset.get(key, {})
            require(isinstance(labels, dict), 'asset labels must be locale maps')
            for locale in ('zh', 'en'):
                public_text(labels.get(locale, ''), 'asset ' + key)
        if asset['kind'] in ('image', 'video'):
            require(all(asset.get('alt', {}).get(l) and asset.get('caption', {}).get(l) for l in ('zh', 'en')), 'media requires bilingual alternative text and caption')
        if asset['kind'] == 'video':
            if asset.get('poster'):
                asset_path(source, asset['poster'])
            languages = set()
            for track in asset.get('tracks', []):
                track_path = asset_path(source, track.get('src', ''))
                require(track_path.suffix == '.vtt', 'caption tracks must be VTT files')
                text = public_text(track_path.read_text(encoding='utf-8'), 'caption track')
                require(text.startswith('WEBVTT'), 'caption track is missing WEBVTT header')
                require(track.get('srclang') in ('zh', 'en') and track['srclang'] not in languages, 'expected one caption track per language')
                public_text(track.get('label', ''), 'track label')
                languages.add(track['srclang'])
                if track.get('sha256'):
                    require(digest(track_path) == track['sha256'], 'caption hash does not match')
    for step in demo.get('steps', []):
        for key in ('title', 'body'):
            require(isinstance(step.get(key), dict), 'demo step requires bilingual ' + key)
            for locale in ('zh', 'en'):
                public_text(step[key].get(locale, ''), 'demo step ' + key)
        public_text(step.get('command', ''), 'demo command')
    if demo['status'] == 'verified':
        package = demo.get('package', {})
        name = package.get('filename')
        require(isinstance(name, str) and name == Path(name).name, 'package filename must be a basename')
        public_text(name, 'package filename')
        require(SHA.fullmatch(package.get('sha256') or ''), 'verified demo requires the exact package SHA-256')
        require(all(demo.get('verification', {}).get(k) is True for k in ('exact_version', 'source_unchanged', 'recovery_readback')), 'verified demo requires exact_version, source_unchanged, and recovery_readback')
        require(any(a['kind'] in ('image', 'video') for a in demo.get('assets', [])), 'verified demo requires actual captured media')
        require(any(a['kind'] == 'download' for a in demo.get('assets', [])), 'verified demo requires the actual sample download')
        require(all(SHA.fullmatch(a.get('sha256') or '') for a in demo.get('assets', [])), 'verified assets require SHA-256 values')
    require(not production or demo['status'] == 'verified', 'production requires a verified final-package recovery demo')
    return demo


class Markdown:
    """Escaped Markdown subset with checked links; unsupported raw HTML is text."""
    def __init__(self, locale, known, base, resources, evidence, teaser):
        self.locale, self.known, self.base = locale, known, base
        self.resources, self.evidence = resources, evidence
        self.teaser = teaser
        self.links = []
        self.headings = []
        self.ids = set()

    def href(self, value):
        value = html.unescape(value)
        parsed = urlsplit(value)
        if parsed.scheme:
            require(parsed.scheme in ('https', 'http', 'mailto'), 'unsupported link scheme: ' + parsed.scheme)
            return value
        require(not value.startswith('//') and not value.startswith('/'), 'use content-relative links: ' + value)
        if not parsed.path:
            return value
        parts = list(PurePosixPath(self.locale).parts)
        for part in PurePosixPath(parsed.path).parts:
            if part == '..':
                require(bool(parts), 'relative link escapes content root')
                parts.pop()
            elif part != '.':
                parts.append(part)
        target = '/'.join(parts)
        require(target in self.known, 'unknown internal content link: ' + target)
        self.links.append(target)
        route = self.known[target]
        return self.base + route + ('#' + quote(parsed.fragment) if parsed.fragment else '')

    def inline(self, text):
        # Tokenize code first so punctuation inside commands stays literal.
        pattern = re.compile(r'(`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\)|\*\*[^*\n]+\*\*)')
        result = []
        for part in pattern.split(text):
            if part.startswith('`') and part.endswith('`'):
                result.append('<code>' + html.escape(part[1:-1]) + '</code>')
            elif part.startswith('**') and part.endswith('**'):
                result.append('<strong>' + self.inline(part[2:-2]) + '</strong>')
            elif part.startswith('[') and '](' in part and part.endswith(')'):
                label, target = part[1:-1].split('](', 1)
                result.append('<a href="' + html.escape(self.href(target), quote=True) + '">' + self.inline(label) + '</a>')
            else:
                result.append(html.escape(part))
        return ''.join(result)

    def render(self, text):
        lines, out, i = text.splitlines(), [], 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line in ('<!-- RECOVERY_RESOURCES -->', '<!-- RECOVERY_EVIDENCE -->', '<!-- RECOVERY_TEASER -->'):
                out.append(self.resources if 'RESOURCES' in line else self.teaser if 'TEASER' in line else self.evidence)
                i += 1
                continue
            if line.startswith('```'):
                language, block = line[3:].strip(), []
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    block.append(lines[i]); i += 1
                require(i < len(lines), 'unclosed code fence')
                require(re.fullmatch(r'[A-Za-z0-9_-]*', language), 'invalid code fence language')
                out.append('<pre tabindex="0"><code class="language-' + language + '">' + html.escape('\n'.join(block)) + '</code></pre>')
                i += 1
                continue
            heading = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading:
                level, title = len(heading[1]), heading[2]
                slug = re.sub(r'[^\w\-]+', '-', title.lower(), flags=re.UNICODE).strip('-') or 'section'
                original, count = slug, 1
                while slug in self.ids:
                    count += 1; slug = original + '-' + str(count)
                self.ids.add(slug)
                self.headings.append((level, title, slug))
                out.append('<h{0} id="{1}">{2}</h{0}>'.format(level, html.escape(slug), self.inline(title)))
                i += 1
                continue
            if i + 1 < len(lines) and line.startswith('|') and re.fullmatch(r'[|\s:-]+', lines[i + 1]) and '-' in lines[i + 1]:
                row = lambda s: [c.strip() for c in s.strip().strip('|').split('|')]
                headers = row(line)
                rows = []
                i += 2
                while i < len(lines) and lines[i].startswith('|'):
                    cells = row(lines[i]); require(len(cells) == len(headers), 'table column mismatch')
                    rows.append('<tr>' + ''.join('<td>' + self.inline(c) + '</td>' for c in cells) + '</tr>')
                    i += 1
                out.append('<div class="table-wrap" tabindex="0"><table><thead><tr>' + ''.join('<th scope="col">' + self.inline(c) + '</th>' for c in headers) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
                continue
            item = re.match(r'^(?:([-+*])|([0-9]+)\.)\s+(.+)$', line)
            if item:
                tag = 'ol' if item[2] else 'ul'
                items = []
                while i < len(lines):
                    m = re.match(r'^(?:([-+*])|([0-9]+)\.)\s+(.+)$', lines[i])
                    if not m or ('ol' if m[2] else 'ul') != tag:
                        break
                    items.append('<li>' + self.inline(m[3]) + '</li>'); i += 1
                out.append('<' + tag + '>' + ''.join(items) + '</' + tag + '>')
                continue
            if line.startswith('> '):
                out.append('<blockquote><p>' + self.inline(line[2:]) + '</p></blockquote>')
                i += 1
                continue
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r'^(#|```|<!--|\||[-+*] |[0-9]+\. |>)', lines[i]):
                paragraph.append(lines[i]); i += 1
            out.append('<p>' + self.inline('\n'.join(paragraph)) + '</p>')
        require(sum(level == 1 for level, _, _ in self.headings) == 1, 'each page must have exactly one h1')
        return '\n'.join(out)


def demo_html(demo, locale, base, download_url):
    zh = locale == 'zh'
    links = []
    if download_url:
        links.append('<a href="' + html.escape(download_url, quote=True) + '">' + ('下载此版本 Skill 包' if zh else 'Download this version’s Skill package') + '</a>')
    for asset in demo.get('assets', []):
        if asset['kind'] == 'download':
            links.append('<a href="' + html.escape(base + asset['path'], quote=True) + '" download>' + ('下载独立教程样本 ZIP' if zh else 'Download the independent tutorial sample ZIP') + '</a>')
    resources = '<aside class="resources">' + ''.join('<p>' + link + '</p>' for link in links) + '</aside>' if links else '<aside class="notice"><p>' + ('样本 ZIP 和安装包演示正在本地核验，完成后才显示可用资源。当前没有虚构下载链接。' if zh else 'The sample ZIP and package demo are awaiting local verification. Available resources will appear after verification.') + '</p></aside>'
    if demo['status'] != 'verified':
        return resources, '<section class="evidence"><h2>' + ('演示核验状态' if zh else 'Demo verification status') + '</h2><p class="notice">' + ('待最终候选安装包的真实操作、录屏与恢复读回。以上是可执行教程，不是已通过的演示回执。' if zh else 'Pending the final candidate package run, real recording, and recovery readback. The steps above are a runnable tutorial, not a successful demo receipt.') + '</p></section>'
    output = ['<section class="evidence"><h2>' + ('已核验的样本演示' if zh else 'Verified sample demonstration') + '</h2><p>' + ('本次合成样本已核对安装包版本、恢复文件读回与当前源文件未变。此结果不代表所有项目均可恢复或运行。' if zh else 'This synthetic run checked the package version, recovered file readback, and unchanged current source. It does not prove every project can be recovered or run.') + '</p>']
    for asset in demo.get('assets', []):
        path = html.escape(base + asset['path'], quote=True)
        caption = html.escape(asset.get('caption', {}).get(locale, ''))
        alt = html.escape(asset.get('alt', {}).get(locale, ''), quote=True)
        if asset['kind'] == 'image':
            media = '<img src="' + path + '" alt="' + alt + '" loading="lazy" decoding="async">'
        elif asset['kind'] == 'video':
            poster = ' poster="' + html.escape(base + asset['poster'], quote=True) + '"' if asset.get('poster') else ''
            tracks = ''.join('<track kind="captions" src="' + html.escape(base + track['src'], quote=True) + '" srclang="' + track['srclang'] + '" label="' + html.escape(track['label'], quote=True) + '"' + (' default' if track['srclang'] == locale else '') + '>' for track in asset.get('tracks', []))
            media = '<video controls preload="metadata" playsinline aria-label="' + alt + '"' + poster + '><source src="' + path + '">' + tracks + '<a href="' + path + '">' + ('下载录屏' if zh else 'Download recording') + '</a></video>'
            caption += ' ' + ('无声录屏；可切换中英字幕。片中历史预览在录制前另行采集；默认 prepare.py 不生成截图。无需采集依赖也能按上方步骤查看 index.html 内容、比较并恢复。' if zh else 'Silent recording with Chinese and English captions. Historical previews were captured separately before recording; prepare.py does not generate screenshots. You can inspect index.html, compare, and recover without capture dependencies.')
        else:
            continue
        output.append('<figure>' + media + '<figcaption>' + caption + '</figcaption></figure>')
    for step in demo.get('steps', []):
        output.append('<details><summary>' + html.escape(step['title'][locale]) + '</summary><p>' + html.escape(step['body'][locale]) + '</p>')
        if step.get('command'):
            output.append('<pre tabindex="0"><code>' + html.escape(step['command']) + '</code></pre>')
        output.append('</details>')
    output.append('<p class="checksum">' + html.escape(demo['package']['filename']) + '<br>SHA-256: ' + demo['package']['sha256'] + '</p></section>')
    return resources, '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/site')
    parser.add_argument('--out', required=True, type=Path, help='New output directory; must not already exist')
    parser.add_argument('--base-path', default='/Reprise/')
    parser.add_argument('--mode', choices=('preview', 'production'), default='preview')
    parser.add_argument('--origin', default='')
    parser.add_argument('--download-url', default='')
    parser.add_argument('--report', type=Path, help='Optional private build report outside output')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.out.resolve()
    require(not output.exists(), 'output already exists; choose a new path to retain earlier artifacts')
    require(source not in output.parents and output not in source.parents, 'output must not contain or be inside docs/site')
    base = args.base_path
    require(re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*', base), 'base path must start/end with / and contain safe path segments')
    if args.report:
        report = args.report.resolve()
        require(report != output and output not in report.parents and not report.exists(), 'report must be new and outside public output')
    meta = json.loads((source / 'content/metadata.json').read_text(encoding='utf-8'))
    version = meta['version']
    production = args.mode == 'production'
    origin = public_https(args.origin, 'origin', origin=True) if args.origin else ''
    download = public_https(args.download_url, 'download URL') if args.download_url else ''
    require(production or not (origin or download), 'preview does not accept public origin/download values')
    if production:
        require(origin and download, 'production requires explicit --origin and --download-url')
        require(meta.get('publish_ready') is True and meta.get('status') in ('released', 'prerelease'), 'production requires reviewed publish_ready=true and status released/prerelease')
    demo = load_demo(source, version, production)
    pages = meta['pages']
    require(len(pages) == 2 * len(SLUGS) and {(p['locale'], p['slug']) for p in pages} == {(l, s) for l in ('zh', 'en') for s in SLUGS}, 'expected matching focused pages in each language')
    known = {p['source']: p['locale'] + '/' + p['slug'] + '.html' for p in pages}
    require(len(known) == 2 * len(SLUGS), 'duplicate page source')
    rendered, link_count = {}, 0
    for p in pages:
        locale, slug = p['locale'], p['slug']
        require(p['source'] == locale + '/' + slug + '.md', 'page source must match locale/slug')
        for field in ('title', 'description'):
            public_text(p[field], 'page ' + field)
        text = public_text((source / 'content' / p['source']).read_text(encoding='utf-8'), p['source'])
        resources, evidence = demo_html(demo, locale, base, download)
        video = next((a for a in demo.get('assets', []) if a['kind'] == 'video' and a.get('poster')), None)
        poster = video['poster'] if video else next((a['path'] for a in demo.get('assets', []) if a['kind'] == 'image' and ('gallery-' + locale) in a['path']), None)
        teaser = ''
        if poster and demo['status'] == 'verified':
            teaser = '<figure class="teaser"><a href="' + base + locale + '/find-compare-restore.html"><img src="' + html.escape(base + poster, quote=True) + '" alt="' + ('Reprise 已安装 Skill 的真实工作台' if locale == 'zh' else 'Actual workbench from the installed Reprise Skill') + '" loading="lazy"></a><figcaption><a href="' + base + locale + '/find-compare-restore.html">' + ('看实际画面与恢复步骤' if locale == 'zh' else 'See actual pictures and recovery steps') + '</a></figcaption></figure>'
        markdown = Markdown(locale, known, base, resources, evidence, teaser)
        body = markdown.render(text)
        link_count += len(markdown.links)
        other = 'en' if locale == 'zh' else 'zh'
        nav = '<span class="nav-label">' + ('使用文档' if locale == 'zh' else 'DOCUMENTATION') + '</span>'
        nav += ''.join('<a class="nav-link" href="' + base + locale + '/' + s + '.html"' + (' aria-current="page"' if s == slug else '') + '>' + NAV[locale][i] + '</a>' for i, s in enumerate(SLUGS))
        nav += '<a class="language" href="' + base + other + '/' + slug + '.html" lang="' + ('en' if other == 'en' else 'zh-Hans') + '">' + ('English' if locale == 'zh' else '简体中文') + '</a>'
        banner = 'Reprise ' + version + (' · 本地候选文档' if locale == 'zh' else ' · Local candidate docs') if not production else 'Reprise ' + version
        extra = seo_tags(origin, base, locale, slug) if production else '<meta name="robots" content="noindex, nofollow">'
        rendered[known[p['source']]] = document(p['title'], p['description'], meta['locale_tags'][locale], base, extra, '<a class="skip" href="#main">' + ('跳到正文' if locale == 'zh' else 'Skip to content') + '</a><header id="top"><a class="brand" href="' + base + locale + '/index.html">Reprise</a><span class="edition">' + banner + '</span></header><div class="layout"><aside class="sidebar"><nav aria-label="' + ('文档导航' if locale == 'zh' else 'Documentation') + '">' + nav + '</nav></aside><div><details class="mobile-nav"><summary>' + ('文档目录 / English' if locale == 'zh' else 'Documentation / 简体中文') + '</summary><nav aria-label="' + ('移动文档导航' if locale == 'zh' else 'Mobile documentation') + '">' + nav + '</nav></details><article id="main">' + body + '<footer>' + ('本地预览 · 不提交索引 · 不提供未发布下载' if locale == 'zh' and not production else 'Local preview · no indexing · no unpublished download' if not production else 'Reprise ' + version) + '<br><a class="back-top" href="#top">' + ('返回页首' if locale == 'zh' else 'Back to top') + '</a></footer></article></div></div>')
    chooser_extra = seo_tags(origin, base, None, 'index') if production else '<meta name="robots" content="noindex, nofollow">'
    chooser = '<header><a class="brand" href="' + base + '">Reprise</a><span class="edition">' + html.escape(version) + (' · Local preview' if not production else '') + '</span></header><main class="chooser"><h1>Save the draft.<br>Find it by its picture.</h1><p class="intro">给本地网页留一稿，以后凭画面找回来。<br>Choose a guide in your language.</p><div class="locale-options"><section class="locale-option" lang="zh-Hans"><h2><a href="' + base + 'zh/index.html">简体中文</a></h2><p>接入 Skill、保存两稿与画面、取回旧稿副本。</p></section><section class="locale-option"><h2><a href="' + base + 'en/index.html">English</a></h2><p>Connect the Skill, save two drafts with pictures, and recover a copy.</p></section></div><footer>' + ('本地预览文档 · Local preview documentation. No public download is linked.' if not production else 'Reprise ' + version) + '</footer></main>'
    rendered['index.html'] = document('Reprise documentation / 使用文档', 'Find, compare, and recover local project versions. 本地项目版本的保存、比较与恢复教程。', 'en', base, chooser_extra, chooser)
    # All validation above precedes output creation. On I/O failure, retain the partial output.
    output.mkdir(parents=True)
    for name, text in rendered.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    (output / 'assets').mkdir()
    shutil.copyfile(source / 'assets/style.css', output / 'assets/style.css')
    assets = {asset['path'] for asset in demo.get('assets', [])}
    for asset in demo.get('assets', []):
        if asset.get('poster'):
            assets.add(asset['poster'])
        assets.update(track['src'] for track in asset.get('tracks', []))
    for name in sorted(assets):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset_path(source, name), target)
    (output / '.nojekyll').write_text('', encoding='utf-8')
    # robots.txt only controls crawlers when served at the origin root. At /Reprise/
    # it is informational; preview exclusion is supplied on every HTML page.
    robots = '# Effective only when served at the origin root. Project-path placement is not a crawler control.\nUser-agent: *\n' + ('Allow: /\nSitemap: ' + origin + base + 'sitemap.xml\n' if production else 'Disallow: /\n')
    (output / 'robots.txt').write_text(robots, encoding='utf-8')
    if production:
        namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        ET.register_namespace('', namespace)
        tree = ET.Element('{' + namespace + '}urlset')
        for name in sorted(rendered):
            item = ET.SubElement(tree, '{' + namespace + '}url')
            ET.SubElement(item, '{' + namespace + '}loc').text = origin + base + ('' if name == 'index.html' else name)
        ET.ElementTree(tree).write(output / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    result = dict(status='built', mode=args.mode, version=version, base_path=base, html_pages=len(rendered), internal_content_links=link_count, demo_status=demo['status'], canonical=production, hreflang=production, sitemap=production, robots_meta='index, follow' if production else 'noindex, nofollow', network_requests=0, deployed=False, files=[dict(path=str(p.relative_to(output)), sha256=digest(p)) for p in sorted(output.rglob('*')) if p.is_file()])
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False, indent=2))


def seo_tags(origin, base, locale, slug):
    route = base + (locale + '/' + slug + '.html' if locale else '')
    tags = ['<meta name="robots" content="index, follow">', '<link rel="canonical" href="' + html.escape(origin + route, quote=True) + '">']
    for language, tag in (('zh', 'zh-Hans'), ('en', 'en')):
        tags.append('<link rel="alternate" hreflang="' + tag + '" href="' + html.escape(origin + base + language + '/' + slug + '.html', quote=True) + '">')
    if slug == 'index':
        tags.append('<link rel="alternate" hreflang="x-default" href="' + html.escape(origin + base, quote=True) + '">')
    image = origin + base + 'assets/reprise-0.8-gallery-' + ('zh' if locale == 'zh' else 'en') + '.png'
    tags.extend(['<meta property="og:type" content="website">', '<meta property="og:url" content="' + html.escape(origin + route, quote=True) + '">', '<meta property="og:image" content="' + html.escape(image, quote=True) + '">', '<meta name="twitter:card" content="summary_large_image">'])
    return '\n'.join(tags)


def document(title, description, language, base, extra, body):
    return '<!doctype html>\n<html lang="' + language + '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><meta name="description" content="' + html.escape(description, quote=True) + '">' + extra + '<meta property="og:title" content="' + html.escape(title, quote=True) + '"><meta property="og:description" content="' + html.escape(description, quote=True) + '"><link rel="stylesheet" href="' + base + 'assets/style.css"></head><body>' + body + '</body></html>\n'


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print('Docs build refused: ' + str(error), file=sys.stderr)
        sys.exit(1)
