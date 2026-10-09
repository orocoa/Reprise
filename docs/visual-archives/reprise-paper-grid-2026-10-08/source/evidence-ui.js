'use strict';
if(typeof uiEnglish==='object')Object.assign(uiEnglish,{'变化':'Changes','查看变化 ↗':'View changes ↗','前后画面':'Before / after','操作录屏':'Interaction recordings','文件依据':'File changes','验证范围':'Verification scope','查看内容':'View content','变化依据':'Change evidence','选择变化内容':'Choose evidence','页面一致 · 共享上一版画面':'Same page · shared previous capture','起点 · 无上一版':'Starting point · no previous version','正在读取变化依据…':'Loading change evidence…'});
if(typeof uiEnglish==='object')Object.assign(uiEnglish,{'本版未修改页面，沿用上一版预览。具体变化见文件依据。':'This version keeps the previous page. See file changes for the update.','查看实际页面改动 ↗':'View the actual page update ↗'});
if(typeof uiEnglish==='object')Object.assign(uiEnglish,{'本版页面未修改，预览与上一版一致；具体变化见文件依据。':'The page is unchanged from the previous version; see file changes for the update.','相同滚动位置：旧版入口尚未完全展开，新版已展开。完整过程见操作录屏。':'At the same scroll position, the previous entry is partially revealed and the new entry is fully revealed. See the recording for the complete interaction.','展示同一页面、语言和视口的已保存画面。截图反映采集时的状态，完整交互过程见操作录屏。':'Saved views of the same page, language and viewport. Images show the captured state; recordings show the complete interaction.','展示同一作品位置、语言和视口的已保存画面。截图反映采集时的状态，完整交互过程见操作录屏。':'Saved views of the same project position, language and viewport. Images show the captured state; recordings show the complete interaction.'});
const evidenceCache = new Map();
let evidenceRequest = 0;
function evidenceEntry(v,scope='detail') {
  if(!v.preview_architecture)return '';
  let changed=version(v.preview_architecture?.shared_from);const seen=new Set();
  while(changed?.preview_architecture?.shared_from&&!seen.has(changed.id)){seen.add(changed.id);changed=version(changed.preview_architecture.shared_from);}
  const content=`<button class="text-button" data-evidence="${v.id}">查看变化 ↗</button>${v.preview_architecture.shared_from?'<span>本版未修改页面，沿用上一版预览。具体变化见文件依据。</span>':''}${changed?`${inlineVersion(changed.id,'查看实际页面改动',scope+'-actual')}`:''}${!v.base?'<span>起点 · 无上一版</span>':''}`;
  return content?`<div class="evidence-entry">${content}</div>`:'';
}
function evidenceMedia(p,label) {
  if(!p)return '<p class="evidence-unavailable">上一版未包含此页面或查看状态，文件依据中保留了新增记录。</p>';
  if(p.status!=='captured')return `<p class="evidence-unavailable">${esc(p.note||'这处预览未能采集，保留文件依据供核对。')}</p>`;
  return `<figure>${previewMedia(p,label,true)}<figcaption>${localizedText(p.caption,contentEnglish[p.caption])}${p.kind==='asset'||!p.viewport?'':` · 视口 ${p.viewport.width}×${p.viewport.height}`}${p.device_scale_factor>1?' · '+p.device_scale_factor+'× 采集':''}${p.duration?' · '+p.duration.toFixed(1)+' 秒':''}</figcaption></figure>`;
}
function renderEvidence(data,group,index=0) {
  const v=version(data.id),base=version(data.base),container=$('#modal-body [data-evidence-content]');if(!container)return;
  const groups=[['pairs','前后画面',data.pairs.length],['motions','操作录屏',data.motions.length],['files','文件依据',data.files.length]];
  const rows=group==='files'?[]:data[group],row=rows[index];
  container.innerHTML=`<div class="evidence-tabs" role="group" aria-label="变化依据">${groups.map(([key,label])=>`<button class="${key===group?'active':''}" data-evidence-group="${key}" aria-pressed="${key===group}">${label}</button>`).join('')}</div><p class="evidence-context">${base?'比较：'+esc(base.title)+' → '+esc(v.title):'此系列起点，没有上一版。'}</p>${data.shared_from?'<p class="evidence-context">页面内容一致，默认画面明确沿用上一版；本次变化见文件依据。</p>':''}${group==='files'?`<p>${esc(data.file_note)}</p><ul class="evidence-files">${data.files.map(f=>`<li><span>${({A:'新增',M:'修改',D:'删除'})[f.status]||esc(f.status)}</span><code>${esc(f.path)}</code></li>`).join('')}</ul>${data.patch?`<details class="evidence-patch"><summary>展开相关文件差异${data.patch_truncated?'（节选）':''}</summary><pre><code>${esc(data.patch)}</code></pre></details>`:''}`:`${rows.length>1?`<label class="evidence-selector">查看内容 <select data-evidence-select aria-label="选择变化内容">${rows.map((r,i)=>`<option value="${i}" ${i===index?'selected':''}>${esc(r.label)}</option>`).join('')}</select></label>`:''}${row?`<div class="evidence-pair">${[[base,row.before,'上一版'],[v,row.after,'此版本']].map(([item,p,label])=>`<article><h3>${label}${item?' · '+esc(item.title):''}</h3>${evidenceMedia(p,label)}</article>`).join('')}</div>`:`<p class="evidence-unavailable">${group==='motions'?'此版本没有已保存的操作录屏。可切换到前后画面或文件依据。':'此版本没有可比较的前后画面。可切换到操作录屏或文件依据。'}</p>`}`}${data.limitations.length?`<details class="evidence-limitations"><summary>验证范围</summary><ul>${data.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}`;
  container.querySelector(`[data-evidence-group="${group}"]`)?.focus({preventScroll:true});
  container.dataset.group=group;container.dataset.version=data.id;wrapNames(container);
  if(group!=='files'&&row){container.querySelector('.evidence-pair').insertAdjacentHTML('beforebegin',`<p class="evidence-context">${esc(row.label)}</p>`);}
}
async function showEvidence(id) {
  const request=++evidenceRequest,v=version(id);if(!v)return;
  modal(`<h2><span>变化</span> · <span data-user-content>${esc(v.title)}</span></h2><div data-evidence-content><p role="status">正在读取变化依据…</p></div>`,true);
  const container=$('#modal-body [data-evidence-content]');
  try{
    const data=evidenceCache.get(id)||await api('/api/evidence?version='+encodeURIComponent(id));evidenceCache.set(id,data);
    if(request!==evidenceRequest||!container.isConnected)return;
    renderEvidence(data,data.motions.length?'motions':data.pairs.length?'pairs':'files');
  }catch(error){if(container.isConnected)container.innerHTML=`<p role="alert">${esc(error.message)}</p>`;}
}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.evidence)showEvidence(button.dataset.evidence);
  if(button.dataset.evidenceGroup){const c=button.closest('[data-evidence-content]');renderEvidence(evidenceCache.get(c.dataset.version),button.dataset.evidenceGroup);}
});
document.addEventListener('change',event=>{
  if(event.target.hasAttribute('data-evidence-select')){const c=event.target.closest('[data-evidence-content]');renderEvidence(evidenceCache.get(c.dataset.version),c.dataset.group,Number(event.target.value));}
});
