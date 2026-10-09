'use strict';
// Actual version media lead update explanations. Git files remain the fallback.
const updateFocusCache=new Map();
function updateVisualItem(item){return !item.missing&&!item.error&&item.url&&['image','video'].includes(item.kind);}
function updateScenario(item){
 const meta=item.legacy||item.capture||item,viewport=meta.viewport||item.viewport;
 const full=Boolean(meta.full_page||item.full_page||/full_url/.test(item.capture_id||''));
 if(item.capture?.route&&viewport)return JSON.stringify([meta.id,meta.route,viewport.width,viewport.height,viewport.scale||1,meta.steps||[],meta.wait_for||'',meta.network||'',meta.runner||'',item.kind,full]);
 if(meta.comparison_key)return JSON.stringify([meta.comparison_key,meta.route||'',viewport?.width||item.width,viewport?.height||item.height,meta.language||'',meta.operation||'',item.kind,full]);
 if(meta.route&&viewport)return JSON.stringify([meta.route,viewport.width,viewport.height,meta.language||'',meta.operation||'',item.kind,full]);
 return null;
}
function updateScene(item){const key=updateScenario(item);return key?JSON.stringify(JSON.parse(key).slice(0,-1)):item.content_sha256||item.url;}
function updateWords(text){const result=new Set(),normalized=String(text).toLowerCase().replace(/英文|中文|全图|版本|本次|更新|保存|资料|预览|截图|完整页面/g,'');for(const word of normalized.match(/[a-z][a-z0-9_-]{2,}|[\u3400-\u9fff]+/g)||[]){if(/^[a-z]/.test(word))result.add(word);else for(let i=0;i<word.length-1;i++)result.add(word.slice(i,i+2));}return result;}
function updateAffinity(item,text){const words=updateWords(item.title||item.name||item.scenario||''),context=updateWords(text);return [...words].filter(w=>context.has(w)).length;}
function updateCards(d){
 const current=mediaItems(d).filter(updateVisualItem),before=[...mediaItems(detail(d.diff.base)),...(d.evidence||[]).filter(e=>e.base===d.diff.base).flatMap(e=>(e.items||[]).map((i,index)=>({...i,index,record:e.id,kind:i.kind||(i.media_type?.startsWith('image/')?'image':i.media_type?.startsWith('video/')?'video':'file'),capture:e.source==='automatic'?{...(e.recipe?.captures||[]).find(c=>c.id===i.capture_id),network:e.recipe?.network,runner:e.runner_version}:i.capture})).filter(i=>i.sha===d.diff.base))].filter(updateVisualItem);
 if(!current.length)return [];
 if(d.diff.available!==false&&d.diff.files.length&&!d.diff.files.some(f=>/\.(html?|css|scss|sass|less|jsx?|tsx?|vue|svelte|mdx|png|jpe?g|webp|avif|bmp|gif|svg|woff2?|ttf|otf|mp4|webm|mov)$/i.test(f.path)))return [];
 const notes=versionNotes(d.commit),localized=Object.values(d.notes?.localizations||d.commit.notes?.localizations||{}),context=[versionTitle(d.commit),notes?.summary,...(notes?.changes||[]),...localized.flatMap(n=>[n.title,n.summary,...(n.changes||[])])].join(' '),scenes=new Map();
 for(const item of current){
  const scenario=updateScenario(item),previous=scenario?before.find(i=>updateScenario(i)===scenario):null;
  if(previous?.content_sha256&&previous.content_sha256===item.content_sha256)continue;
  const score=updateAffinity(item,context),key=updateScene(item),candidate={item,previous,score};
  const existing=scenes.get(key),full=/full_url/.test(item.capture_id||'');
  if(!existing||Boolean(previous)>Boolean(existing.previous)||(Boolean(previous)===Boolean(existing.previous)&&!full&&/full_url/.test(existing.item.capture_id||'')))scenes.set(key,candidate);
 }
 const cards=[...scenes.values()].sort((a,b)=>b.score-a.score),relevant=cards.some(c=>c.score>0)?cards.filter(c=>c.score>0):cards;
 return relevant.slice(0,6);
}
async function ensureUpdateBaseline(d,signal){if(d?.diff.base&&mediaItems(d).some(updateVisualItem)&&!detail(d.diff.base)){try{await loadDetail(d.diff.base,signal);}catch(error){if(error.name==='AbortError')throw error;}}}
function updateVisualMarkup(item,label=''){
 const caption=item.title||item.name||uiText('版本预览');
 return `<figure class="update-image-side">${label?`<figcaption>${label}</figcaption>`:''}${item.kind==='video'?`<video class="update-video" src="${esc(item.url)}" controls preload="metadata"></video>`:`<button class="update-image-open" data-action="media" data-record="${esc(item.record)}" data-index="${item.index}" data-user-label aria-label="${uiText('放大')} ${esc(caption)}"><span class="update-image-viewport"><img src="${esc(item.url)}" alt="${esc(caption)}" ${item.width&&item.height?`width="${item.width}" height="${item.height}"`:''} loading="lazy" data-update-image="${label===uiText('更新前')?'before':'after'}"></span><span class="update-expand" aria-hidden="true"><svg class="icon" viewBox="0 0 18 18"><path d="M6 2H2v4M12 2h4v4M16 12v4h-4M6 16H2v-4"/></svg></span></button>`}</figure>`;
}
function renderVisualUpdates(d){
 const cards=updateCards(d);if(!cards.length)return '';
 const changes=versionNotes(d.commit)?.changes||[];
 return cards.map(({item,previous},index)=>{const associated=changes.filter(text=>updateAffinity(item,text)>0),description=associated.length?associated.slice(0,2):index===0?changes.slice(0,2):[];const title=cards.length===1?versionTitle(d.commit):item.title||item.name||versionTitle(d.commit);return `<section class="feature update-feature"><div class="feature-copy"><span class="feature-kind"><span class="feature-number">${String(index+1).padStart(2,'0')}</span></span><h3 data-user-content>${esc(title)}</h3>${description.map(text=>`<p data-user-content>${esc(text)}</p>`).join('')}</div><div class="update-visual ${previous?'is-paired':''}" data-update-visual><div class="update-visual-grid">${previous?updateVisualMarkup(previous,uiText('更新前')):''}${updateVisualMarkup(item,previous?uiText('更新后'):'')}</div></div></section>`;}).join('');
}
function updatePixelFocus(before,after){
 if(before.naturalWidth!==after.naturalWidth||before.naturalHeight!==after.naturalHeight)return null;
 const width=after.naturalWidth,height=after.naturalHeight,scale=Math.min(1,640/Math.max(width,height)),w=Math.max(1,Math.round(width*scale)),h=Math.max(1,Math.round(height*scale));
 const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;const ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx)return null;
 ctx.drawImage(before,0,0,w,h);const a=ctx.getImageData(0,0,w,h).data;ctx.clearRect(0,0,w,h);ctx.drawImage(after,0,0,w,h);const b=ctx.getImageData(0,0,w,h).data;
 let left=w,top=h,right=0,bottom=0,count=0;
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4,delta=Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2])+Math.abs(a[i+3]-b[i+3]);if(delta>90){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);count++;}}
 if(count<Math.max(12,w*h*.0002))return null;
 const padding=Math.max(12,Math.round(Math.min(w,h)*.035));left=Math.max(0,left-padding);top=Math.max(0,top-padding);right=Math.min(w,right+padding+1);bottom=Math.min(h,bottom+padding+1);
 if((right-left)*(bottom-top)>w*h*.8)return null;
 return {x:left/w,y:top/h,width:(right-left)/w,height:(bottom-top)/h,naturalWidth:width,naturalHeight:height};
}
function enhanceUpdateVisuals(){
 for(const visual of document.querySelectorAll('[data-update-visual].is-paired')){
  if(visual.dataset.enhancing)continue;visual.dataset.enhancing='true';
  const before=visual.querySelector('[data-update-image=before]'),after=visual.querySelector('[data-update-image=after]');if(!before||!after)continue;
  const enhance=()=>{if(!visual.isConnected||!before.complete||!after.complete||!before.naturalWidth||!after.naturalWidth)return;const key=before.src+'|'+after.src;let focus=updateFocusCache.get(key);try{if(focus===undefined){focus=updatePixelFocus(before,after);updateFocusCache.set(key,focus);}}catch{focus=null;}if(!focus)return;for(const img of [before,after]){const frame=img.closest('.update-image-viewport');frame.style.aspectRatio=`${focus.width*focus.naturalWidth} / ${focus.height*focus.naturalHeight}`;frame.classList.add('is-focused');img.style.width=(100/focus.width)+'%';img.style.left=(-focus.x/focus.width*100)+'%';img.style.top=(-focus.y/focus.height*100)+'%';}visual.dataset.focused='true';};
  before.addEventListener('load',enhance,{once:true});after.addEventListener('load',enhance,{once:true});enhance();
 }
}
