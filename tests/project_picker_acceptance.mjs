/* One source can have folder drafts and read-only Git history with the same name. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.REPRISE_PLAYWRIGHT).href);
const [url,file]=process.argv.slice(2),fixture=JSON.parse(await fs.readFile(file,'utf8'));
const browser=await chromium.launch({headless:true,...(process.env.REPRISE_BROWSER?{executablePath:process.env.REPRISE_BROWSER}:{})});
const page=await browser.newPage({viewport:{width:1360,height:900}}),errors=[];
async function openProjectPicker(){
 // The toolbar entry was removed; exercise the retained dialog and its choices.
 await page.evaluate(()=>projectPicker());
 await page.waitForSelector('[data-project-picker]');
}
page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(`${url}?project=${fixture.git}&lang=en`);
 await page.waitForFunction(id=>state.project?.id===id&&!state.loading,fixture.git);
 await openProjectPicker();
 await page.waitForSelector('[data-project-picker]');
 const entry=id=>page.locator(`#dialog [data-action=content-open][data-project="${id}"]`);
 assert.equal(await page.locator('#dialog [data-action=content-open]').count(),2);
 assert.match(await entry(fixture.git).innerText(),/Same webpage[\s\S]*Git history · read only/);
 assert.match(await entry(fixture.folder).innerText(),/Same webpage[\s\S]*Webpage drafts/);
 await page.screenshot({path:fixture.root+'/picker-en.png'});
 await entry(fixture.folder).click();
 await page.waitForFunction(id=>state.project?.id===id&&!state.loading,fixture.folder);
 assert.equal(await page.locator('#content-save').isVisible(),true);
 assert.equal(await page.evaluate(()=>state.commits.length),0,'Selection does not save a checkpoint');
 await openProjectPicker();
 await entry(fixture.git).click();
 await page.waitForFunction(id=>state.project?.id===id&&!state.loading,fixture.git);
 assert.equal(await page.locator('#content-save').isVisible(),false,'Git source stays read-only');
 assert.equal(await page.evaluate(()=>state.commits.length),1);
 await page.click('#settings-toggle');
 await page.waitForSelector('#dialog.settings-dialog');
 await page.click('#dialog [data-language=zh]');
 await page.click('#dialog [data-action=save-settings]');
 await openProjectPicker();
 assert.match(await entry(fixture.git).innerText(),/Git 历史 · 只读/);
 assert.match(await entry(fixture.folder).innerText(),/网页留稿/);
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.locator('#dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
 await page.screenshot({path:fixture.root+'/picker-mobile-zh.png'});
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
