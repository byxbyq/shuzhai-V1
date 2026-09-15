(function() {
  'use strict';


var _debounceSaveTimer = null;
window.debounceSaveWorldMeta = function() {
  clearTimeout(_debounceSaveTimer);
  _debounceSaveTimer = setTimeout(saveWorldMeta, 600);
}

window.val = function(id) {
  var el = document.getElementById(id);
  return el ? el.value : '';
}

// ══ AI生成叙事风格 / 时代环境 ══
window._parseAIKeyValue = function(rawText, keyMap) {
  // 兼容多种格式：JSON、冒号分隔、- 开头列表等
  var result = {};
  if (!rawText) return result;
  var text = String(rawText).replace(/```json|```/gi, '').trim();
  // 尝试JSON
  try {
    var j = JSON.parse(text);
    if (j && typeof j === 'object') {
      for (var jk in j) {
        if (j.hasOwnProperty(jk) && keyMap[jk]) {
          result[keyMap[jk]] = String(j[jk]).trim();
        }
      }
      return result;
    }
  } catch(e) {}
  // 行解析："key: value" 或 "- key: value"
  var lines = text.split(/\r?\n/);
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].replace(/^[\s\-·•\d\.、]+/, '').trim();
    if (!line) continue;
    var m = line.match(/^([^：:]{1,20})[：:]\s*([\s\S]*)$/);
    if (m) {
      var k = m[1].trim();
      var v = m[2].trim();
      if (keyMap[k]) result[keyMap[k]] = v;
    }
  }
  return result;
}

// ══ 世界观：灵感碎片→写入设定编辑器 ══
window._parseAIObjectJSON = function(rawText) {
  // 通用解析：JSON对象/Markdown code block，返回{}
  // 保护：如果AI返回了人物/角色数组或对象，直接返回空{}，避免污染世界观
  var result = {};
  if (!rawText) return result;
  var text = String(rawText).replace(/```json|```/gi, '').trim();
  try {
    var j = JSON.parse(text);
    // 情况A：数组（人物列表/章节大纲列表）→ 不是世界观9字段 → 拒绝
    if (Array.isArray(j)) {
      // 检查第一个元素是不是人物卡（有name/identity）
      var first = j[0];
      if (first && typeof first === 'object') {
        var isCharacterList = (first.name && (first.identity || first.camp || first.personality));
        if (isCharacterList) return {};  // 人物列表，直接拒绝
      }
      return {};  // 其他数组也拒绝，世界观应该是单个对象
    }
    // 情况B：单个对象，但字段是人物卡（有name+identity+camp+personality里至少3个）→ 不是世界观 → 拒绝
    if (j && typeof j === 'object') {
      var charFields = 0;
      ['name','identity','camp','personality','backstory','obsession','weakness','goal','goals','cognitive_boundary','character_position'].forEach(function(f){ if(j[f]) charFields++; });
      if (charFields >= 3) return {};
      // 情况C：是世界观9字段对象（有core_setting/era_background等至少2个）→ 接受
      var worldFields = 0;
      ['core_setting','era_background','overall_style','atmosphere','main_roles_overview','other_settings','perspective_rules','sensory_limits','visual_style'].forEach(function(f){ if(j[f]) worldFields++; });
      if (worldFields >= 2) return j;
      // 情况D：是自由设定key-value（键都是中文短语，值都是长文本）→ 也接受，兼容早期返回格式
      var keys = Object.keys(j);
      var allChineseLike = keys.length >= 3 && keys.every(function(k) { return /[\u4e00-\u9fa5]/.test(k) && typeof j[k] === 'string' && j[k].length > 5; });
      if (allChineseLike) return j;
      // 其他情况：返回空对象避免污染
      return {};
    }
  } catch(e) {}
  // 逐行解析 key: value
  var lines = text.split(/\r?\n/);
  var currentKey = null;
  var currentVal = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var m = line.match(/^\s*(?:[-*•\d\.、]*\s*)?([a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fa5]{2,10})\s*[:：]\s*([\s\S]*)$/);
    if (m) {
      if (currentKey) result[currentKey] = currentVal.join('\n').trim();
      currentKey = m[1];
      currentVal = [m[2]];
    } else if (currentKey) {
      currentVal.push(line);
    }
  }
  if (currentKey) result[currentKey] = currentVal.join('\n').trim();
  // 逐行解析结果也要做人物卡检测
  var charFields2 = 0;
  ['name','identity','camp','personality','backstory','obsession','weakness','goal','goals','cognitive_boundary','character_position'].forEach(function(f){ if(result[f]) charFields2++; });
  if (charFields2 >= 3) return {};
  return result;
}

