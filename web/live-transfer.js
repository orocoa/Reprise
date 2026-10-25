'use strict';
// Directory changes keep project identity; data copies never replace a live library.
function transferReturn(){return state.project?settings():projectPicker();}
async function transferDialog(project=state.project?.id){
 const parent=captureDialogContext(true);
 dialogShell(contentText('备份与目录迁移','Backups and directory relocation'),`<p role="status">${contentText('读取登记…','Reading registration…')}</p>`,'',false,parent);
 $('#dialog').classList.add('content-dialog');
 const request=state.dialogRequest,data=await api('/api/transfer');
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 state.transferProject=project;
 state.transferPrefix=data.backup_command_prefix;
 const available=data.projects.filter(p=>p.kind!=='archive');
 $('#dialog .dialog-body').innerHTML=`<section class="transfer-section"><h3>${contentText('带到另一台电脑','Take your library to another computer')}</h3><ol><li>${contentText('在这台电脑停止 Reprise 后，创建并校验下方的独立备份。','Stop Reprise on this computer, then create and verify the independent backup below.')}</li><li>${contentText('把整个备份目录复制到另一台电脑，保留 payload、manifest.jsonl 和 receipt.json 的结构。无需逐版导出。','Copy the entire backup folder to the other computer, keeping payload, manifest.jsonl and receipt.json together. No per-version export is needed.')}</li><li>${contentText('用另一台电脑的 Reprise 检查备份，恢复到一个新数据目录，再打开该库。不会合并或覆盖已有库。','Use Reprise on the other computer to check the backup, restore into a new data directory, then open that library. Existing libraries are not merged or overwritten.')}</li></ol><p class="snapshot-message">${contentText('已保存文件夹版本不依赖原电脑路径。外部 Git 原仓库、未保存的修改及外部归档不自动装入；回执会列明。自动截图恢复为提醒，需要在新电脑重新确认配置。当前是目录格式，不是单文件安装包。','Saved folder versions do not require the original computer path. External Git sources, unsaved changes and external archives are not automatically included; check the receipt. Automatic screenshots revert to reminders and need confirmation on the new computer. This is a folder format, not a single-file installer.')}</p></section><section class="transfer-section"><h3>${contentText('项目目录','Project location')}</h3>${available.length?`<label class="field">${contentText('选择项目','Project')}<select id="transfer-project">${available.map(p=>`<option value="${esc(p.id)}" ${p.id===project?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><label class="field">${contentText('新的项目目录','New project location')}<input id="transfer-project-path" autocomplete="off" placeholder="/new/project/path"></label><p>${contentText('关联已有目录会先核对真实内容或 Git 历史。复制迁移要求新路径，并保留原目录、项目标识和版本。旧归档继续按原名称恢复。','Relinking an existing folder checks its contents or Git history. Copying requires a new path and retains the original folder, project ID and versions. Legacy archives keep their original recovery workflow.')}</p><div class="transfer-actions"><button class="secondary-button" data-action="transfer-inspect">${contentText('检查已有位置','Inspect existing location')}</button><button class="secondary-button" data-action="transfer-migrate">${contentText('复制到新位置并关联','Copy to new location and link')}</button></div>`:`<p>${contentText('尚无可以迁移的普通文件夹或 Git 项目。','No folder or Git project is available for relocation.')}</p>`}</section><section class="transfer-section"><h3>${contentText('独立备份','Independent backup')}</h3><p data-user-content class="project-path">${esc(data.data_directory)}</p><p>${contentText('先停止此数据目录的 Reprise 服务和任务，再执行下方本机命令。备份包含 Reprise 已管理数据，外部源 Git、未保存的文件和外部旧归档单独列为未纳入。备份未加密，可能包含保存的密钥。','Stop the Reprise service and tasks for this data directory before running these local commands. The backup includes Reprise-managed data; external Git sources, unsaved files and external legacy archives are reported separately as excluded. It is unencrypted and may include saved keys.')}</p><label class="field">${contentText('新的备份目录','New backup directory')}<input id="transfer-backup-to" autocomplete="off" placeholder="/new/backup/path"></label><pre id="transfer-backup-command" class="content-text transfer-command" data-user-content></pre><p>${contentText('同一磁盘的副本不能防护该磁盘故障。原库和失败产物均保留，不会自动切换默认数据目录。','A copy on the same disk does not protect against failure of that disk. The original library and partial outputs are retained; the default data location is not changed automatically.')}</p></section><section class="transfer-section"><h3>${contentText('检查备份与恢复到新库','Verify a backup or restore a new library')}</h3><label class="field">${contentText('已完成的备份目录','Completed backup directory')}<input id="transfer-backup-path" autocomplete="off" placeholder="/path/to/backup"></label><label class="field">${contentText('新的数据目录（恢复时填写）','New data directory (for restore)')}<input id="transfer-data-to" autocomplete="off" placeholder="/new/reprise-data"></label><div class="transfer-actions"><button class="secondary-button" data-action="transfer-backup-check">${contentText('读回检查备份','Read back backup')}</button><button class="secondary-button" data-action="transfer-data-restore">${contentText('恢复到新数据目录','Restore a new data directory')}</button></div></section>`;
 $('#dialog .dialog-footer').innerHTML=`<span id="dialog-status" role="status"></span><button class="secondary-button" data-action="close">${contentText('返回','Back')}</button>`;
 updateBackupCommand();
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
