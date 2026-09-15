(function() {
  'use strict';


// ══ 伏笔管理 ══
var foreshadowHooks = [];

window.loadForeshadows = function() {
  var ch = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  api('/api/project/hooks?current_chapter=' + ch).then(function(r) {
    if (r.ok) {
      foreshadowHooks = r.hooks || [];
      var overdue = r.overdue || [];
      var active = foreshadowHooks.filter(function(h) { return h.status === 'planted' || h.status === 'active'; });
      var summary = document.getElementById('foreshadow-count');
      if (summary) {
        var txt = '共' + foreshadowHooks.length + '个';
        if (active.length) txt += ' | 待回收' + active.length;
        if (overdue.length) txt += ' | ⚠️逾期' + overdue.length;
        summary.textContent = txt;
        summary.style.color = overdue.length ? '#e74c3c' : 'var(--muted)';
      }
    }
  }).catch(function() {});
}

window.renderForeshadowList = function() {
  var list = document.getElementById('foreshadow-list');
  if (!list) return;
  list.innerHTML = '';
  if (foreshadowHooks.length === 0) {
    list.innerHTML = '<div class="empty-state-sm" >还没有伏笔<br>在下方输入伏笔内容并种植</div>';
    updateForeshadowStats();
    return;
  }
  var curCh = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  var statusColors = {
    'planted': '#3498db', 'active': '#3498db',
    'recovered': '#27ae60', 'abandoned': '#95a5a6'
  };
  var statusLabels = {
    'planted': '待回收', 'active': '待回收',
    'recovered': '已回收', 'abandoned': '已放弃'
  };
  foreshadowHooks.forEach(function(h) {
    var expected = h.expected_recovery_chapter || 0;
    var isOverdue = (h.status === 'planted' || h.status === 'active') && expected > 0 && expected < curCh;
    var item = document.createElement('div');
    var borderColor = isOverdue ? '#e74c3c' : 'var(--border-soft)';
    var bgColor = isOverdue ? 'rgba(231,76,60,0.06)' : 'var(--surface)';
    item.style.cssText = 'padding:8px 10px;margin-bottom:6px;border:1px solid ' + borderColor + ';border-radius:6px;background:' + bgColor;
    var color = statusColors[h.status] || '#999';
    var label = statusLabels[h.status] || h.status;
    var html = '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">' +
      '<div class="flex-1" >' +
        '<div style="font-size:12px;color:var(--ink);margin-bottom:2px">' + (isOverdue ? '<span style="color:#e74c3c;font-weight:600">⚠️逾期 </span>' : '') + escapeHtml(h.content) + '</div>' +
        '<div class="text-xs text-muted" >种植:第' + h.planted_chapter + '章' +
          (expected ? ' | 预期回收:第' + expected + '章' : '') +
        '</div>' +
        (h.note ? '<div style="font-size:10px;color:var(--muted);margin-top:2px">' + escapeHtml(h.note) + '</div>' : '') +
      '</div>' +
      '<span style="font-size:9px;padding:2px 6px;border-radius:3px;background:' + color + ';color:#fff;white-space:nowrap">' + label + '</span>' +
    '</div>';
    // 操作按钮
    if (h.status === 'planted' || h.status === 'active') {
      html += '<div style="display:flex;gap:4px;margin-top:6px">' +
        '<button onclick="recoverHook(\'' + h.id + '\')" style="flex:1;padding:3px 8px;font-size:10px;border:1px solid #27ae60;color:#27ae60;background:transparent;border-radius:4px;cursor:pointer">标记已回收</button>' +
        '<button onclick="abandonHook(\'' + h.id + '\')" style="flex:1;padding:3px 8px;font-size:10px;border:1px solid #e74c3c;color:#e74c3c;background:transparent;border-radius:4px;cursor:pointer">放弃</button>' +
      '</div>';
    }
    item.innerHTML = html;
    list.appendChild(item);
  });
  updateForeshadowStats();
}

window.updateForeshadowStats = function() {
  var curCh = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  var active = foreshadowHooks.filter(function(h) { return h.status === 'planted' || h.status === 'active'; });
  var recovered = foreshadowHooks.filter(function(h) { return h.status === 'recovered'; });
  var overdue = active.filter(function(h) { return (h.expected_recovery_chapter || 0) > 0 && (h.expected_recovery_chapter || 0) < curCh; });
  var el = function(id, v) { var e = document.getElementById(id); if (e) e.textContent = v; };
  el('fs-active', active.length);
  el('fs-recovered', recovered.length);
  el('fs-overdue', overdue.length);
}

window.plantHook = function() {
  var content = val('hook-content');
  var planted = parseInt(val('hook-planted')) || 1;
  var expected = parseInt(val('hook-expected')) || 0;
  if (!content) { alert('请输入伏笔内容'); return; }
  // 后端新增端点为 /api/project/hooks/add（HookAdd 模型）；旧路径 POST /api/project/hooks 不存在会 404
  api('/api/project/hooks/add', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      content: content,
      planted_chapter: planted,
      expected_recovery_chapter: expected,
      related_characters: [],
      note: ''
    })
  }).then(function(r) {
    if (r.ok) {
      document.getElementById('hook-content').value = '';
      document.getElementById('hook-expected').value = '';
      loadForeshadows();
      renderForeshadowList();
    } else {
      alert('种植失败: ' + (r.error || ''));
    }
  });
}

