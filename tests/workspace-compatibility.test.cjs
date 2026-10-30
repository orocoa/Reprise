/* The current workbench opens without loading legacy in-app AI settings. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const web = path.resolve(__dirname, '../web');

function harness(language = 'zh') {
  const requests = [], elements = new Map();
  let firstRun = 0;
  const bootstrap = {token: 'test-token', runtimes: [], jobs: [], job_warnings: []};
  Object.defineProperty(bootstrap, 'ai', {get() { throw Error('Legacy AI settings must not be read'); }});
  const context = vm.createContext({
    location: {hash: '', search: '?lang=' + language}, URLSearchParams,
    uiLanguage: language, uiText: value => value, localizeDOM() {},
    contentText: (zh, en) => language === 'en' ? en : zh,
    document: {
      documentElement: {dataset: {}},
      addEventListener() {},
      querySelector(selector) {
        if (!elements.has(selector)) elements.set(selector, {addEventListener() {}, textContent: '', innerHTML: ''});
        return elements.get(selector);
      },
    },
    window: {addEventListener() {}},
    fetch: async url => {
      requests.push(url);
      if (url.startsWith('/api/bootstrap?')) return {ok: true, json: async () => bootstrap};
      if (url.startsWith('/api/workspace/context?')) return {ok: true, json: async () => ({project_id: null})};
      throw Error('Unexpected request: ' + url);
    },
    renderFirstRun() { firstRun++; }, refreshSettingsManagement() {},
    workspaceProjectIds: () => new Set(['project']),
    revisionProject: () => 'project', captureStatus: job => job.status,
  });
  for (const name of ['live-features.js', 'live.js']) {
    vm.runInContext(fs.readFileSync(path.join(web, name), 'utf8'), context, {filename: name});
  }
  return {context, requests, elements, firstRun: () => firstRun};
}

test('first opening and later refresh do not read legacy AI state', async () => {
  const h = harness();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.firstRun(), 1);
  assert.equal(h.elements.get('#detail')?.innerHTML || '', '');
  assert.equal('ai' in h.context.window.repriseWorkspace.snapshot(), false);
  await h.context.refreshWorkspace();
  assert.deepEqual(h.requests, [
    '/api/bootstrap?include_projects=0', '/api/workspace/context?project=', '/api/bootstrap?include_projects=0',
  ]);
  assert.equal(vm.runInContext('Object.hasOwn(state, "ai")', h.context), false);
});

test('historical AI tasks remain visible without unavailable review or retry controls', async () => {
  for (const language of ['zh', 'en']) {
    const h = harness(language);
    await new Promise(resolve => setImmediate(resolve));
    vm.runInContext(`state.jobs=['complete','failed','cancelled'].map(status=>({
      id:status,project_id:'project',operation:'ai/suggest',status,request:{sha:'old-draft'}
    }));`, h.context);
    const html = h.context.renderJobs();
    assert.match(html, language === 'en' ? /AI analysis \(historical task\)/ : /AI 分析（历史任务）/);
    assert.equal((html.match(/data-action="dismiss-job"/g) || []).length, 3);
    assert.doesNotMatch(html, /data-action="(?:review-ai|retry-job|ai-suggest|ai-settings)"/);
    assert.equal(vm.runInContext('state.jobs.length', h.context), 3);
  }
});

test('removed AI actions cannot request a model through the workbench action runner', async () => {
  const h = harness();
  await new Promise(resolve => setImmediate(resolve));
  const before = h.requests.length;
  for (const name of ['ai-settings', 'save-ai', 'ai-suggest', 'ai-suggest-confirm', 'review-ai', 'review-ai-notes', 'review-ai-recipe']) {
    h.context.actionName = name;
    assert.equal(vm.runInContext('Object.hasOwn(featureActions, actionName)', h.context), false);
  }
  await assert.rejects(h.context.startWorkspaceAction('ai/suggest'), /仅支持运行与采集/);
  assert.equal(h.requests.length, before);
});