window._labelOfWorldFieldKey = function(fieldKey) {
  // 英文key -> 中文标签（作为设定key显示）
  var map = {
    core_setting: '核心设定',
    era_background: '时代背景',
    overall_style: '整体风格',
    atmosphere: '氛围基调',
    main_roles_overview: '主要角色概览',
    other_settings: '其他设定',
    perspective_rules: '视角规则',
    sensory_limits: '感官限制',
    visual_style: '视觉风格'
  };
  return map[fieldKey] || fieldKey;
}

/* ===== Define renderSettingsEditor for enhanced UI ===== */
(function() {
  renderSettingsEditor = function(highlightKey) {
    const ed = document.getElementById('settings-editor');
    if (!ed) return;
    ed.innerHTML = '';
    const groups = {};
    (worldSettings || []).forEach(s => { if (!groups[s.group]) groups[s.group] = []; groups[s.group].push(s); });
    const worldItems = groups['世界观'] || [];
    // 过滤掉"角色"分组（人物在步骤2有专门编辑器，不应出现在世界观面板）
    const charGroups = Object.entries(groups).filter(([g]) => g !== '世界观' && g !== '角色');
    const chapterOptions = charGroups.map(([group]) => {
      const match = group.match(/第(\d+)章/);
      return match ? {num: parseInt(match[1]), label: group} : null;
    }).filter(Boolean).sort((a, b) => a.num - b.num);

    const filterDiv = document.createElement('div');
    filterDiv.className = 'settings-filter-bar';
    filterDiv.innerHTML = '<label class="settings-filter-label">章节角色：</label>';
    const filterSelect = document.createElement('select');
    filterSelect.className = 'settings-filter-select';
    filterSelect.innerHTML = '<option value="all">全部显示</option><option value="none">不显示角色</option>';
    chapterOptions.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.label;
      opt.textContent = ch.label;
      filterSelect.appendChild(opt);
    });
    filterSelect.value = currentSettingsChapter || 'all';
    filterSelect.addEventListener('change', (e) => { currentSettingsChapter = e.target.value; renderSettingsEditor(highlightKey); });
    filterDiv.appendChild(filterSelect);
    const countSpan = document.createElement('span');
    countSpan.className = 'settings-filter-count';
    countSpan.textContent = charGroups.reduce((sum, [, items]) => sum + items.length, 0) + ' 个角色';
    filterDiv.appendChild(countSpan);
    // 全部展开/折叠按钮
    const expandToggle = document.createElement('button');
    expandToggle.className = 'btn-sm';
    expandToggle.style.cssText = 'margin-left:auto;padding:4px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--ink);cursor:pointer;font-size:11px';
    expandToggle.textContent = '折叠全部';
    expandToggle.id = 'settings-expand-toggle';
    expandToggle.addEventListener('click', function() {
      const headers = ed.querySelectorAll('.settings-group-header');
      const bodies = ed.querySelectorAll('.section-body');
      const allExpanded = Array.from(headers).every(h => h.classList.contains('expanded'));
      if (allExpanded) {
        headers.forEach(h => h.classList.remove('expanded'));
        bodies.forEach(b => b.classList.add('collapsed'));
        expandToggle.textContent = '展开全部';
      } else {
        headers.forEach(h => h.classList.add('expanded'));
        bodies.forEach(b => b.classList.remove('collapsed'));
        expandToggle.textContent = '折叠全部';
      }
    });
    filterDiv.appendChild(expandToggle);
    ed.appendChild(filterDiv);

    // World settings section
    const worldSec = document.createElement('div');
    worldSec.className = 'settings-group';
    worldSec.innerHTML = '<div class="settings-group-header expanded"><h4>世界观</h4><span class="group-count">' + worldItems.length + '</span><div class="group-actions"><button class="btn-sm ai" data-act="ai-gen-world">🤖 AI生成</button><button class="btn-sm" data-act="ai-opt-world">✨ AI优化</button><button class="group-check-btn" data-act="check-world">🔍 全组检测</button><button class="btn-sm accept" data-act="save-world">💾 保存</button></div></div>';
    const worldBody = document.createElement('div');
    worldBody.className = 'section-body';
    worldItems.forEach(s => {
      const row = document.createElement('div');
      row.className = 'setting-row' + (s.key === highlightKey ? ' conflict-highlight' : '');
      row.id = 'set-' + s.key;
      row.innerHTML = '<div class="set-main"><span class="set-key">' + s.key.replace(/&/g, '&amp;') + '</span><textarea class="set-val" rows="2">' + s.val.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea></div><div class="setting-row-actions"><button class="sra-btn ft-gen" title="AI生成">🤖 生成</button><button class="sra-btn ft-opt" title="AI优化">✨ 优化</button><button class="sra-btn ft-check" title="检测">🔍 检测</button><button class="sra-btn move-group" title="移动分组">📁 移动</button><button class="sra-btn del" title="删除">🗑 删除</button></div>';
      const inp = row.querySelector('.set-val');
      inp.addEventListener('input', function() { s.val = this.value; this.classList.add('modified'); });
      // 点击整行打开详情编辑器 — 显示整个世界观分组的所有条目
      row.addEventListener('click', function(e) {
        if (e.target.closest('.sra-btn')) return; // 点击按钮时不触发
        document.querySelectorAll('.setting-row').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        // 构建字段数组 — 多字段表单模式
        var allWorldItems = (worldSettings || []).filter(function(x) { return x.group === '世界观'; });
        var fields = allWorldItems.map(function(x) {
          return {key: x.key, label: x.key, value: x.val || '', type: 'textarea', source: 'setting'};
        });
        showDetailEditor('世界观设定（全部）', '世界观设定 · 共' + allWorldItems.length + '项', null, {type: 'setting-group', group: '世界观', fields: fields});
      });
      row.querySelector('.del').addEventListener('click', () => {
        // P2-11: 删除前确认
        customConfirm('确定删除设定项「' + s.key + '」？', async function(ok) {
          if (!ok) return;
          const idx = worldSettings.indexOf(s);
          if (idx >= 0) { worldSettings.splice(idx, 1); renderSettingsEditor(); showToast('已删除');
            // 同步保存到后端，避免刷新后恢复
            if (typeof saveSettings === 'function') { try { await saveSettings(); } catch(e) {} }
          }
        });
      });
      // P3-15: 改组功能
      row.querySelector('.move-group').addEventListener('click', () => {
        var existingGroups = Array.from(new Set(worldSettings.map(function(x) { return x.group; })));
        var msg = '当前分组：' + s.group + '\n已有分组：' + existingGroups.join('、');
        customPrompt('移动到分组（' + msg + '）', s.group, function(newGroup) {
          if (newGroup && newGroup.trim() && newGroup.trim() !== s.group) {
            s.group = newGroup.trim();
            renderSettingsEditor();
            showToast('已移动到分组：' + newGroup.trim());
          }
        });
      });
      row.querySelector('.ft-gen').addEventListener('click', async function() {
        this.disabled = true; this.textContent = '⏳';
        try {
          const prompt = '请为小说设定项「' + s.key + '」生成内容。只返回内容文本，不要解释。';
          const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
          if (r.ok && r.content) { inp.value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim(); inp.dispatchEvent(new Event('input')); showToast('✅ AI已生成'); }
          else showToast('❌ 生成失败');
        } catch(e) { showToast('❌ ' + e.message); }
        this.disabled = false; this.textContent = '🤖';
      });
      row.querySelector('.ft-opt').addEventListener('click', async function() {
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
        showToast('🔍 检测中...');
        try {
          const text = inp.value.trim() || s.key;
          const result = await runCheck('quality', text, 'settings');
          showToast('✓ 检测完成');
        } catch(e) {
          showToast('检测失败: ' + e.message);
        }
      });
      worldBody.appendChild(row);
    });
    const addRow = document.createElement('div');
    addRow.className = 'settings-add-row';
    addRow.innerHTML = '<input type="text" placeholder="+ 添加设定项，回车确认...">';
    addRow.querySelector('input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && this.value.trim()) {
        const key = this.value.trim();
        if (!worldSettings.find(s => s.key === key && s.group === '世界观')) {
          worldSettings.push({key, val: '', group: '世界观'});
          renderSettingsEditor(key);
          showToast('已添加：' + key);
        } else { showToast('已存在：' + key); }
        this.value = '';
      }
    });
    worldBody.appendChild(addRow);
    worldSec.appendChild(worldBody);
    ed.appendChild(worldSec);

    // Group actions
    worldSec.querySelector('[data-act="ai-gen-world"]').addEventListener('click', async (e) => {
      const btn = e.target; btn.disabled = true; btn.textContent = '生成中...';
      var projGenre = (typeof currentProject !== 'undefined' && currentProject && currentProject.genre) ? currentProject.genre : '小说';
      const prompt = '请为' + projGenre + '小说生成世界观设定，以JSON数组格式返回，每项包含key和val字段。只返回JSON，不要解释。';
      try {
        const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
        if (r.ok && r.content) {
          try {
            const items = JSON.parse(r.content.replace(/```json|```/g, '').trim());
            if (Array.isArray(items)) {
              items.forEach(item => worldSettings.push({key: item.key, val: item.val, group: '世界观'}));
              await api('/api/project/settings', {method: 'POST', body: JSON.stringify({world_settings: worldSettings.filter(s => s.group === '世界观').reduce((acc, s) => {acc[s.key] = s.val; return acc;}, {})})});
              renderSettingsEditor(); showToast('AI已生成' + items.length + '条世界观设定');
            }
          } catch { showToast('AI返回格式异常'); }
        } else { showToast('生成失败'); }
      } catch(e) { showToast('请求失败:' + e.message); }
      btn.disabled = false; btn.textContent = '🤖 AI生成';
    });
    worldSec.querySelector('[data-act="ai-opt-world"]').addEventListener('click', async (e) => {
      const btn = e.target; btn.disabled = true; btn.textContent = '优化中...';
      const data = worldSettings.filter(s => s.group === '世界观').map(s => s.key + '：' + s.val).join('\n');
      try {
        const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: '请优化以下世界观设定，使表达更精炼：\n' + data}]})});
        if (r.ok) { showToast('优化完成'); } else { showToast('优化失败'); }
      } catch(e) { showToast('请求失败:' + e.message); }
      btn.disabled = false; btn.textContent = '✨ AI优化';
    });
    worldSec.querySelector('[data-act="check-world"]').addEventListener('click', async () => {
      showToast('🔍 全组检测中...');
      try {
        const allText = worldSettings.filter(s => s.group === '世界观').map(s => s.key + ': ' + s.val).join('\n');
        await runCheck('quality', allText, 'settings');
        showToast('✓ 世界观设定检测完成');
      } catch(e) {
        showToast('检测失败: ' + e.message);
      }
    });
    worldSec.querySelector('[data-act="save-world"]').addEventListener('click', async (e) => {
      const btn = e.target; btn.disabled = true; btn.textContent = '保存中...';
      const data = {};
      worldSettings.filter(s => s.group === '世界观').forEach(s => { data[s.key] = s.val; });
      const r = await api('/api/project/settings', {method: 'POST', body: JSON.stringify({world_settings: data})});
      if (r.ok) { showToast('世界观设定已保存'); } else { showToast('保存失败'); }
      btn.disabled = false; btn.textContent = '💾 保存';
    });

    // Character settings sections
    charGroups.forEach(([group, items]) => {
      // 修复：非"第N章"格式的分组（如"角色"、"事件"、"道具"）始终显示，不受章节筛选影响
      var isChapterGroup = /^第\d+章$/.test(group);
      if (isChapterGroup && currentSettingsChapter !== 'all' && currentSettingsChapter !== 'none' && group !== currentSettingsChapter) return;
      if (currentSettingsChapter === 'none' && isChapterGroup) return;
      const sec = document.createElement('div');
      sec.className = 'settings-group';
      sec.innerHTML = '<div class="settings-group-header expanded"><h4>' + group + '</h4><span class="group-count">' + items.length + '</span><div class="group-actions"><button class="btn-sm ai" data-act="ai-gen-char">🤖 AI生成</button><button class="btn-sm" data-act="ai-opt-char">✨ AI优化</button><button class="group-check-btn" data-act="check-char">🔍 全组检测</button><button class="btn-sm accept" data-act="save-char">💾 保存</button></div></div>';
      const body = document.createElement('div');
      body.className = 'section-body';
      items.forEach(s => {
        const row = document.createElement('div');
        row.className = 'setting-row' + (s.key === highlightKey ? ' conflict-highlight' : '');
        row.id = 'set-' + s.key;
        row.innerHTML = '<div class="set-main"><span class="set-key">' + s.key.replace(/&/g, '&amp;') + '</span><textarea class="set-val" rows="2">' + s.val.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea></div><div class="setting-row-actions"><button class="sra-btn ft-gen" title="AI生成">🤖 生成</button><button class="sra-btn ft-opt" title="AI优化">✨ 优化</button><button class="sra-btn ft-check" title="检测">🔍 检测</button><button class="sra-btn move-group" title="移动分组">📁 移动</button><button class="sra-btn del" title="删除">🗑 删除</button></div>';
        const inp = row.querySelector('.set-val');
        inp.addEventListener('input', function() { s.val = this.value; this.classList.add('modified'); });
        // 点击整行打开详情编辑器 — 显示该分组的所有条目
        row.addEventListener('click', function(e) {
          if (e.target.closest('.sra-btn')) return;
          document.querySelectorAll('.setting-row').forEach(r => r.classList.remove('active'));
          row.classList.add('active');
          // 构建字段数组 — 多字段表单模式
          var groupItems = (worldSettings || []).filter(function(x) { return x.group === group; });
          var fields = groupItems.map(function(x) {
            return {key: x.key, label: x.key, value: x.val || '', type: 'textarea', source: 'setting'};
          });
          showDetailEditor(group + '设定（全部）', group + '设定 · 共' + groupItems.length + '项', null, {type: 'setting-group', group: group, fields: fields});
        });
        row.querySelector('.del').addEventListener('click', () => {
          // P2-11: 删除前确认
          customConfirm('确定删除设定项「' + s.key + '」？', async function(ok) {
            if (!ok) return;
            const idx = worldSettings.indexOf(s);
            if (idx >= 0) { worldSettings.splice(idx, 1); renderSettingsEditor(); showToast('已删除');
              if (typeof saveSettings === 'function') { try { await saveSettings(); } catch(e) {} }
            }
          });
        });
        row.querySelector('.ft-gen').addEventListener('click', async function() {
          this.disabled = true; this.textContent = '⏳';
          try {
            const prompt = '请为小说角色设定项「' + s.key + '」生成内容。只返回内容文本，不要解释。';
            const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
            if (r.ok && r.content) { inp.value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim(); inp.dispatchEvent(new Event('input')); showToast('✅ AI已生成'); }
            else showToast('❌ 生成失败');
          } catch(e) { showToast('❌ ' + e.message); }
          this.disabled = false; this.textContent = '🤖';
        });
        row.querySelector('.ft-opt').addEventListener('click', async function() {
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
          showToast('🔍 检测中...');
          try {
            const text = inp.value.trim() || s.key;
            const result = await runCheck('quality', text, 'settings');
            showToast('✓ 检测完成');
          } catch(e) {
            showToast('检测失败: ' + e.message);
          }
        });
        body.appendChild(row);
      });
      const addRow2 = document.createElement('div');
      addRow2.className = 'settings-add-row';
      addRow2.innerHTML = '<input type="text" placeholder="+ 添加角色或设定项，回车确认...">';
      addRow2.querySelector('input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && this.value.trim()) {
          const key = this.value.trim();
          if (!worldSettings.find(s => s.key === key && s.group === group)) {
            worldSettings.push({key, val: '', group});
            renderSettingsEditor(key);
            showToast('已添加：' + key);
          } else { showToast('已存在：' + key); }
          this.value = '';
        }
      });
      body.appendChild(addRow2);
      sec.appendChild(body);
      ed.appendChild(sec);

      sec.querySelector('[data-act="ai-gen-char"]').addEventListener('click', async (e) => {
        const btn = e.target; btn.disabled = true; btn.textContent = '生成中...';
        const prompt = '请为小说[' + group + ']生成角色设定，JSON数组[{key:"角色名",val:"描述"}]。只返回JSON。';
        try {
          const r = await api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})});
          if (r.ok && r.content) {
            try {
              const items = JSON.parse(r.content.replace(/```json|```/g, '').trim());
              if (Array.isArray(items)) {
                items.forEach(item => worldSettings.push({key: item.key, val: item.val, group: group}));
                await api('/api/project/settings', {method: 'POST', body: JSON.stringify({character_settings: worldSettings.filter(s => s.group === group).reduce((acc, s) => {acc[s.key] = s.val; return acc;}, {})})});
                renderSettingsEditor(); showToast('AI已生成角色设定');
              }
            } catch { showToast('AI返回格式异常'); }
          } else { showToast('生成失败'); }
        } catch(e) { showToast('请求失败:' + e.message); }
        btn.disabled = false; btn.textContent = '🤖 AI生成';
      });
      sec.querySelector('[data-act="ai-opt-char"]').addEventListener('click', async (e) => {
        const btn = e.target; btn.disabled = true; btn.textContent = '优化中...';
        try {
          var itemsText = items.map(function(s) { return s.key + '：' + s.val; }).join('\n');
          var data = await api('/api/ai/chat', {method:'POST', body:JSON.stringify({messages:[{role:'user',content:'请优化以下角色设定，使其更详细、更有层次感：\n' + itemsText}]})});
          if (data.ok && data.content) {
            var lines = data.content.split('\n').filter(function(l) { return l.trim(); });
            lines.forEach(function(line) {
              var m = line.match(/^(.+?)[：:]\s*(.+)$/);
              if (m) {
                var existing = worldSettings.find(function(s) { return s.key === m[1].trim() && s.group === group; });
                if (existing) existing.val = m[2].trim();
              }
            });
            renderSettingsEditor();
            showToast('✓ 角色设定已优化');
          } else { showToast('优化失败'); }
        } catch(e) { showToast('请求失败: ' + e.message); }
        btn.disabled = false; btn.textContent = '✨ AI优化';
      });
      sec.querySelector('[data-act="check-char"]').addEventListener('click', async () => {
        showToast('🔍 全组检测中...');
        try {
          const data = items.map(s => s.key + '：' + s.val).join('\n');
          await runCheck('quality', data, 'settings');
          showToast('✓ 角色设定检测完成');
        } catch(e) {
          showToast('检测失败: ' + e.message);
        }
      });
      sec.querySelector('[data-act="save-char"]').addEventListener('click', async (e) => {
        const btn = e.target; btn.disabled = true; btn.textContent = '保存中...';
        const data = {};
        worldSettings.filter(s => s.group === group).forEach(s => { data[s.key] = s.val; });
        const r = await api('/api/project/settings', {method: 'POST', body: JSON.stringify({character_settings: data})});
        if (r.ok) { showToast('角色设定已保存'); } else { showToast('保存失败'); }
        btn.disabled = false; btn.textContent = '💾 保存';
      });
    });

    // 让 .settings-group-header 可点击切换展开/折叠
    ed.querySelectorAll('.settings-group-header').forEach(function(header) {
      header.addEventListener('click', function(e) {
        if (e.target.closest('.group-actions')) return;
        header.classList.toggle('expanded');
        var body = header.nextElementSibling;
        if (body && body.classList.contains('section-body')) {
          body.classList.toggle('collapsed');
        }
      });
    });
  };
})();

