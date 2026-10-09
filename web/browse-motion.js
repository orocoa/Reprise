'use strict';
const gridMotion={duration:620,easing:'cubic-bezier(.22,.68,.18,1)',labels:'.version-card h3,.version-card time,.current-git-choice>span,.current-git-choice>small,.search-box input,.search-icon,.list-heading'};
// Move the directory rules first; reveal labels only in their final positions.
const browseMotion = (() => {
  const {duration,easing}=gridMotion;
  let animations=[],generation=0;
  const rect=element=>element.getBoundingClientRect();
  function cancel() {
    generation++;
    for(const animation of animations)animation.cancel();
    animations=[];
    document.querySelector('#versions-view')?.classList.remove('is-opening');
    document.querySelector('.version-browser')?.removeAttribute('aria-busy');
    const detail=document.querySelector('#version-detail');
    if(detail)detail.inert=false;
  }
  function capture() {
    const view=document.querySelector('#versions-view'),aside=view.querySelector('.version-browser');
    if(!view.classList.contains('is-index')||view.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches||!aside.animate)return null;
    const list=view.querySelector('.version-list'),listBox=rect(list),rows=new Map();
    for(const row of view.querySelectorAll('.current-git-choice,.version-card')) {
      const box=rect(row);
      if(row.classList.contains('version-card')&&(box.bottom<listBox.top||box.top>listBox.bottom))continue;
      rows.set(row.dataset.select||'current',{height:box.height});
    }
    const search=view.querySelector('.search-box'),count=view.querySelector('.list-heading');
    return {aside:rect(aside),asideBorder:parseFloat(getComputedStyle(aside).borderRightWidth),listHeight:listBox.height,rows,searchPadding:getComputedStyle(search).padding,countPadding:getComputedStyle(count).padding};
  }
  function open(before,onDirectoryReady) {
    if(!before){onDirectoryReady?.();return;}
    const view=document.querySelector('#versions-view'),aside=view.querySelector('.version-browser'),detail=view.querySelector('.version-detail');
    const after=rect(aside),list=view.querySelector('.version-list'),listHeight=rect(list).height;
    const rowTargets=[...view.querySelectorAll('.current-git-choice,.version-card')].map(row=>({row,before:before.rows.get(row.dataset.select||'current'),height:rect(row).height}));
    const current=++generation;
    view.classList.add('is-opening');aside.setAttribute('aria-busy','true');detail.inert=true;
    const animate=(element,keyframes,options={})=>{
      const animation=element.animate(keyframes,{duration,easing,fill:'both',...options});
      animations.push(animation);return animation;
    };
    const directory=animate(aside,[{width:(before.aside.width+parseFloat(getComputedStyle(aside).borderRightWidth)-before.asideBorder)+'px',transform:`translate(${before.aside.x-after.x}px,${before.aside.y-after.y}px)`},{width:after.width+'px',transform:'translate(0,0)'}]);
    animate(list,[{height:before.listHeight+'px'},{height:listHeight+'px'}]);
    for(const target of rowTargets) {
      if(!target.before)continue;
      animate(target.row,[{height:target.before.height+'px'},{height:target.height+'px'}]);
    }
    for(const [selector,padding] of [['.search-box',before.searchPadding],['.list-heading',before.countPadding]]) {
      const element=view.querySelector(selector);
      animate(element,[{padding},{padding:getComputedStyle(element).padding}]);
    }
    // Labels return only after the directory rules have reached their final positions.
    for(const label of view.querySelectorAll(gridMotion.labels)) {
      animate(label,[{opacity:0},{opacity:1}],{duration:180,delay:duration,easing:'ease-out'});
    }
    animate(detail,[{opacity:0},{opacity:1}],{duration:200,delay:duration,easing:'ease-out'});
    directory.finished.then(()=>{if(current===generation){detail.inert=false;onDirectoryReady?.();}}).catch(()=>{});
    Promise.all(animations.map(animation=>animation.finished)).then(()=>{if(current===generation)cancel();}).catch(()=>{});
  }
  window.addEventListener('resize',cancel);
  return {capture,open,cancel,get active(){return animations.length>0;}};
})();

