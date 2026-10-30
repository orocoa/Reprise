'use strict';

// One lifecycle for every dialog view. No closed view keeps layout classes,
// ownership metadata or live media; restoring a parent restores its whole view.
var RepriseDialogs=(()=>{
 function create({element,beforeChange,onTransition,onRestore,origin}){
  let generation=0;
  function transition(){generation++;onTransition?.();beforeChange?.();}
  function reset(dialog,className='',dataset={}){
   dialog.className=className;
   for(const key of Object.keys(dialog.dataset))delete dialog.dataset[key];
   Object.assign(dialog.dataset,dataset);
  }
  return {
   get generation(){return generation;},
   owns(token){return element().open&&token===generation;},
   open(markup,{className='',dataset={}}={}){
    const dialog=element();transition();reset(dialog,className,dataset);
    dialog.innerHTML=markup;
    if(!dialog.open)dialog.showModal();
    dialog.querySelector('#dialog-title')?.focus?.({preventScroll:true});
    return generation;
   },
   close(parent=null){
    const dialog=element();transition();
    if(parent){
     reset(dialog,parent.className,parent.dataset);
     dialog.replaceChildren(...parent.nodes);onRestore?.(parent);
     dialog.scrollTop=parent.scrollTop;
     return true;
    }
    dialog.close();dialog.replaceChildren();reset(dialog);
    origin()?.focus?.({preventScroll:true});
    return false;
   }
  };
 }
 return {create};
})();
if(typeof module==='object')module.exports=RepriseDialogs;
