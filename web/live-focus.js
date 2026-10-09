'use strict';
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
 const opened=new Set([...container.querySelectorAll('details[open][data-keep-open]')].map(d=>d.dataset.keepOpen));container.innerHTML=managementContent();
 for(const details of container.querySelectorAll('details[data-keep-open]'))if(opened.has(details.dataset.keepOpen))details.open=true;
}
function previewTools(){return '';}
function settingsContent(){return `<section class="settings-section"><h3 data-user-content>${esc(state.project.name)}</h3><p class="project-path"><code>${esc(state.project.path)}</code></p><p class="snapshot-message">Reprise 专注于启动时所在的仓库。</p></section><section class="settings-section settings-language"><div class="settings-line"><h3>界面语言</h3><div class="segmented language-switch" role="group" aria-label="界面语言"><button data-user-content data-action="language" data-language="zh" aria-pressed="${uiLanguage==='zh'}">中文</button><button data-user-content data-action="language" data-language="en" aria-pressed="${uiLanguage==='en'}">English</button></div></div></section><section class="settings-section"><div class="settings-line"><div><h3>AI</h3><p>${state.ai.enabled?'已启用':'未启用'}</p></div><button class="secondary-button" data-action="ai-settings">配置 AI</button></div></section>${state.selected?`<section class="settings-section"><div class="settings-line"><div><h3>运行与采集</h3><p data-user-content>${esc(versionTitle(commit(state.selected)))}</p></div><button class="secondary-button" data-action="recipe">配置当前版本</button></div><details class="preview-settings"><summary>添加预览资料</summary><div class="preview-tools"><button class="secondary-button" data-action="capture">生成此版本预览</button><button class="text-button" data-action="manual">导入截图 / 录屏</button></div></details></section>`:''}<div id="settings-management">${managementContent()}</div>${(state.historySources||[]).some(s=>s.kind==='archive')?`<details class="settings-section"><summary>历史资料</summary>${state.historySources.filter(s=>s.kind==='archive').map(s=>`<p class="snapshot-message"><span>历史存档</span> · <code>${esc(s.path)}</code></p>`).join('')}</details>`:''}`;}

function keepSelectedHistoryVisible(){requestAnimationFrame(()=>{const row=$(`.version-row[data-id="${state.selected}"]`),scroller=$('#history-scroll');if(!row)return;const top=row.offsetTop,bottom=top+row.offsetHeight;if(top<scroller.scrollTop)scroller.scrollTop=top;else if(bottom>scroller.scrollTop+scroller.clientHeight)scroller.scrollTop=bottom-scroller.clientHeight;});}

function comparisonSummary(diff){const c=diff.counts;if(uiLanguage==='en')return `${c.total||0} files differ between these revisions${c.added?`, ${c.added} added`:''}${c.modified?`, ${c.modified} modified`:''}${c.deleted?`, ${c.deleted} deleted`:''}${c.renamed?`, ${c.renamed} renamed`:''}.`;return `两个版本之间有 ${c.total||0} 个文件变化${c.added?`，新增 ${c.added} 个`:''}${c.modified?`，修改 ${c.modified} 个`:''}${c.deleted?`，删除 ${c.deleted} 个`:''}${c.renamed?`，重命名 ${c.renamed} 个`:''}。`;}
