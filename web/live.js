'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=s=>s?.slice(0,8)||'—';
const icons={search:'<circle cx="8" cy="8" r="5"/><path d="m12 12 4 4"/>',star:'<path d="m9 1.5 2.2 4.5 5 .7-3.6 3.5.8 5-4.4-2.4-4.4 2.4.8-5L1.8 6.7l5-.7z"/>',more:'<circle cx="3" cy="9" r=".6"/><circle cx="9" cy="9" r=".6"/><circle cx="15" cy="9" r=".6"/>',close:'<path d="m4 4 10 10M14 4 4 14"/>',branch:'<circle cx="5" cy="3" r="2"/><circle cx="5" cy="15" r="2"/><circle cx="14" cy="4" r="2"/><path d="M5 5v8M14 6c0 4-9 2-9 7"/>',settings:'<path d="m7.3 1.3-.5 2a6 6 0 0 0-1.4.8l-2-.6-1.7 3 1.5 1.4a6 6 0 0 0 0 1.6l-1.5 1.4 1.7 3 2-.6a6 6 0 0 0 1.4.8l.5 2h3.4l.5-2a6 6 0 0 0 1.4-.8l2 .6 1.7-3-1.5-1.4a6 6 0 0 0 0-1.6l1.5-1.4-1.7-3-2 .6a6 6 0 0 0-1.4-.8l-.5-2z"/><circle cx="9" cy="8.7" r="2.5"/>',refresh:'<path d="M15 7a6 6 0 1 0 .2 4M15 2v5h-5"/>',file:'<path d="M4 1h6l4 4v12H4zM10 1v5h4M7 10h4M7 13h4"/>'};
// Feather edit-2 (MIT): a single outline on the existing 18px icon grid.
icons.pencil='<g transform="scale(.75)" stroke-width="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></g>';
const icon=n=>`<svg class="icon" viewBox="0 0 18 18" aria-hidden="true">${icons[n]||icons.file}</svg>`;
const state={project:null,commits:[],refs:[],graph:null,selected:null,anchorSelection:null,tab:'updates',query:'',filter:'all',details:new Map(),prefs:{stars:[],main:null,density:'compact'},historySources:[],loading:false,searching:false,error:null,snapshot:null,dialogRequest:0,comparison:null,comparisonDraft:null,comparisonLoading:false,comparisonError:null,comparisonRequest:0,view:location.hash==='#resources'?'resources':'versions',ref:'--all',refMembers:null,jobs:[],runtimes:[],jobWarnings:[],commitIndex:new Map(),searchIndex:new Map()};
let token='',selectRequest=0,projectRequest=0,searchRequest=0,toastTimer,searchTimer,returnFocus,detailAbort;
const colors=['#3978bf','#bf5751','#43856b','#8167ae','#a77736'];
let routeColors=new Map();
async function api(path,options={}){const r=await fetch(path,{cache:'no-store',...options,headers:{'Content-Type':'application/json','X-Reprise-Token':token,...options.headers}});const d=await r.json();if(!r.ok)throw Error(d.error||'读取失败');return d;}
const query=(path,values)=>path+'?'+new URLSearchParams(values);
const key=()=>`reprise-live-prefs:${state.project?.id}`;
function readPrefs(){try{const p=JSON.parse(localStorage.getItem(key())||'{}');state.prefs={stars:Array.isArray(p.stars)?p.stars.filter(x=>typeof x==='string'):[],main:typeof p.main==='string'?p.main:null,density:'compact',historyView:['pictures','graph'].includes(p.historyView)?p.historyView:null,presentation:['files','visual'].includes(p.presentation)?p.presentation:'auto'};}catch{state.prefs={stars:[],main:null,density:'compact'};}}
function savePrefs(){try{localStorage.setItem(key(),JSON.stringify(state.prefs));return true;}catch{notify('浏览器无法保存偏好；本次会话仍然有效。');return false;}}
function notify(s){clearTimeout(toastTimer);$('#toast').textContent=s;$('#toast').classList.add('visible');toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
const commit=id=>state.commitIndex.get(id);
function addCommit(c){state.commits.push(c);state.commitIndex.set(c.sha,c);}
const cacheKey=id=>`${revisionProject(id)}:${id}`;
const detail=id=>state.details.get(cacheKey(id));
const dateFormats=new Map();
function formatDate(s,full=false){
 const d=new Date(s);if(!Number.isFinite(+d))return s||'—';
 const key=uiLanguage+'|'+full;
 if(!dateFormats.has(key))dateFormats.set(key,new Intl.DateTimeFormat(uiLanguage==='en'?'en-US':'zh-CN',{...(full?{year:'numeric'}:{}),month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}));
 return dateFormats.get(key).format(d);
}
function refLabel(s){return s.replace(/^refs\/(heads|tags|remotes)\//,'');}
function match(c){const d=detail(c.sha);const localizations=d?.notes?.localizations||c.notes?.localizations||{};const hay=[c.sha,c.subject,...Object.values(localizations).flatMap(n=>[n.title,n.summary,...(n.changes||[])]),c.author,...c.refs,...(state.searchIndex.get(c.sha)||(d?.diff.files||[]).flatMap(f=>[f.path,f.old_path||'']))].join(' ').toLowerCase();return (!state.refMembers||state.refMembers.has(c.sha))&&(!state.query||hay.includes(state.query.toLowerCase()))&&(state.filter==='all'||state.prefs.stars.includes(c.sha));}
const results=()=>state.commits.filter(match);
function independentHistoryStarts(commits){
 const groups=new Map();
 function root(id){if(!groups.has(id))groups.set(id,id);let tip=id;while(groups.get(tip)!==tip)tip=groups.get(tip);while(id!==tip){const next=groups.get(id);groups.set(id,tip);id=next;}return tip;}
 for(const c of commits)for(const parent of c.parents)groups.set(root(c.sha),root(parent));
 return new Set(commits.filter((c,i)=>i>0&&root(c.sha)!==root(commits[i-1].sha)).map(c=>c.sha));
}
function prepareGraph(){
 state.commitIndex=new Map(state.commits.map(c=>[c.sha,c]));
 const branch=state.prefs.main==='HEAD'?null:state.refs.find(r=>r.name===state.prefs.main&&r.target_type==='commit')||state.refs.find(r=>r.name==='refs/heads/main'&&r.target_type==='commit')||state.refs.find(r=>r.name===`refs/heads/${state.project.repository.branch}`&&r.target_type==='commit');
 state.mainRef=branch?.name||'HEAD';state.mainTip=branch?.sha||state.project.head;
 state.graph=RepriseGraph.layout(state.commits.map((c,i)=>({id:c.sha,parents:c.parents,order:state.commits.length-i})),{mainTip:state.mainTip,refs:state.refs.filter(r=>r.target_type==='commit').map(r=>({name:r.name,tip:r.sha,kind:r.kind}))});
 const slots=new Map();routeColors=new Map();
 for(const r of state.graph.routes){let n=r.isMain?0:1;if(!r.isMain)while((slots.get(n)||[]).some(x=>x.startRow<=r.endRow&&r.startRow<=x.endRow))n++;slots.set(n,[...(slots.get(n)||[]),r]);routeColors.set(r.id,colors[n%colors.length]);}
 const rows=new Map(state.graph.rows.map(r=>[r.id,r]));state.commits.sort((a,b)=>rows.get(a.sha).row-rows.get(b.sha).row);
 state.historyBreaks=independentHistoryStarts(state.commits);
 $('#graph-legend').innerHTML=`<span><i style="--route:${colors[0]}"></i>版本关系</span><span style="margin-left:auto">上新 · 下旧</span>`;
}
function renderHistory(){
 if(!state.graph)return;
 if(typeof renderDraftHistory==='function')renderDraftHistory();
 const focus=captureViewFocus($('#version-list'));
 const top=$('#history-scroll').scrollTop;$('#history-count').textContent=state.commits.length;$('#history-track').classList.add('compact');
 const n=results().length;$('#search-status').hidden=!state.query&&state.filter==='all'&&!state.searching;
 $('#search-status').innerHTML=`${state.searching?'<span id="search-progress"></span>':state.filter==='starred'?(n?`<span>${n}</span> <span>个收藏 · 保留版本关系</span>`:'还没有收藏版本'):n?`${n} 个匹配 · 其余为关系节点`:'没有匹配版本'} <button data-action="clear-search">查看全部</button>`;
 if(state.searching)updateSearchProgress();
 const bookmarkFilter=$('#bookmark-filter'),focused=state.filter==='starred';bookmarkFilter.dataset.filter=focused?'all':'starred';bookmarkFilter.setAttribute('aria-pressed',focused);bookmarkFilter.classList.toggle('active',focused);$('#bookmark-filter-icon').innerHTML=icon('star');$('#bookmark-count').textContent=state.commits.filter(c=>state.prefs.stars.includes(c.sha)).length;$('#history-track').classList.toggle('bookmark-focus',focused);
 $('#version-list').innerHTML=state.commits.map(c=>{const matched=match(c),selected=matched&&state.selected===c.sha,starred=state.prefs.stars.includes(c.sha);return `${state.historyBreaks.has(c.sha)?'<div class="history-divider" role="separator" aria-label="独立历史" title="与上一段历史没有已记录的父子连接"><span>独立历史</span><span class="history-divider-note">与上方无连接</span></div>':''}<button class="version-row ${starred?'bookmarked':''} ${selected?'selected':''} ${matched?'':'dimmed context-row'}" data-action="select" data-id="${c.sha}" aria-current="${selected}" data-user-label aria-label="${uiText('版本')} ${esc(versionTitle(c))}${starred?'，'+uiText('已收藏'):''}${matched?'':'，'+uiText('关系节点')}"><span class="version-meta"><span class="version-identity"><span class="version-number">${esc(versionLabel(c))}</span>${state.prefs.stars.includes(c.sha)?icon('star'):''}${c.sha===state.project.head?'<span class="new-label">当前版本</span>':''}</span><time class="version-date" datetime="${esc(c.committed_at)}" title="${esc(formatDate(c.committed_at,true))}">${esc(formatDate(c.committed_at))}</time></span><span class="version-title" data-user-content title="${esc(versionTitle(c))}">${esc(versionTitle(c))}</span>${starred?`<span class="history-bookmark" title="已收藏" aria-label="已收藏">${icon('star')}</span>`:''}<span class="version-summary" data-user-content title="${esc(versionCaption(c))}">${esc(versionCaption(c))}</span></button>`;}).join('');
 if(state.graph.boundaries.length)$('#version-list').insertAdjacentHTML('beforeend','<p class="snapshot-message" style="padding-left:20px">虚线连接当前历史中不可读取的版本</p>');
 $('#history-scroll').scrollTop=top;restoreViewFocus(focus,$('#version-list'));requestAnimationFrame(drawGraph);
}
function rounded(points){const a=[];for(const p of points){if(a.length>=2){const x=a[a.length-2],y=a[a.length-1];if((x.x===y.x&&y.x===p.x)||(x.y===y.y&&y.y===p.y))a.pop();}a.push(p);}if(a.length<2)return '';let d=`M${a[0].x},${a[0].y}`;for(let i=1;i<a.length-1;i++){const x=a[i-1],p=a[i],y=a[i+1],before=Math.hypot(x.x-p.x,x.y-p.y),after=Math.hypot(y.x-p.x,y.y-p.y),r=Math.min(7,before/2,after/2);if(!before||!after)continue;d+=`L${p.x+(x.x-p.x)*r/before},${p.y+(x.y-p.y)*r/before}Q${p.x},${p.y} ${p.x+(y.x-p.x)*r/after},${p.y+(y.y-p.y)*r/after}`;}return d+`L${a.at(-1).x},${a.at(-1).y}`;}
function drawGraph(){
 if(!state.graph||$('#history-scroll').hidden)return;const svg=$('#route-map'),track=$('#history-track'),pos=new Map(),step=18,x=n=>19+n*step;
 // Reserve all node/bypass columns before measuring text-dependent row heights.
 const width=Math.max(76,x(state.graph.laneCount-1)+17);track.style.setProperty('--graph-gutter',`${width+2}px`);svg.setAttribute('width',width);
 // Keep a readable title column when many real branches need extra lanes.
 track.style.minWidth=`${width+202}px`;
 $('.history').style.setProperty('--graph-panel-width',`${Math.max(334,width+226)}px`);
 const overflow=$('#graph-width-hint');
 if(overflow){overflow.hidden=$('#history-scroll').scrollWidth<=$('#history-scroll').clientWidth+1;overflow.textContent=contentText('分支较多，可横向滚动查看完整路线与标题。','Many branches: scroll horizontally for the complete routes and titles.');}
 const rows=new Map($$('.version-row[data-id]').map(row=>[row.dataset.id,row]));
 state.graph.rows.forEach(n=>{const r=rows.get(n.id),m=r?.querySelector('.version-title');if(r)pos.set(n.row,r.offsetTop+(m?m.offsetTop+m.offsetHeight/2:r.offsetHeight/2));});
 const height=$('#version-list').offsetHeight,y=n=>{const f=Math.floor(n),c=Math.ceil(n),a=pos.get(f)??height-12,b=pos.get(c)??height-12;return a+(b-a)*(n-f);};
 svg.setAttribute('height',height);svg.style.height=height+'px';
 svg.innerHTML=state.graph.edges.map(e=>`<path data-child="${e.childId}" data-parent="${e.parentId}" d="${rounded(e.points.map(p=>({x:x(p.x),y:y(p.y)})))}" fill="none" stroke="${routeColors.get(e.routeId)}" stroke-width="2" stroke-linecap="round" ${e.missingParent?'stroke-dasharray="3 3"':''}/>`).join('')+state.graph.rows.map(n=>{const selected=n.id===state.selected&&match(commit(n.id)),color=routeColors.get(n.routeId);return `${selected?`<circle cx="${x(n.lane)}" cy="${y(n.row)}" r="8" fill="#fff" stroke="#34363a" stroke-width="1.5"/>`:''}<circle data-node="${n.id}" cx="${x(n.lane)}" cy="${y(n.row)}" r="${n.isMerge?4.6:3.8}" fill="${selected?color:'var(--side)'}" stroke="${color}" stroke-width="1.8"/>`;}).join('');
}
const groups=[['验证与回归','测试与验收文件',p=>/^(tests?\/|.*\/tests?\/)/.test(p)],['界面与交互','网页、样式与界面脚本',p=>/\.(html?|css|scss|sass|less|jsx?|tsx?|vue|svelte)$/i.test(p)],['图片与媒体','图片、视频与字体文件',p=>/\.(png|jpe?g|webp|gif|svg|mp4|webm|mov|woff2?|ttf|otf)$/i.test(p)],['内容与说明','文档与文本内容',p=>/\.(md|mdx|txt)$/i.test(p)],['核心与脚本','应用源码与工具脚本',p=>p.startsWith('src/')||/\.(py|go|rs|sh|swift)$/i.test(p)],['配置与数据','配置、清单与结构化数据',p=>/\.(json|toml|ya?ml|lock|csv)$/i.test(p)||/(^|\/)(Dockerfile|Makefile|\.[^/]+)$/.test(p)],['其他文件','此版本的其他文件变化',()=>true]];
const labels={A:'新增',M:'修改',D:'删除',R:'重命名',C:'复制',T:'类型变化'};
function summary(d){if(uiLanguage==='en'){if(d.diff.available===false)return 'The comparison baseline is unavailable.';const c=d.diff.counts;return `${c.total||0} changed files${c.added?`, ${c.added} added`:''}${c.modified?`, ${c.modified} modified`:''}${c.deleted?`, ${c.deleted} deleted`:''}${c.renamed?`, ${c.renamed} renamed`:''}.`;}if(d.diff.available===false)return '该提交的比较基准暂不可读取。';const c=d.diff.counts;return `此版本更新 ${c.total||0} 个文件${c.added?`，新增 ${c.added} 个`:''}${c.modified?`，修改 ${c.modified} 个`:''}${c.deleted?`，删除 ${c.deleted} 个`:''}${c.renamed?`，重命名 ${c.renamed} 个`:''}。`;}
function fileRows(files){return files.map(f=>{
 const status=f.status[0],label=uiLanguage==='en'?({A:'Added',M:'Modified',D:'Deleted',R:'Renamed',C:'Copied',T:'Type changed'}[status]||f.status):(labels[status]||f.status);
 const inspect=`<button class="file-row file-inspect" data-action="file" data-path="${esc(f.path)}"><span class="file-status" title="${esc(label)}">${esc(status)}</span><code>${f.old_path?`${esc(f.old_path)} → `:''}${esc(f.path)}</code><span class="file-arrow">↗</span></button>`;
 if(state.project?.kind!=='folder')return inspect;
 const sha=status==='D'?(state.tab==='compare'?state.comparison?.base:detail(state.selected)?.diff.base):state.selected;
 return `<div class="file-task-row">${inspect}${sha?`<button class="text-button" data-action="recover-file-side" data-project="${esc(revisionProject(sha))}" data-sha="${esc(sha)}" data-path="${esc(f.path)}" aria-label="${contentText('恢复文件','Recover file')} ${esc(f.path)}">${status==='D'?contentText('从 A 恢复','Recover from A'):contentText('恢复文件','Recover file')}</button>`:''}</div>`;
}).join('');}

function renderChanges(d){
 if(d.content)return (visualPresentation(d)?versionRecognitionCard(d):'')+renderFolderChanges(d)+`<details class="content-facts" data-keep-open="version-facts"><summary>${contentText('版本信息与存储','Version details and storage')}</summary>${folderSummary(d)}</details>`;
 if(d.diff.files_truncated)return `<section><h3>${uiLanguage==='en'?'Archived files':'归档文件'}</h3><p class="snapshot-message">${uiLanguage==='en'?'Showing the first 200 changes. Full recovery and export still include the complete archive.':'显示前 200 项变化。完整恢复和导出仍包含全部归档内容。'}</p><div class="changed-files">${fileRows(d.diff.files)}</div></section>`;
 const visuals=visualPresentation(d)?renderVisualUpdates(d):'';if(visuals)return updateExplanations(d)+visuals;
 if(d.diff.available===false)return updateExplanations(d)+`<div class="empty-preview"><h3>暂时无法读取文件差异</h3><p>${esc(d.diff.error)}</p></div>`;
 let rest=d.diff.files.slice(),sections=[];for(const [title,description,test] of groups){const files=rest.filter(f=>test(f.path));rest=rest.filter(f=>!test(f.path));if(!files.length)continue;sections.push(`<section class="feature"><div class="feature-copy"><span class="feature-kind"><span class="feature-number">${String(sections.length+1).padStart(2,'0')}</span>${files.length} 个文件</span><h3>${title}</h3><p>${uiLanguage==='en'?esc(uiText(description))+'.<br>File changes relative to '+(d.diff.base?'the first parent.':'an empty repository.'):description+'。<br>记录来自此提交相对'+(d.diff.base?'第一父提交':'空仓库')+'的文件变化。'}</p></div><div class="changed-files">${fileRows(files)}</div></section>`);}
 return updateExplanations(d)+(sections.join('')||'<div class="empty-preview"><h3>此提交没有文件变化</h3><p>提交信息与父子关系仍然保留。</p></div>');
}
function mediaItems(d){return d?evidenceItems(d.evidence,d.commit.sha):[];}
function renderPreview(d,{comparison=false,pairedTarget=null}={}){
 if(d.content&&!comparison){
  const visual=visualPresentation(d),preview=`<section class="version-recognition"><div class="version-recognition-heading"><h3>${contentText('此版本的预览','Preview of this version')}</h3><button class="text-button" data-action="quick-preview">${contentText('保存此稿画面','Capture this draft')}</button></div><p class="snapshot-message">${contentText('只显示绑定此版本的资料；运行使用独立副本。','Only evidence bound to this version appears; runtime previews use a separate copy.')}</p>${rememberCaptureControl(d)}${renderRuntimes(d)}${renderPreview(d,{comparison:true})}</section>`;
  return (visual?preview:'')+(visual?`<details class="draft-file-disclosure" data-keep-open="draft-files"><summary>${contentText('查看这一稿的文件','Inspect this draft’s files')}</summary>${renderFolderFiles()}</details>`:`<h3>${contentText('此版本的文件','Files in this version')}</h3>${renderFolderFiles()}`)+(visual?'':`<details data-keep-open="optional-preview"><summary>${contentText('可选：截图与运行预览','Optional: screenshots and runtime preview')}</summary>${preview}</details>`);
 }
 const items=pairedTarget&&pairedTarget.commit.sha!==d.commit.sha?baselineMediaItems(pairedTarget,d,d.commit.sha):mediaItems(d),[title,message]=previewEmptyText(d);
 const content=!items.length?`<div class="empty-preview">${icon('file')}<h3>${title}</h3><p>${message}</p>${comparison?'':'<button class="secondary-button" data-action="preview-settings">添加预览资料</button>'}</div>`:items.map(item=>{
  const caption=item.title||item.name||item.scenario||uiText('版本预览');
  const media=item.missing||item.error||!item.url?`<div class="empty-content" data-user-content>${esc(item.error||uiText(item.missing?'预览文件不可用':'资料地址不可用'))}</div>`:item.kind==='image'?`<button class="media-open" data-user-label data-action="media" data-record="${esc(item.record)}" data-index="${item.index}" aria-label="${uiText('放大')} ${esc(caption)}"><img src="${esc(item.url)}" alt="${esc(caption)}" loading="lazy"></button>`:item.kind==='video'?`<video src="${esc(item.url)}" controls preload="metadata"></video>`:`<div class="empty-content"><a href="${esc(item.url)}" target="_blank" rel="noopener" data-user-content>${esc(caption)} ↗</a></div>`;
  return `<figure class="saved-media">${media}<figcaption><span data-user-content>${esc(caption)}</span></figcaption></figure>`;
 }).join('');
 const diagnostics=renderCaptureDiagnostics(d);
 return (comparison?'':renderRuntimes(d))+(items.length?diagnostics+content:content+diagnostics);
}
function emptyVersionContent(){
 let title,description,actions;
 if(state.filter==='starred'||state.commits.length){
  const starred=state.filter==='starred';
  title=contentText(starred?'还没有收藏版本':'没有匹配版本',starred?'No starred versions':'No matching versions');
  description=contentText(starred?'点击版本右侧的星标，即可在这里定位。':'清空搜索或切换到全部版本，即可继续查看。',starred?'Star a version to find it here.':'Clear the search or show all versions to continue.');
  actions=`<button class="secondary-button" data-action="clear-search">${contentText('查看全部版本','Show all versions')}</button>`;
 }else{
  const kind=state.project?.kind;
  title=contentText(kind==='folder'?'还没有保存稿件':kind==='archive'?'没有可显示的归档版本':'这个项目还没有提交',kind==='folder'?'No drafts saved yet':kind==='archive'?'No archive versions to display':'This project has no commits');
  description=contentText(kind==='folder'?'保存一稿，留下当前网页的文件和画面。':kind==='archive'?'原始归档继续保留，可以选择其他项目查看。':'首次提交后刷新，版本历史会出现在这里。',kind==='folder'?'Save a draft to keep the website files and their appearance.':kind==='archive'?'The original archive remains saved. Choose another project to continue browsing.':'Refresh after the first commit to see its history here.');
  actions=(kind==='folder'?`<button class="primary-button" data-action="content-snapshot">${contentText('保存第一稿','Save your first draft')}</button>`:'')+`<button class="secondary-button" data-action="content-projects">${contentText('选择项目','Choose a project')}</button>`;
 }
 return `<div class="empty-content"><h3>${title}</h3><p>${description}</p><div class="content-empty-actions">${actions}</div></div>`;
}
function renderDetail(){
 const focus=captureViewFocus($('#detail'));
 const opened=openDisclosures($('#detail')),top=$('#detail').scrollTop;
 const c=commit(state.selected);if(!c){$('#detail').innerHTML=emptyVersionContent();return;}
 const d=detail(c.sha),starred=state.prefs.stars.includes(c.sha),items=d?mediaItems(d):[],notes=versionNotes(c);
 $('#detail').innerHTML=`<div class="detail-head"><div class="detail-topline"><div class="eyebrow"><span class="version-tag">${esc(versionLabel(c))}</span><span class="eyebrow-line"></span><time datetime="${esc(c.committed_at)}">${esc(formatDate(c.committed_at,true))}</time></div><div class="detail-actions"><button class="primary-button" data-action="run" ${d?'':'disabled'}>${versionPreviewLabel(d)}</button><button class="secondary-button" data-action="delete-version" ${d?'':'disabled'}>${contentText('删除版本','Delete version')}</button></div></div><div class="detail-title"><div class="version-name"><h2 data-user-content>${esc(versionTitle(c))}</h2><button class="edit-entry edit-primary" data-action="edit-version" ${d?'':'disabled'} aria-label="编辑版本信息" title="编辑版本信息">${icon('pencil')}</button></div><button class="star-button ${starred?'starred':''}" data-action="star" aria-label="${starred?'取消收藏':'收藏此版本'}" aria-pressed="${starred}">${icon('star')}</button></div><div class="release-intro-row editable-region"><p class="release-intro" data-user-content>${d?esc(notes?.summary||summary(d)):uiText('正在读取此提交的变化…')}</p>${d?``:''}</div><div class="detail-subline">${c.parents.length?c.parents.map((p,i)=>`<button data-action="parent" data-id="${p}" data-user-label title="${esc(versionTitle(commit(p)||{sha:p,subject:uiText('历史版本')}))}"><span>${uiText(i?'合并版本':'上一版')}</span> · <span data-user-content>${esc(versionTitle(commit(p)||{sha:p,subject:uiText('历史版本')}))}</span></button>`).join(''):'<span>项目起点</span>'}<span>·</span><span class="version-author"><span data-user-content>${esc(d?.notes?.author??c.notes?.author??c.author)}</span><button class="edit-entry" data-action="edit-author" ${d?'':'disabled'} aria-label="${contentText('编辑显示作者','Edit display author')}" title="${contentText('编辑显示作者','Edit display author')}">${icon('pencil')}</button></span><button class="text-button detail-recover" data-action="recovery" ${d?'':'disabled'}>${contentText('取出这一稿','Recover this draft')}</button></div><div class="detail-tabs" role="tablist" aria-label="查看内容">${[['updates',d&&visualPresentation(d)?contentText('本次更新','Updates'):contentText('文件变化','File changes'),d?.diff.counts.total??'…'],['preview',state.project?.kind==='folder'?(d&&visualPresentation(d)?contentText('这一稿的画面','This draft’s appearance'):contentText('全部文件','All files')):contentText('版本预览','Version preview'),state.project?.kind==='folder'?(d&&visualPresentation(d)?items.filter(visualEvidence).length:(d?.content?.stats.files??'…')):items.length],['compare',contentText('比较版本','Compare versions'),null]].map(([tab,label,count])=>`<button id="tab-${tab}" data-action="tab" data-tab="${tab}" role="tab" tabindex="${state.tab===tab?0:-1}" aria-selected="${state.tab===tab}" aria-controls="live-content" class="${state.tab===tab?'active':''}">${label}${count===null?'':`<span class="tab-count">${count}</span>`}</button>`).join('')}</div></div><div id="live-content" class="detail-content" role="tabpanel" aria-labelledby="tab-${state.tab}">${versionSelectionNotice()}${typeof importReturnNotice==='function'?importReturnNotice():''}${d?(state.tab==='compare'?renderComparison():state.tab==='preview'?renderPreview(d):renderChanges(d)):'<div class="load-state">正在读取文件变化…</div>'}</div>`;
 restoreDisclosures($('#detail'),opened);restoreViewFocus(focus,$('#detail'));$('#detail').scrollTop=top;
 if(d&&state.tab==='updates')requestAnimationFrame(enhanceUpdateVisuals);
}
async function loadDetail(id,signal,source=revisionProject(id)){
 const owner=projectRequest,k=`${source}:${id}`;
 if(state.details.has(k))return state.details.get(k);
 const d=await api(`/api/projects/${source}/versions/${id}`,{signal});
 if(owner!==projectRequest)return d;
 // File searches survive eviction without retaining every tree, recipe and media record.
 state.searchIndex.set(id,d.diff.files.flatMap(f=>[f.path,f.old_path||'']));
 const pinned=new Set([id,state.selected,state.comparison?.base,state.comparison?.target,
  state.comparisonDraft?.base,state.comparisonDraft?.target,detail(state.selected)?.diff.base]);
 if(state.details.size>=128){
  const oldest=[...state.details.keys()].find(key=>!pinned.has(key.slice(key.lastIndexOf(':')+1)));
  if(oldest)state.details.delete(oldest);
 }
 state.details.set(k,d);
 return d;
}
async function choose(id,{resetTab=false,fromComparison=false}={}){
 if(!commit(id)){notify(state.project?.kind==='folder'?contentText('该历史版本当前不可读取，原有关系记录仍保留。','This historical version is unavailable; its recorded relationship remains.'):uiText('父提交尚未加载，当前历史保留了它的边界。'));return;}
 const c=commit(id);if(id!==state.selected){state.comparison=null;if(!fromComparison){++state.comparisonRequest;state.comparisonDraft=null;state.comparisonLoading=false;state.comparisonError=null;}}if(!match(c)){clearTimeout(searchTimer);++searchRequest;state.searching=false;state.query='';state.filter='all';state.ref='--all';state.refMembers=null;$('#search').value='';}
 state.selected=id;if(!state.query&&state.filter==='all')state.anchorSelection=id;if(resetTab)state.tab=draftView()==='pictures'?'preview':'updates';const url=new URL(location.href);url.searchParams.set('sha',id);history.replaceState(null,'',url);$('#detail').scrollTop=0;renderHistory();renderDetail();requestAnimationFrame(()=>{if(typeof scrollSelectedDraft==='function')scrollSelectedDraft();const row=$(`.version-row[data-id="${id}"]`),scroller=$('#history-scroll');if(row&&scroller){const top=row.offsetTop,bottom=top+row.offsetHeight;if(top<scroller.scrollTop)scroller.scrollTop=top;else if(bottom>scroller.scrollTop+scroller.clientHeight)scroller.scrollTop=bottom-scroller.clientHeight;}});
 detailAbort?.abort();detailAbort=new AbortController();const n=++selectRequest;
 try{const d=await loadDetail(id,detailAbort.signal);if(n===selectRequest&&state.selected===id){renderHistory();renderDetail();if(state.tab==='updates'){await ensureUpdateBaseline(d,detailAbort.signal);if(n===selectRequest&&state.selected===id&&state.tab==='updates')renderDetail();}}}catch(e){if(e.name==='AbortError')return;if(n===selectRequest){$('#live-content').innerHTML=`<div class="empty-preview"><h3>读取失败</h3><p>${esc(e.message)}</p><button class="secondary-button" data-action="retry">重试此提交</button></div>`;}}
}
function updateSearchProgress(){
 const label=$('#search-progress');if(!label)return;
 label.textContent=contentText(`正在搜索版本与文件… ${state.searchIndex.size}/${state.commits.length}`,`Searching revisions and files… ${state.searchIndex.size}/${state.commits.length}`);
}
async function searchAll(){
 const n=++searchRequest;state.searching=true;renderHistory();const project=state.project.id,groups=new Map(),batches=[];let cursor=0;
 for(const c of state.commits)if(!state.searchIndex.has(c.sha)){const source=revisionProject(c.sha);if(!groups.has(source))groups.set(source,[]);groups.get(source).push(c.sha);}
 for(const [source,shas] of groups)for(let i=0;i<shas.length;i+=128)batches.push({source,shas:shas.slice(i,i+128)});
 try{
  await Promise.all(Array.from({length:4},async()=>{
   while(cursor<batches.length){
    const batch=batches[cursor++],result=await api(`/api/projects/${batch.source}/search-index`,{method:'POST',body:JSON.stringify({shas:batch.shas})});
    if(n!==searchRequest||project!==state.project.id)return;
    for(const id of batch.shas){const paths=result.paths?.[id];if(!Array.isArray(paths)||paths.some(p=>typeof p!=='string'))throw Error(contentText('文件搜索索引不完整。','The file search index is incomplete.'));state.searchIndex.set(id,paths);}
    updateSearchProgress();
   }
  }));
  if(n!==searchRequest||project!==state.project.id)return;
  state.searching=false;settleFilter();
 }catch(e){if(n!==searchRequest)return;state.searching=false;renderHistory();notify('部分文件变化读取失败，搜索结果可能不完整：'+e.message);}
}
function settleFilter(){const matches=results();if(!matches.some(c=>c.sha===state.selected))state.selected=matches.find(c=>c.sha===state.anchorSelection)?.sha||matches[0]?.sha||null;renderHistory();renderDetail();if(state.selected)choose(state.selected);}
async function loadProject(id,{preserve=false}={}){
 const n=++projectRequest;++selectRequest;++searchRequest;detailAbort?.abort();state.comparison=null;state.comparisonDraft=null;state.comparisonLoading=false;state.comparisonError=null;++state.comparisonRequest;state.loading=true;state.searching=false;$('#source-status').textContent='正在读取项目…';
 try{const s=await api(query('/api/workspace/snapshot',{project:id}));if(n!==projectRequest)return;state.project=s.project;state.refs=s.refs;state.commits=s.commits;state.historySources=s.history_sources||[];const origin=$('#history-origin'),archived=state.historySources.filter(h=>h.kind==='archive').reduce((n,h)=>n+h.unique_commits,0),current=state.historySources.find(h=>h.kind==='current')?.count||state.commits.length;origin.hidden=!archived;origin.textContent=uiLanguage==='en'?`${current} repository commits · ${archived} archived records`:`当前仓库 ${current} 条 · 历史存档 ${archived} 条`;state.ref='--all';state.refMembers=null;state.snapshot=s.snapshot;state.warnings=s.warnings;state.status=s.status;state.loading=false;readPrefs();prepareGraph();
 setWorkspaceView(state.view,{render:false});$('#project-name').textContent=s.project.name;$('#project-name').title=s.project.name;document.title=s.project.name+' · 版本';
 state.details.clear();state.searchIndex.clear();versionChoices();
 if(!preserve){state.contentFileQuery='';state.query='';state.filter='all';state.tab=draftView()==='pictures'?'preview':'updates';state.draftLimit=60;state.anchorSelection=null;$('#search').value='';}
 if(!commit(state.selected)||!preserve)state.selected=commit(s.project.head)?.sha||state.commits[0]?.sha||null;
 const count=s.status.changes?.length||0;$('#source-status').textContent=`${current} 个提交${archived?' · '+archived+' 条历史存档':''} · ${s.status.available===false?'无工作区':count?count+' 项未提交改动':'工作区干净'}`;$('#snapshot-status').textContent=s.warnings.length?'部分历史未加载':'Git 实时数据';
 $('#content-save').hidden=s.project.kind!=='folder';if(s.project.kind==='folder'){$('#source-status').textContent=uiLanguage==='en'?`${current} saved versions · ${s.status.available===false?'source unavailable':count+' changed entries'}`:`${current} 个已保存版本 · ${s.status.available===false?'原文件夹不可用':count+' 项变化'}`;$('#snapshot-status').textContent=uiText('本地内容版本');}if(s.project.kind==='archive'){$('#source-status').textContent=uiLanguage==='en'?`${current} archived snapshots`:`${current} 个归档快照`;$('#snapshot-status').textContent=uiLanguage==='en'?'Original archive preserved':'原始归档已保留';}refreshContentStatus();const u=new URL(location.href);u.searchParams.set('project',id);history.replaceState(null,'',u);renderHistory();renderDetail();if(state.selected)await choose(state.selected);else renderDetail();if(typeof loadDraftImages==='function')loadDraftImages();
 }catch(e){if(n!==projectRequest)return;state.loading=false;$('#source-status').textContent='读取失败';$('#detail').innerHTML=`<div class="empty-content"><h3>无法读取项目</h3><p>${esc(e.message)}</p><button class="secondary-button" data-action="refresh">重试</button></div>`;notify(e.message);}
}
let dialogParent=null,dialogActionOrigin=null;
function installFocusBehavior(doc=document){
 // WebKit can match :focus-visible after a pointer-opened modal. Record the
 // actual input method instead of relying on engine-specific focus heuristics.
 const root=doc.documentElement;root.dataset.inputModality='pointer';
 doc.addEventListener('pointerdown',()=>{root.dataset.inputModality='pointer';},true);
 doc.addEventListener('keydown',event=>{
  if(!event.altKey&&!event.ctrlKey&&!event.metaKey&&!['Alt','Control','Meta','Shift'].includes(event.key))root.dataset.inputModality='keyboard';
 },true);
}
function pauseDialogMedia(){for(const media of $$('#dialog video, #dialog audio'))media.pause();}
let dialogController=null;
function dialogs(){
 if(!dialogController)dialogController=RepriseDialogs.create({
  element:()=>$('#dialog'),beforeChange:pauseDialogMedia,
  onTransition:()=>{state.dialogRequest++;},
  origin:()=>returnFocus?.isConnected?returnFocus:returnFocus?.dataset.action?$(`[data-action="${returnFocus.dataset.action}"]`):null,
  onRestore:parent=>{
   returnFocus=parent.origin;dialogParent=parent.parent||null;
   if($('#dialog').dataset.fileComparison)renderFileComparison();
   refreshSettingsManagement();localizeDOM();
   if(parent.focused?.isConnected)parent.focused.focus({preventScroll:true});
   else restoreViewFocus(parent.focus,$('#dialog'));
  }
 });
 return dialogController;
}
function dialogShell(title,content,footer='',wide=false,parent=null,view=''){
 if(!$('#dialog').open)returnFocus=dialogActionOrigin?.isConnected?dialogActionOrigin:document.activeElement;
 dialogParent=parent;
 const markup=`<div class="dialog-header"><div><h2 id="dialog-title" tabindex="-1">${esc(title)}</h2></div><button class="icon-button" data-action="close" aria-label="${parent?uiText('返回上一页'):uiText('关闭')}">${icon('close')}</button></div><div class="dialog-body">${content}</div><div class="dialog-footer"><span id="dialog-status" role="status"></span>${footer||'<button class="secondary-button" data-action="close">返回</button>'}</div>`;
 return dialogs().open(markup,{className:[wide?'file-dialog':'',view==='runtime'?'runtime-preview-dialog':''].filter(Boolean).join(' '),dataset:view?{dialogView:view}:{}});
}
function closeDialog({returnToParent=true}={}){
 const parent=returnToParent?dialogParent:null;dialogParent=null;
 const recoveryJob=$('#dialog').querySelector('[data-recovery-job]')?.dataset.recoveryJob;
 if(recoveryJob)state.recoveryParents?.delete(recoveryJob);
 dialogs().close(parent);
}
function conditions(){recipeDialog();}
async function settings(){
 await refreshWorkspace();dialogShell('项目设置',settingsContent(),'<button class="primary-button" data-action="save-settings">完成</button>');$('#dialog').classList.add('settings-dialog');
}
function working(){const files=state.status?.changes||[];dialogShell('当前工作区',`<p class="project-path"><code>${esc(state.project?.path)}</code></p><div class="current-git-summary"><p>当前版本 · <span data-user-content>${esc(versionTitle(commit(state.project?.head)||{sha:state.project?.head,subject:uiText('历史版本')}))}</span></p><p>以下改动尚未保存到版本中。</p></div><div class="changed-files">${files.length?files.map(f=>`<div class="file-row"><span class="file-status">${esc(f.status||'?')}</span><code>${esc(f.path)}</code></div>`).join(''):`<div class="empty-content">${state.status?.available===false?'此仓库没有工作区。':'工作区干净。'}</div>`}</div>`,`<button class="secondary-button" data-action="close">返回</button>${state.project?.head?'<button class="primary-button" data-action="working-head">查看当前版本</button>':''}`);}
async function openFile(path){
 const sha=state.selected,project=state.tab==='compare'&&state.comparison?state.comparison.source_project_id:revisionProject();
 dialogShell(path,`<p role="status">${contentText('读取两侧文件…','Reading both files…')}</p>`,'',true);$('#dialog-title').setAttribute('data-user-content','');
 const n=state.dialogRequest;
 try{
  const d=await api(query('/api/workspace/file',{project,sha,path,...(state.tab==='compare'&&state.comparison?{base:state.comparison.base}:{})}));
  if(n!==state.dialogRequest||!$('#dialog').open)return;
  state.fileComparison={path,project,data:d};renderFileComparison();
 }catch(e){if(n===state.dialogRequest)$('#dialog .dialog-body').textContent=e.message;}
}
function renderFileComparison(){
 if(!$('#dialog').open||!$('#dialog .dialog-body'))return;
 const {path,project,data:d}=state.fileComparison;
 const side=(label,sha,value,base)=>`<section class="code-side-heading"><h3>${label}</h3><p data-user-content>${esc(versionTitle(commit(sha)||{sha,subject:short(sha)}))}</p>${base&&d.base_path&&d.base_path!==path?`<p data-user-content><code>${esc(d.base_path)}</code></p>`:''}${!value.absent&&sha?`<button class="secondary-button" data-action="recover-file-side" data-project="${esc(project)}" data-sha="${esc(sha)}" data-path="${esc(base?(d.base_path||path):path)}">${base?contentText('恢复 A 的文件','Recover file from A'):contentText('恢复 B 的文件','Recover file from B')}</button>`:''}</section>`;
 $('#dialog .dialog-body').innerHTML=`${previewLanguageControls()}<div class="code-columns">${side(contentText('A · 基准版本','A · Base version'),d.base,d.before,true)}${side(contentText('B · 目标版本','B · Target version'),d.sha,d.after,false)}</div>${RepriseTextDiff.render(d.text_diff,{language:uiLanguage})}`;
 $('#dialog').dataset.fileComparison='true';
}

const coreActions={
 select:async b=>{await choose(b.dataset.id);if(state.tab==='compare')await compareSelection();},
 parent:async b=>{await choose(b.dataset.id);if(state.tab==='compare')await compareSelection();},
 tab:b=>setDetailTab(b.dataset.tab),
 refresh:async()=>{
  if(state.loading)return;
  await refreshWorkspace();await loadProject(state.project?.id||new URLSearchParams(location.search).get('project'),{preserve:true});
 },
 retry:()=>state.selected&&choose(state.selected),
 filter:b=>{
  const previous=state.filter;state.filter=b.dataset.filter;
  if(state.filter==='starred')state.bookmarkOrigin=state.selected;
  else if(previous==='starred'){state.selected=state.bookmarkOrigin;state.bookmarkOrigin=null;}
  settleFilter();
 },
 'clear-search':()=>{
  clearTimeout(searchTimer);++searchRequest;state.searching=false;state.query='';state.filter='all';state.selected=state.bookmarkOrigin||state.selected;
  state.bookmarkOrigin=null;state.ref='--all';state.refMembers=null;$('#search').value='';settleFilter();
 },
 star:()=>toggleBookmark(),
 conditions:()=>conditions(),
 settings:()=>settings(),
 'preview-settings':()=>manualDialog(),
 working:()=>working(),
 file:b=>openFile(b.dataset.path),
 close:()=>closeDialog(),
 more:()=>dialogShell('提交信息',`<p class="identity-sha">${esc(state.selected)}</p><p data-user-content>${esc(commit(state.selected)?.subject)}</p><p>引用：<span data-user-content>${esc(commit(state.selected)?.refs.map(refLabel).join(' · ')||'无直接引用')}</span></p><button class="secondary-button" data-action="copy-sha">复制完整 SHA</button>`),
 'copy-sha':async()=>{
  try{await navigator.clipboard.writeText(state.selected);$('#dialog-status').textContent='已复制';}
  catch{$('#dialog-status').textContent='无法自动复制，可选择上方完整 SHA。';}
 },
 'save-settings':()=>{if(state.project){state.prefs.presentation=$('#project-presentation')?.value||state.prefs.presentation;savePrefs();}closeDialog();if(state.project)renderDetail();else renderFirstRun();},
 import:async b=>{
  const path=$('#import-path').value.trim();if(!path){$('#dialog-status').textContent='请填写本地 Git 仓库路径。';return;}
  b.disabled=true;
  try{const project=await api('/api/projects',{method:'POST',body:JSON.stringify({path})});closeDialog();await loadProject(project.id);}
  catch(error){$('#dialog-status').textContent=error.message;b.disabled=false;}
 }
};
async function action(button){
 const name=button.dataset.action;
 const handler=[workspaceActions,coreActions,featureActions,parityActions].find(handlers=>Object.hasOwn(handlers,name))?.[name];
 // macOS does not always focus a button clicked with the mouse. Preserve the
 // actual invoking control across asynchronous dialog preparation as well.
 const previous=dialogActionOrigin;dialogActionOrigin=button;
 try{if(handler)await handler(button);}finally{if(dialogActionOrigin===button)dialogActionOrigin=previous;}
}
document.addEventListener('click',e=>{const summary=e.target.closest('.settings-advanced>summary');if(summary){e.preventDefault();toggleSettingsDisclosure(summary.parentElement);return;}const diffButton=e.target.closest('[data-text-diff-action]');if(diffButton&&RepriseTextDiff.handleAction(diffButton,$('#dialog'))){e.preventDefault();return;}const b=e.target.closest('[data-action]');if(!b||b.disabled)return;const saving=b.dataset.action.startsWith('save-');if(saving)b.disabled=true;action(b).catch(e=>{if($('#dialog').open&&$('#dialog-status'))$('#dialog-status').textContent=e.message;else notify(e.message);}).finally(()=>{if(saving&&b.isConnected)b.disabled=false;});});
installFocusBehavior();
const settingsReducedMotion=typeof matchMedia==='function'?matchMedia('(prefers-reduced-motion: reduce)'):null;
settingsReducedMotion?.addEventListener('change',event=>{
 if(event.matches)for(const details of document.querySelectorAll('.settings-advanced'))settingsDisclosureMotion.get(details)?.animations.forEach(animation=>animation.finish());
});
$('#search').addEventListener('input',()=>{clearTimeout(searchTimer);state.query=$('#search').value.trim();if(!state.query){++searchRequest;state.searching=false;settleFilter();return;}renderHistory();searchTimer=setTimeout(searchAll,180);});
$('#dialog').addEventListener('cancel',e=>{e.preventDefault();closeDialog();});
document.addEventListener('keydown',e=>{if(e.key==='/'&&!$('#dialog').open&&!/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)){e.preventDefault();$('#search').focus();}if(e.target.closest('[role="tablist"]')&&['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const tabs=['updates','preview','compare'],i=tabs.indexOf(state.tab);const tab=e.key==='Home'?tabs[0]:e.key==='End'?tabs[2]:tabs[(i+(e.key==='ArrowRight'?1:2))%3];setDetailTab(tab);}});
window.addEventListener('resize',()=>requestAnimationFrame(drawGraph));
$('#project-name').textContent=uiText('正在读取项目…');
$('#search-icon').innerHTML=icon('search');$('[data-action="settings"]').innerHTML=icon('settings');$('[data-action="refresh"]').innerHTML=icon('refresh');
localizeDOM();
window.repriseWorkspace={snapshot:()=>({view:state.view,language:uiLanguage,ref:state.ref,project:state.project?.name,projectId:state.project?.id,sha:state.selected,commits:state.commits.map(c=>({sha:c.sha,parents:c.parents,source:c.source_project_id,archived:!!c.archived})),mainRef:state.mainRef,mainTip:state.mainTip,filter:state.filter,density:state.prefs.density,historySources:state.historySources,query:state.query,searching:state.searching,tab:state.tab,comparison:state.comparison?{base:state.comparison.base,target:state.comparison.target}:null,comparisonLoading:state.comparisonLoading,comparisonDraft:state.comparisonDraft,comparisonError:state.comparisonError,snapshot:state.snapshot,detailsLoaded:state.details.size}),graph:()=>state.graph};
(async()=>{try{const params=new URLSearchParams(location.search),requested=params.get('sha');const b=await api(query('/api/bootstrap',{include_projects:'0'}));token=b.token;state.runtimes=b.runtimes;state.jobs=b.jobs||[];state.jobWarnings=b.job_warnings||[];for(const j of state.jobs)if(['queued','running','cancelling'].includes(j.status))pollWorkspaceJob(j.id);const context=await api(query('/api/workspace/context',{project:params.get('project')||''}));const id=context.project_id;if(id){await loadProject(id);if(requested&&commit(requested))await choose(requested);}else{state.commits=[];renderFirstRun();}}catch(e){$('#detail').innerHTML=`<div class="empty-content"><h3>无法连接本地服务</h3><p>${esc(e.message)}</p></div>`;}})();

document.addEventListener('change',async e=>{if(e.target.id==='recipe-candidate'&&e.target.value!=='')$('#recipe-json').value=JSON.stringify(state.recipeCandidates[Number(e.target.value)].recipe,null,2);});
