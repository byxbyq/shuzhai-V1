// Extracted from app.js - 命令面板 + 审计日志
// ═══════════════════════════════════════════════════════════════════════
// 6.3 Web端命令面板（Ctrl+P / Ctrl+K）
// ═══════════════════════════════════════════════════════════════════════

// 命令注册表：每条命令含 id/name/icon/keywords/run
function _getCommandList() {
  return [
    {name: '新建项目', icon: '📁', keywords: 'new project 新建', run: function() { var b = document.getElementById('btn-new-project'); if (b) b.click(); }},
    {name: '打开项目', icon: '📂', keywords: 'open project 打开', run: function() { var b = document.getElementById('btn-open-project'); if (b) b.click(); }},
    {name: 'AI生成正文', icon: '✨', keywords: 'generate ai 生成 正文', run: function() { var b = document.getElementById('btn-ai-gen'); if (b) b.click(); }},
    {name: '全部生成', icon: '🚀', keywords: 'generate all 全部 生成', run: function() { var b = document.getElementById('wt-btn-gen-all'); if (b) b.click(); }},
    {name: '去AI味', icon: '🔧', keywords: 'deai opt 去ai 人类化', run: function() { var b = document.getElementById('wt-btn-opt'); if (b) b.click(); }},
    {name: '续写', icon: '✍️', keywords: 'continue 续写', run: function() { var b = document.getElementById('wt-btn-cont'); if (b) b.click(); }},
    {name: '排版', icon: '📐', keywords: 'format 排版 分段 缩进', run: function() { var b = document.getElementById('btn-ai-format'); if (b) b.click(); }},
    {name: '保存', icon: '💾', keywords: 'save 保存', run: function() { if (typeof saveChapter === 'function') saveChapter(currentChapterIndex); else { var b = document.getElementById('btn-save'); if (b) b.click(); } }},
    {name: '头脑风暴', icon: '🧠', keywords: 'brainstorm 头脑 风暴 canvas', run: function() { if (typeof openBrainstormPanel === 'function') openBrainstormPanel(); }},
    {name: '五感描写', icon: '👁️', keywords: 'sensory 五感 描写', run: function() { if (typeof openSensoryPanel === 'function') openSensoryPanel(); }},
    {name: '描写增强', icon: '📝', keywords: 'describe 描写 增强 感官 环境 人物 动作', run: function() { if (typeof openDescribePanel === 'function') openDescribePanel(); }},
    {name: '场景扩写', icon: '📏', keywords: 'expand 扩写 场景 对话 心理 环境 动作', run: function() { if (typeof openExpandPanel === 'function') openExpandPanel(); }},
    {name: '灵活重写', icon: '🔄', keywords: 'rewrite 重写 口语 文学 紧张 轻松 视角', run: function() { if (typeof openRewritePanel === 'function') openRewritePanel(); }},
    {name: '5维反馈', icon: '💡', keywords: 'feedback 反馈 评分 雷达 情感 节奏 画面 对话 悬念', run: function() { if (typeof openFeedbackPanel === 'function') openFeedbackPanel(); }},
    {name: '添加章节', icon: '➕', keywords: 'add chapter 添加 章节', run: function() { var b = document.getElementById('btn-add-chapter'); if (b) b.click(); }},
    {name: '导出书籍', icon: '📥', keywords: 'export 导出 书籍', run: function() { if (typeof openExportPanel === 'function') openExportPanel(); }},
    {name: '版本对比', icon: '📋', keywords: 'diff snapshot 版本 对比', run: function() { if (typeof openSnapshotDiffPanel === 'function') openSnapshotDiffPanel(); }},
    {name: '角色对话', icon: '💬', keywords: 'character chat 角色 对话', run: function() { if (typeof openCharacterChatPanel === 'function') openCharacterChatPanel(); }},
    {name: '云同步', icon: '☁️', keywords: 'sync cloud 云 同步', run: function() { if (typeof openSyncPanel === 'function') openSyncPanel(); }},
    {name: '大纲模板', icon: '📐', keywords: 'template outline 大纲 模板', run: function() { if (typeof openTemplatePanel === 'function') openTemplatePanel(); }},
    {name: '批量检查', icon: '🔍', keywords: 'batch check 批量 检查', run: function() { if (typeof openBatchCheckPanel === 'function') openBatchCheckPanel(); }},
    {name: '写作统计', icon: '📊', keywords: 'stats 写作 统计', run: function() { if (typeof openStatsPanel === 'function') openStatsPanel(); }},
    {name: '技能包', icon: '🧩', keywords: 'skill pack 技能包', run: function() { if (typeof openSkillPackPanel === 'function') openSkillPackPanel(); }},
    {name: 'AI分析面板', icon: '🔬', keywords: 'ai analysis 分析 文风 伏笔', run: function() { if (typeof openAIAnalysisPanel === 'function') openAIAnalysisPanel(); }},
    {name: '快速模式', icon: '⚡', keywords: 'quick mode 快速 模式 一键生成', run: function() { if (typeof openQuickModePanel === 'function') openQuickModePanel(); }},
    {name: '审计日志', icon: '📋', keywords: 'audit log 审计 日志', run: function() { if (typeof openAuditLogPanel === 'function') openAuditLogPanel(); }},
    {name: '切换左面板', icon: '☰', keywords: 'toggle left 左 面板 章节抽屉', run: function() { var b = document.getElementById('btn-toggle-left'); if (b) b.click(); }},
    {name: '切换右面板', icon: '📖', keywords: 'toggle right 右 面板 设定抽屉', run: function() { var b = document.getElementById('btn-toggle-right'); if (b) b.click(); }},
    {name: '阅读模式', icon: '📖', keywords: 'reader 阅读 模式', run: function() { var b = document.getElementById('btn-reader'); if (b) b.click(); }},
  ];
}

