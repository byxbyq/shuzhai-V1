(function() {
  'use strict';

  // ═══════════════════════════════════════════
  // 通用表单组件
  // Form.renderDetail(container, fields, itemData) — 多字段表单渲染
  // Form.renderField(container, field) — 单字段渲染
  // Form.syncToSource(container, itemData) — 从表单读回数据
  // ═══════════════════════════════════════════

  function esc(s) {
    if (!s && s !== 0) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /**
   * 渲染单个表单字段
   * @param {HTMLElement} container - 父容器
   * @param {Object} field - { key, label, value, type, placeholder, group }
   */
  function renderField(container, field) {
    var div = document.createElement('div');
    div.className = 'def-field';
    div.setAttribute('data-field-key', field.key);

    var label = document.createElement('label');
    label.className = 'def-field-label';
    label.textContent = field.label || field.key;
    div.appendChild(label);

    var safeVal = esc(field.value || '');

    switch (field.type) {

      case 'char-arc':
        var arcDiv = document.createElement('div');
        arcDiv.className = 'def-field-char-arc';
        var nameInp = document.createElement('input');
        nameInp.type = 'text';
        nameInp.className = 'def-char-name';
        nameInp.placeholder = '角色名';
        nameInp.value = field.charName || '';
        nameInp.setAttribute('data-sub-key', 'charName');
        arcDiv.appendChild(nameInp);

        var sep = document.createElement('span');
        sep.className = 'def-arc-sep';
        sep.textContent = '→';
        arcDiv.appendChild(sep);

        var arcInp = document.createElement('input');
        arcInp.type = 'text';
        arcInp.className = 'def-arc-text';
        arcInp.placeholder = '从X到Y的转变';
        arcInp.value = field.arcText || '';
        arcInp.setAttribute('data-sub-key', 'arcText');
        arcDiv.appendChild(arcInp);
        div.appendChild(arcDiv);
        break;

      case 'hook':
        var hookInp = document.createElement('input');
        hookInp.type = 'text';
        hookInp.className = 'def-hook-text';
        hookInp.placeholder = '伏笔内容';
        hookInp.value = safeVal;
        hookInp.setAttribute('data-sub-key', 'value');
        div.appendChild(hookInp);
        break;

      case 'text':
        var txtInp = document.createElement('input');
        txtInp.type = 'text';
        txtInp.className = 'def-input';
        txtInp.value = safeVal;
        txtInp.setAttribute('data-sub-key', 'value');
        div.appendChild(txtInp);
        break;

      default: // textarea
        var ta = document.createElement('textarea');
        ta.className = 'def-textarea';
        ta.setAttribute('data-sub-key', 'value');
        ta.placeholder = field.placeholder || '';
        ta.textContent = field.value || '';
        div.appendChild(ta);
        break;
    }

    container.appendChild(div);
    return div;
  }

  /**
   * 渲染多字段表单
   * @param {HTMLElement} container
   * @param {Array} fields - [{key, label, value, type, placeholder, group, ...}]
   * @param {Object} itemData - 额外元数据（可选）
   * @param {Function} onChange - 字段变更回调
   */
  function renderDetail(container, fields, itemData, onChange) {
    container.innerHTML = '';
    var currentGroup = '';

    fields.forEach(function(f) {
      if (f.group !== currentGroup) {
        if (currentGroup !== '') {
          // close previous group
        }
        if (f.group) {
          var groupDiv = document.createElement('div');
          groupDiv.className = 'def-field-group';
          var groupTitle = document.createElement('div');
          groupTitle.className = 'def-field-group-title';
          groupTitle.textContent = f.group;
          groupDiv.appendChild(groupTitle);
          container.appendChild(groupDiv);
        }
        currentGroup = f.group || '';
      }
      renderField(container, f);
    });

    // 绑定 input 事件
    if (onChange) {
      container.querySelectorAll('textarea, input').forEach(function(el) {
        el.addEventListener('input', function() {
          onChange(el);
        });
      });
    }
  }

  /**
   * 从容器中读取表单数据，同步回源 fields 数组
   */
  function syncToSource(container, fields) {
    container.querySelectorAll('.def-field').forEach(function(fieldEl) {
      var key = fieldEl.getAttribute('data-field-key');
      var field = fields.find(function(f) { return f.key === key; });
      if (!field) return;

      if (field.type === 'char-arc') {
        var nameEl = fieldEl.querySelector('[data-sub-key="charName"]');
        var arcEl  = fieldEl.querySelector('[data-sub-key="arcText"]');
        if (nameEl) field.charName = nameEl.value;
        if (arcEl)  field.arcText  = arcEl.value;
      } else {
        var valEl = fieldEl.querySelector('[data-sub-key="value"]');
        if (valEl) field.value = valEl.value;
      }
    });
  }

  window.Form = {
    renderField:    renderField,
    renderDetail:   renderDetail,
    syncToSource:   syncToSource,
    esc:            esc,
  };

})();
