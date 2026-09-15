(function() {
  'use strict';

/* ===== Workflow Step Navigation ===== */
window.currentWorkflowStep = 1;
window.TOTAL_STEPS = 9;

// 全局函数：加载指定章节的大纲
window.loadChapterOutline = function(idx) {
  // 切换章节前先保存当前章节的大纲
  if (typeof currentChapterIndex !== 'undefined' && currentChapterIndex !== idx && typeof saveChapterOutline === 'function') {
    try { saveChapterOutline(true); } catch(e) { console.warn('auto-save outline before switch failed:', e); }
  }
  currentChapterIndex = idx;
  // 切换章节时必须清空全局蓝图和建议，防止上一章数据残留
  window._currentBlueprint = null;
  window._aiSuggestions = [];
  // 加载已保存的蓝图（如果存在）
  if (typeof chapters !== 'undefined' && chapters && idx >= 0 && chapters[idx] && chapters[idx].blueprint) {
    window._currentBlueprint = chapters[idx].blueprint;
  }
  // 先从本地chapters数组尝试读取
  if (typeof chapters !== 'undefined' && chapters && idx >= 0 && chapters[idx]) {
    var chOutlineData = chapters[idx].outline;
    if (chOutlineData && chOutlineData.length) {
      if (Array.isArray(chOutlineData)) {
        chOutline = JSON.parse(JSON.stringify(chOutlineData));
      } else if (typeof chOutlineData === 'string') {
        // 如果是JSON格式，解析为蓝图和可读文本
        var isJsonOL = chOutlineData.trim().startsWith('```json') || chOutlineData.trim().startsWith('{');
        if (isJsonOL) {
          chOutline = parseOutlineJson(chOutlineData, idx);
        } else {
          chOutline = chOutlineData.split('\n').filter(function(l) { return l.trim(); }).map(function(l) { return {text: l.trim(), current: false, source: 'saved'}; });
        }
        if (chOutline.length === 0) chOutline = [{text: '【在此输入第' + (idx + 1) + '章大纲要点】', current: true, source: 'human'}];
      } else {
        chOutline = [{text: '【在此输入第' + (idx + 1) + '章大纲要点】', current: true, source: 'human'}];
      }
      if (typeof loadChapterVolumeOutline === 'function') loadChapterVolumeOutline();
    } else {
      // 本地没有outline，从API加载
      api('/api/chapter/load?index=' + idx).then(function(d) {
        if (d && d.outline && d.outline.length > 5 && d.outline !== 'none') {
          var isJsonOL2 = d.outline.trim().startsWith('```json') || d.outline.trim().startsWith('{');
          if (isJsonOL2) {
            chOutline = parseOutlineJson(d.outline, idx);
          } else {
            chOutline = d.outline.split('\n').filter(function(l) { return l.trim(); }).map(function(l) { return {text: l.trim(), current: false, source: 'saved'}; });
          }
          // 加载蓝图
          if (d.blueprint && !window._currentBlueprint) {
            window._currentBlueprint = d.blueprint;
          }
          if (chOutline.length === 0) chOutline = [{text: '【在此输入第' + (idx + 1) + '章大纲要点】', current: true, source: 'human'}];
        } else if (typeof extractOutlineFromNovelActs === 'function') {
          chOutline = extractOutlineFromNovelActs(idx);
        } else {
          chOutline = [{text: '【在此输入第' + (idx + 1) + '章大纲要点】', current: true, source: 'human'}];
        }
        if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
        if (typeof loadChapterVolumeOutline === 'function') loadChapterVolumeOutline();
      }).catch(function() {
        if (typeof extractOutlineFromNovelActs === 'function') {
          chOutline = extractOutlineFromNovelActs(idx);
        } else {
          chOutline = [{text: '【在此输入第' + (idx + 1) + '章大纲要点】', current: true, source: 'human'}];
        }
        if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
        if (typeof loadChapterVolumeOutline === 'function') loadChapterVolumeOutline();
      });
      return; // 异步加载中，等回调里再渲染
    }
  }
}

// 解析JSON格式的outline，提取蓝图和可读文本
window.parseOutlineJson = function(outlineText, idx) {
  function extField(text, field) {
    var pattern = '"' + field + '"\\s*:\\s*"([^"]*(?:\\\\.[^"]*)*)"';
    var matches = [];
    var re = new RegExp(pattern, 'g');
    var m;
    while ((m = re.exec(text)) !== null) {
      matches.push(m[1].replace(/\\"/g, '"').replace(/\\n/g, ' '));
    }
    return matches;
  }
  // 提取所有字段
  var bpScenes = extField(outlineText, 'scene');
  var bpAtmospheres = extField(outlineText, 'atmosphere');
  var bpTriggers = extField(outlineText, 'trigger');
  var bpEvents = extField(outlineText, 'event');
  var bpLocations = extField(outlineText, 'location');
  var bpChoices = extField(outlineText, 'choice');
  var bpCosts = extField(outlineText, 'cost');
  var bpInfoReveals = extField(outlineText, 'info_reveal');
  var bpConflicts = extField(outlineText, 'conflict');
  var bpTwists = extField(outlineText, 'twist');
  var bpKeyChoices = extField(outlineText, 'key_choice');
  var bpNewStates = extField(outlineText, 'new_state');
  var bpNextHooks = extField(outlineText, 'next_hook');

  // 构建window._currentBlueprint（如果还没有）
  if (!window._currentBlueprint && (bpScenes.length > 0 || bpEvents.length > 0)) {
    // intro用第一个scene（通常是intro的）
    var devArr = [];
    // development的scene从第2个开始（第1个是intro的）
    var devScenes = bpScenes.slice(1);
    var devEvents = bpEvents;
    var devLocations = bpLocations;
    var devChoices = bpChoices;
    var devCosts = bpCosts.slice(0, devScenes.length || devEvents.length);
    var devInfoReveals = bpInfoReveals;
    var maxLen = Math.max(devScenes.length, devEvents.length, devLocations.length, 1);
    for (var di = 0; di < maxLen; di++) {
      devArr.push({
        scene: devScenes[di] || '',
        location: devLocations[di] || '',
        event: devEvents[di] || '',
        choice: devChoices[di] || '',
        cost: devCosts[di] || '',
        info_reveal: devInfoReveals[di] || ''
      });
    }
    window._currentBlueprint = {
      intro: {
        scene: bpScenes[0] || '',
        atmosphere: bpAtmospheres[0] || '',
        trigger: bpTriggers[0] || ''
      },
      development: devArr,
      climax: {
        conflict: bpConflicts[0] || '',
        twist: bpTwists[0] || '',
        key_choice: bpKeyChoices[0] || ''
      },
      ending: {
        new_state: bpNewStates[0] || '',
        next_hook: bpNextHooks[0] || ''
      }
    };
    // 同步到chapters
    if (typeof chapters !== 'undefined' && chapters && idx >= 0 && chapters[idx]) {
      chapters[idx].blueprint = window._currentBlueprint;
    }
  }

  // 构建可读的大纲条目
  var textLines = [];
  if (bpScenes.length > 0) textLines.push('【起】' + bpScenes[0]);
  if (bpAtmospheres.length > 0) textLines.push('氛围：' + bpAtmospheres[0]);
  if (bpTriggers.length > 0) textLines.push('触发：' + bpTriggers[0]);
  var devEvents2 = bpEvents;
  devEvents2.forEach(function(ev, i) {
    if (ev) textLines.push('【承' + (i+1) + '】' + ev);
  });
  if (bpConflicts.length > 0) textLines.push('【转】' + bpConflicts[0]);
  if (bpTwists.length > 0) textLines.push('转折：' + bpTwists[0]);
  if (bpNewStates.length > 0) textLines.push('【合】' + bpNewStates[0]);
  if (bpNextHooks.length > 0) textLines.push('钩子：' + bpNextHooks[0]);

  if (textLines.length === 0) {
    // 正则也提取不到，返回空
    return [];
  }
  return textLines.map(function(l, i) {
    return {text: l.trim(), current: i === 0, source: 'parsed'};
  });
}

window.generateNextChapterOutline = async function() {
  showToast('正在生成下一章大纲...');
  if (typeof generateChapterOutline !== 'function') {
    showToast('AI未配置');
    return;
  }
  // P0: 先同步保存当前章节正文，确保旧章节内容落盘后再创建新章节
  var oldIdx = currentChapterIndex;
  var ed = document.getElementById('editor-content');
  var prevContent = ed ? ed.innerText || '' : '';
  if (oldIdx >= 0 && chapters && chapters[oldIdx] && prevContent.trim()) {
    try {
      await saveChapter(oldIdx, prevContent);
      if (chapters[oldIdx]) chapters[oldIdx].content = prevContent;
    } catch(e) { console.warn('save current chapter failed:', e); }
  }

  // P0-CRITICAL: 在修改 currentChapterIndex 之前，必须 flush 防抖中的 saveChapterOutline
  // 并清空 _currentBlueprint，否则待存的防抖会携带旧章节的 blueprint 写入新章节
  if (typeof saveChapterOutline === 'function') {
    try { await saveChapterOutline(true); } catch(e) { console.warn('flush outline save failed:', e); }
  }
  window._currentBlueprint = null;

  const nextCh = chapters.length + 1;
  // Build context from world settings, novel outline, and previous chapter
  var ctx = '';
  if (worldSettings && worldSettings.length) {
    ctx += '【世界观设定】\n' + worldSettings.map(function(s) { return s.key + ': ' + s.val; }).join('\n') + '\n\n';
  }
  ctx += '【前文内容】\n' + (prevContent || '（尚无内容）');

  var r;
  try {
    r = await generateChapterOutline('第' + nextCh + '章', ctx, chapters.length);
  } catch(e) {
    showToast('生成失败: ' + e.message);
    return;
  }
  if (!r || !r.ok) {
    showToast('生成失败: ' + (r && r.error || '未知错误'));
    return;
  }

  var outlineText = r.outline || '';
  // Parse outline into chOutline items
  var lines = outlineText.split('\n').filter(function(l) { return l.trim(); });
  var newOutline = [];
  lines.forEach(function(line) {
    var clean = line.replace(/^[-*\d.、\s]+/, '').trim();
    if (clean) newOutline.push({text: clean, current: false, source: 'ai'});
  });
  if (!newOutline.length) {
    newOutline.push({text: outlineText.trim(), current: false, source: 'ai'});
  }
  // Add new chapter
  var newTitle = '第' + nextCh + '章';
  chapters.push({title: newTitle, words: 0, word_count: 0});
  if (typeof addChapter === 'function') {
    addChapter(newTitle);
  }
  showToast('✓ 下一章大纲已生成，请审阅调整');

  // P0: 设置跳过标志，防止 goToStep 离开步骤6时自动保存串写到新章节
  window._skipAutoSaveOnLeaveStep6 = true;

  // Set as current and navigate
  currentChapterIndex = chapters.length - 1;
  chOutline = newOutline;
  // 清空编辑器，防止旧章节正文在后续步骤切换的自动保存中串写到新章节
  var ed2 = document.getElementById('editor-content');
  if (ed2) ed2.innerHTML = '<p></p>';
  await goToStep(STEPS.章节大纲);

  // 清除跳过标志
  window._skipAutoSaveOnLeaveStep6 = false;
}
var chDropdownCloseHandler = null;
var chOutlineDropdownCloseHandler = null;

// ── Save chapter outline ──
// P1-8: 防抖版 saveChapterOutline
var _saveChapterOutlineTimer = null;
var _saveChapterOutlinePending = false;
window._doSaveChapterOutline = function() {
  _saveChapterOutlineTimer = null;
  if (!_saveChapterOutlinePending) return Promise.resolve();
  _saveChapterOutlinePending = false;
  if (chapters && currentChapterIndex >= 0 && chapters[currentChapterIndex]) {
    chapters[currentChapterIndex].outline = JSON.parse(JSON.stringify(chOutline));
    // 保存结构化蓝图（如果存在且属于当前章节）
    // P0-DEFENSIVE: 检查 _currentBlueprint 的标题是否与当前章节匹配，防止旧章节的 blueprint 串写
    if (window._currentBlueprint) {
      var _bpTitle = window._currentBlueprint.title || '';
      var _chTitle = chapters[currentChapterIndex].title || '';
      // 如果 blueprint 有标题且与当前章节标题不匹配，跳过保存（防止串写）
      if (_bpTitle && _chTitle && _bpTitle !== _chTitle) {
        console.warn('[saveChapterOutline] blueprint title "' + _bpTitle + '" != chapter title "' + _chTitle + '", skipping blueprint save to prevent cross-chapter contamination');
        window._currentBlueprint = null;
      } else {
        chapters[currentChapterIndex].blueprint = window._currentBlueprint;
      }
    }
    // Also try to save to backend
    if (typeof api === 'function') {
      var postData = {
        index: currentChapterIndex,
        outline: chOutline.map(function(o) { return o.text; }).join('\n')
      };
      if (window._currentBlueprint) {
        postData.blueprint = window._currentBlueprint;
      }
      return api('/api/chapter/outline', {
        method: 'POST',
        body: JSON.stringify(postData)
      }).then(function(r) { if (r && r.ok) { /* saved */ } })
      .catch(function(e) { if (typeof showToast === 'function') showToast('大纲保存失败: ' + e.message); });
    }
    // 刷新卷纲要卡片（卷信息可能在 Step 4 被更新）
    if (typeof loadChapterVolumeOutline === 'function') loadChapterVolumeOutline();
  }
}
window.deleteChapter = function(idx) {
  if (typeof chapters === 'undefined' || !chapters) return;
  if (chapters.length <= 1) { showToast('不能删除最后一章'); return; }
  var chTitle = chapters[idx] ? (chapters[idx].title || ('第' + (idx + 1) + '章')) : ('第' + (idx + 1) + '章');
  if (!confirm('确认删除「' + chTitle + '」？\n\n⚠ 这将永久删除该章的全部内容和大纲，不可恢复。')) return;
  api('/api/chapter/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ index: idx }) })
    .then(function(data) {
      if (data.ok) {
        showToast('已删除「' + chTitle + '」');
        // Refresh chapter list
        if (typeof loadChaptersFromAPI === 'function') loadChaptersFromAPI().then(function() {
          if (typeof renderVolumeNav === 'function') { renderVolumeNav('vol-nav-outline', function(i) { loadChapterOutline(i); currentChapterIndex = i; loadChapterVolumeOutline(); }); renderVolumeNav('vol-nav-content', function(i) { loadChapterContentAPI(i); }); }
        });
      } else {
        showToast('删除失败：' + (data.error || '未知错误'));
      }
    }).catch(function(e) { showToast('网络错误：' + e.message); });
}

window.clearChapterOutline = function(idx) {
  if (typeof currentChapterIndex === 'undefined') idx = currentChapterIndex;
  if (idx == null) return;
  var chTitle = chapters[idx] ? (chapters[idx].title || ('第' + (idx + 1) + '章')) : ('第' + (idx + 1) + '章');
  if (!confirm('确认清空「' + chTitle + '」的章节大纲？')) return;
  api('/api/chapter/outline', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ index: idx, outline: '', blueprint: null }) })
    .then(function(data) {
      if (data.ok) {
        showToast('已清空「' + chTitle + '」的大纲');
        if (typeof chapters !== 'undefined' && chapters[idx]) chapters[idx].outline = '';
        if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
      } else {
        showToast('清空失败：' + (data.error || '未知错误'));
      }
    }).catch(function(e) { showToast('网络错误：' + e.message); });
}

window.saveChapterOutline = async function(immediate) {
  // P1-8: 防抖300ms，immediate=true时立即保存
  if (immediate) {
    if (_saveChapterOutlineTimer) { clearTimeout(_saveChapterOutlineTimer); _saveChapterOutlineTimer = null; }
    _saveChapterOutlinePending = true;  // 必须设为true，否则_doSaveChapterOutline会直接return
    return _doSaveChapterOutline();    // 返回Promise，让调用者可以await
  }
  _saveChapterOutlinePending = true;
  if (_saveChapterOutlineTimer) clearTimeout(_saveChapterOutlineTimer);
  _saveChapterOutlineTimer = setTimeout(_doSaveChapterOutline, 300);
}

/* ===== Chapter Outline View Switcher (Step 4) ===== */

var _currentChapterOutlineView = 'edit';

window.switchChapterOutlineView = function(view) {
  _currentChapterOutlineView = view;
  var editEl = document.getElementById('chapter-outline-editor');
  var kanbanEl = document.getElementById('chapter-kanban-view');
  var matrixEl = document.getElementById('chapter-matrix-view');
  var timelineEl = document.getElementById('chapter-timeline-view');
  var overlay = document.getElementById('chapter-outline-overlay');
  var overlayTitle = document.getElementById('chapter-overlay-title');
  var selectorEl = document.getElementById('chapter-selector-outline');
  var foreshadowEl = document.getElementById('foreshadow-summary');

  if (view === 'edit') {
    if (editEl) editEl.style.display = '';
    if (selectorEl) selectorEl.style.display = '';
    if (foreshadowEl) foreshadowEl.style.display = '';
    if (overlay) overlay.style.display = 'none';
  } else {
    if (editEl) editEl.style.display = 'none';
    if (selectorEl) selectorEl.style.display = 'none';
    if (foreshadowEl) foreshadowEl.style.display = 'none';
    if (overlay) { overlay.style.display = 'flex'; }
    if (overlayTitle) {
      var titles = { kanban: '📌 看板视图', matrix: '📊 矩阵视图', timeline: '👥 时间线' };
      overlayTitle.textContent = titles[view] || '章节大纲';
    }
    if (kanbanEl) kanbanEl.style.display = view === 'kanban' ? 'block' : 'none';
    if (matrixEl) matrixEl.style.display = view === 'matrix' ? 'block' : 'none';
    if (timelineEl) timelineEl.style.display = view === 'timeline' ? 'block' : 'none';
    if (view === 'kanban') renderChapterKanban();
    if (view === 'matrix') renderChapterMatrix();
    if (view === 'timeline') renderChapterTimeline();
  }

  // 更新按钮样式
  document.querySelectorAll('.covs-btn').forEach(function(btn) {
    if (btn.dataset.view === view) {
      btn.style.background = 'var(--accent)';
      btn.style.color = 'var(--bg)';
      btn.style.border = 'none';
    } else {
      btn.style.background = 'var(--bg)';
      btn.style.color = 'var(--muted)';
      btn.style.border = '1px solid var(--border)';
    }
  });
}

window.renderChapterKanban = function() {
  var container = document.getElementById('chapter-kanban-view');
  if (!container) return;
  if (typeof chapters === 'undefined' || !chapters || chapters.length === 0) {
    container.innerHTML = '<div class="empty-state" >暂无章节蓝图数据</div>';
    return;
  }
  var html = '<div style="display:flex;gap:14px;min-height:300px;align-items:flex-start;overflow-x:auto;padding-bottom:12px">';
  chapters.forEach(function(ch, ci) {
    var bp = ch.blueprint;
    var title = ch.title || ('第' + (ci+1) + '章');
    var plotLines = (bp && bp.plot_line) ? bp.plot_line.join(', ') : '主线';
    var wordTarget = (bp && bp.word_target) ? bp.word_target : '-';
    var wordActual = ch.word_count || 0;

    html += '<div style="flex:0 0 280px;background:var(--surface);border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:8px;border:2px solid var(--border-soft)" class="kanban-col" data-ci="' + ci + '">';
    // 标题
    html += '<div style="font-weight:700;font-size:0.88rem;color:var(--accent);padding-bottom:6px;border-bottom:2px solid var(--accent-soft)">' + esc(title) + '</div>';
    // 剧情线
    html += '<div style="font-size:0.72rem;color:var(--muted)">剧情线: ' + esc(plotLines) + '</div>';

    // 开场 - 可编辑
    if (bp && bp.intro) {
      html += '<div style="background:var(--bg);border-radius:6px;padding:8px 10px;font-size:0.78rem;border-left:3px solid #4CAF50">';
      html += '<div style="font-weight:600;color:#4CAF50;margin-bottom:3px">起·开场</div>';
      html += '<div class="kbn-editable input-bare" contenteditable="true" data-ci="' + ci + '" data-path="intro.scene" >' + esc(bp.intro.scene || '') + '</div>';
      if (bp.intro.trigger) html += '<div style="color:var(--muted);margin-top:2px;font-size:0.72rem">触发: <span class="kbn-editable outline-none" contenteditable="true" data-ci="' + ci + '" data-path="intro.trigger" >' + esc(bp.intro.trigger) + '</span></div>';
      html += '</div>';
    }

    // 发展场景 - 可编辑 + 可拖拽 + 可删除
    if (bp && bp.development && bp.development.length > 0) {
      html += '<div style="font-weight:600;font-size:0.78rem;color:#FF9800;margin:4px 0">承·发展 (' + bp.development.length + '场景)</div>';
      html += '<div class="dev-zone flex-col-xs" data-ci="' + ci + '" >';
      bp.development.forEach(function(dev, di) {
        html += '<div class="dev-card" draggable="true" data-ci="' + ci + '" data-di="' + di + '" style="background:var(--bg);border-radius:6px;padding:6px 10px;font-size:0.76rem;border-left:3px solid #FF9800;cursor:move;position:relative">';
        html += '<span class="kbn-del" data-ci="' + ci + '" data-di="' + di + '" style="position:absolute;top:2px;right:4px;color:var(--muted);font-size:12px;cursor:pointer;z-index:2;padding:2px 4px;border-radius:3px" title="删除此场景">✕</span>';
        html += '<div class="kbn-editable input-bare" contenteditable="true" data-ci="' + ci + '" data-path="development.' + di + '.scene" >' + esc(dev.scene || dev.event || '') + '</div>';
        if (dev.characters && dev.characters.length) html += '<div style="color:var(--muted);font-size:0.7rem;margin-top:2px">👥 <span class="kbn-editable outline-none" contenteditable="true" data-ci="' + ci + '" data-path="development.' + di + '.characters" >' + esc(dev.characters.join(', ')) + '</span></div>';
        html += '</div>';
      });
      html += '</div>';
    }

    // 高潮 - 可编辑
    if (bp && bp.climax) {
      html += '<div style="background:var(--bg);border-radius:6px;padding:8px 10px;font-size:0.78rem;border-left:3px solid #F44336">';
      html += '<div style="font-weight:600;color:#F44336;margin-bottom:3px">转·高潮</div>';
      html += '<div class="kbn-editable input-bare" contenteditable="true" data-ci="' + ci + '" data-path="climax.conflict" >' + esc(bp.climax.conflict || bp.climax.twist || '') + '</div>';
      html += '</div>';
    }

    // 结局 - 可编辑
    if (bp && bp.ending) {
      html += '<div style="background:var(--bg);border-radius:6px;padding:8px 10px;font-size:0.78rem;border-left:3px solid #9C27B0">';
      html += '<div style="font-weight:600;color:#9C27B0;margin-bottom:3px">合·结局</div>';
      html += '<div class="kbn-editable" contenteditable="true" data-ci="' + ci + '" data-path="ending.new_state" style="color:var(--ink);outline:none;border:none;min-height:18px">' + esc(bp.ending.new_state || '') + '</div>';
      if (bp.ending.next_hook) html += '<div style="color:var(--muted);font-size:0.72rem;margin-top:2px">钩子: <span class="kbn-editable input-bare outline-none" contenteditable="true" data-ci="' + ci + '" data-path="ending.next_hook" >' + esc(bp.ending.next_hook) + '</span></div>';
      html += '</div>';
    }

    // 字数
    html += '<div style="font-size:0.7rem;color:var(--muted);text-align:right;border-top:1px solid var(--border-soft);padding-top:4px;margin-top:4px">目标: ' + wordTarget + '字 · 实际: ' + wordActual + '字</div>';
    html += '</div>';
  });
  html += '</div>';
  container.innerHTML = html;

  // ── 绑定内联编辑保存 ──
  container.querySelectorAll('.kbn-editable').forEach(function(el) {
    el.addEventListener('blur', function() {
      var ci = parseInt(this.dataset.ci);
      var path = this.dataset.path;
      var newVal = this.textContent.trim();
      if (!path || isNaN(ci) || ci < 0 || ci >= chapters.length) return;
      var bp = chapters[ci].blueprint;
      if (!bp) return;
      var parts = path.split('.');
      // 导航到目标属性
      var target = bp;
      for (var i = 0; i < parts.length - 1; i++) {
        if (parts[i] === 'development') { target = target.development; }
        else if (target[parts[i]]) { target = target[parts[i]]; }
        else return;
      }
      var lastKey = parts[parts.length - 1];
      if (lastKey === 'characters') {
        target[lastKey] = newVal.split(/[,，]/).map(function(s) { return s.trim(); }).filter(function(s) { return s; });
      } else {
        target[lastKey] = newVal;
      }
      // 静默保存
      saveBlueprintToAPI(ci, bp);
    });
  });

  // ── 绑定development场景拖拽排序 ──
  var dragCard = null;
  var dragCi = -1;
  var dragDi = -1;
  container.querySelectorAll('.dev-card').forEach(function(card) {
    card.addEventListener('dragstart', function(e) {
      dragCard = this;
      dragCi = parseInt(this.dataset.ci);
      dragDi = parseInt(this.dataset.di);
      e.dataTransfer.effectAllowed = 'move';
      this.style.opacity = '0.4';
    });
    card.addEventListener('dragend', function() {
      this.style.opacity = '1';
    });
  });
  container.querySelectorAll('.dev-zone').forEach(function(zone) {
    zone.addEventListener('dragover', function(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
    });
    zone.addEventListener('drop', function(e) {
      e.preventDefault();
      var targetCi = parseInt(this.dataset.ci);
      if (!dragCard || dragCi !== targetCi || isNaN(dragCi)) return;
      var bp = chapters[dragCi].blueprint;
      if (!bp || !bp.development) return;
      // 计算落点位置
      var afterCard = null;
      var zoneCards = Array.from(this.querySelectorAll('.dev-card'));
      var rect = this.getBoundingClientRect();
      var dropY = e.clientY - rect.top;
      var accumulated = 0;
      for (var i = 0; i < zoneCards.length; i++) {
        var cr = zoneCards[i].getBoundingClientRect();
        accumulated += cr.height + 4; // +gap
        if (dropY < accumulated) { afterCard = zoneCards[i]; break; }
      }
      // 移动数据
      var moved = bp.development.splice(dragDi, 1)[0];
      var newIdx = afterCard ? parseInt(afterCard.dataset.di) : bp.development.length;
      if (newIdx > dragDi) newIdx--;
      bp.development.splice(newIdx, 0, moved);
      renderChapterKanban();
      saveBlueprintToAPI(dragCi, bp);
      showToast('场景顺序已调整');
    });
  });

  // ── 绑定删除场景按钮 ──
  container.querySelectorAll('.kbn-del').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var ci = parseInt(this.dataset.ci);
      var di = parseInt(this.dataset.di);
      if (isNaN(ci) || isNaN(di)) return;
      var bp = chapters[ci].blueprint;
      if (!bp || !bp.development) return;
      bp.development.splice(di, 1);
      renderChapterKanban();
      saveBlueprintToAPI(ci, bp);
      showToast('已删除场景');
    });
  });
}

