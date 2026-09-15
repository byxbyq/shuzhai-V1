// Extracted from app.js - 首次启动向导 + initApp
// ═══════════════════════════════════════════
// 首次启动向导
// ═══════════════════════════════════════════

async function checkFirstLaunch() {
  try {
    var r = await api('/api/ai/config');
    if (r.ok && r.config) {
      var cfg = r.config;
      var prov = cfg.provider || 'deepseek';
      // 检查当前 provider 或任意 provider 是否已配置密钥
      var hasKey = (cfg[prov] && (cfg[prov].has_key || cfg[prov].api_key)) || cfg.api_key || cfg.deepseek_api_key || (prov === 'ollama' && cfg.ollama_host);
      if (!hasKey) {
        // 再检查其他 provider 是否有密钥
        var provs = ['deepseek', 'openai', 'doubao', 'kimi', 'ollama'];
        for (var i = 0; i < provs.length && !hasKey; i++) {
          var p = provs[i];
          if (cfg[p] && (cfg[p].has_key || cfg[p].api_key)) hasKey = true;
          if (p === 'ollama' && cfg[p] && cfg[p].base_url) hasKey = true;
        }
      }
      // 已有项目也不显示向导
      if (!hasKey) {
        try {
          var projList = JSON.parse(localStorage.getItem('shuzhai_project_list') || '[]');
          if (projList.length > 0) hasKey = true;
        } catch(e) {}
      }
      if (!hasKey) {
        // AI未配置，显示向导
        var wizard = document.getElementById('wizard-overlay');
        if (wizard) { wizard.classList.remove('hidden'); wizard.style.display = 'flex'; }
      }
    }
  } catch(e) { console.error('checkFirstLaunch error:', e); }
}

function skipWizard() {
  var wizard = document.getElementById('wizard-overlay');
  if (wizard) { wizard.style.display = 'none'; wizard.classList.add('hidden'); }
}

async function completeWizard() {
  var wizard = document.getElementById('wizard-overlay');
  var selectedAI = document.querySelector('input[name="wizard-ai"]:checked');
  var provider = selectedAI ? selectedAI.value : 'deepseek';
  
  if (provider === 'deepseek') {
    var apiKey = document.getElementById('wizard-api-key');
    if (apiKey && apiKey.value.trim()) {
      await api('/api/ai/config', { method: 'POST', body: JSON.stringify({
        provider: 'deepseek',
        api_key: apiKey.value.trim(),
        endpoint: 'https://api.deepseek.com',
        model: 'deepseek-v4-flash'
      }) });
      showToast('✅ DeepSeek配置已保存');
    } else {
      showToast('⚠️ 请填写API密钥');
      return;
    }
  } else if (provider === 'ollama') {
    await api('/api/ai/config', { method: 'POST', body: JSON.stringify({
      provider: 'ollama',
      ollama_host: 'http://localhost:11434',
      ollama_model: 'qwen2.5:14b'
    }) });
    showToast('✅ Ollama配置已保存');
  } else if (provider === 'openai') {
    await api('/api/ai/config', { method: 'POST', body: JSON.stringify({
      provider: 'openai'
    }) });
    showToast('✅ OpenAI配置已保存，请在设置中填写密钥');
  }
  
  if (wizard) { wizard.style.display = 'none'; wizard.classList.add('hidden'); }
  if (typeof loadModelConfig === 'function') loadModelConfig();
  // 启动创作向导
  setTimeout(function() { startCreativeWizard(); }, 800);
}

function switchModelProvider(provider) {
  document.querySelectorAll('.mp-tab').forEach(function(t) { t.classList.remove('active'); });
  var tab = document.querySelector('[data-provider="' + provider + '"]');
  if (tab) tab.classList.add('active');
  var dp = document.getElementById('mp-deepseek-panel');
  var op = document.getElementById('mp-ollama-panel');
  var oap = document.getElementById('mp-openai-panel');
  if (dp) dp.style.display = provider === 'deepseek' ? 'block' : 'none';
  if (op) op.style.display = provider === 'ollama' ? 'block' : 'none';
  if (oap) oap.style.display = provider === 'openai' ? 'block' : 'none';
  if (typeof saveModelConfig === 'function') saveModelConfig();
}

