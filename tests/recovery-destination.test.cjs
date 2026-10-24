const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const code = fs.readFileSync(path.join(__dirname, '../web/live-workspace.js'), 'utf8');
const sha = 'a'.repeat(40), older = 'b'.repeat(40);
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}

function harness(api){
  const nodes = new Map(), shells = [], jobs = [], polls = [], origin = {id:'file-comparison-origin'};
  const element = extra => ({dataset:{},value:'',textContent:'',attrs:{},listeners:{},open:false,
    addEventListener(type,handler){this.listeners[type]=handler;},setAttribute(k,v){this.attrs[k]=v;},
    focus(){this.focused=true;},...extra});
  nodes.set('#dialog',element({open:false}));
  const context = vm.createContext({
    uiCopy:{},state:{project:{id:'project',kind:'folder'},selected:sha,dialogRequest:0},dialogParent:null,
    contentText:(zh,en)=>zh,uiText:value=>value,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    short:value=>String(value||'').slice(0,7),commit:value=>[sha,older].includes(value)?{sha:value,subject:'saved draft'}:null,
    versionTitle:c=>c.subject,revisionProject:()=> 'project',captureDialogContext:()=>origin,
    previewLanguageControls:()=>'',workspaceProjectIds:()=>new Set(['project']),
    $:selector=>nodes.get(selector),api,
    mergeWorkspaceJobs:items=>jobs.push(...items),pollWorkspaceJob:id=>polls.push(id),
    dialogShell(title,body,footer,wide,parent){
      context.state.dialogRequest++;context.dialogParent=parent;
      const dialog=nodes.get('#dialog');dialog.open=true;dialog.dataset={};
      shells.push({title,body,footer,parent});
      const value=body.match(/id="restore-path" value="([^"]*)"/)?.[1]||'';
      nodes.set('#restore-path',element({value}));
      nodes.set('#recovery-change-location',element());
      nodes.set('#recovery-destination-label',element());
      nodes.set('#recovery-destination-status',element());
      nodes.set('#dialog [data-action="save-restore"]',element({disabled:footer.includes('data-action="save-restore" disabled')}));
    }
  });
  vm.runInContext(code,context);
  return {context,nodes,shells,jobs,polls,origin,
    open:(paths=null,target={},options={})=>context.recoveryDialog(paths,target,options),
    input(value){const input=nodes.get('#restore-path');input.value=value;input.listeners.input();}}
}

test('opens immediately, then supplies a usable default behind collapsed Change location', async()=>{
  const wait=deferred(),calls=[];const h=harness(url=>{calls.push(url);return wait.promise;});
  h.open(['draft.txt']);
  assert.equal(h.shells.length,1);
  assert.equal(h.nodes.get('#dialog').open,true);
  assert.match(h.shells[0].body,/<details id="recovery-change-location"><summary>更改位置/);
  assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,true);
  assert.equal(h.nodes.get('#restore-path').focused,undefined);
  assert.equal(calls[0],`/api/projects/project/recovery-destination?sha=${sha}`);
  wait.resolve({to:'/safe/recovered-draft',display_label:'恢复的初稿'});await tick();
  assert.equal(h.nodes.get('#restore-path').value,'/safe/recovered-draft');
  assert.equal(h.nodes.get('#recovery-destination-label').textContent,'恢复的初稿');
  assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,false);
  assert.equal(h.context.state.recoveryTarget.to,'/safe/recovered-draft');
});

test('late suggestions never replace a manual path, including a deliberately cleared field',async()=>{
  for(const manual of ['/my/location','']){
    const wait=deferred(),h=harness(()=>wait.promise);h.open();h.input(manual);
    wait.resolve({to:'/automatic/location',display_label:'Automatic'});await tick();
    assert.equal(h.nodes.get('#restore-path').value,manual);
    assert.equal(h.context.state.recoveryTarget.manualDestination,true);
    assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,!manual);
  }
});

test('failed suggestion exposes manual fallback without losing exact recovery identity',async()=>{
  const calls=[],h=harness((url,options)=>{calls.push({url,options});return options?Promise.resolve({id:'restore-job'}):Promise.reject(Error('offline'));});
  h.open(['old/name.txt'],{project:'project',sha:older});await tick();
  assert.equal(h.nodes.get('#recovery-change-location').open,true);
  assert.equal(h.nodes.get('#recovery-destination-status').attrs.role,'alert');
  assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,true);
  h.input('/manual/new-folder');
  await h.context.startRecovery('restore');
  const body=JSON.parse(calls[1].options.body);
  assert.deepEqual(body,{sha:older,to:'/manual/new-folder',paths:['old/name.txt']});
  assert.equal(calls[1].url,'/api/projects/project/restore');
  assert.equal(h.jobs[0].id,'restore-job');
  assert.equal(h.context.state.recoveryParents.get('restore-job'),h.origin);
  assert.deepEqual(h.polls,['restore-job']);
});

test('obsolete suggestions cannot mutate a replacement dialog or revive a closed dialog',async()=>{
  const waits=[deferred(),deferred()];let i=0;const h=harness(()=>waits[i++].promise);
  h.open();h.open(null,{sha:older});
  waits[0].resolve({to:'/obsolete',display_label:'Obsolete'});await tick();
  assert.equal(h.nodes.get('#restore-path').value,'');
  assert.equal(h.context.state.recoveryTarget.sha,older);
  h.nodes.get('#dialog').open=false;h.context.state.dialogRequest++;
  waits[1].resolve({to:'/closed',display_label:'Closed'});await tick();
  assert.equal(h.nodes.get('#dialog').open,false);
  assert.equal(h.nodes.get('#restore-path').value,'');
});

test('retained destination skips another request and survives language reconstruction',async()=>{
  const calls=[],h=harness(url=>{calls.push(url);return Promise.resolve({});});
  h.open(null,{to:'/retained/draft',destinationLabel:'我的恢复稿',sha:older});
  assert.equal(calls.length,0);
  assert.equal(h.nodes.get('#recovery-destination-label').textContent,'我的恢复稿');
  const draft={...h.context.state.recoveryTarget};
  h.context.contentText=(zh,en)=>en;h.open(draft.paths,draft,{parent:h.origin});
  assert.equal(calls.length,0);
  assert.equal(h.nodes.get('#restore-path').value,'/retained/draft');
  assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,false);
  assert.match(h.shells.at(-1).body,/Change location/);
});

test('invalid suggestion stays disabled and export remains independent of destination',async()=>{
  const calls=[],h=harness((url,options)=>{calls.push({url,options});return Promise.resolve(options?{id:'export-job'}:{to:''});});
  h.open();await tick();
  assert.equal(h.nodes.get('#dialog [data-action="save-restore"]').disabled,true);
  assert.equal(h.nodes.get('#recovery-change-location').open,true);
  await h.context.startRecovery('export');
  assert.deepEqual(JSON.parse(calls[1].options.body),{sha,to:null,paths:null});
  assert.equal(calls[1].url,'/api/projects/project/export');
});