window.saveBlueprintToAPI = function(chapterIndex, blueprint) {
  var title = chapters[chapterIndex] ? chapters[chapterIndex].title : '';
  var text = JSON.stringify(blueprint);
  fetch('/api/chapter/outline', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({index: chapterIndex, outline: text})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) {
      chapters[chapterIndex].outline = text;
      chapters[chapterIndex].blueprint = blueprint;
    }
  }).catch(function(err) { console.error('保存蓝图失败', err); });
}

window.renderChapterMatrix = function() {
  var container = document.getElementById('chapter-matrix-view');
  if (!container) return;
  if (typeof chapters === 'undefined' || !chapters || chapters.length === 0) {
    container.innerHTML = '<div class="empty-state" >暂无章节蓝图数据</div>';
    return;
  }
  // 表格：行 = 结构元素（开场/发展/高潮/结局），列 = 各章
  var html = '<table style="width:100%;border-collapse:collapse;font-size:0.78rem;overflow-x:auto;display:block">';
  html += '<thead><tr><th style="padding:8px;border:1px solid var(--border);background:var(--surface);color:var(--accent);text-align:left;position:sticky;left:0;background:var(--surface);z-index:1">结构</th>';
  chapters.forEach(function(ch) {
    html += '<th style="padding:8px;border:1px solid var(--border);background:var(--surface);color:var(--accent);min-width:180px">' + esc(ch.title || ('第' + (chapters.indexOf(ch)+1) + '章')) + '</th>';
  });
  html += '</tr></thead><tbody>';

  var rows = [
    { label: '起·开场', key: 'intro', sub: 'scene', color: '#4CAF50' },
    { label: '承·发展', key: 'development', sub: 'event', color: '#FF9800' },
    { label: '转·高潮', key: 'climax', sub: 'conflict', color: '#F44336' },
    { label: '合·结局', key: 'ending', sub: 'new_state', color: '#9C27B0' }
  ];

  rows.forEach(function(row) {
    html += '<tr><td style="padding:6px 8px;border:1px solid var(--border);font-weight:600;color:' + row.color + ';white-space:nowrap;position:sticky;left:0;background:var(--bg);z-index:1">' + row.label + '</td>';
    chapters.forEach(function(ch) {
      var bp = ch.blueprint;
      var val = '';
      if (bp) {
        if (row.key === 'development') {
          if (bp.development && bp.development.length > 0) {
            val = bp.development.map(function(d, i) { return (i+1) + '.' + esc(d[row.sub] || d.scene || ''); }).join('<br>');
          }
        } else {
          var section = bp[row.key];
          if (section) val = esc(section[row.sub] || '');
        }
      }
      var bg = val ? 'var(--bg)' : 'var(--surface)';
      html += '<td style="padding:6px 8px;border:1px solid var(--border);vertical-align:top;background:' + bg + '">' + (val || '<span class="text-muted" >-</span>') + '</td>';
    });
    html += '</tr>';
  });

  // 字数行
  html += '<tr><td style="padding:6px 8px;border:1px solid var(--border);font-weight:600;color:var(--muted);position:sticky;left:0;background:var(--surface);z-index:1">字数</td>';
  chapters.forEach(function(ch) {
    var wt = (ch.blueprint && ch.blueprint.word_target) ? ch.blueprint.word_target : '-';
    var wa = ch.word_count || 0;
    html += '<td style="padding:6px 8px;border:1px solid var(--border);text-align:center;background:var(--surface);color:var(--muted);font-size:0.72rem">目标' + wt + '<br>实际' + wa + '</td>';
  });
  html += '</tr></tbody></table>';
  container.innerHTML = html;
}

