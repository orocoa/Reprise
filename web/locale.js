/* UI copy only. Git paths, commit messages, user names and command JSON stay literal. */
'use strict';
const uiCopy = {
  '正在连接本地工作台…':'Connecting to the local workspace…','Reprise · Git 版本工作台':'Reprise · Git workspace',
  '版本浏览':'Browse versions','版本管理':'Manage versions','选择项目':'Choose a project','导入项目':'Import project',
  '导入 Git 项目':'Import Git project','返回版本列表':'Back to versions','搜索历史版本':'Search versions','当前 Git ↗':'Current Git ↗',
  '所有分支与标签':'All branches and tags','刷新 Git 历史':'Refresh Git history','加载更早的提交':'Load earlier commits',
  '先导入一个本地 Git 项目。':'Import a local Git project to begin.','仓库中还没有提交。':'This repository has no commits yet.',
  '创建首次提交后，点击刷新即可读取。':'Create the first commit, then refresh.','没有找到这个版本。':'No matching version.',
  '正在读取…':'Loading…','读取 Git…':'Reading Git…','读取精确版本…':'Reading the exact revision…','首次提交':'First commit',
  '未提交改动不属于历史版本。':'Uncommitted changes are not part of historical revisions.',
  '查看 HEAD 版本':'View HEAD revision','尚无提交':'No commits','源码只读':'Source is read-only','工作仓库':'Working repository','裸仓库':'Bare repository','浅克隆':'Shallow clone',
  '当前版本运行与采集配置':'Run and capture settings for this revision','审阅 AI 提出的配置':'Review AI proposal',
  '运行这个版本':'Run this revision','配置运行方式':'Configure running','自动采集预览':'Capture preview','配置自动采集':'Configure capture','项目配置':'Project settings',
  '项目能力':'Project capabilities','历史可读':'History available','变化可比':'Diff available','支持手工资料':'Manual evidence supported',
  '可自动运行与截图':'Ready to run and capture','需要配置或手工资料':'Configuration or manual evidence needed',
  '等待确认运行配置':'Review runtime settings first','运行配置已保存':'Runtime settings saved',
  '使用当前提交的独立副本启动静态服务，按配置采集截图。整个流程无需 AI。':'Serve an independent copy of this commit and capture it using the saved settings. AI is optional.',
  'Git 历史已就绪。可以配置项目运行方式，也可以为精确版本导入已有截图或录像。':'Git history is available. Configure a runner or import screenshots or video for the exact revision.',
  '检测到需要执行命令的项目。先检查并保存运行配置，再运行或采集；导入项目时不会执行命令。':'This project needs commands. Review and save settings before running or capturing. Importing does not execute commands.',
  '将在当前提交的独立副本中执行已保存的命令。截图等待页面、字体、图片及指定的就绪条件。':'Run saved commands in an independent copy of this commit. Capture waits for the page, fonts, images and configured readiness conditions.',
  '当前版本配置':'Revision settings','旧项目配置':'Legacy project settings','仓库内配置':'Repository settings','自动识别':'Detected','尚未配置':'Not configured','AI 建议':'AI suggestion',
  '这个版本改了什么':'What changed in this revision','比较基准':'Comparison baseline','选择两个版本':'Choose two revisions','交换':'Swap',
  '选择两个版本比较':'Compare two revisions','可以选择历史提交，或输入完整 / 简短 SHA、分支名、标签名。比较方向是基准 → 目标。':'Choose commits or enter a full/short SHA, branch or tag. Direction: baseline → target.',
  '基准版本 A':'Baseline A','目标版本 B':'Target B','比较版本':'Compare revisions','空树（首次提交）':'Empty tree (first commit)',
  '版本预览与证据':'Preview and evidence','图片、录像绑定提交与场景。两边使用各自版本的运行配置，以及相同的截图场景。':'Images and videos bind to commits and scenarios. Each side uses its own runtime settings and the same capture scenario.',
  '这个版本还没有预览资料':'No preview evidence for this revision','点击「自动采集预览」，从精确提交启动项目并截图。基础采集无需 AI。':'Choose Capture preview to run and capture this exact commit. Basic capture needs no AI.',
  '先配置适合此项目的运行与采集方式；原生游戏、命令行工具也可以导入手工截图、录像或文件。':'Configure a suitable runner and capture setup. Native games and command-line tools can also use imported screenshots, videos or files.',
  '导入已有资料':'Import evidence','为当前版本导入资料':'Import evidence for this revision','本地文件完整路径':'Full local file path','资料类型':'Evidence type','图片 / 截图':'Image / screenshot','视频 / 录屏':'Video / recording','其他文件':'Other file','标题':'Title','场景标识':'Scenario ID','可选':'Optional',
  '用相同标识组织同一场景的资料。手工导入不会自动证明内容来自该提交。':'Use the same ID for the same scenario. Manual imports do not prove the media came from this commit.',
  '复制并绑定这个版本':'Copy and bind to this revision','资料已复制到证据库，原文件保持不变。':'Evidence copied. The original file is unchanged.',
  '预览服务':'Preview services','运行中':'Running','停止未确认':'Stop not confirmed','重试停止':'Retry stop','停止':'Stop','打开预览':'Open preview','尚未确认此预览服务已停止，请重试停止。':'Preview shutdown is not confirmed. Retry stopping.',
  '已停止预览服务，运行副本与日志保留。':'Preview stopped. Its copy and logs are retained.',
  '操作进度':'Operation progress','启动版本':'Start revision','采集版本预览':'Capture revision','AI 分析配置':'AI analysis','等待中':'Queued','执行中':'Running','正在取消':'Cancelling','已取消':'Cancelled','已完成':'Complete','失败':'Failed','取消任务':'Cancel task','查看提案':'Review proposal','重试':'Retry','收起操作结果':'Dismiss result',
  '正在停止此任务的进程，已有日志与资料保留。':'Stopping task processes. Existing logs and artifacts are retained.','结果已保留，可继续查看。':'Results are retained for review.','在独立目录中执行，日志和产物会保留。':'Runs in an independent directory. Logs and outputs are retained.',
  '导入第一个 Git 项目':'Import your first Git project','仓库完整路径':'Full repository path','显示名称':'Display name','默认使用仓库目录名':'Use repository directory name','读取并导入':'Read and import',
  '输入本机的仓库路径。Reprise 直接读取 Git 对象、引用与提交关系，支持普通仓库、worktree 和裸仓库。':'Enter a local repository path. Reprise reads Git objects, refs and parent relationships, supporting regular repositories, worktrees and bare repositories.',
  '项目代码保留在原处。导入不会安装依赖、构建或执行项目代码。':'Project code stays in place. Import does not install dependencies, build or execute project code.',
  'Git 历史总是先读取；运行和自动采集能力会根据这个项目的文件与配置单独判断。':'Read Git history first. Runtime and capture capabilities depend on this project’s files and settings.',
  '项目已导入，未执行项目代码。':'Project imported without executing its code.','已从 Git 重新读取历史。':'History refreshed from Git.',
  '使用配置模板':'Configuration template','切换会替换下方草稿':'Changing replaces the draft below','保留当前配置':'Keep current settings','静态网页 / 已构建的 Web 游戏':'Static site / built web game','需启动命令的网页 / Web 游戏':'Web site / game requiring start commands','原生应用 / 游戏 / CLI（手工资料）':'Native app / game / CLI (manual evidence)',
  '配置 JSON':'Configuration JSON','保存并确认配置':'Save and approve settings','保存目标：':'Save to:','载入旧项目配置作为草稿':'Load legacy settings as draft',
  '配置只保存到当前提交，不会覆盖其他版本。比较时两边使用相同截图场景。AI 可帮助提出配置，基础运行和截图无需 AI。':'Settings apply only to this commit. Comparison uses the same capture scenarios. AI may suggest settings; basic running and capture work independently.',
  '相对于提交根目录。命令使用参数数组，端口填写':'is relative to the commit root. Commands use argument arrays; use the port placeholder',
  '定义路由、视口、就绪条件与操作步骤。':'defines routes, viewports, readiness conditions and interactions.',
  '我已核对这份配置，授权后续点击「运行」或「采集」时执行其中的命令。':'I reviewed these settings and authorize their commands when I later choose Run or Capture.',
  '保存配置本身不会运行项目。执行使用独立副本，保留日志和产物。':'Saving does not run the project. Execution uses an independent copy and retains logs and outputs.',
  'AI 提案尚未生效。请核对命令、目录、页面和等待条件；只有明确保存后，后续运行或采集才会使用它。':'This AI proposal is inactive. Review commands, directories, pages and readiness conditions; it is used only after explicitly saving.',
  '可选 AI 助手':'Optional AI assistant','AI 助手':'AI assistant','AI 可选':'AI optional','AI 已启用':'AI enabled','已启用':'Enabled','AI 未启用 · 基础流程独立工作':'AI disabled · core workflows remain available',
  'AI 只在你点击「AI 建议」时分析当前项目并提出结构化配置。Git 读取、版本运行、截图与资料管理独立工作。':'AI analyzes the project only when you request a suggestion. Git reading, running, capture and evidence management work independently.',
  '启用 AI 配置建议':'Enable AI suggestions','模型返回的提案需要你检查并保存，不会自动运行或覆盖配置。':'Review and save model proposals. They never run automatically or overwrite settings.',
  '服务类型':'Provider type','Chat Completions 兼容服务':'Chat Completions compatible provider','服务地址':'Endpoint','模型名称':'Model name','填写服务支持的模型名称':'Enter a model supported by your provider',
  '已设置；留空保持原值':'Saved; leave blank to keep it','填写密钥（不会返回给浏览器）':'Enter key (never returned to the browser)','清除已保存密钥':'Clear saved key','密钥已清除。':'Saved key cleared.','保存 AI 设置':'Save AI settings',
  '密钥仅保存在本机私有配置中。模型名称由你设置，不会自动切换。':'The key is stored privately on this device. Your chosen model is preserved.',
  '仅点击「AI 建议」时才发送当前提交的清单文件、最多 300 条文件路径、变化文件名、提交标题与父提交、识别信息；启动工作台不会请求模型。请仅连接你愿意向其发送这些信息的服务。':'Only requesting an AI suggestion sends committed manifests, up to 300 paths, changed filenames, the commit subject and parents, and detection results. Opening the workspace does not call a model. Choose a provider you trust with this information.',
  'AI 设置已保存，尚未发送模型请求。':'AI settings saved. No model request sent.',
  '适应窗口':'Fit window','原文件 ↗':'Original file ↗','关闭预览':'Close preview','原始资料':'Original media','手工资料':'Manual evidence','重新加载':'Reload','关闭':'Close','取消':'Cancel',
  '此资料没有成功加载。检查本地服务是否运行，然后重试。':'Media failed to load. Check the local server and retry.',
  '每个项目，':'Every project','都有值得看见的过程。':'has a history worth seeing.',
  '连接本地 Git 仓库，读取真实版本记录。':'Connect a local Git repository to read its real history.','为网页、游戏和其他项目配置合适的运行与预览方式。':'Configure suitable runners and previews for web sites, games and other projects.',
  '先读懂 Git 历史':'Read Git history','分支、提交、真实父版本与文件变化。导入时保持源码不变。':'Branches, commits, real parents and file changes. Import preserves source files.',
  '按项目能力运行':'Run by project capability','静态网页自动识别。框架、游戏及原生项目使用独立的配置。':'Static sites are detected automatically. Frameworks, games and native projects use their own settings.',
  '让预览有据可查':'Keep verifiable previews','截图绑定精确提交与采集场景；也支持导入已有图片和录像。':'Screenshots bind to exact commits and capture scenarios. Existing images and videos can also be imported.',
  '停止未确认；请查看运行记录并重试。':'Stop not confirmed. Review the runtime record and retry.',
  '请在 Reprise 本机页面发起操作。':'Use the local Reprise page for this operation.','找不到此页面或接口。':'Page or API endpoint not found.','请填写本地 Git 仓库路径。':'Enter a local Git repository path.','项目还没有提交。':'The project has no commits yet.',
  '空仓库':'Empty repository','还没有提交；首次提交后刷新即可读取。':'No commits yet. Refresh after the first commit.',
  '这个项目需要运行配方；也可以先添加人工截图或录屏。':'This project needs runtime settings. You can also import screenshots or video.',
  '这个配方将执行项目命令，请先打开配方编辑器、核对并保存。':'This recipe executes project commands. Review and save it first.',
  'AI 尚未启用或配置；可以直接手工编辑运行配方。':'AI is disabled or unconfigured. You can edit runtime settings manually.',
  '已有 AI 请求正在执行。':'An AI request is already running.','AI 返回内容不完整或格式无效。':'AI returned incomplete or invalid content.','AI 建议未通过结构、配方或 Git 文件依据检查，未应用。':'AI output failed structure, recipe or Git evidence validation and was not applied.',
  'AI 服务无法连接或超时；Git 与采集功能仍可使用。':'AI could not connect or timed out. Git and capture remain available.',
  '先选择一个已提交的版本。':'Select a committed revision first.','这个版本已有相同操作正在进行。':'The same operation is already running for this revision.',
  '版本已启动，可在运行中的预览里打开。':'Revision started. Open it from running previews.','采集已结束，结果与诊断已保留。':'Capture finished. Results and diagnostics are retained.',
  '资料尺寸尚未载入，请稍后再试。':'Media dimensions are not loaded yet. Retry shortly.',
  '保存双语版本说明':'Save bilingual revision notes','版本说明已保存。':'Revision notes saved.','审阅双语版本说明':'Review bilingual revision notes',
};
Object.assign(uiCopy, {
  '已选版本':'Selected revision','工作目录干净。':'Working tree is clean.','工作目录状态不可用。':'Working tree status is unavailable.','当前 Git':'Current Git','没有运行中的预览服务。':'No running preview services.',
  '运行副本、日志和媒体保留在本机数据目录。':'Runtime copies, logs and media are retained in the local data directory.',
  '清除密钥时请保持密钥输入为空。':'Leave the key field empty when clearing the saved key.',
  '提案不属于当前项目和版本。':'The proposal belongs to a different project or revision.',
  '此提案是旧版单语内容，请重新请求双语提案。':'This legacy proposal has only one language. Request a new bilingual proposal.',
  'AI 提案已完成；切换回对应项目后点击「查看提案」。':'AI proposal complete. Return to its project and choose Review proposal.',
  '等待执行':'Queued','正在执行':'Running','项目任务':'Project task','项目服务':'Project service','时间未知':'Unknown time',
  '与所选基准相比，文件内容没有变化。':'No file changes from the selected baseline.',
  '文件变化暂不可用。':'File diff is temporarily unavailable.',
  '当前仓库缺少完整的比较对象，暂时无法计算文件变化。':'Comparison objects are missing from this repository; file diffs are unavailable.',
  '文件列表已截断，详情以 Git 原始记录为准。':'File list truncated. Consult the original Git record for details.',
  '交换基准和目标版本':'Swap baseline and target revisions','AI 只提出建议，运行配置须由你保存':'AI proposes settings; you must review and save them.',
  '提交 SHA、分支或标签':'Commit SHA, branch or tag','将本地截图、录像或其他文件复制到证据库，绑定提交':'Copy local screenshots, video or files to the evidence library and bind them to commit',
  '。原文件会保留，资料明确标记为手工导入。':'. Originals are retained; evidence is marked as a manual import.',
  '例如：关卡 1 · 完成画面':'Example: Level 1 · completion screen',
  '此记录来自旧版资料库，保留原有来源，不视为新采集结果。':'Imported from a legacy evidence library; its original provenance is retained.',
  '此记录没有可显示的图片或录像。':'This record has no displayable image or video.',
  '请查看采集错误，修正配置后重试。':'Review capture errors, correct the settings and retry.',
  '两版在此采集场景中画面相同':'Both revisions look identical in this capture scenario',
  '手工导入 · 未自动验证':'Manual import · not automatically verified','历史资料导入':'Legacy evidence import',
  '采集已取消':'Capture cancelled','采集失败':'Capture failed','部分采集完成':'Partial capture',
  '没有可访问的资料地址':'No accessible media URL','该版本没有可用的场景资料':'No evidence for this scenario in this revision',
  '文件资料':'File evidence','打开文件':'Open file','放大':'Enlarge','放大查看':'Enlarge preview','原始录像':'Original video','版本资料':'Revision evidence',
  '（未选择基准）':'(no baseline selected)','较早的采集记录':'Earlier capture records','其他比较基准的历史记录':'Records with other baselines',
  '基准版本':'Baseline revision','目标版本':'Target revision','预览':'Preview','采集诊断：':'Capture diagnostics:',
  '个真实父提交':'real parent commits','版本总数':'Revision count',
  '已选版本':'Selected revision','未知作者':'Unknown author','无提交说明':'No commit message',
  '静态网站':'Static website','空 Git 仓库':'Empty Git repository','无法识别的项目类型':'Unrecognized project type',
  '文档 / 未识别项目':'Documentation / unrecognized project','桌面应用 (Electron / Tauri)':'Desktop app (Electron / Tauri)',
  '浏览器游戏框架':'Browser game framework','3D / Canvas 网页项目':'3D / Canvas web project',
  'Node.js 命令行应用':'Node.js command-line app','含运行脚本的 Node.js 项目':'Node.js project with runnable scripts',
  'JavaScript / TypeScript 包':'JavaScript / TypeScript package','Godot 游戏':'Godot game','Unreal Engine 游戏':'Unreal Engine game',
  'Unity 游戏':'Unity game','Rust 游戏':'Rust game','Rust 项目':'Rust project','Go 项目':'Go project',
  'Python 网页应用':'Python web app','Python 项目':'Python project','JVM 项目':'JVM project',
  '原生应用 / 库':'Native application / library','PHP 项目':'PHP project','Ruby 项目':'Ruby project',
  '原生构建项目':'Native build project','网页源码（需要构建配置）':'Web source (build configuration needed)',
  'Git 历史与文件变化可查看。配置运行方式或导入手工资料以预览。':'Git history and file diffs are available. Configure a runner or attach manual evidence for visual previews.',
  '存在多个可运行目录，请选择并保存目标应用配置。':'Multiple runnable roots found; select and save a recipe for the intended app.',
  '存在 README':'README present','裸仓库没有工作目录':'Bare repositories do not have a worktree',
  '版本说明须包含中文和英文':'Version notes require both Chinese and English',
  '版本说明须包含标题、摘要和变化':'Version notes require title, summary and changes',
  '版本说明须包含 1–8 条变化说明':'Version notes require 1–8 change explanations',
});
const uiTerms = {'同时采集比较基准':'Also capture baseline','次采集记录':'capture records','所选基准':'Selected baseline','父提交':'Parent commit','基准':'Baseline','目标':'Target','个独立副本':'independent copies','配置':'Settings','自动采集':'Automatic capture','手工导入':'Manual import','缺失':'Missing','诊断':'Diagnostic','通过':'Passed','未提交':'uncommitted','本地服务返回了无法读取的内容':'Local server returned unreadable content','请求失败':'Request failed','项':'changes','保存目标':'Save target','空树':'Empty tree','合并提交':'Merge commit','合并':'Merge','已提交':'Committed','分离 HEAD':'Detached HEAD','JSON 格式不正确':'Invalid JSON','配置已保存到版本':'Settings saved for revision','请选择比较版本':'Choose comparison revisions','未生成':'Not generated','已结束，资料已保留。':'ended; artifacts retained.','预览服务已停止，但状态刷新失败':'Preview stopped, but refreshing state failed','状态刷新失败':'State refresh failed','正在重新连接本地服务；原任务状态尚未确认。':'Reconnecting; the task state is not confirmed.'};
let uiLanguage;
try {uiLanguage=new URLSearchParams(location.search).get('lang') || localStorage.getItem('reprise.language') || 'zh';}catch(_){uiLanguage='zh';}
if(!['zh','en'].includes(uiLanguage))uiLanguage='zh';
const i18nMissing = new Set();
let uiDictionary;
const uiTextCache=new Map();
function compileUICopy(){
  const reverse=new Map();
  for(const [zh,en] of Object.entries(uiCopy))if(!reverse.has(en))reverse.set(en,zh);
  uiDictionary={reverse,english:new Set(Object.values(uiCopy)),entries:Object.entries({...uiCopy,...uiTerms}).sort((a,b)=>b[0].length-a[0].length)};
  uiTextCache.clear();
}
function uiText(value) {
  const text=String(value),trim=text.trim();
  if(!uiDictionary)compileUICopy();
  const key=uiLanguage+'|'+text;
  if(uiTextCache.has(key))return uiTextCache.get(key);
  let result=text;
  if(uiLanguage!=='en'){
    const original=uiDictionary.reverse.get(trim);
    result=original?text.replace(trim,original):text.replace(/^Web app \((.*)\)$/, '网页应用 ($1)').replace('references missing committed assets:', '引用的资源未包含在提交中：');
  }else if(uiCopy[trim])result=text.replace(trim,uiCopy[trim]);
  else if(!uiDictionary.english.has(trim)){
    for(const [zh,en] of uiDictionary.entries)result=result.replaceAll(zh,en);
    if(/[\u3400-\u9fff]/.test(result)&&i18nMissing.size<256)i18nMissing.add(text);
  }
  if(text.length<=2000){if(uiTextCache.size>=512)uiTextCache.delete(uiTextCache.keys().next().value);uiTextCache.set(key,result);}
  return result;
}
const originalTexts=new WeakMap(),originalAttrs=new WeakMap();
function localizeDOM(root=document.body) {
  document.documentElement.lang=uiLanguage==='en'?'en':'zh-CN';const description=document.querySelector('meta[name=description]');if(description)description.content=uiLanguage==='en'?'Reprise — from Git history to verifiable revision previews.':'Reprise — 从 Git 记录到可验证的版本预览。';const name=document.querySelector('#project-name')?.textContent;const title=name?name+' · '+(uiLanguage==='en'?'Versions':'版本'):(uiLanguage==='en'?'Reprise · Git workspace':'Reprise · Git 版本工作台');if(document.title!==title)document.title=title;
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes){
    if(node.parentElement?.closest('[data-user-content],code,pre,textarea,script,style,.commit-subject,.project-name,.ai-proposal,#quick-project option,#project-picker option,#main-picker option'))continue;
    const old=originalTexts.get(node);
    const original=old&&node.nodeValue===old.translated?old.original:node.nodeValue;
    const translated=uiText(original);
    if(node.nodeValue!==translated)node.nodeValue=translated;
    originalTexts.set(node,{original,translated});
  }
  const attributes='[placeholder],[title],[aria-label]';
  for(const element of [...(root.matches?.(attributes)?[root]:[]),...root.querySelectorAll(attributes)]){
    if(element.closest('[data-user-content]')||element.hasAttribute('data-user-label'))continue;
    const originals=originalAttrs.get(element)||{};
    for(const key of ['placeholder','title','aria-label'])if(element.hasAttribute(key)){
      const value=element.getAttribute(key),old=originals[key],original=old&&value===old.translated?old.original:value;
      const translated=uiText(original);if(value!==translated)element.setAttribute(key,translated);originals[key]={original,translated};
    }
    originalAttrs.set(element,originals);
  }
  document.querySelectorAll('[data-action=language]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.language===uiLanguage));
}
let localizeQueued=false;
const localizeRoots=new Set();
new MutationObserver(records=>{
  for(const record of records){
    if(record.type==='characterData'&&originalTexts.get(record.target)?.translated===record.target.nodeValue)continue;
    const root=record.type==='characterData'?record.target.parentElement:record.target;
    if(root?.isConnected)localizeRoots.add(root);
  }
  if(localizeRoots.size&&!localizeQueued){localizeQueued=true;queueMicrotask(()=>{
    const roots=[...localizeRoots];localizeRoots.clear();
    for(const root of roots)if(root.isConnected&&!roots.some(other=>other!==root&&other.contains(root)))localizeDOM(root);
    localizeQueued=false;
  });}
}).observe(document.body,{childList:true,subtree:true,characterData:true});
