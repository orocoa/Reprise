/* Keep full details bounded without losing file search or comparison inputs. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const web=path.resolve(__dirname,'../web');

test('uncached file search loads only diff paths, including old rename paths',async()=>{
 const context=vm.createContext({location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 const result=await vm.runInContext(`(async()=>{
  globalThis.uiLanguage='en';globalThis.revisionProject=()=> 'project';
  state.project={id:'project'};state.commits=[{sha:'a'},{sha:'b'}];
  renderHistory=()=>{};settleFilter=()=>{};updateSearchProgress=()=>{};
  const calls=[];api=async (url,options)=>{calls.push(url);if(!url.endsWith('/search-index'))throw Error('Search must not load full version details');return {paths:Object.fromEntries(JSON.parse(options.body).shas.map(sha=>[sha,['new.txt','old.txt']]))};};
  await searchAll();
  return {calls,index:[...state.searchIndex.values()],details:state.details.size,searching:state.searching};
 })()`,context);
 assert.equal(result.calls.length,1);
 assert.equal(result.details,0);
 assert.equal(result.searching,false);
 assert.deepEqual(Array.from(result.index[0]),['new.txt','old.txt']);
});

test('file index batches are bounded and keep archive sources separate',async()=>{
 const context=vm.createContext({location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 const result=await vm.runInContext(`(async()=>{
  state.project={id:'current'};state.commits=Array.from({length:257},(_,i)=>({sha:i.toString(16).padStart(40,'0')}));
  globalThis.revisionProject=id=>parseInt(id,16)<200?'current':'archive';renderHistory=()=>{};settleFilter=()=>{};updateSearchProgress=()=>{};
  const calls=[];api=async (url,options)=>{const shas=JSON.parse(options.body).shas;calls.push({url,shas});return {paths:Object.fromEntries(shas.map(sha=>[sha,['name.txt']]))};};
  await searchAll();return {calls,size:state.searchIndex.size};
 })()`,context);
 assert.equal(result.size,257);assert.equal(result.calls.length,3);
 for(const call of result.calls){
  assert.ok(call.shas.length<=128);
  assert.ok(Array.from(call.shas).every(sha=>call.url.includes(parseInt(sha,16)<200?'/current/':'/archive/')));
 }
});

test('a late batch cannot populate a different project file index',async()=>{
 let resolve;const response=new Promise(done=>{resolve=done;});
 const context=vm.createContext({location:{hash:''},URLSearchParams,response});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 const pending=vm.runInContext(`state.project={id:'a'};state.commits=[{sha:'a'.repeat(40)}];globalThis.revisionProject=()=> 'a';renderHistory=()=>{};settleFilter=()=>{};updateSearchProgress=()=>{};api=()=>response;searchAll();`,context);
 vm.runInContext(`state.project={id:'b'};state.searchIndex=new Map();state.searching=false;++searchRequest;`,context);
 resolve({paths:{['a'.repeat(40)]:['from-a.txt']}});await pending;
 assert.equal(vm.runInContext('state.searchIndex.size',context),0);
});

test('clearing a query cancels its pending full-history search',()=>{
 const cancelled=[],input={value:'old query'},context=vm.createContext({location:{hash:''},URLSearchParams,document:{querySelector:()=>input},clearTimeout:id=>cancelled.push(id)});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 const result=vm.runInContext(`(()=>{searchTimer=42;state.query='old query';state.searching=true;settleFilter=()=>{};coreActions['clear-search']();return {query:state.query,searching:state.searching};})()`,context);
 assert.deepEqual(cancelled,[42]);
 assert.equal(result.query,'');
 assert.equal(result.searching,false);
 assert.equal(input.value,'');
});

test('refresh restores the same task, runtime or file and never steals outside focus',()=>{
 for(const [attribute,action] of [['data-job','cancel-job'],['data-runtime','stop-runtime'],['data-path','file']]){
  const document={body:{},activeElement:null},context=vm.createContext({document});
  vm.runInContext(fs.readFileSync(path.join(web,'live-focus.js'),'utf8'),context);
  const element=value=>({isConnected:true,tagName:'BUTTON',attrs:{'data-action':action,[attribute]:value},
   hasAttribute(name){return name in this.attrs;},getAttribute(name){return this.attrs[name]??null;},
   focus(){document.activeElement=this;}});
  const old=element('second'),first=element('first'),second=element('second');
  context.root={contains:el=>el===old,querySelectorAll:()=>[first,second]};
  document.activeElement=old;
  vm.runInContext('globalThis.saved=captureViewFocus(root)',context);
  old.isConnected=false;document.activeElement=document.body;
  vm.runInContext('restoreViewFocus(saved,root)',context);
  assert.equal(document.activeElement,second,attribute);
  const search={};document.activeElement=search;
  vm.runInContext('restoreViewFocus(saved,root)',context);
  assert.equal(document.activeElement,search,'Late updates must not take focus back');
 }
});

test('detail eviction retains selected/baseline revisions and renamed-file search',async()=>{
 const context=vm.createContext({location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 vm.runInContext(fs.readFileSync(path.join(web,'live-focus.js'),'utf8'),context);
 const result=await vm.runInContext(`(async()=>{
  globalThis.uiLanguage='en';
  state.project={id:'fixture'};
  state.commits=Array.from({length:150},(_,n)=>({sha:n.toString(16).padStart(40,'0'),subject:'revision '+n,author:'test',refs:[],parents:[]}));
  state.commitIndex=new Map(state.commits.map(c=>[c.sha,c]));
  const ids=state.commits.map(c=>c.sha);
  state.selected=ids[0];state.comparisonDraft={base:ids[1],target:ids[2]};
  let calls=0;
  api=async url=>{calls++;const sha=url.split('/').pop(),index=ids.indexOf(sha);return {commit:commit(sha),diff:{base:ids[3],files:[{path:'new-'+index+'.txt',old_path:'old-'+index+'.txt'}]},evidence:[],recipe:{retained:'x'.repeat(10000)}};};
  for(const id of ids)await loadDetail(id);
  state.query='old-5.txt';
  const retainedSearch=match(commit(ids[5])),evicted=!detail(ids[5]);
  const pinned=[0,1,2,3].every(n=>detail(ids[n]));
  const size=state.details.size;
  renderHistory=()=>{};settleFilter=()=>{};updateSearchProgress=()=>{};
  const before=calls;await searchAll();const repeatedSearchCalls=calls-before;
  await loadDetail(ids[5]);
  return {size,pinned,retainedSearch,evicted,repeatedSearchCalls,reloaded:!!detail(ids[5])};
 })()`,context);
 assert.equal(result.size,128);
 assert.equal(result.pinned,true);
 assert.equal(result.evicted,true);
 assert.equal(result.retainedSearch,true);
 assert.equal(result.repeatedSearchCalls,0);
 assert.equal(result.reloaded,true);
});

test('recent jobs stay bounded while active and newly completed old jobs remain visible',()=>{
 const context=vm.createContext({});
 vm.runInContext('const state={jobs:[]};',context);
 vm.runInContext(fs.readFileSync(path.join(web,'live-features.js'),'utf8'),context);
 const result=vm.runInContext(`(()=>{
  state.jobs=[{id:'active',status:'running',created_at:'2000'},
   {id:'old-long-job',status:'running',created_at:'2000',dismissed:true}];
  const history=Array.from({length:50},(_,n)=>({id:String(n),status:'complete',created_at:String(2100+n)}));
  mergeWorkspaceJobs([...history,{id:'old-long-job',status:'complete',created_at:'2000',finished_at:'9999'}]);
  return {size:state.jobs.length,active:state.jobs.some(j=>j.id==='active'),old:state.jobs.find(j=>j.id==='old-long-job')};
 })()`,context);
 assert.equal(result.size,31);
 assert.equal(result.active,true);
 assert.equal(result.old.status,'complete');
 assert.equal(result.old.dismissed,true);
});

test('live startup processes cannot be opened or stopped as ready previews',()=>{
 const context=vm.createContext({location:{hash:''},URLSearchParams,
  document:{addEventListener(){}},window:{addEventListener(){}}});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 for(const name of ['live-focus.js','live-parity.js','live-features.js'])vm.runInContext(fs.readFileSync(path.join(web,name),'utf8'),context);
 const result=vm.runInContext(`(()=>{
  globalThis.uiText=value=>value;state.project={id:'fixture'};
  const d={commit:{sha:'revision'}},record={id:'runtime',sha:'revision',project_id:'fixture',running:true,url:'http://127.0.0.1:1234/',path:'/copies/<old>&',log_path:'/logs/run.log'};
  const pending=['preparing','install','build','starting'].map(status=>{
   state.runtimes=[{...record,status}];
   return {status:runtimeInfo(state.runtimes[0]).status,card:runtimeCards(state.runtimes),preview:renderRuntimes(d)};
  });
  state.runtimes=[{...record,status:'running'}];
  const ready={card:runtimeCards(state.runtimes),preview:renderRuntimes(d)};
  state.runtimes=[{...record,status:'cleanup_failed',cleanup_error:'ownership unconfirmed'}];
  const uncertain={card:runtimeCards(state.runtimes),preview:renderRuntimes(d)};
  state.runtimes=[{...record,status:'interrupted'}];
  const interrupted={card:runtimeCards(state.runtimes),preview:renderRuntimes(d)};
  return {pending,ready,uncertain,interrupted,cancelled:runtimeInfo({status:'cancelled',running:false}).status};
 })()`,context);
 assert.deepEqual(Array.from(result.pending,r=>r.status),['准备中','安装中','构建中','启动中']);
 for(const row of result.pending){
  assert.doesNotMatch(row.card,/data-action="stop-runtime"|href=/);
  assert.equal(row.preview,'');
 }
 assert.match(result.ready.card,/\/copies\/&lt;old&gt;&amp;/);
 assert.match(result.ready.card,/data-action="stop-runtime"/);
 assert.match(result.ready.preview,/href=/);
 assert.match(result.uncertain.card,/重试停止/);
 assert.doesNotMatch(result.uncertain.card,/href=/);
 assert.equal(result.uncertain.preview,'');
 assert.match(result.interrupted.card,/停止残留进程/);
 assert.match(result.interrupted.card,/data-action="stop-runtime"/);
 assert.doesNotMatch(result.interrupted.card,/href=/);
 assert.equal(result.interrupted.preview,'');
 assert.equal(result.cancelled,'已取消');
});
