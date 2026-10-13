'use strict';
// Full workspace actions use the canonical API and remain bound to exact SHAs.
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
function renderComparison(){const picker=comparisonPicker();if(state.comparisonLoading)return picker+'<p class="comparison-hint" role="status">正在比较所选版本…</p>';if(state.comparisonError)return picker+`<div class="empty-preview"><h3>读取失败</h3><p>${esc(state.comparisonError)}</p><button class="secondary-button" data-action="retry-comparison">重试</button></div>`;if(!state.comparison)return picker+'<p class="comparison-hint">选择任意两版，查看 A → B 的实际变化和各自保存的预览。</p>';const a=detail(state.comparison.base),b=detail(state.selected);return picker+`<p class="snapshot-message">${esc(comparisonSummary(state.comparison.diff))}</p><div class="compare-media-columns">${[[a,'A · 基准版本'],[b,'B · 目标版本']].map(([d,label])=>`<section class="comparison-side"><h3>${label}</h3><p data-user-content>${esc(versionTitle(d.commit))}</p>${renderPreview(d,{comparison:true,pairedTarget:b})}</section>`).join('')}</div><div class="compare-files"><h3>A → B 文件变化</h3><div class="changed-files">${fileRows(state.comparison.diff.files)||'<p class="empty-content">两版文件相同。</p>'}</div></div>`;}
function renderJobs(){return state.jobs.filter(job=>!job.dismissed&&workspaceProjectIds().has(job.project_id)).map(job=>{
 const terminal=['complete','failed','cancelled'].includes(job.status),capture=job.operation==='capture',result=capture?job.result:null;
 const status=capture&&result?captureResultText(result):uiText(captureStatus(job));
 return `<div class="job-row"><span role="status">${esc(uiText({'run':'运行版本','capture':'采集预览','ai/suggest':'AI 分析'}[job.operation]||job.operation))} · <span data-user-content>${esc(versionTitle(commit(job.request?.sha)||{sha:job.request?.sha,subject:uiText('历史版本')}))}</span> · ${esc(status)}${job.error?`<br><span data-user-content>${esc(job.error)}</span>`:''}</span>${job.status==='complete'&&job.operation==='ai/suggest'?`<button class="text-button" data-action="review-ai" data-job="${esc(job.id)}">查看建议</button>`:''}${['queued','running'].includes(job.status)&&job.cancellable?`<button class="text-button" data-action="cancel-job" data-job="${esc(job.id)}">取消任务</button>`:''}${['failed','cancelled'].includes(job.status)&&job.request?.sha?`<button class="text-button" data-action="retry-job" data-job="${esc(job.id)}">重试</button>`:''}${terminal?`<button class="text-button" data-action="dismiss-job" data-job="${esc(job.id)}">收起</button>`:''}${capture&&terminal?captureDiagnostics(result,{error:job.error,key:job.id,force:true}):''}</div>`;
 }).join('');}
