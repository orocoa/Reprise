/* Real saved evidence plus controlled terminal-job responses in an isolated service. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,project,sha,output]=process.argv.slice(2);
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const recordId='c'.repeat(32),terminalRecordId='d'.repeat(32);
try{
 await page.goto(`${url}?project=${project}&sha=${sha}&lang=en`);
 await page.waitForFunction(()=>detail(state.selected)&&!state.loading);
 const base=await page.evaluate(()=>detail(state.selected).diff.base);
 assert.ok(base,'Fixture needs a baseline commit');
 await page.click('[data-tab=preview]');
 const diagnostic=page.locator(`#live-content [data-keep-open="capture-${recordId}"]`);
 assert.match(await diagnostic.innerText(),/Partially complete.*2 saved items/);
 await diagnostic.locator('summary').click();
 assert.match(await diagnostic.innerText(),/Fixture route failed/);
 assert.match(await diagnostic.innerText(),/Fixture asset warning/);
 const retained=await page.evaluate(id=>detail(state.selected).evidence.find(record=>record.id===id),recordId);
 assert.ok(retained.local_directory);assert.ok(retained.record_path);assert.equal(retained.browser_logs.length,1);
 assert.equal(await diagnostic.locator('a').count(),0,'Private diagnostic paths are plain text');
 const privateResponse=await page.request.get(new URL(`/artifacts/${recordId}/after-browser.log`,url).href);
 assert.equal(privateResponse.status(),404);
 await page.screenshot({path:path.join(output,'evidence-diagnostics.png'),fullPage:true});
 await diagnostic.screenshot({path:path.join(output,'evidence-diagnostics-detail.png')});

 // Paired baseline media live in the target record; comparison A must still show them.
 await page.evaluate(async baseline=>{state.tab='compare';await applyComparison(baseline,state.selected);},base);
 assert.equal(await page.locator('.comparison-side').nth(0).locator('img[alt="Captured baseline"]').count(),1);
 assert.equal(await page.locator('.comparison-side').nth(0).locator('img[alt="Captured target"]').count(),0);
 await page.locator('.comparison-side').nth(0).locator('.media-open').click();
 assert.equal(await page.evaluate(()=>state.openMedia.items[state.openMedia.position].sha),base);
 assert.equal(await page.locator('#dialog .large-media img').count(),1);
 await page.click('#dialog [data-action=close]');

 // Ordinary files remain accessible in previews but never enter the media carousel.
 const filePath=path.join(output,'retained-notes.txt');await fs.writeFile(filePath,'Original text evidence remains intact.');
 const imagePath=path.join(output,'retained-preview.png');await fs.writeFile(imagePath,Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kL9sAAAAASUVORK5CYII=','base64'));
 await page.evaluate(async({project,sha,filePath,imagePath})=>{
  for(const [path,kind,title] of [[filePath,'file','Retained notes'],[imagePath,'image','Manual preview']]){
   await api(`/api/projects/${project}/evidence/manual`,{method:'POST',body:JSON.stringify({sha,path,kind,title})});
  }
  state.details.delete(cacheKey(sha));state.tab='preview';await choose(sha);
 },{project,sha,filePath,imagePath});
 assert.equal(await page.locator('#live-content a:has-text("Retained notes")').count(),1);
 await page.locator('#live-content .media-open').first().click();
 const carousel=await page.evaluate(()=>state.openMedia.items.map(item=>({record:item.record,index:item.index,kind:item.kind,sha:item.sha})));
 assert.equal(carousel.length,3);assert.ok(carousel.every(item=>item.kind==='image'));
 assert.equal(new Set(carousel.map(item=>item.record+':'+item.index)).size,3);
 while(!await page.locator('#dialog [data-direction="1"]').isDisabled())await page.click('#dialog [data-direction="1"]');
 assert.equal(await page.locator('#dialog .large-media img').count(),1);
 assert.equal(await page.locator('#dialog .large-media img').evaluate(img=>img.complete&&img.naturalWidth>0),true);
 await page.click('#dialog [data-action=close]');

 // Backend evidence is real; only the asynchronous terminal transitions are controlled.
 const original=await (await page.request.get(new URL(`/api/projects/${project}/versions/${sha}`,url).href)).json();
 let terminalRecord,terminalJob;
 await page.route(`**/api/projects/${project}/versions/${sha}`,async route=>{
  await route.fulfill({json:{...original,evidence:[terminalRecord,...original.evidence]}});
 });
 await page.route('**/api/jobs/evidence-terminal',async route=>{await route.fulfill({json:terminalJob});});
 for(const status of ['partial','failed','cancelled']){
  terminalRecord={...retained,id:terminalRecordId,status,created_at:'2100-01-01',items:status==='failed'?[]:[retained.items.find(item=>item.sha===sha)],errors:status==='cancelled'?[]:[{error:`Terminal ${status} diagnostic`}],warnings:[]};
  terminalJob={id:'evidence-terminal',project_id:project,operation:'capture',request:{sha,base},status:status==='partial'?'failed':status,result:terminalRecord,finished_at:status};
  await page.locator('#tab-preview').focus();
  await page.evaluate(async()=>{await pollWorkspaceJob('evidence-terminal');});
  assert.equal(await page.evaluate(id=>detail(state.selected).evidence[0].id,terminalRecordId),terminalRecordId);
  assert.equal(await page.locator('#live-content .saved-media').count(),status==='failed'?3:4,'Saved output survives terminal failures and cancellation');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'tab-preview','Terminal refresh preserves focus');
  const terminalDiagnostic=page.locator(`#live-content [data-keep-open="capture-${terminalRecordId}"]`);
  if(!await terminalDiagnostic.evaluate(element=>element.open))await terminalDiagnostic.locator('summary').click();
  await page.evaluate(()=>renderDetail());
  assert.equal(await page.locator(`#live-content [data-keep-open="capture-${terminalRecordId}"]`).getAttribute('open'),'');
  assert.ok(await page.locator('#toast').innerText());
 }
 await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('visible'));
 await page.screenshot({path:path.join(output,'evidence-terminal.png'),fullPage:true});
 await page.setViewportSize({width:390,height:900});
 await page.screenshot({path:path.join(output,'evidence-narrow.png'),fullPage:true});
 const narrowDiagnostic=page.locator(`#live-content [data-keep-open="capture-${terminalRecordId}"]`);
 await narrowDiagnostic.screenshot({path:path.join(output,'evidence-narrow-diagnostics.png')});
 assert.equal(await narrowDiagnostic.evaluate(element=>element.scrollWidth<=element.clientWidth),true,'Long local paths wrap inside diagnostics');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'Diagnostics fit a narrow viewport');
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'evidence-result.json'),JSON.stringify({checks:['partial diagnostics','private logs','exact-SHA paired baseline','file excluded from media','terminal refresh','focus and disclosure retention','narrow layout'],errors},null,2));
 console.log(JSON.stringify({ok:true,output}));
}catch(error){
 await page.screenshot({path:path.join(output,'evidence-failure.png'),fullPage:true});
 await fs.writeFile(path.join(output,'evidence-failure.txt'),String(error)+'\n'+await page.locator('body').innerText());
 throw error;
}finally{await browser.close();}
