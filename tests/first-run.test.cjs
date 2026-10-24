const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/live-first-run.js'), 'utf8');
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function harness({bridge, api} = {}) {
  const calls = [], state = {dialogRequest: 1, commits: [], project: null};
  const dialog = {open: true}, fallback = {open: false}, status = {textContent: ''};
  const button = {disabled: false, isConnected: true};
  const context = vm.createContext({
    state, window: bridge ? {RepriseDesktop: bridge} : {}, workspaceActions: {}, uiCopy: {},
    contentText: zh => zh,
    $: selector => ({'#dialog': dialog, '#dialog [data-project-picker]': dialog.open ? {} : null,
      '#manual-folder-path': fallback, '#dialog-status': status,
      '#dialog [data-action="choose-website-folder"]': button}[selector]),
    api: async (url, options) => {
      calls.push([url, options]);
      if (api) return api(url, options);
      assert.equal(url, '/api/projects');
      return {id: 'new-project', kind: 'folder'};
    },
    closeDialog() { dialog.open = false; state.dialogRequest++; calls.push(['close']); },
    loadProject: async id => { state.project = {id}; calls.push(['load', id]); },
    snapshotDialog() { state.dialogRequest++; calls.push(['name-draft']); },
    projectPicker: async () => {},
    dialogShell: (...args) => calls.push(['dialog', ...args]),
  });
  vm.runInContext(source, context, {filename: 'live-first-run.js'});
  return {context, state, dialog, fallback, status, button, calls};
}

test('first-run explains saving before the next edit and finding only saved drafts', () => {
  for (const language of ['zh', 'en']) {
    const elements = new Map();
    const context = vm.createContext({
      workspaceActions: {}, uiCopy: {}, document: {},
      contentText: (zh, en) => language === 'en' ? en : zh,
      $: selector => {
        if (!elements.has(selector)) elements.set(selector, {});
        return elements.get(selector);
      },
    });
    vm.runInContext(source, context);
    context.renderFirstRun();
    const html = elements.get('#detail').innerHTML;
    assert.match(html, language === 'en' ? /Save a draft before the next edit/ : /改下一轮之前，留一稿/);
    assert.match(html, language === 'en' ? /from this draft onward.*find a saved draft/ : /从当前这一稿开始.*找回已保存的稿件/);
    assert.match(html, /data-action="start-website-folder"/);
    assert.doesNotMatch(html, /想找回之前的样子|want an earlier look back/);
  }
});

test('desktop choice joins only that folder and asks for a draft name without saving yet', async () => {
  const selected = '/Users/example/Web project with spaces ';
  const h = harness({bridge: {chooseFolder: async () => ({status: 'selected', path: selected})}});
  await h.context.chooseWebsiteFolder(h.button);
  assert.equal(h.calls[0][0], '/api/projects');
  assert.deepEqual(JSON.parse(h.calls[0][1].body), {path: selected, kind: 'folder'});
  assert.deepEqual(h.calls.slice(1), [['close'], ['load', 'new-project'], ['name-draft']]);
  assert.ok(h.calls.every(([url]) => !String(url).includes('/snapshot')));
});

test('native cancel makes no registration, navigation, or fallback error', async () => {
  const h = harness({bridge: {chooseFolder: async () => ({status: 'cancelled'})}});
  await h.context.chooseWebsiteFolder(h.button);
  assert.deepEqual(h.calls, []);
  assert.equal(h.dialog.open, true);
  assert.equal(h.fallback.open, false);
  assert.equal(h.status.textContent, '');
  assert.equal(h.button.disabled, false);
});

test('browser uses the token-protected API and unavailable chooser reveals manual path', async () => {
  const h = harness({api: async url => {
    assert.equal(url, '/api/desktop/choose-folder');
    return {status: 'unavailable', reason: 'No native picker'};
  }});
  await h.context.chooseWebsiteFolder(h.button);
  assert.equal(h.calls[0][1].method, 'POST');
  assert.equal(h.fallback.open, true);
  assert.equal(h.status.textContent, 'No native picker');
  assert.equal(h.calls.length, 1);
});

test('a late selection never joins a folder after the original dialog was left', async () => {
  const pending = deferred();
  const h = harness({bridge: {chooseFolder: () => pending.promise}});
  const action = h.context.chooseWebsiteFolder(h.button);
  h.state.dialogRequest++;
  pending.resolve({status: 'selected', path: '/old-choice'});
  await action;
  assert.deepEqual(h.calls, []);
});

test('late registration response cannot replace a newer dialog or project', async () => {
  const pending = deferred();
  const h = harness({bridge: {chooseFolder: async () => ({status: 'selected', path: '/site'})},
    api: () => pending.promise});
  const action = h.context.chooseWebsiteFolder(h.button);
  await new Promise(resolve => setImmediate(resolve));
  h.state.dialogRequest++;
  h.state.project = {id: 'other-project'};
  pending.resolve({id: 'new-project', kind: 'folder'});
  await action;
  assert.equal(h.state.project.id, 'other-project');
  assert.equal(h.calls.length, 1);
});

test('a delayed first-run project list cannot open a newer dialog’s chooser', async () => {
  const pending = deferred(); let chosen = 0;
  const h = harness({bridge: {chooseFolder: async () => { chosen++; return {status: 'cancelled'}; }}});
  h.context.projectPicker = () => { h.state.dialogRequest++; return pending.promise; };
  const action = h.context.workspaceActions['start-website-folder']();
  h.state.dialogRequest++;
  pending.resolve();
  await action;
  assert.equal(chosen, 0);
});

test('shutdown shows completion only after the API confirms it', async () => {
  const pending = deferred();
  const h = harness({api: () => pending.promise});
  const action = h.context.workspaceActions['stop-workbench'](h.button);
  assert.equal(h.calls[0][0], '/api/shutdown');
  assert.equal(h.calls.filter(([kind]) => kind === 'dialog').length, 0);
  pending.resolve({stopped: true});
  await action;
  assert.equal(h.calls.find(([kind]) => kind === 'dialog')[1], 'Reprise 已停止');
});
