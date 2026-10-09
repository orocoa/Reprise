/* Frozen Paper Grid layout, connected to the canonical read-only Git services. */
'use strict';
state.index=true;state.view=location.hash==='#resources'?'resources':'versions';state.query='';state.current=null;
const canonicalVersionView=versionView;
const canonicalSelectVersion=selectVersion;
const canonicalSelectProject=selectProject;
function versionTitle(commit) {
  const notes=state.project?.version_notes?.[commit.sha]?.localizations;
  return notes?.[uiLanguage]?.title || commit.subject || commit.sha.slice(0,8);
}
commitRow=function(commit){return `<button class="version-card commit-row ${commit.sha===state.selected&&!state.index?'selected active':''}" data-sha="${esc(commit.sha)}" data-select="${esc(commit.sha)}" aria-current="${commit.sha===state.selected&&!state.index}"><h3 data-user-content>${esc(versionTitle(commit))}</h3></button>`;};
selectVersion=async function(sha,base=null){
  browseMotion.cancel();viewMotion.cancel();
  const before=state.view==='versions'&&state.index&&!state.projectSelecting?browseMotion.capture():null;
  state.index=false;state.current=null;
  await canonicalSelectVersion(sha,base);
  if(before)browseMotion.open(before);
};
selectProject=async function(id){
  state.index=true;state.current=null;state.query='';
  state.projectSelecting=true;try{await canonicalSelectProject(id);}finally{state.projectSelecting=false;}
  state.index=true;render();
};
function headerView(){
  return `<header class="app-header"><div class="project-identity"><a class="brand" href="#versions" data-action="index" data-user-content>${esc(state.project?.name||'Reprise')}</a><div class="language-switch" role="group" aria-label="Interface language" data-user-content>[ <button data-language="zh" aria-pressed="${uiLanguage==='zh'}">中</button> / <button data-language="en" aria-pressed="${uiLanguage==='en'}">EN</button> ]</div></div><nav aria-label="Main navigation"><button class="nav-item ${state.view==='versions'?'active':''}" data-view="versions">版本浏览</button><button class="nav-item ${state.view==='resources'?'active':''}" data-view="resources">版本管理</button></nav></header>`;
}
function projectSwitcher(){return `<div class="project-switcher"><label for="project-select">选择项目</label><select id="project-select">${state.projects.length?state.projects.map(p=>`<option data-user-content value="${esc(p.id)}" ${p.id===state.project?.id?'selected':''}>${esc(p.name)}</option>`).join(''):'<option value="">选择项目</option>'}</select><button class="text-button" data-action="import">导入项目 ＋</button></div>`;}
function currentView(){
  const current=state.current;
  if(!current)return '';
  const changes=current.changes||current.files||[];
  return `<article class="current-summary"><h2>当前 Git</h2><p>未提交改动不属于历史版本。</p><code data-user-content>${esc(state.project.path)}</code>${!current.available?`<p>${esc(current.reason||'工作目录状态不可用。')}</p>`:!current.dirty?'<p>工作目录干净。</p>':''}<div class="current-files"><ul>${changes.map(c=>`<li><code data-user-content>${esc(c.path||c.name||'')}</code> <span>${esc(c.status||c.kind||'')}</span></li>`).join('')}</ul></div>${state.project.head?`<button class="primary-button" data-sha="${esc(state.project.head)}">查看 HEAD 版本 ↗</button>`:'<p>仓库中还没有提交。</p>'}</article>`;
}
function notesView(){
  const notes=state.version?.notes?.localizations?.[uiLanguage];
  if(!notes)return '';
  return `<section class="change-content revision-notes" data-user-content><h2>${esc(notes.title)}</h2><p class="detail-summary">${esc(notes.summary)}</p><ul class="change-list">${notes.changes.map(c=>`<li>${esc(c)}</li>`).join('')}</ul></section>`;
}
function versionsView(){
  const commits=state.history.filter(c=>!state.query||[c.subject,c.sha,...Object.values(state.project?.version_notes?.[c.sha]?.localizations||{}).flatMap(n=>[n.title,n.summary,...n.changes])].some(t=>String(t).toLowerCase().includes(state.query.toLowerCase())));
  return `<section class="view browser-layout ${state.index?'is-index':''}" id="versions-view" aria-label="版本浏览"><aside class="version-browser"><div class="version-browser-contents">${projectSwitcher()}<label class="search-box"><input id="version-search" type="search" value="${esc(state.query)}" placeholder="搜索历史版本" aria-label="搜索历史版本">${icon('zoom')}</label><button class="current-git-choice" data-action="current-git"><span>当前 Git ↗</span><small data-user-content>${esc(state.project?.repository?.branch||'')}</small></button><label class="ref-filter"><select id="ref-select"><option value="--all">所有分支与标签</option>${state.refs.map(r=>`<option data-user-content value="${esc(r.name)}" ${r.name===state.ref?'selected':''}>${esc(r.name)}</option>`).join('')}</select><button class="icon-button" data-action="refresh" aria-label="刷新 Git 历史">${icon('refresh')}</button></label><p class="list-heading"><span>版本总数</span> <span data-user-content>${state.history.length}${state.hasMore?'+':''}</span></p><div id="version-list" class="version-list history-list">${!state.project?'<div class="empty-list">先导入一个本地 Git 项目。</div>':commits.length?commits.map(commitRow).join(''):`<div class="empty-list">${state.query?'没有找到这个版本。':state.loading?'读取 Git…':'仓库中还没有提交。'}</div>`}</div>${state.hasMore?'<button class="subtle-button" data-action="load-more">加载更早的提交</button>':''}</div></aside><section class="version-detail" id="version-detail" ${state.index?'hidden':''}><button class="detail-back" data-action="index">返回版本列表</button>${state.current?currentView():state.loading?'<div class="section-loading">读取精确版本…</div>':state.version?notesView()+canonicalVersionView():'<div class="empty-list">仓库中还没有提交。</div>'}</section></section>`;
}
function managementView(){return `<section class="view management-view" id="resources-view"><div class="management-heading"><h1>版本管理</h1><button class="subtle-button" data-action="refresh">刷新 Git 历史</button></div><div class="managed-section">${projectSwitcher()}${state.project?`<p class="management-note" data-user-content>${esc(state.project.path)}</p>`:''}</div><div class="managed-section"><button class="subtle-button" data-action="ai-settings">可选 AI 助手</button></div><div class="managed-section">${runtimesView()||'<p>没有运行中的预览服务。</p>'}</div><div class="managed-section" id="jobs-region">${jobsView()}</div><p>运行副本、日志和媒体保留在本机数据目录。</p></section>`;}
render=function(){
  state.media=[];
  app.innerHTML=`<div class="app-shell">${headerView()}<main>${state.error?`<div class="inline-notice error">${esc(state.error)}</div>`:''}${state.jobWarnings.map(w=>`<div class="inline-notice warn">${esc(w.message)} <code>${esc(w.file)}</code></div>`).join('')}${state.view==='versions'?`<div id="jobs-region">${jobsView()}</div><div id="running-bar">${runtimesView()}</div>${versionsView()}`:managementView()}</main></div>`;
  localizeDOM();window.demoReady=true;
};
document.addEventListener('click',async event=>{
  const button=event.target.closest('button,a');if(!button)return;
  if(button.dataset.language){
    uiLanguage=button.dataset.language;try{localStorage.setItem('reprise.language',uiLanguage);}catch(_){}
    viewMotion.cancel();browseMotion.cancel();render();localizeDOM();return;
  }
  if(button.dataset.view){
    viewMotion.cancel();browseMotion.cancel();const before=viewMotion.capture(button.dataset.view,!state.index);
    state.view=button.dataset.view;location.hash=state.view;render();if(before)viewMotion.open(before);return;
  }
  if(button.dataset.action==='index'){
    event.preventDefault();viewMotion.cancel();browseMotion.cancel();state.view='versions';state.index=true;state.current=null;location.hash='versions';render();
  }else if(button.dataset.action==='current-git'&&state.project){
    try{state.current=await api(`/projects/${encodeURIComponent(state.project.id)}/status`);state.index=false;render();}catch(e){toast(e.message,true);}
  }
});
document.addEventListener('change',event=>{if(event.target.id==='project-select'&&event.target.value)selectProject(event.target.value);});
document.addEventListener('input',event=>{
  if(event.target.id!=='version-search')return;
  state.query=event.target.value;
  const matches=state.history.filter(c=>[c.subject,c.sha,...Object.values(state.project?.version_notes?.[c.sha]?.localizations||{}).flatMap(n=>[n.title,n.summary,...n.changes])].some(t=>String(t).toLowerCase().includes(state.query.toLowerCase())));
  $('#version-list').innerHTML=matches.length?matches.map(commitRow).join(''):`<div class="empty-list">${uiText('没有找到这个版本。')}</div>`;
});
window.addEventListener('hashchange',()=>{const view=location.hash==='#resources'?'resources':'versions';if(view!==state.view){state.view=view;render();}});
