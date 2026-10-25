'use strict';
// Full workspace actions use the canonical API and remain bound to exact SHAs.
const transferOperations=['relink-check','relink','migrate','backup-check','data-restore'];
const transferJobLabels={
 'relink-check':['检查新位置','Inspect new location'],relink:['重新关联','Relink project'],
 migrate:['复制并迁移','Copy and relocate'],'backup-check':['检查备份','Verify backup'],
 'data-restore':['恢复数据目录','Restore data directory']
};
function transferLabel(operation){const pair=transferJobLabels[operation];return pair?contentText(...pair):operation;}
function versionNotes(c){return detail(c.sha)?.notes?.localizations?.[uiLanguage]||c.notes?.localizations?.[uiLanguage];}
function versionTitle(c){return versionNotes(c)?.title||c.subject||'无提交说明';}
function versionLabel(c){return c.archived?uiText('历史存档'):c.parents.length?'历史版本':'项目起点';}
function versionCaption(c){return versionNotes(c)?.summary||(detail(c.sha)?summary(detail(c.sha)):uiText('选择版本查看实际文件变化'));}
function updateExplanations(d){const notes=versionNotes(d.commit);return `<section class="release-notes editable-region"><div class="release-notes-heading"><h3>更新说明</h3><button class="edit-entry edit-notes" data-action="edit-release-notes" aria-label="编辑更新说明" title="编辑更新说明">${icon('pencil')}</button></div>${notes?.changes?.length?`<ul data-user-content>${notes.changes.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:'<p class="snapshot-message">暂无更新说明。</p>'}${d.notes?.source?`<p class="snapshot-message">${esc(d.notes.source)}</p>`:''}</section>`;}
function compareDialog(){return setDetailTab('compare');}
async function applyComparison(base,target){
 const project=state.project.id,n=++state.comparisonRequest;state.comparisonLoading=true;state.comparisonError=null;
 if(state.tab==='compare')renderDetail();
 try{
  const diff=await api(query('/api/workspace/diff',{project,base,target}));if(n!==state.comparisonRequest||project!==state.project.id)return;
  for(const sha of [diff.base,diff.target])if(!commit(sha)){const d=await loadDetail(sha,undefined,diff.source_project_id);if(n!==state.comparisonRequest||project!==state.project.id)return;addCommit({...d.commit,source_project_id:diff.source_project_id,refs:state.refs.filter(r=>r.sha===sha).map(r=>r.name),notes:d.notes});}
  prepareGraph();await choose(diff.target,{fromComparison:true});if(n!==state.comparisonRequest||project!==state.project.id||state.selected!==diff.target)return;
  await loadDetail(diff.base);if(n!==state.comparisonRequest||project!==state.project.id)return;
  state.comparison={project,source_project_id:diff.source_project_id,base:diff.base,target:diff.target,diff};Object.assign(comparisonSelection(),{base:diff.base,target:diff.target});state.comparisonLoading=false;renderHistory();renderDetail();
 }catch(error){if(n!==state.comparisonRequest||project!==state.project.id)return;state.comparisonLoading=false;state.comparisonError=error.message;renderDetail();}
}
function renderComparison(){
 const picker=comparisonPicker();
 if(state.comparisonLoading)return picker+`<p class="comparison-hint" role="status">${uiText('正在比较所选版本…')}</p>`;
 if(state.comparisonError)return picker+`<div class="empty-preview"><h3>${uiText('读取失败')}</h3><p data-user-content>${esc(state.comparisonError)}</p><button class="secondary-button" data-action="retry-comparison">${uiText('重试')}</button></div>`;
 if(!state.comparison)return picker+`<p class="comparison-hint">${contentText('选择任意两版，查看 A → B 的变化。','Choose any two versions to inspect A → B changes.')}</p>`;
 const a=detail(state.comparison.base),b=detail(state.comparison.target);
 const files=`<section class="compare-files"><h3>${contentText('A → B 文件变化','A → B file changes')}</h3><p class="snapshot-message">${contentText('打开文件即可比较文本，并选择恢复 A 或 B。','Open a file to compare text and recover from A or B.')}</p><div class="changed-files">${fileRows(state.comparison.diff.files)||`<p>${contentText('两版文件相同。','Files are identical in both versions.')}</p>`}</div></section>`;
 const evidence=mediaItems(a).some(visualEvidence)||mediaItems(b).some(visualEvidence);
 const previews=evidence?`<div class="compare-media-columns">${[[a,contentText('A · 基准版本','A · Base version')],[b,contentText('B · 目标版本','B · Target version')]].map(([d,label])=>`<section class="comparison-side"><h3>${label}</h3><p data-user-content>${esc(versionTitle(d.commit))}</p>${renderPreview(d,{comparison:true,pairedTarget:b})}</section>`).join('')}</div>`:'';
 const visual=visualPresentation(b);
 return picker+`<p class="snapshot-message">${esc(comparisonSummary(state.comparison.diff))}</p>`+(visual?previews+files:files+previews)+(visual&&!evidence?`<p class="snapshot-message">${contentText('这两版没有可用的预览资料；文件比较仍可使用。','Neither version has available previews; file comparison is available.')}</p>`:'');
}
function renderJobs(){return state.jobs.filter(job=>!job.dismissed&&(workspaceProjectIds().has(job.project_id)||['storage','backup-check','data-restore','import-folders','folder-import-review','folder-import-preflight'].includes(job.operation))).map(job=>{
 const terminal=['complete','failed','cancelled'].includes(job.status),capture=job.operation==='capture',result=capture?job.result:null;
 const status=capture&&result?captureResultText(result):uiText(captureStatus(job));
 return `<div class="job-row"><span role="status">${esc(uiText({...Object.fromEntries(Object.keys(transferJobLabels).map(k=>[k,transferLabel(k)])),'verify':contentText('版本完整性检查','Version integrity check'),'storage':contentText('本机存储统计','Local storage report'),'version-estimate':contentText('\u6a21\u62df\u7a7a\u95f4\u4f30\u7b97','Simulate storage savings'),'version-delete':contentText('删除版本并回收','Delete versions and reclaim'),'organize':'整理副本','folder-import-preflight':contentText('空间预检','Storage cost preview'),'import-folders':contentText('导入版本合集','Import version collection'),'folder-import-review':contentText('复核原件报告','Recheck originals'),'snapshot':'记录版本','run':'运行版本','capture':'采集预览','ai/suggest':contentText('AI 分析（历史任务）','AI analysis (historical task)'),'restore':'恢复版本','export':'导出 ZIP'}[job.operation]||job.operation))} · <span data-user-content>${esc(['storage','backup-check','data-restore'].includes(job.operation)?contentText('应用数据目录','Application data directory'):['import-folders','folder-import-review','folder-import-preflight'].includes(job.operation)?(job.request?.name||contentText('版本合集','Version collection')):versionTitle(commit(job.request?.sha)||{sha:job.request?.sha,subject:uiText('历史版本')}))}</span> · ${esc(status)}${job.error?`<br><span data-user-content>${esc(job.error)}</span>`:''}</span>${['queued','running'].includes(job.status)&&job.cancellable?`<button class="text-button" data-action="cancel-job" data-job="${esc(job.id)}">取消任务</button>`:''}${['failed','cancelled'].includes(job.status)&&job.request?.sha&&!['restore','export','ai/suggest'].includes(job.operation)?`<button class="text-button" data-action="retry-job" data-job="${esc(job.id)}">重试</button>`:''}${terminal&&['restore','export'].includes(job.operation)?`<button class="text-button" data-action="recovery-result" data-job="${esc(job.id)}">查看结果</button>`:''}${job.status==='complete'&&job.operation==='organize'?`<button class="text-button" data-action="content-plan" data-plan="${esc(job.result.id)}">${contentText('查看副本选择','Review copies')}</button>`:''}${terminal&&['verify','storage'].includes(job.operation)?`<button class="text-button" data-action="content-maintenance-result" data-job="${esc(job.id)}">${contentText('查看结果','View result')}</button>`:''}${terminal&&transferOperations.includes(job.operation)?`<button class="text-button" data-action="transfer-result" data-job="${esc(job.id)}">${contentText('查看回执','View receipt')}</button>`:''}${terminal&&['version-delete','version-estimate'].includes(job.operation)?`<button class="text-button" data-action="${job.operation==='version-estimate'?'version-estimate-result':'version-delete-result'}" data-job="${esc(job.id)}">${job.operation==='version-estimate'?contentText('\u67e5\u770b\u4f30\u7b97','View estimate'):contentText('\u67e5\u770b\u5220\u9664\u56de\u6267','View deletion receipt')}</button>`:''}${terminal&&job.operation==='folder-import-preflight'?`<button class="text-button" data-action="import-cost-result" data-job="${esc(job.id)}">${contentText('查看空间预检','View cost preview')}</button>`:''}${terminal&&['import-folders','folder-import-review'].includes(job.operation)?`<button class="text-button" data-action="import-job-report" data-job="${esc(job.id)}">${contentText('查看原件与空间报告','View originals and space report')}</button>`:''}${terminal?`<button class="text-button" data-action="dismiss-job" data-job="${esc(job.id)}">收起</button>`:''}${capture&&terminal?captureDiagnostics(result,{error:job.error,key:job.id,force:true}):''}</div>`;
 }).join('');}
function renderRuntimes(d){return state.runtimes.filter(r=>r.project_id===revisionProject(d.commit.sha)&&r.sha===d.commit.sha&&runtimeInfo(r).running&&r.url).map(r=>`<div class="runtime-row"><span>运行中</span><a class="text-button" href="${esc(r.url)}" target="_blank" rel="noopener">打开运行预览 ↗</a><button class="text-button" data-action="inline-preview" data-runtime="${esc(r.id)}">嵌入预览</button></div>`).join('');}
function recipeDialog(){state.recipeReturnToSettings=$('#dialog').classList.contains('settings-dialog');const d=detail(state.selected);if(!d)return;const candidates=d.detection?.candidates||[];state.recipeTarget={project:revisionProject(),sha:state.selected};state.recipeCandidates=candidates;const initial=d.recipe;dialogShell('运行与采集配置',`<p class="project-path">${esc(versionTitle(commit(state.selected)))}</p><p>核对并保存此版本的配置后，再点击运行或采集。项目命令在独立副本中执行。</p>${state.project?.preview_preferences?.pending_recipe?`<p>${contentText('本项目已选择后续留稿都保存画面；这次确认的配置也会作为后续模板。配置变更时需要另行确认。','This project is set to include images on future saves. These reviewed settings also become its future template; changes need another review.')}</p>`:''}${candidates.filter(c=>c.recipe).length?`<label class="field">识别到的入口<select id="recipe-candidate"><option value="">当前配置 / 手工填写</option>${candidates.map((c,i)=>c.recipe?`<option value="${i}">${esc(c.root)} · ${esc(c.label)}</option>`:'').join('')}</select></label>`:''}<details class="recipe-advanced" ${initial?.adapter==='command-web'?'open':''}><summary>高级配置 JSON</summary><label class="field">配置 JSON<textarea id="recipe-json" rows="14" spellcheck="false">${esc(JSON.stringify(initial||{schema:1,adapter:'manual',root:'.',commands:{},readiness:{path:'/',timeout_ms:15000},captures:[],network:'local'},null,2))}</textarea></label></details><p class="snapshot-message">${d.recipe_approved?'此版本已有保存的配置。':'此版本尚未保存配置。'} 保存本身不会运行项目。</p>`,`<button class="secondary-button" data-action="${state.recipeReturnToSettings?'settings':'close'}">${state.recipeReturnToSettings?'返回设置':'返回'}</button><button class="primary-button" data-action="save-recipe">保存此版本配置</button>`,true);}
function notesDialog(){const d=detail(state.selected);if(!d)return;state.notesDraft=d.notes?.localizations||{zh:{title:commit(state.selected).subject,summary:summary(d),changes:[summary(d)]},en:{title:commit(state.selected).subject,summary:`${d.diff.counts.total||0} changed files in this commit.`,changes:[`${d.diff.counts.total||0} changed files in this commit.`]}};dialogShell('编辑版本说明',`<p>说明保存到当前版本的本机资料。Git 原始提交信息始终保留。</p><div class="notes-columns">${[['zh','中文'],['en','English']].map(([lang,label])=>`<section><h3>${label}</h3><label class="field">标题<input id="notes-${lang}-title" maxlength="120" value="${esc(state.notesDraft[lang]?.title)}"></label><label class="field">摘要<textarea id="notes-${lang}-summary" rows="3">${esc(state.notesDraft[lang]?.summary)}</textarea></label><label class="field">更新内容（每行一条）<textarea id="notes-${lang}-changes" rows="5">${esc(state.notesDraft[lang]?.changes?.join('\n'))}</textarea></label></section>`).join('')}</div>`,`<button class="secondary-button" data-action="close">返回</button><button class="primary-button" data-action="save-notes">保存版本说明</button>`,true);}
function manualDialog(){
 const parent=captureDialogContext();
 state.manualTarget={project:revisionProject(),sha:state.selected};
 dialogShell('导入截图 / 录屏',`<p>复制资料并绑定 ${short(state.selected)}。原文件会保留，来源标记为手工提供。</p><label class="field">本地文件完整路径<input id="manual-path" autocomplete="off"></label><label class="field">资料类型<select id="manual-kind"><option value="image">图片 / 截图</option><option value="video">视频 / 录屏</option><option value="file">其他文件</option></select></label><label class="field">标题<input id="manual-title" maxlength="200"></label><label class="field">场景标识（可选）<input id="manual-capture"></label>`,
  `<button class="secondary-button" data-action="close">${parent?'返回设置':'返回'}</button><button class="primary-button" data-action="save-manual">复制并绑定此版本</button>`,false,parent);
 $('#manual-path').focus();
}
async function saveManualEvidence(){
 const {project,sha}=state.manualTarget,request=state.dialogRequest;
 await api(`/api/projects/${project}/evidence/manual`,{method:'POST',body:JSON.stringify({sha,path:$('#manual-path').value.trim(),kind:$('#manual-kind').value,title:$('#manual-title').value.trim(),capture_id:$('#manual-capture').value.trim()})});
 state.details.delete(`${project}:${sha}`);await loadDetail(sha,undefined,project);
 if(workspaceProjectIds().has(project)&&typeof loadDraftImages==='function')loadDraftImages();
 if(request!==state.dialogRequest||!$('#dialog').open||state.selected!==sha||revisionProject()!==project){
  notify('资料已复制到证据库，原文件保持不变。');return;
 }
 closeDialog({returnToParent:false});state.tab='preview';renderDetail();
 $('#tab-preview')?.focus({preventScroll:true});notify('资料已复制到证据库，原文件保持不变。');
}

function mergeWorkspaceJobs(items){
 const local=new Map(state.jobs.map(j=>[j.id,j]));
 for(const j of items)local.set(j.id,{...local.get(j.id),...j});
 const rows=[...local.values()],active=j=>['queued','running','cancelling'].includes(j.status);
 const recent=rows.filter(j=>!active(j)).sort((a,b)=>(b.finished_at||b.created_at||'').localeCompare(a.finished_at||a.created_at||''));
 state.jobs=[...rows.filter(active),...recent.slice(0,30)];
}
let runtimeRequest=0;
async function refreshWorkspace(){
 const request=++runtimeRequest;
 const b=await api(query('/api/bootstrap',{include_projects:'0'}));
 token=b.token;if(request===runtimeRequest)state.runtimes=b.runtimes;state.jobWarnings=b.job_warnings||[];
 mergeWorkspaceJobs(b.jobs||[]);
 for(const j of state.jobs)if(['queued','running','cancelling'].includes(j.status))pollWorkspaceJob(j.id);
 refreshSettingsManagement();
}
let runtimeProgress=null,lastRuntimeProgress=0;
async function refreshRuntimeProgress(){
 if(runtimeProgress)return runtimeProgress;
 if(Date.now()-lastRuntimeProgress<1000)return;
 lastRuntimeProgress=Date.now();
 runtimeProgress=(async()=>{
  const request=++runtimeRequest,{runtimes}=await api('/api/runtimes');
  if(request!==runtimeRequest||JSON.stringify(runtimes)===JSON.stringify(state.runtimes))return;
  state.runtimes=runtimes;refreshSettingsManagement();
 })();
 try{await runtimeProgress;}finally{runtimeProgress=null;}
}
async function startWorkspaceAction(operation){if(!['run','capture'].includes(operation))throw Error(contentText('工作台仅支持运行与采集任务。','The workbench only starts run and capture tasks.'));const d=detail(state.selected);if(!d)return;if(!d.recipe_approved){recipeDialog();$('#dialog-status').textContent='先核对并保存此版本的运行配置，再执行。';return;}const project=operation==='capture'&&state.tab==='compare'&&state.comparison&&$('#capture-both')?.checked?state.comparison.source_project_id:revisionProject(),sha=state.selected;const body={sha};if(operation==='capture'&&state.comparison&&$('#capture-both')?.checked)body.base=state.comparison.base;const job=await api(`/api/projects/${project}/${operation}`,{method:'POST',body:JSON.stringify(body)});state.jobs.push(job);renderDetail();refreshSettingsManagement();notify('任务已启动，可在设置中查看进度。');pollWorkspaceJob(job.id);return job;}
const pollingJobs=new Set();
async function pollWorkspaceJob(id){
 if(pollingJobs.has(id))return;
 pollingJobs.add(id);
 try{while(true){
  let job;try{job=await api(`/api/jobs/${id}`);}catch(error){notify(error.message);break;}
  const old=state.jobs.find(item=>item.id===id);
  const changed=!old||old.status!==job.status||old.error!==job.error||old.finished_at!==job.finished_at;
  if(old)Object.assign(old,job);else state.jobs.push(job);
  if(changed&&(workspaceProjectIds().has(job.project_id)||['storage','backup-check','data-restore','import-folders','folder-import-review','folder-import-preflight'].includes(job.operation)))refreshSettingsManagement();
  if(['complete','failed','cancelled'].includes(job.status)){
   if(['restore','export'].includes(job.operation)&&$('#dialog [data-recovery-job]')?.dataset.recoveryJob===job.id)recoveryResult(job);
   if(transferOperations.includes(job.operation)){await transferFinished(job);break;}
   if(['verify','storage'].includes(job.operation)){await maintenanceFinished(job);break;}
   if(job.operation==='organize'){await organizationFinished(job);break;}
   if(job.operation==='snapshot'){await folderSnapshotFinished(job);break;}
   if(job.operation==='version-delete'){await versionDeletionFinished(job);break;}
   if(job.operation==='version-estimate'){versionEstimateFinished(job);break;}
   if(['import-folders','folder-import-review','folder-import-preflight'].includes(job.operation)){await importFoldersFinished(job);break;}
   // Partial and cancelled captures can already contain saved artifacts. Invalidate
   // their exact project/SHA keys even when the user is viewing another revision.
   const affected=new Set([job.request?.sha,job.request?.base,job.result?.sha,job.result?.base].filter(Boolean));
   for(const sha of affected)state.details.delete(`${job.project_id}:${sha}`);
   await refreshWorkspace();
   if(workspaceProjectIds().has(job.project_id)){
    const project=state.project.id,selected=state.selected;
    const visible=new Set([selected,state.comparison?.base,state.comparison?.target,state.tab==='updates'?detail(selected)?.diff.base:null].filter(Boolean));
    const reload=[...visible].filter(sha=>affected.has(sha)&&revisionProject(sha)===job.project_id);
    try{
     await Promise.all(reload.map(sha=>loadDetail(sha,undefined,job.project_id)));
     if(project===state.project?.id&&selected===state.selected&&reload.length){
      const current=detail(selected);
      if(state.tab==='updates')await ensureUpdateBaseline(current);
      if(project===state.project?.id&&selected===state.selected)renderDetail();
     }
    }catch(error){notify(uiText('读取失败')+'：'+error.message);}
    if(project===state.project?.id){
     if(job.operation==='capture'){notify(captureJobNotice(job));if(typeof loadDraftImages==='function')loadDraftImages();}
     else if(job.status==='complete'&&['restore','export'].includes(job.operation))notify('恢复 / 导出已完成，可在设置中查看结果。');
     else if(job.status==='complete'&&job.operation==='run')notify('版本已运行，可打开预览。');
     else if(job.error)notify(job.error);
    }
   }
   break;
  }
  if(['run','capture'].includes(job.operation)&&workspaceProjectIds().has(job.project_id)&&$('#dialog').open&&$('#dialog').classList.contains('settings-dialog')){
   try{await refreshRuntimeProgress();}catch(error){notify(error.message);}
  }
  await new Promise(resolve=>setTimeout(resolve,1200));
 }}catch(error){notify(error.message);}finally{pollingJobs.delete(id);}
}
async function showMedia(record,index){
 const d=detail(state.selected);if(!d)return;
 const baseline=state.tab==='compare'&&state.comparison?state.comparison.base:d.diff.base;
 const items=mediaGallery(d,detail(baseline),baseline),position=items.findIndex(item=>item.record===record&&String(item.index)===String(index)),item=items[position];
 if(!item)return;
 state.openMedia={items,position,zoom:'fit'};
 const origin=$('#dialog').open?returnFocus:null;
 dialogShell(item.title||item.name||'版本预览',`<div class="media-tools"><button class="text-button" data-action="media-step" data-direction="-1" ${position===0?'disabled':''}>上一项</button><span data-user-content>${position+1} / ${items.length}</span><button class="text-button" data-action="media-step" data-direction="1" ${position===items.length-1?'disabled':''}>下一项</button>${item.kind==='image'?'<div><button class="text-button" data-action="media-zoom" data-zoom="fit" aria-pressed="true">适应窗口</button><button class="text-button" data-action="media-zoom" data-zoom="100" aria-pressed="false">100%</button><button class="text-button" data-action="media-zoom" data-zoom="200" aria-pressed="false">200%</button></div>':''}</div><div class="large-media">${item.kind==='video'?`<video src="${esc(item.url)}" controls autoplay></video>`:`<img src="${esc(item.url)}" alt="${esc(item.title||'保存的预览')}">`}</div>`,`<button class="secondary-button" data-action="close">返回版本</button><a class="secondary-button" href="${esc(item.url)}" target="_blank" rel="noopener">打开原文件 ↗</a>`,true);
 $('#dialog-title').setAttribute('data-user-content','');if(origin)returnFocus=origin;
}
// Named handlers keep each operation inspectable without a cross-file switch chain.
const featureActions={
 'edit-version':()=>inlineNotesDialog('metadata'),
 'edit-summary':()=>inlineNotesDialog('summary'),
 'edit-release-notes':()=>inlineNotesDialog('changes'),
 'save-inline-notes':()=>saveInlineNotes(),
 compare:compareDialog,
 'apply-comparison':()=>compareSelection(),
 'swap-comparison':async()=>{
  const {base,target}=comparisonSelection();state.comparisonDraft={base:target,target:base};
  await applyComparison(target,base);
 },
 'retry-comparison':()=>compareSelection(),
 'reset-comparison':()=>{state.comparison=null;state.tab='updates';renderDetail();},
 recipe:()=>recipeDialog(),
 notes:()=>notesDialog(),
 manual:manualDialog,
 run:()=>startWorkspaceAction('run'),
 capture:()=>startWorkspaceAction('capture'),
 'save-recipe':async()=>{
  const {project,sha}=state.recipeTarget,recipe=JSON.parse($('#recipe-json').value);
  if(project!==revisionProject()||sha!==state.selected)throw Error('编辑对象已经变化，请重新打开。');
  await api(`/api/projects/${project}/recipe`,{method:'PUT',body:JSON.stringify({sha,recipe})});
  state.details.delete(cacheKey(sha));await loadDetail(sha);closeDialog();renderDetail();
  if(state.recipeReturnToSettings)await settings();
  notify('此版本配置已保存，尚未运行。');
 },
 'save-notes':async()=>{
  const project=revisionProject(),sha=state.selected;
  const localizations=Object.fromEntries(['zh','en'].map(l=>[l,{title:$(`#notes-${l}-title`).value,summary:$(`#notes-${l}-summary`).value,changes:$(`#notes-${l}-changes`).value.split('\n').filter(s=>s.trim())}]));
  await api(`/api/projects/${project}/notes`,{method:'PUT',body:JSON.stringify({sha,localizations})});
  state.details.delete(cacheKey(sha));await loadDetail(sha);commit(sha).notes=detail(sha).notes;
  closeDialog();renderHistory();renderDetail();notify('版本说明已保存。');
 },
 'save-manual':saveManualEvidence,
 'cancel-job':b=>api(`/api/jobs/${b.dataset.job}/cancel`,{method:'POST',body:'{}'}),
 'dismiss-job':b=>{state.jobs.find(j=>j.id===b.dataset.job).dismissed=true;renderDetail();refreshSettingsManagement();},
 'stop-runtime':async b=>{
  try{await api(`/api/runtimes/${b.dataset.runtime}/stop`,{method:'POST',body:'{}'});}
  finally{await refreshWorkspace();renderDetail();}
 },
 media:b=>showMedia(b.dataset.record,b.dataset.index)
};
