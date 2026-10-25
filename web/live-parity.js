'use strict';
function setWorkspaceView(view,{render=true}={}){state.view='versions';$('.workspace').hidden=false;const url=new URL(location.href);url.hash='versions';history.replaceState(null,'',url);if(render){renderDetail();if(view==='resources')settings();}}
function runtimeInfo(r){
 // A live install/build process is not a ready preview service.
 const pending=['preparing','install','build','building','starting'].includes(r.status),uncertain=r.status==='cleanup_failed',interrupted=r.status==='interrupted';
 const running=!pending&&!uncertain&&!interrupted&&!!(r.running||r.alive);
 const status=uncertain?'停止未确认':interrupted?'已中断':pending?({preparing:'准备中',install:'安装中',build:'构建中',building:'构建中',starting:'启动中'}[r.status]):running?'运行中':({failed:'失败',cancelled:'已取消',exited:'已结束',stopped:'已停止'}[r.status]||'已停止');
 return {pending,uncertain,interrupted,running,status};
}
function runtimeCards(rows){return rows.map(r=>{
 const {pending,uncertain,interrupted,running,status}=runtimeInfo(r);
 const paths=[['独立副本',r.path||r.snapshot||r.directory||r.workspace],['运行日志',r.log_path||r.log||r.logs],['运行标识',r.id]];
 return `<article class="managed-runtime"><div><h3><span>${status}</span> · <span data-user-content>${esc(versionTitle(commit(r.sha)||{sha:r.sha,subject:uiText('历史版本')}))}</span></h3>${pending?'<p>启动尚未完成，可在下方操作进度取消任务。</p>':''}${interrupted?`<p>${r.running?'启动任务已中断，可停止残留进程。副本与日志会保留。':'启动任务已中断，副本与日志已保留。'}</p>`:''}${uncertain?`<p class="data-warning">${esc(r.cleanup_error||r.recovery_error||'尚未确认此预览服务已停止，请重试停止。')}</p>`:''}${r.error?`<p class="data-warning">${esc(r.error)}</p>`:''}</div><div class="runtime-actions">${running&&r.url?`<a class="secondary-button" href="${esc(r.url)}" target="_blank" rel="noopener">打开运行预览 ↗</a>`:''}${running||uncertain||interrupted?`<button class="text-button" data-action="stop-runtime" data-runtime="${esc(r.id)}">${uncertain?'重试停止':interrupted?(r.running?'停止残留进程':'确认结束'):'停止运行'}</button>`:''}<button class="text-button" data-action="runtime-version" data-id="${esc(r.sha)}">查看此版本</button></div><details data-keep-open="runtime-${esc(r.id)}"><summary>运行记录与本地目录</summary><dl>${paths.filter(([,v])=>v).map(([label,value])=>`<dt>${label}</dt><dd><code>${esc(typeof value==='object'?JSON.stringify(value):value)}</code></dd>`).join('')}</dl></details></article>`;
 }).join('');}
