/* Exact-SHA evidence remains consistent across previews, comparisons and jobs. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const web=path.resolve(__dirname,'../web');
function workspace(){
 const context=vm.createContext({location:{hash:''},URLSearchParams,uiCopy:{},uiLanguage:'zh',uiText:value=>value,
  document:{querySelector:()=>({open:false,setAttribute(){}})}});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 for(const name of ['live-focus.js','live-evidence.js','live-features.js','live-updates.js']){
  const source=fs.readFileSync(path.join(web,name),'utf8').split('// Named handlers')[0];
  vm.runInContext(source,context);
 }
 vm.runInContext("state.project={id:'project'};state.selected='target';state.tab='preview';",context);
 return context;
}

test('normalization binds sides and capture recipes to their exact revisions',()=>{
 const context=workspace();
 const result=vm.runInContext(`(()=>{
  const records=[{id:'pair',sha:'target',base:'base',source:'automatic',recipe:{network:'local',captures:[{id:'scene',route:'/new'}]},base_recipe:{network:'online',captures:[{id:'scene',route:'/old'}]},items:[
   {side:'after',capture_id:'scene',media_type:'image/png',url:'/target'},
   {side:'before',capture_id:'scene',media_type:'image/png',url:'/base'},
   {side:'base',sha:'target',kind:'image',url:'/wrong-side'},
   {sha:'unrelated',kind:'image',url:'/wrong-sha'}]}];
  return {target:evidenceItems(records,'target',{side:'target'}),base:evidenceItems(records,'base',{side:'base'})};
 })()`,context);
 assert.equal(result.target.length,1);assert.equal(result.base.length,1);
 assert.equal(result.target[0].sha,'target');assert.equal(result.target[0].capture.route,'/new');
 assert.equal(result.base[0].sha,'base');assert.equal(result.base[0].capture.route,'/old');
 assert.equal(result.base[0].capture.network,'online');
 assert.equal(result.base[0].index,1);
});

test('gallery skips files, failed and unavailable artifacts while preserving video and baseline identity',()=>{
 const result=vm.runInContext(`(()=>{
  const d={commit:{sha:'target'},evidence:[{id:'target-record',sha:'target',base:'base',items:[
   {kind:'image',url:'/image'}, {kind:'file',url:'/notes'}, {kind:'image',url:'/missing',missing:true},
   {kind:'video',url:'/video'}, {kind:'image',url:'/bad',error:'invalid'}, {kind:'image'},
   {kind:'image',url:'/baseline',sha:'base',side:'before'}]}]};
  const baseline={commit:{sha:'base'},evidence:[{id:'old-record',sha:'base',items:[{kind:'image',url:'/old'}]}]};
  const items=mediaGallery(d,baseline,'base');
  return {gallery:items.map(item=>[item.record,item.index,item.kind,item.sha]),all:mediaItems(d).length,
   dedup:uniqueEvidence([...items,...items]).length};
 })()`,workspace());
 assert.deepEqual(JSON.parse(JSON.stringify(result.gallery)),[
  ['target-record',0,'image','target'],['target-record',3,'video','target'],
  ['target-record',6,'image','base'],['old-record',0,'image','base']]);
 assert.equal(result.all,6);assert.equal(result.dedup,4);
});

test('preview displays errors and ordinary files; diagnostics escape content without serving local paths',()=>{
 const result=vm.runInContext(`(()=>{
  renderRuntimes=()=>'';
  const record={id:'failed',sha:'target',source:'automatic',status:'partial',items:[
   {kind:'file',url:'/notes',title:'Notes'},{kind:'image',url:'/bad',error:'<script>bad</script>'}],
   errors:[{side:'after',error:'<img onerror=alert(1)>'}],warnings:[{message:'asset missing'}],
   record_path:'/private/<record>.json',local_directory:'/private/evidence',browser_logs:['/private/browser.log']};
  const d={commit:{sha:'target'},evidence:[record]};
  return {preview:renderPreview(d),empty:renderPreview({...d,evidence:[{...record,status:'failed',items:[]}]}),never:renderPreview({...d,evidence:[]})};
 })()`,workspace());
 assert.match(result.preview,/href="\/notes"/);assert.doesNotMatch(result.preview,/<img src="\/bad"/);
 assert.match(result.preview,/&lt;script&gt;bad&lt;\/script&gt;/);
 assert.match(result.preview,/&lt;img onerror=alert\(1\)&gt;/);
 assert.match(result.preview,/部分完成 · 已保存 1 项/);
 assert.match(result.preview,/data-keep-open="capture-failed"/);
 assert.match(result.preview,/<code>\/private\/browser.log<\/code>/);
 assert.doesNotMatch(result.preview,/href="[^\"]*private/);
 assert.match(result.empty,/采集未完成/);assert.match(result.never,/此版本尚未保存截图或录屏/);
});

for(const resultStatus of ['partial','failed','cancelled','complete'])test(`${resultStatus} capture refreshes both visible revisions without touching other projects`,async()=>{
 const context=workspace();context.resultStatus=resultStatus;
 const result=await vm.runInContext(`(async()=>{
  const job={id:'job',operation:'capture',project_id:'project',request:{sha:'target',base:'base'},status:resultStatus==='partial'?'failed':resultStatus,
   result:{status:resultStatus,sha:'target',base:'base',items:[{kind:'image',url:'/saved'}]}};
  state.comparison={base:'base',target:'target'};
  state.details=new Map([['project:target',{old:true}],['project:base',{old:true}],['other:target',{untouched:true}]]);
  state.jobs=[{...job,status:'running'}];
  const loaded=[],notices=[];let renders=0;
  api=async()=>job;refreshWorkspace=async()=>{};refreshSettingsManagement=()=>{};
  loadDetail=async(sha,signal,project)=>{loaded.push([sha,project]);state.details.set(project+':'+sha,{commit:{sha},evidence:[],diff:{base:null}});};
  renderDetail=()=>renders++;notify=text=>notices.push(text);
  await pollWorkspaceJob('job');
  return {loaded,renders,notices,selected:state.selected,other:state.details.get('other:target'),polling:pollingJobs.size};
 })()`,context);
 assert.deepEqual(JSON.parse(JSON.stringify(result.loaded)),[['target','project'],['base','project']]);
 assert.equal(result.renders,1);assert.equal(result.selected,'target');assert.equal(result.other.untouched,true);assert.equal(result.polling,0);
 const expected={partial:'部分完成',failed:'采集失败',cancelled:'已取消',complete:'采集完成'}[resultStatus];
 assert.match(result.notices[0],new RegExp(expected));
});

test('background terminal capture invalidates its cache but leaves user selection and view intact',async()=>{
 const result=await vm.runInContext(`(async()=>{
  state.selected='unrelated';state.details=new Map([['project:target',{old:true}],['project:unrelated',{keep:true}]]);
  const job={id:'job',operation:'capture',project_id:'project',request:{sha:'target'},status:'failed',result:{status:'failed',items:[]}};
  let loaded=0,renders=0;
  api=async()=>job;refreshWorkspace=async()=>{};refreshSettingsManagement=()=>{};
  loadDetail=async()=>loaded++;renderDetail=()=>renders++;notify=()=>{};
  await pollWorkspaceJob('job');return {selected:state.selected,stale:state.details.has('project:target'),loaded,renders,keep:detail('unrelated').keep};
 })()`,workspace());
 assert.equal(result.selected,'unrelated');assert.equal(result.stale,false);assert.equal(result.loaded,0);assert.equal(result.renders,0);assert.equal(result.keep,true);
});

test('media viewer never opens an ordinary file and video retains its native controls',async()=>{
 const result=await vm.runInContext(`(async()=>{
  state.details.set('project:target',{commit:{sha:'target'},diff:{base:null},evidence:[{id:'media',sha:'target',items:[
   {kind:'image',url:'/image'},{kind:'file',url:'/text'},{kind:'video',url:'/video'}]}]});
  let dialogs=[];dialogShell=(title,body)=>dialogs.push(body);
  await showMedia('media','1');const fileDialogs=dialogs.length;
  await showMedia('media','2');return {fileDialogs,body:dialogs[0],count:state.openMedia.items.length,position:state.openMedia.position};
 })()`,workspace());
 assert.equal(result.fileDialogs,0);assert.equal(result.count,2);assert.equal(result.position,1);
 assert.match(result.body,/<video src="\/video" controls autoplay>/);assert.doesNotMatch(result.body,/<img/);
});

test('comparison baseline renders paired evidence retained only on the target record',()=>{
 const result=vm.runInContext(`(()=>{
  renderRuntimes=()=>'';
  const baseline={commit:{sha:'base'},evidence:[]},target={commit:{sha:'target'},evidence:[{id:'pair',sha:'target',base:'base',items:[
   {sha:'base',side:'before',kind:'image',url:'/before',title:'Baseline'},
   {sha:'target',side:'after',kind:'image',url:'/after',title:'Target'}]}]};
  return renderPreview(baseline,{comparison:true,pairedTarget:target});
 })()`,workspace());
 assert.match(result,/src="\/before"/);assert.doesNotMatch(result,/src="\/after"/);assert.doesNotMatch(result,/没有预览/);
});
