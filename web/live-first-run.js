'use strict';
// The first task is choosing one working folder, then explicitly saving a draft.
function renderFirstRun(){
 $('#project-name').textContent='Reprise';
 document.title=contentText('Reprise · 网页稿件','Reprise · Website drafts');
 $('#source-status').textContent=contentText('稿件保存在这台电脑上','Drafts stay on this computer');
 $('#detail').innerHTML=`<section class="first-run"><p class="first-run-kicker">Reprise</p><h1>${contentText('改下一轮之前，留一稿。','Save a draft before the next edit.')}</h1><p class="first-run-description">${contentText('选择电脑里的网页文件夹，从当前这一稿开始保存文件和画面。以后按画面找回已保存的稿件。','Choose your local website folder and start saving its files and appearance from this draft onward. Later, find a saved draft by its picture.')}</p><ol class="first-run-steps"><li>${contentText('选择网页文件夹','Choose your website folder')}</li><li>${contentText('保存文件和画面','Save files and picture')}</li><li>${contentText('按画面找回旧稿','Find an earlier draft by its picture')}</li></ol><button class="primary-button" data-action="start-website-folder">${contentText('选择网页文件夹…','Choose website folder…')}</button><p class="snapshot-message">${contentText('原文件夹保持原样，继续用你习惯的方式修改。','Your original folder stays in place. Keep editing with your usual tools.')}</p></section>`;
}

function websitePickerCurrent(request){
 return request===state.dialogRequest&&$('#dialog').open&&!!$('#dialog [data-project-picker]');
}

async function addWebsiteFolder(path,request){
 if(!websitePickerCurrent(request)||state.websiteFolderAdding)return;
 state.websiteFolderAdding=true;
 try{
  const project=await api('/api/projects',{method:'POST',body:JSON.stringify({path,kind:'folder'})});
  if(!websitePickerCurrent(request))return;
  closeDialog();
  const closedRequest=state.dialogRequest;
  await loadProject(project.id);
  if(state.project?.id===project.id&&state.dialogRequest===closedRequest&&!$('#dialog').open&&project.kind==='folder'&&!state.commits.length)snapshotDialog();
 }catch(error){if(websitePickerCurrent(request))throw error;}
 finally{state.websiteFolderAdding=false;}
}

async function chooseWebsiteFolder(button){
 const request=state.dialogRequest;
 if(!websitePickerCurrent(request)||state.websiteFolderChoosing)return;
 state.websiteFolderChoosing=true;button.disabled=true;
 try{
  const bridge=window.RepriseDesktop;
  const result=typeof bridge?.chooseFolder==='function'?await bridge.chooseFolder():await api('/api/desktop/choose-folder',{method:'POST',body:'{}'});
  if(!websitePickerCurrent(request))return;
  if(result?.status==='selected'&&typeof result.path==='string'&&result.path){
   await addWebsiteFolder(result.path,request);
  }else if(result?.status!=='cancelled'){
   $('#manual-folder-path').open=true;
   $('#dialog-status').textContent=result?.reason||contentText('未能选择文件夹。可以重试，或粘贴文件夹路径。','The folder could not be selected. Retry or paste its path.');
  }
 }catch(error){if(websitePickerCurrent(request))throw error;}
 finally{state.websiteFolderChoosing=false;if(button.isConnected)button.disabled=false;}
}

function confirmStopWorkbench(){
 const parent=captureDialogContext(true);
 dialogShell(contentText('停止 Reprise','Stop Reprise'),`<p>${contentText('停止本机服务和网页预览。正在进行的可取消任务会停止；已保存的稿件、原文件与日志继续保留。','Stop the local service and website previews. Cancellable tasks in progress will stop; saved drafts, original files, and logs remain.')}</p><p>${contentText('以后重新打开 Reprise 即可继续。','Open Reprise again when you want to continue.')}</p>`,`<button class="secondary-button" data-action="close">${contentText('返回','Back')}</button><button class="primary-button" data-action="stop-workbench">${contentText('停止 Reprise','Stop Reprise')}</button>`,false,parent);
}

Object.assign(workspaceActions,{
 'start-website-folder':async()=>{
  const opening=projectPicker(),request=state.dialogRequest;
  await opening;
  if(!websitePickerCurrent(request))return;
  const button=$('#dialog [data-action="choose-website-folder"]');
  if(button&&!button.disabled)await chooseWebsiteFolder(button);
 },
 'choose-website-folder':chooseWebsiteFolder,
 'confirm-stop-workbench':confirmStopWorkbench,
 'stop-workbench':async button=>{
  button.disabled=true;
  try{
   const result=await api('/api/shutdown',{method:'POST',body:'{}'});
   if(!result.stopped)throw Error(contentText('服务未确认停止，请重试。','Service shutdown was not confirmed. Retry.'));
   dialogShell(contentText('Reprise 已停止','Reprise stopped'),`<p>${contentText('可以关闭这个窗口。已保存的稿件仍在，下次打开 Reprise 继续。','You can close this window. Your saved drafts remain available next time you open Reprise.')}</p>`,`<button class="secondary-button" data-action="close">${contentText('关闭提示','Dismiss')}</button>`);
  }finally{if(button.isConnected)button.disabled=false;}
 },
 language:button=>{
  const firstRun=!!$('#detail .first-run');
  changeLanguage(button.dataset.language);
  if(firstRun&&!state.project)renderFirstRun();
 }
});
Object.assign(uiCopy,{'停止 Reprise':'Stop Reprise','正在打开网页稿件…':'Opening website drafts…'});