window.recoverHook = function(hid) {
  var ch = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
  api('/api/project/hooks/recover', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({hook_id: hid, chapter: ch})
  }).then(function(r) {
    if (r.ok) { loadForeshadows(); renderForeshadowList(); }
  });
}

window.abandonHook = function(hid) {
  if (!confirm('确定放弃这个伏笔？')) return;
  api('/api/project/hooks/abandon', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({hook_id: hid, reason: '手动放弃'})
  }).then(function(r) {
    if (r.ok) { loadForeshadows(); renderForeshadowList(); }
  });
}

// ══ 支线标记 ══
window.updatePlotLine = function(checkbox) {
  if (typeof chapters === 'undefined' || !chapters[currentChapterIndex]) return;
  if (!chapters[currentChapterIndex].blueprint) chapters[currentChapterIndex].blueprint = {};
  var lines = chapters[currentChapterIndex].blueprint.plot_line || ['主线'];
  if (!Array.isArray(lines)) lines = ['主线'];
  var line = checkbox.value;
  if (checkbox.checked) {
    if (lines.indexOf(line) < 0) lines.push(line);
  } else {
    // 不能取消最后一个
    if (lines.length <= 1) { checkbox.checked = true; return; }
    lines = lines.filter(function(l) { return l !== line; });
  }
  chapters[currentChapterIndex].blueprint.plot_line = lines;
  // 保存到后端
  saveChapterBlueprint(currentChapterIndex);
}

window.saveChapterBlueprint = function(idx) {
  if (typeof chapters === 'undefined' || !chapters[idx]) return;
  try {
    api('/api/chapter/' + idx + '/blueprint', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({blueprint: chapters[idx].blueprint || {}})
    });
  } catch(e) {}
}

// ══ 人物档案系统 ══
var characters = []; // 人物列表
var _selectedCharIdx = -1; // 当前在中间面板选中的人物索引

window.renderCharacterList = function() {
  var listEl = document.getElementById('character-list');
  if (!listEl) return;
  renderCharChapterSelect();
  renderChapterCharList();
  listEl.innerHTML = '';
  if (characters.length === 0) {
    listEl.innerHTML = '<div >还没有人物档案<br>点击上方"+ 添加"开始创建</div>';
    showCharDetail(-1);
    return;
  }
  characters.forEach(function(char, idx) {
    var card = document.createElement('div');
    card.className = 'char-card' + (idx === _selectedCharIdx ? ' char-card-active' : '');
    card.innerHTML =
      '<div class="char-card-header empty-state-sm" onclick="selectCharacter(' + idx + ')">' +
        '<span class="char-name">' + escapeHtml(char.name || '未命名') + '</span>' +
        '<span class="char-role">' + escapeHtml(char.identity || char.role || char.faction || '') + '</span>' +
      '</div>';
    listEl.appendChild(card);
  });
  // 自动选中第一个或保持之前的选中
  if (_selectedCharIdx >= 0 && _selectedCharIdx < characters.length) {
    showCharDetail(_selectedCharIdx);
  } else if (characters.length > 0) {
    selectCharacter(0);
  } else {
    showCharDetail(-1);
  }
}

