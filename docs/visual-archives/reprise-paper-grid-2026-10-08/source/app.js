'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const model = {versions:[], selected:null, query:'', state:{resources:[], running:0}, view:'versions', busy:false, token:'', preview:{}, current:null, commitPlan:null, project:'', comparison:null, comparisonExpanded:true, previewOptionsOpen:false, inlineExpanded:new Set()};
const version = id => model.versions.find(v => v.id === id);
const resource = id => model.state.resources.find(r => r.sha === id && r.exists);
const size = bytes => bytes >= 1e9 ? (bytes/1e9).toFixed(2)+' GB' : bytes >= 1e6 ? (bytes/1e6).toFixed(1)+' MB' : (bytes/1e3).toFixed(1)+' KB';
const stamp = v => new Date(v.time).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','.');
const fullStamp = v => new Date(v.time).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});
function localizedText(zh,en) {
  return `<span data-i18n-zh="${esc(zh)}" data-i18n-en="${esc(en||zh)}">${esc(uiLanguage==='en'?(en||zh):zh)}</span>`;
}
function versionName(v) {
  return v?.custom_title ? `<span data-verbatim>${esc(v.title)}</span>` : localizedText(v?.title||'',v?.localizations?.en?.title||contentEnglish[v?.title]);
}
function editableVersionName(v) {
  return v.custom_title || (uiLanguage==='en' ? v.localizations?.en?.title||contentEnglish[v.title]||v.title : v.title);
}

// User-defined names can be a single long word; keep them readable in each surface.
function wrapNames(element) {
  for(const node of element.querySelectorAll('h2,h3,p,li,.comparison-link>span,.detail-header>div')) {
    node.style.overflowWrap='anywhere';node.style.minWidth='0';
  }
}

async function api(path, payload) {
  const response = await fetch(path, payload ? {method:'POST', headers:{'Content-Type':'application/json','X-Demo-Token':model.token}, body:JSON.stringify(payload)} : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作没有完成，请重试。');
  return data;
}
let toastTimer;
function toast(text, error=false) {
  $('#toast').textContent = text;
  $('#toast').className = 'toast'+(error?' error':'');
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>{$('#toast').hidden=true;}, error?8000:4200);
}
function modal(html, lightbox=false) {
  const element = $('#modal');
  element.classList.toggle('lightbox',lightbox);
  element.classList.remove('runtime-dialog','comparison-modal');
  $('#modal-body').innerHTML = html;
  wrapNames($('#modal-body'));
  if (!element.open) element.showModal();
}
function closeModal() { $('#modal').close(); }
function go(view,animate=true) {
  const before=animate?viewMotion.capture(view):null;
  viewMotion.cancel();
  if(view!=='versions')browseMotion.cancel();
  const changing=view!==model.view;
  model.view = view;
  for (const panel of $$('.view')) panel.hidden = panel.id !== view+'-view';
  for (const button of $$('.nav-item')) button.classList.toggle('active', button.dataset.view === view);
  $('#versions-caption').hidden=view!=='versions'||!$('#versions-caption').textContent;
  location.hash = view;
  if (view === 'resources') renderResources();else fitVersionList();
  if(changing)window.scrollTo({top:0,behavior:'instant'});
  if(animate)viewMotion.open(before);
}

