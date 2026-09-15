// Extracted from app.js - 工具箱8大面板 (导出/导入/快照对比/角色对话/同步/模板/批量检查/统计)
function closeOverlay(id) {
  var el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

// 通用：清除AI编辑批注（与后端 _strip_edit_annotations 规则保持一致）
// 注意：此处规则必须与 backend/routers/chapter.py 中的 _strip_edit_annotations 完全对齐
function _stripEditAnnotations(text) {
  if (!text) return text;
  // 1. Markdown标题行（#### 问题5的确认 等）——正常小说正文不会用#标题
  text = text.replace(/^#{1,6}\s+[^\n]*\n?/gm, '');
  // 2. Markdown分隔线（---）单独成行
  text = text.replace(/^---+\s*\n/gm, '');
  // 3. 行首批注：**修改建议：** / **编辑注：** 等
  text = text.replace(/^\*\*[^*]+[：:]\*\*\s*.*$/gm, '');
  // 4. 行首孤立**片段（如 **了。 或 **某词）
  text = text.replace(/^\*\*[^*\n]{0,50}\n?/gm, '');
  // 5. 【文字】格式的编辑标记行
  text = text.replace(/^【[^】\n]{2,30}】[：:]?[^\n]*\n?/gm, '');
  // 6. 方括号批注：[编辑：...] / [修改：...] / [建议：...] / [批注：...] / [评审：...] / [纠错：...] / [润色：...]
  text = text.replace(/\[[编辑修改建议批注评审纠错润色][：:].*?\]/g, '');
  // 7. 花括号批注：{编辑：...}
  text = text.replace(/\{编辑[：:].*?\}/g, '');
  // 8. 独立行以 箭头→/➜/✏️/📝/🔧 开头的修改指示
  text = text.replace(/^(?:→|➜|✏️|📝|🔧)\s*.+$/gm, '');
  // 9. 内联编辑指令："在第2章末尾，增加一句..."等（AI修复可能将指令混入正文）
  text = text.replace(/在第\d+章(?:末尾|开头|中间|前|后|中)?[，,][^。\n]*?[。]\s*/g, '');
  // 10. 清除多余空行
  text = text.replace(/\n{3,}/g, '\n\n');
  return text.trim();
}

// 工具箱下拉菜单
function toggleToolbox(e) {
  if (e) e.stopPropagation();
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = (dd.style.display === 'none') ? 'block' : 'none';
}
document.addEventListener('click', function(e) {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd && dd.style.display === 'block' && !e.target.closest('#toolbox-dropdown') && !e.target.closest('button[onclick^="toggleToolbox"]')) {
    dd.style.display = 'none';
  }
});

// 在 APK/WebView 中打开应用内页面（避免 window.open('_blank') 被拦截）
function openToolboxPage(url) {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  if (typeof Capacitor !== 'undefined' && Capacitor.isNative) {
    window.location.href = url;
  } else {
    window.location.href = url;
  }
}

// ── 1. 导出 ──
function openExportPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  document.getElementById('export-overlay').style.display = 'flex';
}

// ── 1b. 导入小说（M10）──
function openImportPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  if (!document.getElementById('import-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'import-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1100';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1101;width:92%;max-width:620px;height:80vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">📤</span><span class="title-accent-md-xl">导入小说</span></div>'
      + '    <button onclick="closeOverlay(\'import-overlay\')" class="btn-ghost-icon-xl-alt">✕</button>'
      + '  </div>'
      + '  <div style="padding:16px 20px;overflow-y:auto;flex:1">'
      + '    <div style="font-size:12px;color:var(--muted);margin-bottom:12px">支持导入 .txt 格式的小说文本。系统将自动按"第X章"分割章节、提取角色、生成摘要大纲。</div>'
      + '    <div id="import-drop-zone" style="border:2px dashed var(--border);border-radius:var(--radius-sm);padding:30px;text-align:center;margin-bottom:12px;cursor:pointer">'
      + '      <div style="font-size:28px;margin-bottom:8px">📄</div>'
      + '      <div style="font-size:13px;color:var(--muted)">拖拽 .txt 文件到此处，或<span class="text-accent-underline">点击选择文件</span></div>'
      + '      <input type="file" id="import-file-input" accept=".txt,.text" class="hidden">'
      + '    </div>'
      + '    <div style="margin-bottom:12px">'
      + '      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">或直接粘贴文本：</div>'
      + '      <textarea id="import-text-input" placeholder="粘贴小说全文（需包含"第一章"等章节标记）..." style="width:100%;min-height:120px;max-height:200px;padding:8px 10px;border:1px solid var(--border-soft);border-radius:var(--radius-sm);background:var(--bg);color:var(--ink);font-size:12px;font-family:var(--sans);resize:vertical;line-height:1.6"></textarea>'
      + '    </div>'
      + '    <button id="btn-import-novel" style="width:100%;padding:10px;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#fff;font-size:13px;cursor:pointer;font-weight:600">📤 开始导入</button>'
      + '    <div id="import-result" class="mt-3"></div>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(overlay);

    // 文件选择
    var fileInput = document.getElementById('import-file-input');
    var dropZone = document.getElementById('import-drop-zone');
    var textInput = document.getElementById('import-text-input');

    dropZone.addEventListener('click', function() { fileInput.click(); });
    fileInput.addEventListener('change', function(e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function(ev) {
        textInput.value = ev.target.result;
        showToast('已加载文件: ' + file.name);
      };
      reader.readAsText(file, 'UTF-8');
    });

    // 拖拽支持
    dropZone.addEventListener('dragover', function(e) { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; });
    dropZone.addEventListener('dragleave', function(e) { dropZone.style.borderColor = 'var(--border)'; });
    dropZone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropZone.style.borderColor = 'var(--border)';
      var file = e.dataTransfer.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function(ev) {
        textInput.value = ev.target.result;
        showToast('已加载文件: ' + file.name);
      };
      reader.readAsText(file, 'UTF-8');
    });

    // 导入按钮
    document.getElementById('btn-import-novel').addEventListener('click', async function() {
      var text = textInput.value.trim();
      if (!text || text.length < 50) {
        document.getElementById('import-result').innerHTML = '<div style="color:var(--warn);font-size:12px;padding:8px">⚠️ 请输入至少50字的小说文本</div>';
        return;
      }
      var btn = this;
      btn.disabled = true;
      btn.textContent = '⏳ 导入中...';
      document.getElementById('import-result').innerHTML = '<div style="color:var(--muted);font-size:12px;padding:8px">⏳ 正在分析文本、分割章节、提取角色...</div>';

      try {
        var formData = new FormData();
        formData.append('file', new Blob([text], {type:'text/plain'}), 'import.txt');
        var r = await fetch('/api/import/novel', {method:'POST', body: formData});
        var d = await r.json();
        if (d.ok) {
          var html = '<div class="card-surface-md">';
          html += '<div style="color:var(--success);font-weight:600;margin-bottom:8px">✅ 导入成功！</div>';
          if (d.chapters && d.chapters.length) {
            html += '<div class="mb-1.5">📊 分割章节: <strong>' + d.chapters.length + '</strong> 章</div>';
          }
          if (d.characters && d.characters.length) {
            html += '<div class="mb-1.5">👥 提取角色: <strong>' + d.characters.length + '</strong> 个</div>';
          }
          if (d.outline) {
            html += '<div class="mb-1.5">📋 大纲摘要: 已生成</div>';
          }
          html += '<div style="margin-top:8px;color:var(--muted)">请刷新页面查看导入的内容</div>';
          html += '</div>';
          document.getElementById('import-result').innerHTML = html;
          btn.textContent = '✅ 导入完成';
        } else {
          document.getElementById('import-result').innerHTML = '<div style="color:var(--danger);font-size:12px;padding:8px">❌ 导入失败: ' + (d.error || '未知错误') + '</div>';
          btn.disabled = false;
          btn.textContent = '📤 开始导入';
        }
      } catch(e) {
        document.getElementById('import-result').innerHTML = '<div style="color:var(--danger);font-size:12px;padding:8px">❌ 网络错误: ' + e.message + '</div>';
        btn.disabled = false;
        btn.textContent = '📤 开始导入';
      }
    });
  } else {
    document.getElementById('import-overlay').style.display = 'flex';
  }
}

// ── 2. 版本对比 ──
function openSnapshotDiffPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  var sel = document.getElementById('diff-chapter-select');
  if (sel) {
    sel.textContent = '';
    if (typeof chapters !== 'undefined' && chapters) {
      chapters.forEach(function(ch, i) {
        var opt = document.createElement('option');
        opt.value = i;
        opt.textContent = '第' + (i+1) + '章 ' + (ch.title || '');
        sel.appendChild(opt);
      });
    }
    if (typeof currentChapterIndex !== 'undefined' && currentChapterIndex >= 0) {
      sel.value = currentChapterIndex;
    }
  }
  document.getElementById('diff-result').style.display = 'none';
  document.getElementById('diff-empty').style.display = 'block';
  document.getElementById('snapshot-diff-overlay').style.display = 'flex';
  loadDiffSnapshots();
}

async function loadDiffSnapshots() {
  var sel = document.getElementById('diff-chapter-select');
  if (!sel) return;
  var idx = parseInt(sel.value) || 0;
  var r = await getSnapshots(idx);
  var sela = document.getElementById('diff-snapshot-a');
  var selb = document.getElementById('diff-snapshot-b');
  sela.innerHTML = '<option value="">--选择--</option>';
  selb.innerHTML = '<option value="">--选择--</option>';
  if (r.ok && r.snapshots) {
    r.snapshots.forEach(function(s) {
      var fname = typeof s === 'string' ? s : s.file;
      var time = typeof s === 'string' ? s : (s.time || '');
      var size = typeof s === 'string' ? '' : (s.size ? (s.size + 'B') : '');
      var label = time + (size ? ' (' + size + ')' : '');
      var o1 = document.createElement('option');
      o1.value = fname; o1.textContent = label;
      sela.appendChild(o1);
      var o2 = document.createElement('option');
      o2.value = fname; o2.textContent = label;
      selb.appendChild(o2);
    });
    if (r.snapshots.length >= 2) {
      sela.value = typeof r.snapshots[r.snapshots.length-1] === 'string' 
        ? r.snapshots[r.snapshots.length-1] 
        : r.snapshots[r.snapshots.length-1].file;
      selb.value = typeof r.snapshots[r.snapshots.length-2] === 'string'
        ? r.snapshots[r.snapshots.length-2]
        : r.snapshots[r.snapshots.length-2].file;
    }
  }
}