window.selectCharacter = function(idx) {
  _selectedCharIdx = idx;
  // 更新左侧卡片高亮
  var cards = document.querySelectorAll('#character-list .char-card');
  cards.forEach(function(c, i) {
    c.classList.toggle('char-card-active', i === idx);
  });
  showCharDetail(idx);
}

window.showCharDetail = function(idx) {
  var panel = document.getElementById('char-detail-panel');
  var emptyEl = document.getElementById('detail-editor-empty');
  var headerEl = document.getElementById('detail-editor-header');
  if (!panel) return;
  // 只在步骤3（人物）显示人物面板
  if (typeof currentWorkflowStep === 'undefined' || currentWorkflowStep !== STEPS.人物) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';
  if (headerEl) headerEl.classList.add('hidden');

  if (idx < 0 || idx >= characters.length) {
    document.getElementById('char-detail-title').textContent = '选择人物';
    document.getElementById('char-detail-subtitle').textContent = '点击左侧人物卡片进行编辑';
    document.getElementById('char-detail-avatar').textContent = '👤';
    document.getElementById('char-detail-actions').innerHTML = '';
    document.getElementById('char-detail-form').innerHTML = '<div class="empty-state-lg" >← 请从左侧选择一个人物<br>在此处编辑详细档案</div>';
    return;
  }
  var ch = characters[idx];
  document.getElementById('char-detail-title').textContent = ch.name || '未命名';
  document.getElementById('char-detail-subtitle').textContent = ch.identity || ch.faction || '角色';
  document.getElementById('char-detail-avatar').textContent = ch.name ? ch.name.charAt(0) : '👤';
  document.getElementById('char-detail-actions').innerHTML =
    '<button onclick="aiGenCharDetail()" title="AI丰富此人物" style="padding:4px 10px;border:1px solid var(--border);background:var(--surface);color:var(--muted);border-radius:4px;font-size:11px;cursor:pointer">🤖</button>' +
    '<button onclick="deleteCharacter(' + idx + ')" title="删除人物" style="padding:4px 10px;border:1px solid rgba(212,80,80,0.3);background:rgba(212,80,80,0.05);color:var(--danger);border-radius:4px;font-size:11px;cursor:pointer">🗑</button>';

  // 渲染大表单
  var fields = [
    {key:'name', label:'姓名', type:'input', placeholder:'角色名称'},
    {key:'identity', label:'身份', type:'input', placeholder:'如：剑客/商人/程序员/皇子'},
    {key:'faction', label:'阵营', type:'select', options:['主角','配角','反派','中立']},
    {key:'importance', label:'角色定位', type:'select', options:['核心人物','次要人物']},
    {key:'personality', label:'性格', type:'input', placeholder:'如：冷静/冲动/阴沉/开朗'},
    {key:'background', label:'身世过往', type:'textarea', rows:4, placeholder:'角色的成长经历、重要事件'},
    {key:'obsession', label:'执念', type:'input', placeholder:'内心最深的渴望'},
    {key:'weakness', label:'软肋', type:'input', placeholder:'致命弱点或情感盲区'},
    {key:'goal', label:'目标', type:'textarea', rows:2, placeholder:'每行一个目标，格式：目标描述|权重(0~1)\n示例：通过内门考核|0.8'},
    {key:'bonds', label:'人物羁绊', type:'textarea', rows:3, placeholder:'与其他角色的关系和羁绊'},
    {key:'appearance', label:'外貌特征', type:'textarea', rows:2, placeholder:'容貌、体型、标志性特征'},
    {key:'speech', label:'语言风格', type:'textarea', rows:2, placeholder:'说话的语气、口头禅、措辞习惯'},
    {key:'habits', label:'行为习惯', type:'textarea', rows:2, placeholder:'日常习惯、小动作、癖好'},
    {key:'catchphrase', label:'口头禅', type:'input', placeholder:'标志性台词或口头禅'},
    {key:'cognitive_boundary', label:'认知边界', type:'textarea', rows:2, placeholder:'角色不知道的信息/领域限制\n如：不知道幕后主使是谁、不了解外界世界'},
    {key:'key_events', label:'重要经历', type:'textarea', rows:3, placeholder:'人生中的关键事件和转折点'}
  ];
  var html = '';
  fields.forEach(function(f) {
    html += '<div class="char-detail-field">';
    html += '<label>' + f.label + '</label>';
    if (f.type === 'input') {
      html += '<input type="text" data-cidx="' + idx + '" data-cfield="' + f.key + '" value="' + escapeHtml(ch[f.key]||'') + '" placeholder="' + (f.placeholder||'') + '">';
    } else if (f.type === 'textarea') {
      html += '<textarea data-cidx="' + idx + '" data-cfield="' + f.key + '" rows="' + (f.rows||3) + '" placeholder="' + (f.placeholder||'') + '">' + escapeHtml(ch[f.key]||'') + '</textarea>';
    } else if (f.type === 'select') {
      html += '<select data-cidx="' + idx + '" data-cfield="' + f.key + '">';
      (f.options||[]).forEach(function(opt) {
        html += '<option value="' + opt + '"' + (ch[f.key]===opt?' selected':'') + '>' + opt + '</option>';
      });
      html += '</select>';
    }
    html += '</div>';
  });
  document.getElementById('char-detail-form').innerHTML = html;

  // 绑定输入事件：实时保存
  panel.querySelectorAll('input,textarea,select').forEach(function(input) {
    input.addEventListener('input', function() {
      var i = parseInt(this.dataset.cidx);
      var f = this.dataset.cfield;
      if (!isNaN(i) && f) {
        characters[i][f] = this.value;
        saveCharacters();
        // 姓名或身份变化时更新左侧卡片和标题
        if (f === 'name' || f === 'identity' || f === 'faction') {
          var nameEl = document.getElementById('char-detail-title');
          var subEl = document.getElementById('char-detail-subtitle');
          var avatarEl = document.getElementById('char-detail-avatar');
          if (nameEl) nameEl.textContent = characters[i].name || '未命名';
          if (subEl) subEl.textContent = characters[i].identity || characters[i].faction || '角色';
          if (avatarEl) avatarEl.textContent = characters[i].name ? characters[i].name.charAt(0) : '👤';
          renderCharacterList(); // 重渲染左侧列表
        }
      }
    });
  });
}

