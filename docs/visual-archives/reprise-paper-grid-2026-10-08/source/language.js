'use strict';
// Interface strings and generated copy use separate dictionaries. Original Git
// data, custom names, code, paths and captured pixels retain their identity.
const contentEnglish = Object.create(null);
const uiEnglish = {
  '查看最近变更':'View latest changes','查看实际页面改动':'View the actual page update','收起并返回':'Collapse and return','返回版本列表':'Back to version list','此版本没有已保存的操作录屏。可切换到前后画面或文件依据。':'No saved recording for this version. Choose before / after or file changes.','此版本没有可比较的前后画面。可切换到操作录屏或文件依据。':'No comparable images for this version. Choose recordings or file changes.',
  '这组预览尚未完整采集，暂时无法直接比较。':'These previews are incomplete and cannot be compared directly yet.','展示同一作品位置、语言和视口的已保存截图。动画、滚动和加载变化不会体现在静态截图里。':'Saved screenshots of the same project position, language and viewport. Motion, scrolling and loading changes do not appear in static screenshots.',
  '和上一版一起看':'View alongside the previous version','上一版尚无此页面。':'This page is unavailable in the previous version.','上一版没有同位置的预览，暂时无法并排比较。':'No matching preview is available for the previous version.','展示同一页面、语言和视口的已保存截图。动画、滚动和加载变化不会体现在静态截图里。':'Saved screenshots of the same page, language and viewport. Motion, scrolling and loading changes do not appear in static screenshots.','展示同一页面的已保存预览，可分别播放查看。':'Saved previews of the same page; play them separately to compare.',
  '此版本':'This version','版本对比':'Version comparison',
  '发布包':'Release package','Git 提交':'Git commit','这个版本改了什么':'What changed','相对上一份发布存档':'Compared with the previous release','相对上一版 Git':'Compared with the previous Git version','系列起点':'Starting version','上一版':'Previous version','上一版：':'Previous version: ','对比上一版':'Compare previous version',
  '界面语言':'Interface language','主导航':'Main navigation','版本浏览':'Browse versions','版本管理':'Manage versions','选择版本':'Choose a version','版本内容':'Version content',
  '搜索历史版本…':'Search versions…','搜索历史版本':'Search versions','历史版本':'Version history','当前 Git ↗':'Current Git ↗','当前 Git':'Current Git','· 当前 Git':'· Current Git','个文件':'files','填写提交说明，并至少选择一个文件。':'Enter a commit message and select at least one file.','版本名称已保存。':'Version name saved.','已恢复原名。':'Original name restored.','请输入版本名称。':'Enter a version name.','版本名称最多 80 个字符。':'Version names can contain up to 80 characters.','版本名称不能包含换行或隐藏控制字符。':'Version names cannot contain line breaks or hidden control characters.','操作没有完成，请重试。':'The operation did not complete. Try again.','开始处理':'Starting…','当前项目已打开；工作区内容未改动':'Current project opened; working directory unchanged','已停止当前项目预览；工作区内容保留':'Current preview stopped; working directory retained','当前项目':'Current project','当前项目 Git':'Current project Git','当前变更':'Current changes',
  '正在读取…':'Loading…','正在读取版本…':'Loading versions…','刷新':'Refresh','Git 保存版本。已下载的环境可保留或删除。':'Git keeps your versions. Downloaded environments can be kept or removed.',
  '已下载版本环境':'Downloaded version environments','删除全部环境':'Remove all environments','可选 AI':'Optional AI','Git 内容':'Git contents','历史 Git 存档':'Git history archive','原项目':'Source project',
  '不可读取':'Unavailable','已提交':'Committed','已保留':'Always kept','已停止，已保留':'Stopped, retained','已停止':'Stopped','运行中':'Running','打开':'Open','进入 ↗':'Enter ↗','停止…':'Stop…','停止运行':'Stop running','删除环境…':'Remove environment…','导出备份':'Export backup','查看变更 ↗':'View changes ↗',
  '暂无已下载版本环境':'No downloaded version environments','当前项目不可读取。':'The current project is unavailable.','未提交的改动尚未存入历史版本。':'Uncommitted changes are not saved in version history yet.','工作区与最近一次提交一致。':'The working directory matches the latest commit.',
  '提交变更':'Commit changes','查看最近变更 ↗':'View latest changes ↗','打开此版本 ↗':'Open this version ↗','进入此版本 ↗':'Enter this version ↗','修改':'Modified','新增':'Added','删除':'Deleted','未跟踪':'Untracked','变化':'Changed',
  '重命名':'Rename','详细变化':'Change details','查看上一版 →':'View previous version →','对比上一版 ↗':'Compare previous version ↗','预览':'Preview','选择预览':'Choose preview','暂无预览':'No preview','没有找到这个版本。':'No matching versions.','Git 存档不可读取':'Git archive unavailable',
  '关闭弹窗':'Close dialog','取消':'Cancel','保存':'Save','完成':'Done','版本名称':'Version name','保存名称':'Save name','恢复原名':'Restore original name','最多 80 个字符。':'Up to 80 characters.','提交到 Git':'Commit to Git','提交说明':'Commit message','简述这次改动':'Describe these changes','核对提交范围':'Review files to commit','保存所选文件的当前内容，包含已暂存与未暂存的改动。':'Save the selected files, including staged and unstaged changes.',
  '当前工作区 · 包含未提交改动':'Current working directory · includes uncommitted changes','运行中 · 当前 Git':'Running · Current Git','准备版本':'Preparing version','打开当前项目':'Opening current project','停止当前项目':'Stopping current project',
  'AI 辅助':'AI assistance','未配置':'Not configured','已关闭':'Disabled','待测试':'Not tested','连接成功':'Connected','请求失败':'Request failed','配置不可读':'Settings unavailable','本地模式':'Local mode','关闭':'Disable','配置 ↗':'Configure ↗','AI 分析 ↗':'AI analysis ↗','启用 AI 辅助':'Enable AI assistance',
  '保存后可测试本机 Codex 连接。':'Save settings to test your local Codex connection.','https://你的服务地址/v1':'https://your-provider.example/v1','查看变化 ↗':'View changes ↗','连接方式':'Connection','兼容 API':'Compatible API','连接 Codex':'Connect Codex','服务地址':'Service URL','模型名称':'Model name','API 密钥':'API key','清除已保存的密钥':'Clear saved key','保存并测试连接':'Save and test connection','哪些内容会发送给 AI？':'What is sent to AI?',
  '支持 Chat Completions 兼容接口，本机服务可使用 HTTP。':'Supports Chat Completions compatible APIs; local services may use HTTP.','密钥仅存本机，不进入 Git。更换服务地址时请重新填写密钥。':'The key stays on this computer, outside Git. Enter it again when changing the service URL.',
  '已保存，留空保留现有密钥':'Saved; leave blank to keep the key','填写密钥；无需鉴权的本机服务可留空':'Enter a key; leave blank for local services without authentication','填写服务提供的模型名称':'Enter the model identifier from your provider','跟随 Codex 现有配置':'Use your existing Codex configuration',
  '复用本机 Codex 登录。模型留空时跟随现有配置。':'Uses your local Codex login. Leave the model blank to use your existing configuration.','本机 Codex 已登录':'Local Codex is signed in','本机 Codex 尚未登录':'Local Codex is not signed in','本机未检测到 Codex':'Codex was not found on this computer',
  '配置已保存，尚未通过真实请求验证。':'Settings saved; a real request has not been tested yet.','填写服务地址和模型后可测试连接。':'Enter a service URL and model to test the connection.','选择 Codex 后可保存并测试连接。':'Select Codex, then save and test the connection.',
  '正在测试…':'Testing…','正在发送真实模型请求…':'Sending a real model request…','操作未完成':'Operation incomplete','请检查配置后重试。':'Check your settings and try again.','AI 配置已保存。':'AI settings saved.','AI 已关闭，继续使用已有版本说明。':'AI disabled; existing version notes remain available.',
  '测试连接仅发送一条测试消息。点击版本的“AI 分析”时，发送该版本与上一版编号、已核对说明和最多 80 条 Git 文件路径；不发送源码、图片或视频。结果作为建议单独保存。浏览和打开版本不会自动请求 AI。':'Connection tests send only a test message. AI analysis sends version identifiers, verified notes and up to 80 Git paths, without source code, images or videos. Suggestions are saved separately. Browsing and opening versions do not request AI.',
  'Git 备份已保存':'Git backup saved','下载 Git 备份':'Download Git backup','下载版本配置':'Download version settings','备份包含全部提交与标签；配置文件保存版本说明和运行方式。':'The backup contains all commits and tags; the settings include version notes and launch instructions.',
  '暂无同位置对比':'No matching comparison','上一版没有这处变化对应的预览，不能直接比较。':'The previous version has no matching preview for this change.','查看上一版页面':'View previous version','对比上一版':'Compare previous version','视口或采集状态未完全对齐，这组预览不能直接证明变化。':'These previews were captured in different conditions and do not prove the change.',
  '结束体验':'Stop version','停止并保留环境':'Stop and keep environment','停止并删除环境…':'Stop and remove environment…','停止并保留':'Stop and keep','确认删除':'Confirm removal','删除全部环境？':'Remove all environments?','删除这份环境？':'Remove this environment?','Git、截图和说明继续保留。有未保存改动的环境不会删除。':'Git history, screenshots and notes are retained. Environments with unsaved changes cannot be removed.'
};
let uiLanguage = 'zh';
try { uiLanguage = localStorage.getItem('reprise.language') === 'en' ? 'en' : 'zh'; } catch (_) {}
const uiOriginal = new WeakMap();
const uiAttributes = new WeakMap();
const authoredContent = '[data-user-content],.detail-summary,.change-list,.preview-note,.ai-result-summary,.ai-result-list,.ai-suggestions code,script,style';
const verbatimContent = '[data-verbatim],#project-name,code,pre,script,style,[data-i18n-zh]';
Object.assign(uiEnglish, {
  '正在提交…':'Committing…','Git 提交未完成。':'The Git commit did not complete.','操作未完成。':'The operation did not complete.',
  '清理运行副本':'Removing runtime copy','删除运行环境':'Removing environments','导出 Git 备份':'Exporting Git backup',
  '没有需要删除的环境。':'No environments to remove.','这个版本已停止，请重新打开。':'This version has stopped. Open it again.',
  '请使用独立窗口查看。':'Open in a new window to view this.','交互版本':'Interactive version',
  '上一版未包含此页面或查看状态，文件依据中保留了新增记录。':'This page or view state is absent from the previous version; the file changes retain its addition.',
  '这处预览未能采集，保留文件依据供核对。':'This preview could not be captured; file changes remain available for review.',
  '此系列起点，没有上一版。':'This is the start of the series, with no previous version.',
  '页面内容一致，默认画面明确沿用上一版；本次变化见文件依据。':'Page content is unchanged. The default view retains the previous capture; see file changes for this update.',
  '展开相关文件差异':'Expand relevant file differences','展开相关文件差异（节选）':'Expand relevant file differences (excerpt)',
  '正在分析相对上一版的变化…':'Analyzing changes from the previous version…',
  '已有说明 · 本次未采用 AI 结果':'Existing notes · AI result not used','已保存的结果':'Saved result','本次模型请求':'Current model request',
  '预览建议 · 待核对':'Preview suggestions · awaiting review','图片':'Image','视频':'Video','文字 / 文件':'Text / files','需补充依据':'More evidence needed',
  '建议名称':'Suggested name','基于已有说明与文件清单；未运行或验证页面。原有说明与真实媒体继续保留。':'Based on existing notes and file lists; the page has not been run or verified. Original notes and real media are retained.',
  'AI 未启用，继续使用已有版本说明。':'AI is disabled; existing version notes remain available.','AI 分析':'AI analysis',
  'AI 结果格式或文件依据无效，继续使用已有说明。':'The AI result has invalid structure or file evidence; existing notes remain available.'
});
function registerLocalizedCatalog(data) {
  Object.assign(contentEnglish, data.copy_en || {});
  for (const item of data.versions || []) {
    const zh=item.localizations?.zh, en=item.localizations?.en;
    if (!zh || !en) continue;
    for (const field of ['title','summary']) if (typeof zh[field]==='string' && typeof en[field]==='string') contentEnglish[zh[field]]=en[field];
    if (zh.changes?.length===en.changes?.length) zh.changes.forEach((source,i)=>{contentEnglish[source]=en.changes[i];});
    for(const p of [...(item.previews||[]),...(item.comparison_pages||[])]) {
      const caption=contentEnglish[p.caption]||p.caption;
      if(!item.custom_title) {
        contentEnglish[item.title+'：'+p.caption]=en.title+': '+caption;
        contentEnglish[item.title+' '+p.caption]=en.title+' '+caption;
        contentEnglish[item.title+'交互版本']=en.title+' · Interactive version';
      }
    }
  }
}
function englishCopy(source) {
  if (Object.hasOwn(contentEnglish,source)) return contentEnglish[source];
  if (uiEnglish[source]) return uiEnglish[source];
  const select=source.match(/^选择 (.+) (\d{4}\/\d{1,2}\/\d{1,2} .+)$/);
  if(select) return 'Select '+englishCopy(select[1])+' '+select[2];
  const rules = [
    [/^选择 /, 'Select '],
    [/^放大 /, 'Enlarge '],
    [/截图$/, ' screenshot'],
    [/^AI 分析 · /, 'AI analysis · '],
    [/^运行中 · /, 'Running · '],
    [/^(\d+) 项未提交$/, '$1 uncommitted changes'],
    [/^(.+) · (\d+) 项未提交$/, '$1 · $2 uncommitted changes'],
    [/^(.+) · 已提交$/, '$1 · committed'],
    [/^(\d+) 份 · (.+)$/, '$1 environments · $2'],
    [/^(\d+) 个版本 · 提交、标签与还原配置$/, '$1 versions · commits, tags and restore settings'],
    [/^(\d+) 个文件$/, '$1 files'],
    [/^真实请求通过 · /, 'Real request passed · '],
    [/ · AI 当前已关闭$/, ' · AI is disabled'],
    [/^默认排除独立项目：/, 'Separate project excluded by default: '],
    [/^原名：/, 'Original name: '],
    [/^已提交 ([a-f0-9]+)$/, 'Committed $1'],
    [/^(\d+) 个文件已存入当前项目的 Git。$/, '$1 files committed to the current project.'],
    [/^默认配置$/, 'Default configuration'],
    [/^Codex 默认配置$/, 'Codex default configuration'],
    [/^配置模型 · /, 'Configured model · ']
  ];
  const translated=rules.reduce((value,[pattern,replacement])=>value.replace(pattern,replacement),source);
  if (translated!==source) {
    for (const prefix of ['Select ','Enlarge ','AI analysis · ','Running · ','Original name: ']) {
      if (translated.startsWith(prefix)) return prefix+englishCopy(translated.slice(prefix.length));
    }
    return translated;
  }
  if(source.startsWith('比较：')) return 'Compare: '+source.slice(3).split(' → ').map(englishCopy).join(' → ');
  if(source.startsWith('AI 辅助 · ')) return 'AI assistance · '+source.slice(8);
  const reviewSuffix=' 可关闭后重新核对提交范围。';
  if(source.endsWith(reviewSuffix)) return englishCopy(source.slice(0,-reviewSuffix.length))+' Close this dialog to review the files again.';
  if(source.endsWith('…') && uiEnglish[source.slice(0,-1)])return uiEnglish[source.slice(0,-1)]+'…';
  if(source.includes(' · '))return source.split(' · ').map(part=>Object.hasOwn(contentEnglish,part)?contentEnglish[part]:uiEnglish[part]||part).join(' · ');
  return source.replace(/^(\d+) 份环境 · /,'$1 environments · ').replace(/ · 视口 /g,' · Viewport ').replace(/× 采集/g,'× capture').replace(/ 秒$/,' seconds');
}
function translated(source) {
  return uiLanguage === 'en' ? source.replace(/\S[\s\S]*\S|\S/, match => englishCopy(match)) : source;
}
function translateUI() {
  document.documentElement.lang = uiLanguage === 'en' ? 'en' : 'zh-CN';
  document.querySelectorAll('[data-language]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.language === uiLanguage)));
  document.querySelectorAll('[data-i18n-zh]').forEach(element=>{
    const value=element.getAttribute(uiLanguage==='en'?'data-i18n-en':'data-i18n-zh') || element.dataset.i18nZh;
    if(element.textContent!==value)element.textContent=value;
  });
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement?.closest(verbatimContent)) continue;
    const previous = uiOriginal.get(node);
    const source = previous && node.nodeValue === previous.output ? previous.source : node.nodeValue;
    const authored=node.parentElement?.closest(authoredContent);
    const output = authored && !Object.hasOwn(contentEnglish,source.trim()) ? source : translated(source);
    uiOriginal.set(node, {source, output});
    if (node.nodeValue !== output) node.nodeValue = output;
  }
  document.querySelectorAll('[aria-label],[placeholder],[alt],[title]').forEach(element => {
    if (element.closest('[data-verbatim],#project-name,code,pre,script,style')) return;
    let saved = uiAttributes.get(element) || {};
    for (const name of ['aria-label','placeholder','alt','title']) {
      if (!element.hasAttribute(name)) continue;
      const value = element.getAttribute(name), old = saved[name];
      const source = old && value === old.output ? old.source : value;
      const output = translated(source);
      saved[name] = {source, output};
      if (value !== output) element.setAttribute(name, output);
    }
    uiAttributes.set(element, saved);
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-language]');
  if (!button) return;
  uiLanguage = button.dataset.language;
  try { localStorage.setItem('reprise.language', uiLanguage); } catch (_) {}
  translateUI();
  document.dispatchEvent(new CustomEvent('reprise-language-change',{detail:{language:uiLanguage}}));
});
new MutationObserver(translateUI).observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['placeholder','aria-label','alt','title']});
translateUI();
