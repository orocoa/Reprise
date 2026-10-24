# 倒带 / Reprise 分享成稿

本页是待发布文案，不代表已经发布或开放下载。适用于 0.8 本地候选；正式发布时应重新核对下载入口和能力范围。试用任务与停止条件以[中文任务单](PRIVATE-TEST-TASKS-20261024.md) / [English task sheet](PRIVATE-TEST-TASKS.en-20261024.md)为准。

## 小红书正文

**网页改了几版，还是想要之前那版**

用 AI 改网页，配色、间距和布局经常要来回试。

有时改完才发现，我还是更喜欢前一版。但只记得它的样子，想不起存在哪个文件夹。

所以做了倒带 / Reprise。准备再改一轮时，先让它保存这一稿和画面。之后打开工作台，按图认出想要的那版，取出一份副本继续改，现在这稿也留着。

它需要提前保存，不能找回从没存过的内容。

目前是轻量源码 Skill 的本地候选，先做小范围试用，还没有公开的新版本下载。由 agent 先复用环境，缺依赖时按正常授权补齐。如果你最近也有过找旧稿的经历，我更想知道你原来怎么找，以及哪一步最麻烦。

GitHub 搜「orocoa / Reprise」

#VibeCoding #AI编程 #本地网页 #开源工具

## GitHub 中文分享短文

倒带 / Reprise 给正在修改的本地网页主动留稿，以后按截图、名称和时间认出旧稿，并取回到新文件夹继续修改。

在已有的 agent 对话里选择 Reprise Skill：说“打开”只进入工作台，说“保存当前网页这一稿，同时记住画面”才留稿。程序在本机执行，当前项目保持原样。

0.8 仍未公开，主交付是轻量源码 Skill 与脚本。agent 先检查复用环境，缺少依赖时按官方方法和正常授权补齐。静态 HTML 可尝试直接出图；受支持的独立 npm/Vite 项目会先保存，再请你确认安装和运行计划。它不会自动记录所有修改，也无法取回从未保存的版本。

代码采用 MIT，依赖保留各自许可。现在需要的是具体任务反馈：你原来如何找稿，是否找到正确版本，安装和保存是否值得多这一步。

## English project introduction

**Save a draft before your next change, then find it later by how it looked.**

Reprise helps people repeatedly editing local websites with an AI agent or editor keep named drafts, recognize them by screenshots, and recover a copy into a new folder. The current project stays unchanged.

After setup, select the Reprise Skill. Say “Open” to see the workbench, or “Save this website draft, including its screenshot” to keep a draft. You must save before editing; Reprise cannot recover versions you never saved.

The unpublished 0.8 candidate is primarily a lightweight source Skill and scripts. The agent checks/reuses tools and installs missing dependencies through official methods and normal authorization. Static HTML can attempt capture directly. Supported standalone npm/Vite projects save first and request approval of an install-and-run plan. Source code is MIT-licensed; dependencies retain their own licenses.

We are looking for specific workflow feedback: how you previously found an older draft, whether Reprise retrieved the right one, and whether the benefit justified setup and saving.

## English trial invitation

Have you recently wanted an earlier version of a local webpage but remembered only how it looked? I am testing Reprise: save a draft before another edit, then recognize it by its picture and recover a copy.

I would like to observe a few people who already have this task, using a nonsensitive copy of a real project. The current candidate uses host dependencies through a lightweight source Skill; not every agent can install or run them. We will confirm the device, agent client and project fit before providing a candidate; there is no public 0.8 download yet. I am looking for obstacles and reasons not to use it, not a Star or a positive review.

## 使用这些文案时

先核对实际演示和候选包。保留“提前保存”“本地候选”和实际支持范围；不要加“所有网页”“一键找回任何历史”“所有 agent 通用”等承诺。以上正文不需要同时附上全部内部评审。视频操作顺序见[中文分镜](SHARING-BRIEF.md) / [English storyboard](SHARING-BRIEF.en.md)。