window.renderChapterTimeline = function() {
  var container = document.getElementById('chapter-timeline-view');
  if (!container) return;
  if (typeof chapters === 'undefined' || !chapters || chapters.length === 0) {
    container.innerHTML = '<div class="empty-state" 暂无章节蓝图数据</div>';
    return;
  }
  // 时间线视图：垂直排列，每章一个节点，展示场景流程和人物出场
  var html = '<div style="position:relative;padding-left:24px">';
  // 竖线
  html += '<div style="position:absolute;left:8px;top:0;bottom:0;width:2px;background:var(--border)"></div>';

  var allChars = {};
  chapters.forEach(function(ch, ci) {
    var bp = ch.blueprint;
    var title = ch.title || ('第' + (ci+1) + '章');
    var chars = [];
    if (bp) {
      if (bp.development) bp.development.forEach(function(d) { (d.characters || []).forEach(function(c) { chars.push(c); }); });
    }
    chars = [...new Set(chars)];
    chars.forEach(function(c) { allChars[c] = (allChars[c] || 0) + 1; });

    html += '<div style="position:relative;margin-bottom:20px">';
    // 节点圆点
    html += '<div style="position:absolute;left:-20px;top:4px;width:12px;height:12px;border-radius:50%;background:var(--accent);border:2px solid var(--bg);z-index:1"></div>';
    // 标题
    html += '<div style="font-weight:700;font-size:0.88rem;color:var(--accent);margin-bottom:6px">' + esc(title) + '</div>';

    // 场景列表
    if (bp) {
      var scenes = [];
      if (bp.intro) scenes.push({label: '开场', text: bp.intro.scene || '', trigger: bp.intro.trigger || ''});
      if (bp.development) bp.development.forEach(function(d, i) { scenes.push({label: '场景' + (i+1), text: d.scene || d.event || '', chars: d.characters || []}); });
      if (bp.climax) scenes.push({label: '高潮', text: bp.climax.conflict || bp.climax.twist || ''});
      if (bp.ending) scenes.push({label: '结局', text: bp.ending.new_state || '', hook: bp.ending.next_hook || ''});

      html += '<div style="display:flex;flex-direction:column;gap:4px;margin-left:8px">';
      scenes.forEach(function(s) {
        html += '<div style="display:flex;align-items:flex-start;gap:8px;font-size:0.78rem">';
        html += '<span style="color:var(--muted);white-space:nowrap;min-width:40px">' + esc(s.label) + '</span>';
        html += '<span class="text-ink" >' + esc(s.text) + '</span>';
        if (s.chars && s.chars.length) html += '<span style="color:var(--accent);font-size:0.7rem;margin-left:auto;white-space:nowrap">' + esc(s.chars.join(', ')) + '</span>';
        html += '</div>';
      });
      html += '</div>';
    } else {
      html += '<div style="color:var(--muted);font-size:0.78rem;margin-left:8px">暂无蓝图数据</div>';
    }

    html += '</div>';
  });
  html += '</div>';

  // 人物出场统计
  var charEntries = Object.entries(allChars).sort(function(a, b) { return b[1] - a[1]; });
  if (charEntries.length > 0) {
    html += '<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-soft)">';
    html += '<div style="font-weight:600;font-size:0.82rem;color:var(--accent);margin-bottom:8px">👥 人物出场统计</div>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
    charEntries.forEach(function(entry) {
      html += '<span style="padding:3px 10px;border-radius:12px;background:var(--surface);border:1px solid var(--border-soft);font-size:0.75rem;color:var(--ink)">' + esc(entry[0]) + ' <span style="color:var(--accent);font-weight:600">' + entry[1] + '章</span></span>';
    });
    html += '</div></div>';
  }

  container.innerHTML = html;
}