// ===== 章节人物功能 =====
var charChapterIndex = 0; // 人物面板当前选中的章节

window.renderCharChapterSelect = function() {
  var sel = document.getElementById('char-chapter-select');
  if (!sel) return;
  sel.innerHTML = '';
  var chs = (typeof chapters !== 'undefined') ? chapters : [];
  chs.forEach(function(ch, i) {
    var opt = document.createElement('option');
    opt.value = i;
    opt.textContent = '第' + (i+1) + '章' + (ch.title ? ' · ' + ch.title : '');
    sel.appendChild(opt);
  });
  if (charChapterIndex < chs.length) sel.value = String(charChapterIndex);
}

window.onCharChapterChange = function(val) {
  charChapterIndex = parseInt(val) || 0;
  renderChapterCharList();
}

window.renderChapterCharList = function() {
  var listEl = document.getElementById('chapter-char-list');
  if (!listEl) return;
  listEl.innerHTML = '';
  var chs = (typeof chapters !== 'undefined') ? chapters : [];
  var ch = chs[charChapterIndex];
  if (!ch) {
    listEl.innerHTML = '<div class="label-muted-inline-sm" >无章节数据</div>';
    return;
  }
  // 从blueprint获取章节人物节点
  var nodes = (ch.blueprint && ch.blueprint.character_nodes) ? ch.blueprint.character_nodes : [];
  if (nodes.length === 0) {
    listEl.innerHTML = '<div class="label-muted-inline-sm" >本章暂无出场人物</div>';
  } else {
    nodes.forEach(function(node, i) {
      var item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 8px;background:var(--surface);border-radius:4px;border:1px solid var(--border-soft)';
      var charInfo = (typeof characters !== 'undefined') ? characters.find(function(c){return c.name === node.name;}) : null;
      var faction = charInfo ? charInfo.faction : '';
      item.innerHTML = '<span style="font-size:11px;font-weight:600;color:var(--ink)">' + escapeHtml(node.name||'') + '</span>' +
        (faction ? '<span style="font-size:10px;color:var(--muted);padding:1px 4px;background:var(--bg);border-radius:2px">' + escapeHtml(faction) + '</span>' : '') +
        '<span style="font-size:10px;color:var(--muted);flex:1">' + escapeHtml(node.appearance||'') + '</span>' +
        '<button onclick="removeCharFromChapter(' + i + ')" style="font-size:10px;color:#c44;border:none;background:none;cursor:pointer;padding:2px">✕</button>';
      listEl.appendChild(item);
    });
  }
  // 添加人物到章节的下拉框
  var addDiv = document.createElement('div');
  addDiv.style.cssText = 'display:flex;gap:4px;margin-top:4px';
  var sel = document.createElement('select');
  sel.id = 'char-add-to-chapter';
  sel.style.cssText = 'flex:1;font-size:10px;padding:2px 4px;border:1px solid var(--border);border-radius:3px;background:var(--bg);color:var(--ink)';
  sel.innerHTML = '<option value="">+ 从全书人物中添加…</option>';
  if (typeof characters !== 'undefined') {
    characters.forEach(function(c) {
      var already = nodes.some(function(n) { return n.name === c.name; });
      if (!already) {
        var opt = document.createElement('option');
        opt.value = c.name;
        opt.textContent = c.name + ' (' + (c.faction||'') + ')';
        sel.appendChild(opt);
      }
    });
  }
  var addBtn = document.createElement('button');
  addBtn.textContent = '添加';
  addBtn.style.cssText = 'font-size:10px;padding:2px 8px;border:1px solid var(--accent);border-radius:3px;background:var(--accent);color:#fff;cursor:pointer';
  addBtn.onclick = function() {
    var name = document.getElementById('char-add-to-chapter').value;
    if (!name) return;
    addCharToChapter(name);
  };
  addDiv.appendChild(sel);
  addDiv.appendChild(addBtn);
  listEl.appendChild(addDiv);
}

