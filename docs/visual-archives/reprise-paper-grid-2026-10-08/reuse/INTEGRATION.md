# 接入新项目

打开 index.html 体验通用内容的同一排版与动画。该示例不含 PersonalWeb 的项目数据或媒体；demo-grid.svg 为本次创建的中性示例画面。

styles.css 和 browse-motion.js 是已确认源文件的原样副本。HTML 示例将 CSS 和运动引擎内联以支持直接打开。实际接入时使用独立 CSS/JS，按业务映射选择器与内容；遵循 ../DESIGN.md、../MOTION.md。

关键 DOM 契约：.view、.browser-layout.is-index、.version-browser、.version-browser-contents、.current-git-choice、.search-box、.version-list、.version-card、.version-detail、.detail-header、.change-content、.preview-menu、.management-heading、.resource-row。引擎里的原 Reprise 页面 ID 仅是这个参考实现的选择器契约，迁移时替换为新项目的页面结构。

导航前 capture 实际边框，再取消旧动画，渲染终点布局，最后 open；全宽目录选中条目使用 browseMotion，跨页和详情内容切换使用 viewMotion。设置 demoReady 后启用运动，resize/scroll 和减少动态效果沿用原清理行为。避免复制原应用的服务器地址、Git 逻辑、标题与 SHA。
