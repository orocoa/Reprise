'use strict';
// Visual history is a view of immutable versions, not a second history model.
let draftImages = new Map(), draftImageRequest = 0;
function draftView(){return state.prefs.historyView||(state.project?.kind==='folder'?'pictures':'graph');}
async function loadDraftImages(){
 const request=++draftImageRequest,project=state.project?.id;
 draftImages=new Map();
 const sources=[...new Set([project,...state.commits.map(c=>c.source_project_id)].filter(Boolean))];
 const results=await Promise.allSettled(sources.map(id=>api(`/api/projects/${id}/visual-history`)));
 if(request!==draftImageRequest||project!==state.project?.id)return;
 results.forEach((result,i)=>{if(result.status==='fulfilled')for(const [sha,item] of Object.entries(result.value.images))draftImages.set(`${sources[i]}:${sha}`,item);});
 state.draftImagesError=results.some(result=>result.status==='rejected');
 renderDraftHistory();
}
function draftImage(c){
 return draftImages.get(`${revisionProject(c.sha)}:${c.sha}`);
}
function renderDraftHistory(){
 const list=$('#draft-list');if(!list)return;
 const pictures=draftView()==='pictures';
 list.hidden=!pictures;$('#history-scroll').hidden=pictures;
 $('.history')?.classList.toggle('picture-history',pictures);
 $$('[data-action="draft-view"]').forEach(b=>{const selected=b.dataset.view===draftView();b.classList.toggle('active',selected);b.setAttribute('aria-pressed',selected);});
 if(!pictures)return;
 const scroll=list.scrollTop,focus=captureViewFocus(list),matches=results();
 const limit=state.draftLimit||60,visible=matches.slice(0,limit),selectedIndex=matches.findIndex(c=>c.sha===state.selected);
 if(selectedIndex>=limit)visible.push(matches[selectedIndex]);
 list.innerHTML=(state.draftImagesError?`<p class="snapshot-message">${contentText('部分截图读取失败，可刷新重试。','Some images could not be read. Refresh to retry.')}</p>`:'')+visible.map((c,index)=>{
  const image=draftImage(c),selected=c.sha===state.selected;
  const gap=index===limit?`<p class="snapshot-message draft-gap">${contentText(`省略 ${selectedIndex-limit} 稿，已定位所选旧稿。`,`${selectedIndex-limit} drafts skipped to show the selected older version.`)}</p>`:'';
  return gap+`<button class="draft-card ${selected?'selected':''}" data-action="draft-select" data-id="${esc(c.sha)}" aria-current="${selected}" data-user-label aria-label="${esc(versionTitle(c))}"><span class="draft-image">${image?`<img src="${esc(image.url)}" alt="${esc(versionTitle(c))}" loading="lazy">`:`<span class="draft-missing">${icon('file')}<span>${contentText('此稿尚无截图','No image for this draft')}</span></span>`}</span><span class="draft-card-copy"><strong data-user-content>${esc(versionTitle(c))}</strong><time datetime="${esc(c.committed_at)}">${esc(formatDate(c.committed_at))}</time>${image?.source==='manual'?`<small>${contentText('自行提供的截图','User-supplied image')}</small>`:''}${image&&(!image.complete||image.warnings?.length)?`<small>${contentText('画面有诊断提醒','Capture has diagnostics')}</small>`:''}${state.prefs.stars.includes(c.sha)?`<span class="draft-favorite">${icon('star')}${contentText('已收藏','Saved favorite')}</span>`:''}</span></button>`;
 }).join('')+(!matches.length?`<p class="snapshot-message">${contentText(state.commits.length?'没有匹配的版本。':'保存第一稿后，画面会出现在这里。',state.commits.length?'No matching versions.':'Save your first draft to see it here.')}</p>`:'')+(matches.length>limit?`<button class="secondary-button" data-action="draft-more">${contentText(`再显示 60 稿 · 共 ${matches.length} 稿`,`Show 60 more · ${matches.length} drafts`)}</button>`:'');
 list.scrollTop=scroll;restoreViewFocus(focus,list);
}
function scrollSelectedDraft(){
 if(draftView()!=='pictures')return;
 const list=$('#draft-list'),card=list?.querySelector('.draft-card.selected');
 if(!card)return;
 const view=list.getBoundingClientRect(),item=card.getBoundingClientRect();
 if(item.top<view.top)list.scrollTop+=item.top-view.top;
 else if(item.bottom>view.bottom)list.scrollTop+=item.bottom-view.bottom;
}
function scrollSelectedHistory(){
 if(draftView()==='pictures'){scrollSelectedDraft();return;}
 const row=$(`.version-row[data-id="${state.selected}"]`),scroller=$('#history-scroll');
 if(!row||!scroller)return;
 const top=row.offsetTop,bottom=top+row.offsetHeight;
 if(top<scroller.scrollTop)scroller.scrollTop=top;
 else if(bottom>scroller.scrollTop+scroller.clientHeight)scroller.scrollTop=bottom-scroller.clientHeight;
}
async function quickPreviewDialog(root,target=null){
 const project=target?.project||revisionProject(),sha=target?.sha||state.selected;
 if(project!==revisionProject()||sha!==state.selected)return;
 dialogShell(contentText('保存这一稿的画面','Save this draft’s appearance'),previewLanguageControls()+`<p role="status">${contentText('正在识别网页入口…','Finding the webpage entry…')}</p>`);
 $('#dialog').dataset.quickPreview='true';
 state.quickPreviewTarget={project,sha,root,recipe:null};
 const request=state.dialogRequest;
 const plan=await api(query(`/api/projects/${project}/quick-preview`,{sha,...(root?{root}:{})}));
 if(request!==state.dialogRequest||!$('#dialog').open||project!==revisionProject()||sha!==state.selected)return;
 state.quickPreviewTarget={project,sha,root:plan.root,recipe:plan.status==='needs-approval'?plan.recipe:null};
 const reasons={
  'existing-settings':['这一稿已有你保存的运行配置，请使用原配置截图，或在高级设置中修改。','This draft already has saved run settings. Use them to capture, or edit them in advanced settings.'],
  'no-static-entry':['这个项目需要运行配置，才能生成画面。文件版本已经保留。','This project needs run settings before an image can be captured. Its files remain saved.'],
  'missing-assets':['这一稿缺少网页引用的本地文件。先检查文件，或使用高级配置。','This draft refers to missing local assets. Inspect its files or use advanced settings.'],
  'remote-assets':['网页使用网络图片、字体或脚本，需要先确认网络权限。','This webpage uses online assets. Review network access in advanced settings first.'],
  'ambiguous-entry':['这一稿有多个同名入口，需要选择配置。','This draft has ambiguous entry files. Choose its configuration first.'],
  'missing-npm-lockfile':['这一稿没有 package-lock.json，暂不能准备 npm/Vite 快捷截图。可在原项目中生成并核对锁文件后保存新稿，或手动配置运行方式。已保存的文件保留。','This draft has no package-lock.json, so the npm/Vite quick capture plan is unavailable. Generate and review a lockfile in your source project, then save a new draft, or configure the run commands manually. Saved files remain available.'],
  'npm-lockfile-needs-configuration':['这一稿的 npm 锁文件不符合快捷预览条件：需要与 package.json 一致的 v2/v3 锁文件，以及完整的 HTTPS 依赖记录。请核对后保存新稿，或手动配置。','This npm lockfile does not meet quick preview requirements: a v2/v3 lock matching package.json with complete HTTPS dependency records. Review it and save a new draft, or configure commands manually.'],
  'dev-script-needs-configuration':['快捷预览目前只支持 dev 脚本为 vite、vite dev 或 vite serve 的项目。此稿使用其他启动方式，请核对并保存运行配置。','Quick preview currently supports dev scripts containing only vite, vite dev, or vite serve. This draft uses another start command; review and save its run settings.'],
  'workspace-needs-configuration':['这一稿使用多包 workspace，需要明确依赖安装与启动目录。请在运行配置中核对；不会自动执行脚本。','This draft uses a multi-package workspace. Review its install and start directories in run settings; no scripts run automatically.'],
  'package-manager-needs-configuration':['快捷预览目前仅支持 npm package-lock.json。此稿使用其他包管理器或锁文件，请核对并保存对应运行配置。','Quick preview currently supports npm package-lock.json only. This draft uses another package manager or lockfile; review and save the matching run settings.'],
  'missing-vite-html-entry':['选定目录没有可用的 index.html，无法作为此 Vite 快捷预览的入口。请核对入口，或手动配置运行方式。','The selected directory has no usable index.html for this Vite quick preview. Review the entry or configure the run commands manually.'],
  'unsupported-package':['这个包不在 Vite 快捷预览范围内。请选择其他入口，或核对并保存它的运行配置。','This package is outside the Vite quick preview scope. Choose another entry, or review and save its run settings.'],
  'project-path-needs-configuration':['此项目目录不能直接生成快捷预览配置，请手动核对运行目录和命令。','A quick preview recipe could not be prepared for this project path. Review its working directory and commands manually.']
 };
 const ready=plan.status==='ready',multiple=plan.status==='choose-entry',approval=plan.status==='needs-approval';
 if(approval){
  const commands=plan.recipe.commands;
  const scripts=Object.entries(plan.execution?.scripts||{}).map(([name,value])=>`${name}: ${value}`).join('\n');
  $('#dialog .dialog-body').innerHTML=previewLanguageControls()+`<p data-user-content>${esc(versionTitle(commit(sha)))}</p><p>${contentText('文件已保存。这个 Vite 网页需要先安装依赖并启动，才能截图。','Files are saved. This Vite webpage needs dependencies installed and a server started before capture.')}</p><p>${contentText('以下命令只以这一稿的独立副本为工作目录；会联网下载依赖，并执行项目及依赖脚本、Vite 配置和插件。命令使用当前系统权限，独立副本不是安全沙箱。','These commands use an independent copy of this draft as their working directory. They download dependencies and execute project and dependency scripts, Vite configuration, and plugins with your current system permissions. The copy is not a security sandbox.')}</p><pre data-user-content>${esc([...(commands.install||[]),commands.start].map(argv=>argv.join(' ')).join('\n'))}</pre>${scripts?`<details><summary>${contentText('此稿的相关脚本','Related scripts in this draft')}</summary><pre data-user-content>${esc(scripts)}</pre></details>`:''}<p>${contentText(state.project?.preview_preferences?.pending_recipe?'本项目已选择以后留稿都保存画面。确认后，这份配置也用于后续留稿；新配置另行确认。浏览器的本机网络限制不约束上述命令。':'本次批准只保存到这一稿。浏览器截图仅允许本机网络；此限制不约束上面的命令。',state.project?.preview_preferences?.pending_recipe?'This project is set to save images on future drafts. Approving these settings also enables their reuse; changed settings need another review. The browser local-network limit does not restrict the commands above.':'Approval is saved for this draft only. Browser capture allows local network access; this limit does not restrict the commands above.')}</p>`;
  $('#dialog .dialog-footer').innerHTML=`<span id="dialog-status" role="status"></span><button class="secondary-button" data-action="close">${contentText('暂不运行','Not now')}</button><button class="primary-button" data-action="approve-draft-preview">${contentText('批准以上命令并截图','Approve these commands and capture')}</button>`;
  return;
 }
 $('#dialog .dialog-body').innerHTML=previewLanguageControls()+`<p data-user-content>${esc(versionTitle(commit(sha)))}</p>${ready?`<p>${contentText('将在这一稿的独立副本中打开网页并截图，只允许本机网络，不执行安装或构建命令。','Opens an independent copy of this draft and captures it with local network access only. No install or build commands run.')}</p><p><code>${esc(plan.entry)}</code></p>`:multiple?`<p>${contentText('这一稿包含多个网页，请选择要记住的画面。','This draft contains multiple websites. Choose the appearance to save.')}</p><div class="content-projects">${plan.candidates.map(c=>`<button class="content-project" data-action="quick-entry" data-root="${esc(c.root)}"><strong data-user-content>${esc(c.entry||c.root)}</strong><span>${c.available?(c.framework==='vite'?contentText('需批准运行命令','Command approval needed'):contentText('可直接截图','Ready to capture')):contentText('需要配置','Needs configuration')}</span></button>`).join('')}</div>`:`<p>${contentText(...(reasons[plan.reason]||['此网页暂不能直接截图，请补充运行配置。','This webpage needs additional run settings.']))}</p>`}`;
 $('#dialog .dialog-footer').innerHTML=`<span id="dialog-status" role="status"></span><button class="secondary-button" data-action="close">${contentText('返回','Back')}</button>${ready?`<button class="primary-button" data-action="save-quick-preview">${contentText('保存配置并截图','Save settings and capture')}</button>`:multiple?'':`${plan.reason==='existing-settings'?`<button class="primary-button" data-action="capture">${contentText('按原配置截图','Capture with saved settings')}</button>`:''}<button class="secondary-button" data-action="recipe">${contentText('打开运行配置','Open run settings')}</button><button class="text-button" data-action="manual">${contentText('提供自己的截图','Attach my screenshot')}</button>`}`;
}
Object.assign(workspaceActions,{
 'draft-view':b=>{state.prefs.historyView=b.dataset.view;savePrefs();renderHistory();requestAnimationFrame(scrollSelectedHistory);},
 'draft-select':async b=>{await setDetailTab('preview');await choose(b.dataset.id);},
 'draft-more':()=>{state.draftLimit=(state.draftLimit||60)+60;renderDraftHistory();},
 'quick-preview':()=>quickPreviewDialog(),
 'quick-entry':b=>quickPreviewDialog(b.dataset.root),
 'approve-draft-preview':async()=>{
  const target=state.quickPreviewTarget,request=state.dialogRequest;
  if(!target?.recipe||target.project!==revisionProject()||target.sha!==state.selected)throw Error(contentText('所选版本已变化。','The selected version changed.'));
  await api(`/api/projects/${target.project}/recipe`,{method:'PUT',body:JSON.stringify({sha:target.sha,recipe:target.recipe})});
  state.details.delete(`${target.project}:${target.sha}`);
  await loadDetail(target.sha,undefined,target.project);
  const job=await api(`/api/projects/${target.project}/capture`,{method:'POST',body:JSON.stringify({sha:target.sha})});
  mergeWorkspaceJobs([job]);
  if(request===state.dialogRequest&&$('#dialog').open&&target.project===revisionProject()&&target.sha===state.selected){closeDialog();state.tab='preview';renderDetail();}
  notify(contentText('配置已保存，正在保存这一稿的画面…','Settings saved. Capturing this draft’s appearance…'));pollWorkspaceJob(job.id);
 },
 'save-quick-preview':async()=>{
  const target=state.quickPreviewTarget,request=state.dialogRequest;
  if(!target||target.project!==revisionProject()||target.sha!==state.selected)throw Error(contentText('所选版本已变化。','The selected version changed.'));
  const job=await api(`/api/projects/${target.project}/quick-preview`,{method:'POST',body:JSON.stringify({sha:target.sha,root:target.root})});
  mergeWorkspaceJobs([job]);
  if(request===state.dialogRequest&&$('#dialog').open&&target.project===revisionProject()&&target.sha===state.selected){closeDialog();state.tab='preview';renderDetail();}
  notify(contentText('正在保存这一稿的画面…','Saving this draft’s appearance…'));pollWorkspaceJob(job.id);
 },
 'choose-local-folder':async b=>{
  const request=state.dialogRequest;b.disabled=true;
  try{
   const result=await api('/api/desktop/choose-folder',{method:'POST',body:'{}'});
   if(request!==state.dialogRequest||!$('#dialog').open)return;
   if(result.status==='selected'){$('#content-import-path').value=result.path;$('#chosen-folder-label').textContent=result.path;}
   else if(result.status!=='cancelled'){$('#manual-folder-path').open=true;$('#dialog-status').textContent=result.reason||contentText('系统选择器不可用，请粘贴文件夹路径。','The native picker is unavailable. Paste a folder path.');}
  }finally{if(b.isConnected)b.disabled=false;}
 }
});