// Carry the visible rules to their destination before revealing the new content.
// Read real borders so row counts, languages, scroll positions and viewport sizes
// all use the same motion without copying a directory into the management page.
const viewMotion = (() => {
  const {duration,easing}=gridMotion;
  let animations=[],frame=null,target=null,scrollOrigin=null,generation=0;
  const rect=element=>element.getBoundingClientRect();
  function contentBox(view) {
    const box=rect(view),style=getComputedStyle(view),left=parseFloat(style.borderLeftWidth),right=parseFloat(style.borderRightWidth);
    return {left:box.left+left,top:Math.max(0,box.top),width:box.width-left-right,bottom:Math.min(innerHeight,box.bottom)};
  }
  function cancel() {
    generation++;
    for(const animation of animations)animation.cancel();
    animations=[];frame?.remove();frame=null;scrollOrigin=null;
    if(target){target.inert=false;target.removeAttribute('aria-busy');target=null;}
  }
  function rules(view,detailOnly=false) {
    const box=contentBox(view),items=[];
    const selectors=detailOnly
      ? '.detail-header,.change-content,.preview-menu,.current-summary'
      : view.id==='versions-view'
      ? '.current-git-choice,.search-box,.version-card,.version-list>.empty-list'
      : '.management-heading,.resource-row,#resource-list>.empty-list';
    for(const element of view.querySelectorAll(selectors)) {
      const bounds=rect(element),style=getComputedStyle(element);
      if(!bounds.width||!bounds.height)continue;
      const list=element.closest('.version-list'),clip=list?rect(list):box;
      for(const side of ['Top','Bottom']) {
        const height=parseFloat(style['border'+side+'Width']);
        const y=side==='Top'?bounds.top:bounds.bottom-height;
        if(!height||y<Math.max(box.top,clip.top)||y+height>Math.min(box.bottom,clip.bottom)+.5)continue;
        const item={x:bounds.left,y,width:bounds.width,height,color:style['border'+side+'Color'],opacity:1};
        if(!items.some(old=>Math.abs(old.y-y)<.5&&Math.abs(old.x-item.x)<.5))items.push(item);
      }
    }
    return items.sort((a,b)=>a.y-b.y);
  }
  function divider(view) {
    const box=contentBox(view),aside=view.querySelector('.version-browser');
    const border=aside?parseFloat(getComputedStyle(aside).borderRightWidth):0;
    return {x:aside?rect(aside).right-border:box.left,y:box.top,height:box.bottom-box.top,opacity:border?1:0};
  }
  function capture(nextView,force=false) {
    const view=document.querySelector('.view:not([hidden])');
    if(!window.demoReady||!view||(!force&&view.id===nextView+'-view')||matchMedia('(prefers-reduced-motion: reduce)').matches||!view.animate)return null;
    // A second click continues from the currently painted rules, not an endpoint.
    const moving=frame?[...frame.querySelectorAll('.view-motion-rule')].map(element=>{
      const box=rect(element),style=getComputedStyle(element);
      return {x:box.x,y:box.y,width:box.width,height:box.height,color:style.backgroundColor,opacity:Number(style.opacity)};
    }).filter(item=>item.opacity>.001).sort((a,b)=>a.y-b.y):null;
    const line=frame?.querySelector('.view-motion-divider');
    const edge=line?{x:rect(line).x,y:rect(line).y,height:rect(line).height,opacity:Number(getComputedStyle(line).opacity)}:divider(view);
    const detail=view.querySelector('.version-detail'),detailMoving=frame?.dataset.scope==='detail';
    return {view:view.id,box:contentBox(view),rules:!detailMoving&&moving||rules(view),detailRules:detailMoving&&moving||rules(view,true),detailBox:detail?contentBox(detail):null,divider:edge,index:view.classList.contains('is-index'),directory:Boolean(view.querySelector('.version-browser'))};
  }
  function open(before,onReady) {
    if(!before){onReady?.();return;}
    target=document.querySelector('.view:not([hidden])');
    const actual=target.querySelector('.version-browser');
    const detailOnly=before.view===target.id&&!before.index&&actual&&!target.classList.contains('is-index');
    const after=rules(target,detailOnly),source=detailOnly?before.detailRules:before.rules;
    const sourceBox=detailOnly?before.detailBox:before.box;
    if(detailOnly)target=target.querySelector('.version-detail');
    const box=contentBox(target),current=++generation;
    const origin={x:box.left,y:Math.min(box.top,sourceBox.top)};
    frame=document.createElement('div');frame.className='view-motion-frame';
    frame.dataset.scope=detailOnly?'detail':'view';
    frame.setAttribute('aria-hidden','true');frame.inert=true;
    Object.assign(frame.style,{left:origin.x+'px',top:origin.y+'px',width:box.width+'px',height:Math.max(0,Math.max(box.bottom,sourceBox.bottom)-origin.y)+'px'});
    document.body.append(frame);scrollOrigin={x:scrollX,y:scrollY};
    target.inert=true;target.setAttribute('aria-busy','true');
    function animate(element,keyframes,options={}) {
      const animation=element.animate(keyframes,{duration,easing,fill:'both',...options});animations.push(animation);return animation;
    }
    const paint=item=>({transform:`translate(${item.x-origin.x}px,${item.y-origin.y}px) scaleX(${item.width})`,height:item.height+'px',backgroundColor:item.color,opacity:item.opacity});
    // Every rule has at most one source and one destination. Extra source
    // rules retire in the gaps; new destination rules appear after arrival.
    const count=Math.min(source.length,after.length);
    const matches=Array.from({length:count},(_,i)=>({
      index:Math.round(i*(source.length-1)/Math.max(1,count-1)),
      destination:Math.round(i*(after.length-1)/Math.max(1,count-1)),
    }));
    for(const [index,from] of source.entries()) {
      const match=matches.find(item=>item.index===index);
      const line=document.createElement('div');line.className='view-motion-rule';frame.append(line);
      if(match) {
        const to=after[match.destination];
        // Position and length settle first. Weight/color change with the reveal.
        animate(line,[paint(from),paint({...to,height:from.height,color:from.color})]);
        animate(line,[{height:from.height+'px',backgroundColor:from.color},{height:to.height+'px',backgroundColor:to.color}],{duration:200,delay:duration,easing:'ease-out'});
      } else {
        // Retire a surplus line between its neighbors, never onto either one.
        const lower=[...matches].reverse().find(item=>item.index<index)||matches[0];
        const upper=matches.find(item=>item.index>index)||lower;
        let to=from;
        if(lower) {
          const low=after[lower.destination],high=after[upper.destination];
          const span=source[upper.index].y-source[lower.index].y;
          const y=span?low.y+(high.y-low.y)*(from.y-source[lower.index].y)/span:low.y+from.y-source[lower.index].y;
          to={...from,x:low.x,y,width:low.width};
        }
        animate(line,[paint(from),paint(to)]);
        animate(line,[{opacity:from.opacity},{opacity:0}],{duration:160,easing:'ease-out'});
      }
    }
    for(const [destination,to] of after.entries()) {
      if(matches.some(item=>item.destination===destination))continue;
      const line=document.createElement('div');line.className='view-motion-rule';frame.append(line);
      Object.assign(line.style,paint(to));
      animate(line,[{opacity:0},{opacity:1}],{duration:200,delay:duration,easing:'ease-out'});
    }
    if(!detailOnly) {
      const from=before.divider,to=divider(target);
      // A departing internal divider can join a real right-hand frame border.
      // Never invent a divider when neither layout has one.
      if(from.opacity>.001&&!actual&&parseFloat(getComputedStyle(target).borderRightWidth)>0) {
        to.x=box.left+box.width;to.opacity=1;
      }
      if(from.opacity>.001||to.opacity>.001) {
        const line=document.createElement('div');line.className='view-motion-divider';frame.append(line);
        const edgePaint=item=>({transform:`translate(${item.x-origin.x}px,${item.y-origin.y}px)`,height:item.height+'px'});
        if(from.opacity>.001&&to.opacity>.001) {
          animate(line,[edgePaint(from),edgePaint(to)]);
          animate(line,[{opacity:from.opacity},{opacity:to.opacity}]);
        } else if(from.opacity>.001) {
          Object.assign(line.style,edgePaint(from));
          animate(line,[{opacity:from.opacity},{opacity:0}],{duration:160,easing:'ease-out'});
        } else {
          Object.assign(line.style,edgePaint(to));
          animate(line,[{opacity:0},{opacity:to.opacity}],{duration:200,delay:duration,easing:'ease-out'});
        }
      }
    }
    const reveal=element=>animate(element,[{opacity:0},{opacity:1}],{duration:200,delay:duration,easing:'ease-out'});
    for(const section of target.children)reveal(section);
    const caption=document.querySelector('#versions-caption');
    if(caption&&!caption.hidden)reveal(caption);
    // Keep the final rules painted over the content fade. Removing the overlay
    // earlier would make the horizontal borders vanish and fade back in.
    Promise.all(animations.map(animation=>animation.finished)).then(()=>{if(current===generation){cancel();onReady?.();}}).catch(()=>{});
  }
  window.addEventListener('resize',cancel);
  // A viewport scroll changes the coordinate space; settle before handing over.
  window.addEventListener('scroll',()=>{if(frame&&(scrollX!==scrollOrigin.x||scrollY!==scrollOrigin.y))cancel();},{passive:true});
  return {capture,open,cancel,get active(){return animations.length>0;}};
})();
