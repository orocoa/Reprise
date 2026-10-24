/* Preview planning and language changes never approve or execute commands. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const web = path.resolve(__dirname, '../web');
const plan = {status: 'needs-approval', root: 'site', reason: 'vite-command-approval',
  recipe: {commands: {install: [['npm', 'ci']], start: ['npm', 'run', 'dev']}},
  execution: {scripts: {dev: 'vite'}}};

function harness(response = () => Promise.resolve(plan)) {
  const requests = [], body = {innerHTML: ''}, footer = {innerHTML: ''};
  const dialog = {open: false, dataset: {}, classList: {contains: () => false}};
  const state = {project: {id: 'project'}, selected: 'draft', dialogRequest: 0,
    historySources: [], commits: [{sha: 'draft'}]};
  const context = vm.createContext({state, uiLanguage: 'zh', workspaceActions: {},
    URL, URLSearchParams, location: {href: 'http://127.0.0.1/?lang=zh'},
    history: {replaceState() {}}, localStorage: {setItem() {}},
    document: {addEventListener() {}}, window: {addEventListener() {}}, dialogParent: null,
    $: selector => ({'#dialog': dialog, '#dialog .dialog-body': body,
      '#dialog .dialog-footer': footer, '#history-origin': {}}[selector] || null),
    revisionProject: () => state.project.id, query: (url, values) => url + '?' + new URLSearchParams(values),
    api: (url, options) => {requests.push({url, method: options?.method || 'GET'}); return response(requests.length);},
    commit: sha => ({sha, subject: 'Saved draft'}), versionTitle: c => c.subject, esc: String,
    renderHistory() {}, keepSelectedHistoryVisible() {}, renderDetail() {},
    localizeDOM() {}, refreshContentStatus() {}, notify: message => assert.fail(message),
    dialogShell(_title, content, buttons = '') {
      state.dialogRequest++; dialog.open = true; dialog.dataset = {};
      body.innerHTML = content; footer.innerHTML = buttons;
    },
  });
  vm.runInContext(`contentText=(zh,en)=>uiLanguage==='en'?en:zh;
    previewLanguageControls=()=>'<button data-action="language" data-language="zh">中文</button><button data-action="language" data-language="en">English</button>';`, context);
  for (const name of ['live-drafts.js', 'live-parity.js']) {
    vm.runInContext(fs.readFileSync(path.join(web, name), 'utf8'), context, {filename: name});
  }
  return {context, state, requests, body, footer, dialog};
}

test('language rebuild keeps the exact preview target and root, with GET requests only', async () => {
  const h = harness();
  await h.context.quickPreviewDialog('site');
  assert.match(h.body.innerHTML, /data-action="language"/);
  assert.match(h.footer.innerHTML, /批准以上命令并截图/);
  h.context.changeLanguage('en');
  await new Promise(resolve => setImmediate(resolve));
  assert.match(h.body.innerHTML, /This Vite webpage needs dependencies/);
  assert.match(h.footer.innerHTML, /Approve these commands and capture/);
  assert.equal(h.state.quickPreviewTarget.project, 'project');
  assert.equal(h.state.quickPreviewTarget.sha, 'draft');
  assert.equal(h.state.quickPreviewTarget.root, 'site');
  assert.equal(h.state.quickPreviewTarget.recipe, plan.recipe);
  assert.deepEqual(h.requests, Array(2).fill({url: '/api/projects/project/quick-preview?sha=draft&root=site', method: 'GET'}));
});

test('changing language while planning ignores the older response and preserves the chosen root', async () => {
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const h = harness(count => count === 1 ? pending : Promise.resolve(plan));
  const first = h.context.quickPreviewDialog('site');
  h.context.changeLanguage('en');
  await new Promise(done => setImmediate(done));
  resolve({...plan, root: 'wrong-old-response'}); await first;
  assert.equal(h.state.quickPreviewTarget.root, 'site');
  assert.match(h.footer.innerHTML, /Approve these commands and capture/);
  assert.ok(h.requests.every(request => request.method === 'GET'));
});

test('late plans cannot install approval controls after a project or revision change', async () => {
  let resolve;
  const h = harness(() => new Promise(done => { resolve = done; }));
  const pending = h.context.quickPreviewDialog('site');
  h.state.project = {id: 'other'}; h.state.selected = 'other-draft';
  resolve(plan); await pending;
  assert.doesNotMatch(h.footer.innerHTML, /approve-draft-preview/);
  assert.equal(h.state.quickPreviewTarget.recipe, null);
  const before = h.requests.length;
  await h.context.quickPreviewDialog('site', {project: 'project', sha: 'draft'});
  assert.equal(h.requests.length, before);
});

test('missing npm lockfile gives an actionable bilingual reason without approval controls', async () => {
  const h = harness(() => Promise.resolve({status: 'needs-configuration', root: 'site', reason: 'missing-npm-lockfile'}));
  await h.context.quickPreviewDialog('site');
  assert.match(h.body.innerHTML, /没有 package-lock.json/);
  assert.match(h.body.innerHTML, /保存新稿/);
  h.context.changeLanguage('en');
  await new Promise(resolve => setImmediate(resolve));
  assert.match(h.body.innerHTML, /no package-lock.json/);
  assert.match(h.body.innerHTML, /save a new draft/);
  assert.doesNotMatch(h.footer.innerHTML, /approve-draft-preview/);
  assert.ok(h.requests.every(request => request.method === 'GET'));
});

test('available Vite entries are labeled as needing approval rather than direct capture', async () => {
  const h = harness(() => Promise.resolve({status: 'choose-entry', candidates: [
    {root: 'site', entry: 'site/index.html', framework: 'vite', available: true},
  ]}));
  await h.context.quickPreviewDialog();
  assert.match(h.body.innerHTML, /需批准运行命令/);
  assert.doesNotMatch(h.body.innerHTML, /可直接截图/);
  assert.doesNotMatch(h.footer.innerHTML, /approve-draft-preview/);
});