async function runSnapshotDiff() {
  var idx = parseInt(document.getElementById('diff-chapter-select').value) || 0;
  var sa = document.getElementById('diff-snapshot-a').value;
  var sb = document.getElementById('diff-snapshot-b').value;
  if (!sa || !sb) { if (typeof showToast==='function') showToast('请选择两个快照'); return; }
  var r = await diffSnapshots(idx, sa, sb);
  var resultDiv = document.getElementById('diff-result');
  var emptyDiv = document.getElementById('diff-empty');
  if (r.ok && r.diff) {
    emptyDiv.style.display = 'none';
    resultDiv.style.display = 'block';
    var html = '<div style="margin-bottom:8px;padding:6px 10px;background:var(--surface);border-radius:4px;font-size:12px;color:var(--muted)">'
      + '新增 ' + (r.stats.added_lines||0) + ' 行 · 删除 ' + (r.stats.removed_lines||0) + ' 行 · ' + (r.stats.changed_blocks||0) + ' 处变更</div>';
    r.diff.forEach(function(line) {
      var bg = '', prefix = '';
      if (line.type === 'added') { bg = 'background:rgba(40,167,69,0.12);color:#28a745'; prefix='+'; }
      else if (line.type === 'removed') { bg = 'background:rgba(220,53,69,0.12);color:#dc3545'; prefix='-'; }
      html += '<div style="padding:1px 8px;' + bg + ';white-space:pre-wrap;word-break:break-all">' + prefix + ' ' + (line.text||'').replace(/</g,'&lt;') + '</div>';
    });
    resultDiv.innerHTML = html;
  } else {
    resultDiv.style.display = 'none';
    emptyDiv.style.display = 'block';
    emptyDiv.textContent = '对比失败: ' + (r.error || '未知错误');
  }
}

// ── 3. 角色对话模拟 ──
var _chatHistory = [];

function openCharacterChatPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  document.getElementById('character-chat-overlay').style.display = 'flex';
  loadChatCharacters();
}

async function loadChatCharacters() {
  var sel = document.getElementById('chat-character-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">--选择角色--</option>';

  // 优先使用已加载的 characters 全局变量（从后端 /api/project/settings 加载）
  var charList = [];
  if (typeof characters !== 'undefined' && characters && characters.length > 0) {
    charList = characters;
  } else {
    // 回退：从 localStorage 读取
    var r = await getChatCharacters();
    if (r.ok && r.characters) {
      charList = r.characters.map(function(name) {
        return { name: name };
      });
    }
  }

  if (charList.length > 0) {
    charList.forEach(function(c) {
      var opt = document.createElement('option');
      var name = (typeof c === 'string') ? c : (c.name || c.character_name || '');
      var role = (typeof c === 'object') ? (c.role || c.realm || c.description || '') : '';
      opt.value = name;
      opt.textContent = name + (role ? ' (' + role.substring(0, 20) + ')' : '');
      sel.appendChild(opt);
    });
  } else {
    sel.innerHTML = '<option value="">暂无角色设定，请先在设定中添加角色</option>';
  }
}

function clearChatHistory() {
  _chatHistory = [];
  var msgDiv = document.getElementById('chat-messages');
  if (msgDiv) {
    msgDiv.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:13px;padding:20px">对话已清空，开始新的对话</div>';
  }
}

async function sendChatMessage() {
  var sel = document.getElementById('chat-character-select');
  var input = document.getElementById('chat-input');
  if (!sel || !sel.value) { if (typeof showToast==='function') showToast('请先选择角色'); return; }
  var msg = input.value.trim();
  if (!msg) return;
  var character = sel.value;
  var msgDiv = document.getElementById('chat-messages');
  // 清除空提示
  if (msgDiv.querySelector('div[style*="text-align:center"]')) msgDiv.textContent = '';
  // 显示用户消息
  msgDiv.innerHTML += '<div style="align-self:flex-end;max-width:80%;padding:8px 12px;background:var(--accent);color:#fff;border-radius:12px 12px 4px 12px;font-size:13px">' + msg.replace(/</g,'&lt;') + '</div>';
  input.value = '';
  msgDiv.scrollTop = msgDiv.scrollHeight;
  // 显示等待
  var waitDiv = document.createElement('div');
  waitDiv.style.cssText = 'align-self:flex-start;max-width:80%;padding:8px 12px;background:var(--surface);border:1px solid var(--border);border-radius:12px 12px 12px 4px;font-size:13px;color:var(--muted)';
  waitDiv.textContent = character + ' 正在思考...';
  msgDiv.appendChild(waitDiv);
  msgDiv.scrollTop = msgDiv.scrollHeight;
  // 调用API
  var r = await chatTalk(character, msg, _chatHistory);
  msgDiv.removeChild(waitDiv);
  if (r.ok && r.reply) {
    msgDiv.innerHTML += '<div style="align-self:flex-start;max-width:80%;padding:8px 12px;background:var(--surface);border:1px solid var(--border);border-radius:12px 12px 12px 4px;font-size:13px"><strong class="text-accent">' + character + '：</strong> ' + r.reply.replace(/</g,'&lt;').replace(/\n/g,'<br>') + '</div>';
    _chatHistory.push({role: 'user', content: msg});
    _chatHistory.push({role: 'assistant', content: r.reply});
  } else {
    msgDiv.innerHTML += '<div style="align-self:flex-start;max-width:80%;padding:8px 12px;background:rgba(220,53,69,0.1);border:1px solid #dc3545;border-radius:12px 12px 12px 4px;font-size:13px;color:#dc3545">对话失败: ' + (r.error||'未知错误') + '</div>';
  }
  msgDiv.scrollTop = msgDiv.scrollHeight;
}

// ── 5. 云同步 ──
function openSyncPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  document.getElementById('sync-overlay').style.display = 'flex';
  loadSyncConfig();
}

async function loadSyncConfig() {
  var r = await getSyncConfig();
  if (r.ok && r.config) {
    document.getElementById('sync-url').value = r.config.webdav_url || '';
    document.getElementById('sync-username').value = r.config.username || '';
    document.getElementById('sync-password').value = r.config.password || '';
    document.getElementById('sync-remote-path').value = r.config.remote_path || '/';
  }
}

function _getSyncConfig() {
  return {
    webdav_url: document.getElementById('sync-url').value.trim(),
    username: document.getElementById('sync-username').value.trim(),
    password: document.getElementById('sync-password').value,
    remote_path: document.getElementById('sync-remote-path').value.trim() || '/',
    auto_sync: false
  };
}

async function saveSyncSettings() {
  var cfg = _getSyncConfig();
  if (!cfg.webdav_url) { if (typeof showToast==='function') showToast('请填写WebDAV地址'); return; }
  var r = await saveSyncConfig(cfg);
  var st = document.getElementById('sync-status');
  if (st) { st.textContent = r.ok ? '✅ 配置已保存' : '❌ 保存失败: ' + (r.error||''); st.style.color = r.ok ? 'var(--success)' : 'var(--danger)'; }
}

async function testSyncConnection() {
  var cfg = _getSyncConfig();
  if (!cfg.webdav_url) { if (typeof showToast==='function') showToast('请填写WebDAV地址'); return; }
  var st = document.getElementById('sync-status');
  if (st) { st.textContent = '⏳ 正在测试连接...'; st.style.color = 'var(--muted)'; }
  var r = await testSync(cfg);
  if (st) { st.textContent = (r.ok?'✅ ':'❌ ') + (r.message||''); st.style.color = r.ok ? 'var(--success)' : 'var(--danger)'; }
}

async function doSyncPush() {
  var cfg = _getSyncConfig();
  if (!cfg.webdav_url) { if (typeof showToast==='function') showToast('请填写WebDAV地址'); return; }
  var st = document.getElementById('sync-status');
  if (st) { st.textContent = '⏳ 正在上传...'; st.style.color = 'var(--muted)'; }
  var r = await syncPush(cfg);
  if (st) { st.textContent = (r.ok?'✅ ':'❌ ') + (r.message||''); st.style.color = r.ok ? 'var(--success)' : 'var(--danger)'; }
}

async function doSyncPull() {
  var cfg = _getSyncConfig();
  if (!cfg.webdav_url) { if (typeof showToast==='function') showToast('请填写WebDAV地址'); return; }
  if (!confirm('拉取将覆盖当前项目文件，确定继续？')) return;
  var st = document.getElementById('sync-status');
  if (st) { st.textContent = '⏳ 正在下载...'; st.style.color = 'var(--muted)'; }
  var r = await syncPull(cfg);
  if (st) { st.textContent = (r.ok?'✅ ':'❌ ') + (r.message||''); st.style.color = r.ok ? 'var(--success)' : 'var(--danger)'; }
  if (r.ok) { if (typeof showToast==='function') showToast('同步成功，正在重新加载...'); setTimeout(function(){location.reload();}, 1500); }
}

// ── 6. 大纲模板 ──
function openTemplatePanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  document.getElementById('template-overlay').style.display = 'flex';
  loadOutlineTemplates();
}

