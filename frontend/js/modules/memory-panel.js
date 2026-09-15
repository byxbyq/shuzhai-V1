// 上下文面板：本章即时 + 搜索 + 质量检查（全书记忆/伏笔/时间线移至时间线页面）

function esc(s) { if (!s) return ''; return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

// ── Memory System: Build context from all chapters ──
// 优先使用后端 Truth Ledger 数据，fallback 到前端解析
async function buildMemoryContext(beforeChapter) {
  // 从后端 state_memory 蒸馏摘要读取，替代裸读 state/worldSettings/chapters 等全局变量
  var cutoff = (typeof beforeChapter === 'number') ? beforeChapter : 999;
  try {
    var r = await api('/api/project/state-memory?before_chapter=' + cutoff);
    if (r && r.ok && r.text) {
      return '【全书记忆上下文（蒸馏摘要）】\n\n' + r.text;
    }
  } catch(e) {}
  return '';
}

// ── 上下文面板（单Tab：搜索+本章即时+时间线入口） ──
(function setupContextPanel() {
  var searchInput = document.getElementById('mem-search-input');
  if (searchInput) {
    var searchTimer = null;
    searchInput.addEventListener('input', function() {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(function() {
        var query = searchInput.value.trim();
        if (query.length === 0) {
          var sr = document.getElementById('ctx-search-results');
          var cc = document.getElementById('ctx-content');
          if (sr) sr.style.display = 'none';
          if (cc) cc.style.display = '';
        } else if (query.length >= 1) {
          renderContextSearchResults(query.toLowerCase());
        }
      }, 250);
    });
    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (searchTimer) clearTimeout(searchTimer);
        var query = searchInput.value.trim();
        if (query) renderContextSearchResults(query.toLowerCase());
      }
    });
  }
})();

function loadContextPanelData() {
  try {
    if (typeof loadContextPanel === 'function') loadContextPanel();
  } catch(e) { console.error('loadContext error:', e); }
}

function renderContextSearchResults(query) {
  var resultsDiv = document.getElementById('ctx-search-results');
  var contentDiv = document.getElementById('ctx-content');
  if (!contentDiv) return;

  if (!resultsDiv) {
    resultsDiv = document.createElement('div');
    resultsDiv.id = 'ctx-search-results';
    resultsDiv.style.padding = '4px 12px 8px';
    contentDiv.parentNode.insertBefore(resultsDiv, contentDiv);
  }

  resultsDiv.style.display = '';
  contentDiv.style.display = 'none';

  var html = '';
  var found = 0;

  if (typeof worldSettings !== 'undefined' && worldSettings.length) {
    var settingMatches = worldSettings.filter(function(s) {
      return (s.key + ' ' + s.val + ' ' + (s.group||'')).toLowerCase().indexOf(query) >= 0;
    });
    if (settingMatches.length) {
      html += '<div class="mem-arc"><h4>匹配设定 (' + settingMatches.length + ')</h4>';
      settingMatches.forEach(function(s) {
        html += '<div style="padding:4px 8px;border-bottom:1px solid var(--border-soft);font-size:11px">';
        html += '<span class="text-accent">[' + esc(s.group||'') + ']</span> ';
        html += '<strong>' + esc(s.key) + '</strong>: <span class="text-muted">' + esc(s.val) + '</span>';
        html += '</div>';
        found++;
      });
      html += '</div>';
    }
  }

  html += '<div style="margin:12px 8px 8px;padding:8px 12px;background:var(--accent-soft);border-radius:4px;font-size:11px;color:var(--accent);cursor:pointer;text-align:center" onclick="openTimelinePanel()">';
  html += '⏱ 在时间线中查看角色/伏笔/事件 →';
  html += '</div>';

  if (found === 0) {
    html = '<div class="mem-arc"><h4>无匹配</h4><p style="color:var(--muted);font-size:12px;padding:8px">未找到包含"' + esc(query) + '"的设定</p></div>' + html;
  }

  resultsDiv.innerHTML = html;
}

