/* Keep full details bounded without losing file search or comparison inputs. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const web=path.resolve(__dirname,'../web');

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
  renderHistory=()=>{};settleFilter=()=>{};
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
