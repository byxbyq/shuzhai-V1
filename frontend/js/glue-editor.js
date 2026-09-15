(function() {
  'use strict';


// ═══════════════════════════════════════════
// Detail Editor (Steps 1-3)
// ═══════════════════════════════════════════

var currentDetailItem = null; // {type: 'setting'|'outline', key: string, data: object, textareaEl: element}

window.showDetailEditorEmpty = function() {
  document.getElementById('detail-editor-empty').style.display = 'flex';
  document.getElementById('detail-editor-header').classList.add('hidden');
  document.getElementById('detail-editor-textarea').classList.add('hidden');
  var formEl = document.getElementById('detail-editor-form');
  if (formEl) { formEl.classList.add('hidden'); formEl.innerHTML = ''; }
  var volPanel = document.getElementById('vol-detail-panel');
  if (volPanel) volPanel.style.display = 'none';
  currentDetailItem = null;
}

window.showDetailEditor = function(title, subtitle, content, itemData) {
  document.getElementById('detail-editor-empty').style.display = 'none';
  document.getElementById('detail-editor-header').classList.remove('hidden');
  document.getElementById('detail-editor-title').textContent = title;
  document.getElementById('detail-editor-subtitle').textContent = subtitle;

  var formEl = document.getElementById('detail-editor-form');
  var ta = document.getElementById('detail-editor-textarea');

  if (itemData && itemData.fields && Array.isArray(itemData.fields)) {
    // 多字段表单模式
    ta.classList.add('hidden');
    if (formEl) {
      formEl.classList.remove('hidden');
      formEl.innerHTML = '';
      renderDetailForm(formEl, itemData.fields, itemData);
    }
  } else {
    // 原有的 textarea 模式（向后兼容蓝图等）
    if (formEl) { formEl.classList.add('hidden'); formEl.innerHTML = ''; }
    ta.classList.remove('hidden');
    ta.value = content || '';
    ta.focus();
  }
  currentDetailItem = itemData;
}

// 表单模式：从多字段表单读取值同步回源
window.syncFormFieldsToSource = function(itemData) {
  var formEl = document.getElementById('detail-editor-form');
  if (!formEl) return;

  var fields = itemData.fields;
  var type = itemData.type;

  fields.forEach(function(f) {
    var fieldEl = formEl.querySelector('[data-field-key="' + f.key + '"]');
    if (!fieldEl) return;

    if (f.type === 'char-arc') {
      var nameInput = fieldEl.querySelector('.def-char-name');
      var arcInput = fieldEl.querySelector('.def-arc-text');
      if (nameInput) f.charName = nameInput.value;
      if (arcInput) f.arcText = arcInput.value;
    } else if (f.type === 'hook') {
      var hookInput = fieldEl.querySelector('.def-hook-text');
      if (hookInput) f.value = hookInput.value;
    } else if (f.type === 'text') {
      var textInput = fieldEl.querySelector('.def-input');
      if (textInput) f.value = textInput.value;
    } else {
      var ta = fieldEl.querySelector('.def-textarea');
      if (ta) f.value = ta.value;
    }
  });

  // 根据类型同步回数据源
  if (type === 'setting-group') {
    var groupName = itemData.group || '世界观';
    var groupItems = (worldSettings || []).filter(function(x) { return x.group === groupName; });
    fields.forEach(function(f) {
      var item = groupItems.find(function(x) { return x.key === f.key; });
      if (item) {
        item.val = f.value || '';
        var rowEl = document.getElementById('set-' + f.key);
        if (rowEl) {
          var smallTa = rowEl.querySelector('.set-val');
          if (smallTa && smallTa.value !== (f.value || '')) smallTa.value = f.value || '';
        }
      }
    });
  } else if (type === 'novel-outline-group') {
    if (!_novelOutlineDict) return;
    fields.forEach(function(f) {
      if (f.source === 'field' && f.dataKey) {
        _novelOutlineDict[f.dataKey] = f.value || '';
        var fEl = document.querySelector('.nv-field[data-key="' + f.dataKey + '"]');
        if (fEl && fEl.value !== (f.value || '')) fEl.value = f.value || '';
      } else if (f.source === 'char-arc' && f.arcIndex !== undefined) {
        if (!_novelOutlineDict.character_arcs) _novelOutlineDict.character_arcs = [];
        if (!_novelOutlineDict.character_arcs[f.arcIndex]) _novelOutlineDict.character_arcs[f.arcIndex] = {character: '', arc: ''};
        _novelOutlineDict.character_arcs[f.arcIndex].character = f.charName || '';
        _novelOutlineDict.character_arcs[f.arcIndex].arc = f.arcText || '';
        var nameInputs = document.querySelectorAll('.nv-char-name');
        var arcTexts = document.querySelectorAll('.nv-char-arc-text');
        if (nameInputs[f.arcIndex] && nameInputs[f.arcIndex].value !== (f.charName || '')) nameInputs[f.arcIndex].value = f.charName || '';
        if (arcTexts[f.arcIndex] && arcTexts[f.arcIndex].value !== (f.arcText || '')) arcTexts[f.arcIndex].value = f.arcText || '';
      } else if (f.source === 'hook' && f.hookIndex !== undefined) {
        if (!_novelOutlineDict.key_hooks) _novelOutlineDict.key_hooks = [];
        if (!_novelOutlineDict.key_hooks[f.hookIndex]) _novelOutlineDict.key_hooks[f.hookIndex] = {content: ''};
        _novelOutlineDict.key_hooks[f.hookIndex].content = f.value || '';
        var hookInputs = document.querySelectorAll('.nv-hook-text');
        if (hookInputs[f.hookIndex] && hookInputs[f.hookIndex].value !== (f.value || '')) hookInputs[f.hookIndex].value = f.value || '';
      }
    });
  } else if (type === 'outline-group') {
    if (!chOutline) return;
    fields.forEach(function(f) {
      var idx = f.outlineIndex;
      if (idx !== undefined && idx >= 0 && idx < chOutline.length) {
        chOutline[idx].text = f.value || '';
        chOutline[idx].source = 'human-edited';
        var oiRows = document.querySelectorAll('.outline-item .oi-input');
        if (oiRows[idx] && oiRows[idx].value !== (f.value || '')) oiRows[idx].value = f.value || '';
      }
    });
    saveChapterOutline();
  } else if (type === 'blueprint-group') {
    // 蓝图多字段同步回 window._currentBlueprint
    if (!window._currentBlueprint) return;
    fields.forEach(function(f) {
      if (!f.bpPath) return;
      var parts = f.bpPath.split('.');
      var obj = window._currentBlueprint;
      for (var i = 0; i < parts.length - 1; i++) {
        var p = parts[i];
        if (/^\d+$/.test(p)) {
          // 数字索引（数组）
          var idx = parseInt(p);
          if (!obj[idx]) obj[idx] = {};
          obj = obj[idx];
        } else {
          if (!obj[p]) obj[p] = {};
          obj = obj[p];
        }
      }
      var lastKey = parts[parts.length - 1];
      obj[lastKey] = f.value || '';
    });
    // 同步到左侧蓝图显示
    document.querySelectorAll('.bp-val').forEach(function(el) {
      var path = el.dataset.bpPath || '';
      if (!path || !window._currentBlueprint) return;
      var parts = path.split('.');
      var obj = window._currentBlueprint;
      for (var i = 0; i < parts.length - 1; i++) {
        var p = parts[i];
        obj = /^\d+$/.test(p) ? obj[parseInt(p)] : obj[p];
        if (!obj) return;
      }
      var lastKey = parts[parts.length - 1];
      var val = obj[lastKey] || '';
      if (el.textContent !== val) el.textContent = val;
    });
    // 同步到 chapters
    if (typeof chapters !== 'undefined' && typeof currentChapterIndex !== 'undefined' && chapters && chapters[currentChapterIndex]) {
      chapters[currentChapterIndex].blueprint = window._currentBlueprint;
    }
    saveChapterOutline();
  }
}

// 同步大编辑框内容回左侧小输入框
window.syncDetailToSource = function() {
  if (!currentDetailItem) return;

  // 表单模式：从多字段表单读取值同步回源
  if (currentDetailItem.fields && Array.isArray(currentDetailItem.fields)) {
    syncFormFieldsToSource(currentDetailItem);
    return;
  }

  var ta = document.getElementById('detail-editor-textarea');
  var newVal = ta.value;
  if (currentDetailItem.type === 'setting-group') {
    // 按"key：value"格式解析回各条目
    var lines = newVal.split(/\n\n/);
    var groupName = currentDetailItem.group || '世界观';
    var groupItems = (worldSettings || []).filter(function(x) { return x.group === groupName; });
    lines.forEach(function(line) {
      var m = line.match(/^(.+?)：(.*)$/s);
      if (m) {
        var k = m[1].trim();
        var v = m[2].trim();
        var item = groupItems.find(function(x) { return x.key === k; });
        if (item) {
          item.val = v;
          var rowEl = document.getElementById('set-' + k);
          if (rowEl) {
            var smallTa = rowEl.querySelector('.set-val');
            if (smallTa) smallTa.value = v;
          }
        }
      }
    });
  } else if (currentDetailItem.type === 'setting') {
    // 更新数据模型
    currentDetailItem.data.val = newVal;
    // 更新左侧小输入框
    var row = document.getElementById('set-' + currentDetailItem.key);
    if (row) {
      var smallTa = row.querySelector('.set-val');
      if (smallTa) smallTa.value = newVal;
    }
  } else if (currentDetailItem.type === 'outline') {
    currentDetailItem.data.text = newVal;
    // 更新左侧小输入框 - 章节大纲 (oi-input)
    var chRow = document.querySelector('.outline-item.current');
    if (chRow) {
      var chInp = chRow.querySelector('.oi-input');
      if (chInp) chInp.value = newVal;
    }
  } else if (currentDetailItem.type === 'outline-group') {
    // 按"编号. 内容"格式解析回各条目
    var olSections = newVal.split(/\n\n/);
    var parsedItems = [];
    olSections.forEach(function(sec) {
      var m = sec.match(/^\d+\.\s*(.*)$/s);
      if (m) {
        parsedItems.push({text: m[1].trim(), current: false, source: 'human-edited'});
      }
    });
    if (parsedItems.length > 0) {
      chOutline.length = 0;
      parsedItems.forEach(function(item) { chOutline.push(item); });
      // 更新左侧小输入框
      var oiRows = document.querySelectorAll('.outline-item');
      oiRows.forEach(function(row, idx) {
        if (idx < parsedItems.length) {
          var inp = row.querySelector('.oi-input');
          if (inp) inp.value = parsedItems[idx].text;
        }
      });
    }
  } else if (currentDetailItem.type === 'novel-outline-group') {
    // 按"标签：value"格式解析回各字段
    var labelsRev = {'🎯 主题':'theme','⚔️ 核心冲突':'core_conflict','📖 故事走向':'story_arc','🌍 世界观锚点':'world_anchor','🏁 结局指引':'ending','🎭 基调':'tone'};
    var sections = newVal.split(/\n\n/);
    sections.forEach(function(sec) {
      // 普通字段
      var m = sec.match(/^(.+?)：(.*)$/s);
      if (m) {
        var label = m[1].trim();
        var val = m[2].trim();
        var fk = labelsRev[label];
        if (fk) {
          var fEl = document.querySelector('.nv-field[data-key="' + fk + '"]');
          if (fEl) fEl.value = val;
          if (_novelOutlineDict) _novelOutlineDict[fk] = val;
        }
      }
    });
  } else if (currentDetailItem.type === 'novel-outline') {
    // 同步中间编辑器内容回全书大纲字段
    if (currentDetailItem.el) {
      currentDetailItem.el.value = newVal;
    }
    if (_novelOutlineDict && currentDetailItem.key) {
      _novelOutlineDict[currentDetailItem.key] = newVal;
    }
  } else if (currentDetailItem.type === 'novel-outline-char-name') {
    // 同步角色名
    if (currentDetailItem.el) {
      currentDetailItem.el.value = newVal;
    }
    if (_novelOutlineDict && _novelOutlineDict.character_arcs) {
      var row = currentDetailItem.el ? currentDetailItem.el.closest('.nv-char-arc') : null;
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : currentDetailItem.index;
      if (typeof idx === 'number' && idx >= 0) {
        if (!_novelOutlineDict.character_arcs[idx]) {
          _novelOutlineDict.character_arcs[idx] = {character: '', arc: ''};
        }
        _novelOutlineDict.character_arcs[idx].character = newVal;
      }
    }
  } else if (currentDetailItem.type === 'novel-outline-char-arc') {
    // 同步角色弧光内容
    if (currentDetailItem.el) {
      currentDetailItem.el.value = newVal;
    }
    if (_novelOutlineDict && _novelOutlineDict.character_arcs) {
      var row = currentDetailItem.el ? currentDetailItem.el.closest('.nv-char-arc') : null;
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : currentDetailItem.index;
      if (typeof idx === 'number' && idx >= 0) {
        if (!_novelOutlineDict.character_arcs[idx]) {
          _novelOutlineDict.character_arcs[idx] = {character: '', arc: ''};
        }
        _novelOutlineDict.character_arcs[idx].arc = newVal;
      }
    }
  } else if (currentDetailItem.type === 'novel-outline-key-hook') {
    // 同步关键伏笔内容
    if (currentDetailItem.el) {
      currentDetailItem.el.value = newVal;
    }
    if (_novelOutlineDict && _novelOutlineDict.key_hooks) {
      var row = currentDetailItem.el ? currentDetailItem.el.closest('.nv-key-hook') : null;
      var idx = row && row.parentElement ? Array.from(row.parentElement.children).indexOf(row) : currentDetailItem.index;
      if (typeof idx === 'number' && idx >= 0) {
        if (!_novelOutlineDict.key_hooks[idx]) {
          _novelOutlineDict.key_hooks[idx] = {content: ''};
        }
        _novelOutlineDict.key_hooks[idx].content = newVal;
      }
    }
  } else if (currentDetailItem.type === 'blueprint') {
    // 同步中间编辑器内容回蓝图字段
    if (currentDetailItem.el) {
      currentDetailItem.el.textContent = newVal;
    }
    // 更新 window._currentBlueprint
    if (window._currentBlueprint && currentDetailItem.key) {
      var parts = currentDetailItem.key.split('.');
      var obj = window._currentBlueprint;
      for (var i = 0; i < parts.length - 1; i++) {
        if (obj[parts[i]]) obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = newVal;
      // 同步到 chapters
      if (typeof chapters !== 'undefined' && typeof currentChapterIndex !== 'undefined' && chapters && chapters[currentChapterIndex]) {
        chapters[currentChapterIndex].blueprint = window._currentBlueprint;
      }
    }
  }
}

// 大编辑框输入时实时同步
document.addEventListener('DOMContentLoaded', function() {
  var ta = document.getElementById('detail-editor-textarea');
  if (ta) {
    ta.addEventListener('input', syncDetailToSource);
  }
});

window.saveDetailItem = function() {
  syncDetailToSource();
  if (currentDetailItem) {
    if (currentDetailItem.type === 'setting' || currentDetailItem.type === 'setting-group') {
      saveSettings();
    } else if (currentDetailItem.type === 'outline' || currentDetailItem.type === 'outline-group' || currentDetailItem.type === 'blueprint' || currentDetailItem.type === 'blueprint-group') {
      saveOutline();
    } else if (currentDetailItem.type === 'novel-outline' || currentDetailItem.type === 'novel-outline-group' || currentDetailItem.type === 'novel-outline-char-name' || currentDetailItem.type === 'novel-outline-char-arc' || currentDetailItem.type === 'novel-outline-key-hook') {
      api('/api/project/novel-outline', {
        method: 'POST',
        body: JSON.stringify({novel_outline: _novelOutlineDict})
      }).then(function() { showToast('💾 全书大纲已保存'); })
        .catch(function(e) { console.error('Save structured outline failed:', e); showToast('保存失败'); });
      return;
    }
  }
  showToast('💾 已保存');
}

window.aiGenDetailItem = function() {
  if (!currentDetailItem) return;
  var ta = document.getElementById('detail-editor-textarea');
  var prompt = '请为「' + currentDetailItem.key + '」生成内容。只返回内容文本，不要解释。';
  if (ta.value.trim()) {
    prompt = '请基于以下内容，为「' + currentDetailItem.key + '」生成更完善的内容。只返回内容文本，不要解释。\n\n当前内容：\n' + ta.value.trim();
  }
  showToast('🤖 AI生成中...');
  api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})})
    .then(function(r) {
      if (r.ok && r.content) {
        ta.value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim();
        syncDetailToSource();
        showToast('✅ AI已生成');
      } else showToast('❌ 生成失败');
    })
    .catch(function(e) { showToast('❌ ' + e.message); });
}

