/* Large real Git DAG: exact edges, fixed compact view and bounded picture paging. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url),{verifyGraph}=require('./graph-contract.cjs');
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,fixturePath]=process.argv.slice(2),fixture=JSON.parse(await fs.readFile(fixturePath,'utf8'));
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(project=>localStorage.setItem(`reprise-live-prefs:${project}`,JSON.stringify({density:'full',historyView:'graph',stars:[]})),fixture.project);
const frame=()=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
const selectedVisible=()=>page.evaluate(()=>{
 const box=document.querySelector(state.prefs.historyView==='pictures'?'.draft-card.selected':'.version-row.selected')?.getBoundingClientRect();
 const view=document.querySelector(state.prefs.historyView==='pictures'?'#draft-list':'#history-scroll').getBoundingClientRect();
 return !!box&&box.top>=view.top-1&&box.bottom<=view.bottom+1;
});
try{
 const started=Date.now();
 await page.goto(`${url}?project=${fixture.project}`);
 await page.waitForFunction(n=>state.commits.length===n&&!state.loading&&!!detail(state.selected),fixture.expected.length,{timeout:45000});
 await frame();
 const readyMs=Date.now()-started,graph=await page.evaluate(()=>repriseWorkspace.graph()),baseline=JSON.stringify(graph);
 verifyGraph(fixture.expected,graph);
 assert.equal(await page.locator('[data-density]').count(),0);
 assert.equal(await page.evaluate(()=>state.prefs.density),'compact','A saved detailed-view preference cannot restore removed controls');
 assert.equal(await page.locator('.version-row').count(),fixture.expected.length);
 const geometry=await page.evaluate(()=>({
  bad:state.graph.rows.filter(n=>{
   const row=document.querySelector(`.version-row[data-id="${n.id}"]`),label=row.querySelector('.version-title'),circle=document.querySelector(`[data-node="${n.id}"]`);
   return row.offsetHeight!==32||label.clientWidth<180||Math.abs(Number(circle.getAttribute('cy'))-(row.offsetTop+label.offsetTop+label.offsetHeight/2))>.1;
  }).map(n=>n.id),
  lanes:state.graph.laneCount,sidebarWidth:document.querySelector('.history').clientWidth,
  trackWidth:document.querySelector('#history-track').clientWidth,
  documentOverflow:document.documentElement.scrollWidth>innerWidth
 }));
 assert.deepEqual(geometry.bad,[],'Every row remains readable and every circle is aligned, including deep history');
 assert.equal(geometry.documentOverflow,false);
 await page.screenshot({path:fixture.root+'/large-desktop.png'});
 const oldest=fixture.expected[0].id;
 await page.click(`.version-row[data-id="${oldest}"]`);
 await page.waitForFunction(sha=>state.selected===sha&&!!detail(sha),oldest);
 await frame();assert.equal(await selectedVisible(),true);
 await page.click('[data-action="draft-view"][data-view="pictures"]');
 await frame();assert.equal(await selectedVisible(),true,'An old selection beyond the first 60 thumbnails remains visible');
 assert.equal(await page.locator('.draft-card').count(),61,'Do not render all 1301 picture cards to locate an old draft');
 assert.equal(await page.locator('.draft-gap').count(),1);
 await page.click('[data-action="draft-view"][data-view="graph"]');
 await frame();assert.equal(await selectedVisible(),true);
 const searchStarted=Date.now();
 await page.fill('#search','no-match-large-history-441');
 await page.waitForFunction(n=>state.searching||state.searchIndex.size>=n,fixture.expected.length,{timeout:10000});
 const progress=await page.evaluate(()=>({active:state.searching,label:document.querySelector('#search-progress')?.textContent||''}));
 if(progress.active)assert.match(progress.label,/1301/);
 await page.waitForFunction(n=>!state.searching&&document.querySelectorAll('.context-row').length===n,fixture.expected.length,{timeout:45000});
 const searchMs=Date.now()-searchStarted;
 assert.equal(await page.evaluate(()=>JSON.stringify(repriseWorkspace.graph())),baseline);
 await page.click('[data-action="clear-search"]');
 await page.waitForFunction(()=>!state.searching&&!document.querySelector('#search').value);
 const middle=graph.rows[Math.floor(graph.rows.length/2)].id;
 await page.click(`.version-row[data-id="${middle}"]`);
 await page.waitForFunction(sha=>state.selected===sha&&!!detail(sha),middle);
 await page.screenshot({path:fixture.root+'/large-middle.png'});
 await page.setViewportSize({width:390,height:844});await frame();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.equal(await page.evaluate(()=>[...document.querySelectorAll('.version-title')].every(x=>x.clientWidth>=180)),true);
 assert.equal(await page.locator('#graph-width-hint').isVisible(),true,'Wide real branches explain horizontal scrolling on mobile');
 await page.screenshot({path:fixture.root+'/large-mobile.png'});
 await page.locator('#history-scroll').evaluate(el=>{el.scrollLeft=el.scrollWidth;});
 assert.equal(await page.evaluate(()=>{const view=document.querySelector('#history-scroll').getBoundingClientRect(),title=document.querySelector('.version-row.selected .version-title').getBoundingClientRect();return title.left>=view.left&&title.right<=view.right;}),true,'Wide titles are reachable with the documented horizontal scroll');
 await page.screenshot({path:fixture.root+'/large-mobile-titles.png'});
 assert.deepEqual(errors,[]);
 await fs.writeFile(fixture.root+'/graph-scale-result.json',JSON.stringify({passed:true,commits:graph.rows.length,edges:graph.edges.length,merges:graph.rows.filter(n=>n.isMerge).length,readyMs,searchMs,geometry,oldSelectionAcrossViews:true,boundedPictureCards:61,filterPreservesDAG:true,mobileNoPageOverflow:true,errors},null,2));
}finally{await browser.close();}