async function loadOutlineTemplates() {
  var list = document.getElementById('template-list');
  if (!list) return;
  list.innerHTML = '<div class="empty-state">加载中...</div>';
  var r = await getOutlineTemplates();
  if (!r.ok || !r.templates) { list.innerHTML = '<div style="text-align:center;color:var(--danger);padding:20px">加载失败</div>'; return; }
  list.textContent = '';
  r.templates.forEach(function(tpl) {
    var card = document.createElement('div');
    card.style.cssText = 'border:1px solid var(--border);border-radius:var(--radius-sm);padding:16px;cursor:pointer;transition:all .2s';
    card.onmouseenter = function() { card.style.borderColor = 'var(--accent)'; };
    card.onmouseleave = function() { card.style.borderColor = 'var(--border)'; };
    var chaptersHtml = '';
    tpl.chapters.forEach(function(ch, i) {
      chaptersHtml += '<div style="font-size:11px;color:var(--muted);padding:2px 0"><strong>第'+(i+1)+'章</strong> ' + ch.title + ': ' + ch.summary + '</div>';
    });
    card.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
      + '<div><span style="font-weight:600;font-size:14px;color:var(--ink)">' + tpl.name + '</span>'
      + '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border:1px solid var(--border);border-radius:10px;color:var(--muted)">' + tpl.genre + ' · ' + tpl.chapter_count + '章</span></div>'
      + '<button class="btn-sm accept" onclick="event.stopPropagation();applyTemplate(\'' + tpl.id + '\')">应用</button></div>'
      + '<div style="font-size:12px;color:var(--muted);margin-bottom:8px">' + tpl.description + '</div>'
      + '<details><summary style="font-size:11px;color:var(--accent);cursor:pointer">查看章节大纲</summary><div style="margin-top:6px;max-height:200px;overflow:auto;padding:8px;background:var(--surface);border-radius:4px">' + chaptersHtml + '</div></details>';
    list.appendChild(card);
  });
}

async function applyTemplate(id) {
  if (!confirm('应用模板将覆盖现有大纲，确定继续？')) return;
  if (typeof showToast==='function') showToast('正在应用模板...');
  var r = await applyOutlineTemplate(id);
  if (r.ok) {
    if (typeof showToast==='function') showToast('✅ 模板已应用');
    closeOverlay('template-overlay');
    if (typeof loadProjectOutline === 'function') loadProjectOutline();
  } else {
    if (typeof showToast==='function') showToast('应用失败: ' + (r.error||''));
  }
}

// ── 7. 批量检查 ──
var _batchCheckTypes = [
  {id:'all-in-one',name:'19维合并检查(推荐)'},
  {id:'outline-quality',name:'大纲质量'},
  {id:'settings-quality',name:'设定质量'},
  {id:'characters-quality',name:'人物质量'},
  {id:'twist',name:'转折'},{id:'duplicate',name:'重复'},
  {id:'style',name:'风格'},{id:'timeline',name:'时间线'},{id:'conflict',name:'冲突'},
  {id:'quality',name:'质量'},{id:'memory',name:'记忆'},
  {id:'ai-flavor',name:'AI味'}
];

function openBatchCheckPanel(preSelect) {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  var overlay = document.getElementById('batch-check-overlay');
  if (overlay) overlay.style.display = 'flex';
  var ctDiv = document.getElementById('batch-check-types');
  if (!ctDiv) return;
  ctDiv.textContent = '';
  var types = _batchCheckTypes || [
    {id:'outline-quality',name:'大纲质量'},
    {id:'settings-quality',name:'设定质量'},
    {id:'twist',name:'转折'},{id:'duplicate',name:'重复'},
    {id:'style',name:'风格'},{id:'timeline',name:'时间线'},{id:'conflict',name:'冲突'},
    {id:'quality',name:'质量'},{id:'ai-flavor',name:'AI味'}
  ];
  types.forEach(function(t) {
    var lbl = document.createElement('label');
    lbl.style.cssText = 'font-size:12px;cursor:pointer;display:flex;align-items:center;gap:3px;padding:4px 10px;border:1px solid var(--border);border-radius:14px';
    // 如果指定了 preSelect，则只选中该项，其他不选中
    var checked = preSelect ? (t.id === preSelect ? 'checked' : '') : 'checked';
    lbl.innerHTML = '<input type="checkbox" value="' + t.id + '" ' + checked + ' class="v-middle-gap-xs"> ' + t.name;
    ctDiv.appendChild(lbl);
  });
  var resultDiv = document.getElementById('batch-check-result');
  if (resultDiv) resultDiv.textContent = '';
  // 如果指定了 preSelect，自动开始检查
  if (preSelect) {
    setTimeout(function() { runBatchCheck(); }, 100);
  }
}

// 快捷入口：从工具箱下拉菜单直接检查大纲/设定
function quickQualityCheck(type) {
  openBatchCheckPanel(type);
}