var _cmdSelectedIndex = 0;
var _cmdFilteredList = [];

// 初始化命令面板
function initCommandPalette() {
  var overlay = document.getElementById('cmd-palette-overlay');
  var input = document.getElementById('cmd-input');
  var list = document.getElementById('cmd-list');
  if (!overlay || !input || !list) return;

  // 输入实时过滤
  input.addEventListener('input', function() {
    _renderCommandList(input.value);
  });

  // 键盘导航
  input.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _cmdSelectedIndex = Math.min(_cmdSelectedIndex + 1, _cmdFilteredList.length - 1);
      _updateCommandSelection();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _cmdSelectedIndex = Math.max(_cmdSelectedIndex - 1, 0);
      _updateCommandSelection();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (_cmdFilteredList[_cmdSelectedIndex]) {
        var cmd = _cmdFilteredList[_cmdSelectedIndex];
        closeCommandPalette();
        try { cmd.run(); } catch (err) { console.error('[CmdPalette]', err); }
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeCommandPalette();
    }
  });

  // 点击遮罩关闭
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) closeCommandPalette();
  });
}

// 打开命令面板
function openCommandPalette() {
  var overlay = document.getElementById('cmd-palette-overlay');
  var input = document.getElementById('cmd-input');
  if (!overlay || !input) return;
  overlay.style.display = 'flex';
  input.value = '';
  _renderCommandList('');
  setTimeout(function() { input.focus(); }, 50);
}

// 关闭命令面板
function closeCommandPalette() {
  var overlay = document.getElementById('cmd-palette-overlay');
  if (overlay) overlay.style.display = 'none';
}

// 渲染命令列表（支持过滤）
function _renderCommandList(query) {
  var list = document.getElementById('cmd-list');
  var countEl = document.getElementById('cmd-count');
  if (!list) return;
  var all = _getCommandList();
  query = (query || '').trim().toLowerCase();
  if (query) {
    _cmdFilteredList = all.filter(function(c) {
      var name = (c.name || '').toLowerCase();
      var kw = (c.keywords || '').toLowerCase();
      return name.indexOf(query) >= 0 || kw.indexOf(query) >= 0;
    });
  } else {
    _cmdFilteredList = all.slice();
  }
  _cmdSelectedIndex = 0;
  if (countEl) countEl.textContent = _cmdFilteredList.length;
  if (_cmdFilteredList.length === 0) {
    list.innerHTML = '<div style="text-align:center;color:var(--muted);padding:24px;font-size:12px">无匹配命令</div>';
    return;
  }
  list.innerHTML = _cmdFilteredList.map(function(c, i) {
    var active = i === 0;
    return '<div class="cmd-item" data-idx="' + i + '" onclick="_selectCommand(' + i + ')" style="padding:9px 12px;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:8px;border-radius:var(--radius-sm);' + (active ? 'background:var(--accent-soft, rgba(199,91,57,0.15));color:var(--accent)' : 'color:var(--text)') + '">'
      + '<span style="font-size:14px">' + (c.icon || '›') + '</span>'
      + '<span>' + c.name + '</span>'
      + '</div>';
  }).join('');
}

