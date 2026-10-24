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
 vm.runInContext(locale.slice(locale.indexOf('function preferredLanguage'),locale.indexOf('Object.assign(uiCopy',locale.indexOf('function preferredLanguage'))),c);
 assert.equal(vm.runInContext('uiLanguage',c),'en');
});