async function runBatchCheck() {
  var checks = [];
  document.querySelectorAll('#batch-check-types input:checked').forEach(function(el) { checks.push(el.value); });
  if (checks.length === 0) { if (typeof showToast==='function') showToast('请至少选择一项检查'); return; }
  var resultDiv = document.getElementById('batch-check-result');
  resultDiv.innerHTML = '<div class="empty-state">⏳ 正在批量检查，请稍候（可能需要数分钟）...</div>';

  // 分离全书级检查和逐章检查
  var bookChecks = checks.filter(function(c) { return c === 'outline-quality' || c === 'settings-quality' || c === 'characters-quality'; });
  var chapterChecks = checks.filter(function(c) { return c !== 'outline-quality' && c !== 'settings-quality' && c !== 'characters-quality'; });

  // 渲染全书级检查结果的辅助函数
  function renderQualityCard(data, label) {
    if (!data) return '';
    if (!data.ok && data.error) {
      return '<div class="card-surface-sm">'
        + '<div style="font-size:13px;font-weight:600;color:var(--warn)">' + label + ' - 检查失败</div>'
        + '<div style="font-size:12px;color:var(--muted);margin-top:4px">' + (data.error||'') + '</div></div>';
    }
    // 降级：AI 返回了纯文本而非 JSON
    if (data.result && !data.dimensions) {
      return '<div class="card-surface-sm">'
        + '<div style="font-size:13px;font-weight:600;color:var(--accent)">' + label + '</div>'
        + '<div style="font-size:12px;color:var(--text);margin-top:6px;white-space:pre-wrap;line-height:1.6">' + (data.result||'').replace(/</g,'&lt;') + '</div></div>';
    }
    var html = '<div class="card-surface-sm">';
    // 总分头部
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
      + '<div style="font-size:14px;font-weight:600;color:var(--accent)">' + label + '</div>';
    if (data.overall_score !== undefined) {
      var scoreColor = data.overall_score >= 8 ? 'var(--success)' : (data.overall_score >= 6 ? 'var(--warn)' : 'var(--danger)');
      html += '<div style="font-size:18px;font-weight:700;color:' + scoreColor + '">' + data.overall_score + '<span style="font-size:11px;font-weight:400;color:var(--muted)">/10</span></div>';
    }
    html += '</div>';
    // 总结
    if (data.summary) {
      html += '<div style="font-size:12px;color:var(--text);line-height:1.6;margin-bottom:10px;padding:8px;background:var(--bg);border-radius:4px">' + (data.summary||'').replace(/</g,'&lt;') + '</div>';
    }
    // 维度卡片
    if (data.dimensions && data.dimensions.length) {
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-bottom:10px">';
      data.dimensions.forEach(function(dim) {
        var dimColor = dim.status === '✓' ? 'var(--success)' : (dim.status === '⚠' ? 'var(--warn)' : 'var(--danger)');
        var dimBg = dim.status === '✓' ? 'rgba(16,185,129,0.06)' : (dim.status === '⚠' ? 'rgba(245,158,11,0.06)' : 'rgba(239,68,68,0.06)');
        html += '<div style="padding:8px 10px;background:' + dimBg + ';border:1px solid var(--border-soft);border-radius:4px;cursor:default" title="' + (dim.detail||'').replace(/"/g,'&quot;').replace(/</g,'&lt;') + '">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">'
          + '<span style="font-size:11px;color:var(--text)">' + dim.status + ' ' + (dim.name||'') + '</span>'
          + (dim.score !== undefined && dim.score > 0 ? '<span style="font-size:12px;font-weight:700;color:' + dimColor + '">' + dim.score + '</span>' : '<span class="text-xs text-muted">N/A</span>')
          + '</div>'
          + '<div style="font-size:10px;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">' + (dim.detail||'').replace(/</g,'&lt;') + '</div>'
          + '</div>';
      });
      html += '</div>';
    }
    // 建议
    if (data.suggestions && data.suggestions.length) {
      html += '<div style="font-size:12px;color:var(--text);line-height:1.6"><span style="font-weight:600;color:var(--accent)">改进建议：</span>';
      data.suggestions.forEach(function(s, i) {
        html += '<div style="margin-left:12px;margin-top:2px">' + (i+1) + '. ' + s.replace(/</g,'&lt;') + '</div>';
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  var allHtml = '';

  // 执行全书级检查
  var qualityResults = {};
  for (var qi = 0; qi < bookChecks.length; qi++) {
    var qType = bookChecks[qi];
    try {
      var qRes = await api('/api/validate/' + qType, { method: 'POST', body: '{}' });
      qualityResults[qType] = qRes;
    } catch(e) {
      qualityResults[qType] = { ok: false, error: e.message || '请求失败' };
    }
  }

  // 渲染全书级检查结果
  if (bookChecks.indexOf('outline-quality') >= 0) {
    allHtml += renderQualityCard(qualityResults['outline-quality'], '大纲质量检查');
  }
  if (bookChecks.indexOf('settings-quality') >= 0) {
    allHtml += renderQualityCard(qualityResults['settings-quality'], '设定质量检查');
  }
  if (bookChecks.indexOf('characters-quality') >= 0) {
    allHtml += renderQualityCard(qualityResults['characters-quality'], '人物质量检查');
  }

  // 执行逐章检查
  if (chapterChecks.length > 0) {
    var r = await batchValidate(chapterChecks, []);
    // 加载结果到检查面板
    if (typeof CheckPanel !== 'undefined' && r && r.ok) {
      CheckPanel.loadResults(r);
    }
    if (r.ok && r.results) {
      var summary = r.summary || {};
      allHtml += '<div style="padding:10px 12px;background:var(--surface);border-radius:4px;margin-bottom:12px;font-size:12px">'
        + '逐章检查：共检查 ' + (summary.total||0) + ' 章 · '
        + (summary.issues_found||0) + ' 个问题</div>';
      r.results.forEach(function(ch) {
        var issues = [];
        if (ch.checks) {
          Object.keys(ch.checks).forEach(function(ct) {
            var c = ch.checks[ct];
            // 处理 all-in-one（19维合并检查）
            if (ct === 'all-in-one' && c && c.ok) {
              // 渲染10维问题检查
              if (c.checks) {
                Object.keys(c.checks).forEach(function(checkType) {
                  var check = c.checks[checkType];
                  if (!check.ok) {
                    issues.push({type: '19维-' + checkType, message: check.content || '存在问题'});
                  }
                });
              }
              // 渲染6维责编评分
              if (c.editorial && c.editorial.dimensions) {
                var editorialScores = [];
                c.editorial.dimensions.forEach(function(dim) {
                  editorialScores.push(dim.name + ':' + dim.score + '分');
                });
                issues.push({type: '责编评分', message: editorialScores.join(' | ')});
              }
              // 渲染3维市场评分
              if (c.market && c.market.dimensions) {
                var marketScores = [];
                c.market.dimensions.forEach(function(dim) {
                  marketScores.push(dim.name + ':' + dim.score + '分');
                });
                issues.push({type: '市场评分', message: marketScores.join(' | ')});
              }
              return; // 跳过后续处理
            }
            if (c && (!c.ok || c.error)) {
              if (ct === 'ai-flavor' && c.issues) {
                var scoreText = c.score !== undefined ? ' [AI味:' + c.score + '/100 ' + (c.level||'') + ']' : '';
                c.issues.forEach(function(iss) {
                  issues.push({type: 'AI味', message: iss.message || '', locations: iss.locations, scope: iss.scope});
                });
                if (issues.length === 0 && c.result) {
                  issues.push({type: 'AI味', message: c.result + scoreText});
                }
              } else {
                issues.push({type: ct, message: c.result || c.error || '存在问题'});
              }
            }
          });
        }
        var hasIssues = issues.length > 0;
        allHtml += '<div style="margin-bottom:8px;border:1px solid var(--border-soft);border-radius:4px;overflow:hidden">'
          + '<div style="padding:8px 12px;background:var(--surface);font-size:13px;font-weight:600;cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'">'
          + (hasIssues?'⚠️':'✅') + ' 第' + (ch.chapter_index+1) + '章 ' + (ch.title||'')
          + (hasIssues?' <span style="float:right;color:var(--warn);font-size:11px">'+issues.length+'个问题</span>':'<span style="float:right;color:var(--success);font-size:11px">通过</span>')
          + '</div>';
        if (hasIssues) {
          allHtml += '<div style="padding:8px 12px;display:none">';
          issues.forEach(function(iss) {
            allHtml += '<div style="padding:4px 0;font-size:12px;border-bottom:1px solid var(--border-soft)">'
              + '<span style="color:var(--warn);font-weight:600">['+iss.type+']</span> '
              + (iss.message||'').replace(/</g,'&lt;');
            if (iss.locations && iss.locations.length > 0) {
              allHtml += '<div style="margin-top:3px;display:flex;flex-wrap:wrap;gap:3px">';
              iss.locations.forEach(function(loc) {
                var locText = loc.line ? ('第' + loc.line + '行') : ('位置' + loc.offset);
                allHtml += '<button onclick="window._auditJumpTo(' + (loc.line || 0) + ',' + (loc.offset || 0) + ')" '
                  + 'style="font-size:9px;padding:1px 5px;border:1px solid var(--border-soft);border-radius:999px;background:var(--bg);color:var(--muted);cursor:pointer"'
                  + '>' + locText + '</button>';
              });
              allHtml += '</div>';
            } else if (iss.scope === 'global') {
              allHtml += '<div style="margin-top:2px;font-size:9px;color:var(--muted-deep)">📊 全文统计</div>';
            }
            allHtml += '</div>';
          });
          allHtml += '</div>';
        }
        allHtml += '</div>';
      });
    } else if (r.error) {
      allHtml += '<div style="text-align:center;color:var(--danger);padding:10px">逐章检查失败: ' + (r.error||'') + '</div>';
    }
  }

  if (allHtml) {
    resultDiv.innerHTML = allHtml;
  } else {
    resultDiv.innerHTML = '<div class="empty-state">未执行任何检查</div>';
  }
}

// ── 8. 写作统计 ──
function openStatsPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  document.getElementById('stats-overlay').style.display = 'flex';
  loadStats();
}



// === 一键启用指南预设 ===
function applyGuidePreset(scene) {
  try {
    var enableIds = [];
    var disableIds = [];

    if (scene === 'short') {
      enableIds = ['tomato-short-story-base','anti-ai-wuhang','hook-opener-library','short-fiction-flow'];
      disableIds = ['pacing-control','golden-three-chapters','strand-weave-rhythm','chapter-positioning','style-upgrade','genre-templates-37','deslop-7gate','anti-ai-base'];
    } else if (scene === 'long') {
      enableIds = ['pacing-control','golden-three-chapters','strand-weave-rhythm','chapter-positioning','hook-opener-library'];
      disableIds = ['tomato-short-story-base','short-fiction-flow',
        'short-reborn-revenge','short-ceo-marriage-first','short-mystery-twist',
        'short-infinite-flow','short-time-travel-history','short-cyberpunk',
        'short-urban-ghost-stories','short-healing-fantasy','short-rule-horror',
        'short-wasteland-apocalypse','short-xuanhuan-brainhole',
        'short-apocalypse-cultivation','short-urban-martial','short-folklore-jianghu','short-eerie-wuxia'];
    } else if (scene === 'audit') {
      enableIds = ['ai-editor-fanqie','platform-review','reader-retention'];
      disableIds = [];
    } else if (scene === 'polish') {
      enableIds = ['polish-prose','anti-ai-wuhang','deslop-7gate'];
      disableIds = [];
    }

    // Disable
    disableIds.forEach(function(id) {
      if (enableIds.indexOf(id) === -1) {
        var s = SkillPack.getSkill(id);
        if (s && s.enabled) SkillPack.toggle(id);
      }
    });
    // Enable
    enableIds.forEach(function(id) {
      var s = SkillPack.getSkill(id);
      if (s && !s.enabled) SkillPack.toggle(id);
    });

    if (typeof renderSkillsList === 'function') renderSkillsList(_skillTab);
    if (typeof renderSkillCheckList === 'function') renderSkillCheckList();
    var names = {'short':'番茄短篇','long':'长篇连载','audit':'审稿诊断','polish':'润色修改'};
    if (typeof showToast === 'function') showToast('已一键切换为「' + (names[scene]||scene) + '」模式');
  } catch(e) {
    if (typeof showToast === 'function') showToast('切换失败: ' + e.message);
    else alert('切换失败: ' + e.message);
  }
}

// === 技能包使用指南 ===
function _renderSkillGuide() {
  var box = 'padding:12px;margin-bottom:10px;border-radius:8px;border:1px solid var(--border);background:var(--surface)';
  var h3 = 'font-size:14px;font-weight:600;margin:0 0 8px 0;color:var(--accent)';
  var p = 'font-size:12px;color:var(--text);line-height:1.8;margin:4px 0';
  var tag = 'display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;margin:2px 4px 2px 0';
  var green = 'background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3)';
  var red = 'background:rgba(239,68,68,0.12);color:#ef4444;border:1px solid rgba(239,68,68,0.25)';
  var yellow = 'background:rgba(245,158,11,0.12);color:#f59e0b;border:1px solid rgba(245,158,11,0.25)';

  return ''
    + '<div style="font-size:13px;color:var(--muted);margin-bottom:12px">根据写作场景选择技能包，避免全部启用导致prompt过长</div>'

    // 写短篇
    + '<div style="' + box + '">'
    + '  <h3 style="' + h3 + '">📝 写番茄短篇（8k-2.5w字）<button onclick="applyGuidePreset(\'short\')" class="btn-accent-float-xs">⚡ 一键启用</button></h3>'
    + '  <div style="' + p + '"><b class="text-emerald">必须启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + green + '">番茄短故事通用约束</span>'
    + '    <span style="' + tag + green + '">对应题材规则（选1个）</span>'
    + '  </div>'
    + '  <div style="' + p + '"><b class="text-emerald">建议启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + green + '">去除AI味 - 武行完整版</span>'
    + '    <span style="' + tag + green + '">悬念钩子13式 + 章首引子7式</span>'
    + '    <span style="' + tag + green + '">短篇写作专用流程</span>'
    + '  </div>'
    + '  <div style="' + p + '"><b style="color:#ef4444">必须禁用（长篇专用）：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + red + '">爽点节奏控制</span>'
    + '    <span style="' + tag + red + '">黄金三章优化</span>'
    + '    <span style="' + tag + red + '">Strand Weave 三线节奏</span>'
    + '    <span style="' + tag + red + '">章节定位六型</span>'
    + '    <span style="' + tag + red + '">升级流风格规则</span>'
    + '    <span style="' + tag + red + '">37题材写作模板库</span>'
    + '  </div>'
    + '</div>'

    // 写长篇
    + '<div style="' + box + '">'
    + '  <h3 style="' + h3 + '">📚 写长篇连载（10w+字）<button onclick="applyGuidePreset(\'long\')" class="btn-accent-float-xs">⚡ 一键启用</button></h3>'
    + '  <div style="' + p + '"><b class="text-emerald">建议启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + green + '">去除AI味 - Humanizer中文版</span>'
    + '    <span style="' + tag + green + '">爽点节奏控制</span>'
    + '    <span style="' + tag + green + '">黄金三章优化</span>'
    + '    <span style="' + tag + green + '">Strand Weave 三线节奏</span>'
    + '    <span style="' + tag + green + '">章节定位六型 + 字数预算</span>'
    + '    <span style="' + tag + green + '">悬念钩子13式 + 章首引子7式</span>'
    + '    <span style="' + tag + green + '">对应风格规则（升级流/言情/种田）</span>'
    + '  </div>'
    + '  <div style="' + p + '"><b style="color:#f59e0b">可选启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + yellow + '">7Gate去AI味系统</span>'
    + '    <span style="' + tag + yellow + '">文风指纹仿写系统</span>'
    + '    <span style="' + tag + yellow + '">读者留存分析</span>'
    + '  </div>'
    + '  <div style="' + p + '"><b style="color:#ef4444">建议禁用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + red + '">番茄短故事通用约束</span>'
    + '    <span style="' + tag + red + '">短篇写作专用流程</span>'
    + '    <span style="' + tag + red + '">所有"短篇规则 · "题材包</span>'
    + '  </div>'
    + '</div>'

    // 审稿诊断
    + '<div style="' + box + '">'
    + '  <h3 style="' + h3 + '">🔍 审稿诊断（写完用）<button onclick="applyGuidePreset(\'audit\')" class="btn-accent-float-xs">⚡ 一键启用</button></h3>'
    + '  <div style="' + p + '"><b class="text-emerald">启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + green + '">AI责编 · 番茄过签版</span>'
    + '    <span style="' + tag + green + '">平台审稿诊断</span>'
    + '    <span style="' + tag + green + '">读者留存分析</span>'
    + '  </div>'
    + '  <div style="' + p + '"><span class="text-muted-sm">审稿时不需要启用写作规则类技能包，诊断工具独立工作</span></div>'
    + '</div>'

    // 润色
    + '<div style="' + box + '">'
    + '  <h3 style="' + h3 + '">✏️ 润色修改（写完用）<button onclick="applyGuidePreset(\'polish\')" class="btn-accent-float-xs">⚡ 一键启用</button></h3>'
    + '  <div style="' + p + '"><b class="text-emerald">启用：</b></div>'
    + '  <div class="my-1-ml3">'
    + '    <span style="' + tag + green + '">正文润色</span>'
    + '    <span style="' + tag + green + '">去除AI味 - 武行完整版</span>'
    + '    <span style="' + tag + green + '">7Gate去AI味系统</span>'
    + '  </div>'
    + '  <div style="' + p + '"><span class="text-muted-sm">润色时通过工具箱"正文润色"功能调用，不需要在写作时启用</span></div>'
    + '</div>'

    // 通用提示
    + '<div style="' + box + ';border-color:var(--accent);background:rgba(74,158,255,0.05)">'
    + '  <h3 style="' + h3 + '">💡 通用原则</h3>'
    + '  <div style="' + p + '">1. <b>不要全部启用</b> — 技能包内容会注入AI prompt，太多会导致注意力分散、规则冲突</div>'
    + '  <div style="' + p + '">2. <b>写作时启用3-6个</b> — 通用约束 + 题材规则 + 去AI味 + 1-2个技法</div>'
    + '  <div style="' + p + '">3. <b>审稿/润色时切换</b> — 写完后再启用诊断和润色类技能包</div>'
    + '  <div style="' + p + '">4. <b>同类型二选一</b> — 如Humanizer和武行版功能重叠，选一个即可</div>'
    + '</div>';
}

// ===== 技能包系统 =====
async function openSkillPackPanel() {
  document.getElementById('toolbox-dropdown').style.display = 'none';
  // 用和统计面板类似的overlay方式
  if (!document.getElementById('skills-overlay')) {
    // 动态创建面板
    var overlay = document.createElement('div');
    overlay.id = 'skills-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1100';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1101;width:92%;max-width:680px;height:85vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">🧩</span><span class="title-accent-md-xl">技能包管理</span><span style="font-size:11px;color:var(--muted);background:var(--bg);padding:2px 8px;border-radius:10px" id="skills-count">0</span></div>'
      + '    <div class="flex-row-xs">'
      + '      <button onclick="showSkillEditor()" style="padding:4px 12px;font-size:12px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer">+ 新建</button>'
      + '      <button onclick="openSkillImportDialog()" style="padding:4px 12px;font-size:12px;background:var(--surface);border:1px solid var(--accent);border-radius:4px;cursor:pointer;color:var(--accent)">📥 导入技能包</button>'
      + '      <button onclick="document.getElementById(\'skills-overlay\').style.display=\'none\'" class="btn-ghost-icon-xl-alt">✕</button>'
      + '    </div>'
      + '  </div>'
      + '  <div style="display:flex;gap:2px;padding:8px 12px 0;border-bottom:1px solid var(--border);background:var(--surface)">'
      + '    <button class="skill-tab active" data-type="all" onclick="switchSkillTab(\'all\')">全部</button>'
      + '    <button class="skill-tab" data-type="rules" onclick="switchSkillTab(\'rules\')">规则</button>'
      + '    <button class="skill-tab" data-type="skill" onclick="switchSkillTab(\'skill\')">技能</button>'
      + '    <button class="skill-tab" data-type="workflow" onclick="switchSkillTab(\'workflow\')">工作流</button>'
      + '    <button class="skill-tab" data-type="prompt" onclick="switchSkillTab(\'prompt\')">提示词</button>'
      + '    <button class="skill-tab" data-type="guide" onclick="switchSkillTab(\'guide\')" style="margin-left:auto">📖 使用指南</button>'
      + '  </div>'
      + '  <div id="skills-list" style="flex:1;overflow-y:auto;padding:12px"></div>'
      + '</div>';
    document.body.appendChild(overlay);
  } else {
    document.getElementById('skills-overlay').style.display = 'flex';
  }
  // 先从后端加载导入的技能包，再渲染列表
  if (typeof SkillPack !== 'undefined' && SkillPack.loadImported) {
    await SkillPack.loadImported();
  }
  renderSkillsList('all');
}

function renderSkillsList(type) {
  var list = document.getElementById('skills-list');
  if (!list) return;
  if (type === 'guide') {
    document.getElementById('skills-count').textContent = '指南';
    list.innerHTML = _renderSkillGuide();
    return;
  }
  var skills = typeof SkillPack !== 'undefined' ? SkillPack.listAll() : [];
  if (type && type !== 'all') {
    skills = skills.filter(function(s) { return s.type === type; });
  }
  document.getElementById('skills-count').textContent = skills.length;
  
  if (skills.length === 0) {
    list.innerHTML = '<div class="empty-state-lg-alt">暂无技能包，点击右上角"新建"创建</div>';
    return;
  }
  
  var typeLabels = {rules: '规则', skill: '技能', workflow: '工作流', prompt: '提示词'};
  var typeColors = {rules: 'var(--accent)', skill: 'var(--warning, #f59e0b)', workflow: 'var(--success, #10b981)', prompt: 'var(--muted)'};
  
  list.innerHTML = skills.map(function(s) {
    var enabledBtn = s.enabled
      ? '<button onclick="toggleSkill(\'' + s.id + '\')" style="padding:3px 10px;font-size:11px;background:var(--accent);color:#fff;border:none;border-radius:3px;cursor:pointer">✓ 启用</button>'
      : '<button onclick="toggleSkill(\'' + s.id + '\')" style="padding:3px 10px;font-size:11px;background:var(--surface);border:1px solid var(--border);border-radius:3px;cursor:pointer;color:var(--muted)">已禁用</button>';
    // 操作按钮：内置=查看+导出；导入=查看+导出+删除(后端)；自定义=编辑+导出+删除(本地)
    var actions;
    if (s.builtin) {
      actions = enabledBtn + ' <button onclick="viewSkill(\'' + s.id + '\')" class="btn-surface-xs">查看</button> <button onclick="exportSkill(\'' + s.id + '\')" class="btn-surface-xs">导出</button>';
    } else if (s.imported) {
      actions = enabledBtn + ' <button onclick="viewSkill(\'' + s.id + '\')" class="btn-surface-xs">查看</button> <button onclick="exportSkill(\'' + s.id + '\')" class="btn-surface-xs">导出</button> <button onclick="deleteImportedSkill(\'' + s.id + '\')" style="padding:3px 10px;font-size:11px;background:var(--surface);border:1px solid var(--danger,#ef4444);border-radius:3px;cursor:pointer;color:var(--danger,#ef4444)">删除</button>';
    } else {
      actions = enabledBtn + ' <button onclick="editSkill(\'' + s.id + '\')" class="btn-surface-xs">编辑</button> <button onclick="exportSkill(\'' + s.id + '\')" class="btn-surface-xs">导出</button> <button onclick="deleteSkill(\'' + s.id + '\')" style="padding:3px 10px;font-size:11px;background:var(--surface);border:1px solid var(--danger,#ef4444);border-radius:3px;cursor:pointer;color:var(--danger,#ef4444)">删除</button>';
    }
    
    // 标记徽章：内置 / 导入
    var badge = '';
    if (s.builtin) {
      badge = '<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--accent-soft);color:var(--accent)">内置</span>';
    } else if (s.imported) {
      badge = '<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:rgba(74,124,89,0.15);color:var(--success,#4a7c59)">导入</span>';
    }
    
    return '<div style="padding:12px;margin-bottom:8px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm)">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">' +
        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">' +
          '<span class="text-base font-semibold">' + s.name + '</span>' +
          '<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:' + (typeColors[s.type]||'var(--muted)') + '20;color:' + (typeColors[s.type]||'var(--muted)') + '">' + (typeLabels[s.type]||s.type) + '</span>' +
          badge +
        '</div>' +
        '<div style="display:flex;gap:4px;flex-shrink:0">' + actions + '</div>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--muted);line-height:1.5">' + (s.description||'') + '</div>' +
      '<div style="font-size:10px;color:var(--muted);margin-top:4px;opacity:0.7">作者: ' + (s.author||'未知') + ' · 版本: ' + (s.version||'1.0.0') + '</div>' +
    '</div>';
  }).join('');
}

var _skillTab = 'all';
function switchSkillTab(type) {
  _skillTab = type;
  document.querySelectorAll('.skill-tab').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.type === type);
    btn.style.cssText = btn.classList.contains('active')
      ? 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid var(--accent);background:none;color:var(--accent);cursor:pointer'
      : 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid transparent;background:none;color:var(--muted);cursor:pointer';
  });
  renderSkillsList(type);
}

function toggleSkill(id) {
  SkillPack.toggle(id);
  renderSkillsList(_skillTab);
  renderSkillCheckList();
  showToast('技能包已' + (SkillPack.getSkill(id).enabled ? '启用' : '禁用'));
}

function viewSkill(id) {
  var s = SkillPack.getSkill(id);
  if (!s) return;
  showSkillEditor(s, true);
}

function editSkill(id) {
  var s = SkillPack.getSkill(id);
  if (!s) return;
  showSkillEditor(s, false);
}

function showSkillEditor(skill, readonly) {
  // 动态创建编辑器
  if (!document.getElementById('skill-editor-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'skill-editor-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1150';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1151;width:92%;max-width:580px;height:80vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <span class="title-accent-md-xl" id="skill-editor-title">新建技能包</span>'
      + '    <button onclick="document.getElementById(\'skill-editor-overlay\').style.display=\'none\'" class="btn-ghost-icon-xl-alt">✕</button>'
      + '  </div>'
      + '  <div style="flex:1;overflow-y:auto;padding:16px 18px;display:flex;flex-direction:column;gap:12px">'
      + '    <div><label class="label-muted-md">名称</label><input type="text" id="skill-edit-name" placeholder="技能包名称" class="input-surface-lg"></div>'
      + '    <div style="display:flex;gap:12px"><div class="flex-1"><label class="label-muted-md">类型</label><select id="skill-edit-type" class="input-surface-lg"><option value="rules">规则（自动生效）</option><option value="skill">技能（手动触发）</option><option value="workflow">工作流（多步骤）</option><option value="prompt">提示词模板</option></select></div><div class="flex-1"><label class="label-muted-md">生效范围</label><select id="skill-edit-scope" class="input-surface-lg"><option value="generate">正文生成</option><option value="check">内容检查</option><option value="polish">润色修改</option><option value="chat">对话</option><option value="all">全部</option></select></div></div>'
      + '    <div><label class="label-muted-md">描述</label><input type="text" id="skill-edit-desc" placeholder="简要描述技能包的作用" class="input-surface-lg"></div>'
      + '    <div id="skill-trigger-row" class="hidden"><label class="label-muted-md">触发词（用|分隔多个关键词）</label><input type="text" id="skill-edit-trigger" placeholder="如：审稿|诊断|过签" class="input-surface-lg"></div>'
      + '    <div style="flex:1;display:flex;flex-direction:column"><label class="label-muted-md">内容（Prompt/规则文本）</label><textarea id="skill-edit-content" placeholder="输入技能包的完整内容..." style="flex:1;width:100%;min-height:200px;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;line-height:1.6;font-family:monospace;resize:none"></textarea></div>'
      + '    <div style="display:flex;gap:8px;justify-content:flex-end"><button onclick="document.getElementById(\'skill-editor-overlay\').style.display=\'none\'" style="padding:8px 16px;font-size:13px;background:var(--surface);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text)">取消</button><button onclick="saveSkillFromEditor()" style="padding:8px 16px;font-size:13px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer">保存</button></div>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(overlay);
  } else {
    document.getElementById('skill-editor-overlay').style.display = 'flex';
  }
  
  var isReadonly = readonly === true;
  var s = skill || {};
  document.getElementById('skill-editor-title').textContent = s.id ? (isReadonly ? '查看技能包' : '编辑技能包') : '新建技能包';
  document.getElementById('skill-edit-name').value = s.name || '';
  document.getElementById('skill-edit-type').value = s.type || 'rules';
  document.getElementById('skill-edit-scope').value = s.scope || 'generate';
  document.getElementById('skill-edit-desc').value = s.description || '';
  document.getElementById('skill-edit-trigger').value = s.trigger || '';
  document.getElementById('skill-edit-content').value = s.content || '';
  
  // 显示/隐藏触发词
  var typeVal = document.getElementById('skill-edit-type').value;
  document.getElementById('skill-trigger-row').style.display = (typeVal === 'skill') ? 'block' : 'none';
  
  // 保存当前编辑的ID
  window._editingSkillId = s.id || null;
  window._editingSkillReadonly = isReadonly;
  
  // 只读模式
  var inputs = document.querySelectorAll('#skill-editor-overlay input, #skill-editor-overlay select, #skill-editor-overlay textarea');
  inputs.forEach(function(el) { el.disabled = isReadonly; });
  document.querySelector('#skill-editor-overlay button[onclick="saveSkillFromEditor()"]').style.display = isReadonly ? 'none' : '';
}

function saveSkillFromEditor() {
  var name = document.getElementById('skill-edit-name').value.trim();
  var content = document.getElementById('skill-edit-content').value.trim();
  if (!name) { showToast('请输入技能包名称'); return; }
  if (!content) { showToast('请输入技能包内容'); return; }
  
  var data = {
    name: name,
    type: document.getElementById('skill-edit-type').value,
    scope: document.getElementById('skill-edit-scope').value,
    description: document.getElementById('skill-edit-desc').value.trim(),
    content: content
  };
  if (data.type === 'skill') {
    data.trigger = document.getElementById('skill-edit-trigger').value.trim();
  }
  
  if (window._editingSkillId) {
    SkillPack.update(window._editingSkillId, data);
  } else {
    SkillPack.add(data);
  }
  
  document.getElementById('skill-editor-overlay').style.display = 'none';
  renderSkillsList(_skillTab);
  renderSkillCheckList();
  showToast('技能包已保存');
}

function deleteSkill(id) {
  if (!confirm('确定删除此技能包？')) return;
  SkillPack.remove(id);
  renderSkillsList(_skillTab);
  renderSkillCheckList();
  showToast('已删除');
}

// 删除后端导入的技能包（调用 DELETE /api/skills/{id}）
async function deleteImportedSkill(id) {
  if (!confirm('确定删除此导入技能包？将从当前项目中移除。')) return;
  try {
    await SkillPack.removeImported(id);
    renderSkillsList(_skillTab);
    renderSkillCheckList();
    showToast('已删除导入技能包');
  } catch(err) {
    showToast('删除失败: ' + err.message);
  }
}

function exportSkill(id) {
  var json = SkillPack.exportSkill(id);
  if (!json) return;
  var blob = new Blob([json], {type: 'application/json'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'skill_' + id + '.json';
  a.click();
  URL.revokeObjectURL(url);
  showToast('已导出');
}

function importSkillFromFile(input) {
  if (!input.files || !input.files[0]) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    try {
      SkillPack.importSkill(e.target.result);
      renderSkillsList(_skillTab);
      renderSkillCheckList();
      showToast('技能包导入成功');
    } catch(err) {
      showToast('导入失败: ' + err.message);
    }
  };
  reader.readAsText(input.files[0]);
  input.value = '';
}

// === 技能包导入弹窗（支持拖拽 / 点击选择 / 粘贴 JSON）===
function openSkillImportDialog() {
  // 若弹窗已存在则移除重建（保证状态干净）
  var old = document.getElementById('skill-import-overlay');
  if (old) old.remove();

  var overlay = document.createElement('div');
  overlay.id = 'skill-import-overlay';
  overlay.className = 'overlay-backdrop';
  overlay.style.cssText = 'display:flex;z-index:1200';

  overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1201;width:92%;max-width:520px;max-height:85vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
    + '  <div class="row-between-lg">'
    + '    <div class="flex-center-sm"><span class="text-xl">📥</span><span style="font-size:15px;font-weight:600;color:var(--accent)">导入技能包</span></div>'
    + '    <button onclick="document.getElementById(\'skill-import-overlay\').remove()" class="btn-ghost-icon-xl-alt">✕</button>'
    + '  </div>'
    + '  <div style="flex:1;overflow-y:auto;padding:16px 18px;display:flex;flex-direction:column;gap:14px">'
    // 拖拽 / 点击选择区域
    + '    <div id="skill-drop-zone" style="border:2px dashed var(--border);border-radius:var(--radius-sm);padding:28px 16px;text-align:center;cursor:pointer;transition:all 0.2s;background:var(--surface)">'
    + '      <div style="font-size:28px;margin-bottom:6px;opacity:0.7">📁</div>'
    + '      <div class="text-md text-muted">拖拽 .json 文件到此处，或<span class="text-accent-underline">点击选择文件</span></div>'
    + '      <div style="font-size:10px;color:var(--muted);opacity:0.6;margin-top:4px">支持从小说蒸馏器导出的技能包</div>'
    + '      <input type="file" id="skill-import-file-input" accept=".json,application/json" class="hidden">'
    + '    </div>'
    // 选中文件提示
    + '    <div id="skill-import-file-info" style="display:none;padding:8px 12px;background:var(--accent-soft);border:1px solid var(--accent);border-radius:var(--radius-sm);font-size:12px;color:var(--accent);align-items:center;gap:6px">'
    + '      <span>📄</span><span id="skill-import-file-name" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>'
    + '      <span onclick="clearSkillImportFile()" style="cursor:pointer;opacity:0.7">✕</span>'
    + '    </div>'
    // 分隔线
    + '    <div style="display:flex;align-items:center;gap:10px;color:var(--muted);font-size:11px">'
    + '      <div style="flex:1;height:1px;background:var(--border)"></div><span>或粘贴 JSON 文本</span><div style="flex:1;height:1px;background:var(--border)"></div>'
    + '    </div>'
    // 粘贴区域
    + '    <textarea id="skill-import-paste" placeholder=\'在此粘贴技能包 JSON 文本...&#10;必需字段: id, name, type, description, content\' style="width:100%;min-height:120px;max-height:200px;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-size:12px;line-height:1.5;font-family:monospace;resize:vertical;outline:none" onfocus="this.style.borderColor=\'var(--accent)\'" onblur="this.style.borderColor=\'var(--border)\'"></textarea>'
    // 错误提示
    + '    <div id="skill-import-error" style="display:none;padding:8px 12px;background:rgba(184,70,62,0.12);border:1px solid var(--danger,#b8463e);border-radius:var(--radius-sm);font-size:12px;color:var(--danger,#b8463e)"></div>'
    // 格式说明
    + '    <div style="font-size:10px;color:var(--muted);line-height:1.6;opacity:0.8">'
    + '      <div style="font-weight:600;margin-bottom:2px">技能包格式要求：</div>'
    + '      <div>• 必需字段：<code class="text-accent">id, name, type, description, content</code></div>'
    + '      <div>• type 可选值：rules / skill / workflow / prompt</div>'
    + '      <div>• 导入后保存在当前项目的 skills/ 目录，可启用/禁用/查看/删除</div>'
    + '    </div>'
    + '  </div>'
    // 底部按钮
    + '  <div style="display:flex;gap:8px;justify-content:flex-end;padding:12px 18px;border-top:1px solid var(--border);background:var(--surface)">'
    + '    <button onclick="document.getElementById(\'skill-import-overlay\').remove()" style="padding:8px 16px;font-size:13px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);cursor:pointer;color:var(--text)">取消</button>'
    + '    <button id="skill-import-confirm-btn" onclick="confirmSkillImport()" style="padding:8px 18px;font-size:13px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius-sm);cursor:pointer">导入</button>'
    + '  </div>'
    + '</div>';
  document.body.appendChild(overlay);

  // === 绑定事件 ===
  var dropZone = document.getElementById('skill-drop-zone');
  var fileInput = document.getElementById('skill-import-file-input');
  var fileInfo = document.getElementById('skill-import-file-info');
  var fileName = document.getElementById('skill-import-file-name');
  var pasteArea = document.getElementById('skill-import-paste');
  var _selectedFile = null;

  // 保存选中文件到全局供 confirmSkillImport 使用
  window._skillImportSelectedFile = null;

  // 点击拖拽区域 → 触发文件选择
  dropZone.addEventListener('click', function() {
    fileInput.click();
  });

  // 文件选择
  fileInput.addEventListener('change', function() {
    if (fileInput.files && fileInput.files[0]) {
      _setSelectedFile(fileInput.files[0]);
    }
  });

  function _setSelectedFile(file) {
    window._skillImportSelectedFile = file;
    fileName.textContent = file.name + ' (' + _formatSize(file.size) + ')';
    fileInfo.style.display = 'flex';
    // 清空粘贴区
    pasteArea.value = '';
    _hideSkillImportError();
  }

  // 拖拽事件
  dropZone.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.style.borderColor = 'var(--accent)';
    dropZone.style.background = 'var(--accent-soft)';
  });
  dropZone.addEventListener('dragleave', function(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.style.borderColor = 'var(--border)';
    dropZone.style.background = 'var(--surface)';
  });
  dropZone.addEventListener('drop', function(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.style.borderColor = 'var(--border)';
    dropZone.style.background = 'var(--surface)';
    var files = e.dataTransfer.files;
    if (files && files.length > 0) {
      var file = files[0];
      // 校验文件类型
      var name = file.name.toLowerCase();
      if (!name.endsWith('.json') && file.type !== 'application/json') {
        _showSkillImportError('请选择 .json 文件');
        return;
      }
      _setSelectedFile(file);
    }
  });

  // 粘贴时清除文件选择
  pasteArea.addEventListener('input', function() {
    if (pasteArea.value.trim() && window._skillImportSelectedFile) {
      window._skillImportSelectedFile = null;
      fileInfo.style.display = 'none';
      fileInput.value = '';
    }
    _hideSkillImportError();
  });
}

// 格式化文件大小
function _formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

// 清除已选文件
function clearSkillImportFile() {
  window._skillImportSelectedFile = null;
  document.getElementById('skill-import-file-info').style.display = 'none';
  document.getElementById('skill-import-file-input').value = '';
}

// 显示/隐藏错误
function _showSkillImportError(msg) {
  var el = document.getElementById('skill-import-error');
  if (el) {
    el.textContent = msg;
    el.style.display = 'block';
  }
}
function _hideSkillImportError() {
  var el = document.getElementById('skill-import-error');
  if (el) el.style.display = 'none';
}

// 确认导入（点击"导入"按钮）
async function confirmSkillImport() {
  var file = window._skillImportSelectedFile;
  var pasteText = document.getElementById('skill-import-paste').value.trim();
  var btn = document.getElementById('skill-import-confirm-btn');

  _hideSkillImportError();

  // 校验：必须有文件或粘贴文本
  if (!file && !pasteText) {
    _showSkillImportError('请选择 .json 文件或粘贴 JSON 文本');
    return;
  }

  // 禁用按钮，显示加载状态
  btn.disabled = true;
  btn.textContent = '导入中...';

  try {
    if (file) {
      // 从文件导入
      await SkillPack.importToBackend(file);
    } else {
      // 从粘贴文本导入：先尝试JSON，失败则自动包装纯文本为技能包
      var importData = pasteText;
      try {
        JSON.parse(pasteText);
      } catch(e) {
        // 不是JSON，自动包装为技能包
        var firstLine = pasteText.split('\n')[0].trim();
        var autoName = firstLine.length > 30 ? firstLine.substring(0, 30) + '...' : firstLine;
        if (!autoName) autoName = '自定义技能包';
        var autoId = 'custom_' + Date.now();
        var autoDesc = firstLine.length > 80 ? firstLine.substring(0, 80) + '...' : firstLine;
        importData = JSON.stringify({
          id: autoId,
          name: autoName,
          type: 'rules',
          version: '1.0.0',
          author: '用户',
          description: autoDesc,
          scope: 'generate',
          content: pasteText
        });
      }
      await SkillPack.importToBackend(importData);
    }
    // 导入成功
    document.getElementById('skill-import-overlay').remove();
    renderSkillsList(_skillTab);
    renderSkillCheckList();
    showToast('技能包导入成功');
  } catch(err) {
    _showSkillImportError(err.message || '导入失败');
  } finally {
    btn.disabled = false;
    btn.textContent = '导入';
  }
}

// 渲染右栏检查标签里的技能包按钮
function renderSkillCheckList() {
  var container = document.getElementById('skill-check-list');
  if (!container) return;
  if (typeof SkillPack === 'undefined') { container.textContent = ''; return; }
  var skills = SkillPack.listByScope('check').filter(function(s) { return s.type === 'skill'; });
  if (skills.length === 0) {
    container.innerHTML = '<span class="text-xs text-muted">暂无检查技能包，在工具箱→技能包中添加</span>';
    return;
  }
  container.innerHTML = skills.map(function(s) {
    return '<button class="check-btn' + (s.enabled ? '' : ' disabled') + '" onclick="runSkillCheck(\'' + s.id + '\')" style="padding:4px 10px;font-size:11px;cursor:pointer;border:1px solid var(--border);border-radius:4px;background:' + (s.enabled ? 'var(--accent-soft)' : 'var(--bg)') + ';color:' + (s.enabled ? 'var(--accent)' : 'var(--muted)') + '">' + s.name + '</button>';
  }).join('');
}

async function runSkillCheck(skillId) {
  var skill = SkillPack.getSkill(skillId);
  if (!skill || !skill.enabled) { showToast('技能包未启用'); return; }
  
  var checkScope = document.querySelector('input[name="check-scope"]:checked');
  checkScope = checkScope ? checkScope.value : 'chapter';
  
  var content = '';
  var chapterTitle = '';
  if (checkScope === 'chapter') {
    content = getEditorText();
    chapterTitle = (chapters && chapters[currentChapterIndex]) ? chapters[currentChapterIndex].title : '当前章';
  } else {
    // 全文模式
    for (var i = 0; i < chapters.length; i++) {
      var ch = await api('/api/chapter/load?index=' + i);
      if (ch.ok && ch.content) {
        content += '## ' + ch.title + '\n\n' + ch.content + '\n\n';
      }
    }
    chapterTitle = '全文';
  }
  
  // 构建prompt
  var prompt = skill.content + '\n\n## 待审稿内容\n\n### 书名: ' + (projectMeta ? projectMeta.title : '未知') + '\n### 章节: ' + chapterTitle + '\n\n' + content;
  
  // 添加世界观上下文
  var worldSettings = '';
  if (typeof getWorldSettingsText === 'function') {
    worldSettings = getWorldSettingsText();
  }
  if (worldSettings) {
    prompt = '## 世界观设定\n\n' + worldSettings + '\n\n' + prompt;
  }
  
  // 调用AI — 结果追加到历史记录，不覆盖之前的检查
  var resultsDiv = document.getElementById('val-results');
  var ts = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
  var loadingId = 'skill-check-loading-' + Date.now();
  
  // 如果是第一次检查，清空初始提示
  if (resultsDiv.querySelector('.val-empty-hint')) {
    resultsDiv.textContent = '';
  }
  
  // 追加加载提示
  var loadingHtml = '<div id="' + loadingId + '" style="padding:10px 12px;color:var(--accent);font-size:13px;border-left:3px solid var(--accent);margin-bottom:8px;background:var(--surface)">🤖 ' + skill.name + ' 正在分析... <span class="text-sm text-muted">' + ts + '</span></div>';
  resultsDiv.insertAdjacentHTML('afterbegin', loadingHtml);
  
  try {
    var r = await api('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({messages: [{role: 'user', content: prompt}]})
    });
    var loadingEl = document.getElementById(loadingId);
    if (loadingEl) loadingEl.remove();
    
    if (r.ok && r.content) {
      var html = (typeof marked !== 'undefined' ? marked.parse(r.content) : r.content.replace(/\n/g, '<br>'));
      var resultHtml = '<div style="padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:var(--radius-sm);font-size:13px;line-height:1.8;max-height:500px;overflow-y:auto;margin-bottom:8px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border-soft)">'
        + '<span style="font-weight:600;color:var(--accent);font-size:12px">📋 ' + skill.name + '</span>'
        + '<span class="text-sm text-muted">' + ts + '</span>'
        + '</div>'
        + '<div class="skill-check-body">' + html + '</div>'
        + '</div>';
      resultsDiv.insertAdjacentHTML('afterbegin', resultHtml);
    } else {
      var errHtml = '<div class="msg-danger-block">❌ ' + skill.name + '：' + (r.error || '分析失败') + ' <span class="text-sm text-muted">' + ts + '</span></div>';
      resultsDiv.insertAdjacentHTML('afterbegin', errHtml);
    }
  } catch(e) {
    var loadingEl2 = document.getElementById(loadingId);
    if (loadingEl2) loadingEl2.remove();
    var errHtml2 = '<div class="msg-danger-block">❌ ' + skill.name + '：' + e.message + ' <span class="text-sm text-muted">' + ts + '</span></div>';
    resultsDiv.insertAdjacentHTML('afterbegin', errHtml2);
  }
}

