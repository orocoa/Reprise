'use strict';
let aiBusy = false;
const aiStatus = ai => ({unconfigured:'未配置',disabled:'已关闭',unverified:'待测试',connected:'连接成功',error:'请求失败',unavailable:'配置不可读'}[ai?.status] || '未配置');
const aiDate = value => new Date(value).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});

function renderAIManagement() {
  const ai=model.state.ai;
  const label=ai?.provider==='codex'?(ai.codex_model||'Codex 默认配置'):ai?.model;
  $('#ai-management').innerHTML=`<article class="resource-row ai-resource"><div class="resource-main"><h3>AI 辅助</h3><p>${ai?.provider==='codex'?'Codex':'兼容 API'}</p></div><div class="resource-status">${aiStatus(ai)}</div><div class="resource-size" ${ai?.enabled&&(ai.provider==='codex'?ai.codex_model:ai.model)?'data-user-content':''} title="${esc(label||'')}">${esc(ai?.enabled?label:'本地模式')}</div><div class="resource-actions">${ai?.enabled?'<button data-ai-disable>关闭</button>':''}<button data-ai-settings>配置 ↗</button></div></article>`;
}
function aiEntry(v) {
  return model.state.ai?.enabled&&model.state.ai.configured?`<div class="ai-entry"><button class="text-button" data-ai-analyze="${v.id}" ${aiBusy?'disabled':''}>AI 分析 ↗</button></div>`:'';
}
function connectionDescription(ai) {
  const c=ai?.connection;
  if(ai?.error)return ai.error;
  if(!c)return ai?.configured?'配置已保存，尚未通过真实请求验证。':ai?.provider==='codex'?'选择 Codex 后可保存并测试连接。':'填写服务地址和模型后可测试连接。';
  if(c.status==='error')return c.message+' 原有功能仍可使用。';
  return `真实请求通过 · ${c.model_source==='configuration'?'配置模型 · ':''}${c.model} · ${c.latency_ms} ms · ${aiDate(c.at)}${ai.enabled?'':' · AI 当前已关闭'}`;
}
function settingsDialog() {
  const ai=model.state.ai||{};
  modal(`<h2>可选 AI</h2><form id="ai-settings-form"><div class="ai-connection" role="status"><strong id="ai-status">${aiStatus(ai)}</strong><p id="ai-connection-message">${esc(connectionDescription(ai))}</p></div><label class="ai-toggle"><input name="enabled" type="checkbox" ${ai.enabled?'checked':''}>启用 AI 辅助</label><label class="ai-field"><span>连接方式</span><select name="provider"><option value="api" ${ai.provider!=='codex'?'selected':''}>兼容 API</option><option value="codex" ${ai.provider==='codex'?'selected':''}>连接 Codex</option></select></label><div id="ai-codex-fields"><p class="ai-help">${ai.codex?.available?(ai.codex.logged_in?'本机 Codex 已登录':'本机 Codex 尚未登录'):'本机未检测到 Codex'}</p><label class="ai-field"><span>模型名称</span><input name="codex_model" value="${esc(ai.codex_model||'')}" placeholder="跟随 Codex 现有配置" maxlength="200" autocomplete="off"></label><p class="ai-help">复用本机 Codex 登录。模型留空时跟随现有配置。</p></div><div id="ai-api-fields"><label class="ai-field"><span>服务地址</span><input name="base_url" type="url" value="${esc(ai.base_url||'')}" placeholder="https://你的服务地址/v1" autocomplete="off" aria-describedby="ai-endpoint-help"></label><p class="ai-help" id="ai-endpoint-help">支持 Chat Completions 兼容接口，本机服务可使用 HTTP。</p><label class="ai-field"><span>模型名称</span><input name="model" value="${esc(ai.model||'')}" placeholder="填写服务提供的模型名称" maxlength="200" autocomplete="off"></label><label class="ai-field"><span>API 密钥</span><input name="api_key" type="password" value="" placeholder="${ai.has_key?'已保存，留空保留现有密钥':'填写密钥；无需鉴权的本机服务可留空'}" autocomplete="new-password" aria-describedby="ai-key-help"></label><p class="ai-help" id="ai-key-help">密钥仅存本机，不进入 Git。更换服务地址时请重新填写密钥。</p><label class="ai-toggle" id="ai-clear-key-row" ${ai.has_key?'':'hidden'}><input name="clear_key" type="checkbox">清除已保存的密钥</label></div><details class="ai-sharing"><summary>哪些内容会发送给 AI？</summary><p>测试连接仅发送一条测试消息。点击版本的“AI 分析”时，发送该版本与上一版编号、已核对说明和最多 80 条 Git 文件路径；不发送源码、图片或视频。结果作为建议单独保存。浏览和打开版本不会自动请求 AI。</p></details><p id="ai-settings-error" class="ai-error" role="alert" hidden></p><div class="modal-actions"><button class="subtle-button" type="button" data-ai-test ${aiBusy?'disabled':''}>保存并测试连接</button><button class="primary-button" type="submit">保存</button></div></form>`);
  updateAIProvider($('#ai-settings-form'));
}
function updateAIProvider(form) {
  const codex=form.elements.provider.value==='codex';
  form.querySelector('#ai-codex-fields').hidden=!codex;
  form.querySelector('#ai-api-fields').hidden=codex;
  for(const control of form.querySelectorAll('#ai-api-fields input'))control.disabled=codex;
  form.elements.codex_model.disabled=!codex;
  if(!aiBusy)form.querySelector('#ai-connection-message').textContent=codex?'保存后可测试本机 Codex 连接。':connectionDescription(model.state.ai);
}
function acceptAIState(ai) {
  model.state.ai=ai;
  renderAIManagement();renderDetail();
}
function updateSettingsStatus(form, ai) {
  if(!form.isConnected)return;
  form.querySelector('#ai-status').textContent=aiStatus(ai);
  form.querySelector('#ai-connection-message').textContent=connectionDescription(ai);
  form.elements.api_key.value='';
  form.elements.api_key.placeholder=ai.has_key?'已保存，留空保留现有密钥':'填写密钥；无需鉴权的本机服务可留空';
  form.elements.clear_key.checked=false;
  form.querySelector('#ai-clear-key-row').hidden=!ai.has_key;
}
async function saveAISettings(form, test=false) {
  if(form.dataset.saving||aiBusy)return;
  if(!form.reportValidity())return;
  const body={enabled:form.elements.enabled.checked,provider:form.elements.provider.value,codex_model:form.elements.codex_model.value.trim()};
  if(body.provider==='api')Object.assign(body,{base_url:form.elements.base_url.value.trim(),model:form.elements.model.value.trim(),api_key:form.elements.api_key.value.trim(),clear_key:form.elements.clear_key.checked});
  const error=form.querySelector('#ai-settings-error');
  error.hidden=true;form.dataset.saving='true';
  aiBusy=true;for(const control of form.elements)control.disabled=true;
  try {
    const saved=await api('/api/ai/settings',body);
    acceptAIState(saved.ai);updateSettingsStatus(form,saved.ai);
    if(test){
      form.querySelector('#ai-status').textContent='正在测试…';
      form.querySelector('#ai-connection-message').textContent='正在发送真实模型请求…';
      const result=await api('/api/ai/test',{});
      acceptAIState(result.ai);updateSettingsStatus(form,result.ai);
      if(!result.ok){error.textContent=result.error;error.hidden=false;}
    }else toast('AI 配置已保存。');
  } catch(problem){
    if(form.isConnected){error.textContent=problem.message;error.hidden=false;form.querySelector('#ai-status').textContent='操作未完成';form.querySelector('#ai-connection-message').textContent='请检查配置后重试。';}
    else toast(problem.message,true);
  } finally {
    aiBusy=false;delete form.dataset.saving;for(const control of form.elements)control.disabled=false;updateAIProvider(form);renderDetail();
  }
}
async function disableAI() {
  const ai=model.state.ai;
  if(!ai)return;
  try {
    const data=await api('/api/ai/settings',{enabled:false,base_url:ai.base_url,model:ai.model});
    acceptAIState(data.ai);toast('AI 已关闭，继续使用已有版本说明。');
  }catch(error){toast(error.message,true);}
}
async function analyzeVersion(id) {
  if(aiBusy)return;
  const v=version(id);if(!v)return;
  aiBusy=true;renderDetail();
  modal(`<h2><span>AI 分析</span> · ${versionName(v)}</h2><div data-analysis-version="${id}"><p role="status">正在分析相对上一版的变化…</p></div>`);
  const container=$('#modal-body [data-analysis-version]');
  try {
    const result=await api('/api/ai/analyze',{version:id});
    acceptAIState(result.ai);
    if(!container.isConnected)return;
    if(result.source!=='ai'){
      container.innerHTML=`<p class="ai-provenance">已有说明 · 本次未采用 AI 结果</p><p class="ai-error">${esc(result.error)}</p><p class="ai-result-summary">${esc(result.summary)}</p>`;
      return;
    }
    const en=result.localizations.en;
    const labels={image:'图片',video:'视频',text:'文字 / 文件',none:'需补充依据'};
    container.innerHTML=`<p class="ai-provenance"><span>AI 辅助</span> · <span data-verbatim>${esc(result.model)}</span> · <span>${result.cached?'已保存的结果':'本次模型请求'}</span><br><span data-verbatim>${esc(result.provider)}</span> · ${esc(aiDate(result.generated_at))}</p><p><span>建议名称</span> · ${localizedText(result.title,en.title)}</p><p class="ai-result-summary">${localizedText(result.summary,en.summary)}</p>${result.changes.length?`<ul class="ai-result-list">${result.changes.map((c,i)=>`<li>${localizedText(c,en.changes[i])}</li>`).join('')}</ul>`:''}${result.evidence.length?`<details class="ai-suggestions"><summary>预览建议 · 待核对</summary><ul>${result.evidence.map((e,i)=>`<li><strong>${labels[e.type]}</strong> · ${localizedText(e.reason,en.evidence[i].reason)}${e.paths.length?`<div><code>${e.paths.map(esc).join('<br>')}</code></div>`:''}</li>`).join('')}</ul></details>`:''}<p class="ai-help">基于已有说明与文件清单；未运行或验证页面。原有说明与真实媒体继续保留。</p>`;
    wrapNames(container);
  } catch(error){if(container.isConnected)container.innerHTML=`<p class="ai-error">${esc(error.message)}</p><p class="ai-result-summary">${esc(v.summary)}</p>`;}
  finally {aiBusy=false;renderDetail();}
}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.hasAttribute('data-ai-settings'))settingsDialog();
  if(button.hasAttribute('data-ai-test'))saveAISettings(button.closest('form'),true);
  if(button.hasAttribute('data-ai-disable'))disableAI();
  if(button.dataset.aiAnalyze)analyzeVersion(button.dataset.aiAnalyze);
});
document.addEventListener('submit',event=>{if(event.target.id==='ai-settings-form'){event.preventDefault();saveAISettings(event.target);}});

document.addEventListener('change',event=>{if(event.target.name==='provider'&&event.target.closest('#ai-settings-form'))updateAIProvider(event.target.form);});
