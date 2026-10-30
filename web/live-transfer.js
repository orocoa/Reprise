'use strict';
// Directory changes keep project identity; data copies never replace a live library.
function transferReturn(){return state.project?settings():projectPicker();}
async function transferDialog(project=state.project?.id){
 const parent=captureDialogContext(true);
 dialogShell(contentText('项目目录','Project location'),`<p role="status">${contentText('读取登记…','Reading registration…')}</p>`,'',false,parent);
 $('#dialog').classList.add('content-dialog');
 const request=state.dialogRequest,data=await api('/api/transfer');
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 state.transferProject=project;
 state.transferPrefix=data.backup_command_prefix;
 const available=data.projects.filter(p=>p.kind!=='archive');
 $('#dialog .dialog-body').innerHTML=`<section class="transfer-section"><h3>${contentText('项目目录','Project location')}</h3>${available.length?`<label class="field">${contentText('选择项目','Project')}<select id="transfer-project">${available.map(p=>`<option value="${esc(p.id)}" ${p.id===project?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><label class="field">${contentText('新的项目目录','New project location')}<input id="transfer-project-path" autocomplete="off" placeholder="/new/project/path"></label><p>${contentText('关联已有目录会先核对真实内容或 Git 历史。复制迁移要求新路径，并保留原目录、项目标识和版本。旧归档继续按原名称恢复。','Relinking an existing folder checks its contents or Git history. Copying requires a new path and retains the original folder, project ID and versions. Legacy archives keep their original recovery workflow.')}</p><div class="transfer-actions"><button class="secondary-button" data-action="transfer-inspect">${contentText('检查已有位置','Inspect existing location')}</button><button class="secondary-button" data-action="transfer-migrate">${contentText('复制到新位置并关联','Copy to new location and link')}</button></div>`:`<p>${contentText('尚无可以迁移的普通文件夹或 Git 项目。','No folder or Git project is available for relocation.')}</p>`}</section>`;
 $('#dialog .dialog-footer').innerHTML=`<span id="dialog-status" role="status"></span><button class="secondary-button" data-action="close">${contentText('返回','Back')}</button>`;

}
function updateBackupCommand(){
 const target=$('#transfer-backup-command');if(!target)return;
 const quote=value=>"'"+String(value).replace(/'/g,"'\\''")+"'";
 const prefix=state.transferPrefix,output=$('#transfer-backup-to').value.trim()||'/new/backup/path';
 target.textContent=[prefix.slice(0,-1).concat('shutdown'),prefix.concat('--to',output)].map(parts=>parts.map(quote).join(' ')).join('\n');
}
async function startTransfer(operation,project=null,path=null){
 const request=state.dialogRequest;
 let endpoint,body;
 if(['relink-check','relink','migrate'].includes(operation)){
  project=project||$('#transfer-project')?.value;
  path=path||$('#transfer-project-path')?.value.trim();
  if(!project||!path)throw Error(contentText('请选择项目并填写新位置。','Select a project and enter its new location.'));
  endpoint=`/api/projects/${project}/${operation}`;body={to:path};
 }else{
  const backup=$('#transfer-backup-path').value.trim();
  const to=$('#transfer-data-to').value.trim();
  if(!backup||(operation==='data-restore'&&!to))throw Error(contentText('请填写备份目录和需要的新数据目录。','Enter the backup directory and, for restore, a new data directory.'));
  endpoint='/api/'+operation;body={backup,to};
 }
 const job=await api(endpoint,{method:'POST',body:JSON.stringify(body)});
 mergeWorkspaceJobs([job]);
 if(request===state.dialogRequest&&$('#dialog').open){
  dialogShell(transferLabel(operation),`<p role="status" data-transfer-job="${esc(job.id)}">${contentText('正在核对并读回内容。原目录和已有版本保留。','Checking and reading back content. Original folders and saved versions are retained.')}</p>`,`<span></span><button class="secondary-button" data-action="transfer-return">${contentText('返回','Back')}</button><button class="secondary-button" data-action="cancel-job" data-job="${esc(job.id)}">${uiText('取消任务')}</button>`);
  $('#dialog').classList.add('content-dialog');
 }
 pollWorkspaceJob(job.id);
}
async function transferFinished(job){
 if(job.status==='complete'&&['relink','migrate'].includes(job.operation)&&state.project?.id===job.project_id)await loadProject(job.project_id,{preserve:true});
 await refreshWorkspace();
 if($('#dialog [data-transfer-job]')?.dataset.transferJob===job.id)transferResult(job);
 else notify(job.status==='complete'?contentText('目录操作完成，可在设置查看回执。','Directory operation complete. View the receipt in Settings.'):job.error||uiText('已取消'));
}
function transferResult(job){
 const ok=job.status==='complete',r=job.result||{},inspection=job.operation==='relink-check';
 const target=r.target||r.destination||r.directory||job.request?.to;
 const summary=ok?(inspection?contentText('候选位置身份核对通过，登记尚未改变。','The candidate location passed identity checks. Registration has not changed.'):contentText('操作完成，原目录和已有版本保留。','Operation complete. Original folders and saved versions are retained.')):job.error||uiText('已取消');
 const body=`<p role="${ok?'status':'alert'}" data-user-content>${esc(summary)}</p>${target?`<p class="project-path" data-user-content>${esc(target)}</p>`:''}${['backup-check','data-restore'].includes(job.operation)?`<p>${contentText('检查范围是备份内的 Reprise 已管理数据；外部源与旧归档仍以回执中的缺失条件为准。恢复到新库不会执行旧工程或重用原进程身份。','The check covers Reprise-managed data in this backup. External sources and legacy archives remain subject to the receipt’s exclusions. Restoring a new library does not execute projects or reuse original process identities.')}</p>`:''}<details><summary>${contentText('查看回执摘要','Receipt summary')}</summary><pre class="content-text" data-user-content>${esc(JSON.stringify(r,null,2))}</pre></details>`;
 dialogShell(transferLabel(job.operation),body,`<button class="secondary-button" data-action="transfer-return">${contentText('返回','Back')}</button>${ok&&inspection?`<button class="primary-button" data-action="transfer-relink-confirm" data-project="${esc(job.project_id)}" data-path="${esc(job.request.to)}">${contentText('确认关联这个位置','Link this location')}</button>`:''}`);
 $('#dialog').classList.add('content-dialog');
}
Object.assign(workspaceActions,{
 'content-transfer':()=>transferDialog(),
 'transfer-from-picker':()=>transferDialog($('#transfer-picker-project').value),
 'transfer-return':transferReturn,
 'transfer-inspect':()=>startTransfer('relink-check'),
 'transfer-migrate':()=>startTransfer('migrate'),
 'transfer-relink-confirm':b=>startTransfer('relink',b.dataset.project,b.dataset.path),
 'transfer-backup-check':()=>startTransfer('backup-check'),
 'transfer-data-restore':()=>startTransfer('data-restore'),
 'transfer-result':b=>{const job=state.jobs.find(j=>j.id===b.dataset.job);if(job)transferResult(job);}
});
document.addEventListener('input',event=>{if(event.target.id==='transfer-backup-to')updateBackupCommand();});

async function backupFileAction(importing=false){
 const parent=captureDialogContext(true);
 const title=contentText(importing?'导入备份':'备份',importing?'Import backup':'Backup');
 dialogShell(title,`<p role="status">${contentText(importing?'请选择 Reprise 导出的备份文件。':'请选择备份文件的保存位置。',importing?'Choose the backup file exported by Reprise.':'Choose where to save your backup file.')}</p>`,'',false,parent);
 const request=state.dialogRequest;
 try{
  const choice=typeof window.RepriseDesktop?.chooseBackup==='function'?await window.RepriseDesktop.chooseBackup(!importing):await api('/api/desktop/'+(importing?'open-backup':'save-backup'),{method:'POST',body:'{}'});
  if(choice.status==='cancelled'){if(request===state.dialogRequest)closeDialog();return;}
  if(choice.status!=='selected')throw Error(contentText('无法打开系统文件选择器，请在本机桌面重试。','The system file picker is unavailable. Retry on the local desktop.'));
  if(request!==state.dialogRequest)return;
  $('#dialog .dialog-body').innerHTML=`<p role="status">${contentText(importing?'正在校验并导入备份…':'正在导出并校验备份文件…',importing?'Verifying and importing backup…':'Exporting and verifying backup…')}</p><p class="snapshot-message">${contentText('请等待完成，当前资料保留。','Wait for completion. Your current library is retained.')}</p>`;
  const result=await api(importing?'/api/backup-import':'/api/backup-file',{method:'POST',body:JSON.stringify(importing?{path:choice.path}:{to:choice.path})});
  if(request!==state.dialogRequest){notify(contentText('备份操作已完成。','Backup operation complete.'));return;}
  if(importing)state.importedBackup=result;
  $('#dialog .dialog-body').innerHTML=`<p role="status">${contentText(importing?'备份已导入，校验通过。':'备份文件已导出，校验通过。',importing?'Backup imported and verified.':'Backup file exported and verified.')}</p><p class="project-path" data-user-content>${esc(importing?choice.path:result.path)}</p><p class="snapshot-message">${contentText(importing?'导入为一个新库，当前库继续保留。':'包含 Reprise 管理的数据；原项目文件夹和外部 Git 另行保管。',importing?'Imported as a new library. Your current library remains available.':'Contains Reprise-managed data. Keep original project folders and external Git repositories separately.')}</p>`;
  $('#dialog .dialog-footer').innerHTML=`<span id="dialog-status" role="status"></span><button class="secondary-button" data-action="close">${uiText('返回')}</button>${importing?`<button class="primary-button" data-action="backup-open">${contentText('打开导入的备份','Open imported backup')}</button>`:''}`;
 }catch(error){if(request===state.dialogRequest){$('#dialog .dialog-body').innerHTML=`<p role="alert" data-user-content>${esc(error.message)}</p>`;$('#dialog .dialog-footer').innerHTML=`<button class="secondary-button" data-action="close">${uiText('返回')}</button>`;}else notify(error.message);}
}
Object.assign(workspaceActions,{
 'backup-export':()=>backupFileAction(false),
 'backup-import':()=>backupFileAction(true),
 'backup-open':async()=>{
  const native=!!window.RepriseDesktop;
  const result=await api('/api/backup-open',{method:'POST',body:JSON.stringify({id:state.importedBackup?.id,window:native})});
  if(!native)location.href=result.url;
  else closeDialog();
 }
});