function renderRuntimes(d){return state.runtimes.filter(r=>r.project_id===revisionProject(d.commit.sha)&&r.sha===d.commit.sha&&runtimeInfo(r).running&&r.url).map(r=>`<div class="runtime-row"><span>运行中</span><a class="text-button" href="${esc(r.url)}" target="_blank" rel="noopener">打开运行预览 ↗</a></div>`).join('');}
function recipeDialog(proposal=null){state.recipeReturnToSettings=$('#dialog').classList.contains('settings-dialog');const d=detail(state.selected);if(!d)return;state.recipeProposal=proposal;const candidates=d.detection?.candidates||[];state.recipeCandidates=candidates;const initial=proposal?.recipe||d.recipe;dialogShell('运行与采集配置',`<p class="project-path">${esc(versionTitle(commit(state.selected)))}</p><p>核对并保存此版本的配置后，再点击运行或采集。项目命令在独立副本中执行。</p>${candidates.filter(c=>c.recipe).length?`<label class="field">识别到的入口<select id="recipe-candidate"><option value="">当前配置 / 手工填写</option>${candidates.map((c,i)=>c.recipe?`<option value="${i}">${esc(c.root)} · ${esc(c.label)}</option>`:'').join('')}</select></label>`:''}<label class="field">配置 JSON<textarea id="recipe-json" rows="14" spellcheck="false">${esc(JSON.stringify(initial||{schema:1,adapter:'manual',root:'.',commands:{},readiness:{path:'/',timeout_ms:15000},captures:[],network:'local'},null,2))}</textarea></label><p class="snapshot-message">${d.recipe_approved?'此版本已有保存的配置。':'此版本尚未保存配置。'} 保存本身不会运行项目。</p>`,`<button class="secondary-button" data-action="${state.recipeReturnToSettings?'settings':'close'}">${state.recipeReturnToSettings?'返回设置':'返回'}</button><button class="primary-button" data-action="save-recipe">保存此版本配置</button>`,true);}
function notesDialog(proposal=null){const d=detail(state.selected);if(!d)return;state.notesDraft=proposal?.localizations||d.notes?.localizations||{zh:{title:commit(state.selected).subject,summary:summary(d),changes:[summary(d)]},en:{title:commit(state.selected).subject,summary:`${d.diff.counts.total||0} changed files in this commit.`,changes:[`${d.diff.counts.total||0} changed files in this commit.`]}};dialogShell('编辑版本说明',`<p>说明保存到当前版本的本机资料。Git 原始提交信息始终保留。</p><div class="notes-columns">${[['zh','中文'],['en','English']].map(([lang,label])=>`<section><h3>${label}</h3><label class="field">标题<input id="notes-${lang}-title" maxlength="120" value="${esc(state.notesDraft[lang]?.title)}"></label><label class="field">摘要<textarea id="notes-${lang}-summary" rows="3">${esc(state.notesDraft[lang]?.summary)}</textarea></label><label class="field">更新内容（每行一条）<textarea id="notes-${lang}-changes" rows="5">${esc(state.notesDraft[lang]?.changes?.join('\n'))}</textarea></label></section>`).join('')}</div>`,`<button class="secondary-button" data-action="close">返回</button><button class="primary-button" data-action="save-notes">保存版本说明</button>`,true);}
async function aiSettings(){state.ai=await api('/api/ai');const c=state.ai;dialogShell('AI 设置',`<p>仅在点击「AI 建议」时分析当前版本。建议需要检查并保存，模型由你选择。</p><label class="check-field"><input id="ai-enabled" type="checkbox" ${c.enabled?'checked':''}>启用 AI 建议</label><label class="field">服务类型<select id="ai-provider"><option value="compatible">Chat Completions 兼容服务</option></select></label><label class="field">服务地址<input id="ai-endpoint" type="url" value="${esc(c.endpoint)}" placeholder="https://your-provider.example/v1"></label><label class="field">模型名称<input id="ai-model" value="${esc(c.model)}" placeholder="填写服务支持的模型" autocomplete="off"></label><label class="field">API Key<input id="ai-key" type="password" autocomplete="new-password" placeholder="${c.has_key?'已保存；留空保持原值':'填写密钥'}"></label><label class="check-field"><input id="ai-clear-key" type="checkbox">清除已保存密钥</label><p class="snapshot-message">仅发送当前提交的标题、父提交、变化文件名、最多 300 条文件路径、最多 6 个已提交清单和识别信息。密钥仅保存在本机。启动和浏览不会请求模型。</p>`,`<button class="secondary-button" data-action="settings">返回设置</button><button class="primary-button" data-action="save-ai">保存 AI 设置</button>${c.enabled&&state.selected?'<button class="secondary-button" data-action="ai-suggest">分析当前版本</button>':''}`);}
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
 if(request!==state.dialogRequest||!$('#dialog').open||state.selected!==sha||revisionProject()!==project){
  notify('资料已复制到证据库，原文件保持不变。');return;
 }
 closeDialog({returnToParent:false});state.tab='preview';renderDetail();
 $('#tab-preview')?.focus({preventScroll:true});notify('资料已复制到证据库，原文件保持不变。');
}

