// Extracted from app.js - 记忆蒸馏面板 (Memory Distillation)
// ═══════════════════════════════════════════════════════════════════════
// 6.8 章节记忆蒸馏（Memory Distillation）
//   后端接口：
//     POST /api/distill/chapters  {chapter_indices, options:{extractors}}
//     GET  /api/distill/memory    返回所有蒸馏记忆
//     GET  /api/distill/status    返回各章节蒸馏状态
// ═══════════════════════════════════════════════════════════════════════

// 蒸馏提取器配置：key 与后端一致，label 为中文展示
// 改造后：
// - character/plot/foreshadowing/relationship 由 state_memory 自动产出（前端只读）
// - worldbuilding / writing_technique 仍可手动触发 AI 蒸馏
var _DISTILL_EXTRACTORS = [
  {key: 'state_memory',     label: '章节状态（自动）',   editable: false},
  {key: 'worldbuilding',    label: '世界观（AI 合成）',  editable: true},
  {key: 'writing_technique',label: '写作技法（AI 合成）',editable: true}
];

// 蒸馏面板当前状态
var _distillState = {
  chapters: [],     // 归一化后的章节列表（含蒸馏状态）
  selected: {},     // 章节勾选状态：{index: true/false}
  distilling: false,// 是否正在蒸馏
  currentTab: 'state_memory',
  memory: null      // 缓存的蒸馏记忆（避免切换标签时重复请求）
};

