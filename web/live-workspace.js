'use strict';

// Recovery and previews share the same local API as the portable CLI.
function recoveryLocationLabel(value){return String(value||'').replace(/[\\/]+$/,'').split(/[\\/]/).pop()||String(value||'');}
function syncRecoveryDestination(target){
 if(state.recoveryTarget!==target||!$('#dialog').open||!$('#dialog').dataset.recoveryForm)return;
 const input=$('#restore-path'),button=$('#dialog [data-action="save-restore"]'),label=$('#recovery-destination-label'),status=$('#recovery-destination-status');
 if(!input||!button||!label||!status)return;
 const to=input.value.trim();target.to=to;button.disabled=!to;
 label.textContent=to?(target.manualDestination?recoveryLocationLabel(to):target.destinationLabel||recoveryLocationLabel(to)):contentText('新的恢复文件夹','New recovery folder');
 status.textContent=to?contentText('点击恢复后创建，不会覆盖现有文件夹。','Created when you recover; existing folders will not be overwritten.'):target.destinationLoading?contentText('正在准备一个可用的新位置…','Preparing an available new location…'):target.destinationError?contentText('未能自动准备位置。请在“更改位置”中填写一个尚不存在的新文件夹路径。','The location could not be prepared automatically. Enter a new, nonexistent folder path under “Change location”.'):contentText('请填写一个尚不存在的新文件夹路径。','Enter the path of a new, nonexistent folder.');
 status.setAttribute('role',target.destinationError&&!to?'alert':'status');
}
async function loadRecoveryDestination(target,request,input){
 try{
  const suggestion=await api(`/api/projects/${encodeURIComponent(target.project)}/recovery-destination?sha=${encodeURIComponent(target.sha)}`);
  if(state.recoveryTarget!==target||state.dialogRequest!==request||!$('#dialog').open||!$('#dialog').dataset.recoveryForm||$('#restore-path')!==input)return;
  // A pending suggestion must never overwrite a location the user has edited.
  if(target.manualDestination)return;
  if(!suggestion||typeof suggestion.to!=='string'||!suggestion.to.trim())throw Error('No recovery location');
  input.value=suggestion.to;target.destinationLabel=typeof suggestion.display_label==='string'?suggestion.display_label:recoveryLocationLabel(suggestion.to);
  target.destinationLoading=false;target.destinationError=false;syncRecoveryDestination(target);
 }catch(error){
  if(state.recoveryTarget!==target||state.dialogRequest!==request||!$('#dialog').open||!$('#dialog').dataset.recoveryForm||$('#restore-path')!==input||target.manualDestination)return;
  target.destinationLoading=false;target.destinationError=true;
  const details=$('#recovery-change-location');if(details)details.open=true;
  syncRecoveryDestination(target);
 }
}
function recoveryDialog(paths=null,target={},options={}){
 const parent=Object.hasOwn(options,'parent')?options.parent:captureDialogContext(true);
 state.recoveryTarget={project:target.project||revisionProject(),sha:target.sha||state.selected,paths,to:target.to||'',destinationLabel:target.destinationLabel||'',manualDestination:!!target.manualDestination,destinationLoading:!target.to,destinationError:false};
 const t=state.recoveryTarget,c=commit(t.sha)||{sha:t.sha,subject:short(t.sha)},folder=state.project?.kind==='folder';
 dialogShell(contentText('恢复文件','Recover files'),`${previewLanguageControls()}<dl class="recovery-summary"><dt>${contentText('版本','Version')}</dt><dd data-user-content>${esc(versionTitle(c))} · <code>${short(t.sha)}</code></dd><dt>${contentText('恢复范围','Scope')}</dt><dd data-user-content>${paths?paths.map(esc).join('<br>'):contentText('此版本的全部文件','All files in this version')}</dd><dt>${contentText('恢复到','Recover into')}</dt><dd id="recovery-destination-label" data-user-content></dd></dl><p id="recovery-destination-status" role="status"></p><p>${contentText('取回到新目录，当前工作文件夹和其他版本保持原位。','Retrieve into a new folder; the working folder and other versions stay in place.')}</p><details id="recovery-change-location"><summary>${contentText('更改位置','Change location')}</summary><label class="field">${uiText('新的恢复目录')}<input id="restore-path" value="${esc(t.to)}" autocomplete="off" spellcheck="false" placeholder="${uiText('填写尚不存在的目录完整路径')}" aria-describedby="recovery-destination-status"></label></details><details><summary>${contentText('校验范围与 ZIP 导出','Verification scope and ZIP export')}</summary><p>${folder?contentText('恢复保存的字节、权限、时间、已保存扩展属性和目录，并读回核对。排除项、ACL、标志及所有者不在快照中。','Restores saved bytes, modes, times, saved extended attributes and directories, then reads them back. Exclusions, ACLs, flags and ownership are outside the snapshot.'):contentText('从指定 Git 对象取回文件并核对对象散列；不运行过滤器或改写原仓库。LFS 指针和子模块见回执。','Retrieves files from the specified Git objects and checks object hashes, without filters or source changes. See the receipt for LFS pointers and submodules.')}</p><button class="secondary-button" data-action="save-export">${uiText('下载 ZIP')}</button></details>`,`<button class="secondary-button" data-action="close">${parent?contentText('返回上一页','Back'):uiText('返回版本')}</button><button class="primary-button" data-action="save-restore"${t.to?'':' disabled'}>${uiText('恢复到新目录')}</button>`,false,parent);
 $('#dialog').dataset.recoveryForm='true';
 const input=$('#restore-path');
 input.addEventListener('input',()=>{if(state.recoveryTarget!==t)return;t.manualDestination=true;t.destinationLoading=false;t.destinationError=false;syncRecoveryDestination(t);});
 syncRecoveryDestination(t);
 if(!t.to)loadRecoveryDestination(t,state.dialogRequest,input);
}
async function startRecovery(operation){
 const target=state.recoveryTarget;
 if(!target||!workspaceProjectIds().has(target.project)||!commit(target.sha))throw Error(uiText('编辑对象已经变化，请重新打开。'));
 const to=operation==='restore'?$('#restore-path').value.trim():null;
 if(operation==='restore'&&!to)throw Error(uiText('请填写新的恢复目录。'));
 const parent=dialogParent,job=await api(`/api/projects/${target.project}/${operation}`,{method:'POST',body:JSON.stringify({sha:target.sha,to,paths:target.paths})});
 mergeWorkspaceJobs([job]);state.recoveryParents=state.recoveryParents||new Map();state.recoveryParents.set(job.id,parent);
 dialogShell(contentText('正在恢复文件','Recovering files'),`${previewLanguageControls()}<p data-recovery-job="${esc(job.id)}" role="status">${contentText('正在取回指定版本并校验文件…','Retrieving the specified version and verifying files…')}</p><p>${uiText('可以返回版本，稍后在项目设置查看任务结果。')}</p>`,`<button class="secondary-button" data-action="close">${uiText('返回版本')}</button><button class="secondary-button" data-action="cancel-job" data-job="${esc(job.id)}">${uiText('取消任务')}</button>`,false,parent);
 pollWorkspaceJob(job.id);
}
function recoveryContinuationText(job){
 const r=job?.result,paths=r?.paths??job?.request?.paths;
 if(job?.status!=='complete'||job.operation!=='restore'||!r?.path||paths!=null||!/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(r.sha||''))return '';
 const path=JSON.stringify(r.path);
 return contentText(
  `用倒带 / Reprise 继续制作这份已取回的网页。\n本轮工作目录（完整路径）：${path}\n取回版本：${r.sha}\n先核对副本的文件和网页入口，之后只在这个目录按我的下一条要求修改；原项目保持原样。\n后续留稿沿用这个副本目录。打开倒带只打开工作台，不额外保存。\n需要运行时复用本轮已确认的命令；缺少配置时先给出运行计划。`,
  `Continue working on this recovered webpage with Reprise.\nWorking folder (full path): ${path}\nRecovered version: ${r.sha}\nCheck this copy’s files and webpage entry, then apply my next request only in this folder. Keep the original project unchanged.\nUse this copy’s folder for future draft saves. Opening Reprise only opens the workbench; it does not save a draft.\nReuse commands already approved in this task. If configuration is missing, present the run plan first.`);
}
function recoveryResult(job,options={}){
 if(!job)return;
 const r=job.result,ok=job.status==='complete'&&r,parent=Object.hasOwn(options,'parent')?options.parent:state.recoveryParents?.get(job.id)||captureDialogContext();
 state.recoveryParents?.delete(job.id);
 state.recoveryResultJob=job;
 const sha=r?.sha||job.request?.sha,c=commit(sha)||{sha,subject:short(sha)},paths=r?.paths||job.request?.paths;
 const continuation=recoveryContinuationText(job);
 dialogShell(ok?contentText('文件已取回','Files retrieved'):uiText('恢复 / 导出未完成'),`${previewLanguageControls()}<dl class="recovery-summary"><dt>${contentText('版本','Version')}</dt><dd data-user-content>${esc(versionTitle(c))} · <code>${short(sha)}</code></dd><dt>${contentText('恢复范围','Scope')}</dt><dd data-user-content>${paths?paths.map(esc).join('<br>'):contentText('此版本的全部文件','All files in this version')}</dd></dl>${ok?`<p role="status">${r.report?.readback_verified?contentText('恢复文件已逐字节读回核对。','Recovered files were read back and checked byte for byte.'):contentText('指定版本的文件对象散列已校验。','File object hashes for the specified version were verified.')}</p><p class="project-path" data-user-content>${esc(r.path)}</p><div class="recovery-location"><button class="secondary-button" data-action="reveal-recovery">${contentText('打开所在位置','Show in folder')}</button><button class="text-button" data-action="copy-recovery-path">${contentText('复制位置','Copy location')}</button></div>${continuation?`<p>${contentText('把继续修改指令粘贴给正在做网页的 Agent，让它改这份副本。','Paste the continuation instructions into your agent so it edits this copy.')}</p><details><summary>${contentText('查看继续修改指令','Read continuation instructions')}</summary><textarea id="recovery-continuation" class="continuation-text" readonly aria-label="${contentText('继续修改指令','Continuation instructions')}" data-user-content>${esc(continuation)}</textarea></details>`:''}${r.report?.warnings?.length?`<ul data-user-content>${r.report.warnings.map(w=>`<li>${esc(typeof w==='string'?w:JSON.stringify(w))}</li>`).join('')}</ul>`:''}<details><summary>${contentText('完整校验回执','Full verification receipt')}</summary><pre class="content-text" data-user-content>${esc(JSON.stringify(r.report,null,2))}</pre></details>`:`<p role="alert" data-user-content>${esc(job.error||uiText(job.status))}</p><p>${uiText('已有输出和诊断记录保留，可选择另一个新目录重试。')}</p>`}`,`<button class="secondary-button" data-action="close">${parent?contentText('返回上一页','Back'):uiText('返回版本')}</button>${!ok?`<button class="primary-button" data-action="retry-recovery">${contentText('选择新位置重试','Retry in a new location')}</button>`:''}${continuation?`<button class="primary-button" data-action="copy-recovery-continuation">${contentText('复制给 Agent 继续修改','Copy instructions to continue')}</button>`:''}${ok&&r.download_url?`<a class="primary-button" href="${esc(r.download_url)}" download>${uiText('下载 ZIP')}</a>`:''}`,false,parent);
 $('#dialog').dataset.recoveryResult='true';
}