function reviewAI(job){
 const p=job.result;if(!p)return;
 const localized=p.localizations?.[uiLanguage];
 if(!localized||!Array.isArray(localized.changes)){
  dialogShell('检查 AI 建议','<p role="alert">此提案是旧版单语内容，请重新请求双语提案。</p>');return;
 }
 state.aiProposal={...p,project:job.project_id,job:job.id};
 dialogShell('检查 AI 建议',`<p class="snapshot-message">${esc(p.model)} · ${esc(versionTitle(commit(p.sha)||{sha:p.sha,subject:uiText('历史版本')}))} · 尚未应用</p><h3 data-user-content>${esc(localized.title)}</h3><p data-user-content>${esc(localized.summary)}</p><ul data-user-content>${localized.changes.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><h3>配置提案</h3><pre class="proposal-json">${esc(JSON.stringify(p.recipe,null,2))}</pre>`,`<button class="secondary-button" data-action="close">返回</button><button class="secondary-button" data-action="review-ai-notes">编辑说明后保存</button>${p.recipe?'<button class="primary-button" data-action="review-ai-recipe">核对运行配置</button>':''}`,true);
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
 token=b.token;state.ai=b.ai;if(request===runtimeRequest)state.runtimes=b.runtimes;state.jobWarnings=b.job_warnings||[];
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
async function startWorkspaceAction(operation){const d=detail(state.selected);if(!d)return;if(operation==='ai/suggest'&&!state.ai.enabled){await aiSettings();return;}if(operation!=='ai/suggest'&&!d.recipe_approved){recipeDialog();$('#dialog-status').textContent='先核对并保存此版本的运行配置，再执行。';return;}const project=operation==='capture'&&state.tab==='compare'&&state.comparison&&$('#capture-both')?.checked?state.comparison.source_project_id:revisionProject(),sha=state.selected;const body={sha};if(operation==='capture'&&state.comparison&&$('#capture-both')?.checked)body.base=state.comparison.base;const job=await api(`/api/projects/${project}/${operation}`,{method:'POST',body:JSON.stringify(body)});state.jobs.push(job);renderDetail();refreshSettingsManagement();notify('任务已启动，可在设置中查看进度。');pollWorkspaceJob(job.id);}
const pollingJobs=new Set();
async function pollWorkspaceJob(id){
 if(pollingJobs.has(id))return;
 pollingJobs.add(id);
 try{while(true){
  let job;try{job=await api(`/api/jobs/${id}`);}catch(error){notify(error.message);break;}
  const old=state.jobs.find(item=>item.id===id);
  const changed=!old||old.status!==job.status||old.error!==job.error||old.finished_at!==job.finished_at;
  if(old)Object.assign(old,job);else state.jobs.push(job);
  if(changed&&workspaceProjectIds().has(job.project_id))refreshSettingsManagement();
  if(['complete','failed','cancelled'].includes(job.status)){
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
     if(job.operation==='capture')notify(captureJobNotice(job));
     else if(job.status==='complete')notify(job.operation==='ai/suggest'?'AI 建议已返回，点击「查看建议」核对。':'版本已运行，可打开预览。');
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
 'history-density':b=>{
  state.prefs.density=b.dataset.density;savePrefs();renderHistory();
  const row=$(`.version-row[data-id="${state.selected}"]`),scroller=$('#history-scroll');
  if(row)scroller.scrollTop=Math.max(0,row.offsetTop-scroller.clientHeight/3);
 },
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
 'ai-settings':aiSettings,
 manual:manualDialog,
 run:()=>startWorkspaceAction('run'),
 capture:()=>startWorkspaceAction('capture'),
 'ai-suggest':()=>startWorkspaceAction('ai/suggest'),
 'save-recipe':async()=>{
  const project=revisionProject(),sha=state.selected,recipe=JSON.parse($('#recipe-json').value);
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
 'save-ai':async()=>{
  const payload={enabled:$('#ai-enabled').checked,provider:$('#ai-provider').value,endpoint:$('#ai-endpoint').value.trim(),model:$('#ai-model').value.trim(),clear_key:$('#ai-clear-key').checked};
  if($('#ai-key').value.trim())payload.api_key=$('#ai-key').value.trim();
  state.ai=await api('/api/ai',{method:'PUT',body:JSON.stringify(payload)});
  closeDialog();await settings();notify('AI 设置已保存，尚未请求模型。');
 },
 'save-manual':saveManualEvidence,
 'review-ai':async b=>{
  const job=state.jobs.find(j=>j.id===b.dataset.job);if(!job||!workspaceProjectIds().has(job.project_id))return;
  setWorkspaceView('versions');if(state.selected!==job.request.sha)await choose(job.request.sha);
  await loadDetail(job.request.sha);reviewAI(job);
 },
 'review-ai-notes':()=>editAIProposal('notes'),
 'review-ai-recipe':()=>editAIProposal('recipe'),
 'cancel-job':b=>api(`/api/jobs/${b.dataset.job}/cancel`,{method:'POST',body:'{}'}),
 'dismiss-job':b=>{state.jobs.find(j=>j.id===b.dataset.job).dismissed=true;renderDetail();refreshSettingsManagement();},
 'stop-runtime':async b=>{
  try{await api(`/api/runtimes/${b.dataset.runtime}/stop`,{method:'POST',body:'{}'});}
  finally{await refreshWorkspace();renderDetail();}
 },
 media:b=>showMedia(b.dataset.record,b.dataset.index)
};
function editAIProposal(kind){
 const proposal=state.aiProposal;
 if(proposal.project!==revisionProject()||proposal.sha!==state.selected){notify('建议与当前版本不匹配。');return;}
 if(kind==='notes')notesDialog(proposal);else recipeDialog(proposal);
}