// ═══════════════════════════════════════════
// 创作向导（在 AI 配置完成后启动）
// ═══════════════════════════════════════════

// 向导状态
window._wizardState = null; // {stage, genre, world_text, protagonist_info, char_text, oneliner, outline_text}

function startCreativeWizard(force) {
  // 非强制模式：已有项目则跳过
  if (!force) {
    try {
      var projList = JSON.parse(localStorage.getItem('shuzhai_project_list') || '[]');
      if (projList.length > 0) return;
    } catch(e) {}
  }
  
  window._wizardState = { stage: 'ask_genre', genre: '', world_text: '', protagonist_info: '', char_text: '', oneliner: '', outline_text: '', volumes_text: '', chapter_outline_text: '', append_stage: null, append_volume_index: null };
  
  // 打开 AI 助手面板
  var panel = document.getElementById('ai-assistant-panel');
  var fab = document.getElementById('ai-assistant-fab');
  if (panel && panel.style.display === 'none') {
    panel.style.display = 'flex';
    if (fab) fab.style.display = 'none';
  }
  
  // 注入向导欢迎消息
  var msgDiv = document.getElementById('assistant-messages');
  if (!msgDiv) return;
  msgDiv.innerHTML = '';
  
  var welcomeDiv = document.createElement('div');
  welcomeDiv.style.cssText = 'align-self:flex-start;max-width:90%;padding:10px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:12px 12px 12px 4px;font-size:13px;line-height:1.6;word-break:break-word;color:var(--ink);white-space:pre-wrap';
  welcomeDiv.textContent = '🎉 欢迎使用书斋！我是你的创作向导，帮你一步步搭建小说的世界观、人物和大纲。\n\n首先：你想写什么题材？';
  msgDiv.appendChild(welcomeDiv);
  
  // 题材快捷按钮
  var btnDiv = document.createElement('div');
  btnDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin:4px 0;padding:0 14px;align-self:flex-start;max-width:90%';
  btnDiv.id = 'wizard-genre-btns';
  var genres = ['仙侠', '都市', '玄幻', '科幻', '历史', '悬疑', '言情', '军事', '游戏', '末世', '重生', '穿越', '武侠', '灵异', '同人', '轻小说', '古言', '职场', '电竞', '无限流', '系统流', '快穿', '甜宠', '星际'];
  genres.forEach(function(g) {
    var b = document.createElement('button');
    b.textContent = g;
    b.style.cssText = 'padding:4px 12px;background:var(--bg);border:1px solid var(--border);border-radius:14px;font-size:12px;cursor:pointer;color:var(--ink)';
    b.onmouseover = function() { b.style.background = 'var(--accent)'; b.style.color = '#fff'; b.style.borderColor = 'var(--accent)'; };
    b.onmouseout = function() { b.style.background = 'var(--bg)'; b.style.color = 'var(--ink)'; b.style.borderColor = 'var(--border)'; };
    b.onclick = function() {
      document.getElementById('assistant-input').value = g;
      sendAssistantMessage();
    };
    btnDiv.appendChild(b);
  });
  msgDiv.appendChild(btnDiv);
  msgDiv.scrollTop = msgDiv.scrollHeight;
  
  setTimeout(function() {
    var input = document.getElementById('assistant-input');
    if (input) input.placeholder = '点击上面题材按钮，或直接输入...';
  }, 300);
}

function _clearWizardGenreBtns() {
  var btns = document.getElementById('wizard-genre-btns');
  if (btns) btns.remove();
}

