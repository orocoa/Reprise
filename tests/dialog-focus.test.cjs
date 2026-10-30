/* Mouse-opened modals must be quiet without losing keyboard navigation. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../web/live.js'),'utf8').split("document.addEventListener('click'")[0];

test('pointer and keyboard focus remain distinct across modal transitions',()=>{
 const listeners={},doc={documentElement:{dataset:{}},addEventListener:(name,fn,capture)=>{assert.equal(capture,true);listeners[name]=fn;}};
 const context=vm.createContext({document:doc,location:{hash:''},URLSearchParams});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/dialog-controller.js'),'utf8'),context);
 vm.runInContext(source,context);
 vm.runInContext('installFocusBehavior()',context);
 assert.equal(doc.documentElement.dataset.inputModality,'pointer');
 listeners.keydown({key:'Tab'});
 assert.equal(doc.documentElement.dataset.inputModality,'keyboard');
 listeners.pointerdown({pointerType:'mouse'});
 assert.equal(doc.documentElement.dataset.inputModality,'pointer');
 listeners.keydown({key:'s',metaKey:true});
 assert.equal(doc.documentElement.dataset.inputModality,'pointer');
 listeners.keydown({key:'Enter'});
 assert.equal(doc.documentElement.dataset.inputModality,'keyboard');
 listeners.pointerdown({pointerType:'touch'});
 assert.equal(doc.documentElement.dataset.inputModality,'pointer');
});

test('modal starts on its heading and returns to the invoking button even when macOS did not focus it',async()=>{
 const doc={querySelectorAll:()=>[]};
 const opener={isConnected:true,dataset:{action:'test-dialog'},focus(){doc.activeElement=this;}};
 const heading={focus(){doc.activeElement=this;}};
 const close={};
 const dialog={open:false,dataset:{},classList:{remove(){},toggle(){}},
  showModal(){this.open=true;doc.activeElement=close;},
  querySelector(selector){return selector==='#dialog-title'?heading:null;},close(){this.open=false;},replaceChildren(){}};
 doc.activeElement={tagName:'MAIN'};
 doc.querySelector=selector=>selector==='#dialog'?dialog:selector==='#dialog-title'?heading:null;
 const context=vm.createContext({document:doc,location:{hash:''},URLSearchParams,uiText:v=>v,trigger:opener,workspaceActions:{},featureActions:{},parityActions:{}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/dialog-controller.js'),'utf8'),context);
 vm.runInContext(source,context);
 vm.runInContext("workspaceActions['test-dialog']=async()=>{await Promise.resolve();dialogShell('Settings','Settings content');}",context);
 await vm.runInContext('action(trigger)',context);
 assert.equal(doc.activeElement,heading);
 assert.match(dialog.innerHTML,/id="dialog-title" tabindex="-1"/);
 vm.runInContext('closeDialog()',context);
 assert.equal(doc.activeElement,opener);
});
