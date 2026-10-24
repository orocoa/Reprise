const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/text-diff.js'), 'utf8'), context);
const diff = context.RepriseTextDiff;
const model = () => ({schema:1,status:'ok',summary:{changes:2,inserted:2,deleted:1},
  hunks:[{rows:[{kind:'delete',before_line:2,after_line:null,text:'old',eol:'crlf',change:0},
    {kind:'insert',before_line:null,after_line:2,text:'new',eol:'lf',change:0}]},
    {rows:[{kind:'insert',before_line:null,after_line:10,text:'last',eol:'none',change:1}]}],
  gaps:[{before_hunk:1,count:7,rows:[{kind:'equal',before_line:3,after_line:3,text:'same',eol:'lf'}]}]});

test('file text is inert and change navigation targets one row per edit block', () => {
  const data = model();
  data.hunks[0].rows[0].text = '</code><img src=x onerror="evil()">&\'"';
  const html = diff.render(data, {language:'en'});
  assert.doesNotMatch(html, /<img|<script|onerror="evil/);
  assert.match(html, /&lt;img src=x onerror=&quot;evil\(\)&quot;&gt;&amp;&#39;&quot;/);
  assert.equal((html.match(/data-text-diff-change /g) || []).length, 2);
  assert.match(html, /↵ CRLF/);
  assert.match(html, /↵ LF/);
  assert.match(html, /No newline at end of line/);
});

test('unchanged regions are collapsed by default and controls do not claim restore actions', () => {
  const html = diff.render(model());
  assert.match(html, /<details class="text-diff-gap"><summary>展开 7 行未变内容/);
  assert.doesNotMatch(html, /<details[^>]+ open|data-action=|recover-file-side/);
  assert.match(html, /data-text-diff-action="next"/);
});

test('binary, read failure, and limited inputs are not reported as no changes', () => {
  for (const data of [{status:'unavailable',reason:'binary'},{status:'unavailable',reason:'read_error'},
    {status:'too_large',reason:'repeated_lines'},{status:'truncated',reason:'input_truncated'}]) {
    const html = diff.render(data, {language:'en'});
    assert.doesNotMatch(html, /text is identical|0 changes|text-diff-toolbar/);
    assert.match(html, /complete file/);
  }
  assert.match(diff.render({status:'truncated',reason:'output_budget',hunks:[],summary:{}}), /不是完整比较/);
});

test('available change targets and rendered rows are bounded even for oversized responses', () => {
  const data = model();
  data.hunks = [{rows:Array.from({length:5000}, (_,i) => ({kind:'insert',text:'x',after_line:i+1,eol:'lf',change:i}))}];
  data.gaps = [];
  const html = diff.render(data);
  assert.equal((html.match(/class="text-diff-row /g) || []).length, 2000);
});

test('next/previous change moves focus, announces position, wraps, and stays inside host', () => {
  const targets = [0,1].map(index => ({attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
    focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;}}));
  const position = {textContent:''};
  const root = {dataset:{textDiffIndex:'-1'},querySelectorAll:()=>targets,querySelector:()=>position};
  const button = action => ({dataset:{textDiffAction:action},closest:()=>root});
  assert.equal(diff.handleAction(button('next'), {contains:()=>false}), false);
  assert.equal(diff.handleAction(button('next'), root), true);
  assert.equal(position.textContent, '1 / 2');
  assert.equal(targets[0].attrs['aria-current'], 'true');
  assert.ok(targets[0].focused && targets[0].scrolled);
  diff.handleAction(button('previous'), root);
  assert.equal(position.textContent, '2 / 2');
  assert.equal(targets[0].attrs['aria-current'], undefined);
  assert.equal(targets[1].attrs['aria-current'], 'true');
  assert.equal(diff.handleAction({dataset:{action:'close'}}, root), false);
});

test('empty added files differ from unchanged empty text', () => {
  assert.match(diff.render({status:'ok',reason:'empty_added',summary:{}}), /新增了一个空文件/);
  assert.match(diff.render({status:'unchanged',summary:{}}), /两版文本相同/);
});
