(function() {
  'use strict';

  // ═══════════════════════════════════════════
  // 通用弹窗组件
  // Modal.open(id) / Modal.close(id) / Modal.create(id, opts)
  // Confirm.show(msg, cb) / Confirm.prompt(title, defVal, cb)
  // 向后兼容: customConfirm / customPrompt 自动路由到 Confirm
  // ═══════════════════════════════════════════

  var _registry = {};   // id -> { overlay, onClose }
  var _dialogReady = false;
  var _dialogEls = {};

  // ── 动态弹窗（Modal.create 创建的）──

  function buildOverlay(id, opts) {
    var overlay = document.createElement('div');
    overlay.id = id;
    overlay.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10000;' +
      'display:none;align-items:center;justify-content:center';
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay && opts.backdropClose !== false) {
        window.Modal.close(id);
      }
    });

    var content = document.createElement('div');
    content.style.cssText =
      'background:var(--surface,#1e1e2e);border:1px solid var(--border,#333);' +
      'border-radius:10px;max-width:' + (opts.width || '480px') + ';width:90%;' +
      'max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.45)';

    var html = '';
    // 标题栏
    html += '<div style="padding:16px 20px;border-bottom:1px solid var(--border-soft,var(--border,#333));' +
      'font-size:16px;font-weight:600;display:flex;justify-content:space-between;align-items:center">' +
      '<span>' + (opts.title || '') + '</span>' +
      '<button onclick="Modal.close(\'' + id + '\')" ' +
      'style="border:none;background:none;color:var(--muted,#888);cursor:pointer;font-size:18px;padding:0 4px;line-height:1">&times;</button>' +
      '</div>';

    // 内容体
    var bodyCls = opts.bodyPad === false ? '' : 'padding:20px;';
    html += '<div style="' + bodyCls + 'font-size:13px;line-height:1.6">' + (opts.body || '') + '</div>';

    // 按钮栏
    if (opts.buttons && opts.buttons.length) {
      html += '<div style="padding:12px 20px;border-top:1px solid var(--border-soft,var(--border,#333));' +
        'display:flex;justify-content:flex-end;gap:8px">';
      opts.buttons.forEach(function(btn) {
        var style = btn.type === 'primary'
          ? 'background:var(--accent,#c75b39);color:#fff;border:none'
          : 'background:transparent;color:var(--muted,#888);border:1px solid var(--border,#444)';
        html += '<button style="padding:6px 18px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;' + style + '"' +
          (btn.onClick ? ' onclick="' + btn.onClick + '"' : '') + '>' + (btn.text || '') + '</button>';
      });
      html += '</div>';
    }

    content.innerHTML = html;
    overlay.appendChild(content);
    document.body.appendChild(overlay);
    return overlay;
  }

  window.Modal = {
    /**
     * 打开指定弹窗（动态创建的或已存在的 DOM 元素）
     */
    open: function(id) {
      var m = _registry[id];
      if (m) {
        m.overlay.style.display = 'flex';
        return;
      }
      var existing = document.getElementById(id);
      if (existing) {
        existing.style.display = 'flex';
      }
    },

    /**
     * 关闭指定弹窗
     */
    close: function(id) {
      var m = _registry[id];
      if (m) {
        m.overlay.style.display = 'none';
        if (m.onClose) m.onClose();
        return;
      }
      var existing = document.getElementById(id);
      if (existing) existing.style.display = 'none';
    },

    /**
     * 动态创建弹窗
     * opts: { title, body, width, buttons, backdropClose, bodyPad, onClose }
     * buttons: [{ text, type:'primary'|'default', onClick:'jsCode' }]
     */
    create: function(id, opts) {
      opts = opts || {};
      var overlay = buildOverlay(id, opts);
      _registry[id] = { overlay: overlay, onClose: opts.onClose };
      return overlay;
    },

    /**
     * 创建并立即打开弹窗（快捷方法）
     */
    show: function(id, opts) {
      var overlay = this.create(id, opts);
      overlay.style.display = 'flex';
      return overlay;
    },

    /**
     * 销毁动态弹窗的 DOM
     */
    remove: function(id) {
      var m = _registry[id];
      if (m && m.overlay.parentNode) {
        m.overlay.parentNode.removeChild(m.overlay);
      }
      delete _registry[id];
    },
  };

  // ── 确认/输入对话框（自建 DOM，不依赖 HTML 中的 custom-dialog-overlay）──

  function ensureDialogElements() {
    if (_dialogReady) return;

    var overlay = document.createElement('div');
    overlay.id = 'comp-dialog-overlay';
    overlay.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10001;' +
      'display:none;align-items:center;justify-content:center';
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) {
        // 不响应遮罩点击，强制按钮操作
      }
    });

    overlay.innerHTML =
      '<div style="background:var(--surface,#1e1e2e);border:1px solid var(--border,#333);' +
      'border-radius:10px;width:380px;max-width:90vw;box-shadow:0 8px 32px rgba(0,0,0,0.5);overflow:hidden">' +
      '<div id="comp-dialog-title" ' +
      'style="padding:16px 20px;font-size:15px;font-weight:600;border-bottom:1px solid var(--border-soft,var(--border,#333))"></div>' +
      '<div id="comp-dialog-message" ' +
      'style="padding:20px;font-size:13px;line-height:1.7;color:var(--ink,#ddd);display:none"></div>' +
      '<input id="comp-dialog-input" type="text" ' +
      'style="display:none;margin:0 20px 16px;width:calc(100% - 40px);padding:8px 12px;' +
      'border:1px solid var(--border,#444);border-radius:6px;background:var(--bg,#1a1a2e);' +
      'color:var(--ink,#eee);font-size:13px;outline:none" placeholder="">' +
      '<div style="padding:12px 20px;border-top:1px solid var(--border-soft,var(--border,#333));' +
      'display:flex;justify-content:flex-end;gap:8px">' +
      '<button id="comp-dialog-cancel" ' +
      'style="padding:6px 16px;border:1px solid var(--border,#444);border-radius:6px;' +
      'background:transparent;color:var(--muted,#888);cursor:pointer;font-size:12px">取消</button>' +
      '<button id="comp-dialog-ok" ' +
      'style="padding:6px 20px;border:none;border-radius:6px;background:var(--accent,#c75b39);' +
      'color:#fff;cursor:pointer;font-size:12px;font-weight:600">确定</button>' +
      '</div></div>';

    document.body.appendChild(overlay);

    _dialogEls.overlay = overlay;
    _dialogEls.title   = document.getElementById('comp-dialog-title');
    _dialogEls.message = document.getElementById('comp-dialog-message');
    _dialogEls.input   = document.getElementById('comp-dialog-input');
    _dialogEls.ok      = document.getElementById('comp-dialog-ok');
    _dialogEls.cancel  = document.getElementById('comp-dialog-cancel');
    _dialogReady = true;
  }

  function dialogCleanup() {
    var d = _dialogEls;
    d.overlay.style.display = 'none';
    d.ok.onclick = null;
    d.cancel.onclick = null;
    if (d.input) d.input.onkeydown = null;
  }

  window.Confirm = {
    show: function(message, callback) {
      ensureDialogElements();
      var d = _dialogEls;
      d.title.textContent = '确认操作';
      d.message.style.display = 'block';
      d.message.textContent = message;
      d.input.style.display = 'none';
      d.overlay.style.display = 'flex';
      setTimeout(function() { d.ok.focus(); }, 60);

      d.ok.onclick = function() { dialogCleanup(); if (callback) callback(true); };
      d.cancel.onclick = function() { dialogCleanup(); if (callback) callback(false); };
    },

    prompt: function(title, defaultValue, callback) {
      ensureDialogElements();
      var d = _dialogEls;
      d.title.textContent = title || '请输入';
      d.message.style.display = 'none';
      d.input.style.display = 'block';
      d.input.value = defaultValue || '';
      d.input.placeholder = '请输入...';
      d.overlay.style.display = 'flex';
      setTimeout(function() { d.input.focus(); d.input.select(); }, 60);

      d.ok.onclick = function() {
        var v = d.input.value;
        dialogCleanup();
        if (callback) callback(v);
      };
      d.cancel.onclick = function() {
        dialogCleanup();
        if (callback) callback(null);
      };
      d.input.onkeydown = function(e) {
        if (e.key === 'Enter') { e.preventDefault(); d.ok.click(); }
        if (e.key === 'Escape') { e.preventDefault(); d.cancel.click(); }
      };
    },
  };

  // 向后兼容：覆盖 index.html 中的 customConfirm / customPrompt
  window.customConfirm = function(message, callback) {
    window.Confirm.show(message, callback);
  };
  window.customPrompt = function(title, defaultValue, callback) {
    window.Confirm.prompt(title, defaultValue, callback);
  };

})();
