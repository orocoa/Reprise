/* Parent return and async ownership are one dialog lifecycle. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const {create}=require('../web/dialog-controller.js');
function fixture(){
 const focused=[],dialog={open:false,className:'',dataset:{},scrollTop:0,
  showModal(){this.open=true},close(){this.open=false},replaceChildren(...nodes){this.nodes=nodes},
  querySelector(){return {focus(){focused.push('heading')}}}};
 const controller=create({element:()=>dialog,origin:()=>({focus(){focused.push('origin')}}),
  onRestore:parent=>parent.focused.focus()});
 return {dialog,controller,focused};
}
test('closed dialogs drop all view metadata and styles and invalidate late work',()=>{
 const {dialog,controller,focused}=fixture();
 const token=controller.open('runtime',{className:'runtime-preview-dialog',dataset:{dialogView:'runtime',futureField:'owned'}});
 assert.equal(controller.owns(token),true);controller.close();
 assert.equal(dialog.open,false);assert.equal(dialog.className,'');assert.deepEqual(dialog.dataset,{});
 assert.equal(controller.owns(token),false);assert.deepEqual(focused,['heading','origin']);
});
test('an unrelated replacement cannot be overwritten by a former async owner',()=>{
 const {dialog,controller}=fixture();const old=controller.open('starting');
 const current=controller.open('settings',{className:'settings-dialog'});
 assert.equal(controller.owns(old),false);assert.equal(controller.owns(current),true);
 assert.equal(dialog.innerHTML,'settings');
});
test('nested return restores the full parent view without closing it',()=>{
 const {dialog,controller}=fixture();controller.open('child',{dataset:{quickPreview:'true'}});
 let restored=false;
 controller.close({nodes:['saved form'],className:'content-dialog',dataset:{recoveryForm:'true'},
  scrollTop:120,focused:{focus(){restored=true}}});
 assert.equal(dialog.open,true);assert.equal(dialog.className,'content-dialog');
 assert.deepEqual(dialog.dataset,{recoveryForm:'true'});assert.deepEqual(dialog.nodes,['saved form']);
 assert.equal(dialog.scrollTop,120);assert.equal(restored,true);
});
