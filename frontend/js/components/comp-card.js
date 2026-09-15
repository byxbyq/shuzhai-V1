(function() {
  'use strict';

  // ═══════════════════════════════════════════
  // 通用卡片组件
  // Card.settingsRow(container, item, callbacks) — 设定行（含 gen/opt/check/move/del 按钮）
  // Card.renderGroup(container, groupName, items, callbacks) — 整组渲染
  // ═══════════════════════════════════════════

  /**
   * 创建单行设定卡片
   * @param {HTMLElement} container - 父容器
   * @param {Object} item - { key, val, group }
   * @param {Object} callbacks - { onGen, onOpt, onCheck, onMove, onDel, onSelect, onInput }
   * @returns {HTMLElement} 行元素
   */
  function createSettingsRow(container, item, callbacks) {
    callbacks = callbacks || {};
    var highlightKey = callbacks.highlightKey || '';

    var row = document.createElement('div');
    row.className = 'setting-row' + (item.key === highlightKey ? ' conflict-highlight' : '');
    row.id = 'set-' + item.key;

    // 左侧：key + textarea
    var main = document.createElement('div');
    main.className = 'set-main';
    var keySpan = document.createElement('span');
    keySpan.className = 'set-key';
    keySpan.textContent = item.key;
    main.appendChild(keySpan);

    var textarea = document.createElement('textarea');
    textarea.className = 'set-val';
    textarea.rows = 2;
    textarea.value = item.val || '';
    textarea.addEventListener('input', function() {
      item.val = this.value;
      this.classList.add('modified');
      if (callbacks.onInput) callbacks.onInput(item, this.value);
    });
    main.appendChild(textarea);
    row.appendChild(main);

    // 右侧：操作按钮
    var actions = document.createElement('div');
    actions.className = 'setting-row-actions';

    function addBtn(label, title, cls, cb) {
      var btn = document.createElement('button');
      btn.className = 'sra-btn ' + (cls || '');
      btn.title = title;
      btn.textContent = label;
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        if (cb) cb(item, row, textarea);
      });
      actions.appendChild(btn);
    }

    addBtn('🤖 生成',  'AI生成', 'ft-gen',  callbacks.onGen);
    addBtn('✨ 优化',  'AI优化', 'ft-opt',  callbacks.onOpt);
    addBtn('🔍 检测', '检测',   'ft-check', callbacks.onCheck);
    addBtn('📁 移动', '移动分组', 'move-group', callbacks.onMove);
    addBtn('🗑 删除',  '删除',   'del',      callbacks.onDel);

    row.appendChild(actions);

    // 点击整行选中
    row.addEventListener('click', function(e) {
      if (e.target.closest('.sra-btn')) return;
      if (callbacks.onSelect) callbacks.onSelect(item, row);
    });

    container.appendChild(row);
    return row;
  }

  /**
   * 渲染一个分组的所有设定行
   * @param {HTMLElement} container - 父容器
   * @param {string} groupName - 分组名
   * @param {Array} items - 设定项数组 [{key, val, group}]
   * @param {Object} callbacks - { onGen, onOpt, onCheck, onMove, onDel, onSelect, onSaveGroup, onAIGenGroup, onAIOptGroup, onCheckGroup }
   * @returns {HTMLElement} 分组区块
   */
  function renderGroup(container, groupName, items, callbacks) {
    callbacks = callbacks || {};

    var sec = document.createElement('div');
    sec.className = 'settings-group';

    // 头部
    var header = document.createElement('div');
    header.className = 'settings-group-header expanded';
    header.innerHTML =
      '<h4>' + groupName + '</h4>' +
      '<span class="group-count">' + (items ? items.length : 0) + '</span>' +
      '<div class="group-actions">' +
      (callbacks.onAIGenGroup  ? '<button class="btn-sm ai" data-act="ai-gen">🤖 AI生成</button>' : '') +
      (callbacks.onAIOptGroup  ? '<button class="btn-sm" data-act="ai-opt">✨ AI优化</button>' : '') +
      (callbacks.onCheckGroup  ? '<button class="group-check-btn" data-act="check">🔍 全组检测</button>' : '') +
      (callbacks.onSaveGroup   ? '<button class="btn-sm accept" data-act="save">💾 保存</button>' : '') +
      '</div>';

    // 展开/折叠
    header.addEventListener('click', function(e) {
      if (e.target.closest('.group-actions')) return;
      header.classList.toggle('expanded');
      var body = header.nextElementSibling;
      if (body && body.classList.contains('section-body')) {
        body.classList.toggle('collapsed');
      }
    });

    sec.appendChild(header);

    // 内容体
    var body = document.createElement('div');
    body.className = 'section-body';
    if (items) {
      items.forEach(function(item) {
        createSettingsRow(body, item, callbacks);
      });
    }

    // 添加行
    var addRow = document.createElement('div');
    addRow.className = 'settings-add-row';
    var addInput = document.createElement('input');
    addInput.type = 'text';
    addInput.placeholder = '+ 添加设定项，回车确认...';
    addInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && this.value.trim()) {
        var key = this.value.trim();
        if (!items.find(function(s) { return s.key === key && s.group === groupName; })) {
          var newItem = { key: key, val: '', group: groupName };
          items.push(newItem);
          createSettingsRow(body, newItem, callbacks);
          if (callbacks.onAdd) callbacks.onAdd(newItem);
          // 更新计数
          var countEl = header.querySelector('.group-count');
          if (countEl) countEl.textContent = items.length;
        }
        this.value = '';
      }
    });
    addRow.appendChild(addInput);
    body.appendChild(addRow);
    sec.appendChild(body);

    // 头部按钮事件
    var aiGenBtn  = header.querySelector('[data-act="ai-gen"]');
    var aiOptBtn  = header.querySelector('[data-act="ai-opt"]');
    var checkBtn  = header.querySelector('[data-act="check"]');
    var saveBtn   = header.querySelector('[data-act="save"]');
    if (aiGenBtn)  aiGenBtn.addEventListener('click', function() { if (callbacks.onAIGenGroup) callbacks.onAIGenGroup(groupName, items); });
    if (aiOptBtn)  aiOptBtn.addEventListener('click', function() { if (callbacks.onAIOptGroup) callbacks.onAIOptGroup(groupName, items); });
    if (checkBtn)  checkBtn.addEventListener('click', function() { if (callbacks.onCheckGroup) callbacks.onCheckGroup(groupName, items); });
    if (saveBtn)   saveBtn.addEventListener('click', function() { if (callbacks.onSaveGroup) callbacks.onSaveGroup(groupName, items); });

    container.appendChild(sec);
    return sec;
  }

  window.Card = {
    createSettingsRow: createSettingsRow,
    renderGroup: renderGroup,
  };

})();
