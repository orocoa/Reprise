'use strict';
// Preserve the control being used across synchronous view refreshes. A later
// async response must never pull focus back from another part of the page.
function captureViewFocus(root){
 const active=document.activeElement;
 if(!active||!root?.contains(active))return null;
 if(active.tagName==='SUMMARY'&&active.parentElement.dataset.keepOpen)return {active,disclosure:active.parentElement.dataset.keepOpen};
 const attributes=['id','data-action','data-id','data-tab','data-record','data-index','data-density','data-job','data-runtime','data-path','data-language','data-direction','data-zoom'];
 const identity=attributes.filter(name=>active.hasAttribute(name)).map(name=>[name,active.getAttribute(name)]);
 return identity.length?{active,identity}:null;
}
function restoreViewFocus(saved,root){
 if(!saved||saved.active.isConnected||document.activeElement!==document.body)return;
 const replacement=saved.disclosure?
  [...root.querySelectorAll('details[data-keep-open]')].find(element=>element.dataset.keepOpen===saved.disclosure)?.querySelector('summary'):
  [...root.querySelectorAll('[id],[data-action]')].find(element=>saved.identity.every(([name,value])=>element.getAttribute(name)===value));
 replacement?.focus({preventScroll:true});
}
function openDisclosures(root){return new Set([...root.querySelectorAll('details[open][data-keep-open]')].map(element=>element.dataset.keepOpen));}
function restoreDisclosures(root,opened){for(const element of root.querySelectorAll('details[data-keep-open]'))element.open=opened.has(element.dataset.keepOpen);}
function captureDialogContext(any=false){
 const dialog=$('#dialog');
 if(!dialog.open||(!any&&!dialog.classList.contains('settings-dialog')))return null;
 return {nodes:[...dialog.childNodes],className:dialog.className,origin:returnFocus,parent:dialogParent,dataset:{...dialog.dataset},
  focused:document.activeElement,focus:captureViewFocus(dialog),scrollTop:dialog.scrollTop};
}
// The workspace follows its launch repository. Related archives retain their own identities.
function revisionProject(sha=state.selected){return commit(sha)?.source_project_id||state.project?.id;}
function workspaceProjectIds(){return new Set([state.project?.id,...(state.historySources||[]).map(s=>s.id)]);}
function notesDraft(){const d=detail(state.selected),c=commit(state.selected);return structuredClone(d.notes?.localizations||{zh:{title:c.subject,summary:uiLanguage==='zh'?summary(d):`${d.diff.counts.total} 个文件变化。`,changes:[`${d.diff.counts.total} 个文件变化。`]},en:{title:c.subject,summary:`${d.diff.counts.total} changed files in this commit.`,changes:[`${d.diff.counts.total} changed files in this commit.`]}});}
function inlineNotesDialog(field='metadata'){
 if(!detail(state.selected))return;
 const draft=notesDraft(),language=uiLanguage,entry=draft[language];
 state.noteEdit={project:revisionProject(),sha:state.selected,field,language,draft};
 const titleField=`<label class="field">名称<input id="inline-title" maxlength="120" value="${esc(entry.title)}" autocomplete="off"></label>`;
 const summaryField=`<label class="field">简介<textarea id="inline-summary" rows="4" maxlength="1200">${esc(entry.summary)}</textarea></label>`;
 const changesField=`<label class="field">更新说明（每行一条）<textarea id="inline-changes" rows="7">${esc((entry.changes||[]).join('\n'))}</textarea></label>`;
 const fields=field==='changes'?changesField:field==='summary'?summaryField:titleField+summaryField;
 dialogShell(field==='changes'?'修改更新说明':field==='summary'?'编辑简介':'修改版本信息',`<p class="snapshot-message">Git 原始提交信息始终保留。</p>${fields}`,`<button class="secondary-button" data-action="close">取消</button><button class="primary-button" data-action="save-inline-notes">保存修改</button>`);
 $(field==='changes'?'#inline-changes':field==='summary'?'#inline-summary':'#inline-title')?.focus();
}
async function saveInlineNotes(){
 const edit=state.noteEdit;if(!edit||edit.sha!==state.selected||edit.project!==revisionProject())throw Error('编辑对象已经变化，请重新打开。');
 const entry=edit.draft[edit.language];
 if(edit.field==='changes')entry.changes=$('#inline-changes').value.split('\n').map(v=>v.trim()).filter(Boolean);
 else if(edit.field==='summary')entry.summary=$('#inline-summary').value.trim();
 else{entry.title=$('#inline-title').value.trim();entry.summary=$('#inline-summary').value.trim();}
 await api(`/api/projects/${edit.project}/notes`,{method:'PUT',body:JSON.stringify({sha:edit.sha,localizations:edit.draft})});
 state.details.delete(cacheKey(edit.sha));await loadDetail(edit.sha);commit(edit.sha).notes=detail(edit.sha).notes;closeDialog();renderHistory();renderDetail();
 $(`[data-action="${edit.field==='changes'?'edit-release-notes':edit.field==='summary'?'edit-summary':'edit-version'}"]`)?.focus({preventScroll:true});
 notify('版本说明已保存。');
}
function comparisonSelection(){
 if(state.comparisonDraft)return state.comparisonDraft;
 const d=detail(state.selected),base=state.comparison?.base||d?.diff.base||state.commits.find(c=>c.sha!==state.selected)?.sha||state.selected;
 return state.comparisonDraft={base,target:state.selected};
}
function comparisonPicker(){
 const selected=comparisonSelection(),options=value=>state.commits.map(c=>`<option data-user-content value="${c.sha}" ${c.sha===value?'selected':''}>${esc(versionTitle(c))}</option>`).join('');
 return `<div class="comparison-picker"><label class="field">基准版本 A<select id="compare-base">${options(selected.base)}</select></label><button class="icon-button swap-button" data-action="swap-comparison" aria-label="交换两侧版本" title="交换两侧版本"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/></svg></button><label class="field">目标版本 B<select id="compare-target">${options(selected.target)}</select></label></div>`;
}
async function compareSelection(){const selected=comparisonSelection();await applyComparison(selected.base,selected.target);}
async function setDetailTab(tab){
 if(tab!=='compare'){++state.comparisonRequest;state.comparisonLoading=false;}
 state.tab=tab;renderDetail();$(`#tab-${tab}`)?.focus();
 if(tab==='compare'&&!state.comparisonLoading){const pair=comparisonSelection();if(!state.comparison||state.comparison.base!==pair.base||state.comparison.target!==pair.target||state.comparisonError)await compareSelection();}
 if(tab==='updates'){const id=state.selected;await ensureUpdateBaseline(detail(id));if(id===state.selected&&state.tab==='updates')renderDetail();}
}
async function changeComparison(target){
 const draft=comparisonSelection();
 if(target.id==='compare-base')draft.base=target.value;
 if(target.id==='compare-target')draft.target=target.value;
 await compareSelection();
}
function toggleBookmark(){
 const id=state.selected;if(!id)return;
 const added=!state.prefs.stars.includes(id);state.prefs.stars=added?[...state.prefs.stars,id]:state.prefs.stars.filter(x=>x!==id);
 const saved=savePrefs();if(state.filter==='starred'&&!added)settleFilter();else{renderHistory();renderDetail();}$('[data-action=star]')?.focus({preventScroll:true});
 if(saved)notify(added?'已收藏此版本。':'已取消收藏。');
}
function refreshSettingsManagement(){
 const container=$('#settings-management');if(!container||!$('#dialog').open)return;
 const opened=openDisclosures(container),focus=captureViewFocus(container),top=$('#dialog').scrollTop;
 container.innerHTML=managementContent();restoreDisclosures(container,opened);restoreViewFocus(focus,container);$('#dialog').scrollTop=top;
}
function settingsContent(){return `<section class="settings-section"><h3 data-user-content>${esc(state.project.name)}</h3><p class="project-path"><code>${esc(state.project.path)}</code></p><p class="snapshot-message">${contentText('继续在这个文件夹修改，想留下当前效果时保存一稿。','Keep editing this folder. Save a draft when you want to keep its current appearance.')}</p></section>${state.project.kind==='folder'?`<section class="settings-section"><div class="settings-line"><div><h3>${contentText('保存时的画面','Images when saving')}</h3><p>${contentText('默认尝试保存静态网页画面；已有选择会继续沿用。','Static website capture is attempted by default; existing preferences are respected.')}</p></div><button class="secondary-button" data-action="preview-preferences">${contentText('截图偏好','Screenshot preference')}</button></div></section>`:''}<section class="settings-section settings-language"><div class="settings-line"><h3>界面语言</h3><div class="segmented language-switch" role="group" aria-label="界面语言"><button data-user-content data-action="language" data-language="zh" aria-pressed="${uiLanguage==='zh'}">中文</button><button data-user-content data-action="language" data-language="en" aria-pressed="${uiLanguage==='en'}">English</button></div></div></section>${state.selected?`<details class="settings-section preview-settings" data-keep-open="preview-help"><summary>${contentText('画面没有保存成功？','Image not saved?')}</summary><p>${contentText('文件已经保存。可以检查这一稿的网页入口，或提供自己的截图。','The files are saved. Check this draft’s website entry or attach your own screenshot.')}</p><div class="preview-tools"><button class="secondary-button" data-action="saved-preview-capture" data-sha="${esc(state.selected)}">${contentText('检查网页并截图','Check website and capture')}</button><button class="text-button" data-action="manual">${contentText('提供截图','Attach screenshot')}</button></div><details><summary>${contentText('需要构建的网页','Websites requiring a build')}</summary><button class="text-button" data-action="recipe">${contentText('检查当前稿的运行配置','Review this draft’s run settings')}</button></details></details>`:''}<details class="settings-section" data-keep-open="project-activity"><summary>${contentText('任务与预览服务','Tasks and preview services')}</summary><div id="settings-management">${managementContent()}</div></details><details class="settings-section" data-keep-open="saved-drafts"><summary>${contentText('已保存稿件','Saved drafts')}</summary><button class="text-button" data-action="versions-manage">${contentText('管理历史版本','Manage saved versions')}</button>${presentationFields()}</details><section class="settings-section"><button class="text-button" data-action="confirm-stop-workbench">${contentText('停止 Reprise','Stop Reprise')}</button></section>`;}

function keepSelectedHistoryVisible(){requestAnimationFrame(()=>{const row=$(`.version-row[data-id="${state.selected}"]`),scroller=$('#history-scroll');if(!row)return;const top=row.offsetTop,bottom=top+row.offsetHeight;if(top<scroller.scrollTop)scroller.scrollTop=top;else if(bottom>scroller.scrollTop+scroller.clientHeight)scroller.scrollTop=bottom-scroller.clientHeight;});}

function comparisonSummary(diff){const c=diff.counts;if(uiLanguage==='en')return `${c.total||0} files differ between these revisions${c.added?`, ${c.added} added`:''}${c.modified?`, ${c.modified} modified`:''}${c.deleted?`, ${c.deleted} deleted`:''}${c.renamed?`, ${c.renamed} renamed`:''}.`;return `两个版本之间有 ${c.total||0} 个文件变化${c.added?`，新增 ${c.added} 个`:''}${c.modified?`，修改 ${c.modified} 个`:''}${c.deleted?`，删除 ${c.deleted} 个`:''}${c.renamed?`，重命名 ${c.renamed} 个`:''}。`;}
