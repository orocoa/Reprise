# Reprise 设计参考与偏好

记录日期：2026-10-09。用于后续 Reprise 设计与参考检索。优先保留用户明确喜欢的部分；较新的具体选择优先于较早的探索方案。

核心方向：简约、清爽、柔和、容易亲近的可视化版本选择器。让非计算机背景的用户也能找到想要的版本，看懂其来历与变化，再决定是否加载；仍然分不清时才进入比较。

## 本次重点收藏

| 参考与官网 | 喜欢的部分 | 在 Reprise 中的用途 |
| --- | --- | --- |
| [Retcon](https://retcon.app/) | 整体层级和分区。清楚交代“选中了什么”和“正在看什么”；列表有扫描密度，内容区不被同等重量的卡片切碎。 | 左侧定位版本，右侧聚焦当前版本；把主要内容换成可辨认的版本画面与更新内容。 |
| [Gitfox](https://www.gitfox.app/) | 图片差异视图、A/B 选择、信息表达，以及沿着彩色线条追溯来历的能力。 | 参考画面对比、历史路线、选中状态和日期排列。主线固定竖轨，分叉与汇合以短圆弧换轨。 |
| [As Dusk Falls](https://www.asduskfalls.com/) | 用户特别认可路线与选择逻辑。 | 参考版本之间的发展关系、节点选择和回到某个阶段的理解方式。 |

Retcon 和 Gitfox 收藏的重点是官网展示的应用界面。《As Dusk Falls》收藏的重点是游戏中的路线与选择逻辑：用户此前明确认为它的视觉风格一般，视觉上更偏向 Retcon＋Gitfox，因此不把游戏美术或宣传网站外观视为最终风格。

Gitfox 官网提供图片分屏与并排比较的展示。用户喜欢的是其中的信息表达与选择方式，不满足于普通的“两张图片摆在一起”，也不希望照搬完整 Git 客户端的复杂信息密度。

## 之前明确喜欢的参考

| 参考与官网 | 用户表达的偏好 | 使用范围 |
| --- | --- | --- |
| [Fork](https://www.fork.dev/) | 喜欢历史定位和扫描效率，认为完整信息密度可以进一步收敛。 | 借快速定位历史的能力，同时提高版本画面的辨识度。 |
| [Quantum Break](https://www.remedygames.com/games/quantum-break) | 与《As Dusk Falls》一起被认可为不错的逻辑参考，视觉评价低于 Retcon＋Gitfox。 | 补充参考章节、时间线与选择逻辑，不作为主要美术风格。 |
| [Langbase](https://langbase.com/) | 明确喜欢其视觉风格，并要求参考动画、表达方式及每个元素的用途。 | 将表达方式用于可视化工作界面，保留已认可的功能区和布局。 |
| [Nothing](https://nothing.tech/) | 明确喜欢品牌风格与点阵的视觉感、科技感；点阵加载可以保留。 | 研究视觉系统后再融合；避免过度依赖 Nothing 的识别特征或刻意添加黑框。 |

[Nothing Playground](https://playground.nothing.tech/) 是此前研究中的补充官网入口；用户明确喜欢的是 Nothing 风格，未单独指定 Playground 为最喜欢的页面。

## 版本浏览与内容偏好

- **先找到版本。** 图片能让人认出画面，一句功能名补充图片无法表达的变化。重要版本应容易辨认；比较作为需要时的辅助入口。
- **先看懂，再加载。** 像游戏选择存档一样，能先了解版本，再加载运行。运行环境可以移除，版本历史继续保留。
- **来历必须清楚。** 左侧沿线可以追溯从哪里发展而来；分叉、汇合和主支线有明确意义，连接来自真实 Git 父子关系。
- **连线平稳。** 主线沿固定竖轨，分叉和汇合用合理的短曲线；避免长斜线、误穿节点和为了外观虚构连接。
- **列表紧凑但易读。** 版本号与日期同排，功能概括在下一排，星标突出重要版本。最新已采用的方案默认取消左侧看不清的小缩略图。
- **更新与画面一一对应。** 中间和右侧组成完整更新条目：简短功能标题、必要说明及对应图片或视频，共同滚动；不重复摆放同一张缩略图与大图。
- **文案短且有用。** 顶部直接写“此版本新增了什么、修复了什么”，详细说明放下方。省去无意义标签和宣传口号。
- **内容类型开放。** 支持各种 Git 项目的版本理解，不把内容范围限制在截图、录屏或代码差异。
- **保留操作上下文。** 查看详情、展开或返回后仍清楚自己在哪里，减少在多个页面之间来回找版本。

## 较新的视觉与字体选择

| 项目 | 截至本次记录的选择 |
| --- | --- |
| 整体 | 保留已认可的功能区和布局；融合 Langbase、Nothing 的视觉表达，做可视化工作界面。 |
| 控件形状 | 长方形操作按钮采用全圆角胶囊形（pill button）；设置等方形图标按钮采用圆形（circular icon button）。更多操作的省略号采用透明、无底色、无边框的无框按钮（borderless button），悬停也不出现圆底。收藏保留无外框的星标，位于名称行右侧、“运行此版本”下方。 |
| 颜色 | 红蓝为主要路线颜色；其他颜色在多个分叉同时出现时使用。颜色要醒目、可区分，不过度高饱和。最近 Demo 采用主线蓝、第一支线红。 |
| 字体气质 | 科技感与人文感融合，阅读内容保持易读。 |
| 设置入口 | 位于顶部右侧，放在刷新按钮后；中英文切换收进设置窗口的“界面语言”，切换时保持窗口打开。 |
| 左上项目名 | 自动识别实际项目名称，与下方左侧内容对齐；最新选择为 [Departure Mono](https://www.departuremono.com/)＋正格点黑 16。 |
| 其他文字 | Inter＋系统中文字体。此前喜欢过 Kode Mono，但后续已将特殊字体的使用收窄到左上项目名，并将该处改为 Departure Mono。 |
| 点阵 | 喜欢点阵的视觉感，可保留点阵加载；不把 Nothing 的专有品牌字样直接搬入产品。 |
| 历史浏览 | 使用“详细视图 / 紧凑视图”。紧凑视图采用 32px 单行标题，选中后也不展开简介，与详细视图明显拉开密度差距；保留分叉连线和收藏星标，通过“收藏”入口快速定位。没有真实父子连接的历史保持断开，并以“独立历史”轻量说明。 |
| 编辑入口 | 使用极简线性铅笔，偏好 Nothing 式的克制感。主入口常驻铅笔图标，去掉“编辑”文字；更新说明旁同样保留无文字的铅笔入口。采用 Feather edit-2，16px，只有外轮廓、没有内部装饰线；按钮保持透明、无边框。比较与选择依据见 [图标记录](/Users/kai/Documents/GitOrocoa/Reprise/work/visual-references/edit-icon-20261009/selection.md)。 |

## 需要避免的方向

- 工程化程度过高、复杂信息挤满页面，让不熟悉 Git 的人无从下手。
- 同等重量的卡片和黑线网格掩盖主次，无法判断先点哪里。早期白纸线框仍作为历史视觉档案保留，不视为当前唯一基线。
- 看不出变化的小缩略图、重复的媒体、无意义标签与口号。
- 把“比较差异”当成找版本的必经步骤，或仅用代码差异代表版本内容。
- 将游戏的逻辑参考误记成喜欢其全部视觉风格，将营销网站的页面结构直接移入工作界面。

## 已有参考画面与资料

以下原件继续保存在原目录，可回看当时喜欢的具体界面。

- [Retcon 分区画面](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/app-references-2026-10-08/retcon-commit.png)
- [Gitfox 历史路线](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/app-references-2026-10-08/gitfox-history.png)与[图片差异](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/app-references-2026-10-08/gitfox-images.png)
- [As Dusk Falls 路线树](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/game-version-references-2026-10-09/as-dusk-falls-tree.png)
- [Fork 历史界面](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/app-references-2026-10-08/fork.png)
- [Quantum Break 时间线](/Users/kai/Documents/GitOrocoa/Reprise/work/test-artifacts/game-version-references-2026-10-09/quantum-timeline.png)
- [Nothing 已有研究记录](/Users/kai/Documents/GitOrocoa/Reprise/work/visual-references/20261009-nothing-depth/nothing-official-research.md)
- [早期白纸线框视觉档案](/Users/kai/Documents/GitOrocoa/Reprise/docs/visual-archives/reprise-paper-grid-2026-10-08/DESIGN.md)

偏好依据：本次用户指示，以及聊天《寻找版本管理视觉参考》（2026-10-08 至 2026-10-09）和《Refine Reprise visual design》（2026-10-09）中的用户原话与后续修正。官网入口于 2026-10-09 核对。

Framer、Screen Studio、Linear、Raycast、Notion、Craft、Photomator、Darkroom、Flighty 等此前由助手提出的参考，不因出现在讨论中就自动列入用户喜欢清单。
