/* Production workspace regression against an isolated service, with a stub AI. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,project,sha,output]=process.argv.slice(2);
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const snapshot=()=>page.evaluate(()=>repriseWorkspace.snapshot());
try {
 await page.goto(`${url}?project=${project}&sha=${sha}&lang=en`);
 await page.waitForFunction(()=>state.commits.length===2&&detail(state.selected)&&!state.loading);
 assert.equal(await page.locator('#search').getAttribute('placeholder'),'Search commits, files or changes…');
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
 assert.equal(await page.locator('button[data-action=run]').innerText(),'Run this revision');
 assert.equal(await page.locator('.chrome [data-action=language]').count(),0);
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
 await page.click('[data-action=settings]');
 assert.equal(await page.locator('#settings-management').innerText().then(t=>t.includes('This job record cannot be read.')),true);
 assert.equal(await page.locator('#settings-management code').first().innerText(),'broken-record.json');
 await page.evaluate(()=>reviewAI({id:'legacy',project_id:state.project.id,result:{sha:state.selected,model:'legacy-model',title:'old'}}));
 assert.equal(await page.locator('#dialog [role=alert]').innerText(),'This legacy proposal has only one language. Request a new bilingual proposal.');
 assert.equal(await page.locator('[data-action=review-ai-notes]').count(),0);
 await page.click('#dialog [data-action=close]');
 await page.click('[data-action=settings]');
 await page.click('[data-language=zh]');
 assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);
 assert.equal(await page.locator('[data-action=run]').innerText(),'运行此版本');
 await page.click('[data-language=en]');
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
 await page.click('[data-action=settings]');
 await page.click('[data-action=ai-settings]');
 await page.check('#ai-clear-key');
 await page.click('[data-action=save-ai]');
 await page.waitForFunction(()=>document.querySelector('#dialog').open&&document.querySelector('#dialog').classList.contains('settings-dialog'));
 assert.equal((await snapshot()).ai.model,'exact-test-model');
 assert.equal((await snapshot()).ai.has_key,false);
 await page.click('[data-action=ai-settings]');
 await page.click('[data-action=ai-suggest]');
 await page.click('#dialog [data-action=settings]');
 await page.waitForSelector('[data-action=review-ai]',{timeout:20000});
 await page.click('[data-action=review-ai]');
 await page.waitForSelector('[data-action=review-ai-notes]');
 assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);
 assert.equal(await page.evaluate(()=>detail(state.selected).recipe_approved),false);
 await page.click('[data-action=review-ai-notes]');
 await page.click('[data-action=save-notes]');
 await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 assert.equal(await page.locator('.version-name h2').innerText(),'Static site');
 assert.equal(await page.evaluate(()=>detail(state.selected).recipe_approved),false);
 await page.click('[data-action=run]');
 await page.waitForSelector('#recipe-json');
 assert.equal(JSON.parse(await page.locator('#recipe-json').inputValue()).adapter,'static-web');
 await page.click('[data-action=save-recipe]');
 await page.waitForFunction(()=>!document.querySelector('#dialog').open);
 assert.equal(await page.evaluate(()=>detail(state.selected).recipe_approved),true);
 await page.click('[data-action=run]');
 await page.waitForFunction(()=>state.runtimes.some(r=>r.running),null,{timeout:20000});
 await page.click('[data-action=settings]');
 await page.click('[data-action=stop-runtime]');
 await page.waitForFunction(()=>!state.runtimes.some(r=>r.running),null,{timeout:15000});
 await page.click('summary:text-is("Add previews")');
 await page.click('[data-action=capture]');
 await page.waitForFunction(()=>detail(state.selected)?.evidence.some(e=>e.status==='complete'),null,{timeout:30000});
 await page.click('#dialog [data-action=close]');
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
 await page.click('[data-tab=updates]');
 await page.screenshot({path:output+'/desktop-en.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:output+'/mobile-en.png',fullPage:true});
 assert.deepEqual(errors,[]);
 await fs.writeFile(output+'/ui-result.json',JSON.stringify({ok:true,sha,model:'exact-test-model',ai_calls:1,notes_saved:true,recipe_explicitly_approved:true,run_stop:true,capture:true,bookmark_persistence:true,compact_height:32,auto_compare:true,compare_race:true,media_modal:true,mobile_overflow:false,errors},null,2));
} finally {await browser.close();}