// 更新选中项样式
function _updateCommandSelection() {
  var items = document.querySelectorAll('.cmd-item');
  items.forEach(function(el, i) {
    var active = i === _cmdSelectedIndex;
    el.style.background = active ? 'var(--accent-soft, rgba(199,91,57,0.15))' : 'transparent';
    el.style.color = active ? 'var(--accent)' : 'var(--text)';
  });
  // 滚动到可见
  var sel = items[_cmdSelectedIndex];
  if (sel && sel.scrollIntoView) {
    var container = sel.parentElement;
    var cRect = container.getBoundingClientRect();
    var sRect = sel.getBoundingClientRect();
    if (sRect.top < cRect.top || sRect.bottom > cRect.bottom) {
      sel.scrollIntoView({block: 'nearest'});
    }
  }
}

// 鼠标点击选择命令
function _selectCommand(idx) {
  _cmdSelectedIndex = idx;
  if (_cmdFilteredList[idx]) {
    var cmd = _cmdFilteredList[idx];
    closeCommandPalette();
    try { cmd.run(); } catch (err) { console.error('[CmdPalette]', err); }
  }
}

// 注册全局快捷键 Ctrl+P / Ctrl+K
document.addEventListener('keydown', function(e) {
  // Ctrl+P 或 Ctrl+K 打开命令面板（阻止浏览器默认行为）
  if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P' || e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    e.stopPropagation();
    var overlay = document.getElementById('cmd-palette-overlay');
    if (overlay && overlay.style.display === 'flex') {
      closeCommandPalette();
    } else {
      openCommandPalette();
    }
    return false;
  }
});

// 页面加载完成后初始化命令面板
document.addEventListener('DOMContentLoaded', function() {
  initCommandPalette();
});
// 兜底：若 DOMContentLoaded 已触发，立即初始化
if (document.readyState !== 'loading') {
  initCommandPalette();
}

// ═══════════════════════════════════════════════════════════════════════
// 6.7 事件审计链（前端面板 + auditLog 记录函数）
// ═══════════════════════════════════════════════════════════════════════

// 记录一条审计事件（调用后端 POST /api/audit-log/log）
async function auditLog(action, target, detail) {
  try {
    await api('/api/audit-log/log', {
      method: 'POST',
      body: JSON.stringify({action: action, target: target || '', detail: detail || ''})
    });
  } catch (e) {
    // 审计日志失败不应影响主流程，仅打印日志
    console.warn('[AuditLog] 记录失败:', e);
  }
}

