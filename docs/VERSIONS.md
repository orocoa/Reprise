# Reprise Git 版本索引 / Git version index

2026-10-08 保存。通用程序与当前预览界面分别维护在已有仓库中。所有标签绑定确切提交；原文件、QA 和媒体保持原位。

- 通用程序：`/Users/kai/Documents/GitOrocoa/Reprise`
- 当前预览界面：`/Users/kai/Documents/Codex/2026-10-07/superset-devpod-git-git-ai/outputs/git-version-demo`
- 界面快照分支：`codex/reprise-ui-iterations`
- 当前预览双语版本：`reprise-ui/v08`，提交 `54ec0db`。

## 已有提交与当前保存 / Saved commits

| 仓库 | 标签 | SHA | 版本 |
|---|---|---|---|
| Core | `reprise-core/v01` | `a751bb8` | 通用 Reprise 基线 / Standalone Reprise baseline |
| Core | `reprise-core/v02` | `e35e550` | 取消、恢复与跨版本比较 / Cancellation, recovery and revision-specific comparison |
| UI | `reprise-ui/v01` | `171f360` | 初版：保存版本名称 / Initial demo with persistent names |
| UI | `reprise-ui/v02` | `eab4802` | RCA 网格与浏览简化 / RCA layout and simplified browsing |
| UI | `reprise-ui/v03` | `5750efb` | 极简预览布局 / Minimal preview layout |
| UI | `reprise-ui/v04` | `03b3a63` | 当前 Git 提交与视频预览 / Current Git commits and video previews |
| UI | `reprise-ui/v05` | `8c90cde` | 全天界面细化基线 / Saved layout baseline |
| UI | `reprise-ui/v06` | `5ea5c72` | 关联版本展开与证据导航 / Expandable related versions and evidence navigation |
| UI | `reprise-ui/v07` | `838d27c` | 响应式界面布局 / Responsive layout |
| UI | `reprise-ui/v08` | `54ec0db` | 完整中英内容与双语生成 / Bilingual content and first-generation output |

## 恢复的界面迭代 / Recovered UI iterations

这些是由保留的修改前源码和差异恢复的修改后代码快照，恢复提交的时间是本次保存时间；保留的原提交没有改写。每份快照的 `docs/ITERATION-SNAPSHOT.json` 列出来源、基准提交、逐文件 SHA-256 和恢复范围。对代码差异逐项核对无缺口，JS 语法通过。最早一份预览折叠快照的 README 存在额外未记入该轮差异的文字变化，已记录并使用该轮保存的 README 前稿与差异恢复。没有把新截图当作历史快照证据。

| 标签 | SHA | 迭代 |
|---|---|---|
| `reprise-ui/snapshot/preview-accordion-20261008-140955` | `5ebe202` | 预览折叠菜单 |
| `reprise-ui/snapshot/selection-hover-20261008-142229` | `08f7be2` | 选择状态与悬停 |
| `reprise-ui/snapshot/edge-to-edge-nav-20261008-144230` | `155b8be` | 接边网格与页面切换 |
| `reprise-ui/snapshot/page-frame-sidebar-20261008-145341` | `ff49135` | 页面框架与侧栏 |
| `reprise-ui/snapshot/header-subtle-navigation-20261008-150921` | `5efa63d` | 顶部导航与细线 |
| `reprise-ui/snapshot/navigation-grid-20261008-154501` | `fbc822a` | 初始目录居中与网格动画 |
| `reprise-ui/snapshot/rightward-detail-navigation-20261008-162446` | `beb2c3a` | 详情与管理的右向过渡 |
| `reprise-ui/snapshot/continuous-grid-20261008` | `5209d89` | 连续网格边线 |
| `reprise-ui/snapshot/no-line-merge-20261008` | `6f1b405` | 浏览动画边线处理 |
| `reprise-ui/snapshot/single-comparison-entry-20261008-172058` | `bd27c67` | 保留单一比较入口 |
| `reprise-ui/snapshot/no-line-merge-all-20261008` | `d22cc13` | 全部过渡边线处理 |

## 查看 / Inspect

在上面对应仓库目录执行，只读查看：

```sh
git tag --list "reprise-*"
git show reprise-ui/v08 --stat
git diff reprise-ui/v07 reprise-ui/v08
git log --oneline codex/reprise-ui-iterations
```

Core 仓库使用 `reprise-core/v01` 与 `reprise-core/v02`。当前预览保留原有本地数据目录；Git 标签保存程序与界面源码，媒体和私密 AI 配置留在原位置，不作为新版本源码提交。

## 验证 / Validation

- 61 个历史版本的英文名称、摘要、变化与预览标签检查通过；英文首次加载、中英往返、英文搜索、比较和证据弹窗、AI 设置页已验证。
- AI 生成须一次返回 zh/en 名称、摘要、变化与证据建议；缺失语言或证据不对应时拒绝保存。19 项本地夹具测试通过，没有实际模型请求。
- 通用核心测试 71 项运行通过，其中 8 项浏览器环境测试按配置跳过。
- Git 快照的恢复文件哈希与语法均通过检查。
- 证据目录：`/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/bilingual-content-20261008-212801`。
