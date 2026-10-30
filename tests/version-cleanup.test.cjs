/* Read-only imports still need a useful, explicit local removal path. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

function harness({local=true,environment=false,language='zh'}={}){
 const nodes={'#dialog':{open:true,classList:{add(){}}},'#dialog .dialog-body':{},'#dialog .dialog-footer':{}},requests=[];
 const state={project:{id:'project'},selected:'a'.repeat(40),dialogRequest:0};
 const context=vm.createContext({state,uiCopy:{},workspaceActions:{},document:{addEventListener(){}},
  $:selector=>nodes[selector],esc:v=>String(v),uiText:v=>v,contentBytes:v=>v+' B',
  contentText:(zh,en)=>language==='en'?en:zh,commit:sha=>({sha,subject:'中文名称'}),versionTitle:c=>c.subject,
  revisionProject:()=> 'project',captureDialogContext:()=>null,dialogParent:null,
  query:(p,v)=>p+'?'+new URLSearchParams(v),
  dialogShell(_title,body,footer){state.dialogRequest++;nodes['#dialog .dialog-body'].innerHTML=body;nodes['#dialog .dialog-footer'].innerHTML=footer;},
  api:async url=>{requests.push(url);return {sha:state.selected,source_history_retained:local,has_environment:environment,actions:{default:environment?'environment':'all',choices:[{id:'all',effect:local?'remove-local':'delete-saved',enabled:true},{id:'environment',effect:'clear-environment',enabled:environment}]}};}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/live-versions.js'),'utf8'),context);
 return {context,nodes,requests};
}

test('Git with no environment offers local removal and explains the disabled cleanup',async()=>{
 const {context,nodes,requests}=harness();
 await vm.runInContext('deleteVersionDialog()',context);
 const html=nodes['#dialog .dialog-body'].innerHTML;
 assert.match(html,/从 Reprise 移除此版本/);
 assert.match(html,/value="all" checked/);
 assert.doesNotMatch(html,/value="all" disabled/);
 assert.match(html,/value="environment" disabled/);
 assert.match(html,/没有可清理的受管环境/);
 assert.match(requests[0],/version-cleanup-options\?sha=a{40}/);
 assert.match(nodes['#dialog .dialog-footer'].innerHTML,/version-cleanup-review/);
});

test('a saved folder with an environment keeps both choices and defaults to environment',async()=>{
 const {context,nodes}=harness({local:false,environment:true});
 await vm.runInContext('deleteVersionDialog()',context);
 const html=nodes['#dialog .dialog-body'].innerHTML;
 assert.match(html,/删除全部内容 \[无法恢复\]/);
 assert.match(html,/value="environment" checked/);
 assert.doesNotMatch(html,/input[^>]*disabled/);
});

test('late capability responses cannot replace a closed dialog',async()=>{
 const {context,nodes}=harness();
 vm.runInContext('api=async()=>{state.dialogRequest++;return {source_history_retained:true,has_environment:false};}',context);
 await vm.runInContext('deleteVersionDialog()',context);
 assert.doesNotMatch(nodes['#dialog .dialog-body'].innerHTML,/version-delete-mode/);
});

test('English removal copy accurately retains source history',async()=>{
 const {context,nodes}=harness({language:'en'});
 await vm.runInContext('deleteVersionDialog()',context);
 assert.match(nodes['#dialog .dialog-body'].innerHTML,/source history retained/);
 assert.match(nodes['#dialog .dialog-body'].innerHTML,/Source Git commits, original archives/);
 assert.match(nodes['#dialog .dialog-body'].innerHTML,/No environment cleanup is needed/);
});

test('stop and review stops only this plan’s previews before requesting a fresh plan',async()=>{
 const {context}=harness();
 vm.runInContext(`state.cleanupTarget={project:'project',sha:'selected'};state.cleanupPlan={mode:'all',active_runtime_ids:['selected-preview','uncertain-preview']};
  globalThis.calls=[];api=async url=>{calls.push(url);};refreshWorkspace=async()=>calls.push('refresh');reviewVersionCleanup=async()=>calls.push('review');`,context);
 await vm.runInContext('stopVersionCleanupPreviews()',context);
 assert.deepEqual(Array.from(vm.runInContext('calls',context)),['/api/runtimes/selected-preview/stop','/api/runtimes/uncertain-preview/stop','refresh','review']);
 assert.equal(vm.runInContext('state.cleanupStopping',context),false);
});