/* ===== Blueprint helper ===== */
// P3-16: 蓝图字段支持局部编辑
window.bpField = function(key, val, path) {
  var safePath = path ? path.replace(/'/g, "\\'") : '';
  return '<div class="bp-field"><span class="bp-key">' + esc(key) + '</span><span class="bp-val" contenteditable="true" data-bp-path="' + esc(safePath) + '" style="outline:none;border-radius:3px;padding:1px 3px" onfocus="this.style.background=\'var(--bg)\'" onblur="this.style.background=\'transparent\'">' + esc(val) + '</span></div>';
}

window.esc = function(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }


window._getEdgeColor = function(edge) {
  // 根据六轴值判断关系类型，返回对应颜色
  var absLr = Math.abs(edge.lr || 0);
  var absSd = Math.abs(edge.sd || 0);
  var absUd = Math.abs(edge.ud || 0);
  var absIo = Math.abs(edge.io || 0);
  var absFb = Math.abs(edge.fb || 0);
  // 优先级：敌对 > 合作 > 师徒 > 利益 > 情感
  if (absLr > 0.5 && edge.lr < 0) return '#e74c3c'; // 敌对
  if (absLr > 0.5 && edge.lr > 0) return '#2ecc71'; // 合作
  if (absUd > 0.5) return '#3498db'; // 师徒/层级
  if (absIo > 0.5 && edge.io < 0) return '#9b59b6'; // 利用
  if (absIo > 0.5 || absSd > 0.5) return '#f39c12'; // 情感
  return '#95a5a6'; // 其他
}

window._getEdgeLabel = function(edge) {
  var parts = [];
  if (edge.lr > 0.3) parts.push('合作');
  else if (edge.lr < -0.3) parts.push('竞争');
  if (edge.sd > 0.3) parts.push('共鸣');
  else if (edge.sd < -0.3) parts.push('冲突');
  if (edge.ud > 0.3) parts.push('仰视');
  else if (edge.ud < -0.3) parts.push('压制');
  if (edge.io > 0.3) parts.push('亲密');
  else if (edge.io < -0.3) parts.push('疏离');
  if (edge.fb > 0.3) parts.push('推动');
  else if (edge.fb < -0.3) parts.push('阻碍');
  if (edge.metadata && edge.metadata.relationship_text) {
    parts.push('（' + edge.metadata.relationship_text + '）');
  }
  return parts.join('、') || '关联';
}

window._escapeXml = function(s) {
  return String(s).replace(/[<>&"']/g, function(c) {
    return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&apos;'}[c];
  });
}

window.escHtml = function(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

})();