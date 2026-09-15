// Extracted from app.js - 初始化逻辑 (extractOutlineFromNovelActs, handleProjectClick, reloadAllProjectData, injectFieldToolbar, renderValResult, AI修复)

// 安全HTML转义函数（避免依赖memory-panel.js加载顺序）
function esc(str) {
  if (str == null) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── 全局章节列表渲染函数 ──
// 渲染所有4个卷导航容器（供 state.js Proxy 和各模块调用）
function renderChapterList() {
  var containers = ['vol-nav-writing', 'vol-nav-outline', 'vol-nav-timeline', 'vol-nav-content'];
  containers.forEach(function(cid) {
    if (typeof renderVolumeNav === 'function') {
      renderVolumeNav(cid, function(idx) {
        if (typeof syncChapterAcrossPanels === 'function') {
          syncChapterAcrossPanels(idx);
        } else if (typeof loadChapterContentAPI === 'function') {
          loadChapterContentAPI(idx);
        }
      });
    }
  });
}

// 全局迷你章节列表渲染函数（简化版，只渲染写作容器）
function renderChapterMiniList() {
  if (typeof renderVolumeNav === 'function') {
    renderVolumeNav('vol-nav-writing', function(idx) {
      if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(idx);
    });
  }
}

// ── 加载工作流状态 ──
// 从 localStorage 恢复工作流步骤和步骤状态
function loadWorkflowState() {
  try {
    var saved = localStorage.getItem('shuzhai_workflow_state');
    if (saved) {
      var data = JSON.parse(saved);
      if (data && data.currentStep) {
        workflowState.currentStep = data.currentStep;
        if (data.stepStatus) {
          Object.keys(data.stepStatus).forEach(function(key) {
            workflowState.stepStatus[key] = data.stepStatus[key];
          });
        }
      }
    }
  } catch( e) {
    console.warn('loadWorkflowState failed:', e);
  }
}

// ── 保存工作流状态 ──
function saveWorkflowState() {
  try {
    localStorage.setItem('shuzhai_workflow_state', JSON.stringify(workflowState));
  } catch( e) {
    console.warn('saveWorkflowState failed:', e);
  }
}

function extractOutlineFromNovelActs(chIndex) {
  var items = [];
  if (typeof novelActs !== 'undefined' && novelActs.length) {
    novelActs.forEach(function(act) {
      if (act.events) {
        act.events.forEach(function(ev) {
          // 匹配章节号，如 "Ch.1" 或 "第1章"
          var chMatch = (ev.ch || '').match(/(\d+)/);
          var evCh = chMatch ? parseInt(chMatch[1]) : -1;
          if (evCh === chIndex + 1) {
            items.push({text: ev.text, current: items.length === 0, source: 'novel-act'});
          }
        });
      }
    });
  }
  if (items.length === 0) {
    items.push({text: '【第' + (chIndex + 1) + '章大纲要点】', current: true, source: 'human'});
  }
  return items;
}

  // 全局项目点击处理函数（用于内联 onclick）
  window.handleProjectClick = async function(path) {
    const projectDropdown = document.getElementById('project-dropdown');
    projectDropdown.style.display = 'none';
    showToast('正在打开项目...');

    const r = await api('/api/project/open', {
      method: 'POST',
      body: JSON.stringify({path})
    });
    if (r.ok) {
      // 重新加载所有项目数据（不刷新页面）
      await reloadAllProjectData();
      showToast('项目已切换: ' + (r.title || ''));
    } else {
      showToast('打开失败: ' + (r.error || '未知错误'));
    }
  }

  // 重新加载所有项目数据（切换项目后调用）
  // isNewProject: 如果是新建项目，使用空数据而非默认值
  async function reloadAllProjectData(isNewProject) {
    try {
      // 0. 清空旧数据 —— 必须清空所有全局变量，否则旧项目内存数据会覆盖新项目
      worldSettings = [];
      novelActs = [];
      chOutline = [];
      chapters = [];
      currentChapterIndex = 0;
      // ★ 修步骤乱打勾：清空上一个项目残留的工作流步骤状态缓存（否则UI步骤圈会显示旧项目的✓）
      window._workflowStepCache = null;
      // 重置当前步骤，避免新项目时还停留在旧项目的步骤6/7/8
      currentWorkflowStep = 1;
      // 清空结构化设定面板和角色面板的内存残留（防止新项目显示旧项目数据）
      if (typeof worldMeta !== 'undefined') {
        worldMeta = { narrative_style: {}, era: {}, world_rules: [] };
        // ★ 必须同步清空UI输入框，否则旧DOM值会被saveWorldMeta写入新项目DB
        if (typeof renderWorldMeta === 'function') renderWorldMeta();
      }
      // 清除待执行的saveWorldMeta debounce定时器（防止旧项目保存请求覆盖新项目）
      if (typeof _debounceSaveTimer !== 'undefined' && _debounceSaveTimer) {
        clearTimeout(_debounceSaveTimer);
        _debounceSaveTimer = null;
      }
      if (typeof characters !== 'undefined') {
        characters = [];
      }
      
      // 1. 加载项目信息
      var info = await loadProjectInfo();
      if (info.ok) {
        var elP = document.getElementById('project-name');
        var elC = document.getElementById('current-chapter-label');
        if (elP) elP.textContent = info.title || '';
        if (elC) elC.textContent = info.genre || '';
      }
      // 2. 加载设定和大纲（从后端或默认值）
      if (isNewProject) {
        // 新项目：保持空数据，让用户自己填写
        worldSettings = [];
        novelActs = [];
        chOutline = [];
      } else {
        // 切换已有项目：从后端加载，无数据时使用默认值
        await loadProjectSettings();
        await loadProjectOutline();
      }
      // 3. 加载章节列表
      await loadChaptersFromAPI();
      // 4. 重新渲染所有UI
      if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
      if (typeof renderNovelOutlineEditor === 'function') renderNovelOutlineEditor();
      if (typeof renderChapterList === 'function') renderChapterList();
      if (typeof renderChapterMiniList === 'function') renderChapterMiniList();
      if (chapters && chapters.length > 0) {
        await loadChapterContentAPI(0);
      }
      // 5. 刷新上下文面板
      loadContextPanel();
      // 6. 如果当前在步骤3，刷新章节大纲编辑器
      if (currentWorkflowStep === STEPS.章节大纲 && typeof renderChapterOutlineEditor === 'function') {
        renderChapterOutlineEditor();
      }
    } catch(e) { console.error('reloadAllProjectData error:', e); }
  }


  

  /* ---- REAL-TIME WORD COUNT ---- */
  function initEditorWordCount() {
    var editorContent = document.getElementById('editor-content');
    if (!editorContent) { setTimeout(initEditorWordCount, 200); return; }

    function updateWordCount(){
      var text=(editorContent.textContent||'').trim();
      var count=text?text.replace(/\s+/g,'').length:0;
      var wcEl = document.getElementById('word-count');
      if (wcEl) wcEl.textContent=count.toLocaleString('zh-CN');
      var currentCh=document.querySelector('.chapter-item.active');
      if(currentCh){var ch=currentCh.dataset.ch;chapters[ch].words=count;}
      if(typeof updateWritingToolbar==='function') updateWritingToolbar();
    }
    editorContent.addEventListener('input',updateWordCount);
    updateWordCount();
  }
  initEditorWordCount();

  function setFontScale(v){
    v=parseFloat(v);
    var app=document.getElementById('app')||document.body;
    app.style.transform='scale('+v+')';
    app.style.transformOrigin='top left';
    app.style.width=(100/v)+'%';
    app.style.height=(100/v)+'%';
    var fsVal = document.getElementById('fs-val');
    var fsSlider = document.getElementById('fs-slider');
    if (fsVal) fsVal.textContent=Math.round(v*100)+'%';
    if (fsSlider) fsSlider.value=v;
    localStorage.setItem('v24-font-scale',v);
  }
  function changeFontScale(delta){
    var fsSlider = document.getElementById('fs-slider');
    if (!fsSlider) return;
    var s=parseFloat(fsSlider.value);
    s=Math.max(0.8,Math.min(1.5,s+delta));
    setFontScale(s);
  }
  // restore saved font scale
  (function(){var saved=localStorage.getItem('v24-font-scale');if(saved){setTimeout(function(){setFontScale(parseFloat(saved));},100);}})();

  console.log('书斋 已就绪');

  // ── 项目切换按钮事件绑定 ──
  var btnOpen = document.getElementById('btn-open-project');
  if (btnOpen && typeof toggleProjectPicker === 'function') {
    btnOpen.addEventListener('click', toggleProjectPicker);
  }
  var btnNew = document.getElementById('btn-new-project');
  if (btnNew) {
    btnNew.addEventListener('click', function() {
      document.getElementById('new-project-overlay').classList.add('active');
      document.getElementById('new-project-title').value = '';
      document.getElementById('new-project-title').focus();
    });
  }

  // ── 新建项目对话框按钮 ──
  function closeNewProjectOverlay() {
    document.getElementById('new-project-overlay').classList.remove('active');
  }
  var btnClose = document.getElementById('new-project-close');
  if (btnClose) btnClose.addEventListener('click', closeNewProjectOverlay);
  var btnCancel = document.getElementById('new-project-cancel');
  if (btnCancel) btnCancel.addEventListener('click', closeNewProjectOverlay);
  var btnCreate = document.getElementById('new-project-create');
  if (btnCreate) {
    btnCreate.addEventListener('click', async function() {
      var title = document.getElementById('new-project-title').value.trim();
      if (!title) { document.getElementById('new-project-title').focus(); return; }
      var genre = document.getElementById('new-project-genre').value;
      var lenSel = document.getElementById('new-project-length').value;
      var length = lenSel === 'custom' ? parseInt(document.getElementById('new-project-custom-input').value) || 10 : parseInt(lenSel);
      btnCreate.disabled = true;
      btnCreate.textContent = '创建中...';
      try {
        var r = await newProject(title, genre, length);
        if (r && r.ok) {
          closeNewProjectOverlay();
          await reloadAllProjectData(true);
          if (typeof loadProjectList === 'function') loadProjectList();
          if (typeof showToast === 'function') showToast('项目已创建: ' + title);
        } else {
          if (typeof showToast === 'function') showToast('创建失败: ' + (r && r.error || '未知错误'));
        }
      } catch(e) {
        if (typeof showToast === 'function') showToast('创建出错: ' + e.message);
      }
      btnCreate.disabled = false;
      btnCreate.textContent = '创建';
    });
  }

// ── Model Popover toggle ──
function toggleModelPopover(e) {
  if (e) e.stopPropagation();
  const pop = document.getElementById('model-popover');
  pop.classList.toggle('visible');
  if (pop.classList.contains('visible') && typeof loadAIUsage === 'function') {
    loadAIUsage(false);
  }
}
async function loadProjectList() {
  try {
    var r = await api('/api/project/list');
    var inner = document.getElementById('project-list-inner');
    var projects = (r && r.data) || (r && r.items) || r || [];
    if (!Array.isArray(projects)) projects = [];
    // 持久化项目列表（书架首页/空库向导判断用）
    try { localStorage.setItem('shuzhai_project_list', JSON.stringify(projects)); } catch(_eS) {}
    if (!inner) return projects;
    inner.textContent = '';
    if (projects.length === 0) {
      inner.innerHTML = '<div style="color:#888;text-align:center;padding:12px">暂无项目</div>';
      return projects;
    }
    var currentDir = (typeof currentProjectDir !== 'undefined') ? currentProjectDir : '';
    projects.forEach(function(p) {
      var dir = p.project_dir || p.dir || '';
      var title = p.title || p.name || dir.split(/[/\\]/).pop();
      var isActive = dir === currentDir;
      var div = document.createElement('div');
      div.className = 'proj-item' + (isActive ? ' active' : '');
      div.style.cssText = 'padding:8px 12px;cursor:pointer;border-radius:6px;margin:4px 0;display:flex;justify-content:space-between;align-items:center;color:#222;' + (isActive ? 'background:var(--accent,#4a9eff);color:#fff;' : 'background:#f0f0f0;');
      var delBtn = '<button class="proj-del-btn" title="删除项目" style="background:none;border:none;cursor:pointer;font-size:14px;color:#999;padding:2px 6px;border-radius:4px;" >🗑</button>';
      div.innerHTML = '<span class="flex-1">' + esc(title) + '</span><span style="font-size:11px;opacity:0.7;margin-right:6px">' + esc(p.genre || '') + ' ' + (p.chapter_count || '') + '章</span>' + (isActive ? '' : delBtn);
      div.onclick = function(e) {
        if (e.target.classList.contains('proj-del-btn') || e.target.closest('.proj-del-btn')) return;
        if (!isActive && typeof switchProject === 'function') switchProject(dir);
      };
      // 删除按钮事件
      var delBtnEl = div.querySelector('.proj-del-btn');
      if (delBtnEl) {
        delBtnEl.addEventListener('click', function(e) {
          e.stopPropagation();
          if (confirm('确定删除项目「' + title + '」？\n此操作不可恢复！')) {
            api('/api/project/delete', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              body: JSON.stringify({project_dir: dir})
            }).then(function(r) {
              if (r && r.ok) {
                showToast('已删除: ' + title, 'success', 2000);
                if (typeof loadProjectList === 'function') loadProjectList();
              } else {
                showToast('删除失败: ' + (r && r.error || '未知错误'), 'error', 3000);
              }
            }).catch(function(e) {
              showToast('删除失败: ' + e.message, 'error', 3000);
            });
          }
        });
      }
      inner.appendChild(div);
    });
    return projects;
  } catch(e) {
    console.warn('loadProjectList failed:', e);
    return [];
  }
}

