'use strict';
Object.assign(uiCopy,{
 '恢复 / 导出':'Recover / Export','恢复 / 导出版本':'Recover / export revision','恢复 / 导出完成':'Recovery / export complete',
 '恢复 / 导出未完成':'Recovery / export incomplete','新的恢复目录':'New recovery folder',
 '填写尚不存在的目录完整路径':'Enter the full path to a new folder','恢复到新目录':'Recover into a new folder',
 '下载 ZIP':'Download ZIP','返回版本':'Back to revision','查看结果':'View result','恢复版本':'Recover revision','导出 ZIP':'Export ZIP',
 '高级配置 JSON':'Advanced recipe JSON','嵌入预览':'Embed preview',
 '恢复到新目录，或下载此提交的文件 ZIP。文件从 Git 对象读取并校验，原工作区及未提交改动保持不变。':'Recover into a new folder or download this commit as ZIP. Files are read and verified from Git objects; the source worktree and uncommitted changes are preserved.',
 '结果是此提交的文件快照，不含 Git 历史。子模块和 LFS 指针会在结果中说明。':'The result is a file snapshot without Git history. Submodules and LFS pointers are reported.',
 '文件对象已校验。':'File objects verified.','文件已保存到新目录。':'Files saved in the new folder.',
 'ZIP 已生成，可以下载。':'ZIP is ready to download.','正在从 Git 对象生成文件…':'Reading files from Git objects…',
 '可以返回版本，稍后在项目设置查看任务结果。':'You can return to the revision and review the job in project settings.',
 '已有输出和诊断记录保留，可选择另一个新目录重试。':'Existing output and diagnostics are retained. Retry with another new folder.',
 '请填写新的恢复目录。':'Enter a new recovery folder.','恢复 / 导出已完成，可在设置中查看结果。':'Recovery / export complete. View the result in Settings.'
});
// Recovery and previews share the same local API as the portable CLI.
function recoveryDialog(){
 state.recoveryTarget={project:revisionProject(),sha:state.selected};
 dialogShell('恢复 / 导出版本',`<p data-user-content>${esc(versionTitle(commit(state.selected)))}</p><p class="identity-sha">${esc(state.selected)}</p><p>恢复到新目录，或下载此提交的文件 ZIP。文件从 Git 对象读取并校验，原工作区及未提交改动保持不变。</p><label class="field">新的恢复目录<input id="restore-path" autocomplete="off" placeholder="填写尚不存在的目录完整路径"></label><p class="snapshot-message">结果是此提交的文件快照，不含 Git 历史。子模块和 LFS 指针会在结果中说明。</p>`, '<button class="secondary-button" data-action="close">返回版本</button><button class="secondary-button" data-action="save-export">下载 ZIP</button><button class="primary-button" data-action="save-restore">恢复到新目录</button>');
 $('#restore-path').focus();
}
async function startRecovery(operation){
 const target=state.recoveryTarget;
 if(!target||target.project!==revisionProject()||target.sha!==state.selected)throw Error('编辑对象已经变化，请重新打开。');
 const to=operation==='restore'?$('#restore-path').value.trim():null;
 if(operation==='restore'&&!to)throw Error('请填写新的恢复目录。');
 const job=await api(`/api/projects/${target.project}/${operation}`,{method:'POST',body:JSON.stringify({sha:target.sha,to})});
 mergeWorkspaceJobs([job]);
 dialogShell('恢复 / 导出版本',`<p data-recovery-job="${esc(job.id)}" role="status">正在从 Git 对象生成文件…</p><p>可以返回版本，稍后在项目设置查看任务结果。</p>`,'<button class="secondary-button" data-action="close">返回版本</button><button class="secondary-button" data-action="cancel-job" data-job="'+esc(job.id)+'">取消任务</button>');
 pollWorkspaceJob(job.id);
}
function recoveryResult(job){
 const r=job.result,ok=job.status==='complete';
 dialogShell(ok?'恢复 / 导出完成':'恢复 / 导出未完成',`<p class="identity-sha">${esc(job.request?.sha)}</p>${ok?`<p>文件对象已校验。${r.operation==='restore'?'文件已保存到新目录。':'ZIP 已生成，可以下载。'}</p><p class="project-path" data-user-content>${esc(r.path)}</p>${r.report?.warnings?.length?`<ul data-user-content>${r.report.warnings.map(w=>`<li>${esc(typeof w==='string'?w:JSON.stringify(w))}</li>`).join('')}</ul>`:''}`:`<p role="alert" data-user-content>${esc(job.error||job.status)}</p><p>已有输出和诊断记录保留，可选择另一个新目录重试。</p>`}`,
 `<button class="secondary-button" data-action="close">返回</button>${ok&&r.download_url?`<a class="primary-button" href="${esc(r.download_url)}" download>下载 ZIP</a>`:''}`);
}
const workspaceActions={
 recovery:recoveryDialog,
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