/* ===== 全书大纲多视图 ===== */
var _currentNovelOutlineView = 'edit';
var _novelOutlineDict = {};
window.switchNovelOutlineView = function(view) {
  _currentNovelOutlineView = view;
  var editEl = document.getElementById('novel-outline-editor');
  var matrixEl = document.getElementById('novel-matrix-view');
  var kanbanEl = document.getElementById('novel-kanban-view');
  var overlay = document.getElementById('novel-outline-overlay');
  var overlayTitle = document.getElementById('novel-overlay-title');
  var viewSwitcher = document.getElementById('novel-outline-view-switcher');

  if (view === 'edit') {
    if (editEl) editEl.style.display = '';
    if (overlay) overlay.style.display = 'none';
    if (viewSwitcher) viewSwitcher.style.display = 'flex';
  } else if (view === 'matrix') {
    if (editEl) editEl.style.display = 'none';
    if (overlay) { overlay.style.display = 'flex'; if(overlayTitle) overlayTitle.textContent = '📊 矩阵视图'; }
    if (matrixEl) { matrixEl.style.display = 'block'; renderNovelOutlineMatrix(); }
    if (kanbanEl) kanbanEl.style.display = 'none';
  } else if (view === 'kanban') {
    if (editEl) editEl.style.display = 'none';
    if (overlay) { overlay.style.display = 'flex'; if(overlayTitle) overlayTitle.textContent = '📌 看板视图'; }
    if (matrixEl) matrixEl.style.display = 'none';
    if (kanbanEl) { kanbanEl.style.display = 'block'; renderNovelOutlineKanban(); }
  }
  // 更新按钮样式
  document.querySelectorAll('.novs-btn').forEach(function(btn) {
    if (btn.dataset.view === view) {
      btn.classList.add('active');
      btn.style.background = 'var(--accent)';
      btn.style.color = 'var(--bg)';
      btn.style.border = 'none';
    } else {
      btn.classList.remove('active');
      btn.style.background = 'var(--bg)';
      btn.style.color = 'var(--muted)';
      btn.style.border = '1px solid var(--border)';
    }
  });
}
window.renderNovelOutlineMatrix = function() {
  var container = document.getElementById('novel-matrix-view');
  if (!container) return;
  if (!_novelOutlineDict || Object.keys(_novelOutlineDict).length === 0) {
    container.innerHTML = '<div class="empty-state" >暂无大纲数据，请先在编辑视图中添加。</div>';
    return;
  }
  var fields = [
    {key: 'theme', label: '🎯 主题'},
    {key: 'core_conflict', label: '⚔️ 核心冲突'},
    {key: 'story_arc', label: '📖 故事走向'},
    {key: 'world_anchor', label: '🌍 世界观锚点'},
    {key: 'character_arcs', label: '👤 角色弧光'},
    {key: 'key_hooks', label: '🔮 关键伏笔'},
    {key: 'ending', label: '🏁 结局指引'},
    {key: 'tone', label: '🎭 基调'}
  ];
  var html = '<table style="width:100%;border-collapse:collapse;font-size:0.82rem"><thead><tr><th style="padding:8px;border:1px solid var(--border);background:var(--surface);color:var(--accent);text-align:left;width:120px">字段</th><th style="padding:8px;border:1px solid var(--border);background:var(--surface);color:var(--accent);text-align:left">内容</th></tr></thead><tbody>';
  fields.forEach(function(f) {
    var val = _novelOutlineDict[f.key];
    var displayVal = '';
    if (Array.isArray(val)) {
      displayVal = val.map(function(v) {
        if (typeof v === 'object') return (v.character || v.content || v.text || '') + (v.arc ? ' | ' + v.arc : '');
        return String(v);
      }).join('<br>');
    } else {
      displayVal = String(val || '').replace(/\n/g, '<br>');
    }
    html += '<tr><td style="padding:8px;border:1px solid var(--border);background:var(--surface);font-weight:600">' + f.label + '</td><td style="padding:8px;border:1px solid var(--border);vertical-align:top">' + (displayVal || '<span class="text-muted" >未填写</span>') + '</td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

window.renderNovelOutlineKanban = function() {
  var container = document.getElementById('novel-kanban-view');
  if (!container) return;
  if (!_novelOutlineDict || Object.keys(_novelOutlineDict).length === 0) {
    container.innerHTML = '<div class="empty-state" 暂无大纲数据，请先在编辑视图中添加。</div>';
    return;
  }
  var fields = [
    {key: 'theme', label: '🎯 主题', color: '#6366f1'},
    {key: 'core_conflict', label: '⚔️ 核心冲突', color: '#ef4444'},
    {key: 'story_arc', label: '📖 故事走向', color: '#22c55e'},
    {key: 'world_anchor', label: '🌍 世界观锚点', color: '#14b8a6'},
    {key: 'character_arcs', label: '👤 角色弧光', color: '#f59e0b'},
    {key: 'key_hooks', label: '🔮 关键伏笔', color: '#8b5cf6'},
    {key: 'ending', label: '🏁 结局指引', color: '#ec4899'},
    {key: 'tone', label: '🎭 基调', color: '#06b6d4'}
  ];
  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap">';
  fields.forEach(function(f) {
    var val = _novelOutlineDict[f.key];
    var displayVal = '';
    if (Array.isArray(val)) {
      displayVal = val.map(function(v) {
        if (typeof v === 'object') {
          var name = v.character || '';
          var text = v.arc || v.content || v.text || '';
          return (name ? '<strong>' + esc(name) + '</strong> ' : '') + (text ? '| ' + esc(text) : '');
        }
        return esc(String(v));
      }).join('<br>');
    } else {
      displayVal = esc(String(val || '')).replace(/\n/g, '<br>');
    }
    html += '<div style="width:280px;background:var(--surface);border-radius:8px;padding:12px;border-top:3px solid ' + f.color + '"><div style="font-weight:700;font-size:0.85rem;color:var(--accent);margin-bottom:8px">' + f.label + '</div><div style="font-size:0.82rem;line-height:1.6;color:var(--ink);min-height:60px">' + (displayVal || '<span class="text-muted" 未填写</span>') + '</div></div>';
  });
  html += '</div>';
  container.innerHTML = html;
}

/* ===== 全书大纲渲染 ===== */

window.renderNovelOutlineEditor = async function() {
  const ed = document.getElementById('novel-outline-editor');
  ed.innerHTML = '';

  const nvSec = document.createElement('div');
  nvSec.className = 'outline-section';
  const nvHeader = document.createElement('div');
  nvHeader.className = 'section-header expanded';
  nvHeader.innerHTML = '<span class="section-arrow">▶</span><h4>全书大纲</h4>';
  const nvBody = document.createElement('div');
  nvBody.className = 'section-body';

  // ===== 8字段结构化全书大纲编辑器 =====
  var outlineHtml = '<div id="novel-outline-structured" style="margin-bottom:16px;margin-left:auto;margin-right:auto;padding:12px;max-width:900px;background:var(--surface);border-radius:8px;border:1px solid var(--border-soft)">';
  outlineHtml += '<div style="display:flex;gap:16px;flex-wrap:wrap">';

  // 主题
  outlineHtml += '<div class="nv-field-box" style="flex:1;min-width:200px">';
  outlineHtml += '<label class="label-accent-sm" >🎯 主题</label>';
  outlineHtml += '<textarea id="nv-theme" class="nv-field" data-key="theme" style="width:100%;min-height:40px;padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:12px;font-family:var(--sans);resize:vertical;box-sizing:border-box" placeholder="一句话概括全书在讲什么，15-30字">' + esc((_novelOutlineDict && _novelOutlineDict.theme) || '') + '</textarea>';
  outlineHtml += '</div>';

  // 核心冲突
  outlineHtml += '<div class="nv-field-box" style="flex:2;min-width:300px">';
  outlineHtml += '<label >⚔️ 核心冲突</label>';
  outlineHtml += '<textarea id="nv-core-conflict" class="nv-field textarea-md label-accent-sm" data-key="core_conflict"  placeholder="明线冲突 + 暗线冲突，2-3句话">' + esc((_novelOutlineDict && _novelOutlineDict.core_conflict) || '') + '</textarea>';
  outlineHtml += '</div>';

  outlineHtml += '</div>';

  // 故事走向
  outlineHtml += '<div class="nv-field-box mt-3" >';
  outlineHtml += '<label class="label-accent-sm" 📖 故事走向</label>';
  outlineHtml += '<textarea id="nv-story-arc" class="nv-field label-accent-sm" data-key="story_arc" style="width:100%;min-height:100px;padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:12px;font-family:var(--sans);resize:vertical;box-sizing:border-box" placeholder="起承转合的时间线叙述，从开局到结局的完整脉络">' + esc((_novelOutlineDict && _novelOutlineDict.story_arc) || '') + '</textarea>';
  outlineHtml += '</div>';

  outlineHtml += '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px">';

  // 世界观锚点
  outlineHtml += '<div class="nv-field-box" style="flex:1;min-width:250px">';
  outlineHtml += '<label class="label-accent-sm" 🌍 世界观锚点</label>';
  outlineHtml += '<textarea id="nv-world-anchor" class="nv-field textarea-md label-accent-sm" data-key="world_anchor"  placeholder="核心世界观要素：世界结构、力量体系、关键势力、特殊设定">' + esc((_novelOutlineDict && _novelOutlineDict.world_anchor) || '') + '</textarea>';
  outlineHtml += '</div>';

  // 基调
  outlineHtml += '<div class="nv-field-box" style="flex:0 0 120px">';
  outlineHtml += '<label class="label-accent-sm" 🎭 基调</label>';
  outlineHtml += '<input type="text" id="nv-tone" class="nv-field label-accent-sm" data-key="tone" style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:12px;font-family:var(--sans);box-sizing:border-box" placeholder="热血、沉重、诙谐…" value="' + esc((_novelOutlineDict && _novelOutlineDict.tone) || '') + '">';
  outlineHtml += '</div>';

  outlineHtml += '</div>';

  // 主要角色弧光
  outlineHtml += '<div >';
  outlineHtml += '<label class="label-accent-sm mt-3" >👤 主要角色弧光</label>';
  outlineHtml += '<div id="nv-character-arcs" >';
  var charArcs = (_novelOutlineDict && _novelOutlineDict.character_arcs) || [];
  if (charArcs.length === 0) {
    outlineHtml += '<div class="nv-char-arc" data-index="0"><input type="text" class="nv-char-name input-xs" placeholder="角色名"> <span>|</span> <input type="text" class="nv-char-arc-text input-xs text-muted" placeholder="从X到Y的转变"> <button class="nv-char-del" title="删除">×</button></div>';
  } else {
    charArcs.forEach(function(arc, i) {
      var name = typeof arc === 'object' ? (arc.character || '') : '';
      var text = typeof arc === 'object' ? (arc.arc || '') : String(arc);
      outlineHtml += '<div class="nv-char-arc" data-index="' + i + '"><input type="text" class="nv-char-name input-xs"  value="' + esc(name) + '"> <span >|</span> <input type="text" class="nv-char-arc-text input-xs text-muted"  value="' + esc(text) + '"> <button class="nv-char-del btn-danger-xs" >×</button></div>';
    });
  }
  outlineHtml += '</div>';
  outlineHtml += '<button class="info-link-xs" id="nv-add-char-arc" >➕ 添加角色弧光</button>';
  outlineHtml += '</div>';

  // 关键伏笔
  outlineHtml += '<div class="mt-3" >';
  outlineHtml += '<label class="label-accent-sm" >🔮 关键伏笔</label>';
  outlineHtml += '<div id="nv-key-hooks" >';
  var keyHooks = (_novelOutlineDict && _novelOutlineDict.key_hooks) || [];
  if (keyHooks.length === 0) {
    outlineHtml += '<div class="nv-key-hook" data-index="0"><input type="text" class="nv-hook-text input-xs" placeholder="伏笔内容 | 何时埋下 | 何时揭示"> <button class="nv-hook-del" title="删除">×</button></div>';
  } else {
    keyHooks.forEach(function(hook, i) {
      var text = typeof hook === 'object' ? (hook.content || '') : String(hook);
      outlineHtml += '<div class="nv-key-hook" data-index="' + i + '"><input type="text" class="nv-hook-text input-xs" value="' + esc(text) + '"> <button class="nv-hook-del" title="删除">×</button></div>';
    });
  }
  outlineHtml += '</div>';
  outlineHtml += '<button id="nv-add-key-hook" >➕ 添加伏笔</button>';
  outlineHtml += '</div>';

  // 结局指引
  outlineHtml += '<div class="nv-field-box info-link-xs" style="margin-top:12px">';
  outlineHtml += '<label class="mt-3 label-accent-sm" 🏁 结局指引</label>';
  outlineHtml += '<textarea id="nv-ending" class="nv-field label-accent-sm" data-key="ending" style="width:100%;min-height:60px;padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:12px;font-family:var(--sans);resize:vertical;box-sizing:border-box" placeholder="故事以什么方式收尾，1-2句话">' + esc((_novelOutlineDict && _novelOutlineDict.ending) || '') + '</textarea>';
  outlineHtml += '</div>';

  outlineHtml += '</div>';

  nvBody.innerHTML = outlineHtml + '<div id="novel-inspiration-box" style="margin:8px auto;padding:8px;max-width:900px;border:1px dashed var(--accent);border-radius:6px;background:var(--surface)"><span style="font-size:11px;color:var(--accent);font-weight:600">💡 灵感碎片 → 全书大纲</span><textarea id="novel-inspiration-input" placeholder="在这里写下你的灵感碎片、世界观构想、剧情走向…&#10;例如：主角是一个穿越到修仙世界的程序员，他发现可以用代码思维重构灵力体系…&#10;AI会分析你的想法，结合世界观设定生成完整的全书大纲" style="width:100%;min-height:72px;margin:6px 0;padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px;font-family:var(--sans);resize:vertical;box-sizing:border-box"></textarea><div ><button class="btn-sm ai flex-row-xs" id="btn-inspiration-to-novel-ol">🧠 灵感→大纲</button><button class="btn-sm" id="btn-novel-inspiration-clear">🗑 清空</button></div></div><div class="section-actions" style="max-width:900px;margin:0 auto"><select id="outline-scale" style="padding:2px 6px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px;font-family:var(--sans);cursor:pointer"><option value="short">短篇 10章</option><option value="mid">中篇 20-50章</option><option value="long">长篇 100-200章</option><option value="epic">百万字 300+章</option><option value="custom">自定义</option></select><input type="number" id="outline-custom-chapters" min="3" max="500" value="10" style="display:none;width:60px;padding:2px 4px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px;font-family:var(--sans)" title="输入总章数"><span id="outline-custom-label" style="display:none;font-size:11px;color:var(--muted)">章</span><button class="btn-sm ai" id="btn-ai-gen-novel-ol">🤖 AI生成</button><button class="btn-sm" id="btn-ai-opt-novel-ol">✨ AI优化</button><button class="btn-sm" id="btn-clear-novel-ol" title="清空全书大纲" style="color:#c44">🗑 清空</button><button class="btn-sm accept" id="btn-save-novel-ol">💾 保存</button></div>';
  nvSec.appendChild(nvHeader);
  nvSec.appendChild(nvBody);
  ed.appendChild(nvSec);
  nvHeader.addEventListener('click', () => { nvHeader.classList.toggle('expanded'); nvBody.classList.toggle('collapsed'); });

  // ===== 绑定8字段编辑器事件 =====
  // 添加角色弧光
  document.getElementById('nv-add-char-arc')?.addEventListener?.('click', function() {
    var container = document.getElementById('nv-character-arcs');
    var newIdx = container ? container.children.length : 0;
    var div = document.createElement('div');
    div.className = 'nv-char-arc';
    div.dataset.index = String(newIdx);
    div.innerHTML = '<input type="text" class="nv-char-name input-xs" placeholder="角色名"> <span>|</span> <input type="text" class="nv-char-arc-text input-xs text-muted" placeholder="从X到Y的转变"> <button class="nv-char-del" title="删除">×</button>';
    container.appendChild(div);
    // 绑定中间编辑器事件 — 显示全书大纲全部内容
    var nameInput = div.querySelector('.nv-char-name');
    var arcInput = div.querySelector('.nv-char-arc-text');
    if (nameInput) {
      nameInput.addEventListener('focus', function() {
        var firstField = document.querySelector('.nv-field');
        if (firstField) firstField.dispatchEvent(new Event('focus'));
      });
    }
    if (arcInput) {
      arcInput.addEventListener('focus', function() {
        var firstField = document.querySelector('.nv-field');
        if (firstField) firstField.dispatchEvent(new Event('focus'));
      });
    }
    div.querySelector('.nv-char-del')?.addEventListener?.('click', function() {
      div.remove();
    });
  });
  // 删除角色弧光
  document.querySelectorAll('.nv-char-del')?.forEach(function(btn) {
    btn.addEventListener('click', function() {
      this.parentElement.remove();
    });
  });
  // 添加伏笔
  document.getElementById('nv-add-key-hook')?.addEventListener?.('click', function() {
    var container = document.getElementById('nv-key-hooks');
    var newIdx = container ? container.children.length : 0;
    var div = document.createElement('div');
    div.className = 'nv-key-hook';
    div.dataset.index = String(newIdx);
    div.innerHTML = '<input type="text" class="nv-hook-text input-xs" placeholder="伏笔内容 | 何时埋下 | 何时揭示"> <button class="nv-hook-del" title="删除">×</button>';
    container.appendChild(div);
    // 绑定中间编辑器事件 — 显示全书大纲全部内容
    var hookInput = div.querySelector('.nv-hook-text');
    if (hookInput) {
      hookInput.addEventListener('focus', function() {
        var firstField = document.querySelector('.nv-field');
        if (firstField) firstField.dispatchEvent(new Event('focus'));
      });
    }
    div.querySelector('.nv-hook-del')?.addEventListener?.('click', function() {
      div.remove();
    });
  });
  // 删除伏笔
  document.querySelectorAll('.nv-hook-del')?.forEach(function(btn) {
    btn.addEventListener('click', function() {
      this.parentElement.remove();
    });
  });

  // 下拉切换时显示/隐藏自定义章数输入框
  var scaleSelect = document.getElementById('outline-scale');
  if (scaleSelect) {
    scaleSelect.addEventListener('change', function() {
      var isCustom = this.value === 'custom';
      var numInput = document.getElementById('outline-custom-chapters');
      var numLabel = document.getElementById('outline-custom-label');
      if (numInput) numInput.style.display = isCustom ? 'inline-block' : 'none';
      if (numLabel) numLabel.style.display = isCustom ? 'inline' : 'none';
    });
  }

  // Event handlers
  document.getElementById('btn-ai-gen-novel-ol')?.addEventListener?.('click', async function() {
    var btn = this;
    btn.textContent = '⏳ 生成中…'; btn.disabled = true;
    var genre = document.getElementById('current-chapter-label')?.textContent || '小说';
    var title = document.getElementById('project-name')?.textContent || (state && state.project && state.project.title) || '小说';
    var scale = document.getElementById('outline-scale')?.value || 'short';
    var scaleCfg = {short:10, mid:40, long:150, epic:300};
    var length = scaleCfg[scale] || 10;
    if (scale === 'custom') {
      length = parseInt(document.getElementById('outline-custom-chapters')?.value) || 10;
    }
    // 如果已有内容，提示用户
    if (_novelOutlineDict && Object.keys(_novelOutlineDict).length > 0) {
      if (!confirm('已有全书大纲内容，重新生成将覆盖现有内容。确定继续？')) {
        btn.textContent = '🤖 AI生成'; btn.disabled = false;
        return;
      }
    }
    try {
      var r = await api('/api/generate/outline', {
        method: 'POST',
        body: JSON.stringify({title: title, genre: genre, length: length})
      });
      if (r.ok && r.outline) {
        // 处理结构化返回值（dict格式）
        if (typeof r.outline === 'object' && !Array.isArray(r.outline)) {
          _novelOutlineDict = r.outline;
        } else if (typeof r.outline === 'string') {
          _novelOutlineDict = {};
        }
        renderNovelOutlineEditor();
        showToast('AI已生成全书大纲');
        api('/api/project/novel-outline', {method:'POST', body:JSON.stringify({novel_outline:_novelOutlineDict})}).catch(function(){});
      } else {
        showToast('生成失败: ' + (r.error || '未知错误'));
      }
    } catch(e) { showToast('生成失败: ' + e.message); }
    btn.textContent = '🤖 AI生成'; btn.disabled = false;
  });

  document.getElementById('btn-ai-opt-novel-ol')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 优化中…'; this.disabled = true;
    try {
      const data = JSON.stringify(_novelOutlineDict, null, 2);
      const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: '请优化以下全书大纲（保持8字段JSON格式）：\n' + data}]})});
      if (r.ok && r.content) {
        var jsonMatch = r.content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try {
            _novelOutlineDict = JSON.parse(jsonMatch[0]);
            renderNovelOutlineEditor();
            showToast('✅ 已优化');
          } catch(parseErr) {
            showToast('优化结果格式解析失败');
          }
        } else {
          showToast('优化结果格式解析失败');
        }
        // 优化后自动保存结构化大纲
        api('/api/project/novel-outline', {
          method: 'POST',
          body: JSON.stringify({novel_outline: _novelOutlineDict})
        }).catch(function(e) { console.error('Save optimized outline failed:', e); });
      } else { showToast('优化失败'); }
    } catch(e) { showToast('优化失败: ' + e.message); }
    this.textContent = '✨ AI优化'; this.disabled = false;
  });
  document.getElementById('btn-save-novel-ol')?.addEventListener?.('click', async function() {
    this.textContent = '⏳'; this.disabled = true;
    // 从8字段编辑器读取数据
    var theme = document.getElementById('nv-theme')?.value || '';
    var coreConflict = document.getElementById('nv-core-conflict')?.value || '';
    var storyArc = document.getElementById('nv-story-arc')?.value || '';
    var worldAnchor = document.getElementById('nv-world-anchor')?.value || '';
    var tone = document.getElementById('nv-tone')?.value || '';
    var ending = document.getElementById('nv-ending')?.value || '';
    // 读取角色弧光
    var charArcs = [];
    document.querySelectorAll('.nv-char-arc').forEach(function(row) {
      var name = row.querySelector('.nv-char-name')?.value || '';
      var text = row.querySelector('.nv-char-arc-text')?.value || '';
      if (name || text) {
        charArcs.push({character: name, arc: text});
      }
    });
    // 读取关键伏笔
    var keyHooks = [];
    document.querySelectorAll('.nv-key-hook').forEach(function(row) {
      var text = row.querySelector('.nv-hook-text')?.value || '';
      if (text) {
        keyHooks.push({content: text});
      }
    });
    // 更新 _novelOutlineDict
    _novelOutlineDict = {
      theme: theme,
      core_conflict: coreConflict,
      story_arc: storyArc,
      world_anchor: worldAnchor,
      character_arcs: charArcs,
      key_hooks: keyHooks,
      ending: ending,
      tone: tone
    };
    api('/api/project/novel-outline', {
      method: 'POST',
      body: JSON.stringify({novel_outline: _novelOutlineDict})
    }).then(function() {
      showToast('✓ 全书大纲已保存');
    }).catch(function(e) {
      console.error('Save structured outline failed:', e);
      showToast('保存失败');
    });
    this.textContent = '💾 保存'; this.disabled = false;
  });
  // 清空全书大纲
  document.getElementById('btn-clear-novel-ol')?.addEventListener?.('click', async function() {
    if (!confirm('确定清空全书大纲？此操作不可撤销。')) return;
    _novelOutlineDict = {};
    await api('/api/project/novel-outline', {method: 'POST', body: JSON.stringify({novel_outline: {}})});
    renderNovelOutlineEditor();
    showToast('全书大纲已清空');
  });
  // 灵感碎片 → 全书大纲
  document.getElementById('btn-inspiration-to-novel-ol')?.addEventListener?.('click', async function() {
    var insp = document.getElementById('novel-inspiration-input')?.value?.trim();
    if (!insp) { showToast('请先输入灵感碎片'); return; }
    var btn = this;
    btn.textContent = '⏳ 生成中…'; btn.disabled = true;
    var genre = document.getElementById('current-chapter-label')?.textContent || '小说';
    var title = document.getElementById('project-name')?.textContent || (state && state.project && state.project.title) || '小说';
    var scale = document.getElementById('outline-scale')?.value || 'short';
    var scaleCfg = {short:10, mid:40, long:150, epic:300};
    var length = scaleCfg[scale] || 30;
    if (scale === 'custom') {
      length = parseInt(document.getElementById('outline-custom-chapters')?.value) || 10;
    }
    try {
      var r = await api('/api/generate/inspiration-to-novel-outline', {
        method: 'POST',
        body: JSON.stringify({inspiration: insp, title: title, genre: genre, length: length})
      });
      if (r.ok && r.outline) {
        // 处理结构化返回值（dict格式）
        if (typeof r.outline === 'object' && !Array.isArray(r.outline)) {
          _novelOutlineDict = r.outline;
        } else if (typeof r.outline === 'string') {
          _novelOutlineDict = {};
        }
        renderNovelOutlineEditor();
        showToast('灵感已生成全书大纲');
        // 自动保存
        api('/api/project/novel-outline', {
          method: 'POST',
          body: JSON.stringify({novel_outline: _novelOutlineDict})
        }).catch(function(e) { console.error('Save inspiration outline failed:', e); });
      } else {
        showToast('生成失败: ' + (r.error || '未知错误'));
      }
    } catch(e) { showToast('生成失败: ' + e.message); }
    btn.textContent = '🧠 灵感→大纲'; btn.disabled = false;
  });
  // 点击/聚焦字段时在中间详情编辑器打开 — 显示全书大纲所有字段
  document.querySelectorAll('.nv-field').forEach(function(el) {
    el.addEventListener('focus', function() {
      var key = this.dataset.key;
      var labels = {
        theme: '🎯 主题',
        core_conflict: '⚔️ 核心冲突',
        story_arc: '📖 故事走向',
        world_anchor: '🌍 世界观锚点',
        ending: '🏁 结局指引',
        tone: '🎭 基调'
      };
      // 构建全书大纲所有字段的 fields 数组
      var allFields = ['theme','core_conflict','story_arc','world_anchor','ending','tone'];
      var fields = [];
      allFields.forEach(function(fk) {
        var fEl = document.querySelector('.nv-field[data-key="' + fk + '"]');
        fields.push({
          key: 'field-' + fk,
          label: labels[fk] || fk,
          value: fEl ? (fEl.value || '') : '',
          type: fk === 'tone' ? 'text' : 'textarea',
          source: 'field',
          dataKey: fk
        });
      });
      // 角色弧光
      document.querySelectorAll('.nv-char-arc').forEach(function(row, idx) {
        var nameEl = row.querySelector('.nv-char-name');
        var arcEl = row.querySelector('.nv-char-arc-text');
        fields.push({
          key: 'char-arc-' + idx,
          label: '👤 角色弧光 #' + (idx + 1),
          type: 'char-arc',
          group: '角色弧光',
          charName: nameEl ? nameEl.value : '',
          arcText: arcEl ? arcEl.value : '',
          source: 'char-arc',
          arcIndex: idx
        });
      });
      // 关键伏笔
      document.querySelectorAll('.nv-key-hook').forEach(function(row, idx) {
        var hEl = row.querySelector('.nv-hook-text');
        fields.push({
          key: 'hook-' + idx,
          label: '🔮 关键伏笔 #' + (idx + 1),
          type: 'hook',
          group: '关键伏笔',
          value: hEl ? (hEl.value || '') : '',
          source: 'hook',
          hookIndex: idx
        });
      });
      showDetailEditor('全书大纲（全部）', '全书大纲 · 所有字段', null, {type: 'novel-outline-group', fields: fields});
    });
  });

  // 点击/聚焦角色弧光时 — 也显示全书大纲全部内容
  document.querySelectorAll('.nv-char-name').forEach(function(el) {
    el.addEventListener('focus', function() {
      var row = this.closest('.nv-char-arc');
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : 0;
      // 触发全书大纲整体显示
      var firstField = document.querySelector('.nv-field');
      if (firstField) firstField.dispatchEvent(new Event('focus'));
    });
  });
  document.querySelectorAll('.nv-char-arc-text').forEach(function(el) {
    el.addEventListener('focus', function() {
      var row = this.closest('.nv-char-arc');
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : 0;
      var firstField = document.querySelector('.nv-field');
      if (firstField) firstField.dispatchEvent(new Event('focus'));
    });
  });

  // 点击/聚焦关键伏笔时 — 也显示全书大纲全部内容
  document.querySelectorAll('.nv-hook-text').forEach(function(el) {
    el.addEventListener('focus', function() {
      var row = this.closest('.nv-key-hook');
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : 0;
      var firstField = document.querySelector('.nv-field');
      if (firstField) firstField.dispatchEvent(new Event('focus'));
    });
  });

  // 清空灵感碎片输入
  document.getElementById('btn-novel-inspiration-clear')?.addEventListener?.('click', function() {
    var inp = document.getElementById('novel-inspiration-input');
    if (inp) inp.value = '';
  });
}


