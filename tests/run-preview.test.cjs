/* A run click must expose its result without launching duplicate previews. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const web=path.resolve(__dirname,'../web');
const sha='a'.repeat(40);
const runtime={id:'runtime',project_id:'project',sha,recipe_hash:'saved-recipe',status:'running',running:true,url:'http://127.0.0.1:45678/'};

function harness({ready=false,approved=true,postResponse=null,pollResponse=null}={}){
 const dialog={open:false,dataset:{},classList:{add(){},contains(){return false;}}},messages=[],requests=[],dialogs=[];
 const state={project:{id:'project'},selected:sha,dialogRequest:0,tab:'updates',jobs:[],runtimes:ready?[{...runtime}]:[],details:new Map(),comparison:null};
 const queued={id:'job',project_id:'project',operation:'run',status:'queued',cancellable:true,request:{sha}};
 const completed={...queued,status:'complete',result:{...runtime},finished_at:'now'};
 const detail={commit:{sha},actions:{schema:1,project_id:'project',sha,preview:{mode:approved?'run':'configure',media:null}},recipe_approved:approved,recipe_hash:'saved-recipe',diff:{base:null}};
 const context=vm.createContext({state,URL,Set,Map,Promise,setTimeout,clearTimeout,
  transferOperations:[],dialogParent:null,
  $:selector=>selector==='#dialog'?dialog:selector==='#dialog-status'?{}:null,
  detail:()=>detail,revisionProject:()=>state.project.id,
  runtimeInfo:r=>({running:r.status==='running'&&r.running}),
  contentText:zh=>zh,esc:value=>String(value),commit:id=>({sha:id,subject:'Saved version'}),versionTitle:c=>c.subject,
  dialogShell(title,body,footer){state.dialogRequest++;dialog.open=true;dialog.dataset={};dialogs.push({title,body,footer});},
  recipeDialog(){messages.push('recipe approval');},notify:message=>messages.push(message),
  refreshSettingsManagement(){},renderDetail(){},workspaceProjectIds:()=>new Set([state.project.id]),
  refreshWorkspace:async()=>{state.runtimes=[{...runtime}];},loadDetail:async()=>{},ensureUpdateBaseline:async()=>{},
  api:async(url,options)=>{requests.push({url,method:options?.method||'GET'});return options?.method==='POST'?(postResponse?await postResponse:queued):(pollResponse?await pollResponse:completed);},
 });
 vm.runInContext(fs.readFileSync(path.join(web,'live-run-preview.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(web,'live-features.js'),'utf8').split('// Named handlers')[0],context);
 vm.runInContext("refreshSettingsManagement=()=>{};recipeDialog=()=>notify('recipe approval');",context);
 context.refreshWorkspace=async()=>{state.runtimes=[{...runtime}];};
 return {context,state,dialog,dialogs,messages,requests,detail,queued,completed};
}

test('running exact-version preview opens immediately without any new run request',async()=>{
 const h=harness({ready:true});await h.context.startWorkspaceAction('run');
 assert.equal(h.requests.length,0);assert.match(h.dialogs.at(-1).body,/<iframe/);
 assert.match(h.dialogs.at(-1).body,/http:\/\/127\.0\.0\.1:45678\//);
 assert.match(h.dialogs.at(-1).footer,/返回版本/);
});

test('completed queued run replaces its progress dialog with the interactive page',async()=>{
 const h=harness();await h.context.startWorkspaceAction('run');await new Promise(setImmediate);
 assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
 assert.match(h.dialogs[0].body,/正在准备/);assert.match(h.dialogs.at(-1).body,/<iframe/,JSON.stringify(h.messages));
});

test('repeat clicks while submission is pending create only one run job',async()=>{
 let resolve;const pending=new Promise(done=>{resolve=done;});
 const h=harness({postResponse:pending});const first=h.context.startWorkspaceAction('run');
 const second=h.context.startWorkspaceAction('run');
 assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
 resolve(h.queued);await Promise.all([first,second]);await new Promise(setImmediate);
});

test('a running preview with a different saved recipe is not silently reused',async()=>{
 const h=harness({ready:true});h.state.runtimes[0].recipe_hash='old-recipe';
 await h.context.startWorkspaceAction('run');await new Promise(setImmediate);
 assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});

test('unsaved recipes are still reviewed before any execution or preview reuse',async()=>{
 const h=harness({ready:true,approved:false});await h.context.startWorkspaceAction('run');
 assert.equal(h.requests.length,0);assert.deepEqual(h.messages,['recipe approval']);
 assert.equal(h.dialogs.length,0);
});

test('closing progress or selecting another project prevents a late preview popup',async()=>{
 for(const action of ['close','project']){
  let resolve;const pending=new Promise(done=>{resolve=done;});const h=harness({pollResponse:pending});
  await h.context.startWorkspaceAction('run');
  if(action==='close')h.dialog.open=false;else h.state.project={id:'other'};
  const count=h.dialogs.length;resolve(h.completed);await new Promise(setImmediate);
  assert.equal(h.dialogs.length,count,action);
 }
});

test('failed startup displays its error in the progress dialog',async()=>{
 const failed={id:'job',project_id:'project',operation:'run',status:'failed',request:{sha},error:'The start command failed'};
 const h=harness({pollResponse:Promise.resolve(failed)});await h.context.startWorkspaceAction('run');await new Promise(setImmediate);
 assert.match(h.dialogs.at(-1).body,/role="alert"/,JSON.stringify(h.messages));assert.match(h.dialogs.at(-1).body,/The start command failed/);
 assert.doesNotMatch(h.dialogs.at(-1).body,/<iframe/);
});

test('preview URLs cannot escape loopback or contain credentials',()=>{
 const h=harness();
 for(const url of ['https://example.com/','http://127.0.0.1/','http://user@127.0.0.1:45678/','file:///tmp/index.html']){
  assert.equal(h.context.openRuntimePreview({...runtime,url}),false,url);
 }
 assert.equal(h.dialogs.length,0);
});

test('manual archives open their exact saved image without submitting a run or asking for a recipe',async()=>{
 const h=harness();Object.assign(h.detail,{recipe:{adapter:'manual'},detection:{kind:'archive'}});
 h.detail.actions.preview={mode:'saved',media:{record:'saved-picture',index:0}};
 const opened=[];
 h.context.mediaItems=()=>[{sha,record:'saved-picture',index:0,url:'/exact.png',kind:'image'}];
 h.context.visualEvidence=()=>true;h.context.showMedia=(record,index)=>opened.push({record,index});
 await h.context.startWorkspaceAction('run');
 assert.deepEqual(opened,[{record:'saved-picture',index:0}]);
 assert.equal(h.requests.length,0);assert.deepEqual(h.messages,[]);
});

test('an archive without a runtime recipe or picture explains recovery instead of requesting a run',async()=>{
 const h=harness({approved:false});Object.assign(h.detail,{recipe:null,detection:{kind:'archive'}});
 h.detail.actions.preview={mode:'recover',media:null};
 h.context.mediaItems=()=>[];h.context.visualEvidence=()=>false;
 await h.context.startWorkspaceAction('run');
 assert.equal(h.requests.length,0);assert.deepEqual(h.messages,[]);
 assert.match(h.dialogs.at(-1).body,/尚无运行入口或可用的已保存画面/);
 assert.match(h.dialogs.at(-1).footer,/data-action="recovery"/);
});

test('a reviewed runnable archive still uses its saved runtime recipe',async()=>{
 const h=harness();Object.assign(h.detail,{recipe:{adapter:'static-web'},detection:{kind:'archive'}});
 await h.context.startWorkspaceAction('run');await new Promise(setImmediate);
 assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});

test('an unrelated dialog opened during startup keeps ownership when the old run completes',async()=>{
 let resolve;const response=new Promise(done=>{resolve=done;});const h=harness({pollResponse:response});
 await h.context.startWorkspaceAction('run');
 h.context.dialogShell('Settings','Settings content','');const count=h.dialogs.length;
 resolve(h.completed);await new Promise(setImmediate);
 assert.equal(h.dialogs.length,count);assert.equal(h.dialogs.at(-1).body,'Settings content');
});
test('closing and reopening a pending submission adopts it without sending another request',async()=>{
 let resolve;const response=new Promise(done=>{resolve=done;});const h=harness({postResponse:response});
 const first=h.context.startWorkspaceAction('run');h.dialog.open=false;h.state.dialogRequest++;
 const second=h.context.startWorkspaceAction('run');assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
 resolve(h.queued);await Promise.all([first,second]);await new Promise(setImmediate);
 assert.match(h.dialogs.at(-1).body,/<iframe/);
});
test('a changed recipe during startup cannot open the old runtime',async()=>{
 let resolve;const response=new Promise(done=>{resolve=done;});const h=harness({pollResponse:response});
 await h.context.startWorkspaceAction('run');h.detail.recipe_hash='newly-approved-recipe';
 const count=h.dialogs.length;resolve(h.completed);await new Promise(setImmediate);
 assert.equal(h.dialogs.length,count);
});
test('a late submission failure cannot write into another dialog',async()=>{
 let reject;const response=new Promise((_,fail)=>{reject=fail;});const h=harness({postResponse:response});
 const pending=h.context.startWorkspaceAction('run');h.context.dialogShell('Settings','Settings content','');
 reject(Error('Network failed'));await pending;
 assert.equal(h.dialogs.at(-1).body,'Settings content');assert.deepEqual(h.messages,['Network failed']);
});