// ═══════════════════════════════════════════
// 应用初始化
async function initApp() {
  try {
    // 安全迁移：从后端 API 获取 AI 配置（密钥不在 HTML 中）
    if (window.LocalDB && typeof LocalDB.initAIConfigFromBackend === 'function') {
      LocalDB.initAIConfigFromBackend();
    }
    // Capacitor/APK 模式：提示后端启动中
    if (typeof Capacitor !== 'undefined' && Capacitor.isNative) {
      if (typeof showToast === 'function') showToast('后端启动中，请稍候...', 'info');
      console.log('[initApp] Capacitor 模式，等待 Python 后端启动');
    }
    // 加载项目列表（返回值供书架首页进场判断用）
    var _loadedProjects = [];
    if (typeof loadProjectList === 'function') {
      try { _loadedProjects = (await loadProjectList()) || []; } catch(_eL) { _loadedProjects = []; }
    }
    // 加载工作流状态
    if (typeof loadWorkflowState === 'function') {
      await loadWorkflowState();
    }
    // 加载AI配置
    if (typeof loadModelConfig === 'function') {
      await loadModelConfig();
    }
    // 加载世界设定和叙事风格（确保下拉框回填）
    if (typeof loadProjectSettings === 'function') {
      try { await loadProjectSettings(); } catch(e) { console.warn('loadProjectSettings failed:', e); }
    }
    // 自动加载章节数据（确保按钮点击时chapters不为空）
    if (typeof loadChaptersFromAPI === 'function') {
      try { await loadChaptersFromAPI(); } catch(e) { console.warn('loadChaptersFromAPI failed:', e); }
    }
    // ── 书架首页：进场决策 ──
    // 1) 从书架"继续写"跳转过来（带恢复点）：直接跳到那一章，不再弹书架
    // 2) 书架非空：默认展示书架首页
    // 3) 空书架：保持原行为（加载第1章，下方定时器会弹创作向导）
    var _entryResume = null;
    try { _entryResume = JSON.parse(localStorage.getItem('shuzhai_resume') || 'null'); } catch(_eR) {}
    if (_entryResume) {
      localStorage.removeItem('shuzhai_resume');
      var _resumeCh = (typeof _entryResume.chapter === 'number' && _entryResume.chapter >= 0) ? _entryResume.chapter : 0;
      if (typeof loadChapterContentAPI === 'function') {
        try { await loadChapterContentAPI(_resumeCh); } catch(e) { console.warn('loadChapterContentAPI(resume) failed:', e); }
      }
    } else {
      var _entryPl = Array.isArray(_loadedProjects) ? _loadedProjects : [];
      if (_entryPl.length === 0) {
        try { _entryPl = JSON.parse(localStorage.getItem('shuzhai_project_list') || '[]'); } catch(_eP) {}
      }
      if (_entryPl.length > 0 && window.Reader && typeof Reader.openBookshelf === 'function') {
        // 等 UI 就绪后展示书架（避免与初始化竞态）
        setTimeout(function() { Reader.openBookshelf(); }, 400);
        if (typeof loadChapterContentAPI === 'function') {
          try { await loadChapterContentAPI(0); } catch(e) { console.warn('loadChapterContentAPI failed:', e); }
        }
      } else {
        // 加载第1章内容到编辑器
        if (typeof loadChapterContentAPI === 'function') {
          try { await loadChapterContentAPI(0); } catch(e) { console.warn('loadChapterContentAPI failed:', e); }
        }
      }
    }
    // 刷新上下文面板
    loadContextPanel();
    // 标记数据已加载完成，启动自动保存
    window._dataLoaded = true;
    // 空项目时自动弹出创作向导（延迟确保UI就绪，且向导非活跃时）
    setTimeout(function() {
      if (!window._wizardState) {
        try {
          var _pl = JSON.parse(localStorage.getItem('shuzhai_project_list') || '[]');
          if (_pl.length === 0) startCreativeWizard();
        } catch(_e) {}
      }
    }, 1200);
    // 恢复检查结果（页面刷新后）
    try {
      var restoreIdx = (typeof currentChapterIndex !== 'undefined' && currentChapterIndex >= 0) ? currentChapterIndex : 0;
      // 读取上次使用的scope（保存在localStorage中）
      var lastScope = localStorage.getItem('valResults_lastScope') || 'full';
      var scopes = [lastScope, 'full', 'chapter'];
      var restored = false;
      for (var si = 0; si < scopes.length && !restored; si++) {
        var rKey = 'valResults_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + restoreIdx + '_' + scopes[si];
        var rSaved = localStorage.getItem(rKey);
        if (rSaved) {
          var rData = JSON.parse(rSaved);
          var rDiv = document.getElementById('val-results');
          if (rDiv && rData.html) {
            rDiv.innerHTML = rData.html;
            // 不将 HTML 字符串赋值给 lastValResult（类型不兼容），保留 null 等待下次检查时赋值对象
            restored = true;
            // 恢复问题列表和"一键修复"按钮
            var rProbsKey = 'valProblems_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + restoreIdx + '_' + scopes[si];
            var rSavedProbs = localStorage.getItem(rProbsKey);
            if (rSavedProbs) {
              try {
                window._allValProblems = JSON.parse(rSavedProbs);
                // 重新绑定"一键修复"按钮事件
                var rFixBtn = rDiv.querySelector('#fix-all-bar button');
                if (rFixBtn) {
                  rFixBtn.onclick = function() { valAIFixAll(); };
                }
              } catch(e2) { /* ignore */ }
            }
            // 恢复scope单选按钮状态
            var scopeRadio = document.querySelector('input[name="check-scope"][value="' + scopes[si] + '"]');
            if (scopeRadio) scopeRadio.checked = true;
            console.log('Restored val results for ch' + restoreIdx + ' ' + scopes[si]);
          }
        }
      }
    } catch(e) { /* ignore */ }
  } catch(e) { console.error('Init error:', e); }
}