window._renderNovelOutline = async function(container) {
  // 每次切到步骤2都强制从后端重新加载，确保数据最新
  try {
    var r = await api('/api/project/novel-outline');
    if (r.ok && r.novel_outline) {
      // 处理后端返回的dict格式（theme/core_conflict/story_arc等）
      if (typeof r.novel_outline === 'object' && !Array.isArray(r.novel_outline)) {
        _novelOutlineDict = r.novel_outline;
      } else if (Array.isArray(r.novel_outline) && r.novel_outline.length > 0) {
        _novelOutlineDict = { story_arc: '', theme: '', core_conflict: '', character_arcs: [], key_hooks: [], ending: '', tone: '', world_anchor: '' };
      }
    } else {
      _novelOutlineDict = {};
    }
  } catch(e) { console.error('加载全书大纲失败:', e); }
  renderNovelOutlineEditor();
}

/* ===== Chapter Outline Editor (Step 4) ===== */
window.renderChapterOutlineEditor = async function() {
  const ed = document.getElementById('chapter-outline-editor');
  ed.innerHTML = '';

  // 渲染全书大纲到独立容器已移至goToStep(step===2)中处理

  if (_currentChapterOutlineView !== 'edit') {
    switchChapterOutlineView(_currentChapterOutlineView);
    return;
  }

  // 渲染卷导航（替代旧的章节下拉选择器和目录列表）
  renderVolumeNav('vol-nav-outline', function(idx) {
    syncChapterAcrossPanels(idx);
    if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
  });

  // 显示当前章节信息
  var chNum = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  var chTitle = '';
  if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
    chTitle = chapters[currentChapterIndex].title || '';
  }


  if (!chOutline) chOutline = [];
  if (chOutline.length === 0) {
    // 初始化默认条目
    chOutline = [{text: '【在此输入第' + chNum + '章大纲要点】', current: true, source: 'human'}];
  }


  if (!chOutline) chOutline = [];
  if (chOutline.length === 0) {
    // 初始化默认条目
    chOutline = [{text: '【在此输入第' + chNum + '章大纲要点】', current: true, source: 'human'}];
  }

  const chSec = document.createElement('div');
  chSec.className = 'outline-section';
  const chHeader = document.createElement('div');
  chHeader.className = 'section-header expanded';
  // 获取当前章节的plot_line
  var currentPlotLines = [];
  if (typeof chapters !== 'undefined' && chapters[currentChapterIndex] && chapters[currentChapterIndex].blueprint) {
    currentPlotLines = chapters[currentChapterIndex].blueprint.plot_line || ['主线'];
  }
  if (!currentPlotLines.length) currentPlotLines = ['主线'];
  chHeader.innerHTML = '<span class="section-arrow">▶</span><h4>第' + chNum + '章大纲' + (chTitle ? ' · ' + chTitle : '') + '</h4><span class="group-count">' + chOutline.length + '</span>';
  const chBody = document.createElement('div');
  chBody.className = 'section-body';

  // 支线标签选择器
  var plotLineHtml = '<div style="padding:6px 12px;margin-bottom:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap">' +
    '<span class="text-xs text-muted" >剧情线:</span>';
  var allLines = ['主线', '支线A', '支线B', '支线C'];
  allLines.forEach(function(line) {
    var checked = currentPlotLines.indexOf(line) >= 0 ? 'checked' : '';
    plotLineHtml += '<label style="font-size:10px;display:flex;align-items:center;gap:2px;cursor:pointer">' +
      '<input class="text-xs" type="checkbox" value="' + line + '" ' + checked + ' onchange="updatePlotLine(this)" > ' + line +
    '</label>';
  });
  plotLineHtml += '</div>';

  // 灵感碎片输入区 — 用户输入碎片想法，AI分析后生成完整章节大纲
  var inspirationHtml = '<div style="padding:8px 12px;margin-bottom:6px;border-top:1px solid var(--border-soft);border-bottom:1px solid var(--border-soft)" id="ch-inspiration-box">' +
    '<div style="font-size:10px;color:var(--muted);margin-bottom:6px;display:flex;align-items:center;justify-content:space-between">' +
    '<span>💡 灵感碎片 → 章节主线</span>' +
    '</div>' +
    '<textarea id="ch-inspiration-input" placeholder="在这里写下你的碎片灵感、想法、场景…&#10;例如：主角在地铁上看到一个熟悉的背影，但追上去发现不是那个人…&#10;AI会分析你的想法，结合全书大纲生成完整的结构化章节大纲" ' +
    'style="width:100%;min-height:60px;max-height:120px;resize:vertical;padding:6px 8px;font-size:12px;line-height:1.5;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--ink);font-family:var(--sans);box-sizing:border-box"></textarea>' +
    '<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">' +
    '<button class="btn-sm ai" id="btn-engine-collide" title="引擎推演：基于角色关系六轴图自动检测碰撞冲突，生成灵感碎片" style="background:linear-gradient(135deg,#00b894,#00cec9);white-space:nowrap">⚡ 引擎推演</button>' +
    '<button class="btn-sm" id="btn-graph-view" title="查看角色关系图" style="white-space:nowrap">🕸️ 关系图</button>' +
    '<button class="btn-sm ai" id="btn-inspiration-to-blueprint" title="AI分析你的灵感碎片，生成完整章节大纲（起承转合blueprint）" style="background:linear-gradient(135deg,#6c5ce7,#a29bfe);white-space:nowrap">🧠 灵感→大纲</button>' +
    '<button class="btn-sm text-xs" id="btn-inspiration-clear" title="清空灵感输入" >🗑 清空</button>' +
    '</div>' +
    '</div>';

  // 本章人物节点
  var charNodeHtml = '<div style="padding:6px 12px;margin-bottom:6px;border-top:1px solid var(--border-soft)" id="ch-char-nodes-box">';
  charNodeHtml += '<div style="font-size:10px;color:var(--muted);margin-bottom:4px;display:flex;align-items:center;justify-content:space-between">';
  charNodeHtml += '<span>👥 本章人物</span>';
  charNodeHtml += '<select id="ch-char-add-select" onchange="addCharNodeToChapter(this.value)" style="font-size:10px;padding:2px 4px;border:1px solid var(--border);border-radius:3px;background:var(--bg);color:var(--ink)"><option value="">+ 添加人物</option></select>';
  charNodeHtml += '</div>';
  charNodeHtml += '<div id="ch-char-nodes-list" style="display:flex;flex-direction:column;gap:4px"></div>';
  charNodeHtml += '</div>';

  chBody.innerHTML = plotLineHtml + inspirationHtml + charNodeHtml + '<div class="outline-items flex-col-xs" id="ch-ol-items"></div><div class="section-actions"><button class="btn-sm ai" id="btn-ai-gen-ol">🤖 AI生成</button><button class="btn-sm ai" id="btn-ai-gen-all-ol" title="一键生成全部章节的结构化蓝图" style="background:linear-gradient(135deg,#4a90d9,#5cb85c)">🚀 一键生成全部</button><button class="btn-sm ai" id="btn-ai-next-item" title="基于当前大纲和已写内容，生成下一条大纲">➕ AI下一条</button><button class="btn-sm" id="btn-ai-opt-ol">✨ AI优化</button><button class="btn-sm btn-accent-border" id="btn-chapter-check" title="检测蓝图与全书大纲的一致性、逻辑漏洞和设定偏离" >🔍 整章检测</button><button class="btn-sm btn-accent-border" id="btn-open-bs-panel" title="打开灵感碎片面板" >🧠 灵感碎片</button><button class="btn-sm accept" id="btn-save-ol">💾 保存</button><button class="btn-sm" id="btn-clear-ol" title="清空当前章节的大纲和蓝图" style="background:rgba(212,80,80,0.1);color:var(--danger);border-color:rgba(212,80,80,0.3)">🗑 清空</button></div><div class="oi-add-row"><input type="text" placeholder="+ 自己输入条目，回车添加…" id="ch-ol-add"></div>';
  chSec.appendChild(chHeader);
  chSec.appendChild(chBody);
  ed.appendChild(chSec);
  chHeader.addEventListener('click', () => { chHeader.classList.toggle('expanded'); chBody.classList.toggle('collapsed'); });

  const items = document.getElementById('ch-ol-items');

  // 渲染结构化蓝图（仅当包含实质内容时显示）
  function _blueprintHasContent(bp) {
    if (!bp || typeof bp !== 'object') return false;
    if (bp.intro && (bp.intro.scene || bp.intro.trigger || bp.intro.atmosphere)) return true;
    if (bp.development && bp.development.length) return true;
    if (bp.climax && (bp.climax.conflict || bp.climax.twist)) return true;
    if (bp.ending && (bp.ending.new_state || bp.ending.next_hook)) return true;
    return false;
  }
  if (_blueprintHasContent(window._currentBlueprint)) {
    var bp = window._currentBlueprint;
    var bpHtml = '<div class="blueprint-container">';
    bpHtml += '<div class="blueprint-header"><span>📖 结构化章节蓝图 · 起承转合</span>';
    if (bp.word_target) bpHtml += '<span class="bp-word-target">目标 ' + esc(String(bp.word_target)) + ' 字</span>';
    bpHtml += '</div>';

    // 起 · 开场
    if (bp.intro) {
      var intro = bp.intro;
      bpHtml += '<div class="blueprint-section"><span class="bp-label bp-intro">起 · 开场</span><div class="bp-fields">';
      if (intro.scene) bpHtml += bpField('场景', intro.scene, 'intro.scene');
      if (intro.atmosphere) bpHtml += bpField('氛围', intro.atmosphere, 'intro.atmosphere');
      if (intro.trigger) bpHtml += bpField('触发', intro.trigger, 'intro.trigger');
      if (intro.word_count) bpHtml += bpField('字数', String(intro.word_count));
      bpHtml += '</div></div>';
    }

    // 承 · 发展
    if (bp.development && bp.development.length) {
      bpHtml += '<div class="blueprint-section"><span class="bp-label bp-dev">承 · 发展（' + bp.development.length + '个场景）</span>';
      bp.development.forEach(function(d, di) {
        bpHtml += '<div class="bp-dev-item" data-dev-idx="' + di + '"><div class="bp-dev-scene">' + (di+1) + '. ' + esc(d.scene||'') ;
        if (d.characters && d.characters.length) {
          bpHtml += '<span class="bp-dev-chars">';
          d.characters.forEach(function(c) { bpHtml += '<span class="bp-char-tag">' + esc(c) + '</span>'; });
          bpHtml += '</span>';
        }
        bpHtml += '<button class="sra-btn del bp-del-dev" data-dev-idx="' + di + '" title="删除此场景" style="float:right">×</button>';
        bpHtml += '</div>';
        bpHtml += '<div class="bp-fields">';
        if (d.location) bpHtml += bpField('地点', d.location);
        if (d.event) bpHtml += bpField('事件', d.event);
        if (d.choice) bpHtml += bpField('选择', d.choice);
        if (d.cost) bpHtml += bpField('代价', d.cost);
        if (d.info_reveal) bpHtml += bpField('信息释放', d.info_reveal);
        bpHtml += '</div></div>';
      });
      bpHtml += '</div>';
    }

    // 转 · 高潮
    if (bp.climax) {
      var cl = bp.climax;
      bpHtml += '<div class="blueprint-section"><span class="bp-label bp-climax">转 · 高潮</span><div class="bp-fields">';
      if (cl.conflict) bpHtml += bpField('冲突', cl.conflict, 'climax.conflict');
      if (cl.key_choice) bpHtml += bpField('关键选择', cl.key_choice, 'climax.key_choice');
      if (cl.cost) bpHtml += bpField('代价', cl.cost, 'climax.cost');
      if (cl.twist) bpHtml += bpField('转折', cl.twist, 'climax.twist');
      bpHtml += '</div></div>';
    }

    // 合 · 结尾
    if (bp.ending) {
      var bpEnding = bp.ending;
      bpHtml += '<div class="blueprint-section"><span class="bp-label bp-ending">合 · 结尾</span><div class="bp-fields">';
      if (bpEnding.new_state) bpHtml += bpField('新状态', bpEnding.new_state, 'ending.new_state');
      if (bpEnding.info_reveal) bpHtml += bpField('信息揭露', bpEnding.info_reveal, 'ending.info_reveal');
      if (bpEnding.next_hook) bpHtml += bpField('下章钩子', bpEnding.next_hook, 'ending.next_hook');
      bpHtml += '</div></div>';
    }

    // 蓝图操作按钮
    bpHtml += '<div class="blueprint-actions">';
    bpHtml += '<button class="btn-sm accept" id="bp-adopt">✓ 采纳为大纲条目</button>';
    bpHtml += '<button class="btn-sm" id="bp-dismiss">✕ 关闭蓝图</button>';
    bpHtml += '<button class="btn-sm ai" id="bp-regen">🔄 重新生成</button>';
    bpHtml += '</div>';
    bpHtml += '</div>';

    var bpDiv = document.createElement('div');
    bpDiv.innerHTML = bpHtml;
    items.appendChild(bpDiv.firstChild);

    // P3-16: 蓝图字段局部编辑 — blur时保存到 window._currentBlueprint
    document.querySelectorAll('.bp-val').forEach(function(el) {
      // 点击字段时，在中间编辑器显示整个蓝图的所有字段（多字段表单模式）
      el.addEventListener('click', function(e) {
        if (e.target !== this) return;
        if (!window._currentBlueprint) return;
        var bp = window._currentBlueprint;
        var chNum = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
        var chTitle = (typeof chapters !== 'undefined' && chapters[currentChapterIndex] && chapters[currentChapterIndex].title) ? chapters[currentChapterIndex].title : ('第' + chNum + '章');

        // 收集整个蓝图的所有字段，构建 fields 数组
        var fields = [];
        // 起 · 开场
        if (bp.intro) {
          if (bp.intro.scene) fields.push({key:'bp-intro-scene', label:'场景', value: bp.intro.scene || '', type:'textarea', group:'起 · 开场', bpPath:'intro.scene'});
          if (bp.intro.atmosphere) fields.push({key:'bp-intro-atm', label:'氛围', value: bp.intro.atmosphere || '', type:'textarea', group:'起 · 开场', bpPath:'intro.atmosphere'});
          if (bp.intro.trigger) fields.push({key:'bp-intro-trigger', label:'触发', value: bp.intro.trigger || '', type:'textarea', group:'起 · 开场', bpPath:'intro.trigger'});
        }
        // 承 · 发展
        if (bp.development && bp.development.length) {
          bp.development.forEach(function(d, di) {
            var grpName = '承 · 发展 · 场景' + (di + 1);
            if (d.scene) fields.push({key:'bp-dev-'+di+'-scene', label:'场景', value: d.scene || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.scene'});
            if (d.location) fields.push({key:'bp-dev-'+di+'-loc', label:'地点', value: d.location || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.location'});
            if (d.event) fields.push({key:'bp-dev-'+di+'-event', label:'事件', value: d.event || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.event'});
            if (d.choice) fields.push({key:'bp-dev-'+di+'-choice', label:'选择', value: d.choice || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.choice'});
            if (d.cost) fields.push({key:'bp-dev-'+di+'-cost', label:'代价', value: d.cost || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.cost'});
            if (d.info_reveal) fields.push({key:'bp-dev-'+di+'-info', label:'信息释放', value: d.info_reveal || '', type:'textarea', group: grpName, bpPath:'development.'+di+'.info_reveal'});
          });
        }
        // 转 · 高潮
        if (bp.climax) {
          if (bp.climax.conflict) fields.push({key:'bp-climax-conflict', label:'冲突', value: bp.climax.conflict || '', type:'textarea', group:'转 · 高潮', bpPath:'climax.conflict'});
          if (bp.climax.key_choice) fields.push({key:'bp-climax-choice', label:'关键选择', value: bp.climax.key_choice || '', type:'textarea', group:'转 · 高潮', bpPath:'climax.key_choice'});
          if (bp.climax.cost) fields.push({key:'bp-climax-cost', label:'代价', value: bp.climax.cost || '', type:'textarea', group:'转 · 高潮', bpPath:'climax.cost'});
          if (bp.climax.twist) fields.push({key:'bp-climax-twist', label:'转折', value: bp.climax.twist || '', type:'textarea', group:'转 · 高潮', bpPath:'climax.twist'});
        }
        // 合 · 结尾
        if (bp.ending) {
          if (bp.ending.new_state) fields.push({key:'bp-ending-state', label:'新状态', value: bp.ending.new_state || '', type:'textarea', group:'合 · 结尾', bpPath:'ending.new_state'});
          if (bp.ending.info_reveal) fields.push({key:'bp-ending-info', label:'信息揭露', value: bp.ending.info_reveal || '', type:'textarea', group:'合 · 结尾', bpPath:'ending.info_reveal'});
          if (bp.ending.next_hook) fields.push({key:'bp-ending-hook', label:'下章钩子', value: bp.ending.next_hook || '', type:'textarea', group:'合 · 结尾', bpPath:'ending.next_hook'});
        }

        if (typeof showDetailEditor === 'function') {
          showDetailEditor(chTitle + ' · 结构化蓝图', '起承转合蓝图 · 共' + fields.length + '个字段', null, {
            type: 'blueprint-group',
            fields: fields
          });
        }
      });
      // blur时保存
      if (el.dataset.bpPath) {
        el.addEventListener('blur', function() {
          var path = this.dataset.bpPath;
          var newVal = this.textContent || '';
          if (!path || !window._currentBlueprint) return;
          var parts = path.split('.');
          var obj = window._currentBlueprint;
          for (var i = 0; i < parts.length - 1; i++) {
            if (obj[parts[i]]) obj = obj[parts[i]];
          }
          obj[parts[parts.length - 1]] = newVal;
          // 同步到 chapters
          if (chapters && chapters[currentChapterIndex]) {
            chapters[currentChapterIndex].blueprint = window._currentBlueprint;
          }
        });
      }
    });

    // 删除蓝图中的发展场景
    document.querySelectorAll('.bp-del-dev').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        if (!window._currentBlueprint || !window._currentBlueprint.development) return;
        var idx = parseInt(this.dataset.devIdx);
        window._currentBlueprint.development.splice(idx, 1);
        if (chapters && chapters[currentChapterIndex]) {
          chapters[currentChapterIndex].blueprint = window._currentBlueprint;
        }
        renderChapterOutlineEditor();
        showToast('已删除场景');
      });
    });

    // 采纳蓝图 → 转为大纲条目
    document.getElementById('bp-adopt')?.addEventListener?.('click', function() {
      var newItems = [];
      if (bp.intro) newItems.push({text: '【起】' + (bp.intro.scene||'') + ' — ' + (bp.intro.trigger||''), current: false, source: 'ai'});
      (bp.development||[]).forEach(function(d) { newItems.push({text: '【承】' + (d.scene||'') + '：' + (d.event||''), current: false, source: 'ai'}); });
      if (bp.climax) newItems.push({text: '【转】' + (bp.climax.conflict||'') + ' — ' + (bp.climax.twist||''), current: false, source: 'ai'});
      if (bp.ending) newItems.push({text: '【合】' + (bp.ending.new_state||'') + ' → ' + (bp.ending.next_hook||''), current: false, source: 'ai'});
      chOutline = newItems;
      window._currentBlueprint = null;
      window._aiSuggestions = [];
      renderChapterOutlineEditor();
      saveChapterOutline();
      showToast('✓ 蓝图已转为 ' + newItems.length + ' 条大纲条目');
    });

    document.getElementById('bp-dismiss')?.addEventListener?.('click', function() {
      window._currentBlueprint = null;
      renderChapterOutlineEditor();
    });

    document.getElementById('bp-regen')?.addEventListener?.('click', function() {
      window._currentBlueprint = null;
      document.getElementById('btn-ai-gen-ol')?.click();
    });
  }

  if (!window._currentBlueprint) {
  chOutline.forEach((o, i) => {
    const row = document.createElement('div');
    row.className = 'outline-item' + (o.current ? ' current' : '') + (o.source === 'ai' ? ' suggested' : '');
    row.innerHTML = '<div class="oi-main"><span class="oi-num">' + (i + 1) + '.</span><textarea class="oi-input" rows="1">' + o.text.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea>' + (o.source === 'ai' ? '<span class="suggest-badge">AI 建议</span>' : '') + '</div><div class="oi-actions-row"><button class="sra-btn ft-gen" title="AI生成">🤖</button><button class="sra-btn ft-opt" title="AI优化">✨</button><button class="sra-btn ft-check" title="检测">🔍</button><button class="sra-btn del" title="删除">×</button></div>';
    row.querySelector('.oi-input').addEventListener('input', function() { chOutline[i].text = this.value; chOutline[i].source = 'human-edited'; saveChapterOutline(); });
    row.querySelector('.oi-input').addEventListener('click', () => { chOutline.forEach((_, j) => chOutline[j].current = j === i); renderChapterOutlineEditor(); });
    // 点击整行打开详情编辑器 — 显示整个章节大纲的所有条目
    row.addEventListener('click', function(e) {
      if (e.target.closest('.sra-btn')) return;
      document.querySelectorAll('.outline-item').forEach(r => r.classList.remove('active'));
      row.classList.add('active');
      // 构建字段数组 — 多字段表单模式
      var fields = (chOutline || []).map(function(item, idx) {
        return {
          key: 'outline-' + idx,
          label: String(idx + 1) + '.',
          value: item.text || '',
          type: 'textarea',
          outlineIndex: idx
        };
      });
      var chTitle = (typeof chapters !== 'undefined' && chapters[currentChapterIndex] && chapters[currentChapterIndex].title) ? chapters[currentChapterIndex].title : ('第' + chNum + '章');
      showDetailEditor(chTitle + ' · 大纲（全部）', '章节大纲 · 共' + chOutline.length + '条', null, {type: 'outline-group', chNum: chNum, fields: fields});
    });
    row.querySelector('.del').addEventListener('click', e => { e.stopPropagation(); chOutline.splice(i, 1); if (!chOutline.length) chOutline.push({text: '[在此输入大纲条目]', current: true, source: 'human'}); renderChapterOutlineEditor(); saveChapterOutline(); showToast('已删除'); });
    row.querySelector('.ft-gen').addEventListener('click', async function() {
      this.disabled = true; this.textContent = '⏳';
      try {
        const prompt = '请为小说情节要点生成内容。只返回内容文本，不要解释。';
        const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
        if (r.ok && r.content) { row.querySelector('.oi-input').value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim(); row.querySelector('.oi-input').dispatchEvent(new Event('input')); showToast('✅ AI已生成'); }
        else showToast('❌ 生成失败');
      } catch(e) { showToast('❌ ' + e.message); }
      this.disabled = false; this.textContent = '🤖';
    });
    row.querySelector('.ft-opt').addEventListener('click', async function() {
      const inp = row.querySelector('.oi-input');
      if (!inp.value.trim()) { showToast('⚠️ 内容为空'); return; }
      this.disabled = true; this.textContent = '⏳';
      try {
        const prompt = '请优化以下文本，保持原意，让表达更精炼有力：\n' + inp.value.trim();
        const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
        if (r.ok && r.content) { inp.value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim(); inp.dispatchEvent(new Event('input')); showToast('✅ 已优化'); }
        else showToast('❌ 优化失败');
      } catch(e) { showToast('❌ ' + e.message); }
      this.disabled = false; this.textContent = '✨';
    });
    row.querySelector('.ft-check').addEventListener('click', async function() {
      const inp = row.querySelector('.oi-input');
      if (!inp || !inp.value.trim()) { showToast('⚠️ 内容为空'); return; }
      showToast('🔍 检测中...');
      try {
        await runCheck('quality', inp.value.trim(), 'chapter-outline');
        showToast('✓ 检测完成');
      } catch(e) {
        showToast('检测失败: ' + e.message);
      }
    });
    items.appendChild(row);
  });
  }

  // AI suggestions
  if (!window._currentBlueprint && window._aiSuggestions && window._aiSuggestions.length) {
    window._aiSuggestions.forEach((s, si) => {
      const sr = document.createElement('div');
      sr.className = 'outline-item suggested';
      sr.innerHTML = '<span class="oi-num text-info" >' + (chOutline.length + si + 1) + '.</span><textarea class="oi-input text-info" rows="1" >' + s.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea><span class="suggest-badge">新增建议</span>';
      sr.querySelector('.oi-input').addEventListener('input', function() { window._aiSuggestions[si] = this.value; });
      items.appendChild(sr);
    });
    const actDiv = document.createElement('div');
    actDiv.innerHTML = '<button class="btn-sm accept" id="btn-accept-all-suggestions">✓ 全部采纳</button><button class="btn-sm reject" id="btn-reject-all-suggestions">✕ 全部拒绝</button>';
    items.appendChild(actDiv);
    document.getElementById('btn-accept-all-suggestions')?.addEventListener?.('click', () => { window._aiSuggestions.forEach(s => chOutline.push({text: s, current: false, source: 'ai'})); window._aiSuggestions = []; renderChapterOutlineEditor(); showToast('✓ AI 建议已采纳'); });
    document.getElementById('btn-reject-all-suggestions')?.addEventListener?.('click', () => { window._aiSuggestions = []; renderChapterOutlineEditor(); showToast('AI 建议已拒绝'); });
  }

  document.getElementById('ch-ol-add')?.addEventListener?.('keydown', function(e) { if (e.key === 'Enter' && this.value.trim()) { chOutline.push({text: this.value.trim(), current: false, source: 'human'}); this.value = ''; renderChapterOutlineEditor(); saveChapterOutline(); showToast('✓ 已添加'); } });

  // 有蓝图时隐藏线性条目输入框
  var oiAddRow = document.querySelector('.oi-add-row');
  if (window._currentBlueprint && oiAddRow) {
    oiAddRow.style.display = 'none';
  } else if (oiAddRow) {
    oiAddRow.style.display = '';
  }

  // 清空当前章节的大纲和蓝图（移除confirm避免阻塞自动化；改用双击确认）
  var _clearOlTimer = null;
  document.getElementById('btn-clear-ol')?.addEventListener?.('click', function() {
    var btn = this;
    if (!_clearOlTimer) {
      _clearOlTimer = setTimeout(function() { _clearOlTimer = null; btn.textContent = '🗑 清空'; }, 3000);
      btn.textContent = '⚠️ 再点确认清空';
      btn.style.background = '#c44';
      btn.style.color = '#fff';
      return;
    }
    clearTimeout(_clearOlTimer);
    _clearOlTimer = null;
    btn.textContent = '🗑 清空';
    btn.style.background = '';
    btn.style.color = '';
    chOutline = [{text: '【在此输入大纲条目】', current: true, source: 'human'}];
    window._currentBlueprint = null;
    window._aiSuggestions = [];
    // 清空后端保存的大纲和蓝图
    if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
      chapters[currentChapterIndex].outline = '';
      chapters[currentChapterIndex].blueprint = null;
    }
    api('/api/chapter/outline', {
      method: 'POST',
      body: JSON.stringify({index: currentChapterIndex, outline: '', blueprint: null})
    }).catch(function(e) { console.error('Clear outline failed:', e); });
    renderChapterOutlineEditor();
    showToast('已清空大纲和蓝图');
  });

  // btn-ai-check 已移除
  document.getElementById('btn-ai-gen-ol')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 生成中…'; this.disabled = true;
    try {
    const title = document.getElementById('editor-title').textContent;
    // 构建上下文：加入章节序号、前一章内容
    var ctx = '';
    var chNum = currentChapterIndex + 1;
    ctx += '\n当前是第' + chNum + '章。';
    if (typeof worldSettings !== 'undefined' && worldSettings.length > 0) {
      ctx += '\n小说设定：\n' + worldSettings.map(function(s) { return s.key + '：' + s.val; }).join('\n');
    }
    // 传入故事总览
    if (typeof novel_acts !== 'undefined' && novel_acts.length > 0) {
      ctx += '\n全书大纲（幕级）：\n' + novel_acts.map(function(a) { return a.title || ''; }).join('\n');
    }
    // 传入人物档案
    if (typeof characters !== 'undefined' && characters.length > 0) {
      ctx += '\n主要人物：' + characters.slice(0, 8).map(function(c) { return c.name + '(' + (c.identity || c.role || '') + ')'; }).join('；') + '\n';
      var charDetails = characters.slice(0, 6).map(function(c) {
        var d = c.name;
        if (c.personality) d += '（性格：' + c.personality.substring(0, 50) + '）';
        if (c.background) d += '（背景：' + c.background.substring(0, 80) + '）';
        if (c.goal) d += '（目标：' + c.goal.substring(0, 50) + '）';
        return d;
      });
      ctx += '人物档案：\n' + charDetails.join('\n') + '\n';
    }
    // 传入前一章的大纲（完整，不截断）和正文摘要
    if (currentChapterIndex > 0) {
      var prevCh = (typeof chapters !== 'undefined') ? chapters[currentChapterIndex - 1] : null;
      if (prevCh) {
        var prevContent = prevCh.content || prevCh.text || '';
        if (prevContent.length > 800) prevContent = prevContent.substring(0, 800) + '...';
        ctx += '\n前一章（第' + currentChapterIndex + '章）内容摘要：\n' + prevContent + '\n';
      }
      // 前一章的大纲（完整）
      if (typeof chapterOutlines !== 'undefined' && chapterOutlines[currentChapterIndex - 1]) {
        ctx += '\n【前一章大纲（第' + currentChapterIndex + '章）】\n' + chapterOutlines[currentChapterIndex - 1] + '\n';
      }
      // 前一章blueprint中的ending和next_hook
      var _prevBp = (typeof chapters !== 'undefined' && chapters[currentChapterIndex - 1]) ? chapters[currentChapterIndex - 1].blueprint : null;
      if (_prevBp && _prevBp.ending) {
        if (_prevBp.ending.new_state) ctx += '前一章结尾状态：' + _prevBp.ending.new_state + '\n';
        if (_prevBp.ending.next_hook) ctx += '前一章钩子/悬念：' + _prevBp.ending.next_hook + '\n';
      }
    }
    ctx += '\n请为第' + chNum + '章生成大纲。' + (currentChapterIndex > 0 ? '必须与前一章自然衔接，不要重复前一章的场景和事件。' : '这是第一章，需要有开场感。') + '每章内容必须不同。';
    const r = await generateChapterOutline(title, ctx, currentChapterIndex);
    if (r && r.ok && (r.outline || r.blueprint)) {
      // 结构化蓝图模式：后端返回 blueprint dict
      if (r.blueprint) {
        window._currentBlueprint = r.blueprint;
        // 同时生成兼容的扁平建议列表
        var bp = r.blueprint;
        var suggestions = [];
        if (bp.intro) suggestions.push('【起】' + (bp.intro.scene||'') + ' — ' + (bp.intro.trigger||''));
        (bp.development||[]).forEach(function(d) { suggestions.push('【承】' + (d.scene||'') + '：' + (d.event||'')); });
        if (bp.climax) suggestions.push('【转】' + (bp.climax.conflict||'') + ' — ' + (bp.climax.twist||''));
        if (bp.ending) suggestions.push('【合】' + (bp.ending.new_state||'') + ' → ' + (bp.ending.next_hook||''));
        window._aiSuggestions = suggestions;
      } else {
        // 兼容模式：尝试从raw中解析JSON，失败则按行切分（过滤JSON语法行）
        var rawText = r.outline || r.raw || '';
        // 尝试从raw中提取JSON blueprint
        try {
          var jsonMatch = rawText.match(/```json\s*\n([\s\S]*?)\n```/) || rawText.match(/(\{[\s\S]*"intro"[\s\S]*\})/);
          if (jsonMatch) {
            var parsed = JSON.parse(jsonMatch[1] || jsonMatch[0]);
            if (parsed && parsed.intro) {
              window._currentBlueprint = parsed;
              var s2 = [];
              if (parsed.intro) s2.push('【起】' + (parsed.intro.scene||'') + ' — ' + (parsed.intro.trigger||''));
              (parsed.development||[]).forEach(function(d) { s2.push('【承】' + (d.scene||'') + '：' + (d.event||'')); });
              if (parsed.climax) s2.push('【转】' + (parsed.climax.conflict||'') + ' — ' + (parsed.climax.twist||''));
              if (parsed.ending) s2.push('【合】' + (parsed.ending.new_state||'') + ' → ' + (parsed.ending.next_hook||''));
              window._aiSuggestions = s2;
            } else {
              window._aiSuggestions = [];
              window._currentBlueprint = null;
            }
          } else {
            // 不是JSON，按行切分，过滤JSON语法行
            const lines = rawText.split('\n').filter(l => {
              var t = l.trim();
              return t && !t.startsWith('#') && !t.startsWith('{') && !t.startsWith('}') && !t.startsWith('```') && !t.startsWith('"') && !t.startsWith('[') && !t.startsWith(']');
            });
            window._aiSuggestions = lines.map(l => l.replace(/^[-\d\.\s]+/, '').trim());
            window._currentBlueprint = null;
          }
        } catch(e) {
          window._aiSuggestions = [];
          window._currentBlueprint = null;
        }
      }
      renderChapterOutlineEditor();
      // 自动保存到后端，防止切换章节时丢失
      try {
        // 如果AI生成了建议但chOutline还是旧的，用建议重建chOutline
        if (window._aiSuggestions && window._aiSuggestions.length > 0) {
          var isDefault = chOutline.length === 1 && chOutline[0].text.indexOf('在此输入') !== -1;
          if (isDefault) {
            chOutline = window._aiSuggestions.map(function(s) { return {text: s, current: false, source: 'ai'}; });
          }
        }
        // 构建大纲文本：优先用chOutline，如果有blueprint但chOutline为空则从blueprint生成
        var outlineText = chOutline.map(o => o.text).join('\n');
        if (!outlineText.trim() || outlineText.indexOf('在此输入') !== -1) {
          if (window._currentBlueprint) {
            var bp2 = window._currentBlueprint;
            var bpParts = [];
            if (bp2.intro) bpParts.push('【起】' + (bp2.intro.scene||'') + ' — ' + (bp2.intro.trigger||''));
            (bp2.development||[]).forEach(function(d) { bpParts.push('【承】' + (d.scene||'') + '：' + (d.event||'')); });
            if (bp2.climax) bpParts.push('【转】' + (bp2.climax.conflict||'') + ' — ' + (bp2.climax.twist||''));
            if (bp2.ending) bpParts.push('【合】' + (bp2.ending.new_state||'') + ' → ' + (bp2.ending.next_hook||''));
            outlineText = bpParts.join('\n');
          }
        }
        var saveData = {index: currentChapterIndex, outline: outlineText};
        if (window._currentBlueprint) saveData.blueprint = window._currentBlueprint;
        await api('/api/chapter/outline', {method: 'POST', body: JSON.stringify(saveData)});
        // 同步到内存（保存字符串而非数组）
        if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
          chapters[currentChapterIndex].outline = outlineText;
          if (window._currentBlueprint) chapters[currentChapterIndex].blueprint = window._currentBlueprint;
        }
      } catch(e) { console.error('Auto-save outline failed:', e); }
      showToast(r.blueprint ? '🤖 AI 已生成结构化蓝图（已自动保存）' : '🤖 AI 已生成 ' + (window._aiSuggestions?.length||0) + ' 条建议（已自动保存）');
    } else { showToast('生成失败：' + (r && r.error ? r.error : '未知错误')); }
    } catch(err) { showToast('❌ 生成出错：' + err.message); console.error('AI生成大纲失败:', err); }
    this.textContent = '🤖 AI生成'; this.disabled = false;
  });

  // 一键生成全部章节大纲（事件委托，双击确认代替confirm）
  var _genAllTimer = null;
  document.addEventListener('click', async function(e) {
    if (e.target.id !== 'btn-ai-gen-all-ol' || e.target.disabled) return;
    if (!_genAllTimer) {
      _genAllTimer = setTimeout(function() { _genAllTimer = null; e.target.textContent = '🚀 全部生成'; }, 3000);
      e.target.textContent = '⚠️ 再点确认（全部）';
      e.target.style.background = '#c44';
      return;
    }
    clearTimeout(_genAllTimer);
    _genAllTimer = null;
    e.target.textContent = '🚀 全部生成';
    e.target.style.background = '';
    e.target.textContent = '⏳ 批量生成中…'; e.target.disabled = true;
    showToast('🚀 开始批量生成全部章节大纲…');
    try {
      const r = await api('/api/generate/all-chapter-outlines', {method: 'POST', body: JSON.stringify({})});
      if (r.ok) {
        var successCount = (r.results||[]).filter(function(x){return x.has_blueprint}).length;
        showToast('✅ 批量生成完成！成功 ' + successCount + '/' + r.count + ' 章有结构化蓝图');
        // 重新加载当前章节大纲
        if (typeof loadChapterOutline === 'function') loadChapterOutline(currentChapterIndex);
        if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
        // 重新加载章节列表
        if (typeof loadChaptersFromAPI === 'function') loadChaptersFromAPI();


      } else {
        showToast('❌ 批量生成失败：' + (r.error || '未知错误'));
      }
    } catch(e2) {
      showToast('❌ 网络错误：' + e2.message);
    }
    e.target.textContent = '🚀 一键生成全部'; e.target.disabled = false;
  });

  document.getElementById('btn-open-bs-panel')?.addEventListener?.('click', function() {
    openBrainstormPanel();
  });

  // 🔍 整章检测：检测蓝图/大纲与全书大纲的一致性
  document.getElementById('btn-chapter-check')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 检测中…'; this.disabled = true;
    showToast('🔍 正在检测整章大纲…');
    try {
      // 收集蓝图+大纲条目作为检测内容
      var bp = window._currentBlueprint;
      var outlineText = '';
      if (bp) {
        var parts = [];
        if (bp.title) parts.push('标题: ' + bp.title);
        if (bp.intro) parts.push('【起】' + (bp.intro.scene || '') + ' — ' + (bp.intro.trigger || ''));
        if (bp.development) bp.development.forEach(function(d) { parts.push('【承】' + (d.scene || '') + '：' + (d.event || '')); });
        if (bp.climax) parts.push('【转】' + (bp.climax.conflict || '') + ' — ' + (bp.climax.twist || ''));
        if (bp.ending) parts.push('【合】' + (bp.ending.new_state || '') + ' → ' + (bp.ending.next_hook || ''));
        outlineText = parts.join('\n');
      }
      // 同时收集大纲条目
      var items = (typeof chOutline !== 'undefined' ? chOutline : []).map(function(o) { return o.text || ''; }).filter(function(t) { return t && t.indexOf('【在此输入') === -1 && t !== '[在此输入大纲条目]'; });
      if (items.length) outlineText += (outlineText ? '\n\n' : '') + '【大纲条目】\n' + items.join('\n');
      if (!outlineText.trim()) { showToast('⚠️ 当前章节没有大纲内容，请先生成'); this.textContent = '🔍 整章检测'; this.disabled = false; return; }
      // 调用 batch 检查
      await runCheck('batch', outlineText, 'chapter-outline');
      showToast('✓ 整章检测完成');
    } catch(e) {
      console.error('整章检测失败:', e);
      showToast('检测失败: ' + e.message);
    }
    this.textContent = '🔍 整章检测'; this.disabled = false;
  });

  document.getElementById('btn-inspiration-clear')?.addEventListener?.('click', function() {
    var inp = document.getElementById('ch-inspiration-input');
    if (inp) { inp.value = ''; inp.focus(); }
  });
  // ⚡ 引擎推演 — 调用碰撞引擎生成灵感碎片
  document.getElementById('btn-engine-collide')?.addEventListener?.('click', async function() {
    var _engBtn = this;
    _engBtn.textContent = '⚡ 推演中…'; _engBtn.disabled = true;
    try {
      var r = await api('/api/engine/collide', { method: 'POST', body: '{}' });
      if (r && r.ok && r.inspirations && r.inspirations.length > 0) {
        var inp = document.getElementById('ch-inspiration-input');
        if (inp) {
          // 将所有碰撞灵感拼接填入灵感输入框
          var text = r.inspirations.map(function(ins, i) {
            return '【碰撞' + (i+1) + '·' + (ins.title || '未命名') + '】' + ins.desc;
          }).join('\n\n');
          inp.value = text;
        }
        showToast('✅ 引擎推演完成，检测到 ' + r.inspirations.length + ' 个碰撞灵感，已填入灵感框');
      } else {
        showToast(r?.error || '⚠️ 未检测到碰撞事件，请先在角色档案中添加角色关系');
      }
    } catch(e) {
      showToast('❌ 引擎推演异常：' + e.message);
    }
    _engBtn.textContent = '⚡ 引擎推演'; _engBtn.disabled = false;
  });

  // 🕸️ 关系图可视化
  document.getElementById('btn-graph-view')?.addEventListener?.('click', function() {
    openGraphView();
  });


  // 灵感碎片 → 结构化章节大纲
  document.getElementById('btn-inspiration-to-blueprint')?.addEventListener?.('click', async function() {
    var inspirationInput = document.getElementById('ch-inspiration-input');
    var inspiration = inspirationInput ? inspirationInput.value.trim() : '';
    if (!inspiration) { showToast('⚠️ 请先输入灵感碎片内容'); if (inspirationInput) inspirationInput.focus(); return; }

    var _inspBtn = this;
    _inspBtn.textContent = '🧠 分析中…'; _inspBtn.disabled = true;
    // 锁定章节索引
    var _inspChapterIdx = currentChapterIndex;

    try {
      var title = document.getElementById('editor-title').textContent;
      var chNum = _inspChapterIdx + 1;
      // 构建上下文（与 btn-ai-gen-ol 相同的逻辑）
      var ctx = '';
      ctx += '\n当前是第' + chNum + '章。';
      if (typeof worldSettings !== 'undefined' && worldSettings.length > 0) {
        ctx += '\n小说设定：\n' + worldSettings.map(function(s) { return s.key + '：' + s.val; }).join('\n');
      }
      if (typeof novel_acts !== 'undefined' && novel_acts.length > 0) {
        ctx += '\n全书大纲（幕级）：\n' + novel_acts.map(function(a) { return a.title || ''; }).join('\n');
      }
      if (typeof characters !== 'undefined' && characters.length > 0) {
        ctx += '\n主要人物：' + characters.slice(0, 8).map(function(c) { return c.name + '(' + (c.identity || c.role || '') + ')'; }).join('；') + '\n';
      }
      // 前一章上下文
      if (_inspChapterIdx > 0) {
        var prevCh = (typeof chapters !== 'undefined') ? chapters[_inspChapterIdx - 1] : null;
        if (prevCh) {
          var prevContent = prevCh.content || prevCh.text || '';
          if (prevContent.length > 800) prevContent = prevContent.substring(0, 800) + '...';
          ctx += '\n前一章内容摘要：\n' + prevContent + '\n';
        }
        var _prevBp = (typeof chapters !== 'undefined' && chapters[_inspChapterIdx - 1]) ? chapters[_inspChapterIdx - 1].blueprint : null;
        if (_prevBp && _prevBp.ending) {
          if (_prevBp.ending.new_state) ctx += '前一章结尾状态：' + _prevBp.ending.new_state + '\n';
          if (_prevBp.ending.next_hook) ctx += '前一章钩子/悬念：' + _prevBp.ending.next_hook + '\n';
        }
      }

      // 调用后端灵感→大纲接口
      var r = await api('/api/generate/inspiration-to-blueprint', {
        method: 'POST',
        body: JSON.stringify({
          title: title,
          inspiration: inspiration,
          context: ctx,
          chapter_index: _inspChapterIdx
        })
      });

      if (r && r.ok && (r.outline || r.blueprint)) {
        // 复用现有blueprint渲染流程（与 btn-ai-gen-ol 相同）
        if (r.blueprint) {
          window._currentBlueprint = r.blueprint;
          var bp = r.blueprint;
          var suggestions = [];
          if (bp.intro) suggestions.push('【起】' + (bp.intro.scene||'') + ' — ' + (bp.intro.trigger||''));
          (bp.development||[]).forEach(function(d) { suggestions.push('【承】' + (d.scene||'') + '：' + (d.event||'')); });
          if (bp.climax) suggestions.push('【转】' + (bp.climax.conflict||'') + ' — ' + (bp.climax.twist||''));
          if (bp.ending) suggestions.push('【合】' + (bp.ending.new_state||'') + ' → ' + (bp.ending.next_hook||''));
          window._aiSuggestions = suggestions;
        }
        // 保存到后端
        if (typeof chapters !== 'undefined' && chapters[_inspChapterIdx]) {
          if (r.blueprint) chapters[_inspChapterIdx].blueprint = r.blueprint;
        }
        renderChapterOutlineEditor();
        showToast('✅ 灵感已转化为章节大纲');
      } else {
        showToast(r.error || '灵感→大纲生成失败');
      }
    } catch(e) {
      showToast('❌ 灵感→大纲异常：' + e.message);
    }
    _inspBtn.textContent = '🧠 灵感→大纲'; _inspBtn.disabled = false;
  });

  document.getElementById('btn-ai-opt-ol')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 优化中…'; this.disabled = true;
    const lines = chOutline.map(o => o.text).join('\n');
    const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: '请优化以下章节大纲条目：\n' + lines}]})});
    if (r.ok && r.content) {
      const opts = r.content.split('\n').filter(l => l.trim());
      chOutline = opts.map(l => ({text: l.replace(/^[-\d\.\s]+/, '').trim(), current: false, source: 'ai'}));
      renderChapterOutlineEditor(); showToast('✓ 本章大纲已优化');
    } else { showToast('优化失败'); }
    this.textContent = '✨ AI优化'; this.disabled = false;
  });

  // AI生成下一条大纲
  document.getElementById('btn-ai-next-item')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 生成中…'; this.disabled = true;
    try {
      // 构建上下文：世界观 + 已有章节大纲
      var ctx = '';
      if (typeof worldSettings !== 'undefined' && worldSettings.length > 0) {
        ctx += '【世界观设定】\n' + worldSettings.map(function(s) { return s.key + '：' + s.val; }).join('\n') + '\n\n';
      }
      var currentOutline = chOutline.map(function(o, i) { return (i + 1) + '. ' + o.text; }).join('\n');
      ctx += '【第' + (currentChapterIndex + 1) + '章已有大纲】\n' + currentOutline + '\n\n';
      ctx += '请基于以上内容，生成第' + (currentChapterIndex + 1) + '章的**下一条**大纲要点。只返回一条文本，不要编号，不要解释。';

      const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: ctx}]})});
      if (r.ok && r.content) {
        var newText = r.content.replace(/^[-\d\.\s]+/, '').trim().split('\n')[0];
        if (newText.length > 5) {
          chOutline.push({text: newText, current: false, source: 'ai'});
          renderChapterOutlineEditor();
          showToast('✅ 已生成下一条大纲');
        } else {
          showToast('❌ 生成内容为空');
        }
      } else { showToast('❌ 生成失败'); }
    } catch(e) { showToast('❌ ' + e.message); }
    this.textContent = '➕ AI下一条'; this.disabled = false;
  });

  document.getElementById('btn-save-ol')?.addEventListener?.('click', async function() {
    this.textContent = '⏳ 保存中…'; this.disabled = true;
    var saveData = {index: currentChapterIndex, outline: chOutline.map(o => o.text).join('\n')};
    if (window._currentBlueprint) saveData.blueprint = window._currentBlueprint;
    const r = await api('/api/chapter/outline', {method: 'POST', body: JSON.stringify(saveData)});
    if (r.ok) { showToast('✓ 章节大纲已保存' + (window._currentBlueprint ? '（含结构化蓝图）' : '')); } else { showToast('保存失败: ' + (r.error || '')); }
    this.textContent = '💾 保存'; this.disabled = false;
  });

  // 填充本章人物下拉框和列表
  renderChapterCharNodes();
}

