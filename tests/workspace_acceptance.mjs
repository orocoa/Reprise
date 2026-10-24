/* Production workspace regression; the main UI exposes no AI workflow. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,project,sha,output]=process.argv.slice(2);
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
let aiRequests=0;page.on('request',request=>{if(request.method()==='POST'&&/\/ai\/suggest$/.test(request.url()))aiRequests++;});
const runtimeResponses=[];
page.on('response',async response=>{
 if(!/\/api\/(bootstrap|runtimes)(\?|$)/.test(response.url()))return;
 try{const body=await response.json();runtimeResponses.push({url:response.url(),rows:(body.runtimes||[]).map(r=>({sha:r.sha,status:r.status,running:r.running}))});}catch{}
});
const snapshot=()=>page.evaluate(()=>repriseWorkspace.snapshot());
async function expandSettingsSection(name){
 const section=page.locator(`#dialog details[data-keep-open="${name}"]`);
 if(!await section.evaluate(element=>element.open))await section.locator(':scope > summary').click();
}
try {
 await page.goto(`${url}?project=${project}&sha=${sha}&lang=en`);
 await page.waitForFunction(()=>state.commits.length===2&&detail(state.selected)&&!state.loading);
 assert.equal(await page.locator('#search').getAttribute('placeholder'),'Search draft names or files…');
 assert.equal(await page.locator('[data-action=ai-settings],[data-action=ai-suggest]').count(),0,'The main workspace has no AI entry');
 assert.equal(await page.locator('[data-density=compact]').innerText(),'Compact view');
 const initialGraph=await page.evaluate(()=>JSON.stringify(repriseWorkspace.graph()));
 const graphStyle=await page.locator('#route-map').evaluate(svg=>({
   nodes:[...svg.querySelectorAll('[data-node]')].map(n=>[n.dataset.node,n.getAttribute('cx'),n.getAttribute('stroke')]),
   edges:[...svg.querySelectorAll('path')].map(e=>[e.dataset.child,e.dataset.parent,e.getAttribute('stroke')])
 }));
 async function verifyGraphView(){
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   assert.equal(await page.evaluate(()=>JSON.stringify(repriseWorkspace.graph())),initialGraph,'UI actions must preserve the full DAG');
   const rendered=await page.locator('#route-map').evaluate(svg=>({
     nodes:[...svg.querySelectorAll('[data-node]')].map(n=>[n.dataset.node,n.getAttribute('cx'),n.getAttribute('stroke')]),
     edges:[...svg.querySelectorAll('path')].map(e=>[e.dataset.child,e.dataset.parent,e.getAttribute('stroke')])
   }));
   assert.deepEqual(rendered,graphStyle,'Columns, colors and parent endpoints survive filtering and density changes');
   assert.equal(await page.evaluate(()=>state.graph.rows.every(n=>{
     const row=document.querySelector(`.version-row[data-id="${n.id}"]`);
     const label=row.querySelector(state.prefs.density==='compact'?'.version-title':'.version-meta');
     const circle=document.querySelector(`[data-node="${n.id}"]`);
     return Math.abs(Number(circle.getAttribute('cy'))-(row.offsetTop+label.offsetTop+label.offsetHeight/2))<.1;
   })),true,'Circles align with their actual DOM rows');
 }
 assert.equal(await page.locator('button[data-action=run]').innerText(),'Run preview');
 assert.deepEqual(await page.locator('.chrome [data-action=language]').evaluateAll(buttons=>buttons.map(button=>button.dataset.language)),['zh','en']);
 assert.equal(await page.locator('[data-action=edit-version]').innerText(),'');
 await page.click('[data-action=star]');
 assert.equal((await snapshot()).sha,sha);
 assert.equal(await page.locator('[data-action=star]').getAttribute('aria-pressed'),'true');
 await page.click('[data-density=compact]');
 assert.equal(await page.locator('.version-row.selected').evaluate(e=>e.getBoundingClientRect().height),32);
 assert.equal(await page.locator('.version-row').count(),2);
 await verifyGraphView();
 await page.click('[data-action=filter]');
 assert.equal(await page.locator('.version-row').count(),2);
 assert.equal(await page.locator('.version-row.context-row').count(),1);
 await verifyGraphView();
 await page.click('[data-action=clear-search]');
 await page.fill('#search','no-such-graph-revision-8271');
 await page.waitForFunction(()=>!state.searching&&document.querySelectorAll('.version-row.context-row').length===2);
 await verifyGraphView();
 await page.click('[data-action=clear-search]');
 await page.click(`[data-action=select][data-id="${await page.evaluate(()=>state.commits.find(c=>c.sha!==state.selected).sha)}"]`);
 await page.waitForFunction(()=>detail(state.selected));
 await verifyGraphView();
 await page.click(`[data-action=select][data-id="${sha}"]`);
 await page.waitForFunction(()=>detail(state.selected));
 await page.click('[data-tab=preview]');
 // Tabs must survive both synchronous and asynchronous detail renders.
 await page.press('#tab-preview','ArrowLeft');
 await page.waitForFunction(()=>state.tab==='updates'&&document.activeElement.id==='tab-updates');
 await page.keyboard.press('ArrowRight');
 assert.equal(await page.evaluate(()=>document.activeElement.id),'tab-preview');
 await page.keyboard.press('End');
 await page.waitForFunction(()=>state.comparison&&!state.comparisonLoading);
 assert.equal(await page.evaluate(()=>document.activeElement.id),'tab-compare');
 await page.keyboard.press('Home');
 await page.waitForFunction(()=>state.tab==='updates'&&document.activeElement.id==='tab-updates');
 assert.equal(await page.locator('[role=tab][tabindex="0"]').count(),1);
 // A late response cannot take focus back after the user starts searching.
 await page.evaluate(()=>{
  const original=ensureUpdateBaseline;
  ensureUpdateBaseline=async(...args)=>{
   await new Promise(resolve=>{window.releaseBaseline=resolve;});
   ensureUpdateBaseline=original;return original(...args);
  };
 });
 await page.click('[data-tab=updates]');
 await page.focus('#search');
 await page.evaluate(()=>window.releaseBaseline());
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
 assert.equal(await page.evaluate(()=>document.activeElement.id),'search');
 await page.click('[data-tab=preview]');
 assert.equal(await page.locator('.empty-preview p').innerText(),'No screenshots or recordings have been saved for this revision.');
 await page.screenshot({path:output+'/empty-preview-en.png',fullPage:true});
 await page.click('[data-action=preview-settings]');
 assert.equal(await page.locator('.preview-settings').evaluate(e=>e.open),true);
 assert.equal(await page.locator('[data-action=saved-preview-capture]').innerText(),'Check website and capture');
 // Child-dialog Back and Escape restore the actual scroll container and origin.
 await page.setViewportSize({width:390,height:400});
 await page.locator('[data-action=manual]').scrollIntoViewIfNeeded();
 const settingsTop=await page.locator('#dialog').evaluate(dialog=>dialog.scrollTop);
 assert.ok(settingsTop>0,'The return test must exercise a scrolled settings dialog');
 await page.click('[data-action=manual]');
 assert.equal(await page.locator('#dialog .dialog-footer [data-action=close]').innerText(),'Back to settings');
 await page.keyboard.press('Escape');
 assert.equal(await page.locator('#dialog').evaluate(dialog=>dialog.open&&dialog.classList.contains('settings-dialog')),true);
 assert.equal(await page.locator('.preview-settings').evaluate(element=>element.open),true);
 assert.equal(await page.evaluate(()=>document.activeElement.dataset.action),'manual');
 assert.ok(Math.abs(await page.locator('#dialog').evaluate(dialog=>dialog.scrollTop)-settingsTop)<2);
 await page.click('[data-action=manual]');
 await page.click('#dialog .dialog-footer [data-action=close]');
 assert.equal(await page.evaluate(()=>document.activeElement.dataset.action),'manual');
 await page.screenshot({path:output+'/import-return-mobile-en.png',fullPage:true});
 await page.setViewportSize({width:1360,height:900});
 await page.click('#dialog [data-action=close]');
 assert.equal((await snapshot()).tab,'preview');
 assert.equal((await snapshot()).sha,sha);
 await page.click('[data-tab=updates]');
 await page.click('[data-action=settings]');
 assert.equal(await page.locator('#dialog [data-action=ai-settings],#dialog [data-action=ai-suggest],#dialog [data-action=content-storage],#dialog [data-action=content-transfer]').count(),0,'Settings omit AI and whole-library maintenance entries');
 await expandSettingsSection('project-activity');
 assert.equal(await page.locator('#settings-management').innerText().then(t=>t.includes('This job record cannot be read.')),true);
 assert.equal(await page.locator('#settings-management code').first().innerText(),'broken-record.json');
 await page.click('#dialog [data-action=close]');
 await page.click('[data-action=settings]');
 await page.click('#dialog [data-language=zh]');
 assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);
 assert.equal(await page.locator('[data-action=run]').innerText(),'运行预览');
 await page.click('#dialog [data-language=en]');
 await page.click('[data-action=save-settings]');
 await page.click('[data-action=edit-version]');
 await page.fill('#inline-title','Edited locally');
 await page.fill('#inline-summary','Readable summary');
 await page.click('[data-action=save-inline-notes]');
 await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 assert.equal(await page.locator('.version-name h2').innerText(),'Edited locally');
 await page.reload();
 await page.waitForFunction(()=>detail(state.selected)&&!state.loading);
 assert.equal(await page.locator('.version-name h2').innerText(),'Edited locally');
 assert.equal(await page.locator('[data-action=star]').getAttribute('aria-pressed'),'true');
 assert.equal((await snapshot()).density,'compact');
 await page.click('[data-action=edit-release-notes]');
 await page.fill('#inline-changes','First update\nSecond update');
 await page.click('[data-action=save-inline-notes]');
 await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 assert.equal(await page.locator('.release-notes li').count(),2);
 assert.equal(await page.evaluate(()=>detail(state.selected).recipe_approved),false);
 await page.click('[data-action=run]');
 await page.waitForSelector('#recipe-json',{state:'attached'});
 assert.equal(await page.locator('#recipe-json').isVisible(),false,'Static recipe keeps advanced JSON collapsed');
 await page.locator('.recipe-advanced summary').click();
 assert.equal(JSON.parse(await page.locator('#recipe-json').inputValue()).adapter,'static-web');
 await page.click('[data-action=save-recipe]');
 await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 assert.equal(await page.evaluate(()=>detail(state.selected).recipe_approved),true);
 await page.click('[data-action=run]');
 await page.waitForFunction(()=>state.runtimes.some(r=>r.running),null,{timeout:20000});
 await page.click('[data-action=settings]');
 await expandSettingsSection('project-activity');
 const runningCopy=await page.evaluate(()=>state.runtimes.find(r=>r.status==='running').path);
 await page.click('.managed-runtime summary');
 assert.equal(await page.locator('.managed-runtime dd code').first().innerText(),runningCopy);
 await page.click('[data-action=stop-runtime]');
 await page.waitForFunction(()=>!state.runtimes.some(r=>r.running),null,{timeout:15000});
 await expandSettingsSection('preview-help');
 await page.click('#dialog [data-action=saved-preview-capture]');
 await page.waitForSelector('#dialog [data-action=save-quick-preview],#dialog [data-action=capture]');
 await page.click('#dialog [data-action=save-quick-preview],#dialog [data-action=capture]');
 await page.waitForFunction(()=>detail(state.selected)?.evidence.some(e=>e.status==='complete'),null,{timeout:30000});
 if(await page.locator('#dialog').evaluate(element=>element.open))await page.click('#dialog [data-action=close]');
 await page.click('[data-tab=preview]');
 await page.waitForSelector('.media-open');
 await page.click('.media-open');
 await page.waitForSelector('.large-media img');
 await page.click('#dialog [data-action=close]');
 await page.click('[data-tab=compare]');
 await page.waitForFunction(()=>state.comparison&&!state.comparisonLoading);
 const pair=(await snapshot()).comparison;
 assert.equal(pair.target,sha);
 assert.equal(await page.locator('[data-action=apply-comparison]').count(),0);
 assert.equal(await page.locator('#compare-base-ref').count(),0);
 await page.click('[data-action=swap-comparison]');
 await page.waitForFunction(pair=>state.comparison?.target===pair.base&&!state.comparisonLoading,pair);
 await page.click('[data-action=swap-comparison]');
 await page.waitForFunction(pair=>state.comparison?.target===pair.target&&!state.comparisonLoading,pair);
 // Delayed older response must not replace the newest A/B selection.
 let delayed=false;
 await page.route('**/api/workspace/diff?*',async route=>{
  if(!delayed){delayed=true;await new Promise(resolve=>setTimeout(resolve,400));}
  await route.continue();
 });
 await page.selectOption('#compare-base',sha);
 await page.selectOption('#compare-base',pair.base);
 await page.waitForFunction(pair=>state.comparison?.base===pair.base&&!state.comparisonLoading,pair);
 await page.waitForTimeout(500);
 assert.deepEqual((await snapshot()).comparison,pair);
 await page.unroute('**/api/workspace/diff?*');
 // Exercise a real, explicitly saved install command and cancel its job.
 await page.click('[data-tab=preview]');
 await page.click(`[data-action=select][data-id="${pair.base}"]`);
 await page.waitForFunction(base=>state.selected===base&&detail(base),pair.base);
 assert.equal(await page.locator('.media-open').count(),0,'Another revision’s captured media must not fill this empty preview');
 await page.click('[data-action=run]');
 // This Playwright poller treats a Promise as truthy. Await actual server data
 // in Node rather than using an async waitForFunction predicate.
 const installDeadline=Date.now()+20000;
 let installing=false;
 while(Date.now()<installDeadline){
  const {runtimes:rows}=await (await page.request.get(url+'api/runtimes')).json();
  installing=rows.some(r=>r.sha===pair.base&&r.status==='install'&&r.running);
  if(installing)break;
  await new Promise(resolve=>setTimeout(resolve,200));
 }
 assert.equal(installing,true,'The saved install command must actually be running');
 await page.click('[data-action=settings]');
 await page.waitForFunction(()=>document.querySelector('#dialog').open&&document.querySelector('#dialog').classList.contains('settings-dialog'));
 await expandSettingsSection('project-activity');
 await page.click('[data-action=refresh-management]');
 assert.equal(await page.locator('.runtime-row').count(),0,'An installer is not a ready preview');
 const pending=page.locator('.managed-runtime').filter({hasText:'Installing'});
 await pending.waitFor({state:'visible',timeout:10000});
 assert.equal(await pending.count(),1);
 assert.equal(await pending.locator('[data-action=stop-runtime],a').count(),0);
 await page.screenshot({path:output+'/runtime-install-en.png',fullPage:true});
 await page.click('[data-action=cancel-job]');
 await page.waitForFunction(()=>state.jobs.some(j=>j.operation==='run'&&j.request.sha===state.selected&&j.status==='cancelled'),null,{timeout:15000});
 await page.waitForFunction(()=>state.runtimes.some(r=>r.sha===state.selected&&r.status==='cancelled'&&!r.running));
 assert.equal(await page.locator('.managed-runtime').filter({hasText:'Cancelled'}).count(),1);
 await page.click('#dialog [data-action=close]');
 await page.click(`[data-action=select][data-id="${sha}"]`);
 await page.waitForFunction(()=>state.selected===new URL(location.href).searchParams.get('sha')&&detail(state.selected));
 await page.click('[data-tab=updates]');
 await page.screenshot({path:output+'/desktop-en.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:output+'/mobile-en.png',fullPage:true});
 assert.equal(aiRequests,0,'The complete workflow sends no AI suggestion request');
 assert.deepEqual(errors,[]);
 await fs.writeFile(output+'/ui-result.json',JSON.stringify({ok:true,sha,model:'exact-test-model',ai_calls:0,ai_entries_absent:true,notes_saved:true,recipe_explicitly_approved:true,run_stop:true,capture:true,bookmark_persistence:true,compact_height:32,auto_compare:true,compare_race:true,media_modal:true,empty_preview_entry:true,exact_revision_media:true,runtime_copy_path:true,install_cancel:true,mobile_overflow:false,errors},null,2));
} catch(error){
 await fs.writeFile(output+'/ui-failure.json',JSON.stringify(await page.evaluate(()=>({
  snapshot:repriseWorkspace.snapshot(),runtimes:state.runtimes,
  dialog:document.querySelector('#dialog').innerText
 })),null,2));
 await fs.writeFile(output+'/runtime-responses.json',JSON.stringify(runtimeResponses,null,2));
 await page.screenshot({path:output+'/ui-failure.png',fullPage:true});
 throw error;
} finally {await browser.close();}