async function loadStats() {
  var summaryDiv = document.getElementById('stats-summary');
  var chartDiv = document.getElementById('stats-chart');
  var weeklyDiv = document.getElementById('stats-weekly');
  // 加载汇总
  var sr = await getStatsSummary();
  if (sr.ok) {
    summaryDiv.innerHTML = '<div style="display:flex;gap:16px;flex-wrap:wrap">'
      + _statCard('总字数', sr.total_words||0, '📝')
      + _statCard('章节数', sr.total_chapters||0, '📖')
      + _statCard('平均每章', sr.avg_chapter_words||0, '📊')
      + _statCard('写作天数', sr.writing_days||0, '📅')
      + _statCard('连续天数', sr.streak_days||0, '🔥')
      + _statCard('最佳一天', (sr.best_day&&sr.best_day.words)||0, '🏆')
      + '</div>';
  } else {
    summaryDiv.innerHTML = '<div class="text-md text-muted">' + (sr.error||'暂无数据') + '</div>';
  }
  // 加载每日统计
  var dr = await getStatsDaily(30);
  if (dr.ok && dr.data) {
    chartDiv.innerHTML = _renderBarChart(dr.data);
  } else {
    chartDiv.innerHTML = '<div class="empty-state-md">暂无数据</div>';
  }
  // 加载周统计
  var wr = await getStatsWeekly();
  if (wr.ok && wr.data) {
    weeklyDiv.innerHTML = _renderBarChart(wr.data.map(function(w){return {date:w.week_start,words_added:w.words_added};}), '本周字数');
  } else {
    weeklyDiv.innerHTML = '<div class="empty-state-md">暂无数据</div>';
  }
}