window.renderChapterCharNodes = function() {
  var sel = document.getElementById('ch-char-add-select');
  if (!sel) return;
  // 填充下拉框
  var existingNames = {};
  sel.innerHTML = '<option value="">+ 添加人物</option>';
  if (typeof characters !== 'undefined' && characters) {
    characters.forEach(function(c) {
      var name = c.name || '未命名';
      existingNames[name] = true;
      sel.innerHTML += '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '(' + (c.faction||'') + ')</option>';
    });
  }
  // 渲染已有节点
  var listEl = document.getElementById('ch-char-nodes-list');
  if (!listEl) return;
  if (typeof chapters === 'undefined' || !chapters[currentChapterIndex]) { listEl.innerHTML = ''; return; }
  if (!chapters[currentChapterIndex].blueprint) chapters[currentChapterIndex].blueprint = {};
  var nodes = chapters[currentChapterIndex].blueprint.character_nodes || [];
  if (!nodes.length) {
    listEl.innerHTML = '<div style="font-size:10px;color:var(--muted);padding:2px 0">暂无出场人物</div>';
    return;
  }
  var appLabels = {'first':'首次登场','main':'主线','cameo':'客串','exit':'退场'};
  var appColors = {'first':'#e74c3c','main':'#3498db','cameo':'#95a5a6','exit':'#9b59b6'};
  listEl.innerHTML = '';
  nodes.forEach(function(n, i) {
    var color = appColors[n.appearance] || '#999';
    var label = appLabels[n.appearance] || n.appearance || '出场';
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:4px;padding:4px 6px;border:1px solid var(--border-soft);border-radius:4px;background:var(--surface)';
    row.innerHTML = '<span style="font-size:11px;font-weight:600;min-width:50px">' + escapeHtml(n.name||'') + '</span>' +
      '<select onchange="updateCharNode(' + i + ',\'appearance\',this.value)" style="font-size:9px;padding:1px 3px;border:1px solid ' + color + ';border-radius:3px;color:' + color + ';background:var(--bg)">' +
        ['first','main','cameo','exit'].map(function(a) { return '<option value="'+a+'"'+(n.appearance===a?' selected':'')+'>'+appLabels[a]+'</option>'; }).join('') +
      '</select>' +
      '<input type="text" value="' + escapeHtml(n.status_change||'') + '" placeholder="状态变化" onchange="updateCharNode(' + i + ',\'status_change\',this.value)" style="flex:1;font-size:10px;padding:2px 4px;border:1px solid var(--border);border-radius:3px;background:var(--bg);color:var(--ink)">' +
      '<button onclick="removeCharNode(' + i + ')" style="padding:2px 4px;border:1px solid #e74c3c;color:#e74c3c;background:transparent;border-radius:3px;cursor:pointer;font-size:10px">✕</button>';
    listEl.appendChild(row);
  });
}

