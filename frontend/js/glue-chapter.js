(function() {
  'use strict';


/* ===== Volume Navigation ===== */
var volumesData = [];

window.loadVolumesData = async function() {
  try {
    var data = await api('/api/project/volumes');
    if (data && data.ok && data.volumes && data.volumes.length > 0) {
      volumesData = data.volumes;
    } else {
      volumesData = [];
    }
  } catch(e) {
    volumesData = [];
  }
}

/* 查找当前章节所属的卷 */
window.findVolumeForChapter = function(chIndex) {
  if (!volumesData || !volumesData.length) return null;
  var chNum = chIndex + 1; // 章节号从1开始
  // 精确匹配：chNum 在 chapters 数组中
  for (var i = 0; i < volumesData.length; i++) {
    var vol = volumesData[i];
    if (vol.chapters && vol.chapters.indexOf(chNum) >= 0) return vol;
  }
  // 区间匹配：按卷的章节范围
  for (var i = 0; i < volumesData.length; i++) {
    var vol = volumesData[i];
    if (vol.chapters && vol.chapters.length > 0) {
      var first = vol.chapters[0];
      var last = vol.chapters[vol.chapters.length - 1];
      if (chNum >= first && chNum <= last) return vol;
    }
  }
  // 回退：返回第一卷
  return volumesData[0];
}

/* 加载并展示当前章节所属卷的纲要卡片 */
window.loadChapterVolumeOutline = function() {
  var card = document.getElementById('chapter-vol-outline-card');
  if (!card) return;

  var vol = findVolumeForChapter(currentChapterIndex);
  if (!vol) { card.style.display = 'none'; return; }

  // 从后端加载卷纲要详情
  api('/api/project/volume/' + vol.index + '/outline').then(function(d) {
    if (!d || !d.ok || !d.data) { card.style.display = 'none'; return; }
    var outline = d.data;
    var hasContent = outline.summary || outline.theme || (outline.key_events && outline.key_events.length > 0);
    if (!hasContent) { card.style.display = 'none'; return; }

    // 填充卷标题
    var chRange = '';
    if (vol.chapters && vol.chapters.length > 0) {
      chRange = '（第' + vol.chapters[0] + '-' + vol.chapters[vol.chapters.length - 1] + '章）';
    }
    document.getElementById('cvoc-vol-title').textContent = '卷' + vol.index + ' · ' + (vol.title || '') + ' ' + chRange;

    // 概要
    var sumEl = document.getElementById('cvoc-summary');
    sumEl.textContent = outline.summary || '';
    sumEl.parentElement.style.display = outline.summary ? '' : 'none';

    // 主题
    var themeEl = document.getElementById('cvoc-theme');
    themeEl.textContent = outline.theme || '';
    themeEl.parentElement.style.display = outline.theme ? '' : 'none';

    // 关键事件
    var keSection = document.getElementById('cvoc-keyevents-section');
    var keList = document.getElementById('cvoc-keyevents');
    keList.innerHTML = '';
    if (outline.key_events && outline.key_events.length > 0) {
      outline.key_events.forEach(function(ev) {
        var li = document.createElement('li');
        li.textContent = ev;
        keList.appendChild(li);
      });
      keSection.style.display = '';
    } else {
      keSection.style.display = 'none';
    }

    // 展开卡片
    card.style.display = '';
  }).catch(function() {
    card.style.display = 'none';
  });
}

/* 折叠/展开卷纲要卡片 */
window.toggleChapterVolOutlineCard = function() {
  var body = document.getElementById('cvoc-body');
  var btn = document.querySelector('.cvoc-toggle');
  if (!body || !btn) return;
  var isCollapsed = body.classList.toggle('collapsed');
  btn.textContent = isCollapsed ? '+' : '\u2212';
}


// ══════════════════════════════════════════
// 全局章节同步函数：确保所有面板的章节状态一致
// ══════════════════════════════════════════
window.syncChapterAcrossPanels = function(idx) {
  if (idx == null || idx < 0) return;
  // 1. 更新全局章节索引
  currentChapterIndex = idx;

  // 2. 同步更新写作编辑器内容
  if (typeof loadChapterContentAPI === 'function') {
    loadChapterContentAPI(idx);
  }

  // 3. 同步更新所有章节大纲相关UI
  if (typeof loadChapterOutline === 'function') {
    try { loadChapterOutline(idx); } catch(e) {}
  }
  if (typeof loadChapterVolumeOutline === 'function') {
    try { loadChapterVolumeOutline(); } catch(e) {}
  }
  if (typeof renderChapterOutlineEditor === 'function') {
    try { renderChapterOutlineEditor(); } catch(e) {}
  }

  // 4. 更新所有侧边栏的高亮状态
  ['vol-nav-writing', 'vol-nav-outline', 'vol-nav-timeline', 'vol-nav-content'].forEach(function(cid) {
    var container = document.getElementById(cid);
    if (container) {
      container.querySelectorAll('.ch-directory-item').forEach(function(el) {
        el.classList.remove('active');
      });
      var items = container.querySelectorAll('.ch-directory-item');
      if (items[idx]) {
        items[idx].classList.add('active');
        // 确保所在卷展开
        var volChapters = items[idx].closest('.vol-chapters');
        if (volChapters && !volChapters.classList.contains('open')) {
          volChapters.classList.add('open');
          var arrow = volChapters.previousElementSibling;
          if (arrow) { var a = arrow.querySelector('.vol-arrow'); if (a) a.classList.add('open'); }
        }
      }
    }
  });

  // 5. 更新时间线面板（如果在时间线步骤）
  if (typeof Timeline !== 'undefined' && Timeline.selectChapter) {
    var chNum = idx + 1;
    var volIdx = 0;
    if (typeof volumesData !== 'undefined' && volumesData) {
      for (var vi = 0; vi < volumesData.length; vi++) {
        if (volumesData[vi].chapters && volumesData[vi].chapters.indexOf(chNum) >= 0) {
          volIdx = volumesData[vi].index || 0;
          break;
        }
      }
    }
    Timeline.selectChapter(volIdx, chNum);
  }

  // 6. 更新底部当前章节标签
  var chLabel = document.getElementById('timeline-current-ch');
  if (chLabel && chapters && chapters[idx]) {
    chLabel.textContent = chNum + ' · ' + (chapters[idx].title || '');
  }
  var writingLabel = document.getElementById('writing-current-ch');
  if (writingLabel && chapters && chapters[idx]) {
    writingLabel.textContent = chapters[idx].title || ('第' + chNum + '章');
  }
}

window.confirmPreviewChapter = async function() {
  if (!_chapterPreviewData) return;
  var d = _chapterPreviewData;
  var btn = event && event.target;
  if (btn) { btn.disabled = true; btn.textContent = '保存中…'; }
  try {
    var r = await confirmChapterSave(d.content, d.chapterIndex, d.title, d.validationLog);
    if (r && r.ok) {
      // 更新前端状态
      if (typeof chapters !== 'undefined' && d.chapterIndex < chapters.length) {
        chapters[d.chapterIndex].content = d.content;
        chapters[d.chapterIndex].word_count = d.content.length;
      }
      // 更新编辑器
      var editor = document.getElementById('editor-content');
      if (editor && typeof textToHTML === 'function') {
        editor.innerHTML = textToHTML(d.content);
      } else if (editor) {
        editor.textContent = d.content;
      }
      showToast('✅ 已保存 ' + d.content.length + ' 字');
      closeChapterPreview();
      // 执行回调
      if (d.onConfirm) try { d.onConfirm(d.content); } catch(e) {}
    } else {
      showToast('保存失败: ' + (r && r.error || '未知错误'));
      if (btn) { btn.disabled = false; btn.textContent = '✓ 确认采用'; }
    }
  } catch(e) {
    showToast('保存异常: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '✓ 确认采用'; }
  }
}

// ═══════════════════════════════════════════
// 分卷纲要工作流步骤（Step 3 内联编辑器）
// ═══════════════════════════════════════════

window.renderVolumeOutlineList = function() {
  var list = document.getElementById('vol-outline-list');
  if (!list) return;
  list.innerHTML = '';
  if (!volumesData || volumesData.length === 0) {
    var hasNovelOutline = (typeof _novelOutlineDict !== 'undefined' && _novelOutlineDict && Object.keys(_novelOutlineDict).length > 0);
    if (hasNovelOutline) {
      var storyArc = _novelOutlineDict.story_arc || '';
      var eventCount = storyArc.split('\n').filter(function(l) { return l.trim().startsWith('-'); }).length || 10;
      list.innerHTML = '<div class="card-footer-xs" >' +
        '<div style="margin-bottom:10px;font-size:12px">全书大纲已创建，可一键拆分为卷</div>' +
        '<button onclick="aiGenerateVolumes()" style="padding:7px 20px;border:none;border-radius:4px;background:var(--accent);color:#fff;font-size:11px;cursor:pointer;font-weight:500">AI 自动分卷</button>' +
        '<div style="margin-top:10px;font-size:10px;opacity:0.6">或点击上方"+ 新卷"手动创建</div></div>';
    } else {
      list.innerHTML = '<div class="card-footer-xs" >' +
        '<div style="margin-bottom:6px">暂无卷，点击"+ 新卷"创建</div>' +
        '<div style="font-size:10px;opacity:0.6">在步骤2生成全书大纲后可AI自动分卷</div></div>';
    }
    return;
  }
  volumesData.forEach(function(vol) {
    var item = document.createElement('div');
    item.style.cssText = 'padding:6px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid var(--border-soft);display:flex;align-items:center;gap:6px;transition:background 0.15s';
    if (_currentVolumeEditIndex === vol.index) {
      item.style.background = 'var(--accent)';
      item.style.color = '#fff';
    }
    item.innerHTML = '<span style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1">卷' + (vol.index + 1) + ' · ' + escapeHtml(vol.title) + '</span>' +
      '<span style="font-size:10px;opacity:0.7">' + (vol.chapter_count || 0) + '章</span>' +
      '<button onclick="event.stopPropagation();deleteVolumeInline(' + vol.index + ',\'' + escapeHtml(vol.title) + '\')" style="border:none;background:none;color:inherit;cursor:pointer;font-size:12px;opacity:0.5;padding:0 2px" title="删除">&times;</button>';
    item.addEventListener('click', function() { selectVolumeForEditing(vol.index); });
    item.addEventListener('mouseenter', function() {
      if (_currentVolumeEditIndex !== vol.index) { item.style.background = 'rgba(128,128,128,0.1)'; }
    });
    item.addEventListener('mouseleave', function() {
      if (_currentVolumeEditIndex !== vol.index) { item.style.background = ''; }
    });
    list.appendChild(item);
  });
}

window.selectVolumeForEditing = async function(volIndex) {
  _currentVolumeEditIndex = volIndex;
  var panel = document.getElementById('vol-detail-panel');
  var empty = document.getElementById('vol-detail-empty');
  var form = document.getElementById('vol-detail-form');
  if (!panel) return;

  // 显示分卷详情面板，隐藏其他面板
  var charPanel = document.getElementById('char-detail-panel');
  var detailEmpty = document.getElementById('detail-editor-empty');
  var detailHeader = document.getElementById('detail-editor-header');
  var detailTextarea = document.getElementById('detail-editor-textarea');
  if (charPanel) charPanel.style.display = 'none';
  if (detailEmpty) detailEmpty.style.display = 'none';
  if (detailHeader) detailHeader.classList.add('hidden');
  if (detailTextarea) detailTextarea.classList.add('hidden');
  panel.style.display = 'block';

  if (volIndex < 0) {
    if (empty) empty.style.display = 'block';
    if (form) form.style.display = 'none';
    document.getElementById('vol-detail-title').textContent = '选择卷';
    document.getElementById('vol-detail-subtitle').textContent = '点击左侧卷进行编辑';
    return;
  }

  // 加载现有纲要
  var existing = {summary: '', theme: '', key_events: [], character_arcs: []};
  try {
    var d = await api('/api/project/volume/' + volIndex + '/outline');
    if (d.ok && d.data) {
      existing.summary = d.data.summary || '';
      existing.theme = d.data.theme || '';
      existing.key_events = d.data.key_events || [];
      existing.character_arcs = d.data.character_arcs || [];
    }
  } catch(e) {}

  var vol = null;
  volumesData.forEach(function(v) { if (v.index === volIndex) vol = v; });

  document.getElementById('vol-detail-title').textContent = vol ? vol.title : '卷' + (volIndex + 1);
  document.getElementById('vol-detail-subtitle').textContent = vol ? (vol.chapter_count + '章') : '';
  document.getElementById('vdetail-title').value = vol ? vol.title : '';
  document.getElementById('vdetail-theme').value = existing.theme;
  document.getElementById('vdetail-summary').value = existing.summary;

  // 渲染动态列表
  var ke = document.getElementById('vdetail-key-events');
  var ca = document.getElementById('vdetail-char-arcs');
  ke.innerHTML = '';
  ca.innerHTML = '';
  existing.key_events.forEach(function(it) {
    var div = document.createElement('div');
    div.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;align-items:center';
    div.innerHTML = '<input class="input-base" type="text" value="' + escHtml(it) + '" ><button class="btn-danger-lg" onclick="this.parentElement.remove()"  title="删除">&times;</button>';
    ke.appendChild(div);
  });
  existing.character_arcs.forEach(function(it) {
    var div = document.createElement('div');
    div.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;align-items:center';
    div.innerHTML = '<input class="input-base" type="text" value="' + escHtml(it) + '" ><button class="btn-danger-lg" onclick="this.parentElement.remove()"  title="删除">&times;</button>';
    ca.appendChild(div);
  });

  var chList = document.getElementById('vdetail-chapters');
  chList.innerHTML = '';
  var volChapters = vol ? vol.chapters : [];
  if (volChapters && volChapters.length > 0) {
    volChapters.forEach(function(chIdx) {
      var chTitle = '';
      if (typeof chapters !== 'undefined') {
        chapters.forEach(function(ch) {
          if (ch.index === chIdx) chTitle = ch.title;
        });
      }
      var div = document.createElement('div');
      div.style.cssText = 'display:flex;gap:6px;margin-bottom:2px;align-items:center;padding:4px 8px;border:1px solid var(--border-soft);border-radius:4px;background:var(--bg)';
      div.innerHTML = '<span style="font-size:12px;color:var(--accent);font-weight:600;width:24px">第' + chIdx + '章</span><span style="flex:1;font-size:12px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escHtml(chTitle || '') + '</span><button class="btn-danger-md" onclick="removeChapterFromVolumeBtn(' + volIndex + ', ' + chIdx + ')"  title="从本卷移除">&times;</button>';
      chList.appendChild(div);
    });
  } else {
    chList.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:12px;padding:12px">本卷暂无章节，点击"+ 添加章节"添加</div>';
  }

  if (empty) empty.style.display = 'none';
  if (form) form.style.display = 'flex';
  renderVolumeOutlineList();
}

window.addVolDetailKeyEvent = function() {
  var ke = document.getElementById('vdetail-key-events');
  var div = document.createElement('div');
  div.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;align-items:center';
  div.innerHTML = '<input type="text" value="" placeholder="关键事件" style="flex:1;padding:6px 10px;font-size:13px;border:1px solid var(--border);border-radius:5px;background:var(--bg);color:var(--font)"><button class="input-base btn-danger-lg" onclick="this.parentElement.remove()" title="删除">&times;</button>';
  ke.appendChild(div);
  div.querySelector('input').focus();
}

window.addVolDetailCharArc = function() {
  var ca = document.getElementById('vdetail-char-arcs');
  var div = document.createElement('div');
  div.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;align-items:center';
  div.innerHTML = '<input type="text" value="" placeholder="角色弧线描述" ><button class="btn-danger-lg" onclick="this.parentElement.remove()" title="删除">&times;</button>';
  ca.appendChild(div);
  div.querySelector('input').focus();
}

window.addChapterToVolume = async function() {
  if (_currentVolumeEditIndex < 0) { showToast('请先选择左侧卷'); return; }
  var nextChIdx = 1;
  if (typeof chapters !== 'undefined' && chapters.length > 0) {
    nextChIdx = chapters.length + 1;
  }
  try {
    var d = await api('/api/project/volume/' + _currentVolumeEditIndex + '/add-chapter', {method: 'POST', body: JSON.stringify({chapter_index: nextChIdx})});
    if (d.ok) {
      showToast('章节添加成功');
      await loadVolumesData();
      selectVolumeForEditing(_currentVolumeEditIndex);
    } else {
      showToast('添加失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('添加失败: ' + e.message); }
}

window.removeChapterFromVolumeBtn = async function(volIndex, chIdx) {
  try {
    var d = await api('/api/project/volume/' + volIndex + '/remove-chapter', {method: 'POST', body: JSON.stringify({chapter_index: chIdx})});
    if (d.ok) {
      showToast('章节已移除');
      await loadVolumesData();
      selectVolumeForEditing(volIndex);
    } else {
      showToast('移除失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('移除失败: ' + e.message); }
}

window.saveVolumeDetail = async function() {
  if (_currentVolumeEditIndex < 0) { showToast('请先选择卷'); return; }
  var title = document.getElementById('vdetail-title').value.trim();
  var theme = document.getElementById('vdetail-theme').value.trim();
  var summary = document.getElementById('vdetail-summary').value.trim();
  var keyEvents = [];
  document.querySelectorAll('#vdetail-key-events input').forEach(function(inp) {
    if (inp.value.trim()) keyEvents.push(inp.value.trim());
  });
  var charArcs = [];
  document.querySelectorAll('#vdetail-char-arcs input').forEach(function(inp) {
    if (inp.value.trim()) charArcs.push(inp.value.trim());
  });

  try {
    var d = await api('/api/project/volume/' + _currentVolumeEditIndex + '/outline', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: title,
        theme: theme,
        summary: summary,
        key_events: keyEvents,
        character_arcs: charArcs
      })
    });
    if (d.ok) {
      showToast('保存成功');
      await loadVolumesData();
      selectVolumeForEditing(_currentVolumeEditIndex);
    } else {
      showToast('保存失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('保存失败: ' + e.message); }
}

window.deleteVolumeInline = function(volIndex, volTitle) {
  if (typeof customConfirm !== 'function') {
    if (!confirm('确定删除「' + volTitle + '」？卷内章节将移到前一卷。')) return;
    doDeleteVolumeInline(volIndex);
  } else {
    customConfirm('确定删除「' + volTitle + '」？卷内章节将移到前一卷。', function(ok) {
      if (!ok) return;
      doDeleteVolumeInline(volIndex);
    });
  }
}

window.doDeleteVolumeInline = async function(volIndex) {
  var notify = (typeof showToast === 'function') ? showToast : function(msg) { console.log('[删除卷]', msg); };
  try {
    console.log('[删除卷] 正在删除卷索引:', volIndex);
    var data = await api('/api/project/volume/delete', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({vol_index: volIndex})
    });
    console.log('[删除卷] 服务器响应:', data);
    if (data.ok) {
      notify('✅ 卷已删除');
      await loadVolumesData();
      _currentVolumeEditIndex = -1;
      var editor = document.getElementById('vol-detail-editor');
      var empty = document.getElementById('vol-detail-empty');
      if (editor) editor.style.display = 'none';
      if (empty) empty.style.display = 'flex';
      renderVolumeOutlineList();
    } else {
      notify('❌ 删除失败：' + (data.error || '未知错误'));
    }
  } catch(e) {
    notify('❌ 删除失败: ' + e.message);
    console.error('[删除卷] 异常:', e);
  }
}

window.addNewVolume = async function() {
  var volCount = (typeof volumesData !== 'undefined' && volumesData) ? volumesData.length : 0;
  var nextVolNum = volCount + 1;
  var defStart = (typeof chapters !== 'undefined' && chapters && chapters.length) ? chapters.length + 1 : 1;
  var defEnd = defStart + 4;

  if (typeof customPrompt === 'function') {
    customPrompt('新建卷', '', function(title) {
      var volTitle = (title && title.trim()) || ('第' + nextVolNum + '卷');
      _doAddNewVolume(volTitle, defStart, defEnd);
    }, '第' + nextVolNum + '卷');
  } else {
    var title = prompt('新建卷·请输入标题', '第' + nextVolNum + '卷');
    if (title === null) return;
    var volTitle = title.trim() || ('第' + nextVolNum + '卷');
    _doAddNewVolume(volTitle, defStart, defEnd);
  }
}

window._doAddNewVolume = async function(title, startChapter, endChapter) {
  try {
    var data = await api('/api/project/volume/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title: title, start_chapter: startChapter, end_chapter: endChapter})
    });
    if (data.ok) {
      showToast('新卷「' + title + '」已创建');
      await loadVolumesData();
      renderVolumeOutlineList();
      // 自动选中新卷
      if (data.index !== undefined) {
        selectVolumeForEditing(data.index);
      }
    } else {
      showToast('创建失败: ' + (data.error || '未知错误'));
    }
  } catch(e) { showToast('创建失败: ' + e.message); }
}

window.saveVolumeOutlineInline = async function() {
  if (_currentVolumeEditIndex < 0) return;
  var title = document.getElementById('ve-title').value.trim();
  var theme = document.getElementById('ve-theme').value.trim();
  var summary = document.getElementById('ve-summary').value.trim();

  function collectItems(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return [];
    var items = [];
    var inputs = container.querySelectorAll('input[type="text"]');
    inputs.forEach(function(inp) {
      var v = inp.value.trim();
      if (v) items.push(v);
    });
    return items;
  }
  var keyEvents = collectItems('ve-key-events');
  var characterArcs = collectItems('ve-character-arcs');

  // 如果标题有变化，重命名
  var vol = null;
  volumesData.forEach(function(v) { if (v.index === _currentVolumeEditIndex) vol = v; });
  if (vol && title && title !== vol.title) {
    await api('/api/project/volume/rename', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({vol_index: _currentVolumeEditIndex, title: title})
    });
  }

  try {
    var d = await api('/api/project/volume/' + _currentVolumeEditIndex + '/outline', {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        summary: summary, theme: theme,
        key_events: keyEvents, character_arcs: characterArcs
      })
    });
    if (d.ok) {
      showToast('卷纲要已保存');
      await loadVolumesData();
      renderVolumeOutlineList();
    } else {
      showToast('保存失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('保存失败: ' + e.message); }
}

window.aiGenerateVolumes = async function() {
  var notify = (typeof showToast === 'function') ? showToast : function(msg) { console.log('[AI分卷]', msg); };
  try {
    notify('⏳ AI分卷中...');
    var d = await api('/api/project/ai-split-volumes', {method: 'POST', body: JSON.stringify({})});
    if (d.ok) {
      notify('✅ AI分卷完成，共' + d.volumes.length + '卷，' + d.chapter_count + '章');
      await loadVolumesData();
      renderVolumeOutlineList();
      if (d.volumes.length > 0) {
        selectVolumeForEditing(0);
      } else {
        _currentVolumeEditIndex = -1;
      }
    } else {
      notify('❌ AI分卷失败: ' + (d.error || '未知错误'));
    }
  } catch(e) {
    notify('❌ AI分卷失败: ' + e.message);
    console.error(e);
  }
}

window.aiGenerateThisVolumeOutline = async function() {
  if (_currentVolumeEditIndex < 0) { showToast('请先选择左侧卷'); return; }
  if (typeof showToast !== 'function') return;
  // 使用与弹窗相同的AI生成逻辑（generate_volume_outline）
  try {
    var d = await api('/api/generate/volume-outline/' + _currentVolumeEditIndex, {method: 'POST'});
    if (d.ok) {
      showToast('AI纲要生成完成');
      selectVolumeForEditing(_currentVolumeEditIndex);
    } else {
      showToast('AI生成失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('AI生成失败: ' + e.message); }
}

// 暴露到全局
window.renderVolumeOutlineList = renderVolumeOutlineList;
window.selectVolumeForEditing = selectVolumeForEditing;
window.addNewVolume = addNewVolume;
window.saveVolumeOutlineInline = saveVolumeOutlineInline;
window.deleteVolumeInline = deleteVolumeInline;
window.aiGenerateVolumes = aiGenerateVolumes;
window.aiGenerateThisVolumeOutline = aiGenerateThisVolumeOutline;
window.addVolOutlineDynItem = addVolumeOutlineDynItem;
window.inspirationToVolumeOutline = inspirationToVolumeOutline;
window.addVolDetailKeyEvent = addVolDetailKeyEvent;
window.addVolDetailCharArc = addVolDetailCharArc;
window.saveVolumeDetail = saveVolumeDetail;

window.inspirationToVolumeOutline = async function() {
  if (_currentVolumeEditIndex < 0) { showToast('请先选择左侧卷'); return; }
  var insp = document.getElementById('vdetail-inspiration')?.value?.trim();
  if (!insp) { showToast('请先输入灵感碎片'); return; }
  try {
    var d = await api('/api/generate/volume-outline/' + _currentVolumeEditIndex, {
      method: 'POST',
      body: JSON.stringify({ inspiration: insp })
    });
    if (d.ok) {
      showToast('灵感→卷纲要 生成完成');
      selectVolumeForEditing(_currentVolumeEditIndex);
    } else {
      showToast('生成失败: ' + (d.error || '未知错误'));
    }
  } catch(e) { showToast('生成失败: ' + e.message); }
}

window.saveVolumeOutline = async function() {
  if (_currentVolumeOutlineIdx < 0) return;
  var theme = document.getElementById('vo-theme').value.trim();
  var summary = document.getElementById('vo-summary').value.trim();

  function collectItems(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return [];
    var items = [];
    var inputs = container.querySelectorAll('input[type="text"]');
    inputs.forEach(function(inp) {
      var v = inp.value.trim();
      if (v) items.push(v);
    });
    return items;
  }

  var keyEvents = collectItems('vo-key-events');
  var characterArcs = collectItems('vo-character-arcs');

  try {
    var d = await api('/api/project/volume/' + _currentVolumeOutlineIdx + '/outline', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        summary: summary,
        theme: theme,
        key_events: keyEvents,
        character_arcs: characterArcs
      })
    });
    if (d.ok) {
      showToast('卷纲要已保存');
      closeVolumeOutlineDialog();
      if (typeof loadVolumesData === 'function') {
        await loadVolumesData();
        if (typeof renderVolumeNav === 'function') {
          ['vol-nav-outline','vol-nav-writing'].forEach(function(cid) {
            var c = document.getElementById(cid);
            if (c) renderVolumeNav(cid, function(idx) {
              if (cid === 'vol-nav-outline' && typeof loadChapterOutline === 'function') loadChapterOutline(idx);
              if (cid === 'vol-nav-content' && typeof loadChapterContentAPI === 'function') loadChapterContentAPI(idx);
              currentChapterIndex = idx;
            });
          });
        }
      }
    } else {
      showToast('保存失败: ' + (d.error || '未知错误'));
    }
  } catch(e) {
    showToast('保存失败: ' + e.message);
  }
}

})();