function fitVersionList() {
  const view=$('#versions-view');if(view.hidden)return;
  view.style.setProperty('--browse-header-height',$('.app-header').offsetHeight+'px');
  const aside=$('.version-browser'),box=aside.getBoundingClientRect(),top=Math.max(0,box.top);
  const height=Math.max(0,Math.min(innerHeight-top,box.bottom-top));
  aside.style.setProperty('--browser-visible-height',height+'px');
}
window.addEventListener('resize',fitVersionList);
let browseScrollFrame=0;
window.addEventListener('scroll',()=>{
  if(browseScrollFrame)return;
  browseScrollFrame=requestAnimationFrame(()=>{browseScrollFrame=0;fitVersionList();});
},{passive:true});
new ResizeObserver(fitVersionList).observe($('#versions-view'));
function renderList(focusSelected=false) {
  const git=model.current;
  $('#current-git-status').textContent=git?.available?`${git.branch} · ${git.dirty?git.change_count+' 项未提交':'已提交'}`:'不可读取';
  $('#current-git-choice').classList.toggle('selected',model.selected==='current');
  $('#current-git-choice').setAttribute('aria-pressed',String(model.selected==='current'));
  const previousScroll=$('#version-list').scrollTop;
  const list=model.versions.filter(v=>!model.query || [v.title,v.original_title,v.summary,contentEnglish[v.title],contentEnglish[v.original_title],contentEnglish[v.summary],...(v.changes||[]),...(v.localizations?.en?.changes||[]),v.sha,stamp(v),fullStamp(v)].some(x=>String(x||'').toLowerCase().includes(model.query.toLowerCase()))).sort((a,b)=>new Date(b.time)-new Date(a.time));
  $('#visible-count').textContent=list.length;
  $('#version-list').innerHTML=list.length ? list.map(v=>`<button class="version-card ${v.id===model.selected?'selected':''}" data-select="${v.id}" aria-pressed="${v.id===model.selected}" aria-label="${uiLanguage==='en'?'Select':'选择'} ${esc(v.custom_title?v.title:uiLanguage==='en'?(v.localizations?.en?.title||contentEnglish[v.title]||v.title):v.title)} ${esc(fullStamp(v))}"><h3 data-user-content>${versionName(v)}</h3></button>`).join('') : '<div class="empty-list">没有找到这个版本。</div>';
  wrapNames($('#version-list'));fitVersionList();
  $('#version-list').scrollTop=previousScroll;
  if(focusSelected&&!model.query){const selected=$('#version-list .selected'),listElement=$('#version-list');if(selected){const item=selected.getBoundingClientRect(),box=listElement.getBoundingClientRect();if(item.top<box.top)listElement.scrollTop+=item.top-box.top;else if(item.bottom>box.bottom)listElement.scrollTop+=item.bottom-box.bottom;}}
}
function previewIndex(v,key) { return Math.min(model.preview[key] ?? Math.max(0,v.previews.findIndex(p=>p.language===uiLanguage||p.caption.includes(uiLanguage==='en'?'英文':'中文'))), Math.max(0,v.previews.length-1)); }
function previewMedia(p,label,large=false) {
  return mediaMarkup(p,label);
}
function previewStage(v,key) {
  if(!v.previews.length)return '<div class="preview-empty">暂无预览</div>';
  const index=previewIndex(v,key),p=v.previews[index];
  if(p.status==='failed'||p.media_type==='unavailable')return `<div class="preview-empty">${esc(p.note||'上一版尚无此页面。')}</div>`;
  if(p.media_type==='video')return `<div class="screenshot-frame">${previewMedia(p,v.title+'：'+p.caption)}</div>`;
  return `<div class="screenshot-frame">${previewMedia(p,v.title+'：'+p.caption)}</div>`;
}
function openButton(v) {
  if(model.state.archive && !model.state.archive.available)return '<button class="subtle-button" disabled>Git 存档不可读取</button>';
  const r=resource(v.id);
  return r?.running ? `<button class="primary-button" data-inline="${v.id}">进入此版本 ↗</button>` : `<button class="primary-button" data-action="open" data-id="${v.id}" ${model.busy?'disabled':''}>打开此版本 ↗</button>`;
}
function renderCurrentGit() {
  const g=model.current;
  if(!g?.available){$('#version-detail').innerHTML='<div class="empty-list">当前项目不可读取。</div>';return;}
  const saved=version(g.head), labels={modified:'修改',added:'新增',deleted:'删除',untracked:'未跟踪'};
  $('#version-detail').innerHTML=`<div class="detail-header"><div><div class="detail-overline">${esc(g.branch)} · ${esc(g.head.slice(0,7))}</div><h2>当前项目</h2></div><button class="subtle-button" data-refresh-git>刷新</button></div><div class="current-summary"><h3>${g.dirty?g.change_count+' 项未提交':'已提交'}</h3><p>${g.dirty?'未提交的改动尚未存入历史版本。':'工作区与最近一次提交一致。'}</p>${g.dirty?`<div class="current-files current-changes" aria-label="当前变更"><ul>${g.changes.map(c=>`<li><span>${labels[c.kind]||'变化'}</span><code data-user-content>${esc(c.path)}</code></li>`).join('')}</ul></div>`:''}<div class="current-actions"><div class="current-save-actions"><button class="primary-button" data-commit-git ${model.busy||!g.dirty?'disabled':''}>提交变更</button></div><button class="primary-button" ${model.state.current_preview?.running?'data-current-inline':'data-action="open-current"'} ${model.busy?'disabled':''}>${model.state.current_preview?.running?'进入此版本':'打开此版本'} ↗</button></div>${saved?inlineVersion(saved.id,'查看最近变更','current-recent'):''}</div>`;
}
async function commitDialog() {
  if(model.busy)return;
  try {
    const plan=await api('/api/commit-plan');model.commitPlan=plan;
    modal(`<h2>提交到 Git</h2><form id="commit-form"><p>${esc(plan.branch)} · <span id="commit-count">${plan.files.length}</span> 个文件</p><label class="search-box"><span>提交说明</span><input name="message" id="commit-message" required maxlength="200" autocomplete="off" placeholder="简述这次改动"></label><p>保存所选文件的当前内容，包含已暂存与未暂存的改动。</p>${plan.excluded.length?`<p>默认排除独立项目：${plan.excluded.map(esc).join('、')}</p>`:''}<details class="current-files"><summary>核对提交范围</summary><ul>${plan.files.map((f,i)=>`<li><label><input type="checkbox" name="file" value="${i}" checked> <code>${esc(f.path)}</code></label></li>`).join('')}</ul></details><p id="commit-error" role="alert" hidden></p><div class="modal-actions"><button class="subtle-button" type="button" data-close>取消</button><button class="primary-button" type="submit">提交到 Git</button></div></form>`);
    $('#commit-message').focus();
  } catch(error){toast(error.message,true);}
}
async function submitCommit(form) {
  if(model.busy||!model.commitPlan)return;
  const selected=[...form.querySelectorAll('input[name="file"]:checked')].map(x=>Number(x.value)),message=form.elements.message.value.trim(),error=form.querySelector('#commit-error');
  if(!message||!selected.length){error.textContent='填写提交说明，并至少选择一个文件。';error.hidden=false;return;}
  model.busy=true;error.hidden=true;for(const control of form.elements)control.disabled=true;
  const operation=$('#operation');operation.hidden=false;operation.innerHTML='<span class="spinner"></span><span>正在提交…</span>';
  try {
    let job=await api('/api/commit',{plan:model.commitPlan.id,message,selected});
    while(job.status==='running'){await new Promise(resolve=>setTimeout(resolve,450));job=await api('/api/jobs/'+job.id);}
    if(job.status!=='complete')throw new Error(job.message||'Git 提交未完成。');
    closeModal();model.commitPlan=null;await refresh(true);
    modal(`<h2>已提交 ${esc(job.result.head.slice(0,7))}</h2><p data-verbatim>${esc(job.result.message)}</p><p>${job.result.committed_files} 个文件已存入当前项目的 Git。</p>${job.result.warning?`<p>${esc(job.result.warning)}</p>`:''}<div class="modal-actions"><button class="primary-button" data-close>完成</button></div>`);
  } catch(problem){error.textContent=problem.message+' 可关闭后重新核对提交范围。';error.hidden=false;await refresh(true).catch(()=>{});}
  finally {model.busy=false;operation.hidden=true;for(const control of form.elements)control.disabled=false;renderDetail();renderList();if(model.view==='resources')renderResources();}
}
const foldIcon = (expanded=false) => `<svg class="fold-icon ${expanded?'is-open':''}" width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true"><path d="M0 13h26" stroke="currentColor" stroke-width="2"/><path class="vertical-stroke" d="M13 0v26" stroke="currentColor" stroke-width="2"/></svg>`;
// Related versions expand in place; every expanded surface retains its origin.
function inlineVersion(id,label,scope) {
  const v=version(id);if(!v)return '';
  const open=model.inlineExpanded.has(scope),panelId='inline-'+scope;
  return `<section class="inline-version"><button class="inline-version-toggle" data-toggle-version="${id}" data-inline-scope="${scope}" aria-expanded="${open}" aria-controls="${panelId}"><span>${esc(label)}</span>${foldIcon(open)}</button><div class="inline-version-content" id="${panelId}" ${open?'':'hidden'}>${open?versionPage(v,scope):''}${open?'<button class="inline-version-close" data-collapse-version>收起并返回</button>':''}</div></section>`;
}
function toggleInlineVersion(button,force) {
  const panel=document.getElementById(button.getAttribute('aria-controls')),scope=button.dataset.inlineScope;
  if(!panel)return;
  const open=typeof force==='boolean'?force:button.getAttribute('aria-expanded')!=='true';
  if(open){model.inlineExpanded.add(scope);if(!panel.firstElementChild)panel.innerHTML=versionPage(version(button.dataset.toggleVersion),scope)+'<button class="inline-version-close" data-collapse-version>收起并返回</button>';}
  else {model.inlineExpanded.delete(scope);for(const media of panel.querySelectorAll('video,audio'))media.pause();}
  panel.hidden=!open;button.setAttribute('aria-expanded',String(open));button.querySelector('.fold-icon')?.classList.toggle('is-open',open);
  if(!open){button.focus({preventScroll:true});const box=button.getBoundingClientRect();if(box.top<0||box.bottom>innerHeight)button.scrollIntoView({block:'nearest'});}
}
function versionPage(v, scope='detail', canCompare=true) {
  const previous=version(v.base),changes=v.changes.filter(c=>c!==v.summary);
  const context=previous?(previous.kind==='release'?'相对上一份发布存档':'相对上一版 Git'):'系列起点';
  const tools=(typeof aiEntry==='function'?aiEntry(v):'')+(typeof evidenceEntry==='function'?evidenceEntry(v,scope):'');
  return `<article class="version-page" data-page-version="${v.id}" data-preview-scope="${scope}"><div class="detail-header"><div><div class="detail-overline">${esc(fullStamp(v))} · <span>${v.kind==='release'?'发布包':'Git 提交'}</span></div><h2 data-user-content>${versionName(v)}</h2><button class="text-button" data-rename="${v.id}" ${model.busy?'disabled':''}>重命名</button></div>${openButton(v)}</div><div class="change-content"><div class="change-heading"><h3>这个版本改了什么</h3><span>${context}</span></div><p class="detail-summary" data-user-content>${esc(v.summary)}</p>${changes.length?`<ul class="change-list" data-user-content>${changes.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:''}${tools?`<div class="change-tools">${tools}</div>`:''}${previous?`<div class="comparison-link"><span><span>上一版：</span><span data-user-content>${versionName(previous)}</span></span>${canCompare?`<button class="text-button compare-button" data-compare-version="${v.id}" aria-haspopup="dialog" ${model.busy?'disabled':''}>对比上一版 ↗</button>`:''}</div>`:''}</div><div class="preview-panel">${previewMenu(v,scope)}${previewStage(v,scope)}</div></article>`;
}
let previewAnimation=null;
function previewMenu(v,scope) {
  const index=previewIndex(v,scope),open=model.previewOptionsOpen,id='preview-options-'+scope;
  if(!v.previews.length)return '';
  return `<div class="preview-menu"><button class="preview-toggle" data-toggle-preview aria-expanded="${open}" aria-controls="${id}" ${v.previews.length<2?'disabled':''}><span>预览</span>${v.previews.length>1?foldIcon(open):''}</button><div class="preview-options" id="${id}" ${open?'':'hidden inert'}><div class="preview-options-inner" role="group" aria-label="选择预览">${v.previews.map((p,i)=>`<button class="preview-option" data-preview-choice="${i}" data-preview-scope="${scope}" aria-pressed="${i===index}"><span data-user-content>${esc(p.caption)}</span><span class="preview-selected" aria-hidden="true">${i===index?'✓':''}</span></button>`).join('')}</div></div></div>`;
}
function togglePreview(force, button=$('[data-toggle-preview]')) {
  const panel=button&&document.getElementById(button.getAttribute('aria-controls'));
  if(!panel||button.disabled)return;
  const start=panel.hidden?0:panel.getBoundingClientRect().height;
  previewAnimation?.cancel();
  const open=typeof force==='boolean'?force:button.getAttribute('aria-expanded')!=='true';
  model.previewOptionsOpen=open;button.setAttribute('aria-expanded',String(open));
  button.querySelector('.fold-icon')?.classList.toggle('is-open',open);
  panel.hidden=false;panel.inert=!open;
  const border=parseFloat(getComputedStyle(panel).borderTopWidth)+parseFloat(getComputedStyle(panel).borderBottomWidth);
  const end=open?Math.min(panel.firstElementChild.scrollHeight+border,innerHeight*.5,360):0;
  const finish=()=>{panel.hidden=!open;panel.style.overflow='';previewAnimation=null;};
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){finish();return;}
  panel.style.overflow='hidden';
  const animation=panel.animate([{height:start+'px'},{height:end+'px'}],{duration:420,easing:'cubic-bezier(.22,.68,.18,1)',fill:'both'});
  previewAnimation=animation;
  animation.finished.then(()=>{if(previewAnimation===animation){finish();animation.cancel();}}).catch(()=>{});
}
function choosePreview(button) {
  const scope=button.dataset.previewScope||'detail',page=button.closest('[data-page-version]'),v=version(page?.dataset.pageVersion);
  if(!v)return;
  model.preview[scope]=Number(button.dataset.previewChoice);model.previewOptionsOpen=false;
  page.querySelector(':scope > .preview-panel').innerHTML=previewMenu(v,scope)+previewStage(v,scope);
  page.querySelector(':scope > .preview-panel [data-toggle-preview]')?.focus({preventScroll:true});
  if(scope==='detail'){const preview=v.previews[previewIndex(v,scope)],caption=$('#versions-caption');caption.innerHTML=preview?`<p class="preview-note" data-user-content>${esc(preview.caption)}</p>`:'';caption.hidden=model.view!=='versions'||!preview||preview.status==='failed'||preview.media_type==='unavailable';}
}

function renderDetail() {
  previewAnimation?.cancel();previewAnimation=null;
  const caption=$('#versions-caption');caption.hidden=true;caption.innerHTML='';
  const indexOnly=!model.selected;
  $('#versions-view').classList.toggle('is-index',indexOnly);
  $('#version-detail').hidden=indexOnly;
  if(indexOnly){$('#version-detail').innerHTML='';fitVersionList();return;}
  if(model.selected==='current'){renderCurrentGit();$('#version-detail').insertAdjacentHTML('afterbegin','<button class="detail-back" data-index>返回版本列表</button>');fitVersionList();return;}
  const v=version(model.selected);if(!v)return;
  $('#version-detail').innerHTML=`<button class="detail-back" data-index>返回版本列表</button><div class="version-pages">${versionPage(v)}</div>`;
  wrapNames($('#version-detail'));
  const preview=v.previews[previewIndex(v,'detail')];
  if(preview&&preview.status!=='failed'&&preview.media_type!=='unavailable'){caption.innerHTML=`<p class="preview-note" data-user-content>${esc(preview.caption)}</p>`;caption.hidden=model.view!=='versions';}
  fitVersionList();
}
function matchingPreview(current,previews) {
  if(!current)return null;
  const sameCapture=p=>p.language===current.language&&p.viewport&&current.viewport&&p.viewport.width===current.viewport.width&&p.viewport.height===current.viewport.height;
  return previews.find(p=>p.comparison_key&&p.comparison_key===current.comparison_key&&sameCapture(p))||previews.find(p=>
    p.route&&p.route===current.route&&p.language===current.language&&
    Boolean(p.comparison_key?.startsWith('full:'))===Boolean(current.comparison_key?.startsWith('full:'))&&
    p.media_type===current.media_type&&p.viewport&&current.viewport&&
    p.viewport.width===current.viewport.width&&p.viewport.height===current.viewport.height);
}
function comparisonMedia(p,label) {
  if(!p||!p.url||p.status==='failed'||p.media_type==='unavailable')return `<div class="comparison-empty">${p?.note?`<span data-user-content>${esc(p.note)}</span>`:'上一版尚无此页面。'}</div>`;
  return `<div class="comparison-preview">${mediaMarkup(p,label,true)}</div>`;
}
function comparePrevious(id) {
  const v=version(id),base=version(v?.base);if(!base)return;
  const page=[...document.querySelectorAll('[data-page-version]')].find(p=>p.dataset.pageVersion===id);
  const current=v.previews[previewIndex(v,page?.dataset.previewScope||'detail')];
  // Prefer the captured parent pages for this version, retaining complete-page metadata.
  const old=matchingPreview(current,v.comparison_pages||[])||matchingPreview(current,base.previews);
  const available=p=>p?.url&&p.status!=='failed'&&p.media_type!=='unavailable';
  const staticPair=old?.media_type==='image'&&current?.media_type==='image';
  const samePage=old?.route===current?.route;
  const note=v.preview_architecture?.shared_from?'本版页面未修改，预览与上一版一致；具体变化见文件依据。':!available(old)||!available(current)?'这组预览尚未完整采集，暂时无法直接比较。':current.operation==='fields-arrival-plus-20vh'?'相同滚动位置：旧版入口尚未完全展开，新版已展开。完整过程见操作录屏。':staticPair?(samePage?'展示同一页面、语言和视口的已保存画面。截图反映采集时的状态，完整交互过程见操作录屏。':'展示同一作品位置、语言和视口的已保存画面。截图反映采集时的状态，完整交互过程见操作录屏。'):'展示同一页面的已保存预览，可分别播放查看。';
  modal(`<h2>和上一版一起看</h2><p class="comparison-summary" data-user-content>${esc(v.summary)}</p><div class="cached-pair">${[[base,old],[v,current]].map(([item,p])=>`<article><h3 data-user-content>${versionName(item)}</h3><p data-user-content>${esc(p?.caption||current?.caption||'')}</p>${comparisonMedia(p,item.title+'：'+(p?.caption||''))}</article>`).join('')}</div><p class="comparison-note">${note}</p>`,true);
  $('#modal').classList.add('comparison-modal');
}
function showVersionIndex() {
  const before=viewMotion.capture('versions',Boolean(model.selected));
  viewMotion.cancel();browseMotion.cancel();
  model.selected=null;model.comparison=null;model.previewOptionsOpen=false;delete model.preview.comparison;
  go('versions',false);renderList();renderDetail();
  viewMotion.open(before);
}
function revealSelectedVersion() {
  if(innerWidth<=700)$('#version-detail').scrollIntoView({block:'start',behavior:'instant'});
}
function selectVersion(id) {
  if(id!=='current'&&!version(id))return;
  const navigation=viewMotion.capture('versions',Boolean(model.selected)&&model.selected!==id);
  viewMotion.cancel();browseMotion.cancel();
  const before=browseMotion.capture();
  model.selected=id;model.comparison=null;model.previewOptionsOpen=false;
  delete model.preview.comparison;delete model.preview.detail;
  go('versions',false);renderList(!before);renderDetail();
  const choice=id==='current'?$('#current-git-choice'):$('#version-list .selected');
  choice?.focus({preventScroll:true});
  if(navigation)viewMotion.open(navigation,revealSelectedVersion);
  else browseMotion.open(before,revealSelectedVersion);
}

function renameDialog(id) {
  const v=version(id);if(!v || model.busy)return;
  modal(`<h2>重命名</h2><form id="rename-form" data-version="${v.id}"><label class="search-box"><span>版本名称</span><input id="version-name" name="title" type="text" required autocomplete="off" value="${esc(editableVersionName(v))}" aria-describedby="rename-help rename-error"></label><p id="rename-help">${v.custom_title?'原名：'+esc(v.original_title):'最多 80 个字符。'}</p><p id="rename-error" role="alert" hidden></p><div class="modal-actions">${v.custom_title?'<button class="text-button" type="button" data-reset-name>恢复原名</button>':''}<button class="subtle-button" type="button" data-close>取消</button><button class="primary-button" type="submit">保存名称</button></div></form>`);
  $('#version-name').focus();$('#version-name').select();
}

async function saveName(form,reset=false) {
  if(form.dataset.saving)return;
  const input=form.elements.title, error=form.querySelector('#rename-error');
  const title=reset?null:input.value.trim();
  let message='';
  if(!reset){
    if(!title)message='请输入版本名称。';
    else if(Array.from(title).length>80)message='版本名称最多 80 个字符。';
    else if(/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(input.value))message='版本名称不能包含换行或隐藏控制字符。';
  }
  if(message){error.textContent=message;error.hidden=false;input.focus();return;}
  form.dataset.saving='true';error.hidden=true;
  for(const control of form.elements)control.disabled=true;
  try {
    const data=await api('/api/rename',{version:form.dataset.version,title});
    model.versions=data.versions;model.state.version_names=data.version_names;
    renderList();renderDetail();renderResources();renderRunning();
    if(form.isConnected)closeModal();
    toast(reset?'已恢复原名。':'版本名称已保存。');
  } catch(problem){error.textContent=problem.message;error.hidden=false;}
  finally {delete form.dataset.saving;for(const control of form.elements)control.disabled=false;}
}
function previousPreview(id) {
  if(version(id)?.preview_architecture)return showEvidence(id);
  const v=version(id), base=version(v.base); if(!base?.previews.length)return;
  const current=v.previews[previewIndex(v,'detail')];
  const old=base.previews.find(p=>p.comparison_key&&p.comparison_key===current.comparison_key)||base.previews.find(p=>p.route&&p.route===current.route&&p.caption===current.caption);
  if(!old){modal(`<h2>暂无同位置对比</h2><p>上一版没有这处变化对应的预览，不能直接比较。</p><div class="modal-actions"><button class="subtle-button" data-select="${base.id}" data-close>查看上一版页面</button></div>`);return;}
  const sameViewport=old.viewport&&current.viewport&&old.viewport.width===current.viewport.width&&old.viewport.height===current.viewport.height;
  modal(`<h2>对比上一版</h2><div class="cached-pair">${[[base,old],[v,current]].map(([item,p])=>`<article><h3>${versionName(item)}</h3><p>${esc(p.caption)}</p>${previewMedia(p,item.title+' '+p.caption,true)}</article>`).join('')}</div>${sameViewport?'':'<p>视口或采集状态未完全对齐，这组预览不能直接证明变化。</p>'}`,true);
}
function renderResources() {
  if(typeof renderAIManagement==='function')renderAIManagement();
  const rows=model.state.resources.filter(r=>r.exists).sort((a,b)=>new Date(version(b.sha)?.time||0)-new Date(version(a.sha)?.time||0)),a=model.state.archive||{available:true,bytes:model.state.archive_bytes||0},g=model.current;
  $('#git-management').innerHTML=`<article class="resource-row"><div class="resource-main"><h3>当前项目 Git</h3><p data-user-content>${esc(g?.branch||'')} · ${esc(g?.head?.slice(0,7)||'')}</p></div><div class="resource-status">${g?.available?(g.dirty?g.change_count+' 项未提交':'已提交'):'不可读取'}</div><div class="resource-size">原项目</div><div class="resource-actions"><button data-current-git>查看变更 ↗</button></div></article><article class="resource-row"><div class="resource-main"><h3>历史 Git 存档</h3><p>${model.versions.length} 个版本 · 提交、标签与还原配置</p></div><div class="resource-status">${a.available?'已保留':'不可读取'}</div><div class="resource-size">${size(a.bytes||0)}</div><div class="resource-actions"><button data-action="git-backup" ${model.busy||!a.available?'disabled':''}>导出备份</button></div></article>`;
  $('#environment-total').textContent=rows.length+' 份 · '+size(rows.reduce((sum,r)=>sum+r.bytes,0));
  $('#clean-all').disabled=!rows.length || model.busy || !a.available;
  $('#resource-list').innerHTML=rows.length?rows.map(r=>{const v=version(r.sha);return `<article class="resource-row" data-version-id="${r.sha}"><div class="resource-main"><h3 data-user-content>${v?versionName(v):esc(r.sha.slice(0,7))}</h3>${v?`<p>${esc(stamp(v))}</p>`:''}</div><div class="resource-status">${r.running?'运行中':'已停止，已保留'}</div><div class="resource-size">${size(r.bytes)}</div><div class="resource-actions">${r.running?`<button data-inline="${r.sha}">进入 ↗</button><button data-end="${r.sha}" ${model.busy?'disabled':''}>停止…</button>`:`<button data-action="open" data-id="${r.sha}" ${model.busy||!a.available?'disabled':''}>打开</button>`}<button data-clean="${r.sha}" ${model.busy||!a.available?'disabled':''}>删除环境…</button></div></article>`;}).join(''):'<div class="empty-list">暂无已下载版本环境</div>';
  wrapNames($('#resource-list'));
}
function inlineCurrentExperience() {
  const runtime=model.state.current_preview;
  if(!runtime?.running)return;
  modal(`<h2><span data-verbatim>${esc(model.project)}</span> · 当前 Git</h2>${runtimeTools(runtime.url)}<iframe class="runtime-frame" title="当前项目" src="${esc(runtime.url)}" allow="fullscreen; gamepad" allowfullscreen sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms allow-pointer-lock"></iframe><div class="runtime-footer"><span>当前工作区 · 包含未提交改动</span><button class="text-button" data-action="stop-current">停止运行</button></div>`);
  $('#modal').classList.add('runtime-dialog');
}
function renderRunning() {
  const active=model.state.resources.find(r=>r.running);
  const current=model.state.current_preview;
  $('#running-bar').hidden=!active&&!current?.running;
  if(current?.running){$('#running-bar').innerHTML=`<span class="running-title"><i></i><span>运行中 · 当前 Git</span> · <span data-verbatim>${esc(model.project)}</span></span><div><button data-current-inline>进入 ↗</button><button data-action="stop-current" ${model.busy?'disabled':''}>停止运行</button></div>`;return;}
  if(active)$('#running-bar').innerHTML=`<span class="running-title"><i></i>运行中 · ${esc(version(active.sha)?.title||active.sha.slice(0,7))}</span><div><button data-inline="${active.sha}">进入 ↗</button><button data-end="${active.sha}" ${model.busy?'disabled':''}>结束体验</button></div>`;
}
async function refresh(repaint=false) {
  const before = JSON.stringify([model.state.resources,model.state.archive,model.current,model.state.version_names,model.state.ai,model.state.current_preview]);
  model.state = await api('/api/state'+(repaint?'?fresh=1':''));
  model.current = model.state.current_git || null;
  for(const v of model.versions){v.custom_title=model.state.version_names?.[v.id]||null;v.title=v.custom_title||v.original_title||v.title;}
  renderRunning();
  if (repaint || before !== JSON.stringify([model.state.resources,model.state.archive,model.current,model.state.version_names,model.state.ai,model.state.current_preview])) {
    viewMotion.cancel();browseMotion.cancel();
    renderList();renderDetail();
    if (model.view === 'resources') renderResources();
  }
}
async function perform(action,id) {
  if (model.busy) return;
  closeModal();model.busy=true;
  const label = {open:'准备版本','open-current':'打开当前项目','stop-current':'停止当前项目',stop:'停止运行',clean:'清理运行副本','clean-all':'删除运行环境','git-backup':'导出 Git 备份'}[action];
  const operation = $('#operation');
  operation.hidden=false;$('#toast').hidden=true;
  operation.innerHTML=`<span class="spinner"></span><span>${label}…</span>`;
  renderDetail();renderResources();renderRunning();
  try {
    let job = await api('/api/action',{action,version:id});
    while (job.status === 'running') {
      operation.innerHTML=`<span class="spinner"></span><span>${esc(job.message)}</span>`;
      await new Promise(resolve=>setTimeout(resolve,450));
      job = await api('/api/jobs/'+job.id);
    }
    if (job.status !== 'complete') throw new Error(job.message || '操作未完成。');
    await refresh(true);
    if (action === 'open') {
      inlineExperience(id);
    } else if(action==='open-current'){inlineCurrentExperience();
    } else if(action==='git-backup') {modal(`<h2>Git 备份已保存</h2><p>备份包含全部提交与标签；配置文件保存版本说明和运行方式。</p><div class="modal-actions"><a class="primary-button" href="${esc(job.bundle_url)}" download>下载 Git 备份</a><a class="subtle-button" href="${esc(job.manifest_url)}" download>下载版本配置</a></div>`);} else toast(job.message);
  } catch(error) { toast(error.message,true); await refresh(true).catch(()=>{}); }
  finally {model.busy=false;operation.hidden=true;renderDetail();renderRunning();if(model.view==='resources')renderResources();}
}
function confirmClean(id,all=false) {
  const selected=all?model.state.resources.filter(r=>r.exists):[resource(id)].filter(Boolean);
  if(!selected.length)return toast('没有需要删除的环境。');
  const total=selected.reduce((sum,r)=>sum+r.bytes,0);
  modal(`<h2>${all?'删除全部环境？':'删除这份环境？'}</h2><p>${selected.length} 份环境 · ${size(total)}</p><ul>${selected.map(r=>`<li>${esc(version(r.sha)?.title||r.sha.slice(0,7))}</li>`).join('')}</ul><p>Git、截图和说明继续保留。有未保存改动的环境不会删除。</p><div class="modal-actions"><button class="subtle-button" data-close>取消</button><button class="primary-button" data-confirm-clean="${all?'all':id}">确认删除</button></div>`);
}
function endExperience(id) {
  modal(`<h2>结束体验</h2><p>${esc(version(id).title)}</p><div class="modal-actions"><button class="subtle-button" data-close>继续运行</button><button class="subtle-button" data-end-clean="${id}">删除环境…</button><button class="primary-button" data-action="stop">停止并保留</button></div>`);
}
function runtimeTools(url){return `<div class="runtime-tools"><button class="text-button" data-runtime-fullscreen>全屏体验</button><a class="text-button" href="${esc(url)}" target="_blank" rel="noopener">独立窗口 ↗</a></div>`;}
function inlineExperience(id) {
  const r=resource(id),v=version(id);
  if (!r?.running) return toast('这个版本已停止，请重新打开。');
  modal(`<h2 data-user-content>${versionName(v)}</h2>${runtimeTools(r.url)}<iframe class="runtime-frame" src="${esc(r.url)}" title="${esc(v.title)}交互版本" allow="fullscreen; gamepad" allowfullscreen sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms allow-pointer-lock"></iframe><div class="runtime-footer"><span>运行中</span><button class="subtle-button" data-end="${id}">结束体验</button></div>`);
  $('#modal').classList.add('runtime-dialog');
}
document.addEventListener('click', event => {
  const target = event.target.closest('button,a');
  if (!target) return;
  if (target.dataset.view) {if(target.dataset.view==='versions')showVersionIndex();else go(target.dataset.view);}
  if(target.hasAttribute('data-index')){event.preventDefault();showVersionIndex();}
  if(target.hasAttribute('data-current-git'))selectVersion('current');
  if(target.hasAttribute('data-current-inline'))inlineCurrentExperience();
  if(target.hasAttribute('data-commit-git'))commitDialog();
  if(target.hasAttribute('data-refresh-git'))refresh(true).catch(error=>toast(error.message,true));
  if (target.dataset.go) go(target.dataset.go);
  if (target.dataset.select)selectVersion(target.dataset.select);
  if(target.dataset.compareVersion)comparePrevious(target.dataset.compareVersion);
  if(target.hasAttribute('data-toggle-preview'))togglePreview(undefined,target);
  if(target.dataset.toggleVersion)toggleInlineVersion(target);
  if(target.hasAttribute('data-collapse-version'))toggleInlineVersion(target.closest('.inline-version').querySelector('.inline-version-toggle'),false);
  if(target.hasAttribute('data-preview-choice'))choosePreview(target);
  if (target.dataset.rename)renameDialog(target.dataset.rename);
  if (target.hasAttribute('data-reset-name'))saveName(target.closest('form'),true);
  if (target.dataset.lightbox) {
    const v = version(target.dataset.lightbox), p=v.previews[Number(target.dataset.lightboxIndex)];
    modal(`<h2 data-user-content>${versionName(v)}</h2>${previewMedia(p,v.title+'：'+p.caption,true)}<p>${esc(p.caption)}</p>`,true);
  }
  if (target.dataset.previousPreview) previousPreview(target.dataset.previousPreview);
  if (target.dataset.action) perform(target.dataset.action,target.dataset.id);
  if (target.dataset.clean) confirmClean(target.dataset.clean);
  if (target.dataset.confirmClean) perform(target.dataset.confirmClean==='all'?'clean-all':'clean',target.dataset.confirmClean==='all'?null:target.dataset.confirmClean);
  if (target.dataset.end) endExperience(target.dataset.end);
  if (target.dataset.inline) inlineExperience(target.dataset.inline);
  if (target.dataset.endClean) confirmClean(target.dataset.endClean);
  if (target.hasAttribute('data-close') || target.dataset.enter) closeModal();
});
document.addEventListener('keydown',event=>{
  const option=event.target.closest('[data-preview-choice]');
  if(!option)return;
  if(event.key==='Escape'){event.preventDefault();const button=option.closest('.preview-menu').querySelector('[data-toggle-preview]');togglePreview(false,button);button.focus({preventScroll:true});return;}
  if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
  event.preventDefault();
  const options=[...option.parentElement.querySelectorAll('[data-preview-choice]')],index=options.indexOf(option);
  const next=event.key==='Home'?0:event.key==='End'?options.length-1:(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;
  options[next].focus();
});
document.addEventListener('submit',event=>{if(event.target.id==='rename-form'){event.preventDefault();saveName(event.target);}if(event.target.id==='commit-form'){event.preventDefault();submitCommit(event.target);}});
document.addEventListener('change',event=>{if(event.target.name==='file'&&event.target.closest('#commit-form'))$('#commit-count').textContent=event.target.closest('form').querySelectorAll('input[name="file"]:checked').length;if(event.target.hasAttribute('data-preview-select')){model.preview[event.target.dataset.previewScope||'detail']=Number(event.target.value);renderDetail();}});
$('#search').addEventListener('input',event=>{browseMotion.cancel();model.query=event.target.value;renderList(!model.query);});
$('#refresh-resources').addEventListener('click',()=>refresh(true).catch(error=>toast(error.message,true)));
$('#clean-all').addEventListener('click',()=>confirmClean(null,true));
document.addEventListener('reprise-language-change',()=>{renderList();translateUI();});
window.addEventListener('hashchange',()=>{const view=location.hash.slice(1);if(['versions','resources'].includes(view)&&view!==model.view)go(view);});

async function boot() {
  try {
    const data = await api('/api/catalog');
    registerLocalizedCatalog(data);model.versions=data.versions;model.token=data.token;model.project=data.project;
    $('#project-name').textContent=data.project;document.title=data.project+' · Reprise';
    model.selected=null;
    await refresh(true);
    go(['versions','resources'].includes(location.hash.slice(1))?location.hash.slice(1):'versions');
    setInterval(()=>{if(!model.busy)refresh().catch(()=>{});},8000);
    window.demoReady=true;
  } catch(error) {$('#version-detail').innerHTML='<div class="empty-list">'+esc(error.message)+'</div>';toast(error.message,true);}
}
boot();