window.addCharToChapter = function(name) {
  var chs = (typeof chapters !== 'undefined') ? chapters : [];
  var ch = chs[charChapterIndex];
  if (!ch) return;
  if (!ch.blueprint) ch.blueprint = {};
  if (!ch.blueprint.character_nodes) ch.blueprint.character_nodes = [];
  ch.blueprint.character_nodes.push({name: name, appearance: 'main', status_change: ''});
  // 保存到后端
  if (typeof saveChapterBlueprint === 'function') saveChapterBlueprint(charChapterIndex);
  else if (typeof saveChapterOutline === 'function') saveChapterOutline();
  renderChapterCharList();
  showToast('已添加「' + name + '」到第' + (charChapterIndex+1) + '章');
}

window.removeCharFromChapter = function(idx) {
  var chs = (typeof chapters !== 'undefined') ? chapters : [];
  var ch = chs[charChapterIndex];
  if (!ch || !ch.blueprint || !ch.blueprint.character_nodes) return;
  ch.blueprint.character_nodes.splice(idx, 1);
  if (typeof saveChapterBlueprint === 'function') saveChapterBlueprint(charChapterIndex);
  else if (typeof saveChapterOutline === 'function') saveChapterOutline();
  renderChapterCharList();
  showToast('已移除');
}