// 打开蒸馏面板（入口：写作工具栏按钮 / 工具箱菜单）
function openDistillPanel() {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  if (!document.getElementById('distill-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'distill-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1200';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1201;width:90%;max-width:720px;height:80vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      // 标题栏
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">🧠</span><span class="title-accent-md-xl">章节记忆蒸馏</span></div>'
      + '    <button onclick="closeOverlay(\'distill-overlay\')" class="btn-ghost-icon-xl-alt">✕</button>'
      + '  </div>'
      // 可滚动主体
      + '  <div style="flex:1;overflow-y:auto;padding:14px 18px">'
      // 说明区
      + '    <div style="font-size:12px;color:var(--muted);line-height:1.7;padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:14px">蒸馏已写章节，生成结构化记忆单元。后续生成新章节时自动注入，替代原文灌入，实现 <span style="color:var(--accent);font-weight:600">10倍上下文压缩</span>。</div>'
      // 章节选择区
      + '    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
      + '      <div class="text-base font-semibold">章节选择</div>'
      + '      <div class="flex-row-xs">'
      + '        <button onclick="toggleDistillAll(true)" class="btn-surface-xs">全选</button>'
      + '        <button onclick="toggleDistillAll(false)" class="btn-surface-xs">全不选</button>'
      + '        <button onclick="loadDistillStatus()" class="btn-surface-xs">刷新</button>'
      + '      </div>'
      + '    </div>'
      + '    <div id="distill-chapter-list" style="border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);margin-bottom:14px;max-height:220px;overflow-y:auto"><div class="empty-state-md">⏳ 加载章节列表...</div></div>'
      // 提取器选择区
      + '    <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px">提取器选择</div>'
      + '    <div id="distill-extractors" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px"></div>'
      // 操作区
      + '    <div style="display:flex;gap:8px;margin-bottom:14px">'
      + '      <button id="distill-run-btn" onclick="runDistill()" style="flex:1;padding:9px;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#fff;font-size:13px;font-weight:600;cursor:pointer">🧠 开始蒸馏</button>'
      + '      <button onclick="loadDistillMemory()" style="padding:9px 14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font-size:13px;cursor:pointer">👁️ 查看记忆</button>'
      + '    </div>'
      // 进度区
      + '    <div id="distill-progress" style="display:none;margin-bottom:14px"></div>'
      // 结果统计区
      + '    <div id="distill-result" style="display:none;margin-bottom:14px"></div>'
      // 导入外部素材蒸馏区域
      + '    <div style="border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);margin-bottom:14px">'
      + '      <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border-soft);cursor:pointer" onclick="toggleDistillImportArea()">'
      + '        <span style="font-size:14px">📦</span>'
      + '        <span class="text-base font-semibold">导入外部素材蒸馏</span>'
      + '        <span style="font-size:10px;color:var(--muted);margin-left:4px">支持 .txt/.srt/.vtt/.json/.csv</span>'
      + '        <span id="distill-import-toggle" style="margin-left:auto;font-size:10px;color:var(--muted)">▼</span>'
      + '      </div>'
      + '      <div id="distill-import-area" style="display:none;padding:12px">'
      + '        <div style="font-size:11px;color:var(--muted);margin-bottom:10px">上传文本文件（字幕/笔记/参考资料等），读取内容后追加到当前章节，再调用蒸馏提取器进行分析。</div>'
      + '        <div id="distill-file-drop" style="border:2px dashed var(--border);border-radius:var(--radius-sm);padding:20px;text-align:center;margin-bottom:10px;cursor:pointer">'
      + '          <div style="font-size:24px;margin-bottom:6px">📄</div>'
      + '          <div class="text-md text-muted">拖拽文件到此处，或<span class="text-accent-underline">点击选择</span></div>'
      + '          <input type="file" id="distill-file-input" accept=".txt,.srt,.vtt,.json,.csv" class="hidden" multiple>'
      + '        </div>'
      + '        <div class="mb-2.5">'
      + '          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">'
      + '            <label class="text-md text-muted">目标章节</label>'
      + '            <select id="distill-import-target-chapter" style="padding:4px 8px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--ink);font-size:11px"><option value="-1">仅蒸馏不上传到章节</option></select>'
      + '          </div>'
      + '        </div>'
      + '        <div id="distill-file-info" style="display:none;margin-bottom:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border-soft);border-radius:var(--radius-sm);font-size:11px;color:var(--text)"></div>'
      + '        <textarea id="distill-import-preview" placeholder="文件内容预览（可编辑）..." style="width:100%;min-height:80px;max-height:150px;padding:8px 10px;border:1px solid var(--border-soft);border-radius:var(--radius-sm);background:var(--bg);color:var(--ink);font-size:11px;font-family:var(--mono);resize:vertical;line-height:1.5;display:none"></textarea>'
      + '        <div style="display:flex;gap:8px;margin-top:10px">'
      + '          <button id="distill-import-btn" onclick="distillImportedFile()" style="flex:1;padding:8px;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#fff;font-size:12px;font-weight:600;cursor:pointer" disabled>🧪 蒸馏导入内容</button>'
      + '          <button onclick="clearDistillImport()" style="padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font-size:12px;cursor:pointer">清除</button>'
      + '        </div>'
      + '        <div id="distill-import-result" class="mt-2"></div>'
      + '      </div>'
      + '    </div>'
      // 记忆展示区
      + '    <div id="distill-memory-wrap" class="hidden">'
      + '      <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px">蒸馏记忆</div>'
      + '      <div id="distill-mem-tabs" style="display:flex;gap:2px;border-bottom:1px solid var(--border);margin-bottom:10px"></div>'
      + '      <div id="distill-mem-body" style="min-height:120px"></div>'
      + '    </div>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(overlay);
    // 渲染提取器复选框（默认全选）
    renderDistillExtractors();
  } else {
    document.getElementById('distill-overlay').style.display = 'flex';
  }
  // 加载章节蒸馏状态
  loadDistillStatus();
}

// 渲染提取器复选框
function renderDistillExtractors() {
  var wrap = document.getElementById('distill-extractors');
  if (!wrap) return;
  wrap.innerHTML = _DISTILL_EXTRACTORS.map(function(ex) {
    // 不可编辑的提取器（state_memory）显示为禁用灰色
    var disabled = !ex.editable;
    var checkedAttr = disabled ? 'checked' : 'checked';
    var disabledAttr = disabled ? 'disabled' : '';
    var opacity = disabled ? 'opacity:0.5;cursor:not-allowed;' : 'cursor:pointer;';
    return '<label style="display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);font-size:12px;color:var(--text);' + opacity + '">'
      + '<input type="checkbox" class="distill-extractor-cb" value="' + ex.key + '" ' + checkedAttr + ' ' + disabledAttr + '>'
      + '<span>' + ex.label + '</span>'
      + '</label>';
  }).join('');
}

// 获取已勾选的提取器（仅返回可编辑的，即 enabled=True 的）
function getSelectedDistillExtractors() {
  var cbs = document.querySelectorAll('.distill-extractor-cb');
  var list = [];
  cbs.forEach(function(cb) {
    if (cb.checked && !cb.disabled) list.push(cb.value);
  });
  // 兜底：若未勾选任何项，默认所有可编辑提取器
  if (list.length === 0) {
    list = _DISTILL_EXTRACTORS.filter(function(ex) { return ex.editable; })
                              .map(function(ex) { return ex.key; });
  }
  return list;
}

// 获取已勾选的章节索引（升序）
function getSelectedDistillChapters() {
  var idxs = [];
  Object.keys(_distillState.selected).forEach(function(k) {
    if (_distillState.selected[k]) idxs.push(parseInt(k));
  });
  return idxs.sort(function(a, b) { return a - b; });
}

// 全选 / 全不选
function toggleDistillAll(state) {
  _distillState.chapters.forEach(function(ch) {
    _distillState.selected[ch.index] = !!state;
  });
  renderDistillChapterList();
}

// 归一化获取章节列表（优先蒸馏状态接口，不足则补章节列表接口）
async function _getDistillChapterList() {
  var chapters = [];
  try {
    var statusRes = await api('/api/distill/status');
    if (statusRes && statusRes.ok !== false) {
      chapters = statusRes.chapters || statusRes.status || [];
    }
  } catch (e) { /* 忽略，走兜底 */ }
  // 若状态接口未返回章节基本信息，补充章节列表
  var needFallback = !chapters.length
    || (!chapters[0].title && (chapters[0].word_count === undefined && chapters[0].words === undefined));
  if (needFallback) {
    try {
      var cl = (typeof getChapterList === 'function') ? await getChapterList() : null;
      if (cl && cl.ok && cl.chapters) {
        var statusMap = {};
        chapters.forEach(function(c) { if (c && c.index !== undefined) statusMap[c.index] = c; });
        chapters = cl.chapters.map(function(ch, i) {
          var st = statusMap[i] || {};
          return {
            index: i,
            title: ch.title || ('第' + (i + 1) + '章'),
            word_count: ch.word_count || ch.words || 0,
            distilled: !!st.distilled
          };
        });
      }
    } catch (e) { /* 忽略 */ }
  }
  // 归一化字段
  chapters = chapters.map(function(c, i) {
    var idx = (c && c.index !== undefined) ? c.index : i;
    return {
      index: idx,
      title: (c && c.title) || ('第' + (idx + 1) + '章'),
      word_count: (c && (c.word_count || c.words)) || 0,
      distilled: !!(c && c.distilled)
    };
  });
  return chapters;
}

// 加载章节蒸馏状态
async function loadDistillStatus() {
  var listEl = document.getElementById('distill-chapter-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="empty-state-md">⏳ 加载章节列表...</div>';
  try {
    var chapters = await _getDistillChapterList();
    _distillState.chapters = chapters;
    // 清理已不存在章节的选中状态，并默认勾选所有已写内容（字数>0）的章节
    var validIndices = new Set(chapters.map(function(c) { return c.index; }));
    Object.keys(_distillState.selected).forEach(function(k) {
      if (!validIndices.has(parseInt(k))) delete _distillState.selected[k];
    });
    chapters.forEach(function(ch) {
      if (_distillState.selected[ch.index] === undefined) {
        _distillState.selected[ch.index] = (ch.word_count > 0);
      }
    });
    renderDistillChapterList();
  } catch (e) {
    listEl.innerHTML = '<div style="text-align:center;color:var(--danger);padding:20px;font-size:12px">❌ 加载失败: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// 渲染章节列表（含勾选框）
function renderDistillChapterList() {
  var listEl = document.getElementById('distill-chapter-list');
  if (!listEl) return;
  var chapters = _distillState.chapters;
  if (!chapters || chapters.length === 0) {
    listEl.innerHTML = '<div class="empty-state-md">📝 暂无章节，请先在写作步骤添加章节并写入正文</div>';
    return;
  }
  listEl.innerHTML = chapters.map(function(ch) {
    var checked = _distillState.selected[ch.index] ? 'checked' : '';
    var statusIcon = ch.distilled ? '✅' : '❌';
    var statusText = ch.distilled ? '已蒸馏' : '未蒸馏';
    var statusColor = ch.distilled ? 'var(--success, #10b981)' : 'var(--muted)';
    return '<div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-bottom:1px solid var(--border-soft);font-size:12px">'
      + '<input type="checkbox" class="distill-ch-cb" data-idx="' + ch.index + '" ' + checked + ' onchange="onDistillChToggle(' + ch.index + ', this.checked)" style="cursor:pointer">'
      + '<span style="color:var(--muted);min-width:42px">第' + (ch.index + 1) + '章</span>'
      + '<span style="flex:1;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (ch.title || '').replace(/</g, '&lt;') + '</span>'
      + '<span style="color:var(--muted);font-family:var(--mono);min-width:60px;text-align:right">' + (ch.word_count || 0) + ' 字</span>'
      + '<span style="min-width:64px;text-align:right;color:' + statusColor + '" title="' + statusText + '">' + statusIcon + ' ' + statusText + '</span>'
      + '</div>';
  }).join('');
}

// 章节勾选切换
function onDistillChToggle(idx, checked) {
  _distillState.selected[idx] = !!checked;
}

// 执行蒸馏（按章节顺序逐章蒸馏，提供真实进度反馈）
async function runDistill() {
  if (_distillState.distilling) return;
  var idxs = getSelectedDistillChapters();
  var extractors = getSelectedDistillExtractors();
  if (idxs.length === 0) {
    _setDistillProgress('<div style="text-align:center;color:var(--warn);padding:10px;font-size:12px">⚠️ 请至少勾选一个章节</div>', true);
    return;
  }
  _distillState.distilling = true;
  // 锁定按钮
  var runBtn = document.getElementById('distill-run-btn');
  if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ 蒸馏中...'; runBtn.style.opacity = '0.7'; }
  // 隐藏旧结果
  _hideEl('distill-result');
  _hideEl('distill-memory-wrap');

  var total = idxs.length;
  var success = 0;
  var failed = [];
  for (var i = 0; i < total; i++) {
    var idx = idxs[i];
    var ch = _distillState.chapters.filter(function(c) { return c.index === idx; })[0] || {};
    var chTitle = ch.title || ('第' + (idx + 1) + '章');
    // 更新进度
    _setDistillProgress(
      '<div class="card-surface-md">'
      + '<div class="flex-center-sm-mb2">'
      + '<span class="text-xl">⏳</span>'
      + '<span class="text-ink">正在蒸馏第' + (idx + 1) + '章「' + chTitle.replace(/</g, '&lt;') + '」...</span>'
      + '<span style="margin-left:auto;color:var(--muted)">' + (i + 1) + '/' + total + '</span>'
      + '</div>'
      + '<div class="progress-track">'
      + '<div style="height:100%;width:' + Math.round((i / total) * 100) + '%;background:var(--accent);transition:width .3s"></div>'
      + '</div></div>',
      true
    );
    try {
      var r = await api('/api/distill/chapters', {
        method: 'POST',
        body: JSON.stringify({chapter_indices: [idx], options: {extractors: extractors}})
      });
      if (r && r.ok !== false) {
        success++;
      } else {
        failed.push({idx: idx, title: chTitle, error: (r && r.error) || '未知错误'});
      }
    } catch (e) {
      failed.push({idx: idx, title: chTitle, error: e.message || '请求异常'});
    }
  }

  _distillState.distilling = false;
  if (runBtn) { runBtn.disabled = false; runBtn.textContent = '🧠 开始蒸馏'; runBtn.style.opacity = '1'; }

  // 进度条填满
  _setDistillProgress(
    '<div class="card-surface-md">'
    + '<div class="flex-center-sm-mb2">'
    + '<span class="text-xl">✅</span>'
    + '<span class="text-ink">蒸馏完成</span>'
    + '<span style="margin-left:auto;color:var(--muted)">' + total + '/' + total + '</span>'
    + '</div>'
    + '<div class="progress-track">'
    + '<div style="height:100%;width:100%;background:var(--success, #10b981)"></div>'
    + '</div></div>',
    true
    );

  // 渲染结果统计
  _renderDistillResult(success, total, failed, extractors);

  // 断点2修复：蒸馏成功后将结果写入 SkillPack（持久化到 localStorage）
  if (success > 0 && typeof SkillPack !== 'undefined' && SkillPack.add) {
    try {
      var packName = _distillState.novelName || '蒸馏技能包';
      var packId = 'distill_' + Date.now();
      var packData = {
        id: packId,
        name: packName,
        type: 'distill',
        created: new Date().toISOString(),
        rules: _distillState.lastDistillRules || [],
        memory: _distillState.lastDistillMemory || ''
      };
      SkillPack.add(packData);
      if (typeof showToast === 'function') {
        showToast('蒸馏技能包已保存到技能库', 'success');
      }
    } catch(e) {
      console.warn('[Distill] SkillPack.add 失败:', e);
    }
  }

  // 刷新章节状态 & 加载记忆
  await loadDistillStatus();
  loadDistillMemory();
}

// 渲染蒸馏结果统计
function _renderDistillResult(success, total, failed, extractors) {
  var el = document.getElementById('distill-result');
  if (!el) return;
  el.style.display = 'block';
  var failHtml = '';
  if (failed.length) {
    failHtml = '<div style="margin-top:8px;padding:8px 10px;background:var(--bg);border:1px solid var(--warn);border-radius:var(--radius-sm);font-size:11px;color:var(--warn)">'
      + '<div style="font-weight:600;margin-bottom:4px">⚠️ 失败章节 (' + failed.length + ')</div>'
      + failed.map(function(f) {
        return '<div>· 第' + (f.idx + 1) + '章「' + f.title.replace(/</g, '&lt;') + '」: ' + f.error.replace(/</g, '&lt;') + '</div>';
      }).join('')
      + '</div>';
  }
  el.innerHTML = '<div class="card-surface-md">'
    + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
    + '<span style="color:var(--success, #10b981);font-weight:600">✅ 成功 ' + success + '/' + total + ' 章</span>'
    + '<span class="text-muted">·</span>'
    + '<span class="text-ink">提取器: ' + extractors.map(function(k) {
        var ex = _DISTILL_EXTRACTORS.filter(function(e) { return e.key === k; })[0];
        return ex ? ex.label : k;
      }).join(' / ') + '</span>'
    + '</div>'
    + failHtml
    + '</div>';
}

// 加载蒸馏记忆并渲染标签页
async function loadDistillMemory() {
  var wrap = document.getElementById('distill-memory-wrap');
  var tabsEl = document.getElementById('distill-mem-tabs');
  var bodyEl = document.getElementById('distill-mem-body');
  if (!wrap || !tabsEl || !bodyEl) return;
  wrap.style.display = 'block';
  tabsEl.textContent = '';
  bodyEl.innerHTML = '<div class="empty-state-sm-alt">⏳ 正在加载蒸馏记忆...</div>';
  try {
    var r = await api('/api/distill/memory');
    if (!r || r.ok === false) {
      bodyEl.innerHTML = '<div style="text-align:center;color:var(--danger);padding:30px;font-size:12px">❌ 加载失败: ' + ((r && r.error) || '请先蒸馏章节').replace(/</g, '&lt;') + '</div>';
      return;
    }
    var memory = r.memory || r;
    _distillState.memory = memory; // 缓存记忆，供标签切换复用
    // 渲染标签
    tabsEl.innerHTML = _DISTILL_EXTRACTORS.map(function(ex) {
      var active = ex.key === _distillState.currentTab;
      return '<button class="distill-mem-tab" data-tab="' + ex.key + '" onclick="switchDistillMemTab(\'' + ex.key + '\')" style="padding:6px 12px;font-size:12px;border:none;border-bottom:2px solid ' + (active ? 'var(--accent)' : 'transparent') + ';background:none;color:' + (active ? 'var(--accent)' : 'var(--muted)') + ';cursor:pointer">' + ex.label + '</button>';
    }).join('');
    renderDistillMemTab(memory, _distillState.currentTab);
  } catch (e) {
    bodyEl.innerHTML = '<div style="text-align:center;color:var(--danger);padding:30px;font-size:12px">❌ 加载出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// 切换记忆标签页（从缓存渲染，不重复请求接口）
function switchDistillMemTab(tab) {
  _distillState.currentTab = tab;
  // 更新标签高亮
  document.querySelectorAll('.distill-mem-tab').forEach(function(btn) {
    var active = btn.dataset.tab === tab;
    btn.style.borderBottom = '2px solid ' + (active ? 'var(--accent)' : 'transparent');
    btn.style.color = active ? 'var(--accent)' : 'var(--muted)';
  });
  // 从缓存渲染当前标签内容
  renderDistillMemTab(_distillState.memory, tab);
}

// 渲染单个标签页记忆内容
function renderDistillMemTab(memory, extractor) {
  var bodyEl = document.getElementById('distill-mem-body');
  if (!bodyEl) return;
  var data = _extractDistillMemory(memory, extractor);
  if (data === null || data === undefined) {
    var exLabel = (_DISTILL_EXTRACTORS.filter(function(e) { return e.key === extractor; })[0] || {}).label || extractor;
    bodyEl.innerHTML = '<div class="empty-state-sm-alt">📝 暂无' + exLabel + '记忆单元<br><span style="font-size:11px;opacity:.7">请先蒸馏对应章节</span></div>';
    return;
  }

  // state_memory：按章节渲染可读卡片
  if (extractor === 'state_memory' && Array.isArray(data)) {
    bodyEl.innerHTML = _renderStateMemoryCards(data);
    return;
  }

  // 格式化 JSON 展示在 pre 标签中
  var jsonStr = '';
  try {
    jsonStr = JSON.stringify(data, null, 2);
  } catch (e) {
    jsonStr = String(data);
  }
  bodyEl.innerHTML = '<pre style="margin:0;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);font-family:var(--mono);font-size:11px;line-height:1.6;color:var(--text);white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto">' + jsonStr.replace(/</g, '&lt;') + '</pre>';
}

// 渲染 state_memory 按章节卡片
function _renderStateMemoryCards(stateFiles) {
  if (!stateFiles || !stateFiles.length) {
    return '<div class="empty-state-sm-alt">📝 暂无章节状态记忆<br><span style="font-size:11px;opacity:.7">定稿章节后会自动生成</span></div>';
  }
  // 倒序展示（最近章节在前）
  var sorted = stateFiles.slice().sort(function(a, b) {
    return (b.chapter_index || 0) - (a.chapter_index || 0);
  });
  var html = sorted.map(function(sf) {
    var chIdx = sf.chapter_index + 1;
    var events = (sf.events || []);
    if (!Array.isArray(events)) events = [events];
    var chars = (sf.characters || []);
    if (!Array.isArray(chars)) chars = [chars];
    var ff = sf.foreshadowing || {};
    var planted = (ff.planted || []);
    var resolved = (ff.resolved || []);
    var newSettings = sf.new_settings || [];
    var bridge = sf.bridge || {};

    var parts = [];
    parts.push('<div style="font-weight:600;color:var(--accent);margin-bottom:6px">第' + chIdx + '章</div>');
    if (events.length) {
      parts.push('<div class="my-1"><span class="text-muted">事件:</span> ' + events.map(function(e){return String(e).replace(/</g,'&lt;');}).join('；') + '</div>');
    }
    if (chars.length) {
      parts.push('<div class="my-1"><span class="text-muted">角色:</span> ' + chars.map(function(c){
        if (typeof c === 'string') return c.replace(/</g,'&lt;');
        var name = c.name || '?';
        var bits = [];
        if (c.location) bits.push('位置:' + c.location);
        if (c.realm) bits.push('境界:' + c.realm);
        if (c.mood) bits.push('心绪:' + c.mood);
        if (c.alive === false) bits.push('已死亡');
        return name + (bits.length ? '(' + bits.join('，') + ')' : '');
      }).join(' / ') + '</div>');
    }
    if (planted.length) {
      parts.push('<div class="my-1"><span class="text-muted">种伏笔:</span> ' + planted.map(function(p){
        return (typeof p === 'string' ? p : p.content || '').replace(/</g,'&lt;');
      }).join('；') + '</div>');
    }
    if (resolved.length) {
      parts.push('<div class="my-1"><span class="text-muted">回收伏笔:</span> ' + resolved.map(function(r){
        return (typeof r === 'string' ? r : r.content || '').replace(/</g,'&lt;');
      }).join('；') + '</div>');
    }
    if (newSettings.length) {
      parts.push('<div class="my-1"><span class="text-muted">新设定:</span> ' + newSettings.map(function(s){return String(s).replace(/</g,'&lt;');}).join('、') + '</div>');
    }
    if (bridge.to_next) {
      parts.push('<div class="my-1"><span class="text-muted">留给下章:</span> ' + String(bridge.to_next).replace(/</g,'&lt;') + '</div>');
    }
    return '<div style="padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:8px;font-size:11px;line-height:1.6">' + parts.join('') + '</div>';
  }).join('');
  return html;
}

// 从记忆对象中提取指定提取器的数据（兼容全局结构 / 按章节分结构）
function _extractDistillMemory(memory, extractor) {
  if (!memory || typeof memory !== 'object') return null;
  // 情况1：memory[extractor] 直接存在
  if (memory[extractor] !== undefined) return memory[extractor];
  // 情况2：memory 按章节分（数字键），每章下有 extractor
  var aggregated = {};
  var found = false;
  Object.keys(memory).forEach(function(k) {
    var ch = memory[k];
    if (ch && typeof ch === 'object' && ch[extractor] !== undefined) {
      var num = parseInt(k);
      var label = isNaN(num) ? k : ('第' + (num + 1) + '章');
      aggregated[label] = ch[extractor];
      found = true;
    }
  });
  return found ? aggregated : null;
}

// 工具：设置进度区内容
function _setDistillProgress(html, show) {
  var el = document.getElementById('distill-progress');
  if (!el) return;
  el.innerHTML = html;
  el.style.display = show ? 'block' : 'none';
}

// 工具：隐藏元素
function _hideEl(id) {
  var el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════
// 蒸馏面板 - 导入外部素材蒸馏功能
// ═══════════════════════════════════════════════════════════════

// 导入素材的缓存内容
var _distillImportState = {
  fileName: '',
  fileContent: '',
  loaded: false
};

// 展开/收起导入区域
function toggleDistillImportArea() {
  var area = document.getElementById('distill-import-area');
  var toggle = document.getElementById('distill-import-toggle');
  if (!area) return;
  var visible = area.style.display !== 'none';
  area.style.display = visible ? 'none' : 'block';
  if (toggle) toggle.textContent = visible ? '▼' : '▲';
  // 首次展开时绑定文件上传事件和填充章节下拉
  if (!visible) {
    _initDistillImportEvents();
    _populateDistillImportChapters();
  }
}

// 初始化文件上传事件（仅绑定一次）
var _distillImportEventsInit = false;
function _initDistillImportEvents() {
  if (_distillImportEventsInit) return;
  _distillImportEventsInit = true;

  var fileInput = document.getElementById('distill-file-input');
  var dropZone = document.getElementById('distill-file-drop');

  if (fileInput) {
    fileInput.addEventListener('change', function(e) {
      var files = e.target.files;
      if (files && files.length > 0) {
        if (files.length === 1) {
          _handleDistillFileLoad(files[0]);
        } else {
          // 断点3修复：批量导入多文件
          _handleBatchDistillFiles(files);
        }
      }
    });
  }
  if (dropZone) {
    dropZone.addEventListener('click', function() {
      if (fileInput) fileInput.click();
    });
    dropZone.addEventListener('dragover', function(e) {
      e.preventDefault();
      dropZone.style.borderColor = 'var(--accent)';
    });
    dropZone.addEventListener('dragleave', function() {
      dropZone.style.borderColor = 'var(--border)';
    });
    dropZone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropZone.style.borderColor = 'var(--border)';
      var files = e.dataTransfer.files;
      if (files && files.length > 0) {
        if (files.length === 1) {
          _handleDistillFileLoad(files[0]);
        } else {
          _handleBatchDistillFiles(files);
        }
      }
    });
  }
}

// 断点3修复：批量蒸馏多文件
function _handleBatchDistillFiles(files) {
  var fileArr = Array.prototype.slice.call(files);
  var info = document.getElementById('distill-file-info');
  if (info) {
    info.style.display = 'block';
    info.innerHTML = '<div style="font-weight:600;margin-bottom:4px">📋 批量导入 ' + fileArr.length + ' 个文件</div>'
      + fileArr.map(function(f, i) { return '<div>· ' + (i+1) + '. ' + f.name.replace(/</g, '&lt;') + ' (' + (f.size/1024).toFixed(1) + 'KB)</div>'; }).join('')
      + '<div style="margin-top:6px;color:var(--muted)">点击"蒸馏导入内容"将依次处理</div>';
  }
  // 依次读取所有文件内容并合并
  var allTexts = [];
  var processed = 0;
  fileArr.forEach(function(file, idx) {
    var reader = new FileReader();
    reader.onload = function(ev) {
      allTexts[idx] = { name: file.name, text: ev.target.result };
      processed++;
      if (processed === fileArr.length) {
        // 合并所有文本到预览区
        var preview = document.getElementById('distill-import-preview');
        if (preview) {
          preview.style.display = 'block';
          preview.value = allTexts.map(function(t) {
            return '=== ' + t.name + ' ===\n' + t.text;
          }).join('\n\n');
        }
        var importBtn = document.getElementById('distill-import-btn');
        if (importBtn) importBtn.disabled = false;
        _distillState.batchFiles = allTexts;
      }
    };
    reader.readAsText(file, 'UTF-8');
  });
}

// 填充目标章节下拉框
function _populateDistillImportChapters() {
  var select = document.getElementById('distill-import-target-chapter');
  if (!select) return;
  // 如果已经有章节选项（大于1个），说明已填充过
  if (select.options.length > 1) return;
  var chapters = _distillState.chapters;
  if (!chapters || !chapters.length) return;
  chapters.forEach(function(ch) {
    var opt = document.createElement('option');
    opt.value = ch.index;
    opt.textContent = '第' + (ch.index + 1) + '章 ' + (ch.title || '');
    select.appendChild(opt);
  });
}

// 处理文件加载
function _handleDistillFileLoad(file) {
  // 检查文件类型
  var ext = file.name.split('.').pop().toLowerCase();
  var allowed = ['txt', 'srt', 'vtt', 'json', 'csv'];
  if (allowed.indexOf(ext) === -1) {
    var infoEl = document.getElementById('distill-file-info');
    if (infoEl) {
      infoEl.style.display = 'block';
      infoEl.innerHTML = '<span class="text-danger">不支持的文件格式: .' + ext + '</span>';
    }
    return;
  }

  var reader = new FileReader();
  reader.onload = function(ev) {
    var text = ev.target.result;
    _distillImportState.fileName = file.name;
    _distillImportState.fileContent = text;
    _distillImportState.loaded = true;

    // 显示文件信息
    var infoEl = document.getElementById('distill-file-info');
    if (infoEl) {
      infoEl.style.display = 'block';
      infoEl.innerHTML = '文件: <strong>' + file.name.replace(/</g, '&lt;') + '</strong> | 大小: ' + (file.size / 1024).toFixed(1) + ' KB | 字符数: ' + text.length;
    }

    // 显示预览
    var preview = document.getElementById('distill-import-preview');
    if (preview) {
      preview.style.display = 'block';
      // 预览最多显示前2000字符
      preview.value = text.length > 2000 ? text.substring(0, 2000) + '\n\n... (共' + text.length + '字符，预览已截断)' : text;
    }

    // 启用蒸馏按钮
    var btn = document.getElementById('distill-import-btn');
    if (btn) btn.disabled = false;
  };
  reader.readAsText(file, 'UTF-8');
}

// 执行导入内容蒸馏
async function distillImportedFile() {
  if (!_distillImportState.loaded || !_distillImportState.fileContent) {
    showToast && showToast('请先上传文件');
    return;
  }

  var resultEl = document.getElementById('distill-import-result');
  var btn = document.getElementById('distill-import-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 蒸馏中...'; }
  if (resultEl) resultEl.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:4px">⏳ 正在将导入内容追加到章节并蒸馏...</div>';

  var targetChapter = -1;
  var select = document.getElementById('distill-import-target-chapter');
  if (select && select.value !== '-1') {
    targetChapter = parseInt(select.value);
  }

  try {
    // 如果选择了目标章节，先将内容追加到该章节
    if (targetChapter >= 0 && typeof saveChapter === 'function') {
      // 读取当前章节内容
      var chRes = await api('/api/chapter/load?index=' + targetChapter);
      var existingContent = '';
      if (chRes && chRes.ok !== false && chRes.content) {
        existingContent = chRes.content;
      }
      // 追加导入内容
      var newContent = existingContent + '\n\n---导入素材---\n' + _distillImportState.fileContent;
      await api('/api/chapter/save', {
        method: 'POST',
        body: JSON.stringify({index: targetChapter, content: newContent})
      });
    }

    // 调用蒸馏 API（对所有已勾选章节或目标章节）
    var chaptersToDistill = [];
    if (targetChapter >= 0) {
      chaptersToDistill = [targetChapter];
    } else {
      // 使用已勾选的章节
      chaptersToDistill = getSelectedDistillChapters();
    }

    if (chaptersToDistill.length === 0) {
      if (resultEl) resultEl.innerHTML = '<div style="font-size:11px;color:var(--warn);padding:4px">⚠️ 未选择目标章节且无勾选章节</div>';
      if (btn) { btn.disabled = false; btn.textContent = '🧪 蒸馏导入内容'; }
      return;
    }

    var extractors = getSelectedDistillExtractors();
    var r = await api('/api/distill/chapters', {
      method: 'POST',
      body: JSON.stringify({
        chapter_indices: chaptersToDistill,
        options: {extractors: extractors}
      })
    });

    if (r && r.ok !== false) {
      var extracted = r.extracted || {};
      var summary = Object.keys(extracted).map(function(k) {
        var ex = _DISTILL_EXTRACTORS.filter(function(e) { return e.key === k; })[0];
        return (ex ? ex.label : k) + ': ' + extracted[k] + '条';
      }).join('，');
      if (resultEl) resultEl.innerHTML = '<div style="padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px;color:var(--success, #10b981)">✅ 蒸馏完成！' + summary + '</div>';
      // 刷新章节蒸馏状态
      await loadDistillStatus();
    } else {
      if (resultEl) resultEl.innerHTML = '<div class="text-sm-danger">❌ 蒸馏失败: ' + ((r && r.error) || '未知错误').replace(/</g, '&lt;') + '</div>';
    }
  } catch(e) {
    if (resultEl) resultEl.innerHTML = '<div class="text-sm-danger">❌ 请求异常: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }

  if (btn) { btn.disabled = false; btn.textContent = '🧪 蒸馏导入内容'; }
}

// 清除导入内容
function clearDistillImport() {
  _distillImportState = {fileName: '', fileContent: '', loaded: false};
  var fileInput = document.getElementById('distill-file-input');
  if (fileInput) fileInput.value = '';
  var fileInfo = document.getElementById('distill-file-info');
  if (fileInfo) fileInfo.style.display = 'none';
  var preview = document.getElementById('distill-import-preview');
  if (preview) { preview.value = ''; preview.style.display = 'none'; }
  var btn = document.getElementById('distill-import-btn');
  if (btn) btn.disabled = true;
  var result = document.getElementById('distill-import-result');
  if (result) result.textContent = '';
}
