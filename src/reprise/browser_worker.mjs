// Deterministic browser capture protocol. Reads one JSON file, writes one result file.
// No AI, arbitrary page-evaluate recipe hooks, or shell-generated commands.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output = { items: [], errors: [], warnings: [], runner: 'reprise-playwright-v3' };
let browser, browserServer;
let cancelled = false;
process.on('SIGTERM', () => {
  cancelled = true;
  // Closing the browser interrupts long waits and lets finally retain results.
  if (browserServer) browserServer.close().catch(() => {});
});
function identityFor(pid) {
  try {
    if (fs.existsSync(`/proc/${pid}/stat`)) {
      const content = fs.readFileSync(`/proc/${pid}/stat`, 'utf8');
      const fields = content.slice(content.lastIndexOf(')') + 2).split(/\s+/);
      return fields[0] === 'Z' ? null : 'linux:' + fields[19];
    }
    const content = execFileSync('ps', ['-p', String(pid), '-o', 'lstart=', '-o', 'stat='], {encoding: 'utf8'}).trim();
    const state = content.split(/\s+/).at(-1);
    return state?.startsWith('Z') ? null : 'ps:' + content.replace(/\s+\S+$/, '').trim();
  } catch { return null; }
}
const message = error => String(error?.message || error).slice(0, 5000);
const localURL = url => {
  try {
    const parsed = new URL(url);
    if (['data:', 'blob:', 'about:'].includes(parsed.protocol)) return true;
    if (parsed.protocol === 'ws:') parsed.protocol = 'http:';
    if (parsed.protocol === 'wss:') parsed.protocol = 'https:';
    return parsed.origin === new URL(input.url).origin;
  } catch { return false; }
};
function pngSize(file) {
  const data = fs.readFileSync(file);
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
}
async function ready(page, timeout) {
  const readiness = await page.evaluate(async timeout => {
    const timed = async (promise, label) => Promise.race([
      promise.then(() => null, e => `${label}: ${e?.message || e}`),
      new Promise(resolve => setTimeout(() => resolve(`${label}: timed out`), timeout))
    ]);
    const failures = [];
    const fonts = await timed(document.fonts?.ready || Promise.resolve(), 'fonts');
    if (fonts) failures.push(fonts);
    // Decode rendered images. Unloaded lazy images outside the visible area do not
    // prove an error; full-page mode scrolls the page before calling this function.
    const images = Array.from(document.images).filter(img => {
      const box = img.getBoundingClientRect();
      return img.loading !== 'lazy' || (box.top < innerHeight && box.bottom > 0) || img.complete;
    });
    await Promise.all(images.map(async image => {
      const issue = await timed((async () => {
        if (!image.complete) await new Promise((resolve, reject) => {
          image.addEventListener('load', resolve, {once: true});
          image.addEventListener('error', () => reject(new Error('load failed')), {once: true});
        });
        if (!image.naturalWidth) throw new Error('missing or undecodable image');
        if (image.decode) await image.decode();
      })(), image.currentSrc || image.src || 'image');
      if (issue) failures.push(issue);
    }));
    const videos = Array.from(document.querySelectorAll('video')).filter(video => {
      const box = video.getBoundingClientRect(), style = getComputedStyle(video);
      return box.width > 0 && box.height > 0 && box.top < innerHeight && box.bottom > 0 &&
        box.left < innerWidth && box.right > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    });
    const media = [];
    await Promise.all(videos.map(async video => {
      const source = video.currentSrc || video.getAttribute('src') || video.querySelector('source[src]')?.src;
      // Empty video elements are application placeholders, not loaded media.
      if (!source && !video.srcObject) return;
      const label = 'video ' + (source || '[live srcObject]');
      const issue = await timed((async () => {
        if (video.poster) {
          const poster = new Image();
          poster.src = video.poster;
          await poster.decode();
        }
        await new Promise((resolve, reject) => {
          const events = ['loadedmetadata', 'loadeddata', 'canplay', 'progress', 'error', 'emptied'];
          let timer;
          const finish = error => {
            clearTimeout(timer);
            for (const event of events) video.removeEventListener(event, check);
            error ? reject(error) : resolve();
          };
          const check = () => {
            if (video.error) return finish(new Error('media error ' + video.error.code + ': ' + (video.error.message || 'unavailable or undecodable source')));
            if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) finish();
          };
          for (const event of events) video.addEventListener(event, check);
          timer = setTimeout(() => finish(new Error('metadata/current frame did not become ready (readyState=' + video.readyState + ')')), timeout);
          // Request bytes without autoplay or changing the selected playback time.
          // preload=none otherwise deliberately leaves a valid source unread.
          const unloaded = video.readyState === 0 && video.networkState !== 2;
          video.preload = 'auto';
          if (unloaded) video.load();
          check();
        });
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        media.push({type: 'video', source: video.currentSrc || source || '[live srcObject]',
          video_width: video.videoWidth, video_height: video.videoHeight,
          duration: Number.isFinite(video.duration) ? video.duration : null,
          ready_state: video.readyState, current_time: video.currentTime, paused: video.paused,
          poster: video.poster || null});
      })(), label);
      if (issue) failures.push(issue);
    }));
    return {failures, media};
  }, Math.min(timeout, 15000));
  if (readiness.failures.length) throw new Error(readiness.failures.slice(0, 20).join('\n'));
  return readiness.media;
}

