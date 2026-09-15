(function() {
  'use strict';

  // ═══════════════════════════════════════════
  // Toast 通知组件
  // 用法: Toast.show('消息') / Toast.success('成功') / Toast.error('失败')
  // 向后兼容: window.showToast(msg) 自动路由到本组件
  // ═══════════════════════════════════════════

  var TOAST_TYPES = {
    info:    { bg: '#3b82f6', icon: '' },
    success: { bg: '#22c55e', icon: '' },
    error:   { bg: '#ef4444', icon: '' },
    warning: { bg: '#f59e0b', icon: '' },
  };

  var container = null;

  function ensureContainer() {
    if (container) return container;
    container = document.createElement('div');
    container.id = 'comp-toast-container';
    container.style.cssText =
      'position:fixed;top:16px;right:16px;z-index:99999;' +
      'display:flex;flex-direction:column;gap:8px;' +
      'pointer-events:none;max-width:380px';
    // 注入动画样式（仅一次）
    if (!document.getElementById('comp-toast-style')) {
      var style = document.createElement('style');
      style.id = 'comp-toast-style';
      style.textContent =
        '@keyframes comp-toast-in {' +
        '  from { opacity:0; transform:translateX(40px); }' +
        '  to   { opacity:1; transform:translateX(0); }' +
        '}' +
        '@keyframes comp-toast-out {' +
        '  from { opacity:1; transform:translateX(0); }' +
        '  to   { opacity:0; transform:translateX(40px); }' +
        '}';
      document.head.appendChild(style);
    }
    document.body.appendChild(container);
    return container;
  }

  function createToast(msg, type, duration) {
    var cfg = TOAST_TYPES[type] || TOAST_TYPES.info;
    var el = document.createElement('div');
    el.style.cssText =
      'padding:10px 16px;border-radius:6px;color:#fff;font-size:13px;' +
      'line-height:1.5;word-break:break-word;pointer-events:auto;' +
      'background:' + cfg.bg + ';' +
      'box-shadow:0 4px 12px rgba(0,0,0,0.35);' +
      'animation:comp-toast-in 0.25s ease;' +
      'cursor:default';
    el.textContent = msg;

    ensureContainer().appendChild(el);

    var timer = setTimeout(function() {
      el.style.animation = 'comp-toast-out 0.25s ease forwards';
      setTimeout(function() {
        if (el.parentNode) el.parentNode.removeChild(el);
      }, 250);
    }, duration);

    // 点击提前关闭
    el.addEventListener('click', function() {
      clearTimeout(timer);
      if (el.parentNode) el.parentNode.removeChild(el);
    });

    return el;
  }

  window.Toast = {
    show: function(msg, opts) {
      opts = opts || {};
      return createToast(msg, opts.type || 'info', opts.duration || 3000);
    },
    success: function(msg, duration) { return createToast(msg, 'success', duration || 2500); },
    error:   function(msg, duration) { return createToast(msg, 'error',   duration || 4000); },
    info:    function(msg, duration) { return createToast(msg, 'info',    duration || 3000); },
    warning: function(msg, duration) { return createToast(msg, 'warning', duration || 3500); },
  };

  // 覆盖全局 showToast（向后兼容 1400+ 处调用）
  window.showToast = function(msg) {
    window.Toast.show(msg);
  };

})();
