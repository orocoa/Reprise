const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
function workspace(language){
 const c=vm.createContext({uiLanguage:language,uiCopy:{},workspaceActions:{},location:{hash:''},document:{addEventListener(){}},URLSearchParams});
 vm.runInContext("uiText=value=>uiLanguage==='en'?(uiCopy[value]||value):value",c);
 const web=path.resolve(__dirname,'../web');
 c.compileUICopy=()=>{};
 vm.runInContext(fs.readFileSync(path.join(web,'live-copy.js'),'utf8'),c);
 vm.runInContext(fs.readFileSync(path.join(web,'live.js'),'utf8').split("document.addEventListener('click'")[0],c);
 for(const name of ['live-content.js','live-versions.js','live-imports.js'])vm.runInContext(fs.readFileSync(path.join(web,name),'utf8'),c);
 return c;
}
const report={id:'report',project_id:'project',status:'complete',candidate_logical_bytes:100,candidate_allocated_bytes:4096,
 additional_managed_file_bytes:9000,modeled_net_after_source_removal_bytes:-8192,reviewed_at:'2026-10-24',
 versions:[{title:'Old <draft>',path:'/folder/<source>',sha:'a'.repeat(40),source_logical_bytes:100,removal_candidate:true,
 loss_on_source_removal:'原 ZIP 字节与封装元数据；内部文件可按版本恢复。',recovery_path:'/readback',verification:{coverage:['file bytes']},blockers:[]}],limitations:[]};
test('candidate report distinguishes gross size, costs, negative net and unknown volume reclaim',()=>{
 const c=workspace('zh');c.report=report;const html=vm.runInContext('importReportBody(report)',c);
 assert.match(html,/模型净占用不会减少/);assert.match(html,/实际磁盘释放量未知/);
 assert.match(html,/重新核对/);assert.match(html,/没有删除按钮/);
 assert.doesNotMatch(html,/data-action="[^"]*delete/);assert.doesNotMatch(html,/<input[^>]*checked/);
 assert.match(html,/Old &lt;draft&gt;/);assert.doesNotMatch(html,/<source>/);
});
test('English explains ZIP identity loss without translating user paths or titles',()=>{
 const c=workspace('en');c.report=report;const html=vm.runInContext('importReportBody(report)',c);
 assert.match(html,/Original ZIP bytes and envelope metadata/);assert.match(html,/Keeping every recovery copy/);
 assert.match(html,/Old &lt;draft&gt;/);assert.match(html,/folder\/&lt;source&gt;/);
});
test('incomplete report cannot label unfinished versions as verified candidates',()=>{
 const c=workspace('en');c.report={...report,status:'incomplete',versions:[]};
 const html=vm.runInContext('importReportBody(report)',c);
 assert.match(html,/Do not remove originals/);assert.doesNotMatch(html,/Recovery verified/);
});
const preview={versions:[{title:'Draft <one>',path:'/private/<draft>',keep:false,kind:'folder',expanded_logical_bytes:4096,excluded:[]}],
 additional_content_logical_bytes_max:4096,additional_readback_logical_bytes_max:4096,capacity_budget_bytes:16793600,
 filesystem_free_bytes:99999999,capacity_available:true,source_volumes:[{device:'1'}],data_directory:'/library'};
test('cost preview distinguishes unknown sharing from full readback cost without a removal control',()=>{
 const c=workspace('en');c.preview=preview;const html=vm.runInContext('importCostBody(preview)',c);
 assert.match(html,/No versions or recovery copies were created/);
 assert.match(html,/actual sharing is unknown/);assert.match(html,/Maximum readback expansion/);
 assert.match(html,/Draft &lt;one&gt;/);assert.doesNotMatch(html,/data-action="[^"]*delete/);
 assert.doesNotMatch(html,/Recovery verified/);
});
test('low space is a blocker and a restored preview requires a fresh check',()=>{
 const c=workspace('en');c.preview={...preview,capacity_available:false};
 assert.match(vm.runInContext('importCostBody(preview)',c),/Free space is below/);
 c.preview={...preview,capacity_available:false,restored_historical_report:true,filesystem_free_bytes:null};
 const html=vm.runInContext('importCostBody(preview)',c);
 assert.match(html,/preview came from a backup/);assert.match(html,/Unknown/);
 assert.doesNotMatch(html,/Available on the data volume: 0 B/);
});
test('failed preview stays visibly failed without implying recovery or leaving only progress text',()=>{
 const c=workspace('en');c.job={error:'Missing <input>'};const html=vm.runInContext('importCostFailureBody(job)',c);
 assert.match(html,/role="alert"/);assert.match(html,/Missing &lt;input&gt;/);
 assert.match(html,/preview did not complete/);assert.match(html,/no versions or recovery copies were created/);
 assert.doesNotMatch(html,/Recovery verified/);
});
