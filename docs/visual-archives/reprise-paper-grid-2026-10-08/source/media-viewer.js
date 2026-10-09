'use strict';
if(typeof uiEnglish==='object')Object.assign(uiEnglish,{'适应宽度':'Fit width','查看大图 ↗':'Enlarge ↗','原文件 ↗':'Original file ↗','正在加载…':'Loading…','正在缓冲…':'Buffering…','加载失败，请重试或打开原文件。':'Loading failed. Retry or open the original file.','视频格式无法播放，可打开原文件。':'This video format cannot be played. Open the original file.','重试':'Retry','全屏体验':'Fullscreen','独立窗口 ↗':'Open in new tab ↗','此历史存档缺少部分原媒体，空白处保留原版状态。':'Some original media is missing from this archive; empty areas retain the historical state.'});
function mediaMarkup(p,label,expanded=false){
  const video=p.media_type==='video',data={url:p.url,poster:p.poster,media_type:p.media_type,label,viewport:p.viewport,missing_resources:p.missing_resources,pixel_width:p.pixel_width,pixel_height:p.pixel_height};
  return `<div class="media-viewer" data-media-source="${esc(JSON.stringify(data))}"><div class="media-tools">${video?'':`<button data-media-zoom="fit" aria-pressed="true">适应宽度</button><button data-media-zoom="native" aria-pressed="false">100%</button><button data-media-zoom="double" aria-pressed="false">200%</button>`}${expanded?'':`<button data-media-open>查看大图 ↗</button>`}<a href="${esc(p.url)}" target="_blank" rel="noopener">原文件 ↗</a><output data-media-dimensions data-user-content></output></div><div class="media-viewport" data-zoom="fit">${video?`<video controls playsinline preload="metadata" ${p.poster?`poster="${esc(p.poster)}"`:''} src="${esc(p.url)}" aria-label="${esc(label)}"></video>`:`<img src="${esc(p.url)}" alt="${esc(label)}" ${p.pixel_width&&p.pixel_height?`width="${p.pixel_width}" height="${p.pixel_height}"`:''} loading="eager" decoding="async">`}</div><div class="media-status" role="status" data-state="loading"><span>正在加载…</span><button data-media-retry hidden>重试</button></div>${p.missing_resources?.length?'<p class="media-source-note">此历史存档缺少部分原媒体，空白处保留原版状态。</p>':''}</div>`;
}
function mediaState(root,state,text=''){
  const status=root.querySelector('.media-status');if(!status)return;
  status.dataset.state=state;status.querySelector('span').textContent=text;
  status.querySelector('button').hidden=state!=='error';
}
function fitMedia(root){
  const img=root.querySelector('img'),viewport=root.querySelector('.media-viewport'),video=root.querySelector('video');
  const width=img?.naturalWidth||video?.videoWidth,height=img?.naturalHeight||video?.videoHeight;
  if(width&&height){
    const output=root.querySelector('[data-media-dimensions]');output.textContent=`${width} × ${height}`;
    if(img){
      const source=JSON.parse(root.dataset.mediaSource),frame=source.viewport;
      const portraitFrame=frame&&frame.height>frame.width&&Math.abs(width/height-frame.width/frame.height)<.025;
      const fit=Math.min(1,viewport.clientWidth/width,portraitFrame?parseFloat(getComputedStyle(viewport).maxHeight)/height:Infinity);
      const mode=viewport.dataset.zoom,scale=mode==='native'?1:mode==='double'?2:fit;
      img.style.width=Math.round(width*scale)+'px';img.style.height='auto';
      output.textContent+=` · ${Math.round(scale*100)}%`;
    }
  }
}
const observedMedia=new WeakSet();
const mediaResize=new ResizeObserver(entries=>entries.forEach(entry=>fitMedia(entry.target.closest('.media-viewer'))));
function prepareMedia(root){
  if(observedMedia.has(root))return;observedMedia.add(root);
  mediaResize.observe(root.querySelector('.media-viewport'));
  const node=root.querySelector('img,video');
  if(node instanceof HTMLImageElement&&node.complete){mediaState(root,node.naturalWidth?'ready':'error',node.naturalWidth?'':'加载失败，请重试或打开原文件。');fitMedia(root);}
  if(node instanceof HTMLVideoElement&&node.readyState>=1){mediaState(root,'ready');fitMedia(root);}
}
function mediaRoots(node){return node instanceof Element?[...(node.matches('.media-viewer')?[node]:[]),...node.querySelectorAll('.media-viewer')]:[];}
new MutationObserver(records=>{
  for(const record of records){
    for(const node of record.addedNodes)mediaRoots(node).forEach(prepareMedia);
    for(const node of record.removedNodes)for(const root of mediaRoots(node)){mediaResize.unobserve(root.querySelector('.media-viewport'));const v=root.querySelector('video');if(v){v.pause();v.removeAttribute('src');v.load();}}
  }
}).observe(document.body,{childList:true,subtree:true});
for(const name of ['load','loadedmetadata','canplay','playing','seeked','waiting','error'])document.addEventListener(name,event=>{
  const node=event.target,root=node.closest?.('.media-viewer');if(!root||!node.matches('img,video'))return;
  if(name==='error'){mediaState(root,'error',node.error?.code===4?'视频格式无法播放，可打开原文件。':'加载失败，请重试或打开原文件。');return;}
  if(name==='waiting'){mediaState(root,'loading','正在缓冲…');return;}
  mediaState(root,'ready');fitMedia(root);
},true);
function openMedia(data){
  let dialog=document.querySelector('#media-zoom');
  if(!dialog){dialog=document.createElement('dialog');dialog.id='media-zoom';dialog.className='media-zoom-dialog';document.body.append(dialog);dialog.addEventListener('close',()=>{dialog.innerHTML='';});}
  dialog.innerHTML=`<div class="media-zoom-heading"><h2 data-user-content>${esc(data.label)}</h2><button data-media-close aria-label="关闭弹窗">×</button></div>${mediaMarkup(data,data.label,true)}`;
  dialog.showModal();
}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  const root=button.closest('.media-viewer');
  if(button.hasAttribute('data-media-close'))button.closest('dialog').close();
  if(button.hasAttribute('data-media-open')&&root){root.querySelector('video')?.pause();openMedia(JSON.parse(root.dataset.mediaSource));}
  if(button.dataset.mediaZoom&&root){root.querySelector('.media-viewport').dataset.zoom=button.dataset.mediaZoom;root.querySelectorAll('[data-media-zoom]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));fitMedia(root);}
  if(button.hasAttribute('data-media-retry')&&root){const node=root.querySelector('img,video');mediaState(root,'loading','正在加载…');const data=JSON.parse(root.dataset.mediaSource);node.src=data.url+(data.url.includes('?')?'&':'?')+'retry='+Date.now();if(node instanceof HTMLVideoElement)node.load();}
  if(button.hasAttribute('data-runtime-fullscreen')){const frame=button.closest('dialog').querySelector('.runtime-frame');frame.requestFullscreen().catch(()=>toast('请使用独立窗口查看。',true));}
});
document.addEventListener('close',event=>{if(event.target instanceof HTMLDialogElement)event.target.querySelectorAll('video').forEach(video=>video.pause());},true);