window.aiOptDetailItem = function() {
  if (!currentDetailItem) return;
  var ta = document.getElementById('detail-editor-textarea');
  if (!ta.value.trim()) { showToast('⚠️ 内容为空'); return; }
  showToast('✨ AI优化中...');
  var prompt = '请优化以下文本，保持原意，让表达更精炼有力：\n' + ta.value.trim();
  api('/api/ai/chat', {method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]})})
    .then(function(r) {
      if (r.ok && r.content) {
        ta.value = r.content.replace(/^```[\s\S]*?```$/gm, '').trim();
        syncDetailToSource();
        showToast('✅ 已优化');
      } else showToast('❌ 优化失败');
    })
    .catch(function(e) { showToast('❌ ' + e.message); });
}

window.checkDetailItem = function() {
  if (!currentDetailItem) return;
  var ta = document.getElementById('detail-editor-textarea');
  var text = ta.value.trim() || currentDetailItem.key;
  showToast('🔍 检测中...');
  runCheck('quality', text, currentDetailItem.type === 'setting' ? 'settings' : 'outline')
    .then(function() { showToast('✓ 检测完成'); })
    .catch(function(e) { showToast('检测失败: ' + e.message); });
}

window.prevChapter = function() {
  if (typeof currentChapterIndex === 'undefined') return;
  if (currentChapterIndex <= 0) { showToast('已经是第一章'); return; }
  currentChapterIndex--;
  if (typeof loadChapterOutline === 'function') loadChapterOutline(currentChapterIndex);
  if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(currentChapterIndex);
  document.getElementById('wt-chapter-label').textContent = (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) ? (chapters[currentChapterIndex].title || ('第' + (currentChapterIndex+1) + '章')) : ('第' + (currentChapterIndex+1) + '章');
}
window.nextChapter = function() {
  if (typeof currentChapterIndex === 'undefined') return;
  if (typeof chapters === 'undefined' || !chapters) return;
  if (currentChapterIndex >= chapters.length - 1) { showToast('已经是最后一章'); return; }
  currentChapterIndex++;
  if (typeof loadChapterOutline === 'function') loadChapterOutline(currentChapterIndex);
  if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(currentChapterIndex);
  document.getElementById('wt-chapter-label').textContent = (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) ? (chapters[currentChapterIndex].title || ('第' + (currentChapterIndex+1) + '章')) : ('第' + (currentChapterIndex+1) + '章');
}

})();