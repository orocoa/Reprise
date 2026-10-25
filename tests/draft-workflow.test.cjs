/* Regressions for draft actions crossing asynchronous workspace boundaries. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const web = path.resolve(__dirname, '../web');
const read = name => fs.readFileSync(path.join(web, name), 'utf8');

function productionFunction(context, file, start, end) {
  const source = read(file);
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first, `${file}: production function boundaries`);
  vm.runInContext(source.slice(first, last), context, {filename: file});
}

function delayed() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

test('legacy detailed history preferences retain selection settings but use the one relationship layout', () => {
  const state={prefs:{}};
  const context=vm.createContext({state,key:()=> 'project',localStorage:{getItem:()=>JSON.stringify({density:'full',historyView:'graph',stars:['old-sha'],main:'refs/heads/main'})}});
  productionFunction(context,'live.js','function readPrefs()','function savePrefs()');
  context.readPrefs();
  assert.equal(state.prefs.density,'compact');
  assert.equal(state.prefs.historyView,'graph');
  assert.deepEqual(Array.from(state.prefs.stars),['old-sha']);
  assert.equal(state.prefs.main,'refs/heads/main');
});

test('an older selected picture is included without rendering the entire long history', () => {
  const commits=Array.from({length:1301},(_,i)=>({sha:`sha-${i}`,subject:`Draft ${i}`,committed_at:'2026-10-26'}));
  const list={innerHTML:'',scrollTop:0},state={project:{id:'project',kind:'git'},commits,selected:'sha-1300',prefs:{historyView:'pictures',stars:[]}};
  const context=vm.createContext({state,workspaceActions:{},uiCopy:{},$:s=>s==='#draft-list'?list:s==='.history'?{classList:{toggle(){}}}:{},$$:()=>[],captureViewFocus:()=>null,restoreViewFocus(){},results:()=>commits,contentText:(zh,en)=>en,esc:String,icon:()=>'',versionTitle:c=>c.subject,formatDate:s=>s,revisionProject:()=> 'project'});
  vm.runInContext(read('live-drafts.js'),context);
  context.renderDraftHistory();
  assert.equal((list.innerHTML.match(/data-action="draft-select"/g)||[]).length,61);
  assert.match(list.innerHTML,/data-id="sha-1300"/);
  assert.match(list.innerHTML,/1240 drafts skipped/);
});

test('late quick-capture acceptance tracks the job without closing a newer dialog', async () => {
  const response = delayed();
  const effects = [];
  const state = {
    project: {id: 'project-a'}, selected: 'sha-a', tab: 'preview', dialogRequest: 1,
    quickPreviewTarget: {project: 'project-a', sha: 'sha-a', root: '.'},
  };
  const context = vm.createContext({
    state, workspaceActions: {}, uiCopy: {},
    revisionProject: () => state.project.id,
    api: () => response.promise,
    contentText: zh => zh,
    $: () => ({open: true}),
    mergeWorkspaceJobs: jobs => effects.push(['retained', jobs[0].id]),
    closeDialog: () => effects.push(['closed']),
    renderDetail: () => effects.push(['rendered', state.project.id]),
    notify() {},
    pollWorkspaceJob: id => effects.push(['tracked', id]),
  });
  vm.runInContext(read('live-drafts.js'), context, {filename: 'live-drafts.js'});

  const pending = context.workspaceActions['save-quick-preview']();
  // The user leaves the first modal and opens a different project's comparison.
  state.project = {id: 'project-b'};
  state.selected = 'sha-b';
  state.tab = 'compare';
  state.dialogRequest++;
  response.resolve({id: 'capture-for-a'});
  await pending;

  assert.equal(state.selected, 'sha-b');
  assert.equal(state.tab, 'compare');
  assert.deepEqual(effects, [['retained', 'capture-for-a'], ['tracked', 'capture-for-a']]);
});

test('clicking the current picture cancels an older comparison targeting another draft', async () => {
  const response = delayed();
  const commits = new Map(['a', 'b'].map(sha => [sha, {sha}]));
  const element = {scrollTop: 0, value: '', innerHTML: '', focus() {}};
  const state = {
    project: {id: 'project'}, selected: 'a', tab: 'compare', comparison: null,
    comparisonRequest: 0, comparisonDraft: {base: 'a', target: 'b'},
    comparisonLoading: false, comparisonError: null, query: '', filter: 'all',
  };
  const context = vm.createContext({
    state, workspaceActions: {}, uiCopy: {}, URL, AbortController,
    location: {href: 'http://localhost/?project=project'}, history: {replaceState() {}},
    commit: id => commits.get(id), match: () => true, $: () => element,
    notify() {}, renderHistory() {}, renderDetail() {}, requestAnimationFrame() {},
    loadDetail: async sha => ({commit: {sha}}), prepareGraph() {},
    api: () => response.promise, query: () => '',
    comparisonSelection: () => state.comparisonDraft, contentText: zh => zh,
  });
  vm.runInContext('let detailAbort, selectRequest = 0;', context);
  productionFunction(context, 'live.js', 'async function choose(', 'async function searchAll(');
  productionFunction(context, 'live-features.js',
    'async function applyComparison(', 'function renderComparison(');
  productionFunction(context, 'live-focus.js',
    'async function setDetailTab(', 'async function changeComparison(');
  vm.runInContext(read('live-drafts.js'), context, {filename: 'live-drafts.js'});

  const comparison = context.applyComparison('a', 'b');
  await context.workspaceActions['draft-select']({dataset: {id: 'a'}});
  assert.equal(state.selected, 'a');
  response.resolve({base: 'a', target: 'b', source_project_id: 'project'});
  await comparison;

  assert.equal(state.selected, 'a', 'late comparison must not select draft B');
  assert.equal(state.tab, 'preview');
  assert.equal(state.comparisonLoading, false);
  assert.equal(state.comparison, null);
});

test('manual evidence refreshes picture history even after its dialog was closed', async () => {
  const saved = delayed();
  const requests = [];
  const image = {sha: 'draft', url: '/artifacts/manual.png', source: 'manual'};
  const fields = {
    '#manual-path': {value: '/local/manual.png'}, '#manual-kind': {value: 'image'},
    '#manual-title': {value: 'My screenshot'}, '#manual-capture': {value: ''},
    '#dialog': {open: true},
  };
  const state = {
    project: {id: 'project'}, selected: 'draft', dialogRequest: 1, details: new Map(),
    commits: [{sha: 'draft', source_project_id: 'project'}],
    manualTarget: {project: 'project', sha: 'draft'},
  };
  let rendered = 0;
  const context = vm.createContext({
    state, workspaceActions: {}, uiCopy: {}, $: selector => fields[selector],
    revisionProject: () => state.project.id,
    workspaceProjectIds: () => new Set(['project']),
    api: (url, options) => {
      requests.push([url, options?.method || 'GET']);
      if (options?.method === 'POST') return saved.promise;
      assert.equal(url, '/api/projects/project/visual-history');
      return Promise.resolve({images: {draft: image}});
    },
    loadDetail: async () => {}, notify() {},
    closeDialog: () => assert.fail('the newer dialog must remain untouched'),
    renderDetail: () => assert.fail('a completed background copy must not change the tab'),
    countRender: () => { rendered++; },
  });
  vm.runInContext(read('live-drafts.js'), context, {filename: 'live-drafts.js'});
  vm.runInContext('renderDraftHistory = countRender;', context);
  productionFunction(context, 'live-features.js',
    'async function saveManualEvidence(', 'function mergeWorkspaceJobs(');

  const pending = context.saveManualEvidence();
  state.dialogRequest++;
  fields['#dialog'].open = false;
  saved.resolve({status: 'complete'});
  await pending;
  // The production handler starts the history read without awaiting its render.
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(requests, [
    ['/api/projects/project/evidence/manual', 'POST'],
    ['/api/projects/project/visual-history', 'GET'],
  ]);
  assert.equal(context.draftImage({sha: 'draft'}).url, image.url);
  assert.equal(context.draftImage({sha: 'draft'}).source, 'manual');
  assert.equal(rendered, 1);
});

test('Vite approval saves the displayed exact-version recipe before capture and keeps newer navigation', async () => {
  const saved = delayed(), requests = [], effects = [];
  const recipe = {adapter: 'command-web', commands: {start: ['npm', 'run', 'dev']}};
  const state = {project: {id: 'a'}, selected: 'first', dialogRequest: 1, details: new Map(),
    quickPreviewTarget: {project: 'a', sha: 'first', recipe}};
  const context = vm.createContext({state, workspaceActions: {},
    revisionProject: () => state.project.id, contentText: zh => zh, $: () => ({open: true}),
    api: (url, options) => {requests.push([url, options.method, JSON.parse(options.body)]);
      return options.method === 'PUT' ? saved.promise : Promise.resolve({id: 'capture-first'});},
    loadDetail: async () => {},
    mergeWorkspaceJobs: jobs => effects.push(['retained', jobs[0].id]),
    closeDialog: () => effects.push(['closed']), renderDetail: () => effects.push(['rendered']),
    notify() {}, pollWorkspaceJob: id => effects.push(['tracked', id]),
  });
  vm.runInContext(read('live-drafts.js'), context);
  const pending = context.workspaceActions['approve-draft-preview']();
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0], ['/api/projects/a/recipe', 'PUT', {sha: 'first', recipe}]);
  state.project = {id: 'b'}; state.selected = 'other'; state.dialogRequest++;
  saved.resolve({}); await pending;
  assert.deepEqual(requests[1], ['/api/projects/a/capture', 'POST', {sha: 'first'}]);
  assert.deepEqual(effects, [['retained', 'capture-first'], ['tracked', 'capture-first']]);
});

test('failed recipe persistence cannot start a Vite capture', async () => {
  const requests = [];
  const state = {selected: 'first', dialogRequest: 1, details: new Map(),
    quickPreviewTarget: {project: 'a', sha: 'first', recipe: {adapter: 'command-web'}}};
  const context = vm.createContext({state, workspaceActions: {}, revisionProject: () => 'a',
    contentText: zh => zh, api: async (url) => {requests.push(url); throw Error('Save failed');}});
  vm.runInContext(read('live-drafts.js'), context);
  await assert.rejects(context.workspaceActions['approve-draft-preview'](), /Save failed/);
  assert.deepEqual(requests, ['/api/projects/a/recipe']);
});

test('a rejected Vite capture leaves saved recipe details available for explicit retry', async () => {
  const requests = [], recipe = {adapter: 'command-web'}, kept = {marker: 'unrelated'};
  const state = {project: {id: 'a'}, selected: 'first', dialogRequest: 1,
    details: new Map([['a:first', {recipe_approved: false}], ['b:other', kept]]), jobs: [],
    quickPreviewTarget: {project: 'a', sha: 'first', recipe}};
  let persisted = false, captureAttempts = 0;
  const context = vm.createContext({state, workspaceActions: {}, revisionProject: () => 'a',
    contentText: zh => zh, $: () => ({open: true}),
    api: async (url, options) => {
      requests.push([url, options.method]);
      if (options.method === 'PUT') { persisted = true; return {}; }
      if (++captureAttempts === 1) throw Error('Project already has a task');
      return {id: 'explicit-retry'};
    },
    loadDetail: async (sha, _signal, project) => {
      assert.equal(persisted, true);
      state.details.set(`${project}:${sha}`, {recipe, recipe_approved: true});
    },
    detail: sha => state.details.get(`a:${sha}`),
    renderDetail() {}, refreshSettingsManagement() {}, notify() {},
  });
  for (const file of ['live-features.js', 'live-drafts.js']) vm.runInContext(read(file), context);
  vm.runInContext('pollWorkspaceJob=()=>{};', context);
  await assert.rejects(context.workspaceActions['approve-draft-preview'](), /already has a task/);
  assert.equal(captureAttempts, 1, 'the failed capture is never retried automatically');
  assert.equal(state.details.get('a:first').recipe_approved, true);
  assert.equal(state.details.get('b:other'), kept);
  await context.startWorkspaceAction('capture');
  assert.equal(captureAttempts, 2);
  assert.deepEqual(requests, [['/api/projects/a/recipe', 'PUT'],
    ['/api/projects/a/capture', 'POST'], ['/api/projects/a/capture', 'POST']]);
});