const workspaceActions={
 'copy-recovery-continuation':async()=>{
  const text=recoveryContinuationText(state.recoveryResultJob);if(!text)return;
  try{await navigator.clipboard.writeText(text);notify(contentText('指令已复制，粘贴给正在做网页的 Agent 即可。','Instructions copied. Paste them into the agent working on your webpage.'));}
  catch{const field=$('#recovery-continuation');if(field){field.closest('details').open=true;field.focus();field.select();}notify(contentText('浏览器未允许复制，已展开指令，可手动复制。','Clipboard access was unavailable. The instructions are expanded for manual copying.'));}
 },
 recovery:()=>recoveryDialog(),
 'retry-recovery':()=>{const j=state.recoveryResultJob;recoveryDialog(j.request?.paths,{project:j.project_id,sha:j.request?.sha},{parent:dialogParent});},
 'save-restore':()=>startRecovery('restore'),
 'save-export':()=>startRecovery('export'),
 'recovery-result':b=>recoveryResult(state.jobs.find(j=>j.id===b.dataset.job)),
 'inline-preview':b=>{
  const runtime=state.runtimes.find(r=>r.id===b.dataset.runtime&&r.project_id===revisionProject()&&r.sha===state.selected&&runtimeInfo(r).running);
  if(!runtime)return;
  const url=new URL(runtime.url);if(url.protocol!=='http:'||!['127.0.0.1','localhost'].includes(url.hostname))return;
  const frame=document.createElement('iframe');frame.className='live-preview-frame';frame.title=uiText('版本预览');frame.sandbox='allow-scripts allow-forms allow-same-origin allow-downloads';frame.src=url.href;
  b.closest('.runtime-row').after(frame);b.disabled=true;
 }
};
