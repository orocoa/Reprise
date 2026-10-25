'use strict';
// One evidence model serves previews, comparisons and the media viewer.
function evidenceItems(records,sha,{side}={}){
 return (records||[]).flatMap(record=>(record.items||[]).map((item,index)=>{
  const itemSide=['before','base'].includes(item.side)?'base':'target';
  const expected=itemSide==='base'?record.base:record.sha,revision=item.sha||expected;
  if(!revision||revision!==sha||(expected&&revision!==expected)||(side&&itemSide!==side))return null;
  const recipe=itemSide==='base'?record.base_recipe||record.recipe:record.recipe;
  return {...item,index,sha:revision,side:itemSide,record:record.id,
   kind:item.kind||(item.media_type?.startsWith('image/')?'image':item.media_type?.startsWith('video/')?'video':'file'),
   capture:record.source==='automatic'?{...(recipe?.captures||[]).find(c=>c.id===item.capture_id),network:recipe?.network,runner:record.runner_version}:item.capture,
   sourceLabel:record.source==='legacy'?'历史保留资料 · 沿用原采集元数据':record.source==='manual'?'手工导入 · 归属由提供者指定':'自动采集 · 精确提交'};
 })).filter(Boolean);
}
function visualEvidence(item){return Boolean(item&&!item.missing&&!item.error&&item.url&&['image','video'].includes(item.kind));}
function uniqueEvidence(items){return [...new Map(items.map(item=>[`${item.record}:${item.index}`,item])).values()];}
function baselineMediaItems(target,baseline,sha){
 if(!sha)return [];
 return uniqueEvidence([...evidenceItems((target?.evidence||[]).filter(record=>record.base===sha),sha,{side:'base'}),...mediaItems(baseline)]);
}
function mediaGallery(target,baseline,sha){return uniqueEvidence([...mediaItems(target),...baselineMediaItems(target,baseline,sha)]).filter(visualEvidence);}
function captureStatus(record){return {queued:'排队中',running:'进行中',complete:'已完成',partial:'部分完成',failed:'失败',cancelled:'已取消',cancelling:'取消中'}[record?.status]||record?.status||'';}
function captureSavedCount(record){return (record?.items||[]).filter(item=>!item.missing&&!item.error&&item.url).length;}
function captureResultText(record){
 const count=captureSavedCount(record),status=uiText(captureStatus(record));
 return count?`${status} · ${uiLanguage==='en'?`${count} saved item${count===1?'':'s'}`:`已保存 ${count} 项`}`:status;
}
function captureDiagnostics(record,{error='',key=record?.id||'unknown',force=false}={}){
 if(!record&&!error&&!force)return '';
 const messages=[...(record?.errors||[]).map(item=>({type:'错误',item})),...(record?.warnings||[]).map(item=>({type:'提醒',item}))];
 if(error&&!messages.some(({item})=>(typeof item==='string'?item:item.error||item.message)===error))messages.unshift({type:'任务说明',item:error});
 const paths=[['采集记录',record?.record_path],['本地资料目录',record?.local_directory],...(record?.browser_logs||[]).map(path=>['浏览器日志',path]),...(record?.runtimes||[]).filter(runtime=>runtime.log_path).map(runtime=>['运行日志',runtime.log_path])];
 if(!force&&!messages.length&&!['failed','partial','cancelled'].includes(record?.status))return '';
 return `<details class="capture-diagnostics" data-keep-open="capture-${esc(key)}"><summary><span>${record?`${esc(captureResultText(record))} · `:''}${uiText('查看采集诊断')}</span></summary><div class="capture-diagnostics-content">${messages.length?`<ul>${messages.map(({type,item})=>{const label=typeof item==='object'?{before:'基准版本 A',base:'基准版本 A',after:'目标版本 B',target:'目标版本 B'}[item.side]:'';const text=typeof item==='string'?item:item.error||item.message||item.warning||JSON.stringify(item);return `<li><span>${uiText(type)}${label?' · '+uiText(label):''}</span><p data-user-content>${esc(text)}</p></li>`;}).join('')}</ul>`:`<p>${uiText('暂无更详细诊断。')}</p>`}${paths.length?`<dl>${paths.map(([label,path])=>`<dt>${uiText(label)}</dt><dd><code>${esc(path)}</code></dd>`).join('')}</dl><p>${uiText('日志保留在本机，可在上述位置查看。')}</p>`:''}</div></details>`;
}
function captureRecords(d){return (d?.evidence||[]).filter(record=>record.source==='automatic'&&record.sha===d.commit.sha).sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));}
function renderCaptureDiagnostics(d){return captureRecords(d).map(record=>captureDiagnostics(record)).join('');}
function previewEmptyText(d){
 const latest=captureRecords(d)[0];
 if(latest?.status==='cancelled')return ['采集已取消','此版本尚无保存的预览，可查看下方诊断或重新采集。'];
 if(['failed','partial'].includes(latest?.status))return ['采集未完成','此版本尚无可用预览，可查看下方诊断或重新采集。'];
 if(['running','queued'].includes(latest?.status))return ['正在采集预览','任务进度可在项目设置中查看。'];
 return ['没有预览','此版本尚未保存截图或录屏。'];
}
function captureJobNotice(job){
 const status=job.result?.status||job.status,count=captureSavedCount(job.result);
 if(uiLanguage==='en'&&!count)return status==='cancelled'?'Capture cancelled; no previews saved. View details in Previews or Settings.':'Capture incomplete; no previews saved. View diagnostics in Previews or Settings.';
 if(uiLanguage==='en')return status==='complete'?`Capture complete; ${count} saved item${count===1?'':'s'}.`:status==='partial'?`Capture partially complete; ${count} saved item${count===1?'':'s'}. View diagnostics in Previews or Settings.`:status==='cancelled'?`Capture cancelled; ${count} saved item${count===1?'':'s'} retained. View details in Previews or Settings.`:`Capture failed; ${count} saved item${count===1?'':'s'} retained. View diagnostics in Previews or Settings.`;
 if(!count)return status==='cancelled'?'采集已取消，尚未保存预览。可在版本预览或设置查看详情。':'采集未完成，尚未保存预览。可在版本预览或设置查看诊断。';
 return status==='complete'?`采集完成，已保存 ${count} 项。`:status==='partial'?`采集部分完成，已保存 ${count} 项。可在版本预览或设置查看诊断。`:status==='cancelled'?`采集已取消，已保存的 ${count} 项资料保留。可在版本预览或设置查看详情。`:`采集失败，已保存的 ${count} 项资料保留。可在版本预览或设置查看诊断。`;
}