try {
  const req = createRequire(import.meta.url);
  const moduleName = process.env.REPRISE_PLAYWRIGHT || 'playwright';
  let resolved;
  try { resolved = req.resolve(moduleName); }
  catch {
    try { resolved = createRequire(path.join(process.cwd(), 'package.json')).resolve(moduleName); }
    catch { throw new Error('Playwright is unavailable. Run npm install playwright and npx playwright install chromium, or set REPRISE_PLAYWRIGHT to its installed module path. Manual evidence remains available.'); }
  }
  const playwright = await import(pathToFileURL(resolved).href);
  const chromium = playwright.chromium || playwright.default?.chromium;
  if (!chromium) throw new Error('The configured Playwright module does not provide chromium.');
  const options = { headless: true, args: ['--enable-unsafe-swiftshader'] };
  if (process.env.REPRISE_BROWSER) options.executablePath = process.env.REPRISE_BROWSER;
  if (cancelled) throw new Error('Capture cancelled');
  try {
    browserServer = await chromium.launchServer(options);
    const pid = browserServer.process().pid;
    fs.writeFileSync(input.browser_process_path, JSON.stringify({pid, process_identity: identityFor(pid)}));
    if (cancelled) throw new Error('Capture cancelled');
    browser = await chromium.connect(browserServer.wsEndpoint());
  }
  catch (error) { throw new Error(`Chromium could not start. Install it with npx playwright install chromium or set REPRISE_BROWSER. ${message(error)}`); }
  output.browser_version = browser.version();
  for (const scenario of input.recipe.captures) {
    if (cancelled) break;
    let context, page, video;
    let mediaReadiness = [];
    const errors = [], blocked = new Set(), responses = new Set(), pageErrors = new Set();
    const prefix = `${input.side}-${scenario.id}`;
    try {
      const vp = scenario.viewport;
      const contextOptions = { viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.scale,
        serviceWorkers: 'block', locale: 'en-US', timezoneId: 'UTC', reducedMotion: 'reduce' };
      if (scenario.record) contextOptions.recordVideo = { dir: input.output_dir, size: { width: vp.width, height: vp.height } };
      context = await browser.newContext(contextOptions);
      if (input.recipe.network === 'local') {
        await context.route('**/*', route => {
          if (localURL(route.request().url())) return route.continue();
          blocked.add(route.request().url());
          return route.abort('blockedbyclient');
        });
        if (typeof context.routeWebSocket === 'function') await context.routeWebSocket('**/*', ws => {
          if (localURL(ws.url())) ws.connectToServer();
          else { blocked.add(ws.url()); ws.close(); }
        });
      }
      page = await context.newPage();
      page.setDefaultTimeout(input.recipe.readiness.timeout_ms);
      page.setDefaultNavigationTimeout(input.recipe.readiness.timeout_ms);
      page.on('response', response => { if (response.status() >= 400) responses.add(`${response.status()} ${response.url()}`); });
      page.on('pageerror', error => pageErrors.add(message(error)));
      video = page.video();
      const response = await page.goto(new URL(scenario.route, input.url).href, { waitUntil: 'domcontentloaded' });
      if (!response || response.status() >= 400) throw new Error(`Route did not load successfully: ${scenario.route} (${response?.status() || 'no HTTP response'})`);
      if (input.recipe.readiness.selector) await page.locator(input.recipe.readiness.selector).first().waitFor({ state: 'visible' });
      if (scenario.wait_for) await page.locator(scenario.wait_for).first().waitFor({ state: 'visible' });
      await ready(page, input.recipe.readiness.timeout_ms);
      for (const step of scenario.steps) {
        console.log(`Capture step started: ${step.action}`);
        if (step.action === 'click') await page.locator(step.selector).first().click();
        else if (step.action === 'fill') await page.locator(step.selector).first().fill(step.value);
        else if (step.action === 'press') {
          if (step.selector) await page.locator(step.selector).first().press(step.key);
          else await page.keyboard.press(step.key);
        } else if (step.action === 'wait') await page.waitForTimeout(step.ms);
      }
      if (scenario.full_page) {
        const original = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
        // Trigger lazy assets and bounded reveal animations without infinitely
        // walking an infinite feed. A larger document is explicitly diagnosed.
        const height = await page.evaluate(() => document.documentElement.scrollHeight);
        if (height > 40000 || height * vp.width * vp.scale * vp.scale > 100000000) throw new Error('Full-page image exceeds the capture size limit. Use viewport screenshots or a narrower viewport; a diagnostic viewport image is retained.');
        for (let y = 0; y < Math.min(height, 40000); y += vp.height) {
          await page.evaluate(y => scrollTo(0, y), y);
          await ready(page, input.recipe.readiness.timeout_ms);
        }
        await page.evaluate(pos => scrollTo(pos.x, pos.y), original);
      }
      if (scenario.record) await page.waitForTimeout(scenario.record_ms ?? 1000);
      mediaReadiness = await ready(page, input.recipe.readiness.timeout_ms);
      const file = path.join(input.output_dir, `${prefix}.png`);
      await page.screenshot({ path: file, fullPage: scenario.full_page, animations: 'disabled', timeout: input.recipe.readiness.timeout_ms });
      output.items.push({ capture_id: scenario.id, side: input.side, sha: input.sha, path: file, media_type: 'image/png',
        ...pngSize(file), viewport: vp, full_page: scenario.full_page, route: scenario.route,
        title: scenario.id, captured_at: new Date().toISOString(), media_readiness: mediaReadiness });
    } catch (error) {
      errors.push(message(error));
      if (page && !page.isClosed()) {
        try {
          const file = path.join(input.output_dir, `${prefix}-diagnostic.png`);
          await page.screenshot({ path: file, timeout: 5000 });
          output.items.push({ capture_id: scenario.id, side: input.side, sha: input.sha, path: file,
            media_type: 'image/png', ...pngSize(file), diagnostic: true, route: scenario.route,
            title: scenario.id + ' (failed readiness)', captured_at: new Date().toISOString() });
        } catch { /* Preserve the original actionable error. */ }
      }
    } finally {
      if (context) {
        try { await context.close(); } catch (error) { errors.push(message(error)); }
      }
      if (video) {
        try {
          const file = path.join(input.output_dir, `${prefix}.webm`);
          await video.saveAs(file);
          output.items.push({ capture_id: scenario.id, side: input.side, sha: input.sha, path: file, media_type: 'video/webm',
            width: scenario.viewport.width, height: scenario.viewport.height, viewport: scenario.viewport,
            route: scenario.route, title: scenario.id + ' recording', captured_at: new Date().toISOString(),
            diagnostic: errors.length > 0, media_readiness: mediaReadiness });
        } catch (error) { errors.push(message(error)); }
      }
    }
    for (const item of responses) errors.push('Asset or API request failed: ' + item);
    for (const item of blocked) errors.push('Blocked external request (network=local): ' + item);
    for (const item of pageErrors) errors.push('Page JavaScript error: ' + item);
    if (errors.length) for (const item of output.items) {
      if (item.capture_id === scenario.id && item.side === input.side) item.diagnostic = true;
    }
    for (const error of errors) output.errors.push({ capture_id: scenario.id, side: input.side, error });
  }
} catch (error) {
  output.errors.push({ side: input.side, error: message(error) });
} finally {
  if (browser) await browser.close().catch(error => output.errors.push({ error: message(error) }));
  if (browserServer) await browserServer.close().catch(error => output.errors.push({ error: message(error) }));
  fs.writeFileSync(input.result_path, JSON.stringify(output, null, 2));
}
