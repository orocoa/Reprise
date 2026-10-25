const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {test}=require('node:test');
const locale=fs.readFileSync(path.join(__dirname,'../web/locale.js'),'utf8');
const resolver=locale.slice(locale.indexOf('function preferredLanguage'),locale.indexOf('let savedLanguage'));
test('explicit and remembered language override browser preference without using project text',()=>{
 const c=vm.createContext({});vm.runInContext(resolver,c);
 for(const [explicit,saved,languages,expected] of [
  ['en','zh',['zh-CN'],'en'],['zh','en',['en-US'],'zh'],[null,'en',['zh-CN'],'en'],
  [null,null,['zh-TW','en'],'zh'],[null,null,['fr','en-GB'],'en'],
  ['invalid','zh',['en'],'zh'],[null,null,['fr'],'en'],[null,null,[],'en']]){
  assert.equal(c.preferredLanguage(explicit,saved,languages),expected);
 }
});
test('blocked browser storage does not discard an explicit language',()=>{
 const c=vm.createContext({URLSearchParams,location:{search:'?lang=en'},navigator:{languages:['zh-CN']},localStorage:{getItem(){throw Error('blocked');}}});
 vm.runInContext(locale.slice(locale.indexOf('function preferredLanguage'),locale.indexOf('const i18nMissing',locale.indexOf('function preferredLanguage'))),c);
 assert.equal(vm.runInContext('uiLanguage',c),'en');
});
function localeContext(){
 const c=vm.createContext({URLSearchParams,location:{search:'?lang=en'},navigator:{languages:['en']},localStorage:{getItem:()=>null}});
 vm.runInContext(locale.slice(0,locale.indexOf('const originalTexts')),c);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/live-copy.js'),'utf8'),c);
 return c;
}
test('all workbench copy supports both directions regardless of feature initialization order',()=>{
 const c=localeContext();
 for(const [zh,en] of [['部分完成','Partially complete'],['停止 Reprise','Stop Reprise'],['文件已保存到新目录。','Files saved in the new folder.']]){
  vm.runInContext("uiLanguage='en'",c);assert.equal(c.uiText(zh),en);
  vm.runInContext("uiLanguage='zh'",c);assert.equal(c.uiText(en),zh);
 }
});
test('dynamic counts remain translated while user identifiers remain literal',()=>{
 const c=localeContext();
 assert.equal(c.uiText('1301 个提交'),'1301 commits');
 assert.equal(c.uiText('320 个文件'),'320 files');
 const literal='/work/Personal page/abc123.html';assert.equal(c.uiText(literal),literal);
});