// 打开审计日志面板
function openAuditLogPanel() {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  if (!document.getElementById('audit-log-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'audit-log-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1200';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1201;width:92%;max-width:760px;height:85vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">📋</span><span class="title-accent-md-xl">事件审计日志</span><span style="font-size:11px;color:var(--muted);background:var(--bg);padding:2px 8px;border-radius:10px" id="audit-log-total">0</span></div>'
      + '    <div class="flex-row-xs">'
      + '      <button onclick="loadAuditLogList(50)" style="padding:4px 12px;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text)">刷新</button>'
      + '      <button onclick="closeOverlay(\'audit-log-overlay\')" class="btn-ghost-icon-xl-alt">✕</button>'
      + '    </div>'
      + '  </div>'
      + '  <div id="audit-log-stats" style="padding:10px 14px;border-bottom:1px solid var(--border);background:var(--bg);display:flex;flex-wrap:wrap;gap:6px"></div>'
      + '  <div id="audit-log-list" style="flex:1;overflow-y:auto;padding:10px"></div>'
      + '</div>';
    document.body.appendChild(overlay);
  } else {
    document.getElementById('audit-log-overlay').style.display = 'flex';
  }
  loadAuditLogList(50);
  loadAuditLogStats();
}

// 加载审计日志列表
async function loadAuditLogList(limit) {
  limit = limit || 50;
  var listEl = document.getElementById('audit-log-list');
  var totalEl = document.getElementById('audit-log-total');
  if (!listEl) return;
  listEl.innerHTML = '<div class="empty-state-sm-alt">⏳ 加载中...</div>';
  try {
    var r = await api('/api/audit-log/list?limit=' + limit);
    if (!r.ok) {
      listEl.innerHTML = '<div style="text-align:center;color:var(--danger);padding:30px;font-size:13px">❌ 加载失败: ' + (r.error || '').replace(/</g, '&lt;') + '</div>';
      return;
    }
    var logs = r.logs || [];
    if (totalEl) totalEl.textContent = r.total || logs.length;
    if (logs.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;font-size:13px">📝 暂无审计记录<br><span class="text-sm">执行生成正文、保存章节、去AI味等操作后将自动记录</span></div>';
      return;
    }
    // action 类型对应的颜色和图标
    var actionStyles = {
      generate: {icon: '✨', color: 'var(--accent)'},
      save: {icon: '💾', color: 'var(--success, #10b981)'},
      deai: {icon: '🔧', color: '#e74c3c'},
      continue: {icon: '✍️', color: 'var(--warn)'},
      export: {icon: '📥', color: '#9b59b6'},
      add_chapter: {icon: '➕', color: '#3498db'},
      brainstorm: {icon: '🧠', color: 'var(--accent)'},
    };
    listEl.innerHTML = logs.map(function(item) {
      var st = actionStyles[item.action] || {icon: '•', color: 'var(--muted)'};
      return '<div style="display:flex;gap:10px;padding:10px 12px;border-bottom:1px solid var(--border-soft);font-size:12px">'
        + '<span style="font-size:14px;flex-shrink:0">' + st.icon + '</span>'
        + '<div style="flex:1;min-width:0">'
        + '  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
        + '    <span style="color:' + st.color + ';font-weight:600">' + (item.action || '').replace(/</g, '&lt;') + '</span>'
        + '    <span class="text-ink">' + (item.target || '').replace(/</g, '&lt;') + '</span>'
        + '    <span style="color:var(--muted);font-size:10px;margin-left:auto;flex-shrink:0">' + (item.ts || '').replace(/</g, '&lt;') + '</span>'
        + '  </div>'
        + (item.detail ? '<div style="color:var(--muted);font-size:11px;margin-top:3px">' + item.detail.replace(/</g, '&lt;') + '</div>' : '')
        + '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="text-align:center;color:var(--danger);padding:30px;font-size:13px">❌ 加载出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// 加载审计日志统计
async function loadAuditLogStats() {
  var statsEl = document.getElementById('audit-log-stats');
  if (!statsEl) return;
  try {
    var r = await api('/api/audit-log/stats');
    if (!r.ok) { statsEl.textContent = ''; return; }
    var stats = r.stats || {};
    var keys = Object.keys(stats);
    if (keys.length === 0) {
      statsEl.innerHTML = '<span class="text-sm text-muted">暂无统计数据</span>';
      return;
    }
    var actionLabels = {
      generate: '生成', save: '保存', deai: '去AI味', continue: '续写',
      export: '导出', add_chapter: '添加章节', brainstorm: '头脑风暴'
    };
    statsEl.innerHTML = keys.map(function(k) {
      var label = actionLabels[k] || k;
      return '<span style="font-size:11px;padding:3px 10px;background:var(--surface);border:1px solid var(--border);border-radius:10px;color:var(--text)">' + label + ' <span style="color:var(--accent);font-weight:600">' + stats[k] + '</span></span>';
    }).join('');
  } catch (e) {
    statsEl.textContent = '';
  }
}