function _statCard(label, val, icon) {
  return '<div style="flex:1;min-width:100px;text-align:center;padding:12px;background:var(--surface);border-radius:var(--radius-sm)">'
    + '<div style="font-size:20px;margin-bottom:4px">' + icon + '</div>'
    + '<div style="font-size:18px;font-weight:700;color:var(--accent)">' + (typeof val==='number'?val.toLocaleString():val) + '</div>'
    + '<div class="text-sm text-muted">' + label + '</div></div>';
}

function _renderBarChart(data, title) {
  if (!data || data.length === 0) return '<div class="empty-state-md">暂无数据</div>';
  var maxVal = 0;
  data.forEach(function(d) { if (d.words_added > maxVal) maxVal = d.words_added; });
  if (maxVal === 0) maxVal = 1;
  var html = '<div style="display:flex;align-items:flex-end;gap:2px;height:160px;padding:8px 0;border-bottom:1px solid var(--border-soft)">';
  data.forEach(function(d) {
    var h = Math.max(2, (d.words_added / maxVal) * 140);
    var color = d.words_added > 0 ? 'var(--accent)' : 'var(--border)';
    html += '<div style="flex:1;min-width:4px;height:' + h + 'px;background:' + color + ';border-radius:2px 2px 0 0;position:relative" title="' + d.date + ': ' + d.words_added + '字"></div>';
  });
  html += '</div>';
  // 显示日期标签（只显示首尾和中间）
  if (data.length > 0) {
    html += '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:4px">'
      + '<span>' + data[0].date + '</span>'
      + (data.length > 2 ? '<span>' + data[Math.floor(data.length/2)].date + '</span>' : '')
      + '<span>' + data[data.length-1].date + '</span></div>';
  }
  return html;
}