window.addCharNodeToChapter = function(name) {
  if (!name) return;
  if (typeof chapters === 'undefined' || !chapters[currentChapterIndex]) return;
  if (!chapters[currentChapterIndex].blueprint) chapters[currentChapterIndex].blueprint = {};
  if (!chapters[currentChapterIndex].blueprint.character_nodes) chapters[currentChapterIndex].blueprint.character_nodes = [];
  chapters[currentChapterIndex].blueprint.character_nodes.push({name: name, appearance: 'main', status_change: ''});
  document.getElementById('ch-char-add-select').value = '';
  renderChapterCharNodes();
  saveChapterBlueprint(currentChapterIndex);
}

window.updateCharNode = function(i, field, val) {
  if (typeof chapters === 'undefined' || !chapters[currentChapterIndex]) return;
  var nodes = chapters[currentChapterIndex].blueprint.character_nodes;
  if (nodes && nodes[i]) {
    nodes[i][field] = val;
    saveChapterBlueprint(currentChapterIndex);
  }
  if (field === 'appearance') renderChapterCharNodes();
}

window.removeCharNode = function(i) {
  if (typeof chapters === 'undefined' || !chapters[currentChapterIndex]) return;
  var nodes = chapters[currentChapterIndex].blueprint.character_nodes;
  if (nodes) {
    nodes.splice(i, 1);
    renderChapterCharNodes();
    saveChapterBlueprint(currentChapterIndex);
  }
}

})();