/* Real Git graph geometry, with enough simultaneous branches to grow the gutter. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,project,count,output]=process.argv.slice(2);
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
 await page.goto(`${url}?project=${project}`);
 await page.waitForFunction(n=>state.commits.length===n&&!state.loading&&detail(state.selected),Number(count));
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const baseline=await page.evaluate(()=>JSON.stringify(repriseWorkspace.graph()));
 assert.ok(await page.evaluate(()=>state.graph.laneCount>4));
 const align=async()=>{
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const offsets=await page.evaluate(()=>state.graph.rows.map(n=>{
     const row=document.querySelector(`.version-row[data-id="${n.id}"]`);
     const label=row.querySelector(state.prefs.density==='compact'?'.version-title':'.version-meta');
     const circle=document.querySelector(`[data-node="${n.id}"]`);
     return {sha:n.id,error:Number(circle.getAttribute('cy'))-(row.offsetTop+label.offsetTop+label.offsetHeight/2)};
   }).filter(n=>Math.abs(n.error)>.1));
   assert.deepEqual(offsets,[],'Graph must measure rows after reserving its wider gutter');
   assert.equal(await page.evaluate(()=>JSON.stringify(repriseWorkspace.graph())),baseline);
   assert.equal(await page.locator('#route-map path').count(),await page.evaluate(()=>state.commits.reduce((n,c)=>n+c.parents.length,0)));
 };
 await page.screenshot({path:`${output}/wide-initial.png`});
 await align();
 // Exercise multiline content independently of today's summary truncation style.
 await page.addStyleTag({content:'.version-summary{white-space:normal}'});
 // One projection must reserve its width before measuring, even on the first draw.
 await page.evaluate(()=>{document.querySelector('#history-track').style.setProperty('--graph-gutter','78px');drawGraph();});
 await align();
 await page.screenshot({path:`${output}/wide-variable-rows.png`});
 await page.click('[data-density=compact]');
 await align();
 await page.click('[data-density=full]');
 await align();
 await page.fill('#search','no-match-graph-441');
 await page.waitForFunction(()=>!state.searching&&document.querySelectorAll('.context-row').length===state.commits.length);
 await align();
 await page.click('[data-action=clear-search]');
 await page.setViewportSize({width:390,height:844});
 await align();
 await page.screenshot({path:`${output}/wide-mobile.png`});
 assert.deepEqual(errors,[]);
 await fs.writeFile(`${output}/graph-browser.json`,JSON.stringify({commits:Number(count),passed:true},null,2));
} finally {
 await browser.close();
}
