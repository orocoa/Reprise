'use strict';
// Ordinary folders share the existing version, comparison and recovery workspace.

function contentText(zh,en){return uiLanguage==='en'?en:zh;}
const draftSaveRequests=new Set();
function defaultDraftTitle(){return contentText('留稿 · ','Draft · ')+new Intl.DateTimeFormat(uiLanguage==='en'?'en-GB':'zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date());}
function draftSaveBusy(project=state.project?.id){return draftSaveRequests.has(project)||(state.jobs||[]).some(j=>j.project_id===project&&j.operation==='snapshot'&&['queued','running'].includes(j.status));}
function saveDraftFromToolbar(){
 if(state.project?.kind!=='folder'||draftSaveBusy())return;
 // A saved project preference supplies the future capture scope. First use
 // still explains that scope before any webpage is started.
 if(state.commits.length&&['auto','none','manual'].includes(state.project.preview_preferences?.mode))return saveCurrentDraft(defaultDraftTitle());
 snapshotDialog();
}
async function saveCurrentDraft(title,{fromDialog=false}={}){
 const project=state.project?.id,request=state.dialogRequest;
 if(state.project?.kind!=='folder'||draftSaveBusy(project))return;
 if(fromDialog&&state.snapshotTarget!==project)throw Error(contentText('项目已经变化。','The project has changed.'));
 const initialChoice=fromDialog?$('#initial-preview-choice')?.value:null;
 if(!state.project.preview_preferences?.mode&&!['auto','none'].includes(initialChoice))throw Error(contentText('请先选择这个项目是否需要保存画面。','Choose whether this project should save images first.'));
 const initialPreference=initialChoice?{mode:initialChoice,...(initialChoice==='auto'?{pending_recipe:true}:{})}:null;
 draftSaveRequests.add(project);refreshDraftSaveControl();
 try{
  const job=await api(`/api/projects/${project}/snapshot`,{method:'POST',body:JSON.stringify({title:title.trim()||defaultDraftTitle(),capture_static:initialPreference?false:!['none','manual','auto'].includes(state.project.preview_preferences?.mode),...(initialPreference?{preview_preferences:initialPreference}:{})})});
  mergeWorkspaceJobs([job]);
  if(fromDialog&&request===state.dialogRequest&&state.project?.id===project&&$('#dialog').open)dialogShell(contentText('正在保存这一稿','Saving this draft'),`<p data-folder-job="${esc(job.id)}" role="status">${contentText('正在保存文件，并按项目偏好准备画面。','Saving files and preparing the image with this project’s preference.')}</p><p>${contentText('画面未完成时，已保存文件仍然保留。','Saved files remain available if the image is incomplete.')}</p>`,`<button class="secondary-button" data-action="close">${uiText('返回版本')}</button><button class="secondary-button" data-action="cancel-job" data-job="${esc(job.id)}">${uiText('取消任务')}</button>`);
  else notify(contentText('正在留稿，可继续查看其他版本。','Saving a draft. You can keep browsing.'));
  pollWorkspaceJob(job.id);
 }finally{draftSaveRequests.delete(project);refreshDraftSaveControl();}
}
function refreshDraftSaveControl(){
 const button=$('#content-save');if(!button)return;
 button.disabled=draftSaveBusy();
 button.title=contentText('保存一稿：Ctrl / ⌘ + S；命名保存：Ctrl / ⌘ + Shift + S','Save a draft: Ctrl / ⌘ + S; name a draft: Ctrl / ⌘ + Shift + S');
}
function rememberCaptureControl(d){
 const sha=d.commit?.sha,preference=state.project?.preview_preferences,mode=preference?.mode;
 const automaticReady=mode==='auto'&&!!preference.recipe&&!preference.pending_recipe;
 if(state.project?.kind!=='folder'||sha!==state.selected||automaticReady||['none','manual'].includes(mode)||!d.recipe_approved||!['static-web','command-web'].includes(d.recipe?.adapter))return '';
 const captured=(d.evidence||[]).some(record=>record.sha===sha&&record.status==='complete'&&!record.errors?.length&&record.source!=='manual'&&(record.items||[]).some(item=>!['base','before'].includes(item.side)&&(!item.sha||item.sha===sha)&&!item.missing&&!item.error&&item.url&&item.media_type?.startsWith('image/')));
 return captured?`<div class="draft-preference-hint"><p>${contentText('这一稿的画面已保存。记住配置后，下次点击「保存一稿」即可直接留稿。','This draft’s image is saved. Remember these settings to save your next draft in one click.')}</p><button class="secondary-button" data-action="remember-draft-preview" data-sha="${esc(sha)}">${contentText('记住画面设置…','Remember image settings…')}</button></div>`:'';
}
function contentBytes(bytes){return new Intl.NumberFormat(uiLanguage==='en'?'en-US':'zh-CN',{maximumFractionDigits:1}).format(bytes/((bytes>=1073741824)?1073741824:bytes>=1048576?1048576:bytes>=1024?1024:1))+' '+(bytes>=1073741824?'GiB':bytes>=1048576?'MiB':bytes>=1024?'KiB':'B');}
function refreshContentStatus(){
 refreshDraftSaveControl();
 const target=$('#source-status'),kind=state.project?.kind;
 if(!['folder','archive'].includes(kind)){target.removeAttribute('data-user-content');return;}
 // Render complete localized sentences; substring translation corrupts counts
 // when switching languages on a folder workspace already in view.
 target.setAttribute('data-user-content','');
 const count=state.historySources.find(s=>s.kind==='current')?.count||state.commits.length;
 const changes=state.status?.changes?.length||0;
 target.textContent=kind==='archive'?contentText(`${count} 个归档快照`,`${count} archived snapshots`):
  contentText(`${count} 个已保存版本 · ${state.status?.available===false?'原文件夹不可用':changes+' 项变化'}`,
              `${count} saved versions · ${state.status?.available===false?'source unavailable':changes+' changed entries'}`);
}
// Presentation is a reversible project preference; detection never executes commands.
function visualPresentation(d){
 const mode=state.prefs.presentation||'auto';if(mode!=='auto')return mode==='visual';
 return !!d&&(mediaItems(d).some(visualEvidence)||['static-web','command-web'].includes(d.recipe?.adapter)||
  (d.detection?.candidates||[]).some(c=>['static-web','command-web'].includes(c.recipe?.adapter)));
}
function presentationFields(){return `<section class="settings-section"><label class="field">${contentText('版本内容的显示方式','Version presentation')}<select id="project-presentation">${[['auto','按已识别入口与素材','Use detected entry points and evidence'],['files','文件优先','Files first'],['visual','预览优先','Preview first']].map(([v,zh,en])=>`<option value="${v}" ${(state.prefs.presentation||'auto')===v?'selected':''}>${contentText(zh,en)}</option>`).join('')}</select></label><p class="snapshot-message">${contentText('只改变显示顺序，不运行项目；每个项目分别记住。','Changes display order without running the project; remembered per project.')}</p></section>`;}
function folderSummary(d){
 if(!d.content)return '';
 const s=d.content.stats;
 const origin=d.content.origin;
 const provenance=origin?`<p class="snapshot-message" data-user-content>${contentText('导入记录 · 顺序来自用户输入，并非原 Git 历史；显示时间是保存时间。','Imported record · user-specified order, not original Git ancestry; the displayed date is the save date.')} ${esc(origin.source)}</p>`:'';
 return `<section class="content-summary">${provenance}<p>${uiText('本机已保存 · 未同步云端')}</p><div class="content-metrics">${[[s.files,uiText('文件')],[contentBytes(s.logical_bytes),uiText('逻辑内容')],[contentBytes(s.unique_bytes),uiText('不同内容')],[contentBytes(s.new_bytes),uiText('本次新增')]].map(([value,label])=>`<span><strong>${esc(value)}</strong><small>${esc(label)}</small></span>`).join('')}</div><p>${uiText('相同内容共用存储，名称和目录分别保留。')}</p><p class="snapshot-message">${uiText('这些是内容字节统计，不是磁盘实际释放量。')}</p>${d.content.excluded.length?`<details><summary>${contentText('未纳入此版本','Excluded from this version')} · ${d.content.excluded.length}</summary><p data-user-content>${d.content.excluded.map(esc).join('<br>')}</p></details>`:''}<button class="text-button" data-action="content-duplicates">${uiText('查看重复内容')}</button></section>`;
}
function renderFolderChanges(d){
 if(d.diff.available===false)return `<section><h3>${contentText('此版本的完整内容仍保留','This version’s complete contents remain saved')}</h3><p class="snapshot-message">${contentText('用于比较的历史版本当前不可读取，不能据此判断文件是否变化。你仍可以查看或恢复此版本的完整内容。','The historical comparison baseline is unavailable, so changes cannot be determined. You can still inspect or restore this version’s complete contents.')}</p><button class="secondary-button" data-action="tab" data-tab="preview">${contentText('查看此版本内容','Inspect this version’s contents')}</button></section>`;
 const files=d.diff.files;
 return `<section><h3>${uiLanguage==='en'?'Changes in this version':'此版本的变化'}</h3><p class="snapshot-message">${esc(summary(d))}</p><div class="changed-files">${files.length?fileRows(files):`<p>${uiLanguage==='en'?'File contents are unchanged; directory or metadata changes are preserved.':'文件内容相同；目录或文件属性的变化已保留。'}</p>`}</div></section>`;
}
function projectPurposeLabel(project){
 if(project.kind==='folder')return contentText('网页留稿','Webpage drafts');
 if(project.kind==='archive')return contentText('历史存档 · 只读','History archive · read only');
 return contentText('Git 历史 · 只读','Git history · read only');
}
async function projectPicker(){
 dialogShell(contentText('选择网页文件夹','Choose a website folder'),`<p role="status">${contentText('读取项目…','Loading projects…')}</p>`);
 const request=state.dialogRequest;
 const [{projects},desktop]=await Promise.all([api('/api/projects?summary=1'),api('/api/desktop')]);
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 const native=typeof window.RepriseDesktop?.chooseFolder==='function'||desktop.supported;
 $('#dialog .dialog-body').innerHTML=`<section class="website-folder-picker" data-project-picker><p>${contentText('选你正在修改的网页文件夹。接着给它保存第一稿，以后继续在原文件夹修改。','Choose the website folder you are editing. Save its first draft, then keep editing the original folder.')}</p><button class="primary-button" data-action="choose-website-folder" ${native?'':'disabled'}>${contentText('选择网页文件夹…','Choose website folder…')}</button><p class="snapshot-message">${contentText('只加入你选择的文件夹，不会修改或移动原文件。','Only the folder you choose is added. Original files stay unchanged and in place.')}</p><details id="manual-folder-path" ${native?'':'open'}><summary>${contentText('或粘贴文件夹路径','Or paste a folder path')}</summary><label class="field">${contentText('网页文件夹路径','Website folder path')}<input id="content-import-path" autocomplete="off" placeholder="/path/to/website"></label><button class="secondary-button" data-action="save-content-project">${contentText('继续','Continue')}</button></details></section>${projects.length?`<section class="saved-website-projects"><h3>${contentText('打开已有项目','Open an existing project')}</h3><div class="content-projects">${projects.map(p=>`<button class="content-project" data-action="content-open" data-project="${esc(p.id)}"><strong data-user-content>${esc(p.name)}</strong><small>${projectPurposeLabel(p)}</small><small data-user-content>${esc(p.path)}</small>${p.unavailable?`<span>${esc(p.error)}</span>`:''}</button>`).join('')}</div></section>`:''}`;
}
function previewLanguageControls(){return `<div class="segmented language-switch" role="group" aria-label="${contentText('语言','Language')}"><button data-user-content data-action="language" data-language="zh" aria-pressed="${uiLanguage==='zh'}">中文</button><button data-user-content data-action="language" data-language="en" aria-pressed="${uiLanguage==='en'}">English</button></div>`;}
function previewPreferenceFields(mode=state.project?.preview_preferences?.mode||'remind'){
 const configured=!!state.project?.preview_preferences?.recipe||!!detail(state.selected)?.recipe_approved&&detail(state.selected)?.recipe?.adapter!=='manual';
 const stored=state.project?.preview_preferences,recipe=stored?.recipe||detail(state.selected)?.recipe;
 const source=stored?.source_sha||state.selected;
 const template=configured?`<details><summary data-user-content>${contentText('自动模式会复用的配置','Settings reused by automatic mode')} · ${esc(source?.slice(0,8)||'')}</summary><pre data-user-content class="content-text">${esc(JSON.stringify(recipe,null,2))}</pre></details>`:'';
 return `<section class="settings-section"><h3 data-user-content>${contentText('保存后需要截图吗？','Screenshots after saving?')}</h3><label class="field"><span data-user-content>${contentText('记住这个项目的选择，可随时更改','Remember for this project; change anytime')}</span><select id="preview-preference-mode">${[['none','无需截图','No screenshots needed'],['manual','我自己提供，不再提醒','I will attach my own; no reminders'],['remind','每次保存后提醒我','Remind me after each save'],['auto','每次留稿都保存画面','Save images with future drafts']].map(([v,zh,en])=>`<option data-user-content value="${v}" ${v===mode?'selected':''} >${contentText(zh,en)}</option>`).join('')}</select></label><p class="snapshot-message" data-user-content>${contentText('截图可选，不会截取桌面。自动模式会在独立副本中运行已确认的配置，并用于以后保存；失败不影响版本保存。','Screenshots are optional; the desktop is never captured. Automatic mode runs the approved settings in an independent copy after future saves. Capture failure does not undo the saved version.')}</p>${template}${!configured?`<p data-user-content>${contentText('先记住选择。可直接打开的网页会准备画面；需要运行命令时先确认配置，之后沿用，不再重复询问是否截图。','Your choice is remembered first. Directly viewable webpages can prepare an image; command-based projects need reviewed settings, then reuse them without asking about images again.')}</p>`:''}</section>`;
}
function previewPreferenceRequest(){
 const mode=$('#preview-preference-mode')?.value||state.project?.preview_preferences?.mode||'remind';
 const stored=state.project?.preview_preferences;
 if(mode!=='auto'||stored?.mode==='auto'&&stored.recipe&&!stored.pending_recipe)return {mode};
 return {mode,...(detail(state.selected)?.recipe_approved&&detail(state.selected)?.recipe?.adapter!=='manual'?{recipe_sha:state.selected}:{pending_recipe:true})};
}
function previewPreferenceSummary(){
 const preference=state.project?.preview_preferences;
 if(preference?.mode==='auto')return preference.recipe&&!preference.pending_recipe?
  contentText('已记住画面设置；后续留稿会一起保存画面。','Image settings remembered. Future saves include an image.'):
  contentText('已记住保存画面的选择；仍需确认运行与截图配置。','Your image choice is remembered; run and capture settings still need confirmation.');
 if(preference?.mode==='none')return contentText('已记住仅存文件的选择；后续直接留稿，按时间命名。','Files-only preference remembered. Future saves use a time-based name.');
 if(preference?.mode==='manual')return contentText('留稿时保存文件，画面由你提供。','Saves files; you provide the images.');
 if(preference?.mode==='remind')return contentText('留稿后提醒补画面，文件会先保存。','Reminds you to add an image after saving the files.');
 return contentText('首次留稿会询问是否保存画面，选择后持续沿用；可随时更改。','The first save asks whether to include images. Your choice is remembered and can be changed anytime.');
}
function previewPreferencesDialog(draft={}){
 state.previewPreferenceTarget=state.project.id;
 dialogShell(contentText('截图偏好','Screenshot preference'),previewLanguageControls()+previewPreferenceFields(draft.mode),`<button class="secondary-button" data-action="settings">${uiText('返回')}</button><button class="primary-button" data-action="save-preview-preferences">${contentText('保存偏好','Save preference')}</button>`);
 $('#dialog').dataset.previewPreferences='true';
}
function snapshotDialog(draft={}){
 if(state.project?.kind!=='folder')return;
 state.snapshotTarget=state.project.id;
 const mode=state.project.preview_preferences?.mode;
 const description=!mode?contentText('先保存文件；画面按上面的选择处理。','Files are saved first; the image follows your choice above.'):mode==='auto'?contentText(state.project.preview_preferences.pending_recipe?'截图选择已记住；保存文件后准备画面，配置缺失时给出下一步。':'保存文件，并按已确认的配置截图。',state.project.preview_preferences.pending_recipe?'Your image choice is remembered. Save files, then prepare the image or explain the missing settings.':'Saves the files and captures using your approved settings.'):['none','manual'].includes(mode)?contentText('按你的截图偏好，仅保存文件。','Saves files only, following your screenshot preference.'):contentText('保存文件；识别到可直接打开的网页时，在独立副本中保存画面。只允许本机网络，不执行安装或构建命令。','Saves the files and captures directly viewable webpages in an independent copy. Local network only; no install or build commands.');
 dialogShell(contentText('保存一稿','Save a draft'),previewLanguageControls()+`<label class="field">${contentText('稿件名称（可选）','Draft name (optional)')}<input id="content-version-title" maxlength="120" value="${esc(draft.title||'')}" placeholder="${contentText('例如：蓝色按钮，第二稿','For example: blue button, second draft')}"></label>${!mode?`<label class="field">${contentText('这个项目以后留稿时，需要一起保存画面吗？','Should future drafts of this project include an image?')}<select id="initial-preview-choice" required><option value="" ${!draft.initialPreviewMode?'selected':''}>${contentText('请选择一次，之后沿用','Choose once; remembered for this project')}</option><option value="auto" ${draft.initialPreviewMode==='auto'?'selected':''}>${contentText('是，留稿时一起保存画面','Yes, save an image with each draft')}</option><option value="none" ${draft.initialPreviewMode==='none'?'selected':''}>${contentText('否，只保存文件','No, save files only')}</option></select></label><p class="snapshot-message">${contentText('选择按项目记住。需要安装或运行网页时先确认配置，以后按这份已确认配置执行；可随时在设置中更改。','Remembered for this project. Review install/run settings when needed; future saves reuse those approved settings. Change your choice in settings anytime.')}</p>`:''}<p>${description}</p><p class="snapshot-message">${contentText('截图失败也会保留文件。保存后继续修改原文件夹即可。','Files remain saved even if capture fails. Continue editing your original folder afterward.')}</p><details><summary>${contentText('保存位置与范围','Source and scope')}</summary><p data-user-content>${esc(state.project.path)}</p><p>${contentText('当前仅保存在本机，尚未上传云端。','Saved on this computer only; not uploaded to the cloud.')}</p></details>`,`<button class="secondary-button" data-action="close">${uiText('返回')}</button><button class="primary-button" data-action="save-content-version">${contentText('保存这一稿','Save this draft')}</button>`);
 const input=$('#content-version-title');
 input.placeholder=defaultDraftTitle();
 input.setAttribute('aria-label',contentText('稿件名称（可选，留空按时间命名）','Draft name (optional; leave blank to use the time)'));
 input.insertAdjacentHTML('afterend',`<small>${contentText('名称可留空，按时间命名；之后可随时修改。Ctrl / ⌘ + Enter 保存。','Leave blank to use the time; rename anytime. Ctrl / ⌘ + Enter saves.')}</small>`);
 const choice=$('#initial-preview-choice'),button=$('#dialog [data-action="save-content-version"]');
 if(choice){button.disabled=!choice.value;choice.addEventListener('change',()=>{button.disabled=!choice.value;});choice.focus();}
 else input.focus();
}
async function folderSnapshotFinished(job){
 const ownDialog=$('#dialog [data-folder-job]')?.dataset.folderJob===job.id;
 if(ownDialog)closeDialog();
 await refreshWorkspace();
 if(job.project_id===state.project?.id&&job.status==='complete'){
  const selected=state.selected,tab=state.tab;
  await loadProject(job.project_id,{preserve:true});
  if(state.project?.id!==job.project_id)return;
  if(ownDialog&&job.result?.sha){state.tab='preview';await choose(job.result.sha);}
  else if(selected&&commit(selected)){state.tab=tab;await choose(selected);}
 }
 const preview=job.result?.preview,unchanged=job.result?.unchanged;
 notify(job.status!=='complete'?job.error||job.status:preview?.status==='complete'?contentText(unchanged?'沿用已有稿件，画面已完成。':'文件和画面已保存。',unchanged?'Existing draft reused; image captured.':'Files and image saved.'):['failed','cancelled','needs-configuration','needs-approval'].includes(preview?.status)?contentText('文件已保存，画面未完成；可为这一稿补画面。','Files saved; image incomplete. Capture this same draft later.'):uiText(unchanged?'文件夹没有变化，沿用已有版本。':'版本已保存。'));
 refreshDraftSaveControl();
 if(ownDialog&&job.result?.saved&&job.project_id===state.project?.id){
  const preview=job.result.preview;
  const filesOnly=preview?.status==='needs-configuration'&&preview.plan?.reason==='no-static-entry'&&!visualPresentation(detail(job.result.sha));
  if(preview?.mode==='quick'){
   if(preview.status!=='complete'&&!filesOnly)savedPreviewDialog(job);
  }else if(preview?.mode!=='none'&&preview?.status!=='complete')savedPreviewDialog(job);
 }
}
function savedPreviewDialog(job){
 state.savedPreviewJob=job;
 const p=job.result.preview||{},sha=job.result.sha;
 const message=p.status==='needs-approval'?contentText('文件已保存；截图前需要批准安装依赖和启动网页的命令。尚未执行这些命令。','Files are saved. Review and approve the install and start commands before capture. These commands have not run.'):['auto','quick'].includes(p.mode)?(p.status==='complete'?contentText('截图已生成，并绑定到这一版。','Screenshots captured and bound to this version.'):contentText('版本已保存，但截图未完成；可检查配置后重试。','The version is saved, but capture did not finish. Review settings and retry.')):p.mode==='manual'?contentText('可以提供自己的截图，也可以直接返回；以后不再提醒。','Attach your own screenshot or return now. Future saves will not prompt again.'):contentText('要为这一版添加截图吗？可以跳过，版本已经保存。','Add screenshots for this version? You can skip; the version is already saved.');
 if(p.mode==='manual'){notify(contentText('版本已保存；可在预览中自行添加截图，不再提醒。','Version saved. Attach screenshots in Preview anytime; no reminders.'));return;}
 dialogShell(contentText('版本已保存','Version saved'),`${previewLanguageControls()}<div data-saved-preview="${esc(job.id)}"><p data-user-content>${esc(versionTitle(commit(sha)||{sha,subject:sha.slice(0,8)}))}</p><p data-user-content>${message}</p>${p.error?`<p role="alert" data-user-content>${esc(p.error)}</p>`:''}</div>`,`<button class="secondary-button" data-action="close">${contentText('返回版本','Back to versions')}</button><button class="secondary-button" data-action="saved-preview-manual" data-sha="${esc(sha)}">${contentText('提供截图','Attach screenshot')}</button>${p.status!=='complete'?`<button class="primary-button" data-action="saved-preview-capture" data-sha="${esc(sha)}">${contentText('预览并截图','Preview and capture')}</button>`:`<button class="primary-button" data-action="saved-preview-view" data-sha="${esc(sha)}">${contentText('查看截图','View screenshots')}</button>`}`);
}
function renderFolderFiles(){
 const id=state.project.id,sha=state.selected;
 queueMicrotask(()=>loadFolderFiles(id,sha));
 return `<section class="content-files"><label class="field">${uiText('搜索文件路径')}<input id="content-file-query" type="search" value="${esc(state.contentFileQuery||'')}"></label><div id="content-file-list" role="status">${uiText('读取文件…')}</div></section>`;
}
let contentFileRequest=0,contentFileTimer;
async function loadFolderFiles(project,sha,offset=0){
 const request=++contentFileRequest;
 try{
  const data=await api(query(`/api/projects/${project}/files`,{sha,offset,query:state.contentFileQuery||''}));
  if(request!==contentFileRequest||state.project?.id!==project||state.selected!==sha||state.tab!=='preview'||!$('#content-file-list'))return;
  $('#content-file-list').innerHTML=`<p class="snapshot-message">${data.total} ${uiText('文件')}</p><div class="changed-files">${data.files.map(f=>`<div class="file-row content-file-row"><button class="text-button content-file-name" data-user-content data-action="content-file" data-path="${esc(f.path)}">${esc(f.path)}</button><small>${contentBytes(f.size||0)}</small><button class="text-button" data-action="content-recover" data-path="${esc(f.path)}">${uiText('恢复此文件')}</button></div>`).join('')||`<p>${uiText('没有匹配文件')}</p>`}</div><div class="content-pagination">${offset?`<button class="secondary-button" data-action="content-file-page" data-offset="${Math.max(0,offset-200)}">${uiText('上一页')}</button>`:''}${data.next_offset!==null?`<button class="secondary-button" data-action="content-file-page" data-offset="${data.next_offset}">${uiText('下一页')}</button>`:''}</div>`;
 }catch(error){if(request===contentFileRequest&&$('#content-file-list'))$('#content-file-list').textContent=error.message;}
}
async function duplicateDialog(){
 const project=revisionProject(),sha=state.selected;
 dialogShell('重复内容',`<p>${uiText('读取文件…')}</p>`,'',true);
 const request=state.dialogRequest;
 const data=await api(query(`/api/projects/${project}/duplicates`,{sha}));
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 $('#dialog .dialog-body').innerHTML=`<p>${uiText('相同内容共用存储，名称和目录分别保留。')}</p><p class="snapshot-message">${uiLanguage==='en'?'Duplicate logical bytes':'重复内容字节'} · ${contentBytes(data.shared_bytes)} · ${data.total} ${uiLanguage==='en'?'groups':'组'}</p>${data.groups.map(g=>`<details class="content-duplicate"><summary>${g.paths.length} ${uiText('文件')} · ${contentBytes(g.size)}</summary><p data-user-content>${g.paths.map(esc).join('<br>')}</p></details>`).join('')||`<p>${uiText('没有完全相同的文件内容。')}</p>`}${state.project?.kind==='folder'&&data.total?`<button class="primary-button" data-action="content-organize">${contentText('校验恢复并选择副本','Verify recovery and review copies')}</button>`:''}`;
}
async function contentFileDialog(path){
 const project=revisionProject(),sha=state.selected;
 dialogShell(path,`<p>${uiText('读取文件…')}</p>`,`<button class="secondary-button" data-action="close">${uiText('返回')}</button><button class="primary-button" data-action="content-recover" data-path="${esc(path)}">${uiText('恢复此文件')}</button>`,true);
 $('#dialog-title').setAttribute('data-user-content','');
 const request=state.dialogRequest;
 try{
  const data=await api(query(`/api/projects/${project}/file-content`,{sha,path}));
  if(request!==state.dialogRequest||!$('#dialog').open)return;
  $('#dialog .dialog-body').innerHTML=data.text===null?`<p data-user-content>${esc(data.note)}</p>`:`<pre class="content-text" data-user-content>${esc(data.text)}</pre>`;
 }catch(error){if(request===state.dialogRequest)$('#dialog .dialog-body').textContent=error.message;}
}
Object.assign(workspaceActions,{
 'content-projects':projectPicker,
 'content-open':async b=>{closeDialog();await loadProject(b.dataset.project);},
 'save-content-project':async()=>{
  const path=$('#content-import-path').value.trim();
  if(!path)throw Error(contentText('请先选择或填写网页文件夹。','Choose or enter a website folder first.'));
  await addWebsiteFolder(path,state.dialogRequest);
 },
 'content-snapshot':saveDraftFromToolbar,
 'save-content-version':()=>saveCurrentDraft($('#content-version-title').value,{fromDialog:true}),
 'remember-draft-preview':b=>{if(b.dataset.sha!==state.selected)return;previewPreferencesDialog({mode:'auto'});},
 'preview-preferences':()=>previewPreferencesDialog(),
 'save-preview-preferences':async()=>{
  if(state.previewPreferenceTarget!==state.project?.id)throw Error(contentText('项目已经变化。','The project has changed.'));
  const result=await api(`/api/projects/${state.project.id}/preview-preferences`,{method:'PUT',body:JSON.stringify(previewPreferenceRequest())});
  state.project.preview_preferences=result;renderDetail();await settings();
 },
 'saved-preview-manual':async b=>{await choose(b.dataset.sha);manualDialog();},
 'saved-preview-capture':async b=>{await choose(b.dataset.sha);closeDialog();await quickPreviewDialog();},
 'saved-preview-view':async b=>{closeDialog();await choose(b.dataset.sha);setDetailTab('preview');},
 'content-duplicates':duplicateDialog,
 'content-file':b=>contentFileDialog(b.dataset.path),
 'content-recover':b=>recoveryDialog([b.dataset.path]),
 'recover-file-side':b=>recoveryDialog([b.dataset.path],{project:b.dataset.project,sha:b.dataset.sha}),
 'copy-recovery-path':async()=>{await navigator.clipboard.writeText(state.recoveryResultJob.result.path);notify(contentText('已复制恢复位置。','Recovery location copied.'));},
 'reveal-recovery':async()=>{await api('/api/recoveries/'+state.recoveryResultJob.result.id+'/reveal',{method:'POST',body:'{}'});},
 'content-file-page':b=>loadFolderFiles(state.project.id,state.selected,Number(b.dataset.offset))
});
document.addEventListener('input',e=>{
 if(e.target.id!=='content-file-query')return;
 state.contentFileQuery=e.target.value;clearTimeout(contentFileTimer);
 contentFileTimer=setTimeout(()=>loadFolderFiles(state.project.id,state.selected),180);
});
document.addEventListener('keydown',e=>{
 if(e.isComposing||e.repeat||!(e.ctrlKey||e.metaKey)||e.altKey||state.project?.kind!=='folder')return;
 if(e.key==='Enter'&&$('#dialog').open&&$('#content-version-title')){
  e.preventDefault();Promise.resolve(workspaceActions['save-content-version']()).catch(error=>notify(error.message));return;
 }
 if(e.key.toLowerCase()!=='s'||$('#dialog').open||e.target.closest('input,textarea,select,[contenteditable="true"]'))return;
 e.preventDefault();Promise.resolve(e.shiftKey?snapshotDialog():saveDraftFromToolbar()).catch(error=>notify(error.message));
});

async function privacyDialog(){
 dialogShell(contentText('本地数据与隐私','Local data and privacy'),`<p>${contentText('读取本地设置…','Reading local settings…')}</p>`);
 $('#dialog').classList.add('content-dialog');
 const request=state.dialogRequest,data=await api('/api/privacy');
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 $('#dialog .dialog-body').innerHTML=`<p>${contentText('保存版本、指纹计算、去重和恢复在你的电脑上执行，不调用 AI、不自动上传，也没有使用统计上报。','Saving, fingerprinting, deduplication and recovery run on your computer, without AI calls, automatic uploads or telemetry.')}</p><h3>${contentText('会读取和保存什么','What is read and saved')}</h3><p>${contentText('仅处理你明确加入的项目。首次保存读取文件字节，后续按变化增量处理。索引包含路径、大小、时间、权限和指纹；版本库同时保存文件原始内容。不会做语义分析、OCR 或向量索引，也没有后台全盘扫描。','Only explicitly added projects are processed. The first save reads file bytes; later saves process changes. The index stores paths, sizes, times, modes and hashes, and the version library stores original file content. There is no semantic analysis, OCR, vector indexing or background disk scan.')}</p><h3>${contentText('本地保存位置','Local storage')}</h3><p data-user-content class="project-path">${esc(data.storage)}</p><p>${contentText('版本库未加密。能访问此账户文件的程序可能读取它；这是本地存储，不是独立的系统沙箱。版本仅在明确确认后删除；恢复副本、截图和日志会保留。排除路径不会抹去已经保存的历史。','The library is not encrypted. Programs with access to this account may read it; local storage is not an independent OS sandbox. Versions are deleted only after explicit confirmation; recovery copies, screenshots and logs are retained. Excluding a path does not erase previously saved history.')}</p><h3>${contentText('AI 的边界','AI boundary')}</h3><p>${contentText('通过 Codex 等 AI 代理调用 Skill 时，命令输出和代理打开的文件可能进入模型上下文，适用该代理自己的数据政策。Skill 默认返回摘要，不自动读取正文给模型。','When an AI agent such as Codex uses the Skill, command output and files opened by the agent may enter its model context under its own data policy. The Skill defaults to summaries and does not automatically read document bodies into model context.')}</p><details><summary>${contentText('查看已加入范围与排除规则','Inspect added scopes and exclusions')}</summary>${data.projects.map(p=>`<p data-user-content><strong>${esc(p.name)}</strong><br>${esc(p.path)}${p.exclusions?.length?'<br>'+p.exclusions.map(esc).join('<br>'):''}</p>`).join('')||`<p>${contentText('尚未加入项目。','No projects added.')}</p>`}</details>`;
}
async function startOrganization(){
 const job=await api(`/api/projects/${revisionProject()}/organize`,{method:'POST',body:JSON.stringify({sha:state.selected})});
 mergeWorkspaceJobs([job]);
 dialogShell(contentText('校验恢复','Verify recovery'),`<p data-organization-job="${esc(job.id)}" role="status">${contentText('正在核对可复用的完整恢复副本；没有有效副本时才新建并逐个读回。完成后才会显示副本选择。','Checking an existing exact recovery copy, or creating one if none is valid, then reading back every file. Copy selection appears after verification.')}</p><p>${contentText('恢复副本和回执会保留，并占用本机空间。此操作不会移除原文件。','The restored copy and receipt are retained and use local space. This operation does not remove original files.')}</p>`,`<button class="secondary-button" data-action="close">${uiText('返回版本')}</button><button class="secondary-button" data-action="cancel-job" data-job="${esc(job.id)}">${uiText('取消任务')}</button>`);
 pollWorkspaceJob(job.id);
}
async function organizationFinished(job){
 await refreshWorkspace();
 if($('#dialog [data-organization-job]')?.dataset.organizationJob===job.id){
  if(job.status==='complete')await organizationDialog(job.result.id);
  else $('#dialog .dialog-body').textContent=job.error||job.status;
 }else notify(job.status==='complete'?contentText('恢复校验完成，可在项目设置查看副本选择。','Recovery verified. Review copies in project settings.'):job.error||job.status);
}
async function organizationDialog(id,offset=0){
 dialogShell(contentText('审阅副本清单','Review duplicate copies'),`<p>${uiText('读取文件…')}</p>`,'',true);
 $('#dialog').classList.add('content-dialog');
 const request=state.dialogRequest,plan=await api(`/api/organization/${id}`);
 if(request!==state.dialogRequest||!$('#dialog').open)return;
 if(state.organizationPlan!==id||!state.organizationChoices)state.organizationChoices=new Set(plan.selected_paths);
 state.organizationPlan=id;
 $('#dialog .dialog-body').innerHTML=`<p>${contentText('此快照已完整恢复并读回校验文件内容、权限、修改时间、已保存扩展属性和空目录。ACL、文件系统标志、所有者、排除项和程序运行效果不在此验证范围。','This snapshot was fully restored and its file bytes, modes, modification times, saved extended attributes and empty directories were read back and verified. ACLs, file-system flags, ownership, exclusions and application execution are outside this verification.')}</p><p class="snapshot-message">${contentText('默认不勾选。选择会保存为待执行清单，尚不移除文件；不能把逻辑重复字节当成实际可释放空间。','Nothing is preselected. Choices are saved as a pending review and do not remove files. Logical duplicate bytes are not actual reclaimable disk space.')}</p><p>${plan.candidate_count} ${contentText('个重复副本','duplicate copies')} · ${contentBytes(plan.duplicate_logical_bytes)}</p>${plan.candidates.slice(offset,offset+200).map(c=>`<label class="check-field content-choice"><input type="checkbox" data-content-choice value="${esc(c.path)}" ${c.selectable?'':'disabled'} ${state.organizationChoices.has(c.path)?'checked':''}><span data-user-content>${esc(c.path)}<small>${contentText('保留','Keep')}: ${esc(c.keeper)}${c.reasons.length?'<br>'+c.reasons.map(esc).join('<br>'):''}</small></span></label>`).join('')||`<p>${contentText('没有可整理的重复副本。','No duplicate copies to organize.')}</p>`}<p data-user-content>${plan.recovery_reused?contentText('已重新读回并复用完整恢复副本，本次未新增整版副本。','The existing exact recovery copy was read back again and reused; no full copy was added.'):contentText('本次新增完整恢复副本；该副本继续保留。','This review added a complete recovery copy, which remains saved.')}</p><details><summary>${contentText('恢复位置与回执','Recovery location and receipt')}</summary><p data-user-content>${esc(plan.recovery_path)}<br>${esc(plan.receipt)}</p></details>`;
 if(plan.candidates.length>200)$('#dialog .dialog-body').insertAdjacentHTML('beforeend',`<div class="content-pagination">${offset?`<button class="secondary-button" data-action="content-plan-page" data-offset="${Math.max(0,offset-200)}">${uiText('上一页')}</button>`:''}<span>${offset+1}–${Math.min(offset+200,plan.candidate_count)} / ${plan.candidate_count}</span>${offset+200<plan.candidate_count?`<button class="secondary-button" data-action="content-plan-page" data-offset="${offset+200}">${uiText('下一页')}</button>`:''}</div>`);
 $('#dialog .dialog-footer').innerHTML=`<button class="secondary-button" data-action="close">${uiText('返回版本')}</button><button class="primary-button" data-action="content-select-copies">${contentText('保存我的选择','Save my selection')}</button>`;
}
Object.assign(workspaceActions,{
 'content-privacy':privacyDialog,
 'content-organize':startOrganization,
 'content-plan':b=>organizationDialog(b.dataset.plan),
 'content-plan-page':b=>{captureOrganizationChoices();return organizationDialog(state.organizationPlan,Number(b.dataset.offset));},
 'content-select-copies':async()=>{
  captureOrganizationChoices();
  const paths=[...state.organizationChoices];
  if(paths.length>200)throw Error(contentText('一次最多选择 200 个副本。','Select at most 200 copies at a time.'));

  const result=await api(`/api/organization/${state.organizationPlan}/selection`,{method:'POST',body:JSON.stringify({paths})});
  state.organizationChoices=null;
  dialogShell(contentText('选择已保存','Selection saved'),`<p>${result.selected_count} ${contentText('个副本已列入待执行清单。尚未移除任何文件。','copies in the pending review. No files have been removed.')}</p><p data-user-content>${esc(result.receipt)}</p>`);
 }
});

function captureOrganizationChoices(){
 for(const e of $$('[data-content-choice]')){if(e.checked)state.organizationChoices.add(e.value);else state.organizationChoices.delete(e.value);}
}

async function startMaintenance(operation){
 const project=revisionProject(),sha=state.selected;
 const title=operation==='verify'?contentText('检查已保存版本','Check saved version'):contentText('查看本机存储','Inspect local storage');
 dialogShell(title,`<p role="status">${contentText('正在创建检查任务…','Starting the inspection…')}</p>`);
 $('#dialog').classList.add('content-dialog');
 const request=state.dialogRequest;
 const job=await api(operation==='verify'?`/api/projects/${project}/verify`:'/api/storage',
  {method:'POST',body:JSON.stringify(operation==='verify'?{sha}:{})});
 mergeWorkspaceJobs([job]);
 if(request===state.dialogRequest&&$('#dialog').open){
  $('#dialog .dialog-body').innerHTML=`<p role="status" data-maintenance-job="${esc(job.id)}">${operation==='verify'?contentText('正在读取此版本的清单和已存内容，检查大小与指纹。无需原文件夹在线，也不会生成恢复副本。','Reading this version’s manifest and saved content to check sizes and hashes. The source folder need not be online; no restored copy is created.'):contentText('只统计 Reprise 数据目录内的文件元数据，不读取文件正文，不跟随符号链接。','Counting file metadata only inside the Reprise data directory, without reading file contents or following symbolic links.')}</p>`;
  $('#dialog .dialog-footer').innerHTML=`<button class="secondary-button" data-action="settings">${contentText('返回设置','Back to settings')}</button><button class="secondary-button" data-action="cancel-job" data-job="${esc(job.id)}">${uiText('取消任务')}</button><span id="dialog-status" role="status"></span>`;
 }
 pollWorkspaceJob(job.id);
}
async function maintenanceFinished(job){
 await refreshWorkspace();
 if($('#dialog [data-maintenance-job]')?.dataset.maintenanceJob===job.id)maintenanceResult(job);
 else notify(job.status==='complete'?contentText('检查完成，可在设置中查看结果。','Inspection complete. View the result in Settings.'):job.error||uiText('已取消'));
}
function maintenanceResult(job){
 const storage=job.operation==='storage',r=job.result;
 const complete=job.status==='complete',verified=complete&&r?.status==='verified';
 let body;
 if(!complete){
  body=`<p role="alert" data-user-content>${esc(job.error||uiText('已取消'))}</p><p>${contentText('检查未完成，不代表内容完好。已有版本和诊断保留。','The check did not complete and does not establish content integrity. Existing versions and diagnostics are retained.')}</p>`;
 }else if(storage){
  const label={content:['内容库','Content library'],recoveries:['恢复与导出副本','Recovery and export copies'],runtimes:['运行副本','Runtime copies'],evidence:['预览与媒体','Previews and media'],state:['登记与状态','Registry and state'],other:['其他保留资料','Other retained data']};
  body=`<p role="status">${r.restored_historical_report?contentText('从备份恢复的旧库历史统计，请重新统计','Historical count from the old library; run a new count'):r.status==='complete'?contentText('数据目录统计完成','Data directory counted'):contentText('统计不完整，部分内容无法读取','Partial report: some entries could not be read')}</p><p data-user-content class="project-path">${esc(r.storage_path)}</p><div class="content-metrics">${[[contentBytes(r.logical_bytes),contentText('文件逻辑长度','Logical file bytes')],[r.allocated_bytes===null?contentText('未知','Unknown'):contentBytes(r.allocated_bytes),contentText('文件分配块估计','Estimated allocated file blocks')],[r.filesystem_free_bytes===null?contentText('未知','Unknown'):contentBytes(r.filesystem_free_bytes),contentText('所在文件系统可用','Filesystem available')]].map(([v,l])=>`<span><strong>${esc(v)}</strong><small>${esc(l)}</small></span>`).join('')}</div><table class="storage-table"><thead><tr><th>${contentText('用途','Purpose')}</th><th>${contentText('文件长度','File bytes')}</th><th>${contentText('分配块估计','Allocated estimate')}</th></tr></thead><tbody>${r.categories.map(c=>`<tr><td>${esc((label[c.key]||[c.label,c.label])[uiLanguage==='en'?1:0])}</td><td>${contentBytes(c.logical_bytes)}</td><td>${c.allocated_bytes===null?contentText('未知','Unknown'):contentBytes(c.allocated_bytes)}</td></tr>`).join('')}</tbody></table><p>${contentText('只统计此数据目录内的普通文件，硬链接字节仅计一次。外部源目录、外部恢复路径和旧归档库不在范围内。','Only regular files inside this data directory are counted, with hard-linked bytes counted once. External source folders, external restore destinations and external legacy archives are outside this scope.')}</p><p class="snapshot-message">${contentText('这是运行期间的统计，不是原子快照。APFS 共享块、压缩与快照会影响实际占用；分配块不代表独占空间或可释放量。实际可释放量：未知。没有删除文件。','This is a live count, not an atomic snapshot. APFS shared blocks, compression and snapshots affect physical usage; allocated blocks are not exclusive or reclaimable space. Reclaimable space: unknown. No files were removed.')}</p>${r.warnings.length?`<ul>${r.warnings.map(w=>`<li data-user-content>${esc(w.message)} (${w.count})</li>`).join('')}</ul>`:''}`;
 }else{
  body=`<p role="status">${verified?contentText('此版本的已存内容检查通过','Saved content for this version passed inspection'):contentText('此版本未通过完整性检查','This version did not pass inspection')}</p><p data-user-content class="identity-sha">${esc(r.sha)}</p><div class="content-metrics">${[[r.checked_files,contentText('已检查文件','Files checked')],[r.checked_objects,contentText('不同内容对象','Unique content objects')],[contentBytes(r.checked_bytes),contentText('已读回内容','Content read back')]].map(([v,l])=>`<span><strong>${esc(v)}</strong><small>${esc(l)}</small></span>`).join('')}</div><p>${contentText('本次只检查选中的精确版本。其他历史版本尚未检查；检查未生成恢复副本，不代表实际恢复演练、独立备份或程序运行验证通过。','Only the selected exact version was checked. Other historical versions were not checked. No restored copy was created; this does not establish a successful restore drill, independent backup or application execution.')}</p>`;
 }
 dialogShell(storage?contentText('本机存储账本','Local storage report'):contentText('版本完整性检查','Version integrity check'),body,`<button class="secondary-button" data-action="settings">${contentText('返回设置','Back to settings')}</button>`);
 $('#dialog').classList.add('content-dialog');
}
Object.assign(workspaceActions,{
 'content-storage':()=>startMaintenance('storage'),
 'content-verify':()=>startMaintenance('verify'),
 'content-maintenance-result':b=>maintenanceResult(state.jobs.find(j=>j.id===b.dataset.job))
});
