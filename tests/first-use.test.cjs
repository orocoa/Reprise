/* User-facing impact copy and exact-version recognition, without mutation. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const web=path.resolve(__dirname,'../web');
function workspace(language='zh'){
 const context=vm.createContext({uiLanguage:language,uiCopy:{},uiText:s=>language==='en'?({'文件':'files'}[s]||s):s,
  workspaceActions:{},document:{addEventListener(){}},location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],context);
 for(const name of ['live-evidence.js','live-content.js','live-versions.js'])vm.runInContext(fs.readFileSync(path.join(web,name),'utf8'),context);
 vm.runInContext("versionTitle=c=>c.subject;versionNotes=()=>null;",context);
 return context;
}
const plan={selected_shas:['old'],selected_versions:[{sha:'old',title:'Old draft',files:3,logical_bytes:4096}],
 project_versions_retained:2,other_versions_retained:1,other_projects_protected:1,retained_versions:3,
 unique_content_bytes:3072,shared_content_bytes:1024,unique_files:[],shared_files:[],blockers:[],warnings:[]};
test('impact answers loss and physical-space uncertainty before the file details',()=>{
 const context=workspace();context.plan=plan;
 const html=vm.runInContext('versionImpactBody(plan)',context);
 assert.match(html,/本项目：将删除 1 版，保留 2 版/);
 assert.match(html,/另外 1 个项目的 1 版继续保留/);
 assert.ok(html.indexOf('会失去什么')<html.indexOf('version-impact-files'));
 assert.ok(html.indexOf('实际磁盘释放量：执行后才能确认')<html.indexOf('version-impact-metrics'));
 assert.match(html,/不等于预计释放的磁盘空间/);
 assert.match(html,/不能把单版收益直接相加/);
 assert.doesNotMatch(html,/<input[^>]*checked/);
});
test('zero exclusive bytes and selecting every version have explicit consequences',()=>{
 const context=workspace();context.plan={...plan,unique_content_bytes:0,project_versions_retained:0};
 const html=vm.runInContext('versionImpactBody(plan)',context);
 assert.match(html,/没有可回收的独占文件内容（0 B）/);
 assert.match(html,/仍会失去所选历史状态/);
 assert.match(html,/本项目将没有可恢复的已保存版本/);
});
test('blocked plans never display an enabled confirmation control',()=>{
 const context=workspace();context.plan={...plan,blockers:['Synthetic blocker']};
 const html=vm.runInContext('versionImpactBody(plan)',context);
 assert.match(html,/Synthetic blocker/);assert.doesNotMatch(html,/id="version-delete-confirm"/);
});
test('English impact remains localized and does not mistake global counts for project counts',()=>{
 const context=workspace('en');context.plan=plan;
 const html=vm.runInContext('versionImpactBody(plan)',context);
 assert.match(html,/This project: remove 1, keep 2 versions/);
 assert.match(html,/Actual disk space freed: known only after execution/);
 assert.equal(/[\u3400-\u9fff]/.test(html),false);
});
test('recognition thumbnails never substitute another revision, missing media, or mismatched item',()=>{
 const context=workspace();context.records=[
  {id:'other',sha:'other',items:[{kind:'image',url:'/other.png'}]},
  {id:'missing',sha:'old',items:[{kind:'image',url:'/missing.png',missing:true}]},
  {id:'wrong',sha:'old',items:[{sha:'other',kind:'image',url:'/wrong.png'}]},
 ];
 let html=vm.runInContext("versionThumbnail({sha:'old',subject:'<Old>'},records)",context);
 assert.doesNotMatch(html,/<img/);assert.match(html,/暂无此版截图/);assert.match(html,/&lt;Old&gt;/);
 context.records.push({id:'exact',sha:'old',source:'manual',items:[{kind:'image',url:'/exact.png'}]});
 html=vm.runInContext("versionThumbnail({sha:'old',subject:'Old'},records)",context);
 assert.match(html,/src="\/exact.png"/);assert.match(html,/归属由提供者指定/);
 assert.doesNotMatch(html,/src="\/(other|missing|wrong).png"/);
});
test('missing screenshot stays compact and offers explicit preview configuration',()=>{
 const context=workspace();context.d={commit:{sha:'old',subject:'Old'},evidence:[]};
 const html=vm.runInContext('versionRecognitionCard(d)',context);
 assert.match(html,/data-action="preview-settings"/);
 assert.match(html,/此版本尚无截图/);assert.doesNotMatch(html,/version-recognition-image/);assert.doesNotMatch(html,/data-action="run"/);
});

const measured={estimated_store_reduction_min_bytes:1024,estimated_store_reduction_max_bytes:1024,
 estimated_allocated_reduction_min_bytes:4096,estimated_allocated_reduction_max_bytes:4096,
 baseline_compaction_min_bytes:768,baseline_compaction_max_bytes:768,
 selection_incremental_min_bytes:256,selection_incremental_max_bytes:256,
 modeled_net_reduction_after_records_min_bytes:800,modeled_net_reduction_after_records_max_bytes:800,
 observed_repeat_spread_bytes:0,retained_artifact_bytes:224,report_path:'/local/report.json'};
test('measured savings distinguish repeat spread, real error, compaction and retained record cost',()=>{
 const context=workspace();context.measured=measured;
 const html=vm.runInContext('versionSpaceAnswer(null,measured)',context);
 assert.match(html,/预计版本库文件减少：1 KiB/);
 assert.match(html,/实际误差未知/);assert.match(html,/未保存整份模拟包/);
 assert.match(html,/仅重新打包现有库/);assert.match(html,/舍弃所选版本的额外/);
 assert.match(html,/两次结果相同不代表真实删除误差为零/);
 assert.doesNotMatch(html,/data-action="save-version-delete"/);
});
test('negative modeled savings are labeled as growth and English keeps uncertainty explicit',()=>{
 const context=workspace('en');context.measured={...measured,estimated_store_reduction_min_bytes:-2048,estimated_store_reduction_max_bytes:-1024};
 const html=vm.runInContext('versionSpaceAnswer(null,measured)',context);
 assert.match(html,/Expected library growth/);assert.match(html,/1 KiB – 2 KiB/);
 assert.match(html,/will not achieve a space saving/);
 assert.match(html,/real deletion error is unknown/);assert.match(html,/not a statistical confidence interval/);
 assert.equal(/[\u3400-\u9fff]/.test(html),false);
});
test('an estimate whose records exceed its gains explains the negative net result',()=>{
 const context=workspace();context.measured={...measured,modeled_net_reduction_after_records_max_bytes:-100};
 const html=vm.runInContext('versionSpaceAnswer(null,measured)',context);
 assert.match(html,/保留这些记录时，模型净占用会增加/);
 assert.match(html,/预计版本库文件减少/);
});
