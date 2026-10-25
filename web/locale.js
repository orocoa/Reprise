/* UI copy only. Git paths, commit messages, user names and command JSON stay literal. */
'use strict';
const uiCopy = {};

const uiTerms = {'同时采集比较基准':'Also capture baseline','次采集记录':'capture records','所选基准':'Selected baseline','父提交':'Parent commit','基准':'Baseline','目标':'Target','个独立副本':'independent copies','配置':'Settings','自动采集':'Automatic capture','手工导入':'Manual import','缺失':'Missing','诊断':'Diagnostic','通过':'Passed','未提交':'uncommitted','本地服务返回了无法读取的内容':'Local server returned unreadable content','请求失败':'Request failed','项':'changes','保存目标':'Save target','空树':'Empty tree','合并提交':'Merge commit','合并':'Merge','已提交':'Committed','分离 HEAD':'Detached HEAD','JSON 格式不正确':'Invalid JSON','配置已保存到版本':'Settings saved for revision','请选择比较版本':'Choose comparison revisions','未生成':'Not generated','已结束，资料已保留。':'ended; artifacts retained.','预览服务已停止，但状态刷新失败':'Preview stopped, but refreshing state failed','状态刷新失败':'State refresh failed','正在重新连接本地服务；原任务状态尚未确认。':'Reconnecting; the task state is not confirmed.'};
function preferredLanguage(explicit,saved,languages=[]){
 for(const value of [explicit,saved])if(['zh','en'].includes(value))return value;
 for(const value of languages){const code=String(value).toLowerCase().split('-')[0];if(['zh','en'].includes(code))return code;}
 return 'en';
}
let savedLanguage=null;
try {savedLanguage=localStorage.getItem('reprise.language');}catch(_){}
let uiLanguage=preferredLanguage(new URLSearchParams(location.search).get('lang'),savedLanguage,typeof navigator==='undefined'?[]:(navigator.languages||[navigator.language]));

const i18nMissing = new Set();
let uiDictionary;
const uiTextCache=new Map();
function compileUICopy(){
  const reverse=new Map();
  for(const [zh,en] of Object.entries(uiCopy))if(!reverse.has(en))reverse.set(en,zh);
  uiDictionary={reverse,english:new Set(Object.values(uiCopy)),entries:Object.entries({...uiCopy,...uiTerms}).sort((a,b)=>b[0].length-a[0].length)};
  uiTextCache.clear();
}
function englishDynamicText(text) {
  return text
 .replace(/(\d+) 条历史存档/g,'$1 archived records').replace(/(\d+) 个提交/g,'$1 commits').replace(/(\d+) 项未提交改动/g,'$1 uncommitted changes').replace(/(\d+) 个文件/g,'$1 files').replace(/(\d+) 个匹配 · 其余为关系节点/g,'$1 matches · other nodes show relationships').replace(/(\d+) 个运行或待确认的服务 · (\d+) 条保留记录/g,'$1 running or unconfirmed services · $2 retained records')
 .replace(/说明保存到本机版本资料，绑定 ([a-f0-9]+)。/g,'Notes are saved locally for revision $1.').replace(/复制资料并绑定 ([a-f0-9]+)。原文件会保留，来源标记为手工提供。/g,'Copy evidence for revision $1. Originals are retained and the source is marked as manual.').replace(/A \/ ([a-f0-9—]+) → B \/ ([a-f0-9]+) · 两侧完整文本（单侧上限 64 KB）/g,'A / $1 → B / $2 · complete texts (64 KB maximum per side)');
}
function uiText(value) {
  const text=uiLanguage==='en'?englishDynamicText(String(value)):String(value),trim=text.trim();
  if(!uiDictionary)compileUICopy();
  const key=uiLanguage+'|'+text;
  if(uiTextCache.has(key))return uiTextCache.get(key);
  let result=text;
  if(uiLanguage!=='en'){
    const original=uiDictionary.reverse.get(trim);
    result=original?text.replace(trim,original):text.replace(/^Web app \((.*)\)$/, '网页应用 ($1)').replace('references missing committed assets:', '引用的资源未包含在提交中：');
  }else if(uiCopy[trim])result=text.replace(trim,uiCopy[trim]);
  else if(!uiDictionary.english.has(trim)){
    for(const [zh,en] of uiDictionary.entries)result=result.replaceAll(zh,en);
    if(/[\u3400-\u9fff]/.test(result)&&i18nMissing.size<256)i18nMissing.add(text);
  }
  if(text.length<=2000){if(uiTextCache.size>=512)uiTextCache.delete(uiTextCache.keys().next().value);uiTextCache.set(key,result);}
  return result;
}
const originalTexts=new WeakMap(),originalAttrs=new WeakMap();
function localizeDOM(root=document.body) {
  document.documentElement.lang=uiLanguage==='en'?'en':'zh-CN';const description=document.querySelector('meta[name=description]');if(description)description.content=uiLanguage==='en'?'Reprise — save local webpage drafts, find them by picture, and recover a copy.':'Reprise — 保存本地网页稿，凭画面找回旧版，取出副本继续修改。';const name=document.querySelector('#project-name')?.textContent;const title=name&&name!=='Reprise'?name+' · '+(uiLanguage==='en'?'Versions':'版本'):(uiLanguage==='en'?'Reprise · Website drafts':'Reprise · 网页稿件');if(document.title!==title)document.title=title;
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes){
    if(node.parentElement?.closest('[data-user-content],code,pre,textarea,script,style,.commit-subject,.project-name,.ai-proposal,#quick-project option,#project-picker option,#main-picker option'))continue;
    const old=originalTexts.get(node);
    const original=old&&node.nodeValue===old.translated?old.original:node.nodeValue;
    const translated=uiText(original);
    if(node.nodeValue!==translated)node.nodeValue=translated;
    originalTexts.set(node,{original,translated});
  }
  const attributes='[placeholder],[title],[aria-label]';
  for(const element of [...(root.matches?.(attributes)?[root]:[]),...root.querySelectorAll(attributes)]){
    if(element.closest('[data-user-content]')||element.hasAttribute('data-user-label'))continue;
    const originals=originalAttrs.get(element)||{};
    for(const key of ['placeholder','title','aria-label'])if(element.hasAttribute(key)){
      const value=element.getAttribute(key),old=originals[key],original=old&&value===old.translated?old.original:value;
      const translated=uiText(original);if(value!==translated)element.setAttribute(key,translated);originals[key]={original,translated};
    }
    originalAttrs.set(element,originals);
  }
  document.querySelectorAll('[data-action=language]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.language===uiLanguage));
}
let localizeQueued=false;
const localizeRoots=new Set();
new MutationObserver(records=>{
  for(const record of records){
    if(record.type==='characterData'&&originalTexts.get(record.target)?.translated===record.target.nodeValue)continue;
    const root=record.type==='characterData'?record.target.parentElement:record.target;
    if(root?.isConnected)localizeRoots.add(root);
  }
  if(localizeRoots.size&&!localizeQueued){localizeQueued=true;queueMicrotask(()=>{
    const roots=[...localizeRoots];localizeRoots.clear();
    for(const root of roots)if(root.isConnected&&!roots.some(other=>other!==root&&other.contains(root)))localizeDOM(root);
    localizeQueued=false;
  });}
}).observe(document.body,{childList:true,subtree:true,characterData:true});
