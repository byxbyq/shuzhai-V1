(function() {
  'use strict';


window.openForeshadowDialog = function() {
  var dlg = document.getElementById('foreshadow-dialog');
  if (dlg) dlg.style.display = 'flex';
  renderForeshadowList();
  // 预填种植章节
  var plantedInput = document.getElementById('hook-planted');
  if (plantedInput && !plantedInput.value) {
    plantedInput.value = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  }
}

window.closeForeshadowDialog = function() {
  var dlg = document.getElementById('foreshadow-dialog');
  if (dlg) dlg.style.display = 'none';
}
window.openHooksPanel = function() {
  var p = document.getElementById('hooks-panel');
  if (!p) {
    p = document.createElement('div');
    p.id = 'hooks-panel';
    p.style.cssText = 'position:fixed;top:80px;right:20px;width:380px;max-height:600px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:8px;z-index:1001;box-shadow:0 8px 24px rgba(0,0,0,.4);font-size:11px';
    document.body.appendChild(p);
  }
  loadHooksPanel();
  p.style.display = 'block';
}
window.loadHooksPanel = function() {
  var chIdx = typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0;
  api('/api/project/hooks?current_chapter=' + (chIdx+1)).then(function(d){
    if (!d.ok) return;
    var hooks = d.hooks || [];
    var overdue = d.overdue || [];
    var h = '<div class="p-3" ><h3 style="margin:0 0 6px;font-size:14px">伏笔管理 <span class="text-xs text-muted" >('+hooks.length+'条'+(overdue.length>0?', '+overdue.length+'条超期':'')+')</span></h3>';
    if (overdue.length > 0) {
      h += '<div style="background:rgba(248,81,73,0.12);border:1px solid rgba(248,81,73,0.3);border-radius:4px;padding:6px;margin-bottom:8px;font-size:10px;color:#f85149"><strong>超期告警</strong><br>'+overdue.map(function(oh){return '- '+oh.content}).join('<br>')+'</div>';
    }
    h += '<div style="margin:8px 0"><input id="new-hook-content" placeholder="新伏笔内容..." style="width:70%;padding:4px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px" onkeydown="if(event.key==&#39;Enter&#39;)addHook()"><input id="hook-deadline" type="number" placeholder="截止章" style="width:20%;padding:4px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-size:11px;margin-left:4px"><button onclick="addHook()" style="padding:4px 8px;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:4px;font-size:11px;cursor:pointer;margin-left:4px">+</button></div>';

    hooks.forEach(function(hk, i){
      var statusColor = {planned:'#8b949e',planted:'#58a6ff',advanced:'#d29922',recovered:'#3fb950',overdue:'#f85149'};
      var statusText = {planned:'规划中',planted:'已埋设',advanced:'推进中',recovered:'已回收',overdue:'超期'};
      h += '<div style="padding:6px;margin:3px 0;border:1px solid '+(statusColor[hk.status]||'var(--border)')+';border-radius:4px;font-size:10px">';
      h += '<strong style="color:'+(statusColor[hk.status]||'var(--ink)')+'">['+(statusText[hk.status]||hk.status)+']</strong> '+hk.content;
      h += '<br><span class="text-muted" >埋于第'+hk.planted_chapter+'章'+(hk.deadline_chapter?' | 截止第'+hk.deadline_chapter+'章':'')+(hk.recovery_chapter?' | 回收于第'+hk.recovery_chapter+'章':'')+'</span>';
      h += '<br><button onclick="advanceHook(&#39;&#39;+(hk.id||&#39;&#39;)+&#39;&#39;)" style="font-size:9px;color:var(--accent);border:none;background:none;cursor:pointer;padding:1px 4px">推进</button><button onclick="recoverHook(&#39;&#39;+(hk.id||&#39;&#39;)+&#39;&#39;)" style="font-size:9px;color:var(--green,#3fb950);border:none;background:none;cursor:pointer;padding:1px 4px">回收</button><button onclick="abandonHook(&#39;&#39;+(hk.id||&#39;&#39;)+&#39;&#39;)" style="font-size:9px;color:var(--danger);border:none;background:none;cursor:pointer;padding:1px 4px">放弃</button>';
      h += '</div>';
    });

    h += '<button class="btn-ghost-xs mt-2" onclick="document.getElementById(&#39;hooks-panel&#39;).style.display=&#39;none&#39;" >关闭</button></div>';
    document.getElementById('hooks-panel').innerHTML = h;
  });
}
window.addHook = function() {
  var content = document.getElementById('new-hook-content')?.value;
  var deadline = parseInt(document.getElementById('hook-deadline')?.value) || null;
  if (!content) return;
  var chIdx = typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0;
  api('/api/project/hooks/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:content,chapter_index:chIdx,deadline_chapter:deadline})})
    .then(function(d){
      if(d.ok){showToast('伏笔已添加');loadHooksPanel()}
    });
}
window.openBrainstormPanel = function() {
  var overlay = document.getElementById('brainstorm-overlay');
  if (overlay) overlay.classList.add('active');
  // 从后端加载已有灵感卡片（仅首次）
  if (_bsCards.length === 0) {
    api('/api/project/brainstorm-cards').then(function(r) {
      if (r.ok && r.cards && r.cards.length > 0) {
        var canvas = document.getElementById('brainstorm-canvas');
        var hint = document.getElementById('bs-empty-hint');
        if (hint) hint.style.display = 'none';
        r.cards.forEach(function(idea) {
          if (canvas) _addBrainstormCard(idea);
        });
        // 恢复图谱数据
        if (r.graph) {
          if (r.graph.positions) _bsNodePositions = r.graph.positions;
          if (r.graph.edges) _bsEdges = r.graph.edges;
        }
      }
    });
  }
}
window.closeBrainstormPanel = function() {
  // 自动保存灵感卡片到后端
  _saveBrainstormCards();
  var overlay = document.getElementById('brainstorm-overlay');
  if (overlay) overlay.classList.remove('active');
}

/* ===== Sensory Description Tool ===== */
var _currentSenseType = 'all';

window.openSensoryPanel = function() {
  var overlay = document.getElementById('sensory-overlay');
  if (overlay) overlay.classList.add('active');
}
window.closeSensoryPanel = function() {
  var overlay = document.getElementById('sensory-overlay');
  if (overlay) overlay.classList.remove('active');
}

// Add spin animation for loading
var spinStyle = document.createElement('style');
spinStyle.textContent = '@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }';
document.head.appendChild(spinStyle);

/* ===== C4 章节预览确认 ===== */
var _chapterPreviewData = null; // {content, chapterIndex, title, validationLog, onConfirm}

/* ===== E 关系图可视化 ===== */
var _graphNodes = [];
var _graphEdges = [];

window.openGraphView = function() {
  var overlay = document.getElementById('graph-overlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  var container = document.getElementById('graph-svg-container');
  if (container) {
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:14px" id="graph-loading">加载中…</div>';
  }
  _fetchAndRenderGraph();
}

window.closeGraphView = function() {
  var overlay = document.getElementById('graph-overlay');
  if (overlay) overlay.style.display = 'none';
}

window.showChapterPreview = function(result, chapterIndex, title, onConfirm) {
  var content = result.content || '';
  if (!content) { showToast('生成内容为空'); return; }
  _chapterPreviewData = {
    content: content,
    chapterIndex: chapterIndex,
    title: title || '',
    validationLog: result.validation_log || [],
    onConfirm: onConfirm || null
  };
  var overlay = document.getElementById('chapter-preview-overlay');
  var contentEl = document.getElementById('chapter-preview-content');
  var metaEl = document.getElementById('chapter-preview-meta');
  var assessEl = document.getElementById('chapter-preview-assessment');
  if (!overlay || !contentEl) return;
  contentEl.textContent = content;
  metaEl.textContent = (title || '') + ' | ' + content.length + ' 字' + (result.attempts > 1 ? ' | 重试 ' + result.attempts + ' 次' : '');
  // 展示审计评分
  var assessment = result.assessment;
  if (assessment) {
    var html = '<div style="display:flex;gap:12px;flex-wrap:wrap">';
    if (assessment.editorial_review) {
      var scores = assessment.editorial_review.scores || assessment.editorial_review;
      var dims = ['情感共鸣','节奏控制','画面感','对话质量','悬念设置','整体完成度'];
      var s = '';
      dims.forEach(function(d) {
        var v = scores[d] || scores[d.charAt(0)] || '';
        if (v) s += d + ':' + v + ' ';
      });
      if (s) html += '<span style="color:var(--accent)">📊 ' + s.trim() + '</span>';
    }
    if (assessment.extended_audit) {
      var ea = assessment.extended_audit;
      if (ea.ai_score != null) html += '<span>AI味:' + ea.ai_score.toFixed(1) + '</span>';
      if (ea.issues && ea.issues.length) html += '<span style="color:var(--danger)">⚠️' + ea.issues.length + '项问题</span>';
    }
    if (result.warning) html += '<span style="color:var(--warning)">' + result.warning + '</span>';
    html += '</div>';
    assessEl.innerHTML = html;
    assessEl.style.display = 'block';
  } else {
    assessEl.style.display = 'none';
  }
  overlay.style.display = 'flex';
}

window.closeChapterPreview = function() {
  var overlay = document.getElementById('chapter-preview-overlay');
  if (overlay) overlay.style.display = 'none';
  _chapterPreviewData = null;
}

// Auto-register on load
window.addEventListener('DOMContentLoaded', function() {
  // Plugin bar will be rendered on first toggle
  // 绑定添加人物按钮
  var addCharBtn = document.getElementById('btn-add-character');
  if (addCharBtn) addCharBtn.addEventListener('click', addCharacter);
  // 绑定AI生成人物按钮
  var aiGenBtn = document.getElementById('btn-ai-gen-characters');
  if (aiGenBtn) aiGenBtn.addEventListener('click', aiGenerateCharacters);
  // 绑定清空人物按钮
  var clearCharBtn = document.getElementById('btn-clear-characters');
  if (clearCharBtn) clearCharBtn.addEventListener('click', function() {
    if (!confirm('确定清空所有人物档案？此操作不可撤销。')) return;
    characters.length = 0;
    api('/api/project/settings', {method: 'POST', body: JSON.stringify({characters: []})}).catch(function(e){});
    renderCharacterList();
    showToast('人物档案已清空');
  });

  // 绑定AI生成叙事风格
  var aiGenNs = document.getElementById('btn-ai-gen-narrative');
  if (aiGenNs) aiGenNs.addEventListener('click', aiGenerateNarrativeStyle);
  // 绑定AI生成时代环境
  var aiGenEra = document.getElementById('btn-ai-gen-era');
  if (aiGenEra) aiGenEra.addEventListener('click', aiGenerateEra);
  // 绑定：世界观灵感→设定条目拆解按钮（HTML已有onclick，这里兼容）
  var btnW = document.getElementById('btn-world-inspiration-to-structured');
  if (btnW) btnW.addEventListener('click', function(e) { if (typeof aiWorldInspirationToStructured === 'function') aiWorldInspirationToStructured(); });
  // 绑定：人物灵感→人物卡拆解按钮
  var btnC = document.getElementById('btn-character-inspiration-to-cards');
  if (btnC) btnC.addEventListener('click', function(e) { if (typeof aiCharacterInspirationToCards === 'function') aiCharacterInspirationToCards(); });
  // 绑定：全书大纲灵感→大纲按钮
  var btnNov = document.getElementById('btn-novel-inspiration-to-outline');
  if (btnNov) btnNov.addEventListener('click', function(e) { if (typeof aiNovelInspirationToOutline === 'function') aiNovelInspirationToOutline(); });
  // 绑定：分卷纲要灵感→分卷按钮
  var btnVol = document.getElementById('btn-vol-inspiration-to-outline');
  if (btnVol) btnVol.addEventListener('click', function(e) { if (typeof aiVolumesInspirationToOutline === 'function') aiVolumesInspirationToOutline(); });
  // 绑定：全书章节大纲灵感→章节蓝图+连线框
  var btnCh = document.getElementById('btn-chapter-inspiration-to-outline');
  if (btnCh) btnCh.addEventListener('click', function(e) { if (typeof aiAllChaptersInspirationToOutline === 'function') aiAllChaptersInspirationToOutline(); });

  // 一键生成全部章节正文（逐章生成，确保每章拿到前一章上下文）
  document.addEventListener('click', async function(e) {
    if (e.target.id !== 'wt-btn-gen-all' || e.target.disabled) return;
    // 确保章节数据已加载
    if (!chapters || chapters.length === 0) {
      if (typeof loadChaptersFromAPI === 'function') {
        try { await loadChaptersFromAPI(); } catch(e2) {}
      }
    }
    if (!chapters || chapters.length === 0) { showToast('请先添加章节'); return; }
    if (!confirm('将逐章生成全部' + chapters.length + '章正文，每章约30-60秒。生成过程中请勿操作页面。是否继续？')) return;
    e.target.textContent = '⏳ 逐章生成中…'; e.target.disabled = true;
    showToast('🚀 开始逐章生成（每章生成后自动触发状态提取和记忆注入）…');

    var totalWords = 0;
    var successCount = 0;
    var failCount = 0;
    var skillRules = '';
    if (typeof SkillPack !== 'undefined') {
      skillRules = SkillPack.getActiveRules('generate');
    }

    for (var i = 0; i < chapters.length; i++) {
      var ch = chapters[i];
      e.target.textContent = '⏳ 生成第' + (i+1) + '/' + chapters.length + '章…';
      showToast('📝 正在生成第' + (i+1) + '章《' + (ch.title||'') + '》…');

      try {
        // 构建大纲：优先使用 blueprint（起承转合），outline 仅为补充
        // 如果 outline 是占位符文本则忽略
        var _isPlaceholder = function(t) {
          if (!t || !t.trim()) return true;
          var s = t.trim();
          return s.indexOf('【在此输入') >= 0 || s.indexOf('[在此输入') >= 0 || s.indexOf('大纲要点】') >= 0 || s.indexOf('大纲条目】') >= 0 || s.length < 15;
        };
        var outline = _isPlaceholder(ch.outline) ? '' : (ch.outline || '');
        if (ch.blueprint) {
          var parts = [];
          var intro = ch.blueprint.intro || {};
          if (intro && intro.scene) parts.push('【起】' + intro.scene + ' — ' + (intro.trigger||''));
          (ch.blueprint.development || []).forEach(function(dev) {
            parts.push('【承】' + (dev.scene||'') + '：' + (dev.event||''));
          });
          var climax = ch.blueprint.climax || {};
          if (climax && climax.conflict) parts.push('【转】' + climax.conflict + ' — ' + (climax.twist||''));
          var ending = ch.blueprint.ending || {};
          if (ending && ending.new_state) parts.push('【合】' + ending.new_state + ' → ' + (ending.next_hook||''));
          var bpOutline = parts.join('\n');
          // 如果 outline 有真实内容，拼接到 blueprint 后面
          if (outline) {
            outline = bpOutline + '\n\n【补充大纲条目】\n' + outline;
          } else {
            outline = bpOutline;
          }
        }
        // 如果仍然没有有效大纲，用章节标题作为最低保障
        if (!outline.trim()) {
          outline = '请根据《' + (ch.title || '第' + (i+1) + '章') + '》的章节定位自行构思内容';
        }

        // C4 预览确认链路：先 gate 生成（不落盘），再 confirm 手动保存
        var r = await generateChapterPreview(
          ch.title || ('第' + (i+1) + '章'),
          outline,
          '',
          i
        );

        if (r.ok && r.content) {
          // 预览通过后自动确认写入磁盘（批量逐章生成场景沿用用户的 confirm 确认）
          var confirmR = await confirmChapterSave(
            r.content,
            i,
            ch.title || ('第' + (i+1) + '章'),
            r.validation_log || []
          );
          if (!confirmR.ok) {
            showToast('⚠️ 第' + (i+1) + '章保存失败: ' + (confirmR.error || ''));
          }
          totalWords += r.content.length;
          successCount++;
          // 更新内存
          chapters[i].content = r.content;
          chapters[i].word_count = r.content.length;
          showToast('✅ 第' + (i+1) + '章完成 ' + r.content.length + '字' + (r.warning ? ' (' + r.warning + ')' : ''));
        } else {
          failCount++;
          showToast('⚠️ 第' + (i+1) + '章生成失败: ' + (r.error || ''));
        }
      } catch(err) {
        failCount++;
        showToast('⚠️ 第' + (i+1) + '章异常: ' + err.message);
      }
    }

    // 刷新当前章节显示
    if (typeof loadChaptersFromAPI === 'function') await loadChaptersFromAPI();
    if (typeof loadChapterContentAPI === 'function' && typeof currentChapterIndex !== 'undefined') await loadChapterContentAPI(currentChapterIndex);

    showToast('✅ 逐章生成完成！成功' + successCount + '章' + (failCount ? '，失败' + failCount + '章' : '') + '，共' + totalWords + '字');
    e.target.textContent = '🚀 全部生成'; e.target.disabled = false;
  });
});

// ═══════════════════════════════════════════
// 分卷纲要编辑面板
// ═══════════════════════════════════════════
var _currentVolumeOutlineIdx = -1;
var _currentVolumeEditIndex = -1; // for inline step editor

window.closeVolumeOutlineDialog = function() {
  var dlg = document.getElementById('volume-outline-dialog');
  if (dlg) dlg.style.display = 'none';
  _currentVolumeOutlineIdx = -1;
}

window.openVolumeOutlineDialog = async function(volIndex, volTitle) {
  _currentVolumeOutlineIdx = volIndex;

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

  var dlg = document.getElementById('volume-outline-dialog');
  var body = document.getElementById('vo-body');

  function buildDynList(items, containerId) {
    return items.map(function(it, i) {
      return '<div style="display:flex;gap:4px;margin-bottom:4px;align-items:center">' +
        '<input class="input-flex-sm" type="text" value="' + escHtml(it) + '" >' +
        '<button onclick="this.parentElement.remove()" style="border:none;background:none;color:var(--danger);cursor:pointer;font-size:14px;padding:2px 6px" title="删除">&times;</button>' +
      '</div>';
    }).join('');
  }

  body.innerHTML =
    '<div class="mb-2.5" >' +
      '<label class="label-muted-xs" >卷标题</label>' +
      '<input type="text" id="vo-title" value="' + escHtml(volTitle) + '" readonly style="width:100%;padding:6px 8px;font-size:13px;font-weight:600;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink)">' +
    '</div>' +
    '<div >' +
      '<label class="label-muted-xs mb-2.5" >卷主题</label>' +
      '<input type="text" id="vo-theme" value="' + escHtml(existing.theme) + '" placeholder="本卷的主题" style="width:100%;padding:6px 8px;font-size:12px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink)">' +
    '</div>' +
    '<div class="mb-2.5" >' +
      '<label class="label-muted-xs" 卷概要</label>' +
      '<textarea class="label-muted-xs" id="vo-summary" placeholder="本卷的故事概要..." style="width:100%;min-height:80px;max-height:150px;resize:vertical;padding:6px 8px;font-size:12px;line-height:1.5;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink);font-family:var(--sans)">' + escHtml(existing.summary) + '</textarea>' +
    '</div>' +
    '<div class="mb-2.5" ' +
      '<div class="flex-between-mb4 mb-2.5" >' +
        '<span class="text-sm text-muted" 关键事件</span>' +
        '<button class="btn-accent-dashed-xs text-sm text-muted" onclick="addVolumeOutlineDynItem(\'vo-key-events\')" >+ 添加</button>' +
      '</div>' +
      '<div id="vo-key-events">' + buildDynList(existing.key_events, 'vo-key-events') + '</div>' +
    '</div>' +
    '<div >' +
      '<div class="flex-between-mb4 mb-2.5" >' +
        '<span >角色弧线</span>' +
        '<button class="btn-accent-dashed-xs text-sm text-muted" onclick="addVolumeOutlineDynItem(\'vo-character-arcs\')" >+ 添加</button>' +
      '</div>' +
      '<div id="vo-character-arcs">' + buildDynList(existing.character_arcs, 'vo-character-arcs') + '</div>' +
    '</div>';

  document.getElementById('vo-dlg-title').textContent = '📋 编辑卷纲要 · ' + volTitle;
  dlg.style.display = 'flex';
}

// 暴露内联函数到全局，供app.js和onclick使用
window.openVolumeOutlineDialog = openVolumeOutlineDialog;
window.closeVolumeOutlineDialog = closeVolumeOutlineDialog;
window.loadContextPanel = loadContextPanel;
window.loadProjectSettings = loadProjectSettings;
window.loadProjectOutline = loadProjectOutline;

// ═══════════════════════════════════════════════════════════
// E 连线框 UI引导（modal弹窗 + 横幅提示）
// ═══════════════════════════════════════════════════════════

/**
 * 连线框引导弹窗
 * @param {string} type - 'pre-write' 写作前 | 'post-timeline' 时间线后
 */
window.showWireframeGuide = function(type) {
  // 防止重复弹窗
  if (document.getElementById('wf-guide-modal')) return;

  const guides = {
    'pre-write': {
      title: '💡 建议先布局连线框',
      body: '章节细纲已完成，在开始写作前，建议先使用「连线框」搭建全书逻辑网：<br>• 梳理人物关系（谁和谁有什么关系）<br>• 串联伏笔链条（哪个伏笔呼应哪个）<br>• 标注章节因果（哪章触发哪章）<br><br>这样写作时设定不会跑偏，后续还能对照正文校验一致性。<br><span style="color:#92400e">⚠️ 跳过的话，后续可能需要更多手动核对</span>',
      primaryText: '去布局连线框',
      primaryAction: 'goToStep('+STEPS.连线框+')',
      skipText: '跳过，直接写作',
      skipAction: 'goToStep('+STEPS.写作+')',
      bannerKey: 'wf_pre_write_banner',
    },
    'post-timeline': {
      title: '💡 建议进入草稿定稿',
      body: '时间线对照已完成，建议进入「草稿定稿」阶段：<br>• 用连线框对照修改，逐段校验设定一致性<br>• 联动C5 AI改写需更新段落<br>• 完成后执行Gate最终校验并定稿',
      primaryText: '去草稿定稿',
      primaryAction: 'goToStep('+STEPS.草稿定稿+')',
      skipText: '跳过',
      skipAction: 'goToStep('+STEPS.连线框+')',
      bannerKey: 'wf_post_timeline_banner',
    },
  };
  const g = guides[type];
  if (!g) return;

  const modal = document.createElement('div');
  modal.id = 'wf-guide-modal';
  modal.className = 'wf-modal';
  modal.style.display = 'flex';
  modal.innerHTML =
    '<div class="wf-modal-content" style="max-width:480px">' +
    '<div class="wf-modal-header">' + g.title + '</div>' +
    '<div class="wf-modal-body" style="font-size:13px;line-height:1.8">' + g.body + '</div>' +
    '<div class="wf-modal-footer">' +
    '<button class="wf-btn" onclick="' +
    "this.closest('#wf-guide-modal').remove();" + g.skipAction + ';' +
    "(function(){try{localStorage.setItem('" + g.bannerKey + "','1')}catch(e){}})();" + '">' + g.skipText + '</button>' +
    '<button class="wf-btn wf-btn-primary" onclick="' +
    "this.closest('#wf-guide-modal').remove();" + g.primaryAction + ';' + '">' + g.primaryText + '</button>' +
    '</div></div>';
  document.body.appendChild(modal);

  // 跳过时显示横幅（防遗忘）
  // 横幅在进入目标步骤后由 showWireframeBanner 显示
  if (type === 'pre-write') {
    // 标记需要显示横幅（用户跳过去写作了）
    setTimeout(function() {
      if (currentWorkflowStep === STEPS.写作) showWireframeBanner('pre-write');
    }, 500);
  }
}

/**
 * 连线框横幅提示（非阻塞，可关闭）
 */
window.showWireframeBanner = function(type) {
  // 检查是否已关闭
  const closedKey = type === 'pre-write' ? 'wf_pre_write_banner_closed' : 'wf_post_timeline_banner_closed';
  try { if (localStorage.getItem(closedKey)) return; } catch(e) {}

  // 移除已有横幅
  const old = document.getElementById('wf-guide-banner');
  if (old) old.remove();

  const banners = {
    'pre-write': {
      text: '💡 尚未布局连线框，建议写作前先规划设定关系网',
      actionText: '去布局',
      action: "goToStep("+STEPS.连线框+")",
    },
    'post-timeline': {
      text: '💡 可用连线框对照修改，逐段校验设定一致性',
      actionText: '去对照',
      action: "WireframeCanvas.open('compare')",
    },
  };
  const b = banners[type];
  if (!b) return;

  const banner = document.createElement('div');
  banner.id = 'wf-guide-banner';
  banner.className = 'wf-guide-banner';
  banner.innerHTML =
    '<span>' + b.text + '</span>' +
    '<button class="wf-btn wf-btn-primary" style="font-size:11px;padding:3px 10px" onclick="' + b.action + '">' + b.actionText + '</button>' +
    '<button class="wf-btn" style="font-size:11px;padding:3px 8px" onclick="' +
    "this.closest('#wf-guide-banner').remove();" +
    "(function(){try{localStorage.setItem('" + closedKey + "','1')}catch(e){}})();" +
    '">✕</button>';
  // 插入到编辑器区域顶部
  const editor = document.querySelector('.editor-area') || document.querySelector('.app');
  if (editor && editor.firstChild) {
    editor.insertBefore(banner, editor.firstChild);
  } else {
    document.body.insertBefore(banner, document.body.firstChild);
  }
}

})();