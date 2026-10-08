/* Reprise's UI consumes the local API. Import and navigation never execute project code. */
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const short = sha => String(sha || '').slice(0, 8);
const date = value => { if (!value) return '时间未知'; const d = new Date(value); return Number.isNaN(d.valueOf()) ? String(value) : d.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}); };
const iconPaths = {
  plus:'M12 5v14M5 12h14', folder:'M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z',
  git:'M6 3v12m12-6v3a6 6 0 0 1-6 6H9M9 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm12 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  layers:'m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5', camera:'M4 7h4l2-3h4l2 3h4v13H4ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  play:'m8 4 12 8-12 8V4Z', close:'m6 6 12 12M18 6 6 18', chevron:'m9 5 7 7-7 7', refresh:'M20 7v5h-5M4 17v-5h5M5.5 7a8 8 0 0 1 13 0L20 12M4 12l1.5 5a8 8 0 0 0 13 0',
  settings:'M4 7h16M4 17h16M8 4v6m8 4v6', arrow:'M5 19 19 5M6 5h13v13', check:'m5 12 4 4L20 5', info:'M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  file:'M6 3h8l4 4v14H6Zm8 0v5h4M9 12h6m-6 4h6', upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6', stop:'M6 6h12v12H6Z',
  spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z', terminal:'m5 7 5 5-5 5m8 0h6', image:'M3 3h18v18H3Zm0 13 5-5 4 4 3-3 6 6M16 7h.1',
  shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6', branch:'M6 3v18m0-7c8 0 12-3 12-9m-3 3 3-3 3 3', zoom:'M15 15l6 6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0ZM7 10h6m-3-3v6',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPaths[name] || iconPaths.file}"/></svg>`;
const pill = (text, tone = '') => `<span class="pill ${tone}">${esc(text)}</span>`;
const state = {token:'',projects:[],project:null,history:[],hasMore:false,nextOffset:0,ref:'--all',refs:[],version:null,selected:'',base:'',runtimes:[],ai:{},jobs:[],busy:false,loading:false,error:'',selection:0,compareCapture:true,media:[],mediaIndex:0,mediaZoom:'fit',aiProposal:null};
const app = $('#app');
const dialog = $('#dialog');
const mediaDialog = $('#media-dialog');
const jobLabels = {run:'启动版本',capture:'采集版本预览','ai/suggest':'AI 分析配置'};
function normalizeJob(raw, previous = {}) {
  const kind = raw.operation || raw.kind || previous.kind;
  return {...previous,...raw,projectId:raw.project_id || raw.projectId || previous.projectId,kind,body:raw.request || raw.body || previous.body || null,label:jobLabels[kind] || '项目任务',status:raw.status || 'queued'};
}
function recoverJobs(jobs) {
  let dismissed = []; try { dismissed = JSON.parse(localStorage.getItem('reprise.dismissedJobs') || '[]'); } catch (_) {}
  const local = new Map(state.jobs.map(job => [job.id,job]));
  for (const raw of jobs || []) {
    const existing = local.get(raw.id);
    if (existing) Object.assign(existing,normalizeJob(raw,existing));
    else local.set(raw.id,{...normalizeJob(raw),dismissed:dismissed.includes(raw.id)});
  }
  state.jobs = [...local.values()];
}

async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = {'Accept':'application/json', ...(options.headers || {})};
  if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['X-Reprise-Token'] = state.token; }
  const response = await fetch(`/api${path}`, {...options, method, headers, body: options.body === undefined ? undefined : JSON.stringify(options.body)});
  let data;
  try { data = await response.json(); } catch (_) { throw new Error(`本地服务返回了无法读取的内容（${response.status}）。`); }
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）。`);
  return data;
}
function toast(message, error = false) {
  const el = document.createElement('div'); el.className = `toast${error ? ' error' : ''}`; el.textContent = message;
  $('#toast-region').append(el); setTimeout(() => el.remove(), error ? 7500 : 4500);
}
function safeUrl(url) {
  if (!url) return '';
  try { const parsed = new URL(url, location.href); return ['http:','https:'].includes(parsed.protocol) ? parsed.href : ''; } catch (_) { return ''; }
}
function projectType(project) { return project?.detected?.label || project?.detection?.label || 'Git 项目'; }
function aiEnabled() { return Boolean(state.ai.enabled ?? state.ai.config?.enabled ?? state.ai.settings?.enabled); }
function sourceLabel(source) { return ({project:'项目配置',user:'项目配置',override:'项目配置',repository:'仓库内配置',committed:'仓库内配置',detected:'自动识别',auto:'自动识别',none:'尚未配置'})[source] || (source ? '项目配置' : '尚未配置'); }
function activeRecipe() { return state.version?.recipe || state.project?.recipe || state.version?.detection?.recipe || null; }
function approvedRecipe() { return state.version?.recipe_approved ?? state.project?.recipe_approved ?? false; }
function runnable() { const r = activeRecipe(); return Boolean(r && r.adapter !== 'manual' && (r.adapter !== 'command-web' || approvedRecipe())); }
function captureReady() { return runnable() && (activeRecipe().captures || []).length > 0; }
function recipeStatus() {
  const r = activeRecipe();
  if (!r || r.adapter === 'manual') return {text:'需要配置或手工资料',tone:'warn',description:'Git 历史已就绪。可以配置项目运行方式，也可以为精确版本导入已有截图或录像。'};
  if (r.adapter === 'command-web' && !approvedRecipe()) return {text:'等待确认运行配置',tone:'warn',description:'检测到需要执行命令的项目。先检查并保存运行配置，再运行或采集；导入项目时不会执行命令。'};
  if (r.adapter === 'static-web') return {text:'可自动运行与截图',tone:'good',description:'使用当前提交的独立副本启动静态服务，按配置采集截图。整个流程无需 AI。'};
  return {text:'运行配置已保存',tone:'good',description:'将在当前提交的独立副本中执行已保存的命令。截图等待页面、字体、图片及指定的就绪条件。'};
}
function sidebar() {
  return `<aside class="sidebar"><div class="brand"><span class="brand-symbol">R</span><div><div class="brand-name">Reprise</div><div class="brand-sub">VERSIONS, REVISITED.</div></div></div>
    <div class="sidebar-title"><span class="eyebrow">项目 · Projects</span><button class="icon-button" data-action="import" aria-label="导入 Git 项目" title="导入 Git 项目">${icon('plus')}</button></div>
    <nav class="project-nav" aria-label="Git 项目">${state.projects.length ? state.projects.map(p => `<button class="project-item ${state.project?.id === p.id ? 'active' : ''}" data-project="${esc(p.id)}" ${state.project?.id === p.id ? 'aria-current="page"' : ''}><span class="project-icon">${icon('folder')}</span><span class="project-copy"><span class="project-name">${esc(p.name)}</span><span class="project-type">${esc(projectType(p))}</span></span></button>`).join('') : '<p class="sidebar-empty">从一个 Git 仓库开始。<br>每个项目都有独立配置与证据。</p>'}</nav>
    <div class="sidebar-footer"><div class="engine-label"><span class="status-dot"></span>本地 Git 引擎</div><p>项目代码保留在原处<br>历史预览使用独立副本</p><button class="button subtle" data-action="ai-settings">${icon('spark')}AI 助手 ${aiEnabled() ? '· 已启用' : '· 可选'}</button></div></aside>`;
}
function render() {
  state.media = [];
  app.innerHTML = `<div class="app-shell">${sidebar()}<main class="main"><header class="topbar"><div class="breadcrumb">工作空间 ${icon('chevron')}<span>${esc(state.project?.name || '所有项目')}</span></div><div class="topbar-actions"><button class="button subtle" data-action="ai-settings">${icon('spark')}AI ${aiEnabled() ? '已启用' : '可选'}</button><button class="button outline" data-action="import">${icon('plus')}导入项目</button></div></header><div class="content">${state.error ? `<div class="inline-notice error">${icon('info')}<span>${esc(state.error)}</span></div>` : ''}${state.project ? projectView() : emptyView()}</div></main></div>`;
}
function emptyView() {
  return `<section class="empty-main"><div class="empty-illustration" aria-hidden="true"><div class="empty-sheet"></div><div class="empty-branch">${icon('git')}</div></div><div class="eyebrow">A clearer history of your work</div><h1 style="margin-top:12px">每个项目，<br>都有值得看见的过程。</h1><p>连接本地 Git 仓库，读取真实版本记录。<br>为网页、游戏和其他项目配置合适的运行与预览方式。</p><button class="button primary" data-action="import">${icon('plus')}导入第一个 Git 项目</button><div class="empty-features"><article class="empty-feature"><span>01 / READ</span><h2>先读懂 Git 历史</h2><p>分支、提交、真实父版本与文件变化。导入时保持源码不变。</p></article><article class="empty-feature"><span>02 / RUN</span><h2>按项目能力运行</h2><p>静态网页自动识别。框架、游戏及原生项目使用独立的配置。</p></article><article class="empty-feature"><span>03 / VERIFY</span><h2>让预览有据可查</h2><p>截图绑定精确提交与采集场景；也支持导入已有图片和录像。</p></article></div></section>`;
}
function projectView() {
  const p = state.project, repo = p.repository || {}, detection = state.version?.detection || p.detected || {};
  const rs = recipeStatus();
  return `<section class="project-heading"><div><div class="eyebrow">Project workspace</div><h1>${esc(p.name)}</h1><div class="path-row">${icon('folder')}<code>${esc(p.path)}</code></div></div><div class="heading-status">${pill(repo.bare ? '裸仓库' : repo.work_tree ? '工作仓库' : 'Git 仓库')}${repo.shallow ? pill('浅克隆','warn') : ''}${pill('源码只读','good')}</div></section>
    <div class="overview-strip"><div class="overview-item"><span class="overview-icon">${icon('git')}</span><div><p class="overview-label">Git 原生读取</p><p class="overview-value">${esc(repo.branch || (repo.head ? '分离 HEAD' : '尚无提交'))}</p><p class="overview-detail">${repo.head ? `HEAD ${esc(short(repo.head))}` : '首次提交后可查看历史'}</p></div></div><div class="overview-item"><span class="overview-icon cyan">${icon('layers')}</span><div><p class="overview-label">识别到的项目类型</p><p class="overview-value">${esc(detection.label || projectType(p))}</p><p class="overview-detail">根据提交中的文件与配置识别</p></div></div><div class="overview-item"><span class="overview-icon orange">${icon('camera')}</span><div><p class="overview-label">运行与采集能力</p><p class="overview-value">${esc(rs.text)}</p><p class="overview-detail">AI ${aiEnabled() ? '仅在请求时参与' : '未启用 · 基础流程独立工作'}</p></div></div></div>
    <div id="jobs-region">${jobsView()}</div><div class="workspace"><section class="panel history-panel"><div class="panel-header"><h2>${icon('git')}提交历史</h2><button class="icon-button" data-action="refresh" aria-label="刷新 Git 历史" title="刷新 Git 历史">${icon('refresh')}</button></div><label class="ref-filter"><span class="sr-only">选择分支或引用</span><select id="ref-select"><option value="--all">所有分支与标签</option>${state.refs.map(r => `<option value="${esc(r.name)}" ${r.name === state.ref ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select></label><div class="history-list">${state.loading && !state.history.length ? '<div class="section-loading"><span class="spinner"></span>读取 Git…</div>' : state.history.length ? state.history.map(commitRow).join('') : '<p class="empty-inline">仓库中还没有提交。<br>创建首次提交后，点击刷新即可读取。</p>'}</div>${state.hasMore ? '<div class="history-more"><button class="button subtle" data-action="load-more">加载更早的提交</button></div>' : ''}</section>
    <div class="detail-column">${state.loading ? '<div class="panel loading"><span class="spinner"></span>读取精确版本…</div>' : state.version ? versionView() : '<div class="panel empty-inline">选择一条提交，查看变化与预览。<br>没有提交时仍可保存项目运行配置。<br><button class="button outline" style="margin-top:16px" data-action="recipe">配置项目</button></div>'}</div></div>
    ${runtimesView()}<footer class="footer-note"><span>Git 提供版本事实 · 适配器负责运行 · 采集结果绑定版本与配置</span><span>Reprise / Local workspace</span></footer>`;
}
function commitRow(c) {
  return `<button class="commit-row ${c.sha === state.selected ? 'active' : ''}" data-sha="${esc(c.sha)}" ${c.sha === state.selected ? 'aria-current="true"' : ''}><span class="commit-subject">${esc(c.subject || '无提交说明')}</span><span class="commit-meta"><code>${esc(short(c.sha))}</code><span>${esc(date(c.committed_at || c.authored_at))}</span></span>${c.refs?.length ? `<span class="commit-refs">${c.refs.slice(0, 2).map(r => pill(typeof r === 'string' ? r.replace(/^refs\/(heads|tags)\//,'') : r.name)).join('')}${c.parents?.length > 1 ? pill('合并') : ''}</span>` : c.parents?.length > 1 ? '<span class="commit-refs"><span class="pill">合并提交</span></span>' : ''}</button>`;
}
function versionView() {
  const v = state.version, c = v.commit || state.history.find(c => c.sha === state.selected) || {sha:state.selected}, d = v.detection || {}, rs = recipeStatus();
  const warnings = [...new Set([...(d.warnings || []), ...(v.warnings || []), ...(v.recipe_error ? [v.recipe_error] : [])])];
  const author = typeof c.author === 'object' ? c.author.name : c.author;
  return `<section class="panel version-summary"><div class="version-topline"><span class="eyebrow">Selected revision</span><code title="${esc(c.sha)}">${esc(short(c.sha))}</code>${c.parents?.length > 1 ? pill(`${c.parents.length} 个真实父提交`,'orange') : !c.parents?.length ? pill('首次提交') : ''}</div><h2>${esc(c.subject || '无提交说明')}</h2><div class="version-byline"><span>${esc(author || '未知作者')}</span><span>${esc(date(c.committed_at || c.authored_at))}</span><span>${esc(d.label || projectType(state.project))}</span></div><div class="version-actions"><button class="button primary" data-action="run">${icon('play')}${runnable() ? '运行这个版本' : '配置运行方式'}</button><button class="button outline" data-action="capture">${icon('camera')}${captureReady() ? '自动采集预览' : '配置自动采集'}</button><button class="button subtle" data-action="recipe">${icon('settings')}项目配置</button></div>${warnings.slice(0,3).map(w => `<div class="inline-notice warn">${icon('info')}<span>${esc(typeof w === 'string' ? w : w.message || JSON.stringify(w))}</span></div>`).join('')}</section>
    <section class="panel detail-section"><div class="section-title"><h3>${icon('layers')}项目能力</h3><span class="small muted">${esc(sourceLabel(v.recipe_source || state.project.recipe_source))}</span></div><div class="recipe-status"><div><div class="capability-list">${pill('历史可读','good')}${pill('变化可比','good')}${pill(rs.text,rs.tone)}${pill('支持手工资料')}</div><p>${esc(rs.description)}</p></div><button class="button outline" data-action="ai-suggest" title="AI 只提出建议，运行配置须由你保存">${icon('spark')}AI 建议</button></div>${d.signals?.length ? `<div class="detection-signals">${d.signals.slice(0,5).map(s => `<span>${esc(typeof s === 'string' ? s : s.path || s.message || JSON.stringify(s))}</span>`).join('')}</div>` : ''}</section>
    <section class="panel detail-section"><div class="section-title"><h3>${icon('file')}这个版本改了什么</h3>${diffCounts(v.diff)}</div><div class="compare-controls"><label for="base-select">比较基准</label><select id="base-select">${(c.parents || v.diff?.parents || []).length ? (c.parents || v.diff.parents).map((sha,i) => `<option value="${esc(sha)}" ${sha === state.base ? 'selected' : ''}>父提交 ${i+1} · ${esc(short(sha))}${i === 0 ? '（第一父提交）' : ''}</option>`).join('') : '<option value="">空树（这是首次提交）</option>'}</select></div>${diffView(v.diff)}</section>
    <section class="panel detail-section"><div class="section-title"><h3>${icon('camera')}版本预览与证据</h3><span class="small muted">${(v.evidence || []).length} 次采集记录</span></div><p class="section-subtitle">图片、录像绑定提交与场景。两个版本使用同一份采集配置进行对比。</p><div class="evidence-toolbar"><label class="capture-option"><input id="compare-capture" type="checkbox" ${state.compareCapture ? 'checked' : ''} ${state.base ? '' : 'disabled'}>同时采集所选父版本${state.base ? ` ${esc(short(state.base))}` : '（无父版本）'}</label><button class="button outline" data-action="manual">${icon('upload')}导入已有资料</button></div>${evidenceView(v.evidence || [])}</section>`;
}
function diffCounts(diff) {
  if (!diff || diff.available === false) return '';
  const files = diff.files || [], c = diff.counts || {};
  const count = status => c[status] ?? c[({A:'added',M:'modified',D:'deleted'})[status]] ?? files.filter(f => String(f.status).startsWith(status)).length;
  return `<div class="change-counts"><span class="added">+${count('A')}</span><span class="modified">~${count('M')}</span><span class="deleted">−${count('D')}</span></div>`;
}
function diffView(diff) {
  if (!diff) return '<div class="empty-inline">文件变化暂不可用。</div>';
  if (diff.available === false) return `<div class="inline-notice warn">${icon('info')}<span>当前仓库缺少完整的比较对象，暂时无法计算文件变化。${diff.error ? `<br>${esc(diff.error)}` : ''}</span></div>`;
  const files = diff.files || [];
  if (!files.length) return '<div class="empty-inline">与所选基准相比，文件内容没有变化。</div>';
  return `<div class="file-list">${files.map(f => `<div class="file-row"><span class="file-status ${esc(String(f.status).slice(0,1))}" title="${esc(f.status)}">${esc(String(f.status).slice(0,1))}</span><div class="file-path">${f.old_path ? `<del>${esc(f.old_path)} →</del>` : ''}<code>${esc(f.path)}</code></div></div>`).join('')}</div>${diff.truncated ? '<p class="small muted" style="margin-top:8px">文件列表已截断，详情以 Git 原始记录为准。</p>' : ''}`;
}
function evidenceView(records) {
  if (!records.length) return `<div class="empty-evidence"><span class="empty-icon">${icon('image')}</span><div><h3>这个版本还没有预览资料</h3><p>${captureReady() ? '点击「自动采集预览」，从精确提交启动项目并截图。基础采集无需 AI。' : '先配置适合此项目的运行与采集方式；原生游戏、命令行工具也可以导入手工截图、录像或文件。'}</p></div></div>`;
  // The API returns newest first. Render every retained item once so media
  // indexes remain stable when native <details> reveals earlier records.
  const rendered = records.map(record => {
    const items = record.items || [], manual = record.manual || record.source === 'manual' || record.kind === 'manual' || record.type === 'manual', legacy = record.source === 'legacy';
    const groups = [];
    for (const original of items) {
      const item = {...original}, label = item.capture_id || item.scenario || item.title || 'default', category = /video/i.test(item.media_type || item.kind || '') ? 'video' : /image/i.test(item.media_type || item.kind || '') ? 'image' : 'file', key = `${label}:${category}`;
      if (category === 'video') {
        const poster = items.find(candidate => /image/i.test(candidate.media_type || candidate.kind || '') && !candidate.missing && candidate.url && (candidate.capture_id || candidate.scenario || candidate.title || 'default') === label && candidate.side === item.side && candidate.sha === item.sha);
        if (poster) item.poster = poster.url;
      }
      let group = groups.find(g => g.key === key); if (!group) {group = {key,label,category,items:[]}; groups.push(group);} group.items.push(item);
    }
    const errors = record.errors || [];
    return `<article class="evidence-record"><div class="evidence-record-header"><span>${pill(manual ? '手工导入 · 未自动验证' : legacy ? '历史资料导入' : record.status === 'failed' ? '采集失败' : record.status === 'partial' ? '部分采集完成' : '自动采集',manual || legacy ? 'warn' : record.status === 'failed' ? 'bad' : 'good')} <span>${esc(date(record.created_at || record.completed_at || record.at))}</span></span><code title="${esc(record.recipe_hash || '')}">${record.recipe_hash ? `配置 ${esc(String(record.recipe_hash).slice(0,8))}` : esc(short(record.sha))}</code></div>${legacy ? '<p class="section-subtitle" style="margin-top:3px">此记录来自旧版资料库，保留原有来源，不视为新采集结果。</p>' : ''}${errors.length ? `<div class="evidence-errors">${errors.map(e => esc(typeof e === 'string' ? e : e.error || e.message || JSON.stringify(e))).join('<br>')}</div>` : ''}${groups.map(group => `${identicalImagePair(group,record) ? '<div class="inline-notice" style="margin-bottom:10px">两版在此采集场景中画面相同</div>' : ''}<div class="evidence-pair ${group.items.length === 1 ? 'single' : ''}" style="margin-bottom:10px">${group.items.map(item => mediaTile(item, record, group.label)).join('')}</div>`).join('') || '<div class="evidence-missing">此记录没有可显示的图片或录像。<br>请查看采集错误，修正配置后重试。</div>'}</article>`;
  });
  return rendered[0] + (rendered.length > 1 ? `<details class="older-evidence"><summary>较早的采集记录（${rendered.length - 1}）</summary><div class="older-evidence-records">${rendered.slice(1).join('')}</div></details>` : '');
}
function identicalImagePair(group,record) {
  if (!record.base || group.category !== 'image' || group.items.length !== 2) return false;
  const [a,b] = group.items;
  return !a.missing && !b.missing && a.side !== b.side && a.content_sha256 && a.content_sha256 === b.content_sha256;
}
function mediaTile(item, record, key) {
  const mediaType = item.media_type || item.kind || '', url = item.missing ? '' : safeUrl(item.url || ''), poster = safeUrl(item.poster || ''), isVideo = /video|webm|mp4/i.test(mediaType), isImage = /image|png|jpg|jpeg|webp|gif/i.test(mediaType);
  const isBase = ['base','before','previous'].includes(item.side) || (record.base && item.sha === record.base);
  const side = isBase ? '父版本' : '当前版本', label = item.title || key || '预览', dimensions = item.width && item.height ? `${item.width} × ${item.height}` : '';
  const index = state.media.push({...item,url,poster,isVideo,isImage,title:`${side} · ${label}`,record}) - 1;
  const diagnostics = item.diagnostics || item.warnings || [];
  return `<figure class="evidence-tile" style="margin:0"><div class="evidence-tile-header"><strong>${esc(side)} · ${esc(short(item.sha || record.sha))}</strong><span>${esc(label)}</span></div>${url && isImage ? `<button class="evidence-open" data-media="${index}" aria-label="放大 ${esc(label)}"><img src="${esc(url)}" alt="${esc(side)} ${esc(label)}" loading="lazy" ${item.width && item.height ? `width="${Number(item.width)}" height="${Number(item.height)}"` : ''}></button>` : url && isVideo ? `<video src="${esc(url)}" ${poster ? `poster="${esc(poster)}"` : ''} controls preload="metadata" playsinline aria-label="${esc(label)}"></video>` : url ? `<div class="evidence-missing">${icon('file')}<p style="margin-top:9px">文件资料</p><a class="button outline" href="${esc(url)}" target="_blank" rel="noopener" style="margin-top:10px">打开文件 ${icon('arrow')}</a></div>` : `<div class="evidence-missing">${item.missing ? '该版本没有可用的场景资料' : '没有可访问的资料地址'}${item.error ? `<br>${esc(item.error)}` : ''}</div>`}${diagnostics.length ? `<div class="evidence-errors" style="padding:0 10px">采集诊断：${esc(typeof diagnostics === 'string' ? diagnostics : diagnostics.map(d => typeof d === 'string' ? d : d.message || JSON.stringify(d)).join('；'))}</div>` : ''}<figcaption class="evidence-tile-footer"><span>${esc(dimensions || (isVideo ? '原始录像' : '版本资料'))}</span><span>${url && (isImage || isVideo) ? `<button data-media="${index}">${icon('zoom')}放大</button>` : ''}${url ? ` <a href="${esc(url)}" target="_blank" rel="noopener">原文件 ↗</a>` : ''}</span></figcaption></figure>`;
}
function jobsView() {
  const jobs = state.jobs.filter(j => j.projectId === state.project?.id && !j.dismissed);
  return jobs.length ? `<section class="jobs" aria-label="操作进度">${jobs.map(j => `<article class="job ${j.status === 'failed' ? 'failed' : ''}">${['running','queued'].includes(j.status) ? '<span class="spinner"></span>' : icon(j.status === 'failed' ? 'info' : 'check')}<div class="job-copy"><strong>${esc(j.label)} · ${{queued:'等待执行',running:'正在执行',complete:'已完成',failed:'失败'}[j.status] || esc(j.status)}${j.body?.sha ? ` · ${esc(short(j.body.sha))}` : ''}</strong><p>${esc(j.connection_error || j.error || j.progress?.message || (j.status === 'complete' ? '结果已保留，可继续查看。' : '在独立目录中执行，日志和产物会保留。'))}</p></div>${j.status === 'complete' && j.kind === 'ai/suggest' ? `<button class="button outline" data-review-job="${esc(j.id)}">查看提案</button>` : ''}${j.status === 'failed' && j.body?.sha ? `<button class="button outline" data-retry-job="${esc(j.id)}">重试</button>` : ''}${j.status === 'complete' || j.status === 'failed' ? `<button class="icon-button" data-dismiss-job="${esc(j.id)}" aria-label="收起操作结果">${icon('close')}</button>` : ''}</article>`).join('')}</section>` : '';
}
function runtimesView() {
  const runtimes = state.runtimes.filter(r => (!r.project_id || r.project_id === state.project?.id) && (r.alive || r.running || ['running','starting'].includes(r.status)));
  if (!runtimes.length) return '';
  return `<section class="runtimes"><div class="section-title"><h3>${icon('terminal')}运行中的预览</h3><span class="small muted">${runtimes.length} 个独立副本</span></div><div class="runtime-list">${runtimes.map(r => `<article class="runtime-row"><div class="runtime-info">${pill('运行中','good')} <code>${esc(short(r.sha))}</code> · ${esc(r.adapter || '项目服务')}<a class="runtime-url" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.url)}</a></div><div class="runtime-actions"><a class="button outline" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">打开预览 ${icon('arrow')}</a><button class="button outline" data-stop="${esc(r.id)}">${icon('stop')}停止</button></div></article>`).join('')}</div></section>`;
}

async function bootstrap() {
  try {
    const data = await api('/bootstrap'); state.token = data.token; state.projects = data.projects || []; state.runtimes = data.runtimes || []; state.ai = data.ai || {}; state.error = ''; recoverJobs(data.jobs);
    let saved; try { saved = localStorage.getItem('reprise.project'); } catch (_) {}
    const next = state.projects.find(p => p.id === state.project?.id) || state.projects.find(p => p.id === saved) || state.projects[0];
    render(); if (next) await selectProject(next.id);
    for (const job of state.jobs) if (['queued','running'].includes(job.status)) pollJob(job);
  } catch (e) { state.error = e.message; render(); }
}
async function selectProject(id) {
  const seq = ++state.selection;
  state.project = state.projects.find(p => p.id === id); state.version = null; state.history = []; state.refs = []; state.ref = '--all'; state.selected = ''; state.base = ''; state.loading = true; state.error = ''; render();
  try {
    const [project,history,refs] = await Promise.all([api(`/projects/${encodeURIComponent(id)}`),api(`/projects/${encodeURIComponent(id)}/history?limit=50`),api(`/projects/${encodeURIComponent(id)}/refs`)]);
    if (seq !== state.selection) return;
    state.project = project; state.history = history.commits || []; state.hasMore = history.has_more; state.nextOffset = history.next_offset; state.refs = refs.refs || []; state.loading = false;
    try { localStorage.setItem('reprise.project', id); } catch (_) {}
    render(); if (state.history[0]) await selectVersion(state.history[0].sha);
  } catch (e) { if (seq !== state.selection) return; state.loading = false; state.error = e.message; render(); }
}
async function selectVersion(sha) {
  const seq = ++state.selection, projectId = state.project.id;
  state.selected = sha; state.loading = true; state.error = ''; render();
  try {
    const v = await api(`/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(sha)}`);
    if (seq !== state.selection) return;
    state.version = v; state.base = v.diff?.base || v.commit?.parents?.[0] || ''; state.loading = false; render();
  } catch (e) { if (seq !== state.selection) return; state.loading = false; state.version = null; state.error = e.message; render(); }
}
async function loadHistory(more = false) {
  if (!state.project) return;
  const projectId = state.project.id, ref = state.ref, seq = ++state.selection;
  const button = $('[data-action="load-more"]'); if (button) button.disabled = true;
  try {
    const result = await api(`/projects/${encodeURIComponent(projectId)}/history?ref=${encodeURIComponent(ref)}&offset=${more ? state.nextOffset || state.history.length : 0}&limit=50`);
    if (seq !== state.selection) return;
    state.history = more ? [...state.history, ...(result.commits || [])] : result.commits || []; state.hasMore = result.has_more; state.nextOffset = result.next_offset;
    if (!more && !state.history.some(c => c.sha === state.selected)) { state.version = null; state.selected = ''; render(); if (state.history[0]) await selectVersion(state.history[0].sha); } else render();
  } catch (e) { toast(e.message,true); if (button) button.disabled = false; }
}
async function chooseBase(base) {
  const seq = ++state.selection, sha = state.selected, projectId = state.project.id;
  try { const diff = await api(`/projects/${encodeURIComponent(projectId)}/diff?target=${encodeURIComponent(sha)}${base ? `&base=${encodeURIComponent(base)}` : ''}`); if (seq !== state.selection) return; state.base = diff.base || ''; state.version.diff = diff; render(); } catch (e) { toast(e.message,true); }
}
function showDialog(title, body, footer = '', {onSubmit} = {}) {
  if (dialog.open) dialog.close();
  dialog.innerHTML = `<form id="dialog-form"><header class="dialog-header"><h2 id="dialog-title">${esc(title)}</h2><button type="button" class="icon-button" data-close-dialog aria-label="关闭">${icon('close')}</button></header><div class="dialog-body">${body}<div id="form-error" class="form-error" role="alert"></div></div><footer class="dialog-footer"><button type="button" class="button subtle" data-close-dialog>取消</button>${footer}</footer></form>`;
  $('#dialog-form').addEventListener('submit', async event => { event.preventDefault(); if (!onSubmit) return; const submit = $('button[type="submit"]',dialog); if (submit) submit.disabled = true; $('#form-error').textContent = ''; try { await onSubmit(new FormData(event.currentTarget)); } catch (e) { $('#form-error').textContent = e.message; } finally { if (submit) submit.disabled = false; }});
  dialog.showModal();
}
function importDialog() {
  showDialog('导入 Git 项目', `<p class="dialog-description">输入本机的仓库路径。Reprise 直接读取 Git 对象、引用与提交关系，支持普通仓库、worktree 和裸仓库。</p><label class="field"><span class="field-label">仓库完整路径</span><input name="path" placeholder="/Users/you/projects/my-project" required autofocus autocomplete="off"><small>项目代码保留在原处。导入不会安装依赖、构建或执行项目代码。</small></label><label class="field"><span class="field-label">显示名称 <span class="muted">可选</span></span><input name="name" placeholder="默认使用仓库目录名" maxlength="100"></label><div class="dialog-callout">${icon('shield')} Git 历史总是先读取；运行和自动采集能力会根据这个项目的文件与配置单独判断。</div>`, '<button class="button primary" type="submit">读取并导入</button>', {onSubmit:async form => { const project = await api('/projects',{method:'POST',body:{path:form.get('path').trim(), ...(form.get('name').trim() ? {name:form.get('name').trim()} : {})}}); const i = state.projects.findIndex(p => p.id === project.id); if (i >= 0) state.projects[i] = project; else state.projects.push(project); dialog.close(); await selectProject(project.id); toast('项目已导入，未执行项目代码。'); }});
}
const recipeTemplates = {
  'static-web':{schema:1,adapter:'static-web',root:'.',readiness:{path:'/',timeout_ms:15000},captures:[{id:'home',route:'/',viewport:{width:1440,height:900,scale:2},full_page:true,steps:[]}],network:'local'},
  'command-web':{schema:1,adapter:'command-web',root:'.',commands:{start:['npm','run','dev','--','--host','127.0.0.1','--port','{port}']},readiness:{path:'/',timeout_ms:30000},captures:[{id:'home',route:'/',viewport:{width:1440,height:900,scale:2},full_page:false,steps:[]}],network:'local'},
  manual:{schema:1,adapter:'manual',root:'.',captures:[],network:'local'},
};
function recipeDialog(proposal = null) {
  const existing = proposal?.recipe || proposal?.proposal?.recipe || activeRecipe() || recipeTemplates['manual'];
  const explanation = proposal?.summary || proposal?.explanation || proposal?.reason || '';
  showDialog(proposal ? '审阅 AI 提出的配置' : '项目运行与采集配置', `${proposal ? `<div class="dialog-callout">AI 提案尚未生效。请核对命令、目录、页面和等待条件；只有明确保存后，后续运行或采集才会使用它。</div>${explanation ? `<div class="ai-proposal">${esc(explanation)}</div>` : ''}` : '<p class="dialog-description">每个项目独立配置运行适配器和采集场景。同一场景会用于两个精确版本。AI 可帮助提出配置，基础运行和截图无需 AI。</p>'}<label class="field"><span class="field-label">使用配置模板 <span class="muted">切换会替换下方草稿</span></span><select id="recipe-template"><option value="">保留当前配置</option value="static-web">静态网页 / 已构建的 Web 游戏</option><option value="command-web">需启动命令的网页 / Web 游戏</option><option value="manual">原生应用 / 游戏 / CLI（手工资料）</option></select></label><p class="recipe-help"><code>root</code> 相对于提交根目录。命令使用参数数组，端口填写 <code>{port}</code>。<code>captures</code> 定义路由、视口、就绪条件与操作步骤。</p><label class="field"><span class="field-label">配置 JSON</span><textarea class="recipe-editor" name="recipe" spellcheck="false" required>${esc(JSON.stringify(existing,null,2))}</textarea></label><label class="checkbox-field"><input type="checkbox" name="reviewed" required><span>我已核对这份配置，授权后续点击「运行」或「采集」时执行其中的命令。<small>保存配置本身不会运行项目。执行使用独立副本，保留日志和产物。</small></span></label>`, '<button class="button primary" type="submit">保存并确认配置</button>', {onSubmit:async form => { let recipe; try {recipe = JSON.parse(form.get('recipe'));} catch(e){throw new Error(`JSON 格式不正确：${e.message}`);} const project = await api(`/projects/${encodeURIComponent(state.project.id)}/recipe`,{method:'PUT',body:{recipe}}); state.project = project; state.projects = state.projects.map(p => p.id === project.id ? project : p); dialog.close(); if (state.selected) await selectVersion(state.selected); else render(); toast('配置已保存。可点击运行或采集开始执行。'); }});
  $('#recipe-template').addEventListener('change',event => { if (recipeTemplates[event.target.value]) $('[name="recipe"]',dialog).value = JSON.stringify(recipeTemplates[event.target.value],null,2); });
  $('[name="recipe"]',dialog).addEventListener('keydown',event => { if (event.key === 'Tab') {event.preventDefault();const el=event.target,start=el.selectionStart,end=el.selectionEnd;el.setRangeText('  ',start,end,'end');} });
}
function manualDialog() {
  showDialog('为当前版本导入资料', `<p class="dialog-description">将本地截图、录像或其他文件复制到证据库，绑定提交 <code>${esc(short(state.selected))}</code>。原文件会保留，资料明确标记为手工导入。</p><label class="field"><span class="field-label">本地文件完整路径</span><input name="path" placeholder="/Users/you/Desktop/screenshot.png" required autofocus autocomplete="off"></label><div class="field-grid"><label class="field"><span class="field-label">资料类型</span><select name="kind"><option value="image">图片 / 截图</option><option value="video">视频 / 录屏</option><option value="file">其他文件</option></select></label><label class="field"><span class="field-label">标题</span><input name="title" placeholder="例如：关卡 1 · 完成画面" required maxlength="200"></label></div><label class="field"><span class="field-label">场景标识 <span class="muted">可选</span></span><input name="capture_id" placeholder="level-1-finished"><small>用相同标识组织同一场景的资料。手工导入不会自动证明内容来自该提交。</small></label>`, '<button class="button primary" type="submit">复制并绑定这个版本</button>', {onSubmit:async form => { await api(`/projects/${encodeURIComponent(state.project.id)}/evidence/manual`,{method:'POST',body:{sha:state.selected,path:form.get('path').trim(),kind:form.get('kind'),title:form.get('title').trim(),...(form.get('capture_id').trim() ? {capture_id:form.get('capture_id').trim()} : {})}}); dialog.close(); await refreshEvidence(); toast('资料已复制到证据库，原文件保持不变。'); }});
}
async function aiSettingsDialog() {
  try { state.ai = await api('/ai'); } catch(e) { toast(e.message,true); }
  const config = state.ai.config || state.ai.settings || state.ai;
  showDialog('可选 AI 助手', `<p class="dialog-description">AI 只在你点击「AI 建议」时分析当前项目并提出结构化配置。Git 读取、版本运行、截图与资料管理独立工作。</p><label class="checkbox-field"><input type="checkbox" name="enabled" ${aiEnabled() ? 'checked' : ''}><span>启用 AI 配置建议<small>模型返回的提案需要你检查并保存，不会自动运行或覆盖配置。</small></span></label><label class="field"><span class="field-label">服务类型</span><select name="provider"><option value="compatible">Chat Completions 兼容服务</option></select></label><label class="field"><span class="field-label">服务地址</span><input name="endpoint" value="${esc(config.endpoint || '')}" placeholder="https://your-provider.example/v1" type="url"></label><label class="field"><span class="field-label">模型名称</span><input name="model" value="${esc(config.model || '')}" placeholder="填写服务支持的模型名称" autocomplete="off"></label><label class="field"><span class="field-label">API Key</span><input name="api_key" type="password" placeholder="${config.has_api_key || state.ai.has_api_key ? '已设置；留空保持原值' : '填写密钥（不会返回给浏览器）'}" autocomplete="new-password"><small>密钥仅保存在本机私有配置中。模型名称由你设置，不会自动切换。</small></label><div class="dialog-callout">仅点击「AI 建议」时才发送当前提交的清单文件、最多 300 条文件路径、变化文件名与识别信息；启动工作台不会请求模型。请仅连接你愿意向其发送这些信息的服务。</div>`, '<button class="button primary" type="submit">保存 AI 设置</button>', {onSubmit:async form => { const payload = {enabled:form.has('enabled'),provider:'compatible',endpoint:form.get('endpoint').trim(),model:form.get('model').trim()}; const key = form.get('api_key').trim(); if (key) payload.api_key = key; state.ai = await api('/ai',{method:'PUT',body:payload}); dialog.close(); render(); toast('AI 设置已保存，尚未发送模型请求。'); }});
}
async function startAction(kind) {
  if (!state.project || !state.selected) return;
  if (kind === 'run' && !runnable() || kind === 'capture' && !captureReady()) { recipeDialog(); return; }
  if (kind === 'ai/suggest' && !aiEnabled()) { await aiSettingsDialog(); return; }
  const projectId = state.project.id, sha = state.selected;
  const body = {sha,...(kind === 'capture' && state.compareCapture && state.base ? {base:state.base} : {})};
  const existing = state.jobs.find(j => j.projectId === projectId && j.kind === kind && j.body?.sha === sha && ['running','queued'].includes(j.status));
  if (existing) {toast('这个版本已有相同操作正在进行。');return;}
  try { const result = await api(`/projects/${encodeURIComponent(projectId)}/${kind}`,{method:'POST',body}); const job = normalizeJob(result,{projectId,kind,body}); state.jobs.push(job); render(); if (['complete','failed'].includes(job.status)) await onJobFinished(job); else pollJob(job); } catch(e) { toast(e.message,true); }
}
async function pollJob(job) {
  if (job.polling) return;
  job.polling = true;
  try {
    while (['queued','running'].includes(job.status)) {
      await new Promise(resolve => setTimeout(resolve, Math.min(15000,1000 * (1 + (job.pollErrors || 0)))));
      try {
        const result = await api(`/jobs/${encodeURIComponent(job.id)}`); Object.assign(job,normalizeJob(result,job)); job.pollErrors = 0; job.connection_error = '';
        if (['complete','failed'].includes(job.status)) { render(); await onJobFinished(job); return; }
      } catch(e) { job.pollErrors = (job.pollErrors || 0) + 1; job.connection_error = `正在重新连接本地服务；原任务状态尚未确认。${e.message}`; }
      const region = $('#jobs-region'); if (region) region.innerHTML = jobsView();
    }
  } finally { job.polling = false; }
}
async function onJobFinished(job) {
  if (job.status === 'failed') {
    if (job.kind === 'capture' && state.project?.id === job.projectId && state.selected === job.body?.sha) {
      try { await refreshEvidence(); } catch (_) {}
    }
    toast(job.error || `${job.label}失败，请检查日志和项目配置。`,true); return;
  }
  if (job.kind === 'ai/suggest') {
    state.aiProposal = job.result;
    if (state.project?.id === job.projectId && state.selected === job.body?.sha) recipeDialog(job.result);
    else toast('AI 提案已完成；切换回对应项目后点击「查看提案」。');
  }
  try { const data = await api('/bootstrap'); state.runtimes = data.runtimes || []; state.ai = data.ai || state.ai; } catch (_) {}
  if (state.project?.id === job.projectId && state.selected === job.body?.sha && job.kind === 'capture') await refreshEvidence(); else render();
  if (job.kind !== 'ai/suggest') toast(job.kind === 'run' ? '版本已启动，可在运行中的预览里打开。' : '采集已结束，结果与诊断已保留。');
}
async function refreshEvidence() {
  const projectId = state.project?.id, sha = state.selected;
  if (!projectId || !sha) return;
  const result = await api(`/projects/${encodeURIComponent(projectId)}/evidence?sha=${encodeURIComponent(sha)}`);
  if (state.project?.id === projectId && state.selected === sha && state.version) {state.version.evidence = result.evidence || [];render();}
}
function showMedia(index) {
  const item = state.media[index]; if (!item) return;
  state.mediaIndex = index; state.mediaZoom = 'fit';
  if (mediaDialog.open) mediaDialog.close();
  mediaDialog.innerHTML = `<header class="media-dialog-header"><div class="media-dialog-title"><h2 id="media-dialog-title">${esc(item.title)}</h2><p>${esc(short(item.sha || item.record.sha))} · ${item.width && item.height ? `${item.width} × ${item.height}` : '原始资料'} · ${item.record.recipe_hash ? `配置 ${esc(String(item.record.recipe_hash).slice(0,8))}` : '手工资料'}</p></div><div class="media-zoom-controls"><button class="button active" data-zoom="fit">适应窗口</button><button class="button" data-zoom="1">100%</button><button class="button" data-zoom="2">200%</button><a class="button outline" href="${esc(item.url)}" target="_blank" rel="noopener">原文件 ↗</a><button class="icon-button" data-close-media aria-label="关闭预览">${icon('close')}</button></div></header><div class="media-canvas fit">${item.isVideo ? `<video src="${esc(item.url)}" ${item.poster ? `poster="${esc(item.poster)}"` : ''} controls preload="metadata" playsinline></video>` : `<img src="${esc(item.url)}" alt="${esc(item.title)}" loading="eager" decoding="async">`}</div>`;
  const media = $('img,video',mediaDialog);
  media.addEventListener('error',() => { $('.media-canvas',mediaDialog).innerHTML = '<div class="media-error">此资料没有成功加载。检查本地服务是否运行，然后重试。<br><button class="button outline" data-retry-media>重新加载</button></div>'; });
  mediaDialog.showModal();
}
function setZoom(value) {
  const media = $('img,video',mediaDialog); if (!media) return;
  const item = state.media[state.mediaIndex], canvas = $('.media-canvas',mediaDialog);
  state.mediaZoom = value; canvas.classList.toggle('fit',value === 'fit');
  for (const button of mediaDialog.querySelectorAll('[data-zoom]')) button.classList.toggle('active',button.dataset.zoom === value);
  if (value === 'fit') {media.style.width='';media.style.height='';} else { const width = media.naturalWidth || media.videoWidth || item.width; if (!width) {toast('资料尺寸尚未载入，请稍后再试。');return;} media.style.width = `${width * Number(value)}px`; media.style.height='auto'; }
}
mediaDialog.addEventListener('close',() => { const video = $('video',mediaDialog); if (video) {video.pause();video.removeAttribute('src');video.load();} });
document.addEventListener('click',async event => {
  const target = event.target.closest('button,a'); if (!target) return;
  if (target.hasAttribute('data-close-dialog')) {dialog.close();return;}
  if (target.hasAttribute('data-close-media')) {mediaDialog.close();return;}
  if (target.hasAttribute('data-retry-media')) {showMedia(state.mediaIndex);return;}
  if (target.dataset.zoom) {setZoom(target.dataset.zoom);return;}
  if (target.dataset.media !== undefined) {showMedia(Number(target.dataset.media));return;}
  if (target.dataset.project) {await selectProject(target.dataset.project);return;}
  if (target.dataset.sha) {await selectVersion(target.dataset.sha);return;}
  if (target.dataset.dismissJob) {const job=state.jobs.find(j=>j.id===target.dataset.dismissJob);if(job)job.dismissed=true;try{localStorage.setItem('reprise.dismissedJobs',JSON.stringify(state.jobs.filter(j=>j.dismissed).map(j=>j.id).slice(-100)));}catch(_){}render();return;}
  if (target.dataset.reviewJob) {const job=state.jobs.find(j=>j.id===target.dataset.reviewJob);if(job){if(job.body?.sha && state.selected !== job.body.sha)await selectVersion(job.body.sha);recipeDialog(job.result);}return;}
  if (target.dataset.retryJob) {const job=state.jobs.find(j=>j.id===target.dataset.retryJob);if(job?.body?.sha){target.disabled=true;try{const result=await api(`/projects/${encodeURIComponent(job.projectId)}/${job.kind}`,{method:'POST',body:job.request || job.body});job.dismissed=true;const retry=normalizeJob(result,{projectId:job.projectId,kind:job.kind,body:job.request || job.body});state.jobs.push(retry);render();if(['complete','failed'].includes(retry.status))await onJobFinished(retry);else pollJob(retry);}catch(e){toast(e.message,true);target.disabled=false;}}return;}
  if (target.dataset.stop) {target.disabled=true;try{await api(`/runtimes/${encodeURIComponent(target.dataset.stop)}/stop`,{method:'POST',body:{}});const data=await api('/bootstrap');state.runtimes=data.runtimes||[];render();toast('已停止预览服务，运行副本与日志保留。');}catch(e){toast(e.message,true);target.disabled=false;}return;}
  const action = target.dataset.action;
  if (action === 'import') importDialog();
  else if (action === 'refresh') {await selectProject(state.project.id);toast('已从 Git 重新读取历史。');}
  else if (action === 'load-more') await loadHistory(true);
  else if (action === 'recipe') recipeDialog();
  else if (action === 'manual') manualDialog();
  else if (action === 'ai-settings') await aiSettingsDialog();
  else if (action === 'ai-suggest') await startAction('ai/suggest');
  else if (action === 'run' || action === 'capture') await startAction(action);
});
document.addEventListener('change',async event => {
  if(event.target.id === 'ref-select'){state.ref=event.target.value;await loadHistory();}
  else if(event.target.id === 'base-select')await chooseBase(event.target.value);
  else if(event.target.id === 'compare-capture')state.compareCapture=event.target.checked;
});
for (const modal of [dialog,mediaDialog]) modal.addEventListener('click',event=>{if(event.target===modal){const rect=modal.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)modal.close();}});
bootstrap();
