// ═══════════════════════════════════════════════════════════════
// app.js — 精简后的主入口文件
// 原始完整文件已备份为 app.js.bak
// ═══════════════════════════════════════════════════════════════
//
// 模块拆分说明：
//   以下模块已提取至 frontend/js/modules/ 目录：
//
//   1. modules/check-panel.js      — 行1-481    检查/验证面板 (workflowState, buildCheckContext, runCheck, parseOutline, renderChapterList)
//   2. modules/editor.js           — 行482-697   章节编辑器 (loadChaptersFromAPI, autoSaveBeforeChapterSwitch, loadChapterContentAPI)
//   3. modules/init.js             — 行697-2670  初始化逻辑 (extractOutlineFromNovelActs, handleProjectClick, reloadAllProjectData, injectFieldToolbar, renderValResult, AI修复)
//   4. modules/wizard.js          — 行2671-2861 首次启动向导 + initApp
//   5. modules/settings.js         — 行2862-3071 项目设置/大纲加载保存
//   6. modules/validate-ui.js      — 行3072-4421 检查按钮UI和报告渲染 (setupCheckButtons, showFlavorReport)
//   7. modules/memory-panel.js     — 行4422-5095 记忆面板 (Truth Ledger + 向量记忆 + ShuZhai命名空间挂载)
//   8. modules/shuzhai-namespace.js— 行5044-5090 ShuZhai命名空间挂载 (memory-panel.js 的子集)
//   9. modules/toolbox.js          — 行5096-6229 工具箱8大面板 (导出/导入/快照对比/角色对话/同步/模板/批量检查/统计)
//  10. modules/mobile.js           — 行6230-6409 移动端优化 (滑动手势+虚拟键盘适配+底部工具栏)
//  11. modules/ai-assistant.js     — 行6411-6869 AI对话中枢 (全局助手)
//  12. modules/ai-analysis.js      — 行6871-7588 AI分析面板 (AI味检测/文风指纹/伏笔引力/线程分布)
//  13. modules/commands.js         — 行7589-7889 命令面板 + 审计日志
//  14. modules/distill.js          — 行7890-8551 记忆蒸馏面板 (Memory Distillation)
//
// 引入方式（在 index.html 中添加）:
//   <script src="js/modules/check-panel.js"></script>
//   <script src="js/modules/editor.js"></script>
//   <script src="js/modules/init.js"></script>
//   <script src="js/modules/wizard.js"></script>
//   <script src="js/modules/settings.js"></script>
//   <script src="js/modules/validate-ui.js"></script>
//   <script src="js/modules/memory-panel.js"></script>
//   <script src="js/modules/shuzhai-namespace.js"></script>
//   <script src="js/modules/toolbox.js"></script>
//   <script src="js/modules/mobile.js"></script>
//   <script src="js/modules/ai-assistant.js"></script>
//   <script src="js/modules/ai-analysis.js"></script>
//   <script src="js/modules/commands.js"></script>
//   <script src="js/modules/distill.js"></script>
//
// ═══════════════════════════════════════════════════════════════

// ══ 移动端检测（最早执行） ══
(function(){
  var ua = navigator.userAgent || '';
  // 仅通过 UA 和 Capacitor 判断真实移动设备，不依赖窗口宽度
  var isMobileDevice = /Android|iPhone|iPad|iPod|Mobile/i.test(ua) || !!window.Capacitor;
  function applyMobileMode() {
    var narrow = window.innerWidth <= 768;
    var shouldEnable = isMobileDevice || narrow;
    document.documentElement.classList.toggle('mobile-mode', shouldEnable);
    document.documentElement.classList.toggle('mobile-device', isMobileDevice);
    if (document.body) {
      document.body.classList.toggle('mobile-mode', shouldEnable);
    }
  }
  applyMobileMode();
  // 窗口大小变化时动态切换，避免分屏/缩放导致布局错乱
  var resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(applyMobileMode, 150);
  });
  if (!document.body) {
    document.addEventListener('DOMContentLoaded', function() {
      document.body.classList.toggle('mobile-mode', isMobileDevice || window.innerWidth <= 768);
    });
  }
})();


// ═══════════════════════════════════════════
// 挂载关键函数到 ShuZhai 命名空间
// 注意：各模块还未加载，所以用 try-catch 保护
// 这些函数在模块加载后会自动挂载到 window 全局
// ═══════════════════════════════════════════
window.ShuZhai = window.ShuZhai || {};

// 暴露到全局作用域的辅助函数（各模块加载后会自行挂载）
// 这里只挂载 app.js 自身定义的函数
try { if (typeof showToast === 'function') window.ShuZhai.showToast = showToast; } catch(e) {}

// P2-13: 自动保存（30秒间隔）
// 等待标记：initApp 完成数据加载后设置此标记为 true，才启动自动保存
window._dataLoaded = false;

// 每秒检查一次是否数据已加载，加载后启动 30秒自动保存循环
var _autoSaveCheckInterval = setInterval(function() {
  if (window._dataLoaded) {
    clearInterval(_autoSaveCheckInterval);
    setInterval(function() {
      if (currentChapterIndex >= 0 && chapters && chapters[currentChapterIndex]) {
        var editorEl = document.getElementById('editor-content');
        if (editorEl) {
          // 草稿模式下跳过AutoSave，防止草稿测试数据被写入磁盘
          if (window.DraftManager && DraftManager.isActive()) return;
          // P0: 生成下一章大纲期间跳过自动保存，防止旧章节正文串写到新章节
          if (window._skipAutoSaveOnLeaveStep6) return;
          var content = editorEl.innerText || '';
          if (content.trim() && chapters[currentChapterIndex].content !== content) {
            saveChapter(currentChapterIndex, content).then(function() {
              chapters[currentChapterIndex].content = content;
              console.log('[AutoSave] Content saved at', new Date().toLocaleTimeString());
            }).catch(function(e) {
              console.warn('[AutoSave] Failed:', e);
            });
          }
        }
      }
    }, 30000);
  }
}, 1000);
