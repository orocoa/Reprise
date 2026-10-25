const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const read=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
function context(overrides={}){
 const calls=[],state={project:{id:'a',kind:'folder',preview_preferences:{mode:'auto'}},commits:[{sha:'old'}],jobs:[],dialogRequest:1};
 const c=vm.createContext({state,Intl,Date,Set,workspaceActions:{},document:{addEventListener(){}},contentText:zh=>zh,
  uiLanguage:'zh',uiCopy:{},uiText:s=>s,esc:s=>String(s),$:()=>null,
  api:async(url,options)=>{calls.push([url,JSON.parse(options.body)]);return{id:'job',project_id:'a',operation:'snapshot',status:'queued'};},
  mergeWorkspaceJobs:jobs=>state.jobs.push(...jobs),pollWorkspaceJob:id=>calls.push(['poll',id]),notify(){},...overrides});
 vm.runInContext(read('live-content.js'),c);
 c.snapshotDialog=()=>calls.push(['dialog']);
 return {c,state,calls};
}
test('first use explains save scope; explicit project preferences enable direct saving',async()=>{
 for(const mode of [undefined,'remind','auto','none','manual']){
  const {c,state,calls}=context();state.project.preview_preferences={mode};
  await c.saveDraftFromToolbar();
  if(!mode||mode==='remind'){assert.deepEqual(calls,[['dialog']]);continue;}
  assert.equal(calls[0][0],'/api/projects/a/snapshot');
  assert.equal(calls[0][1].capture_static,false,'never override the stored capture choice');
  assert.match(calls[0][1].title,/留稿/);
 }
 const {c,state,calls}=context();state.commits=[];await c.saveDraftFromToolbar();assert.deepEqual(calls,[['dialog']]);
});
test('repeated clicks share one request and late completion cannot replace a newer dialog',async()=>{
 let resolve;const pending=new Promise(r=>resolve=r),requests=[];
 const {c,state}=context({api:(url,options)=>{requests.push(url);return pending;},dialogShell:()=>assert.fail('new navigation must remain')});
 state.snapshotTarget='a';
 const saving=c.saveCurrentDraft('Before edit',{fromDialog:true});
 // The original dialog is valid for the request, then navigation changes.
 // A second toolbar click must not enqueue another save while the API waits.
 await c.saveDraftFromToolbar();
 state.project={id:'b',kind:'folder'};state.dialogRequest++;
 resolve({id:'first',project_id:'a',operation:'snapshot',status:'queued'});await saving;
 assert.deepEqual(requests,['/api/projects/a/snapshot']);
});
test('rejected API calls release the quick-save guard for an explicit retry',async()=>{
 let n=0;const {c}=context({api:async()=>{n++;throw Error('offline');}});
 await assert.rejects(c.saveCurrentDraft('One'),/offline/);
 await assert.rejects(c.saveCurrentDraft('Two'),/offline/);assert.equal(n,2);
});
test('the first yes or no is sent as a persistent project choice before saving',async()=>{
 for(const mode of ['auto','none']){
  const {c,state,calls}=context({$:selector=>selector==='#initial-preview-choice'?{value:mode}:selector==='#dialog'?{open:false}:null});
  state.project.preview_preferences={};state.snapshotTarget='a';
  await c.saveCurrentDraft('First',{fromDialog:true});
  assert.equal(calls[0][1].capture_static,false);
  assert.deepEqual(calls[0][1].preview_preferences,mode==='auto'?{mode:'auto',pending_recipe:true}:{mode:'none'});
 }
});
test('an unanswered first question cannot save or start a capture',async()=>{
 const {c,state,calls}=context({$:selector=>selector==='#initial-preview-choice'?{value:''}:null});
 state.project.preview_preferences={};state.snapshotTarget='a';
 await assert.rejects(c.saveCurrentDraft('First',{fromDialog:true}),/选择/);
 assert.deepEqual(calls,[]);
});
test('remembering capture settings is offered only for a complete exact capture and approved recipe',()=>{
 const {c,state}=context();state.selected='a'.repeat(40);state.project.preview_preferences={};
 const d={commit:{sha:state.selected},recipe_approved:true,recipe:{adapter:'static-web'},evidence:[{sha:state.selected,status:'complete',source:'capture',items:[{url:'/a.png',media_type:'image/png'}]}]};
 assert.match(c.rememberCaptureControl(d),/remember-draft-preview/);
 for(const broken of [{...d,recipe_approved:false},{...d,evidence:[{...d.evidence[0],sha:'b'.repeat(40)}]},{...d,evidence:[{...d.evidence[0],status:'partial'}]},{...d,evidence:[{...d.evidence[0],source:'manual'}]}])assert.equal(c.rememberCaptureControl(broken),'');
 state.project.preview_preferences={mode:'none'};assert.equal(c.rememberCaptureControl(d),'');
});
function recoveryContext(language='zh'){
 const c=vm.createContext({workspaceActions:{},uiCopy:{},contentText:(zh,en)=>language==='en'?en:zh});
 vm.runInContext(read('live-workspace.js'),c);return c;
}
test('continuation uses the actual recovered folder and exact version, including quoted paths',()=>{
 const job={status:'complete',operation:'restore',result:{path:'/new/has "quotes"\nand 中文',sha:'a'.repeat(40),paths:null}};
 for(const language of ['zh','en']){
  const text=recoveryContext(language).recoveryContinuationText(job);
  assert.ok(text.includes(JSON.stringify(job.result.path)));assert.ok(text.includes(job.result.sha));
  assert.match(text,language==='zh'?/原项目保持原样/:/Keep the original project unchanged/);
 }
});
test('partial files, exports, failed jobs and missing identities never claim a whole editable webpage',()=>{
 const c=recoveryContext(),job={status:'complete',operation:'restore',result:{path:'/copy',sha:'a'.repeat(40)}};
 for(const other of [{...job,status:'failed'},{...job,operation:'export'},{...job,result:{...job.result,paths:['button.css']}},{...job,result:{...job.result,sha:'HEAD'}},{...job,result:{...job.result,path:''}}])assert.equal(c.recoveryContinuationText(other),'');
});