function openTimelinePanel() {
  if (typeof switchChapterOutlineView === 'function') {
    var overlay = document.getElementById('chapter-outline-overlay');
    if (overlay) overlay.style.display = 'flex';
    switchChapterOutlineView('timeline');
  }
}


// ── AI Content Analysis & Extract Settings ──
(function setupAIExtract() {
  var btn = document.getElementById('btn-ai-extract');
  var clearBtn = document.getElementById('btn-ai-extract-clear');
  var input = document.getElementById('ai-extract-input');
  var resultDiv = document.getElementById('ai-extract-result');
  var dropZone = document.getElementById('ai-drop-zone');
  var fileInput = document.getElementById('ai-file-input');

  if (!btn || !input) return;

  // ── 文件拖拽上传 ──
  function setupDragDrop() {
    if (!dropZone) return;

    // 点击触发文件选择
    dropZone.addEventListener('click', function() { fileInput && fileInput.click(); });

    // 拖拽高亮
    ['dragenter', 'dragover'].forEach(function(evt) {
      dropZone.addEventListener(evt, function(e) {
        e.preventDefault(); e.stopPropagation();
        dropZone.style.borderColor = 'var(--accent)';
        dropZone.style.background = 'var(--accent-soft)';
      });
    });
    ['dragleave'].forEach(function(evt) {
      dropZone.addEventListener(evt, function(e) {
        e.preventDefault(); e.stopPropagation();
        dropZone.style.borderColor = 'var(--border)';
        dropZone.style.background = 'transparent';
      });
    });

    // 拖拽放下
    dropZone.addEventListener('drop', function(e) {
      e.preventDefault(); e.stopPropagation();
      dropZone.style.borderColor = 'var(--border)';
      dropZone.style.background = 'transparent';
      var files = e.dataTransfer.files;
      if (files.length) handleFiles(files);
    });

    // 文件选择
    if (fileInput) {
      fileInput.addEventListener('change', function() {
        if (fileInput.files.length) handleFiles(fileInput.files);
        fileInput.value = '';
      });
    }
  }

  // 处理文件列表
  async function handleFiles(files) {
    var validExt = ['.txt', '.md', '.text', '.markdown', '.docx', '.xlsx', '.csv', '.pdf'];
    var hasValid = false;
    for (var i = 0; i < files.length; i++) {
      var ext = '.' + files[i].name.split('.').pop().toLowerCase();
      if (validExt.indexOf(ext) !== -1) { hasValid = true; break; }
    }
    if (!hasValid) { showToast('不支持的文件格式，请使用 txt/md/docx/xlsx/csv/pdf'); return; }

    // 显示加载状态
    dropZone.innerHTML = '<div style="font-size:12px;color:var(--accent)">⏳ 正在解析文件...</div>';

    try {
      var formData = new FormData();
      for (var i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
      }
      var resp = await api('/api/file/parse', { method: 'POST', body: JSON.stringify({}) });
      var data = resp;

      if (data.ok && data.combined) {
        input.value = data.combined;
        var names = data.results.map(function(r) { return r.name + ' (' + (r.size || 0) + '字)'; }).join('、');
        showToast('已加载: ' + names);
      } else {
        showToast('文件解析失败: ' + (data.error || '未知错误'));
      }
    } catch (e) {
      showToast('文件读取失败: ' + e.message);
    } finally {
      // 恢复拖拽区域
      dropZone.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" style="stroke:var(--muted);fill:none;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;margin-bottom:4px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>'
        + '<div class="text-md text-muted">拖拽文件到此处，或<span style="color:var(--accent);cursor:pointer;text-decoration:underline">点击选择文件</span></div>'
        + '<div style="font-size:10px;color:var(--muted);opacity:0.6;margin-top:2px">支持 .txt .md .docx .xlsx .csv .pdf</div>'
        + '<input type="file" id="ai-file-input" accept=".txt,.md,.docx,.xlsx,.csv,.pdf,.text,.markdown" class="hidden" multiple>';
      // 重新绑定事件
      fileInput = document.getElementById('ai-file-input');
      setupDragDrop();
    }
  }

  setupDragDrop();

  // 清空按钮
  if (clearBtn) {
    clearBtn.addEventListener('click', function() {
      input.value = '';
      if (resultDiv) { resultDiv.style.display = 'none'; resultDiv.textContent = ''; }
    });
  }

  // AI分析按钮
  btn.addEventListener('click', async function() {
    var content = input.value.trim();
    if (!content) { showToast('请先粘贴内容或拖入文件'); return; }

    btn.disabled = true;
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" style="stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;animation:spin 1s linear infinite"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> AI分析中...';

    try {
      var data = await api('/api/ai/analyze-content', {
        method: 'POST',
        body: JSON.stringify({ content: content })
      });

      if (data.ok) {
        // 直接从响应数据回填 worldSettings（不依赖二次请求可能失败）
        if (data.settings && typeof data.settings === 'object' && Object.keys(data.settings).length > 0) {
          var extracted = [];
          Object.entries(data.settings).forEach(function([key, val]) {
            if (val && typeof val === 'string') {
              extracted.push({key: key, val: val, group: '世界观'});
            }
          });
          if (extracted.length >= 1) {
            // P0-2: 追加模式而非覆盖式 — 合并到现有 worldSettings
            var existingKeys = {};
            worldSettings.forEach(function(s) { existingKeys[s.key + '|' + s.group] = true; });
            extracted.forEach(function(item) {
              var k = item.key + '|' + item.group;
              if (!existingKeys[k]) {
                worldSettings.push(item);
                existingKeys[k] = true;
              }
            });
          }
        }
        // 二次加载作为补充（合并角色等额外数据）
        try { await loadProjectSettings(); } catch(e) { console.warn('loadProjectSettings fallback failed:', e); }
        if (typeof renderSettingsEditor === 'function') renderSettingsEditor();

        // 显示结果摘要
        var keys = Object.keys(data.settings || {});
        if (resultDiv) {
          resultDiv.innerHTML = '<div style="padding:8px 10px;background:var(--success-soft);border:1px solid var(--success);border-radius:var(--radius-sm);color:var(--success);font-size:12px">✅ 成功提取 ' + keys.length + ' 项设定：' + keys.join('、') + '</div>';
          resultDiv.style.display = 'block';
        }
        showToast('AI分析完成，已提取 ' + keys.length + ' 项设定');
      } else {
        showToast('AI分析失败: ' + (data.error || '未知错误'));
        if (resultDiv) {
          resultDiv.innerHTML = '<div style="padding:8px 10px;background:var(--error-soft);border:1px solid var(--error);border-radius:var(--radius-sm);color:var(--error);font-size:12px">❌ ' + (data.error || '分析失败') + '</div>';
          resultDiv.style.display = 'block';
        }
      }
    } catch (e) {
      showToast('请求失败: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" style="stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> 🤖 AI分析并提取设定';
    }
  });
})();

// ── P2-10: Settings Import/Export ──
(function setupSettingsImportExport() {
  var exportBtn = document.getElementById('btn-export-settings');
  var importBtn = document.getElementById('btn-import-settings');
  var fileInput = document.getElementById('settings-file-input');

  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      try {
        var data = JSON.stringify(worldSettings || [], null, 2);
        var blob = new Blob([data], {type: 'application/json'});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'settings_export_' + new Date().toISOString().slice(0,10) + '.json';
        a.click();
        URL.revokeObjectURL(url);
        showToast && showToast('设定已导出');
      } catch(e) { showToast && showToast('导出失败: ' + e.message); }
    });
  }

  if (importBtn && fileInput) {
    importBtn.addEventListener('click', function() { fileInput.click(); });
    fileInput.addEventListener('change', function(e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function(ev) {
        try {
          var imported = JSON.parse(ev.target.result);
          if (!Array.isArray(imported)) { showToast('文件格式错误：需要数组'); return; }
          // 追加模式导入
          var existingKeys = {};
          (worldSettings || []).forEach(function(s) { existingKeys[s.key + '|' + s.group] = true; });
          var added = 0;
          imported.forEach(function(item) {
            if (item && item.key && item.val) {
              var k = item.key + '|' + (item.group || '世界观');
              if (!existingKeys[k]) {
                worldSettings.push({key: item.key, val: item.val, group: item.group || '世界观'});
                existingKeys[k] = true;
                added++;
              }
            }
          });
          if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
          showToast('已导入 ' + added + ' 项设定');
        } catch(err) { showToast('导入失败: ' + err.message); }
        fileInput.value = '';
      };
      reader.readAsText(file);
    });
  }
})();

