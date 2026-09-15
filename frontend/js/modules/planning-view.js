// ═══════════════════════════════════════════════════════════════════
// 规划可视化模块 - Grid 拖拽排序 / Matrix 全景矩阵 / Timeline 时间线
// 参考 NovelCrafter 的 Grid 拖拽、Matrix 鸟瞰、Scene Labels、自定义 POV
// 原生 JS，无框架依赖，使用项目已有 CSS 变量
// ═══════════════════════════════════════════════════════════════════

var PlanningView = (function() {
  'use strict';

  // ── 内部状态 ──
  var _currentView = 'grid';        // grid / matrix / timeline
  var _matrixData = null;            // 缓存矩阵数据
  var _timelineData = null;          // 缓存时间线数据
  var _dragState = {
    draggingEl: null,
    fromIndex: -1,
    fromVol: -1
  };

  // 状态标签映射
  var STATUS_MAP = {
    'draft':   { label: '草稿',   color: '#95a5a6', bg: 'rgba(149,165,166,0.15)' },
    'revised': { label: '修订',   color: '#f39c12', bg: 'rgba(243,156,18,0.15)' },
    'final':   { label: '定稿',   color: '#27ae60', bg: 'rgba(39,174,96,0.15)' }
  };

  // 时间线节点颜色
  var TIMELINE_COLORS = {
    'character':  '#3498db',   // 角色出场 - 蓝
    'foreshadow': '#2ecc71',   // 伏笔埋设 - 绿
    'recovered':  '#f1c40f',   // 伏笔回收 - 金
    'conflict':   '#e74c3c'    // 冲突点 - 红
  };

  // ── 公共 API ──

  /**
   * 打开规划视图覆盖层
   */
  function open(view) {
    var overlay = document.getElementById('planning-overlay');
    if (!overlay) {
      console.error('[PlanningView] planning-overlay 元素不存在');
      return;
    }
    overlay.style.display = 'flex';
    // 默认显示 grid 视图
    _currentView = view || 'grid';
    _switchView(_currentView);
  }

  /**
   * 关闭规划视图覆盖层
   */
  function close() {
    var overlay = document.getElementById('planning-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  /**
   * 切换视图
   */
  function _switchView(view) {
    _currentView = view;
    // 更新标签页高亮
    var tabs = document.querySelectorAll('.planning-tab-btn');
    tabs.forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.view === view);
    });
    // 显示对应容器
    var containers = ['planning-grid-view', 'planning-matrix-view', 'planning-timeline-view'];
    containers.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    var target = document.getElementById('planning-' + view + '-view');
    if (target) target.style.display = 'block';

    // 加载数据
    if (view === 'grid') {
      _renderGrid();
    } else if (view === 'matrix') {
      _loadAndRenderMatrix();
    } else if (view === 'timeline') {
      _loadAndRenderTimeline();
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // A. Grid 拖拽视图
  // ═══════════════════════════════════════════════════════════════════

  function _renderGrid() {
    var container = document.getElementById('planning-grid-view');
    if (!container) return;

    // 使用全局 chapters 和 volumes 数据
    var chapters = _getChaptersData();
    var volumes = _getVolumesData();

    if (!chapters || chapters.length === 0) {
      container.innerHTML = '<div style="text-align:center;padding:60px 20px;color:var(--muted);font-size:14px">'
        + '📋 暂无章节<br><span class="text-md">请先在"章节大纲"步骤创建章节</span></div>';
      return;
    }

    // 构建 vol → chapters 映射
    var volChaptersMap = _buildVolChaptersMap(chapters, volumes);

    var html = '';
    html += '<div style="margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
      + '<span style="font-size:13px;color:var(--muted)">拖拽卡片可重排章节顺序，双击卡片跳转编辑</span>'
      + '<span style="font-size:11px;padding:3px 10px;border:1px solid var(--border);border-radius:10px;color:var(--muted)">共 ' + chapters.length + ' 章</span>'
      + '</div>';

    // 按卷分组渲染
    if (volumes && volumes.length > 0) {
      volumes.forEach(function(vol, volIdx) {
        var volChapters = volChaptersMap[vol.index] || [];
        html += _renderVolumeSection(vol, volChapters, volIdx);
      });
    } else {
      // 无卷结构，全部放一个默认分组
      html += _renderVolumeSection({ index: 0, title: '全部章节' }, chapters, 0);
    }

    container.innerHTML = html;

    // 绑定拖拽事件
    _bindDragEvents(container);
    // 绑定下拉事件
    _bindDropdownEvents(container);
    // 绑定双击事件
    _bindDblClickEvents(container);
  }

  function _renderVolumeSection(vol, volChapters, volIdx) {
    var html = '';
    html += '<div class="planning-vol-section" data-vol-index="' + (vol.index || 0) + '" style="margin-bottom:24px">'
      + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid var(--accent)">'
      + '<span style="font-size:16px;font-weight:700;color:var(--accent);font-family:var(--display)">' + _esc(vol.title || '未命名卷') + '</span>'
      + '<span style="font-size:11px;padding:2px 8px;border:1px solid var(--border);border-radius:10px;color:var(--muted)">' + volChapters.length + ' 章</span>'
      + '</div>'
      + '<div class="planning-card-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;min-height:60px">';

    volChapters.forEach(function(ch) {
      html += _renderChapterCard(ch, vol.index || 0);
    });

    if (volChapters.length === 0) {
      html += '<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--muted);font-size:12px;border:1px dashed var(--border);border-radius:var(--radius-sm)">本卷暂无章节，拖拽卡片到此</div>';
    }

    html += '</div></div>';
    return html;
  }

  function _renderChapterCard(ch, volIndex) {
    var status = ch.status || 'draft';
    var statusInfo = STATUS_MAP[status] || STATUS_MAP['draft'];
    var pov = ch.pov || '';
    var sceneLabels = ch.scene_labels || [];
    var wordCount = ch.word_count || 0;
    var globalIdx = (typeof ch._globalIndex !== 'undefined') ? ch._globalIndex : -1;

    var html = '';
    html += '<div class="planning-chapter-card" draggable="true" data-chapter-index="' + globalIdx + '" data-vol-index="' + volIndex + '" '
      + 'style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;cursor:grab;transition:all 0.2s;position:relative" '
      + 'onmouseenter="this.style.borderColor=\'var(--accent)\';this.style.boxShadow=\'0 2px 8px rgba(0,0,0,0.15)\'" '
      + 'onmouseleave="this.style.borderColor=\'var(--border)\';this.style.boxShadow=\'none\'">';

    // 顶部：章节序号 + 标题
    html += '<div style="display:flex;align-items:flex-start;gap:6px;margin-bottom:6px">'
      + '<span style="font-size:11px;color:var(--muted);background:var(--bg);padding:1px 6px;border-radius:4px;flex-shrink:0">第' + (globalIdx >= 0 ? globalIdx + 1 : '?') + '章</span>'
      + '<span style="font-size:13px;font-weight:600;color:var(--ink);flex:1;word-break:break-all;line-height:1.4">' + _esc(ch.title || '未命名') + '</span>'
      + '</div>';

    // 字数
    html += '<div style="font-size:11px;color:var(--muted);margin-bottom:8px">📝 ' + wordCount.toLocaleString() + ' 字</div>';

    // 场景标签
    if (sceneLabels.length > 0) {
      html += '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:8px">';
      sceneLabels.forEach(function(label) {
        html += '<span style="font-size:10px;padding:1px 6px;background:var(--accent-soft);color:var(--accent);border-radius:8px">' + _esc(label) + '</span>';
      });
      html += '</div>';
    }

    // 状态下拉
    html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
      + '<span style="font-size:10px;color:var(--muted);flex-shrink:0">状态</span>'
      + '<select class="planning-status-select" data-chapter-index="' + globalIdx + '" style="flex:1;padding:2px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:' + statusInfo.color + ';font-size:11px;cursor:pointer;font-family:var(--sans)">';
    Object.keys(STATUS_MAP).forEach(function(key) {
      html += '<option value="' + key + '"' + (key === status ? ' selected' : '') + '>' + STATUS_MAP[key].label + '</option>';
    });
    html += '</select></div>';

    // POV 下拉
    html += '<div class="flex-center-xs">'
      + '<span style="font-size:10px;color:var(--muted);flex-shrink:0">POV</span>'
      + '<input type="text" class="planning-pov-input" data-chapter-index="' + globalIdx + '" value="' + _esc(pov) + '" placeholder="默认/角色名" '
      + 'style="flex:1;padding:2px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px;font-family:var(--sans)" '
      + 'onclick="event.stopPropagation()" onchange="event.stopPropagation()">'
      + '</div>';

    // 状态色条（左侧）
    html += '<div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:' + statusInfo.color + ';border-radius:var(--radius-sm) 0 0 var(--radius-sm)"></div>';

    html += '</div>';
    return html;
  }

  // ── 拖拽事件绑定 ──

  function _bindDragEvents(container) {
    var cards = container.querySelectorAll('.planning-chapter-card');
    cards.forEach(function(card) {
      card.addEventListener('dragstart', _onDragStart);
      card.addEventListener('dragend', _onDragEnd);
      card.addEventListener('dragover', _onDragOver);
      card.addEventListener('drop', _onDrop);
    });

    // 卷容器也接受 drop（拖到空白处）
    var grids = container.querySelectorAll('.planning-card-grid');
    grids.forEach(function(grid) {
      grid.addEventListener('dragover', _onDragOver);
      grid.addEventListener('drop', _onDrop);
    });
  }

  function _onDragStart(e) {
    var card = e.target.closest('.planning-chapter-card');
    if (!card) return;
    _dragState.draggingEl = card;
    _dragState.fromIndex = parseInt(card.dataset.chapterIndex);
    _dragState.fromVol = parseInt(card.dataset.volIndex);
    card.style.opacity = '0.5';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(_dragState.fromIndex));
  }

  function _onDragEnd(e) {
    var card = e.target.closest('.planning-chapter-card');
    if (card) card.style.opacity = '1';
    // 清除所有 drag-over 样式
    document.querySelectorAll('.planning-chapter-card').forEach(function(c) {
      c.style.borderTop = '';
      c.style.borderBottom = '';
    });
    _dragState.draggingEl = null;
  }

  function _onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    var target = e.target.closest('.planning-chapter-card');
    if (target && target !== _dragState.draggingEl) {
      // 视觉提示：在目标卡片上方/下方显示插入线
      var rect = target.getBoundingClientRect();
      var midY = rect.top + rect.height / 2;
      document.querySelectorAll('.planning-chapter-card').forEach(function(c) {
        c.style.borderTop = '';
        c.style.borderBottom = '';
      });
      if (e.clientY < midY) {
        target.style.borderTop = '3px solid var(--accent)';
      } else {
        target.style.borderBottom = '3px solid var(--accent)';
      }
    }
  }

  function _onDrop(e) {
    e.preventDefault();
    if (_dragState.fromIndex < 0) return;

    var target = e.target.closest('.planning-chapter-card');
    var toIndex = -1;
    var toVol = _dragState.fromVol;

    if (target) {
      toIndex = parseInt(target.dataset.chapterIndex);
      toVol = parseInt(target.dataset.volIndex);
      // 判断插入到目标的前面还是后面
      var rect = target.getBoundingClientRect();
      var midY = rect.top + rect.height / 2;
      if (e.clientY >= midY) {
        toIndex = toIndex + 1; // 插入到后面
      }
    } else {
      // 拖到空白区域：追加到该卷末尾
      var grid = e.target.closest('.planning-card-grid');
      if (grid) {
        var volSection = grid.closest('.planning-vol-section');
        if (volSection) {
          toVol = parseInt(volSection.dataset.volIndex);
        }
      }
      // 追加到末尾
      var chapters = _getChaptersData();
      toIndex = chapters.length;
    }

    // 清除视觉提示
    document.querySelectorAll('.planning-chapter-card').forEach(function(c) {
      c.style.borderTop = '';
      c.style.borderBottom = '';
    });

    // 如果目标位置和源位置相同，不操作
    if (toIndex === _dragState.fromIndex || toIndex === _dragState.fromIndex + 1) {
      _dragState.fromIndex = -1;
      return;
    }

    // 调用后端 API 持久化重排
    _reorderChapter(_dragState.fromIndex, toIndex, _dragState.fromVol, toVol);
    _dragState.fromIndex = -1;
  }

  async function _reorderChapter(fromIndex, toIndex, fromVol, toVol) {
    if (typeof showToast === 'function') showToast('⏳ 正在重排章节...');
    try {
      var r = await api('/api/chapter/reorder', {
        method: 'POST',
        body: JSON.stringify({
          from_index: fromIndex,
          to_index: toIndex,
          from_vol: fromVol,
          to_vol: toVol
        })
      });
      if (r.ok) {
        // 更新全局 chapters 数据
        if (r.chapters) {
          _setChaptersData(r.chapters);
        }
        if (typeof showToast === 'function') showToast('✅ 章节顺序已更新');
        // 重新渲染 grid
        _renderGrid();
        // 刷新左侧章节列表
        if (typeof renderChapterList === 'function') renderChapterList();
        if (typeof loadVolumesData === 'function') loadVolumesData();
      } else {
        if (typeof showToast === 'function') showToast('❌ 重排失败: ' + (r.error || '未知错误'));
        _renderGrid(); // 回滚 UI
      }
    } catch(e) {
      console.error('[PlanningView] reorder error:', e);
      if (typeof showToast === 'function') showToast('❌ 重排失败: ' + e.message);
      _renderGrid();
    }
  }

  // ── 下拉/输入事件绑定 ──

  function _bindDropdownEvents(container) {
    // 状态下拉
    var statusSelects = container.querySelectorAll('.planning-status-select');
    statusSelects.forEach(function(sel) {
      sel.addEventListener('change', async function(e) {
        e.stopPropagation();
        var idx = parseInt(this.dataset.chapterIndex);
        var status = this.value;
        await _updateChapterStatus(idx, status);
      });
      sel.addEventListener('click', function(e) { e.stopPropagation(); });
    });

    // POV 输入
    var povInputs = container.querySelectorAll('.planning-pov-input');
    povInputs.forEach(function(inp) {
      inp.addEventListener('change', async function(e) {
        e.stopPropagation();
        var idx = parseInt(this.dataset.chapterIndex);
        var pov = this.value.trim();
        await _updateChapterPov(idx, pov);
      });
      inp.addEventListener('click', function(e) { e.stopPropagation(); });
    });
  }

  async function _updateChapterStatus(idx, status) {
    try {
      var r = await api('/api/chapter/' + idx + '/status', {
        method: 'POST',
        body: JSON.stringify({ status: status })
      });
      if (r.ok) {
        // 更新本地数据
        var chs = _getChaptersData();
        if (chs && chs[idx]) {
          chs[idx].status = status;
        }
        if (typeof showToast === 'function') showToast('✅ 状态已更新为: ' + (STATUS_MAP[status] ? STATUS_MAP[status].label : status));
        // 局部刷新卡片颜色
        _refreshCardStatus(idx, status);
      } else {
        if (typeof showToast === 'function') showToast('❌ 状态更新失败: ' + (r.error || ''));
      }
    } catch(e) {
      if (typeof showToast === 'function') showToast('❌ 状态更新失败: ' + e.message);
    }
  }

  function _refreshCardStatus(idx, status) {
    var card = document.querySelector('.planning-chapter-card[data-chapter-index="' + idx + '"]');
    if (!card) return;
    var statusInfo = STATUS_MAP[status] || STATUS_MAP['draft'];
    // 更新色条
    var bar = card.querySelector('div[style*="position:absolute;left:0"]');
    if (bar) bar.style.background = statusInfo.color;
    // 更新下拉文字颜色
    var sel = card.querySelector('.planning-status-select');
    if (sel) sel.style.color = statusInfo.color;
  }

  async function _updateChapterPov(idx, pov) {
    try {
      var r = await api('/api/chapter/' + idx + '/pov', {
        method: 'POST',
        body: JSON.stringify({ pov: pov })
      });
      if (r.ok) {
        var chs = _getChaptersData();
        if (chs && chs[idx]) {
          chs[idx].pov = pov;
        }
        if (typeof showToast === 'function') showToast('✅ POV 已设置为: ' + (pov || '默认'));
      } else {
        if (typeof showToast === 'function') showToast('❌ POV 更新失败: ' + (r.error || ''));
      }
    } catch(e) {
      if (typeof showToast === 'function') showToast('❌ POV 更新失败: ' + e.message);
    }
  }

  // ── 双击跳转编辑 ──

  function _bindDblClickEvents(container) {
    var cards = container.querySelectorAll('.planning-chapter-card');
    cards.forEach(function(card) {
      card.addEventListener('dblclick', function(e) {
        var idx = parseInt(this.dataset.chapterIndex);
        if (idx >= 0) {
          _jumpToChapter(idx);
        }
      });
    });
  }

  function _jumpToChapter(idx) {
    // 关闭规划覆盖层
    close();
    // 切换到写作步骤
    if (typeof goToStep === 'function') goToStep(STEPS.章节大纲);
    // 加载章节内容
    try {
      if (typeof currentChapterIndex !== 'undefined') {
        currentChapterIndex = idx;
      }
    } catch(e) {}
    try {
      window.currentChapterIndex = idx;
    } catch(e) {}
    if (typeof loadChapterContentAPI === 'function') {
      loadChapterContentAPI(idx);
    }
    if (typeof showToast === 'function') showToast('📖 已跳转到第' + (idx + 1) + '章');
  }

  // ═══════════════════════════════════════════════════════════════════
  // B. Matrix 全景矩阵视图
  // ═══════════════════════════════════════════════════════════════════

  async function _loadAndRenderMatrix() {
    var container = document.getElementById('planning-matrix-view');
    if (!container) return;
    container.innerHTML = '<div class="empty-state-lg-alt">⏳ 加载矩阵数据...</div>';

    try {
      var r = await api('/api/planning/matrix');
      if (!r.ok) {
        container.innerHTML = '<div class="empty-danger-lg">加载失败: ' + (r.error || '未知错误') + '</div>';
        return;
      }
      _matrixData = r;
      _renderMatrix(container, r);
    } catch(e) {
      container.innerHTML = '<div class="empty-danger-lg">加载失败: ' + e.message + '</div>';
    }
  }

  function _renderMatrix(container, data) {
    var volumes = data.volumes || [];
    var chapters = data.chapters || [];
    var stats = data.stats || {};

    if (chapters.length === 0) {
      container.innerHTML = '<div class="empty-state-xl">📊 暂无章节数据</div>';
      return;
    }

    // 按卷分组章节
    var volChaptersMap = {};
    volumes.forEach(function(vol) {
      volChaptersMap[vol.index] = [];
    });
    chapters.forEach(function(ch) {
      // 找到该章节属于哪个卷
      var volIdx = _findChapterVolume(ch, volumes);
      if (!volChaptersMap[volIdx]) volChaptersMap[volIdx] = [];
      volChaptersMap[volIdx].push(ch);
    });

    var html = '';

    // 统计栏
    html += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm)">';
    html += _statChip('总章数', stats.total_chapters || 0, '📖', 'var(--accent)');
    html += _statChip('总字数', (stats.total_words || 0).toLocaleString(), '📝', 'var(--accent)');
    html += _statChip('平均字数', (stats.avg_words || 0).toLocaleString(), '📊', 'var(--accent)');
    var statusDist = stats.status_distribution || {};
    html += _statChip('草稿', statusDist.draft || 0, '●', STATUS_MAP.draft.color);
    html += _statChip('修订', statusDist.revised || 0, '●', STATUS_MAP.revised.color);
    html += _statChip('定稿', statusDist.final || 0, '●', STATUS_MAP.final.color);
    html += '</div>';

    // 矩阵表格
    html += '<div style="overflow-x:auto">';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px">';

    // 表头：卷标题
    html += '<thead><tr style="background:var(--surface)">';
    html += '<th style="padding:8px 10px;border:1px solid var(--border);text-align:left;color:var(--muted);font-weight:600;white-space:nowrap;width:120px">卷 / 章节</th>';
    // 找到最大章节数的卷，作为列数
    var maxChapters = 0;
    volumes.forEach(function(vol) {
      var cnt = (volChaptersMap[vol.index] || []).length;
      if (cnt > maxChapters) maxChapters = cnt;
    });
    for (var i = 0; i < maxChapters; i++) {
      html += '<th style="padding:6px 4px;border:1px solid var(--border);text-align:center;color:var(--muted);font-weight:400;min-width:80px">' + (i + 1) + '</th>';
    }
    html += '</tr></thead>';

    // 表体：每卷一行
    html += '<tbody>';
    volumes.forEach(function(vol) {
      var volChs = volChaptersMap[vol.index] || [];
      html += '<tr>';
      // 卷标题（可点击编辑）
      html += '<td style="padding:8px 10px;border:1px solid var(--border);background:var(--surface);cursor:pointer" '
        + 'onclick="PlanningView.editVolumeTitle(' + vol.index + ', this)" '
        + 'title="点击编辑卷标题">'
        + '<div style="font-weight:600;color:var(--accent);font-size:13px">' + _esc(vol.title || '未命名') + '</div>'
        + '<div class="text-xs text-muted">' + volChs.length + ' 章</div>'
        + '</td>';
      // 章节单元格
      for (var j = 0; j < maxChapters; j++) {
        if (j < volChs.length) {
          var ch = volChs[j];
          var statusInfo = STATUS_MAP[ch.status] || STATUS_MAP['draft'];
          html += '<td style="padding:4px;border:1px solid var(--border);cursor:pointer;text-align:center;vertical-align:top" '
            + 'onclick="PlanningView.jumpToChapter(' + ch.index + ')" '
            + 'onmouseenter="this.style.background=\'var(--accent-soft)\'" '
            + 'onmouseleave="this.style.background=\'\'" '
            + 'title="' + _esc(ch.title) + ' | ' + ch.word_count + '字 | ' + statusInfo.label + (ch.pov ? ' | POV:' + ch.pov : '') + '">'
            + '<div style="font-size:11px;color:var(--ink);line-height:1.3;margin-bottom:3px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + _esc(ch.title) + '</div>'
            + '<div class="text-xs text-muted">' + (ch.word_count || 0) + '字</div>'
            + '<div style="width:100%;height:3px;border-radius:2px;background:' + statusInfo.color + ';margin-top:3px"></div>'
            + '</td>';
        } else {
          html += '<td style="border:1px solid var(--border);background:var(--bg)"></td>';
        }
      }
      html += '</tr>';
    });
    html += '</tbody></table></div>';

    container.innerHTML = html;
  }

  function _statChip(label, value, icon, color) {
    return '<div style="display:flex;align-items:center;gap:4px;padding:4px 10px;background:var(--bg);border-radius:var(--radius-sm);border:1px solid var(--border-soft)">'
      + '<span style="color:' + color + ';font-size:14px">' + icon + '</span>'
      + '<span class="text-md text-muted">' + label + '</span>'
      + '<span style="font-size:13px;font-weight:700;color:var(--ink)">' + value + '</span>'
      + '</div>';
  }

  function editVolumeTitle(volIndex, tdEl) {
    var titleDiv = tdEl.querySelector('div');
    if (!titleDiv) return;
    var oldTitle = titleDiv.textContent.replace(/\s+章$/, '').trim();
    var newTitle = prompt('编辑卷标题:', oldTitle);
    if (newTitle && newTitle.trim() && newTitle !== oldTitle) {
      _renameVolume(volIndex, newTitle.trim());
    }
  }

  async function _renameVolume(volIndex, newTitle) {
    try {
      var r = await api('/api/project/volume/rename', {
        method: 'POST',
        body: JSON.stringify({ vol_index: volIndex, title: newTitle })
      });
      if (r.ok) {
        if (typeof showToast === 'function') showToast('✅ 卷标题已更新');
        _loadAndRenderMatrix();
      } else {
        if (typeof showToast === 'function') showToast('❌ 更新失败: ' + (r.error || ''));
      }
    } catch(e) {
      if (typeof showToast === 'function') showToast('❌ 更新失败: ' + e.message);
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // C. Timeline 时间线视图
  // ═══════════════════════════════════════════════════════════════════

  async function _loadAndRenderTimeline() {
    var container = document.getElementById('planning-timeline-view');
    if (!container) return;
    container.innerHTML = '<div class="empty-state-lg-alt">⏳ 加载时间线数据...</div>';

    try {
      var r = await api('/api/planning/timeline');
      if (!r.ok) {
        container.innerHTML = '<div class="empty-danger-lg">加载失败: ' + (r.error || '未知错误') + '</div>';
        return;
      }
      _timelineData = r;
      _renderTimeline(container, r);
    } catch(e) {
      container.innerHTML = '<div class="empty-danger-lg">加载失败: ' + e.message + '</div>';
    }
  }

  function _renderTimeline(container, data) {
    var chapters = data.chapters || [];
    var characters = data.characters || [];
    var foreshadowing = data.foreshadowing || [];

    if (chapters.length === 0) {
      container.innerHTML = '<div class="empty-state-xl">📅 暂无章节数据</div>';
      return;
    }

    var totalChapters = chapters.length;

    // 收集所有需要显示的行
    // 行类型：角色出场(蓝) / 伏笔埋设(绿) / 伏笔回收(金) / 冲突点(红)
    var rows = [];

    // 角色行
    characters.forEach(function(c) {
      if (c.name) {
        rows.push({
          type: 'character',
          name: c.name,
          label: c.name + (c.is_alive ? '' : ' (已故)'),
          color: TIMELINE_COLORS.character,
          markers: _getCharacterMarkers(c, chapters, foreshadowing)
        });
      }
    });

    // 伏笔行
    foreshadowing.forEach(function(h) {
      var markers = [];
      if (h.planted_chapter) {
        markers.push({
          chapter: h.planted_chapter,
          type: 'foreshadow',
          color: TIMELINE_COLORS.foreshadow,
          label: '埋设: ' + (h.content || '').substring(0, 30)
        });
      }
      if (h.status === 'recovered' && h.expected_recovery_chapter) {
        markers.push({
          chapter: h.expected_recovery_chapter,
          type: 'recovered',
          color: TIMELINE_COLORS.recovered,
          label: '回收: ' + (h.content || '').substring(0, 30)
        });
      }
      if (markers.length > 0) {
        rows.push({
          type: 'foreshadow',
          name: h.id,
          label: '🔮 ' + (h.content || h.id).substring(0, 20),
          color: TIMELINE_COLORS.foreshadow,
          markers: markers
        });
      }
    });

    if (rows.length === 0) {
      container.innerHTML = '<div class="empty-state-xl">'
        + '📅 暂无角色/伏笔数据<br><span class="text-md">请在写作过程中通过蒸馏或检查功能积累角色状态和伏笔数据</span></div>';
      return;
    }

    // 渲染图例
    var html = '';
    html += '<div style="margin-bottom:16px;display:flex;gap:16px;flex-wrap:wrap;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm)">';
    html += '<div class="flex-center-xs"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + TIMELINE_COLORS.character + '"></span><span class="text-sm text-muted">角色出场</span></div>';
    html += '<div class="flex-center-xs"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + TIMELINE_COLORS.foreshadow + '"></span><span class="text-sm text-muted">伏笔埋设</span></div>';
    html += '<div class="flex-center-xs"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + TIMELINE_COLORS.recovered + '"></span><span class="text-sm text-muted">伏笔回收</span></div>';
    html += '<div class="flex-center-xs"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + TIMELINE_COLORS.conflict + '"></span><span class="text-sm text-muted">冲突点</span></div>';
    html += '</div>';

    // 渲染时间线网格
    var labelWidth = 140;
    var chapterColWidth = Math.max(40, Math.min(80, Math.floor(1200 / totalChapters)));

    html += '<div style="overflow-x:auto">';
    html += '<table style="border-collapse:collapse;font-size:11px;min-width:' + (labelWidth + totalChapters * chapterColWidth) + 'px">';

    // 表头：章节序号
    html += '<thead><tr style="background:var(--surface)">';
    html += '<th style="padding:6px 8px;border:1px solid var(--border);text-align:left;color:var(--muted);font-weight:600;width:' + labelWidth + 'px;position:sticky;left:0;z-index:2;background:var(--surface)">角色 / 伏笔</th>';
    for (var i = 0; i < totalChapters; i++) {
      var ch = chapters[i];
      html += '<th style="padding:4px 2px;border:1px solid var(--border);text-align:center;color:var(--muted);font-weight:400;min-width:' + chapterColWidth + 'px;max-width:' + chapterColWidth + 'px" title="' + _esc(ch.title || '') + '">'
        + '<div style="font-size:10px">' + (i + 1) + '</div>'
        + '</th>';
    }
    html += '</tr></thead>';

    // 表体：每行一个角色/伏笔
    html += '<tbody>';
    rows.forEach(function(row) {
      html += '<tr>';
      html += '<td style="padding:6px 8px;border:1px solid var(--border);background:var(--surface);color:var(--ink);font-weight:500;position:sticky;left:0;z-index:1;max-width:' + labelWidth + 'px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + _esc(row.label) + '">'
        + '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:' + row.color + ';margin-right:4px"></span>'
        + _esc(row.label)
        + '</td>';
      for (var j = 0; j < totalChapters; j++) {
        var chapterNum = j + 1;
        var marker = _findMarkerAtChapter(row.markers, chapterNum);
        if (marker) {
          html += '<td style="padding:2px;border:1px solid var(--border);text-align:center;cursor:pointer" '
            + 'onclick="PlanningView.jumpToChapter(' + j + ')" '
            + 'title="' + _esc(marker.label) + '">'
            + '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:' + marker.color + ';border:2px solid var(--surface);box-shadow:0 0 4px ' + marker.color + '"></span>'
            + '</td>';
        } else {
          html += '<td style="padding:2px;border:1px solid var(--border);text-align:center">'
            + '<span style="display:inline-block;width:4px;height:4px;border-radius:50%;background:var(--border-soft)"></span>'
            + '</td>';
        }
      }
      html += '</tr>';
    });
    html += '</tbody></table></div>';

    container.innerHTML = html;
  }

  function _getCharacterMarkers(character, chapters, foreshadowing) {
    var markers = [];
    // 角色 last_seen_chapter 作为出场标记
    var lastSeen = character.last_seen_chapter || 0;
    if (lastSeen > 0) {
      markers.push({
        chapter: lastSeen,
        type: 'character',
        color: TIMELINE_COLORS.character,
        label: character.name + ' 最后出场于第' + lastSeen + '章' + (character.location ? ' @ ' + character.location : '')
      });
    }
    // 检查与该角色相关的伏笔
    foreshadowing.forEach(function(h) {
      if (h.related_characters && h.related_characters.indexOf(character.name) >= 0) {
        if (h.planted_chapter) {
          markers.push({
            chapter: h.planted_chapter,
            type: 'foreshadow',
            color: TIMELINE_COLORS.foreshadow,
            label: character.name + ' 相关伏笔埋设: ' + (h.content || '').substring(0, 30)
          });
        }
      }
    });
    return markers;
  }

  function _findMarkerAtChapter(markers, chapterNum) {
    for (var i = 0; i < markers.length; i++) {
      if (markers[i].chapter === chapterNum) {
        return markers[i];
      }
    }
    return null;
  }

  // ═══════════════════════════════════════════════════════════════════
  // 辅助函数
  // ═══════════════════════════════════════════════════════════════════

  function _esc(text) {
    if (!text) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function _getChaptersData() {
    // 尝试从全局获取 chapters 数据
    try {
      if (typeof chapters !== 'undefined' && chapters && chapters.length > 0) {
        return chapters;
      }
    } catch(e) {}
    try {
      if (typeof window.chapters !== 'undefined' && window.chapters) {
        return window.chapters;
      }
    } catch(e) {}
    return [];
  }

  function _setChaptersData(newChapters) {
    // 同步更新全局 chapters 变量
    try {
      if (typeof chapters !== 'undefined') {
        chapters = newChapters;
      }
    } catch(e) {}
    try {
      window.chapters = newChapters;
    } catch(e) {}
  }

  function _getVolumesData() {
    // 尝试从全局获取 volumes 数据
    try {
      if (typeof volumesData !== 'undefined' && volumesData && volumesData.length > 0) {
        return volumesData;
      }
    } catch(e) {}
    try {
      if (typeof window._volumesData !== 'undefined' && window._volumesData) {
        return window._volumesData;
      }
    } catch(e) {}
    try {
      if (typeof window.projectMeta !== 'undefined' && window.projectMeta && window.projectMeta.volumes) {
        return window.projectMeta.volumes;
      }
    } catch(e) {}
    return [];
  }

  function _buildVolChaptersMap(chapters, volumes) {
    var map = {};
    if (!volumes || volumes.length === 0) {
      map[0] = chapters.map(function(ch, i) {
        ch._globalIndex = i;
        return ch;
      });
      return map;
    }

    // 初始化
    volumes.forEach(function(vol) {
      map[vol.index] = [];
    });

    // 根据 volumes 中的 chapters 列表分配
    chapters.forEach(function(ch, i) {
      ch._globalIndex = i; // 保存全局下标
      var chIdx = ch.index || (i + 1);
      var assigned = false;
      volumes.forEach(function(vol) {
        var volChList = vol.chapters || [];
        if (volChList.indexOf(chIdx) >= 0) {
          map[vol.index].push(ch);
          assigned = true;
        }
      });
      if (!assigned) {
        // 未分配的章节放到第一个卷
        if (volumes.length > 0) {
          map[volumes[0].index].push(ch);
        } else {
          if (!map[0]) map[0] = [];
          map[0].push(ch);
        }
      }
    });
    return map;
  }

  function _findChapterVolume(ch, volumes) {
    var chIdx = ch.chapter_index || (ch.index + 1);
    for (var i = 0; i < volumes.length; i++) {
      var volChList = volumes[i].chapters || [];
      if (volChList.indexOf(chIdx) >= 0) {
        return volumes[i].index;
      }
    }
    return volumes.length > 0 ? volumes[0].index : 0;
  }

  // ── 暴露公共 API ──
  return {
    open: open,
    close: close,
    switchView: _switchView,
    jumpToChapter: _jumpToChapter,
    editVolumeTitle: editVolumeTitle,
    refreshGrid: _renderGrid,
    refreshMatrix: _loadAndRenderMatrix,
    refreshTimeline: _loadAndRenderTimeline
  };
})();

// ── 全局便捷函数（供 onclick 调用）──
function openPlanningPanel(view) {
  PlanningView.open(view);
}
function closePlanningPanel() {
  PlanningView.close();
}
function switchPlanningView(view) {
  PlanningView.switchView(view);
}