// ── Load model config on init ──
document.addEventListener('DOMContentLoaded', async function() {
  setTimeout(loadModelConfig, 500);
  // 检查是否首次启动（AI未配置）
  setTimeout(checkFirstLaunch, 800);
  // 加载项目列表和数据
  setTimeout(initApp, 300);
  // 初始化技能包检查按钮
  setTimeout(function() { if (typeof renderSkillCheckList === 'function') renderSkillCheckList(); }, 1000);

  // ── 撤销 / 重做 ──
  var btnUndo = document.getElementById('btn-undo');
  var btnRedo = document.getElementById('btn-redo');
  var editorEl = document.getElementById('editor-content');
  function doUndo() {
    if (editorEl) { editorEl.focus(); document.execCommand('undo', false, null); }
  }
  function doRedo() {
    if (editorEl) { editorEl.focus(); document.execCommand('redo', false, null); }
  }
  if (btnUndo) btnUndo.addEventListener('click', doUndo);
  if (btnRedo) btnRedo.addEventListener('click', doRedo);
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); doUndo(); }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); doRedo(); }
  });

  // Load project info and chapters on startup
  try {
    var info = await loadProjectInfo();
    if (info.ok) {
      var elP = document.getElementById('project-name');
      var elC = document.getElementById('current-chapter-label');
      if (elP) elP.textContent = info.title || '';
      if (elC) elC.textContent = info.genre || '';
    }
    // Load project settings (world settings, characters, etc.) from backend
    await loadProjectSettings();
    // Load project outline (novelActs)
    await loadProjectOutline();
    await loadChaptersFromAPI();
    if (chapters && chapters.length > 0) {
      currentChapterIndex = 0;
      if (typeof renderChapterList === 'function') renderChapterList();
      if (typeof renderChapterMiniList === 'function') renderChapterMiniList();
      await loadChapterContentAPI(0);
    }
    // Load context panel after data is ready
    loadContextPanel();
    // 初始化设定编辑器（步骤1）
    setTimeout(function() {
      if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
    }, 100);
    // 恢复上次工作步骤
    setTimeout(function() {
      var lastStep = parseInt(localStorage.getItem('shuzhai_last_step')) || 1;
      if (lastStep > 1 && typeof goToStep === 'function') {
        goToStep(lastStep);
      } else {
        // 步骤1时也调用一次，确保面板状态正确
        if (typeof goToStep === 'function') goToStep(STEPS.世界观);
      }
    }, 200);
    // 标记数据已加载完成，启动自动保存
    window._dataLoaded = true;
  } catch(e) { console.error('Init error:', e); }
});