// ═══════════════════════════════════════════
// 上下文面板：折叠区块
// ═══════════════════════════════════════════

// 折叠/展开记忆区块
function toggleMemBlock(blockName) {
  var body = document.getElementById('mem-block-body-' + blockName);
  var header = document.getElementById('mem-block-' + blockName);
  if (!body || !header) return;
  var arrow = header.querySelector('.mem-block-arrow');
  if (body.style.display === 'none') {
    body.style.display = '';
    if (arrow) arrow.textContent = '▼';
  } else {
    body.style.display = 'none';
    if (arrow) arrow.textContent = '▶';
  }
}

// ═══════════════════════════════════════════
// 挂载关键函数到 ShuZhai 命名空间
// ═══════════════════════════════════════════
window.ShuZhai = window.ShuZhai || {};
window.ShuZhai.loadProjectSettings     = loadProjectSettings;
window.ShuZhai.loadProjectOutline      = loadProjectOutline;
window.ShuZhai.loadChaptersFromAPI     = loadChaptersFromAPI;
window.ShuZhai.loadChapterContentAPI   = loadChapterContentAPI;
window.ShuZhai.loadContextPanel        = loadContextPanel;
try { window.ShuZhai.goToStep = goToStep; } catch(e) { window.ShuZhai.goToStep = function(n){ if(typeof goToStep==='function') goToStep(n); }; }
window.ShuZhai.saveChapterContent      = saveChapter;
window.ShuZhai.showToast               = showToast;
window.ShuZhai.workflowState           = workflowState;
window.ShuZhai.chapters                = chapters;
window.ShuZhai.currentChapterIndex     = currentChapterIndex;
window.ShuZhai.worldSettings           = worldSettings;

