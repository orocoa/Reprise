/* Main-task ordering and exact-version recovery contracts. No mutation runs. */
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function load(language='zh'){
 const c=vm.createContext({uiLanguage:language,uiCopy:{},uiText:s=>s,workspaceActions:{},document:{addEventListener(){}},location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.resolve('web/live.js'),'utf8').split("document.addEventListener('click'")[0],c);
 for(const name of ['dialog-controller','text-diff','live-evidence','live-features','live-content','live-versions'])vm.runInContext(fs.readFileSync(path.resolve('web/'+name+'.js'),'utf8'),c);
 vm.runInContext("state.project={id:'p',kind:'folder'};function revisionProject(){return 'p'};versionTitle=c=>c.subject||c.sha;versionNotes=()=>null;",c);return c;
}
const revision=(sha='b')=>({commit:{sha,subject:'User draft',parents:['a']},evidence:[],recipe:{adapter:'manual'},diff:{files:[{path:'draft.txt',status:'M'}],counts:{total:1}},content:{stats:{files:1,logical_bytes:5,unique_bytes:5,new_bytes:5},excluded:[]}});
test('ordinary files lead with changes and keep optional storage facts collapsed',()=>{
 const c=load();c.d=revision();let html=vm.runInContext('renderChanges(d)',c);
 assert.ok(html.indexOf('draft.txt')<html.indexOf('版本信息与存储'));assert.doesNotMatch(html,/version-recognition-card|<img/);
 assert.match(html,/<details class="content-facts"[^>]*><summary>/);
});
test('visual choice uses detection/evidence and project preference always wins',()=>{
 const c=load();c.d=revision();assert.equal(vm.runInContext('visualPresentation(d)',c),false);
 c.d.detection={candidates:[{recipe:{adapter:'static-web'}}]};assert.equal(vm.runInContext('visualPresentation(d)',c),true);
 vm.runInContext("state.prefs.presentation='files'",c);assert.equal(vm.runInContext('visualPresentation(d)',c),false);
 c.d=revision();vm.runInContext("state.prefs.presentation='visual'",c);assert.equal(vm.runInContext('visualPresentation(d)',c),true);
});
test('comparison without media never reserves two empty panels, in both languages',()=>{
 for(const lang of ['zh','en']){const c=load(lang);c.a=revision('a');c.b=revision('b');
 vm.runInContext("state.selected='b';state.details.set('p:a',a);state.details.set('p:b',b);state.comparison={base:'a',target:'b',diff:b.diff};comparisonPicker=()=>'<select>pair</select>';comparisonSummary=()=>'';",c);
 const html=vm.runInContext('renderComparison()',c);assert.match(html,/draft.txt/);assert.doesNotMatch(html,/compare-media-columns|empty-preview/);
 if(lang==='en')assert.equal(/[\u3400-\u9fff]/.test(html),false);
 }
});
test('compare file recovery binds each button to its actual side and SHA',()=>{
 const c=load('en');c.elements={};vm.runInContext("document.querySelector=selector=>elements[selector]||(elements[selector]={dataset:{},innerHTML:'',open:true});previewLanguageControls=()=>'';state.fileComparison={path:'draft.txt',project:'p',data:{base:'a',base_path:'old-draft.txt',sha:'b',before:{text:'before'},after:{text:'after'}}};renderFileComparison();",c);
 let html=c.elements['#dialog .dialog-body'].innerHTML;assert.match(html,/data-sha="a"/);assert.match(html,/data-sha="b"/);assert.match(html,/data-sha="a" data-path="old-draft.txt"/);assert.match(html,/Recover file from A/);assert.match(html,/Recover file from B/);
 vm.runInContext('state.fileComparison.data.after={absent:true};renderFileComparison()',c);html=c.elements['#dialog .dialog-body'].innerHTML;assert.match(html,/data-sha="a"/);assert.doesNotMatch(html,/data-sha="b"/);
});

test('closing any main-task dialog clears modes before later language changes',()=>{
 const c=load();c.dialog={open:true,dataset:{previewPreferences:'true',fileComparison:'true',recoveryForm:'true',recoveryResult:'true',quickPreview:'true'},close(){this.open=false},replaceChildren(){},querySelector(){return {dataset:{recoveryJob:'done'}}}};
 vm.runInContext("state.recoveryParents=new Map([['done',{old:'context'}]]);document.querySelector=s=>s==='#dialog'?dialog:null;document.querySelectorAll=()=>[];closeDialog();",c);
 assert.equal(vm.runInContext('state.recoveryParents.size',c),0);assert.equal(c.dialog.open,false);assert.deepEqual(Object.keys(c.dialog.dataset),[]);
 // A late render from a previously closed comparison must also be harmless.
 vm.runInContext('renderFileComparison()',c);
});

test('empty archive retains a project return path and never claims Git commits are missing',()=>{
 for(const language of ['zh','en']){
  const c=load(language);vm.runInContext("state.project={id:'archive',kind:'archive'};state.commits=[];state.filter='all'",c);
  const html=vm.runInContext('emptyVersionContent()',c);
  assert.match(html,/data-action="content-projects"/);assert.doesNotMatch(html,/首次提交|first commit/);
  assert.match(html,language==='zh'?/原始归档继续保留/:/original archive remains saved/);
 }
});
test('empty folders and filtered histories keep the appropriate next action',()=>{
 const c=load();vm.runInContext("state.commits=[];state.filter='all'",c);
 assert.match(vm.runInContext('emptyVersionContent()',c),/data-action="content-snapshot"/);
 vm.runInContext("state.filter='starred'",c);
 const html=vm.runInContext('emptyVersionContent()',c);
 assert.match(html,/data-action="clear-search"/);assert.doesNotMatch(html,/data-action="content-snapshot"/);
});
