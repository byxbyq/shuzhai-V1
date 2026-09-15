// Extracted from app.js - 移动端优化 (滑动手势+虚拟键盘适配+底部工具栏)
// ═══════════════════════════════════════════
// 移动端优化：滑动手势 + 虚拟键盘适配 + 底部工具栏
// ═══════════════════════════════════════════

(function() {
  var isMobile = document.body.classList.contains('mobile-mode') || window.innerWidth <= 768 || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  if (!isMobile) return;

  // ── 1. 滑动手势 ──
  var touchStartX = 0, touchStartY = 0, touchEndX = 0, touchEndY = 0, touchStartTime = 0;
  var isSwiping = false;

  document.addEventListener('touchstart', function(e) {
    if (e.touches.length !== 1) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();
    isSwiping = false;
  }, { passive: true });

  document.addEventListener('touchmove', function(e) {
    if (e.touches.length !== 1) return;
    var dx = e.touches[0].clientX - touchStartX;
    var dy = e.touches[0].clientY - touchStartY;
    if (Math.abs(dx) > 20 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      isSwiping = true;
    }
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!isSwiping) return;
    touchEndX = e.changedTouches[0].clientX;
    touchEndY = e.changedTouches[0].clientY;
    var dx = touchEndX - touchStartX;
    var dy = touchEndY - touchStartY;
    var dt = Date.now() - touchStartTime;

    // 快速横向滑动（<500ms，水平位移>60px，垂直位移<80px）
    if (dt < 500 && Math.abs(dx) > 60 && Math.abs(dy) < 80) {
      var target = e.target;
      // 在输入框/textarea/AI面板中不触发
      if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT' || target.closest('#ai-assistant-panel') || target.closest('.suggestion-panel'))) return;

      var leftDrawer = document.querySelector('.left-drawer');
      var rightDrawer = document.querySelector('.right-drawer');

      if (dx > 0) {
        // 右滑：打开左抽屉 或 关闭右抽屉
        if (rightDrawer && rightDrawer.classList.contains('collapsed') === false && !rightDrawer.classList.contains('hidden')) {
          rightDrawer.classList.add('collapsed');
          updateOverlay();
        } else if (leftDrawer && leftDrawer.classList.contains('collapsed')) {
          leftDrawer.classList.remove('collapsed');
          updateOverlay();
        }
      } else {
        // 左滑：关闭左抽屉 或 打开右抽屉
        if (leftDrawer && leftDrawer.classList.contains('collapsed') === false) {
          leftDrawer.classList.add('collapsed');
          updateOverlay();
        } else if (rightDrawer && rightDrawer.classList.contains('collapsed')) {
          rightDrawer.classList.remove('collapsed');
          updateOverlay();
        }
      }
    }
    isSwiping = false;
  }, { passive: true });

  // ── 2. 虚拟键盘适配 ──
  var originalHeight = window.innerHeight;
  window.addEventListener('resize', function() {
    var newHeight = window.innerHeight;
    var heightDiff = originalHeight - newHeight;
    // 键盘弹出（高度减少>150px）
    if (heightDiff > 150) {
      document.body.classList.add('keyboard-open');
      // 聚焦的元素滚动到可视区
      var focused = document.activeElement;
      if (focused && (focused.tagName === 'TEXTAREA' || focused.tagName === 'INPUT')) {
        setTimeout(function() {
          focused.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 300);
      }
    } else {
      document.body.classList.remove('keyboard-open');
    }
    originalHeight = newHeight;
  });

  // AI助手输入框虚拟键盘适配
  var aiInput = document.getElementById('assistant-input');
  if (aiInput) {
    aiInput.addEventListener('focus', function() {
      var panel = document.getElementById('ai-assistant-panel');
      if (panel) {
        panel.style.height = window.innerHeight + 'px';
        panel.style.height = '100vh';
      }
    });
    aiInput.addEventListener('blur', function() {
      setTimeout(function() {
        var panel = document.getElementById('ai-assistant-panel');
        if (panel) panel.style.height = '';
      }, 100);
    });
  }

  // ── 辅助函数：更新遮罩层 ──
  function updateOverlay() {
    var overlay = document.getElementById('drawer-overlay');
    var leftDrawer = document.querySelector('.left-drawer');
    var rightDrawer = document.querySelector('.right-drawer');
    if (!overlay) return;
    var leftOpen = leftDrawer && !leftDrawer.classList.contains('collapsed');
    var rightOpen = rightDrawer && !rightDrawer.classList.contains('collapsed');
    if (leftOpen || rightOpen) {
      overlay.classList.add('visible');
    } else {
      overlay.classList.remove('visible');
    }
  }

  // ── 3. 底部工具栏：使用桌面端原生bottombar（水平滚动），不再覆盖自定义工具栏 ──
  // 确保桌面端bottombar在移动端可见，通过CSS处理水平滚动

  // ── 4. 双指缩放禁用（避免误触放大）但保留输入框缩放 ──
  document.addEventListener('gesturestart', function(e) {
    if (!e.target || (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA')) {
      e.preventDefault();
    }
  });

  // ── 5. 长按选词优化 ──
  document.addEventListener('touchstart', function(e) {
    // 编辑器中长按选词，不影响
    if (e.target && e.target.closest && e.target.closest('.editor-paper')) {
      return;
    }
    // 其他区域长按禁止弹出系统菜单
    if (e.target && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
      e.target.style.webkitTouchCallout = 'none';
    }
  }, { passive: true });

  // ── 6. 移动端顶部栏项目按钮优化 ──
  // 确保新建/打开项目按钮在移动端有正确的触摸区域
  var btnNew = document.getElementById('btn-new-project');
  var btnOpen = document.getElementById('btn-open-project');
  if (btnNew) {
    btnNew.addEventListener('touchstart', function() { btnNew.style.background = 'rgba(255,255,255,0.08)'; }, { passive: true });
    btnNew.addEventListener('touchend', function() { btnNew.style.background = ''; }, { passive: true });
  }
  if (btnOpen) {
    btnOpen.addEventListener('touchstart', function() { btnOpen.style.background = 'rgba(255,255,255,0.08)'; }, { passive: true });
    btnOpen.addEventListener('touchend', function() { btnOpen.style.background = ''; }, { passive: true });
  }

  console.log('[Mobile] 移动端优化已加载：滑动手势+虚拟键盘适配+底部工具栏+项目按钮');
})();