// ── AI责编审稿面板（从右侧检查标签迁移至工具箱）──
function openAIEditorPanel() {
  // 关闭工具箱下拉
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';

  // 如果已有浮层，直接显示
  var existing = document.getElementById('ai-editor-overlay');
  if (existing) { existing.style.display = 'flex'; return; }

  var overlay = document.createElement('div');
  overlay.id = 'ai-editor-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;z-index:400;background:var(--bg);flex-direction:column;display:flex';

  overlay.innerHTML = '<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0">'
    + '<span style="font-size:14px;font-weight:700;color:var(--accent)">📋 AI责编审稿</span>'
    + '<span class="text-sm text-muted">模拟出版社责编审稿，多维打分与诊断</span>'
    + '<span class="flex-1"></span>'
    + '<label style="font-size:11px;color:var(--muted);cursor:pointer;margin-right:8px"><input type="radio" name="ai-editor-scope" value="chapter" checked class="v-middle-gap-xs">单章</label>'
    + '<label style="font-size:11px;color:var(--muted);cursor:pointer"><input type="radio" name="ai-editor-scope" value="full" class="v-middle-gap-xs">全文</label>'
    + '<button onclick="document.getElementById(\'ai-editor-overlay\').style.display=\'none\'" style="padding:4px 12px;border:1px solid var(--border);background:var(--bg);color:var(--muted);border-radius:4px;font-size:12px;cursor:pointer;font-family:var(--sans)">✕ 关闭</button>'
    + '</div>'
    + '<div style="flex:1;overflow:auto;padding:16px;max-width:900px;margin:0 auto;width:100%">'
    + '<div id="ai-editor-skills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px"></div>'
    + '<div id="ai-editor-results" class="flex-col-md"></div>'
    + '</div>';

  document.body.appendChild(overlay);

  // 渲染技能包按钮
  var skillsDiv = document.getElementById('ai-editor-skills');
  if (typeof SkillPack !== 'undefined') {
    var skills = SkillPack.listByScope('check').filter(function(s) { return s.type === 'skill'; });
    if (skills.length === 0) {
      skillsDiv.innerHTML = '<span class="text-md text-muted">暂无检查技能包，请在工具箱→技能包中添加</span>';
    } else {
      skillsDiv.innerHTML = skills.map(function(s) {
        return '<button onclick="runAIEditorCheck(\'' + s.id + '\')" style="padding:6px 14px;font-size:12px;cursor:pointer;border:1px solid var(--border);border-radius:4px;background:' + (s.enabled ? 'var(--accent-soft)' : 'var(--bg)') + ';color:' + (s.enabled ? 'var(--accent)' : 'var(--muted)') + ';font-weight:' + (s.enabled ? '600' : 'normal') + '">' + s.name + '</button>';
      }).join('');
    }
  }
}

