'use strict';

// One controller owns capability dispatch, request deduplication and the view
// awaiting a job. A dialog generation, exact version and recipe identify it.
const versionPreviews={submissions:new Map(),view:null};
function versionPreviewLabel(d){
 const mode=d?.actions?.preview?.mode;
 return mode==='saved'?contentText('查看存档画面','View archive image'):
  mode==='recover'?contentText('查看存档说明','View archive details'):
  !d||['run','configure'].includes(mode)?contentText('运行预览','Run preview'):
  contentText('预览不可用','Preview unavailable');
}
function runtimePreviewUrl(runtime){
 try{
  const url=new URL(runtime.url);
  return url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)&&url.port&&!url.username&&!url.password?url:null;
 }catch{return null;}
}
function previewTarget(d){return {project:revisionProject(),sha:d.commit.sha,recipe:d.recipe_hash};}
function selectedPreview(target){
 return revisionProject()===target.project&&state.selected===target.sha&&detail(target.sha)?.recipe_hash===target.recipe;
}
function ownsPreview(view){
 return view&&versionPreviews.view===view&&$('#dialog').open&&state.dialogRequest===view.generation&&selectedPreview(view.target);
}
function previewRecoveryExplanation(){
 versionPreviews.view=null;
 dialogShell(contentText('此存档尚无可用画面','No usable saved image for this archive'),
  `<p>${contentText('这是一份历史资料存档，尚无运行入口或可用的已保存画面。可以取出此版本的文件继续查看。','This historical archive has no runtime entry or usable saved image. Recover its files to inspect the contents.')}</p>`,
  `<button class="secondary-button" data-action="close">${contentText('返回版本','Back to version')}</button><button class="primary-button" data-action="recovery">${contentText('取出这一稿','Recover this draft')}</button>`);
}
function openRuntimePreview(runtime){
 const d=detail(state.selected);if(!d)return false;
 const target=previewTarget(d),url=runtimePreviewUrl(runtime);
 if(runtime.project_id!==target.project||runtime.sha!==target.sha||runtime.recipe_hash!==target.recipe||!runtimeInfo(runtime).running||!url)return false;
 versionPreviews.view=null;
 dialogShell(contentText('运行预览','Running preview'),
  `<div class="running-preview-heading"><p data-user-content>${esc(versionTitle(commit(target.sha)))}</p><a class="text-button" href="${esc(url.href)}" target="_blank" rel="noopener">${contentText('在浏览器打开 ↗','Open in browser ↗')}</a></div><iframe class="live-preview-frame" title="${contentText('运行预览','Running preview')}" sandbox="allow-scripts allow-forms allow-same-origin allow-downloads" src="${esc(url.href)}"></iframe>`,
  `<button class="secondary-button" data-action="close">${contentText('返回版本','Back to version')}</button>`,true,null,'runtime');
 return true;
}
function previewProgress(target,job=null){
 dialogShell(contentText('正在启动预览','Starting preview'),
  `<p data-user-content>${esc(versionTitle(commit(target.sha)))}</p><p role="status">${contentText('正在准备这一版本的运行副本，完成后会在这里显示可交互网页。','Preparing this version’s runtime copy. Its interactive page will appear here when ready.')}</p>`,
  `${job?.cancellable?`<button class="text-button" data-action="cancel-job" data-job="${esc(job.id)}">${contentText('取消启动','Cancel startup')}</button>`:''}<button class="secondary-button" data-action="close">${contentText('返回版本','Back to version')}</button>`,true);
 return versionPreviews.view={target,job:job?.id||null,generation:state.dialogRequest};
}
function finishRunPreview(job){
 const view=versionPreviews.view;
 if(!ownsPreview(view)||view.job!==job.id||job.project_id!==view.target.project||job.request?.sha!==view.target.sha)return false;
 if(job.status==='complete'){
  const runtime=state.runtimes.find(r=>r.id===job.result?.id);
  if(runtime&&openRuntimePreview(runtime))return true;
 }
 versionPreviews.view=null;
 const message=job.error||contentText(job.status==='cancelled'?'预览启动已取消。':'此版本的预览未就绪，请检查运行记录后重试。',job.status==='cancelled'?'Preview startup was cancelled.':'This version’s preview is not ready. Check its runtime record and retry.');
 dialogShell(contentText('预览未打开','Preview did not open'),`<p role="alert" data-user-content>${esc(message)}</p>`,
  `<button class="secondary-button" data-action="close">${contentText('返回版本','Back to version')}</button>`,true);
 return true;
}
async function startVersionPreview(d){
 const target=previewTarget(d),actions=d.actions;
 if(actions?.schema!==1||actions.project_id!==target.project||actions.sha!==target.sha)throw Error(contentText('版本操作信息不完整，请刷新后重试。','Version actions are incomplete. Refresh and retry.'));
 const mode=actions.preview.mode;
 if(mode==='saved'){
  versionPreviews.view=null;
  const selected=actions.preview.media,item=mediaItems(d).find(i=>i.record===selected?.record&&i.index===selected?.index&&i.sha===target.sha&&visualEvidence(i));
  if(item)return showMedia(item.record,item.index);
  previewRecoveryExplanation();return;
 }
 if(mode==='recover'){previewRecoveryExplanation();return;}
 if(mode==='configure'||!d.recipe_approved){
  versionPreviews.view=null;recipeDialog();$('#dialog-status').textContent=contentText('先核对并保存此版本的运行配置，再执行。','Review and save this version’s runtime settings before running.');return;
 }
 if(mode!=='run')throw Error(contentText('此版本不能运行预览。','This version cannot run a preview.'));
 const ready=state.runtimes.find(r=>r.project_id===target.project&&r.sha===target.sha&&r.recipe_hash===target.recipe&&runtimeInfo(r).running&&runtimePreviewUrl(r));
 if(ready){openRuntimePreview(ready);return ready;}
 const pending=state.jobs.find(j=>j.operation==='run'&&j.project_id===target.project&&j.request?.sha===target.sha&&['queued','running','cancelling'].includes(j.status));
 if(pending){previewProgress(target,pending);pollWorkspaceJob(pending.id);return pending;}
 const key=JSON.stringify(target);
 const existing=versionPreviews.submissions.get(key);
 if(existing){if(!ownsPreview(existing.view))existing.view=previewProgress(target);return existing.promise;}
 const request={view:previewProgress(target)};
 versionPreviews.submissions.set(key,request);
 request.promise=(async()=>{
  try{
   const job=await api(`/api/projects/${target.project}/run`,{method:'POST',body:JSON.stringify({sha:target.sha,recipe_hash:target.recipe})});
   const old=state.jobs.find(j=>j.id===job.id);if(old)Object.assign(old,job);else state.jobs.push(job);
   renderDetail();refreshSettingsManagement();
   if(ownsPreview(request.view))previewProgress(target,job);
   pollWorkspaceJob(job.id);return job;
  }catch(error){
   if(ownsPreview(request.view))finishRunPreview({id:request.view.job,project_id:target.project,request:{sha:target.sha},status:'failed',error:error.message});
   else notify(error.message);
   return null;
  }finally{versionPreviews.submissions.delete(key);}
 })();
 return request.promise;
}
