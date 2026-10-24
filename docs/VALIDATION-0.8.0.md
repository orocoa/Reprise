# Reprise 0.8.0：验证范围 / Verification scope

2026-10-24（Asia/Shanghai）。本页区分维护者实测、未验证范围与外部采用，不把宣传素材当使用证据。

## 本机实际任务

- 将已核验最终源码 Skill ZIP 安装到当前 Codex 已识别的用户技能目录；备份旧技能、保留旧源码运行目录，不改模型或全局权限配置。
- Codex 官方 app-server 的 skills/list forceReload 返回一个已启用的 reprise，描述与新 Skill 一致。
- 通过已安装入口打开空工作台，没有导入当前目录；使用合成静态网页保存蓝色 A 和橙色 B，两张真实 PNG 均为2880×1800，分别绑定完整版本 SHA。
- 在真实工作台按蓝色画面选择 A，切换英文，使用默认新文件夹恢复。读回文件等于 A，源目录仍等于 B，二者为独立文件对象。
- 切换中英文保留所选稿；停止后重开仍保留两稿及原图。最后正常停止，两次服务端口均已关闭。Codex 配置哈希前后一致。

这是本机已有工具环境下的实际安装与任务验证。没有将原生选择器/输入框点击、全新 Mac 自动补齐依赖、WorkBuddy/TRAE 原生接入或所有框架运行写成通过。

## 自动检查

本轮完整 Python 回归：564项，549通过、15跳过、0失败；Node 契约88项通过。跳过项需要另外启用相应浏览器测试。此前一次完整回归中的未知原因等待超时仍保留历史记录；本次全套通过是另一轮实际结果。

截图与文件保存分开检查，恢复需逐字节读回；doctor 仅检查基础工具与包完整性。旧自带运行工具的 macOS 测试包已撤回，不作为安装入口。对公开预览 ZIP 的身份及相同核心文件另行核验，不将文件名相近当作同一包。

## English

The reviewed final source Skill was installed at the existing Codex user-Skill location, with the previous Skill and source runtimes retained. Official app-server discovery returned one enabled reprise with the new description. No model, global permission or Codex configuration change was made.

Using the installed entry, an empty workbench opened without importing the working directory. Two synthetic static webpage drafts produced actual 2880×1800 PNGs tied to their exact revisions. The browser selected blue A by its picture, switched to English and recovered it into the default new folder. Readback matched A, current source stayed B and the files were independent. Language/context, reopening persistence and normal shutdown passed; both test ports closed.

The full Python run completed 564 tests: 549 passed, 15 skipped, 0 failed. All 88 Node contracts passed. The earlier unexplained timeout remains a separate historical result. These checks do not establish fresh-Mac dependency setup, native selector/composer actions, native WorkBuddy/TRAE use, every framework or independent user adoption. The complete macOS runtime test package was withdrawn.