window.toggleCharCard = function(idx) {
  var body = document.getElementById('char-body-' + idx);
  if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

window.addCharacter = function() {
  characters.push({
    name: '新人物', identity: '', faction: '配角', personality: '',
    background: '', obsession: '', weakness: '', goal: '', goals: [], bonds: [], importance: '次要',
    cognitive_boundary: ''
  });
  renderCharacterList();
  saveCharacters();
  // 自动展开新卡片
  setTimeout(function() { toggleCharCard(characters.length - 1); }, 50);
}

window.deleteCharacter = function(idx) {
  characters.splice(idx, 1);
  renderCharacterList();
  saveCharacters();
}

window.saveCharacters = function() {
  try {
    // 将 goal textarea 解析为 goals 数组
    characters.forEach(function(ch) {
      if (typeof ch.goal === 'string' && ch.goal.trim()) {
        var lines = ch.goal.split('\n').filter(function(l) { return l.trim(); });
        ch.goals = lines.map(function(line) {
          var parts = line.split('|');
          if (parts.length >= 2) {
            var w = parseFloat(parts[parts.length - 1].trim());
            if (!isNaN(w)) {
              return {text: parts.slice(0, -1).join('|').trim(), weight: Math.max(0, Math.min(1, w))};
            }
          }
          return {text: line.trim(), weight: 1.0};
        });
      } else if (!ch.goal || !ch.goal.trim()) {
        ch.goals = [];
      }
    });
    var settings = getSettings ? getSettings() : null;
    // 存到project settings里
    api('/api/project/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({characters: characters})
    });
  } catch(e) {}
}

window.loadCharacters = function() {
  return getSettings().then(function(data) {
    characters = (data && data.characters) || [];
    // 将 goals 数组反填到 goal 字段供 textarea 显示
    characters.forEach(function(ch) {
      if (ch.goals && ch.goals.length && !ch.goal) {
        ch.goal = ch.goals.map(function(g) {
          if (typeof g === 'object') return g.text + '|' + (g.weight || 1.0);
          return g + '|1.0';
        }).join('\n');
      }
    });
  }).catch(function() { characters = []; });
}
window.advanceHook = function(id){api('/api/project/hooks/advance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,chapter_index:(typeof currentChapterIndex!=="undefined"?currentChapterIndex:0)})}).then(function(d){if(d.ok)loadHooksPanel()});}
window.recoverHook = function(id){api('/api/project/hooks/recover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,chapter_index:(typeof currentChapterIndex!=="undefined"?currentChapterIndex:0)})}).then(function(d){if(d.ok)loadHooksPanel()});}
window.abandonHook = function(id){if(!confirm('确认放弃此伏笔？'))return;api('/api/project/hooks/abandon',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})}).then(function(d){if(d.ok)loadHooksPanel()});}

// 全书优化诊断

/* ===== Plugin Framework ===== */
var _plugins = [];
var _pluginBarVisible = false;

window.registerPlugin = function(id, name, icon, callback) {
  _plugins.push({id: id, name: name, icon: icon, callback: callback});
  if (_pluginBarVisible) renderPluginBar();
}
window.togglePluginBar = function() {
  _pluginBarVisible = !_pluginBarVisible;
  var bar = document.getElementById('plugin-bar');
  if (bar) bar.style.display = _pluginBarVisible ? 'block' : 'none';
  if (_pluginBarVisible) renderPluginBar();
}

window._fetchAndRenderGraph = async function() {
  try {
    var r = await api('/api/engine/graph');
    _graphNodes = (r && r.nodes) || [];
    _graphEdges = (r && r.edges) || [];
    if (_graphNodes.length === 0) {
      var container = document.getElementById('graph-svg-container');
      if (container) container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:14px">暂无角色关系数据<br><span style="font-size:12px">请先创建角色档案</span></div>';
      return;
    }
    _renderGraphSVG();
  } catch(e) {
    var container = document.getElementById('graph-svg-container');
    if (container) container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--danger);font-size:14px">加载失败: ' + e.message + '</div>';
  }
}

window.addVolumeOutlineDynItem = function(containerId) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var div = document.createElement('div');
  div.style.cssText = 'display:flex;gap:4px;margin-bottom:4px;align-items:center';
  div.innerHTML = '<input class="input-flex-sm" type="text" value="" >' +
    '<button class="btn-danger-md" onclick="this.parentElement.remove()"  title="删除">&times;</button>';
  container.appendChild(div);
}

window.showWireframeGuide = showWireframeGuide;
window.showWireframeBanner = showWireframeBanner;

})();