function jobWarnings(){return (state.jobWarnings||[]).map(w=>`<p class="snapshot-message" role="alert">${uiText('这份任务记录无法读取，已保留原文件，其他任务可继续使用。')} <code>${esc(w.file)}</code></p>`).join('');}
function managementContent(){
 const rows=state.runtimes.filter(r=>workspaceProjectIds().has(r.project_id)),active=rows.filter(r=>{const info=runtimeInfo(r);return info.pending||info.running||info.uncertain||(info.interrupted&&r.running);});
 return `${jobWarnings()}<section class="settings-section"><div class="settings-line"><div><h3>当前工作区</h3><p data-user-content>${esc(versionTitle(commit(state.project?.head)||{sha:state.project?.head,subject:uiText('历史版本')}))}</p></div><button class="secondary-button" data-action="working">查看当前改动</button></div></section><section class="settings-section"><div class="settings-line"><div><h3>预览服务</h3><p>${active.length} 个活动或待确认的服务 · ${rows.length} 条保留记录</p></div><button class="text-button" data-action="refresh-management">刷新状态</button></div>${rows.length?runtimeCards(rows):'<p class="management-empty">没有运行中的预览服务。</p>'}</section><section class="settings-section"><h3>操作进度</h3>${renderJobs()}${state.jobs.some(j=>!j.dismissed&&workspaceProjectIds().has(j.project_id))?'':'<p class="management-empty">没有待处理的任务。</p>'}<p class="snapshot-message">运行副本、日志和媒体保留在本机数据目录。</p></section>`;
}
const parityActions={
 'workspace-view':b=>setWorkspaceView(b.dataset.view),
 language:b=>changeLanguage(b.dataset.language),
 'refresh-management':async()=>{await refreshWorkspace();refreshSettingsManagement();},
 'runtime-version':async b=>{closeDialog();setWorkspaceView('versions');await choose(b.dataset.id);},
 'working-head':async()=>{closeDialog();setWorkspaceView('versions');await choose(state.project.head);},
 'media-step':async b=>{
  const next=state.openMedia.position+Number(b.dataset.direction),item=state.openMedia.items[next];
  if(item)await showMedia(item.record,String(item.index));
 },
 'media-zoom':b=>{
  const img=$('.large-media img');if(!img?.naturalWidth){notify('资料尺寸尚未载入，请稍后再试。');return;}
  state.openMedia.zoom=b.dataset.zoom;
  img.style.width=b.dataset.zoom==='fit'?'100%':Math.round(img.naturalWidth*Number(b.dataset.zoom)/100)+'px';
  $$('[data-action=media-zoom]').forEach(element=>element.setAttribute('aria-pressed',element===b));
 },
 'retry-job':async b=>{
  const job=state.jobs.find(j=>j.id===b.dataset.job);if(!job?.request?.sha)return;
  const next=await api(`/api/projects/${job.project_id}/${job.operation}`,{method:'POST',body:JSON.stringify(job.request)});
  job.dismissed=true;state.jobs.push(next);renderDetail();refreshSettingsManagement();pollWorkspaceJob(next.id);
 }
};
function changeLanguage(language){
 if(!['zh','en'].includes(language))return;
 const presentationDraft=$('#project-presentation')?.value;
 const settingsOpen=$('#dialog').open&&$('#dialog').classList.contains('settings-dialog');
 const snapshotDraft=$('#dialog').open&&$('#content-version-title')?{title:$('#content-version-title').value,initialPreviewMode:$('#initial-preview-choice')?.value,mode:$('#preview-preference-mode')?.value}:null;
 const preferenceDraft=$('#dialog').open&&$('#dialog').dataset.previewPreferences?{mode:$('#preview-preference-mode').value}:null;
 const recoveryDraft=$('#dialog').open&&$('#dialog').dataset.recoveryForm?{...state.recoveryTarget,to:$('#restore-path').value}:null;
 const recoveryResultJob=$('#dialog').open&&$('#dialog').dataset.recoveryResult?state.recoveryResultJob:null;
 const fileComparison=$('#dialog').open&&$('#dialog').dataset.fileComparison?state.fileComparison:null;
 const returnContext=dialogParent;
 const savedPreview=$('#dialog [data-saved-preview]')?state.savedPreviewJob:null;
 const quickPreview=$('#dialog').open&&$('#dialog').dataset.quickPreview?{...state.quickPreviewTarget}:null;
 const importDraft=$('#dialog #folder-import-name')?readImportDraft():null;
 const importReport=$('#dialog #folder-import-report')?state.importReport:null;
 const importCost=$('#dialog #folder-import-preflight')?state.importCost:null;
 const importCostFailure=$('#dialog #folder-import-preflight-failure')?state.importCostFailure:null;
 uiLanguage=language;try{localStorage.setItem('reprise.language',uiLanguage);}catch{}
 const url=new URL(location.href);url.searchParams.set('lang',uiLanguage);history.replaceState(null,'',url);
 // Keep unrelated editors and their user-entered values open while translating.

 const origin=$('#history-origin'),archive=state.historySources.filter(s=>s.kind==='archive').reduce((n,s)=>n+s.unique_commits,0),current=state.historySources.find(s=>s.kind==='current')?.count||state.commits.length;
 origin.textContent=uiLanguage==='en'?`${current} repository commits · ${archive} archived records`:`当前仓库 ${current} 条 · 历史存档 ${archive} 条`;
 renderHistory();keepSelectedHistoryVisible();renderDetail();
 if(settingsOpen){const dialog=$('#dialog'),top=dialog.scrollTop;$('#dialog .dialog-body').innerHTML=settingsContent();dialog.scrollTop=top;if(presentationDraft)$('#project-presentation').value=presentationDraft;}
 if(recoveryDraft)recoveryDialog(recoveryDraft.paths,recoveryDraft,{parent:returnContext});
 else if(recoveryResultJob)recoveryResult(recoveryResultJob,{parent:returnContext});
 else if(fileComparison){renderFileComparison();}
 else if(snapshotDraft)snapshotDialog(snapshotDraft);
 else if(preferenceDraft)previewPreferencesDialog(preferenceDraft);
 else if(savedPreview)savedPreviewDialog(savedPreview);
 else if(quickPreview)quickPreviewDialog(quickPreview.root,quickPreview).catch(error=>notify(error.message));
 else if(importDraft)importFoldersDialog(importDraft);
 else if(importReport)importReportDialog(importReport);
 else if(importCost)importCostDialog(importCost.preview,importCost.input);
 else if(importCostFailure)importCostFailureDialog(importCostFailure);
 localizeDOM();refreshContentStatus();if(settingsOpen)$(`#dialog [data-action=language][data-language=${uiLanguage}]`)?.focus({preventScroll:true});
}
document.addEventListener('change',async e=>{try{if(['compare-base','compare-target'].includes(e.target.id))await changeComparison(e.target);}catch(error){notify(error.message);}});
window.addEventListener('hashchange',()=>{if(state.project)setWorkspaceView(location.hash==='#resources'?'resources':'versions');});