// 暴露到全局作用域，供HTML onclick调用
// 注意：goToStep等函数定义在index.html的内联script中（在app.js之后加载），
// 所以这里不能直接引用，用try-catch保护，失败则由index.html内联script自行暴露
try { if (typeof goToStep !== 'undefined') window.goToStep = goToStep; } catch(e) {}
try { if (typeof loadContextPanel !== 'undefined') window.loadContextPanel = loadContextPanel; } catch(e) {}
try { if (typeof loadProjectSettings !== 'undefined') window.loadProjectSettings = loadProjectSettings; } catch(e) {}
try { if (typeof loadProjectOutline !== 'undefined') window.loadProjectOutline = loadProjectOutline; } catch(e) {}
window.loadChaptersFromAPI = loadChaptersFromAPI;
window.loadChapterContentAPI = loadChapterContentAPI;
window.saveChapter = saveChapter;
window.showToast = showToast;

// P2-13: 自动保存（30秒间隔）
window._autoSaveTimer = setInterval(function() {
  if (currentChapterIndex >= 0 && chapters && chapters[currentChapterIndex]) {
    var editorEl = document.getElementById('editor-content');
    if (editorEl) {
      // 草稿模式下跳过AutoSave，防止草稿测试数据被写入磁盘
      if (window.DraftManager && DraftManager.isActive()) return;
      var content = editorEl.innerText || '';
      if (content.trim() && chapters[currentChapterIndex].content !== content) {
        saveChapter(currentChapterIndex, content).then(function() {
          chapters[currentChapterIndex].content = content;
          console.log('[AutoSave] Content saved at', new Date().toLocaleTimeString());
        }).catch(function(e) {
          console.warn('[AutoSave] Failed:', e);
        });
      }
    }
  }
}, 30000);

// ═══════════════════════════════════════════
// 工具箱功能 (8大新功能前端交互)
// ═══════════════════════════════════════════

// 通用：关闭弹窗
// 页面卸载时清理定时器
window.addEventListener('beforeunload', function() {
  if (window._autoSaveTimer) clearInterval(window._autoSaveTimer);
});