async function runAIEditorCheck(skillId) {
  if (typeof SkillPack === 'undefined') { showToast('技能包模块未加载'); return; }
  var skill = SkillPack.getSkill(skillId);
  if (!skill || !skill.enabled) { showToast('技能包未启用'); return; }

  var scopeRadio = document.querySelector('input[name="ai-editor-scope"]:checked');
  var checkScope = scopeRadio ? scopeRadio.value : 'chapter';

  var content = '';
  var chapterTitle = '';
  if (checkScope === 'chapter') {
    var el = document.getElementById('editor-content');
    content = el ? (el.innerText || '') : '';
    chapterTitle = (typeof chapters !== 'undefined' && chapters && typeof currentChapterIndex !== 'undefined' && chapters[currentChapterIndex])
      ? chapters[currentChapterIndex].title : '当前章';
  } else {
    if (typeof chapters !== 'undefined' && chapters) {
      for (var i = 0; i < chapters.length; i++) {
        try {
          var ch = await api('/api/chapter/load?index=' + i);
          if (ch.ok && ch.content) content += '## ' + ch.title + '\n\n' + ch.content + '\n\n';
        } catch(e) {}
      }
    }
    chapterTitle = '全文';
  }

  if (!content.trim() || content.trim().length < 100) {
    showToast('内容太少，至少需要100字'); return;
  }

  var prompt = skill.content + '\n\n## 待审稿内容\n\n### 书名: ' + (typeof projectMeta !== 'undefined' && projectMeta ? projectMeta.title : '未知') + '\n### 章节: ' + chapterTitle + '\n\n' + content;

  if (typeof getWorldSettingsText === 'function') {
    var ws = getWorldSettingsText();
    if (ws) prompt = '## 世界观设定\n\n' + ws + '\n\n' + prompt;
  }

  var resultsDiv = document.getElementById('ai-editor-results');
  var ts = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
  var loadingId = 'ai-editor-loading-' + Date.now();

  var loadingHtml = '<div id="' + loadingId + '" style="padding:10px 12px;color:var(--accent);font-size:13px;border-left:3px solid var(--accent);margin-bottom:8px;background:var(--surface)">🤖 ' + skill.name + ' 正在分析… <span class="text-sm text-muted">' + ts + '</span></div>';
  resultsDiv.insertAdjacentHTML('afterbegin', loadingHtml);

  try {
    var r = await api('/api/ai/chat', { method: 'POST', body: JSON.stringify({messages: [{role: 'user', content: prompt}]}) });
    var loadingEl = document.getElementById(loadingId);
    if (loadingEl) loadingEl.remove();

    if (r.ok && r.content) {
      var html = (typeof marked !== 'undefined' ? marked.parse(r.content) : r.content.replace(/\n/g, '<br>'));
      var resultHtml = '<div style="padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:var(--radius-sm);font-size:13px;line-height:1.8;max-height:500px;overflow-y:auto;margin-bottom:8px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border-soft)">'
        + '<span style="font-weight:600;color:var(--accent);font-size:12px">📋 ' + skill.name + '</span>'
        + '<span class="text-sm text-muted">' + ts + '</span>'
        + '</div>'
        + '<div>' + html + '</div>'
        + '</div>';
      resultsDiv.insertAdjacentHTML('afterbegin', resultHtml);
    } else {
      var errHtml = '<div class="msg-danger-block">❌ ' + skill.name + '：' + (r.error || '分析失败') + ' <span class="text-sm text-muted">' + ts + '</span></div>';
      resultsDiv.insertAdjacentHTML('afterbegin', errHtml);
    }
  } catch(e) {
    var loadingEl2 = document.getElementById(loadingId);
    if (loadingEl2) loadingEl2.remove();
    var errHtml2 = '<div class="msg-danger-block">❌ 网络错误: ' + e.message + '</div>';
    resultsDiv.insertAdjacentHTML('afterbegin', errHtml2);
  }
}