async function switchProject(projectDir) {
  try {
    var r = await api('/api/project/open', {
      method: 'POST',
      body: JSON.stringify({path: projectDir})
    });
    if (r && r.ok) {
      showToast('已切换到: ' + (r.title || projectDir), 'success', 2000);
      // 重新加载页面以加载新项目数据
      setTimeout(function() { location.reload(); }, 500);
    } else {
      showToast('切换失败: ' + (r && r.error || '未知错误'), 'error', 3000);
    }
  } catch(e) {
    console.error('switchProject failed:', e);
    showToast('切换项目失败: ' + e.message, 'error', 3000);
  }
}

function toggleProjectPicker(e) {
  if (e) e.stopPropagation();
  const pop = document.getElementById('project-picker');
  pop.classList.toggle('visible');
  if (pop.classList.contains('visible') && typeof loadProjectList === 'function') loadProjectList();
}

// ── Load context panel ──
function loadContextPanel() {
  try {
    var charsEl = document.getElementById('context-chars');
    var sceneEl = document.getElementById('context-scene');
    var adviceEl = document.getElementById('context-advice');
    
    // 获取当前章节的blueprint（结构化蓝图）
    var bp = window._currentBlueprint || (chapters && chapters[currentChapterIndex] && chapters[currentChapterIndex].blueprint) || null;
    
    // 获取当前章节正文
    var editorEl = document.getElementById('editor-content');
    var chapterText = editorEl ? (editorEl.innerText || '') : '';
    
    // 收集所有角色名（从worldSettings）
    var allChars = [];
    if (typeof worldSettings !== 'undefined' && worldSettings.length) {
      worldSettings.forEach(function(s) {
        if (s.group === '角色' || s.group === '角色设定' || (s.key && (s.key.includes('男主') || s.key.includes('女主') || s.key.includes('反派') || s.key.includes('配角')))) {
          // 提取角色名（去掉描述部分）
          var name = s.key.split(/[：:（(]/)[0].replace(/男主|女主|反派|配角/g, '').trim();
          if (name) allChars.push({name: name, key: s.key, val: s.val || ''});
        }
      });
    }
    
    // ===== 本章角色：从正文中扫描出场角色 =====
    var charDetails = [];
    if (bp && bp.development) {
      // blueprint有角色信息时优先使用
      var charSet = {};
      bp.development.forEach(function(dev) {
        if (dev.characters && Array.isArray(dev.characters)) {
          dev.characters.forEach(function(c) {
            if (c && !charSet[c]) { charSet[c] = true; charDetails.push(c); }
          });
        }
      });
    }
    // blueprint没有角色信息时，从正文扫描
    if (charDetails.length === 0 && chapterText.length > 50) {
      allChars.forEach(function(ch) {
        // 在正文中查找角色名
        if (chapterText.indexOf(ch.name) >= 0) {
          var desc = ch.val ? ch.val.substring(0, 40) : '';
          charDetails.push(ch.name + (desc ? '：' + desc + '...' : ''));
        }
      });
    }
    // 如果正文也没匹配到，回退到全局角色列表（最多5个）
    if (charDetails.length === 0) {
      allChars.slice(0, 5).forEach(function(ch) {
        charDetails.push(ch.key + '：' + (ch.val ? ch.val.substring(0, 30) : '') + '...');
      });
    }
    
    if (charsEl) {
      charsEl.innerHTML = charDetails.length ? '<ul style="margin:0;padding-left:16px;font-size:12px">' + charDetails.map(function(c) { return '<li>' + c + '</li>'; }).join('') + '</ul>' : '<p class="text-md text-muted">暂无角色数据</p>';
    }
    
    // ===== 本章场景：从blueprint或正文提取 =====
    if (sceneEl) {
      var sceneParts = [];
      if (bp) {
        if (bp.intro && bp.intro.scene) {
          sceneParts.push('【开场】' + bp.intro.scene);
          if (bp.intro.atmosphere) sceneParts.push('氛围：' + bp.intro.atmosphere);
        }
        if (bp.development) {
          bp.development.forEach(function(dev, i) {
            if (dev.scene || dev.location) {
              sceneParts.push('【场景' + (i+1) + '】' + (dev.location || '') + (dev.scene ? ' - ' + dev.scene : ''));
            }
          });
        }
        if (bp.climax && bp.climax.conflict) {
          sceneParts.push('【高潮】' + bp.climax.conflict);
        }
      }
      // 回退：从章节大纲提取场景信息
      if (sceneParts.length === 0 && chOutline && chOutline.length > 0) {
        chOutline.forEach(function(item, i) {
          if (item.text) sceneParts.push('• ' + item.text.substring(0, 60));
        });
      }
      // 再回退：显示全局世界观
      if (sceneParts.length === 0 && typeof worldSettings !== 'undefined' && worldSettings.length) {
        var scene = worldSettings.find(function(s) { return s.key === '世界观'; });
        if (scene) sceneParts.push(scene.val);
      }
      sceneEl.innerHTML = sceneParts.length ? sceneParts.join('<br>') : '<span class="text-muted">暂无场景数据</span>';
    }
    
    // ===== 写作建议：从blueprint或章节大纲提取 =====
    if (adviceEl) {
      var adviceItems = [];
      if (bp) {
        if (bp.intro && bp.intro.trigger) adviceItems.push('触发事件：' + bp.intro.trigger);
        if (bp.development) {
          bp.development.forEach(function(dev) {
            if (dev.event) adviceItems.push(dev.event);
            if (dev.choice) adviceItems.push('选择：' + dev.choice);
          });
        }
        if (bp.climax) {
          if (bp.climax.conflict) adviceItems.push('核心冲突：' + bp.climax.conflict);
          if (bp.climax.twist) adviceItems.push('转折：' + bp.climax.twist);
        }
        if (bp.ending) {
          if (bp.ending.new_state) adviceItems.push('新状态：' + bp.ending.new_state);
          if (bp.ending.next_hook) adviceItems.push('下章钩子：' + bp.ending.next_hook);
        }
      }
      // 回退1：从章节大纲提取
      if (adviceItems.length === 0 && chOutline && chOutline.length > 0) {
        chOutline.forEach(function(item) {
          if (item.text) adviceItems.push(item.text);
        });
      }
      // 回退2：从全书大纲匹配当前章节
      if (adviceItems.length === 0 && typeof novelActs !== 'undefined' && novelActs.length > 0 && typeof chapters !== 'undefined' && chapters.length > 0) {
        var chIdx = currentChapterIndex || 0;
        var chTitle = chapters[chIdx] ? chapters[chIdx].title : '';
        var chNum = (chTitle.match(/(\d+)/) || [])[1];
        if (chNum) {
          novelActs.forEach(function(act) {
            if (act.range && act.range.indexOf(chNum) >= 0) {
              act.events.forEach(function(ev) { adviceItems.push(ev.text); });
            }
          });
        }
        // 如果没匹配到，取所有幕的事件作为参考（最多5个）
        if (adviceItems.length === 0) {
          novelActs.forEach(function(act) {
            act.events.forEach(function(ev) { adviceItems.push(ev.text); });
          });
        }
      }
      if (adviceItems.length > 0) {
        adviceEl.innerHTML = '<ul style="margin:0;padding-left:16px;font-size:12px">' + adviceItems.slice(0, 6).map(function(a) { return '<li>' + a + '</li>'; }).join('') + '</ul>';
      } else {
        adviceEl.innerHTML = '<p class="text-md text-muted">完成设定和大纲后，此处将显示本章写作建议</p>';
      }
    }
  } catch(e) { console.error('loadContext error:', e); }
}