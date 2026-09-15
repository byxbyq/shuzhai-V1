(function() {
  'use strict';


window.goToStep = async function(step) {
  if (step < 1 || step > TOTAL_STEPS) return;

  // ═══ 阶段一7：步骤顺序强制校验 ═══
  // 进入写作、时间线、草稿定稿前，必须先完成连线框的布局
  // —— 不能允许跳过连线框直接写正文或定稿，这是因果链检查的核心卡口
  var _REQUIRE_WIREFRAME_BEFORE = [STEPS.写作, STEPS.时间线, STEPS.草稿定稿];
  if (_REQUIRE_WIREFRAME_BEFORE.indexOf(step) >= 0 && typeof api === 'function') {
    var _pc_ok = null;
    // 优先用缓存（最新一次拉取结果）
    if (window._workflowStepCache && typeof window._workflowStepCache.planning_cards_ready === 'boolean') {
      _pc_ok = window._workflowStepCache.planning_cards_ready;
    }
    if (_pc_ok === null) {
      try {
        var _st = await api('/api/project/workflow-step-status', {method: 'GET'});
        if (_st && _st.ok && _st.data) {
          window._workflowStepCache = _st.data;
          _pc_ok = !!_st.data.planning_cards_ready;
        }
      } catch(e) { console.warn('[goToStep] 拉取步骤状态失败，保守放行：', e); _pc_ok = true; }
    }
    if (_pc_ok === false) {
      var _whichName = STEPS._nameOf[step] || step;
      showToast('⚠️ 进入「' + _whichName + '」前必须先完成「连线框」的画布布局（至少拖入1张卡片），已为您自动跳转到连线框。', 'warning', 10000);
      // 强制拦回连线框（不能允许跳过）
      step = STEPS.连线框;
    }
  }

  // 离开当前步骤时，强制保存对应数据（避免编辑内容丢失）
  if (currentWorkflowStep !== step) {
    if (currentWorkflowStep === STEPS.世界观) {
      // 如果AI提取文本框有内容，先自动触发AI提取
      var extractInput = document.getElementById('ai-extract-input');
      if (extractInput && extractInput.value.trim()) {
        console.log('[工作流] 离开步骤1，检测到AI提取输入框有内容，自动触发提取...');
        try {
          var extractData = await api('/api/ai/analyze-content', {
            method: 'POST',
            body: JSON.stringify({ content: extractInput.value.trim() })
          });
          if (extractData && extractData.ok && extractData.settings) {
            var extracted = [];
            Object.entries(extractData.settings).forEach(function([key, val]) {
              if (val && typeof val === 'string') {
                extracted.push({key: key, val: val, group: '世界观'});
              }
            });
            if (extracted.length >= 1 && typeof worldSettings !== 'undefined') {
              var existingKeys = {};
              worldSettings.forEach(function(s) { existingKeys[s.key + '|' + s.group] = true; });
              extracted.forEach(function(item) {
                var k = item.key + '|' + item.group;
                if (!existingKeys[k]) { worldSettings.push(item); existingKeys[k] = true; }
              });
            }
            if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
            showToast('AI自动提取完成，已提取 ' + extracted.length + ' 项设定');
          }
        } catch(e) { console.warn('[工作流] AI自动提取失败:', e); }
      }
      // 保存世界观设定
      if (typeof saveWorldMeta === 'function') {
        await saveWorldMeta();
      }
    }
    if (currentWorkflowStep === STEPS.章节大纲 && typeof saveChapterOutline === 'function' && typeof chOutline !== 'undefined') {
      try { await saveChapterOutline(true); } catch(e) { console.warn('save outline on leave step5:', e); }
    }
    // ═══ 章节大纲→写作时：检查当前卷大纲是否全部完成，触发30维全书检查 ═══
    if (currentWorkflowStep === STEPS.章节大纲 && step >= STEPS.写作) {
      (function() {
        // 检查当前卷的章节是否都有大纲
        var allHaveOutline = true;
        var currentVolChapters = [];
        try {
          if (typeof volumes !== 'undefined' && volumes && volumes.length > 0) {
            // 找到当前章节所在的卷
            var chNum = (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0) + 1;
            var curVol = null;
            for (var vi = 0; vi < volumes.length; vi++) {
              var vc = volumes[vi].chapters || [];
              if (vc.indexOf(chNum) >= 0 || (vc.length && vc[0] <= chNum && chNum <= vc[vc.length-1])) {
                curVol = volumes[vi]; break;
              }
            }
            if (curVol) {
              var volChapters = curVol.chapters || [];
              for (var ci = 0; ci < volChapters.length; ci++) {
                var chIdx = volChapters[ci] - 1;
                if (chIdx >= 0 && typeof chapters !== 'undefined' && chapters[chIdx]) {
                  var hasOl = chapters[chIdx].blueprint || chapters[chIdx].outline;
                  if (!hasOl) { allHaveOutline = false; break; }
                }
              }
            } else {
              // 没有卷结构，检查所有章节
              if (typeof chapters !== 'undefined' && chapters) {
                for (var ci2 = 0; ci2 < chapters.length; ci2++) {
                  if (!chapters[ci2].blueprint && !chapters[ci2].outline) { allHaveOutline = false; break; }
                }
              }
            }
          } else {
            // 没有卷数据，检查所有章节
            if (typeof chapters !== 'undefined' && chapters) {
              for (var ci3 = 0; ci3 < chapters.length; ci3++) {
                if (!chapters[ci3].blueprint && !chapters[ci3].outline) { allHaveOutline = false; break; }
              }
            }
          }
        } catch(e) { console.warn('[工作流] 检查大纲完成状态失败:', e); }

        if (allHaveOutline && typeof chapters !== 'undefined' && chapters && chapters.length > 0) {
          console.log('[工作流] 章节大纲已全部完成，自动触发30维全书检查...');
          showToast('📊 章节大纲已完成，正在自动进行30维全书检查...');
          api('/api/validate/project-review', {
            method: 'POST',
            body: JSON.stringify({})
          }).then(function(reviewResult) {
            if (reviewResult && reviewResult.ok) {
              window._lastProjectReview = reviewResult;
              var issueCount = 0;
              var cats = ['outline_quality', 'settings_quality', 'characters_quality'];
              var catNames = {outline_quality: '大纲', settings_quality: '设定', characters_quality: '人物'};
              var parts = [];
              cats.forEach(function(cat) {
                if (reviewResult[cat] && reviewResult[cat].dimensions) {
                  var total = 0, cnt = 0;
                  reviewResult[cat].dimensions.forEach(function(dim) {
                    total += (dim.score || 0); cnt++;
                    if ((dim.score || 5) <= 4) issueCount++;
                  });
                  parts.push(catNames[cat] + ':' + (cnt > 0 ? (total/cnt).toFixed(1) : 0) + '分');
                }
              });
              if (issueCount > 0) {
                showToast('30维检查完成，发现 ' + issueCount + ' 个低分项，' + parts.join(' | '), 'warning', 8000);
              } else {
                showToast('30维检查完成！' + parts.join(' | '), 'success', 5000);
              }
              if (typeof CheckPanel !== 'undefined' && CheckPanel.showProjectReview) {
                CheckPanel.showProjectReview(reviewResult);
              }
            }
          }).catch(function(e) { console.warn('[工作流] 30维检查失败:', e); });
        }
      })();
    }
    if (currentWorkflowStep === STEPS.写作) {
      // 离开步骤6时，currentChapterIndex 可能已被其他流程提前修改（如生成下一章大纲），
      // 直接使用全局变量会导致旧章节正文串写到新章节。这里显式记录旧的索引。
      // P0: 如果 _skipAutoSaveOnLeaveStep6 标志为 true，说明 generateNextChapterOutline 已自行保存，
      // 跳过自动保存以避免把旧章节正文串写到新章节
      if (window._skipAutoSaveOnLeaveStep6) {
        console.log('[goToStep] 跳过步骤6自动保存（generateNextChapterOutline 已处理）');
      } else {
        var leavingIdx = currentChapterIndex;
        try {
          var leavingEd = document.getElementById('editor-content');
          var leavingContent = leavingEd ? (leavingEd.innerText || '') : '';
          if (leavingIdx >= 0 && chapters && chapters[leavingIdx] && leavingContent.trim()) {
            await saveChapter(leavingIdx, leavingContent);
            chapters[leavingIdx].content = leavingContent;
          }
        } catch(e) { console.warn('autoSave on leave step6 failed:', e); }
      }
    }
  }
  // ═══ E连线框UI引导：关键节点弹窗 ═══
  // 指引①：章节大纲→写作（细纲完成即将写作），建议先布局连线框
  if (currentWorkflowStep === STEPS.章节大纲 && step === STEPS.写作) {
    try { showWireframeGuide('pre-write'); } catch(e) {}
  }
  // 指引②：时间线→连线框或草稿定稿，建议进入草稿定稿
  if (currentWorkflowStep === STEPS.时间线 && (step === STEPS.连线框 || step === STEPS.草稿定稿)) {
    try { showWireframeGuide('post-timeline'); } catch(e) {}
  }

  currentWorkflowStep = step;
  window.goToStep = goToStep; // 立即暴露到全局，避免后续代码出错导致未定义
  window._goToStepReal = goToStep; // 保存真实引用，防止 fallback 循环
  // 保存当前步骤到localStorage，刷新后恢复
  try { localStorage.setItem('shuzhai_last_step', step); } catch(e) {}

  // ══════════════════════════════════════════════════════════
  // 阶段一6：修UI状态一致性——步骤圈绿色对勾必须以对应表实际有数据为准（不能乱勾/不能按顺序无脑勾）
  // 真实数据来自后端 /api/project/workflow-step-status，对应9步（见 step-constants.js）：世界观/人物/全书大纲/分卷/章节大纲/连线框/写作/时间线/草稿定稿
  // ══════════════════════════════════════════════════════════
  function _renderStepIndicatorByRealData(currentStep, realStepsObj) {
    realStepsObj = realStepsObj || {};
    var stepMap = realStepsObj.steps || {};
    document.querySelectorAll('.step-item').forEach(function(item) {
      var s = parseInt(item.dataset.step);
      item.classList.remove('active', 'completed');
      var circle = item.querySelector('.step-circle');
      // 当前步骤：高亮active
      if (s === currentStep) {
        item.classList.add('active');
        if (circle) circle.textContent = String(s);
        return;
      }
      // 其他步骤：必须 realStepsObj.steps[s] === true（对应表有实际数据）才打绿色✓
      // —— 再也不用 s < currentStep 这种"凭感觉乱勾"的逻辑了
      if (stepMap[s] === true) {
        item.classList.add('completed');
        if (circle) circle.textContent = '✓';
      } else {
        if (circle) circle.textContent = String(s);
      }
    });
  }

  // ① 同步：先用缓存（上一次拉的真实状态）立刻渲染，用户不需要等
  _renderStepIndicatorByRealData(step, window._workflowStepCache || null);

  // ② 异步：立刻拉一次后端最新真实数据，刷新缓存 + 重新渲染UI（保证对勾永远最新）
  if (typeof api === 'function') {
    try {
      api('/api/project/workflow-step-status', {method: 'GET'}).then(function(_st) {
        if (_st && _st.ok && _st.data) {
          window._workflowStepCache = _st.data;
          // 注意：第二个参数用的是当前步骤 currentWorkflowStep（已经=step），避免用户又点了另一步导致高亮不一致
          _renderStepIndicatorByRealData(currentWorkflowStep, _st.data);
          // 同时同步到 workflowState.stepStatus（按真实数据写status，供其它模块读）
          if (typeof workflowState !== 'undefined' && workflowState && workflowState.stepStatus) {
            var _status = _st.data.steps || {};
            var _keys = Object.keys(_status);
            for (var _k = 0; _k < _keys.length; _k++) {
              var _idx = parseInt(_keys[_k]);
              if (!_idx || !workflowState.stepStatus[_idx]) continue;
              workflowState.stepStatus[_idx].status = _status[_idx] ? 'completed' :
                (_idx === currentWorkflowStep ? 'in-progress' : 'locked');
            }
          }
        }
      }).catch(function(e) { console.warn('[step-indicator] 异步刷新步骤状态失败：', e); });
    } catch(e) {}
  }

  // 同步 workflowState（允许自由切换，仅记录当前步骤）
  try {
    if (typeof workflowState !== 'undefined' && workflowState) {
      workflowState.currentStep = step;
      if (workflowState.stepStatus && workflowState.stepStatus[step]) {
        workflowState.stepStatus[step].status = 'in-progress';
      }
      // 保存到后端（静默）
      try {
        api('/api/workflow', {method:'POST', body: JSON.stringify(workflowState)});
      } catch(e) {}
    }
  } catch(e) { console.warn('workflowState sync failed:', e); }

  // Switch panel content
  document.querySelectorAll('.left-tab-content').forEach(c => c.classList.remove('active'));
  const panel = document.querySelector('.left-tab-content[data-step="' + step + '"]');
  if (panel) panel.classList.add('active');

  // 右侧面板仅有"记忆"标签，无需切换

  // Trigger renders
  if (step === 1) setTimeout(function() {
    if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
    // 隐藏人物详情面板，恢复详情编辑器默认状态
    var charPanel = document.getElementById('char-detail-panel');
    if (charPanel) charPanel.style.display = 'none';
    // AI提取区域始终显示（方便用户随时补充分析）
    var extractBox = document.getElementById('ai-extract-box');
    if (extractBox) {
      extractBox.style.display = 'block';
    }
    // ── 绑定三个结构化卡片点击→显示到中间详情编辑面板 ──
    function _collectStructuredWorldFields() {
      var fields = [];
      // 叙事风格5字段
      var nsLabels = {'ns-pov':'叙事视角','ns-tense':'时态','ns-tone':'基调','ns-pacing':'节奏','ns-description':'描写风格'};
      for (var nid in nsLabels) { var nel = document.getElementById(nid); if (nel) fields.push({key:nid,label:nsLabels[nid],value:nel.value||'',type:(nel.tagName==='SELECT'?'select':'text'),source:'narrative'}); }
      // 时代环境5字段
      var eraLabels = {'era-tech':'科技水平','era-society':'社会制度','era-geography':'地理特征','era-culture':'文化背景','era-social-attitude':'社会态度'};
      for (var eid in eraLabels) { var eel = document.getElementById(eid); if (eel) fields.push({key:eid,label:eraLabels[eid],value:eel.value||'',type:'text',source:'era'}); }
      // 世界规则列表项
      if (typeof worldMeta !== 'undefined' && worldMeta.world_rules && Array.isArray(worldMeta.world_rules)) {
        worldMeta.world_rules.forEach(function(r, idx) {
          fields.push({key:'rule_'+idx,label:'世界规则 '+(idx+1),value:r.content||r||'',type:'textarea',source:'rules'});
        });
      }
      return fields;
    }
    var narBox = document.getElementById('world-meta-narrative');
    if (narBox && !narBox._bindedDetailClick) {
      narBox._bindedDetailClick = true;
      narBox.style.cursor = 'pointer';
      narBox.addEventListener('click', function(e) {
        if (e.target.closest('button') || e.target.closest('select') || e.target.closest('input')) return;
        var all = _collectStructuredWorldFields();
        var nsF = all.filter(function(x){return x.source==='narrative';});
        showDetailEditor('叙事风格 · 共5项', '✍️ 叙事风格 · 结构化字段', null, {type:'setting-group',group:'叙事风格',fields:nsF});
      });
    }
    var eraBox = document.getElementById('world-meta-era');
    if (eraBox && !eraBox._bindedDetailClick) {
      eraBox._bindedDetailClick = true;
      eraBox.style.cursor = 'pointer';
      eraBox.addEventListener('click', function(e) {
        if (e.target.closest('button') || e.target.closest('input')) return;
        var all = _collectStructuredWorldFields();
        var eF = all.filter(function(x){return x.source==='era';});
        showDetailEditor('时代环境 · 共5项', '🌍 时代环境 · 结构化字段', null, {type:'setting-group',group:'时代环境',fields:eF});
      });
    }
    var ruleBox = document.getElementById('world-meta-rules');
    if (ruleBox && !ruleBox._bindedDetailClick) {
      ruleBox._bindedDetailClick = true;
      ruleBox.style.cursor = 'pointer';
      ruleBox.addEventListener('click', function(e) {
        if (e.target.closest('button') || e.target.closest('input') || e.target.closest('textarea')) return;
        var all = _collectStructuredWorldFields();
        var rF = all.filter(function(x){return x.source==='rules';});
        showDetailEditor('世界规则 · 共'+rF.length+'项', '⚖️ 世界规则 · 列表', null, {type:'setting-group',group:'世界规则',fields:rF.length?rF:[{key:'empty',label:'暂无规则',value:'点击下方「+ 添加规则」按钮添加世界规则',type:'textarea',source:'rules'}]});
      });
    }
  }, 0);
  if (step === STEPS.全书大纲) {
    // 全书大纲：渲染结构化大纲编辑器
    setTimeout(async function() {
      var nvEd = document.getElementById('novel-outline-editor');
      if (nvEd) {
        nvEd.innerHTML = ''; // 清空旧内容重新渲染
        await _renderNovelOutline();
      }
    }, 0);
  }
  if (step === STEPS.人物) {
    // 人物：加载人物列表并显示人物详情面板
    setTimeout(function() {
      if (typeof loadCharacters === 'function') loadCharacters().then(function() { if (typeof renderCharacterList === 'function') renderCharacterList(); }); else if (typeof renderCharacterList === 'function') renderCharacterList();
      // 显示人物详情面板
      var charPanel = document.getElementById('char-detail-panel');
      var emptyEl = document.getElementById('detail-editor-empty');
      var headerEl = document.getElementById('detail-editor-header');
      if (charPanel) charPanel.style.display = 'block';
      if (emptyEl) emptyEl.style.display = 'none';
      if (headerEl) headerEl.classList.add('hidden');
    }, 0);
  }
  if (step === 4) {
    // 步骤4=分卷纲要
    setTimeout(async function() {
      // 隐藏人物详情面板
      var charPanel = document.getElementById('char-detail-panel');
      if (charPanel) charPanel.style.display = 'none';
      // 隐藏详情编辑器默认元素
      var detailEmpty = document.getElementById('detail-editor-empty');
      var detailHeader = document.getElementById('detail-editor-header');
      var detailTextarea = document.getElementById('detail-editor-textarea');
      if (detailEmpty) detailEmpty.style.display = 'none';
      if (detailHeader) detailHeader.classList.add('hidden');
      if (detailTextarea) detailTextarea.classList.add('hidden');
      // 显示分卷详情面板
      var volPanel = document.getElementById('vol-detail-panel');
      if (volPanel) volPanel.style.display = 'block';
      // 确保 _novelOutlineDict 已加载（用于空状态下AI分卷按钮判断）
      if (typeof _novelOutlineDict === 'undefined' || !_novelOutlineDict || Object.keys(_novelOutlineDict).length === 0) {
        try {
          var nloData = await api('/api/project/novel-outline');
          if (nloData.ok && nloData.novel_outline) {
            _novelOutlineDict = nloData.novel_outline;
          }
        } catch(e) {}
      }
      await loadVolumesData();
      renderVolumeOutlineList();
      _currentVolumeEditIndex = -1;
      // 显示空状态提示
      var volEmpty = document.getElementById('vol-detail-empty');
      var volForm = document.getElementById('vol-detail-form');
      if (volEmpty) volEmpty.style.display = 'block';
      if (volForm) volForm.style.display = 'none';
    }, 0);
  }
  if (step === 5) {
    // 步骤5=章节大纲
    setTimeout(function() {
      // 隐藏人物详情面板
      var charPanel = document.getElementById('char-detail-panel');
      if (charPanel) charPanel.style.display = 'none';
      loadChapterOutline(currentChapterIndex);
      loadVolumesData().then(function() { loadChapterVolumeOutline(); });
      if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
      renderChapterDropdown('chapter-dropdown-outline', currentChapterIndex, function(idx) {
        loadChapterOutline(idx);  // 内部会保存旧章节并设置currentChapterIndex
        currentChapterIndex = idx;
        loadChapterVolumeOutline();
        renderChapterOutlineEditor();
        loadForeshadows();
        if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
        // 流水线联动：正文生成后触发票据更新（deferred to avoid blocking）
        try { fetch('/api/generate/extract-state', { method: 'POST', body: JSON.stringify({ content: '', chapter_idx: currentChapterIndex + 1, title: (chapters && chapters[currentChapterIndex]) ? chapters[currentChapterIndex].title : '' }) }).catch(function(){}); } catch(e2) {}
      });
      // 加载伏笔
      loadForeshadows();
    }, 0);
  }
  if (step === STEPS.写作) {
    // 写作步骤 - 显示编辑器
    setTimeout(function() { if (typeof updateWritingToolbar === 'function') updateWritingToolbar(); }, 0);
  }
  if (step === STEPS.时间线) {
    // 时间线 - 先加载时间线数据，再渲染左侧章节列表
    setTimeout(function() {
      var tlLoad = (typeof Timeline !== 'undefined' && Timeline.load) ? Timeline.load() : Promise.resolve({ok: false});
      tlLoad.then(function(tlRes) {
        if (!tlRes || !tlRes.ok) {
          console.warn('[goToStep 时间线] Timeline.load failed, left nav may be incomplete');
        }
        // 渲染章节列表到左抽屉，并从实际内容文件获取字数
        loadVolumesData().then(function() {
          // 从时间线API获取 has_content 状态，从章节API获取实际字数
          var timelineHasContent = {};
          api('/api/timeline').then(function(tlRes2) {
            if (tlRes2 && tlRes2.chapters) {
              for (var k in tlRes2.chapters) {
                timelineHasContent[k] = tlRes2.chapters[k].has_content || false;
              }
            }
          }).catch(function(){});
          var wordPromises = (chapters || []).map(function(ch, i) {
            return api('/api/chapter/load?index=' + i + '&_t=' + Date.now()).then(function(res) {
              chapters[i]._actual_words = (res && res.ok && res.content && res.content.trim()) ? (res.word_count || 0) : 0;
              chapters[i]._has_content = !!(res && res.ok && res.content && res.content.trim().length > 100);
            }).catch(function() {
              chapters[i]._actual_words = 0;
              chapters[i]._has_content = false;
            });
          });
          Promise.all(wordPromises).then(function() {
            renderVolumeNav('vol-nav-timeline', function(idx) {
              syncChapterAcrossPanels(idx);
            });
            // 默认选中当前章节
            if (typeof currentChapterIndex !== 'undefined' && currentChapterIndex >= 0) {
              syncChapterAcrossPanels(currentChapterIndex);
            }
          });
        });
      });
    }, 0);
    // 时间线步骤：隐藏右侧抽屉
    var rightDrawer = document.querySelector('.right-drawer');
    if (rightDrawer) rightDrawer.style.display = 'none';
  } else {
    // 非时间线步骤：显示右侧抽屉
    var rightDrawer = document.querySelector('.right-drawer');
    if (rightDrawer) rightDrawer.style.display = 'flex';
  }
  // 时间线模式：时间线步骤时使用编辑器区域显示全屏时间线
  var mainEl = document.querySelector('.main');
  if (mainEl) {
    if (step === STEPS.时间线) {
      mainEl.classList.add('timeline-mode');
    } else {
      mainEl.classList.remove('timeline-mode');
    }
  }
  // Toggle editor mode: writing (写作) vs detail editor (其他步骤) vs timeline (时间线)
  var editorPaper = document.getElementById('editor-paper');
  var detailPanel = document.getElementById('detail-editor-panel');
  var timelineFullEditor = document.getElementById('timeline-full-editor');
  if (editorPaper && detailPanel) {
    if (step === STEPS.写作) {
      editorPaper.style.display = 'block';
      detailPanel.classList.remove('active');
      if (timelineFullEditor) timelineFullEditor.style.display = 'none';
    } else if (step === STEPS.时间线) {
      editorPaper.style.display = 'none';
      detailPanel.classList.remove('active');
      if (timelineFullEditor) timelineFullEditor.style.display = 'flex';
    } else {
      editorPaper.style.display = 'none';
      detailPanel.classList.add('active');
      if (timelineFullEditor) timelineFullEditor.style.display = 'none';
      // Reset detail editor to empty state
      if (step !== STEPS.时间线) showDetailEditorEmpty();
    }
  }

  // Toggle writing toolbar (仅写作步骤显示)
  var wt = document.getElementById('writing-toolbar');
  if (wt) wt.style.display = (step === STEPS.写作) ? 'flex' : 'none';

  if (step === STEPS.写作) {
    setTimeout(async function() {
      // 确保章节数据已加载
      if (typeof loadChaptersFromAPI === 'function') {
        try { await loadChaptersFromAPI(); } catch(e2) { console.warn('loadChapters failed:', e2); }
      }
      if (typeof renderChapterMiniList === 'function') renderChapterMiniList();
      // 加载卷数据并渲染卷导航
      loadVolumesData().then(function() {
        renderVolumeNav('vol-nav-writing', async function(idx) {
          syncChapterAcrossPanels(idx);
          if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
        });
      });
      // Auto-load current chapter content into editor
      if (typeof loadChapterContentAPI === 'function' && currentChapterIndex >= 0) {
        loadChapterContentAPI(currentChapterIndex);
      }
      // 写作步骤自动展开右侧面板（检查面板）
      var rightDrawer = document.querySelector('.right-drawer');
      if (rightDrawer && rightDrawer.classList.contains('collapsed')) {
        rightDrawer.classList.remove('collapsed');
      }
      // 检查标签已移除，无需切换
      // Bind writing toolbar buttons
      var wtGen = document.getElementById('wt-btn-gen');
      var wtSave = document.getElementById('wt-btn-save');
      if (wtGen) wtGen.onclick = function() { document.getElementById('btn-ai-gen')?.click(); };
      if (wtSave) wtSave.onclick = function() { document.getElementById('btn-save')?.click(); };
      var wtFlavor = document.getElementById('wt-btn-flavor');
      if (wtFlavor) wtFlavor.onclick = async function() {
        var el = document.getElementById('editor-content');
        if (!el || !(el.innerText || '').trim()) { showToast('没有内容可检测'); return; }
        var origText = this.textContent;
        this.disabled = true; this.textContent = '⏳ 检测中…';
        try {
          var content = el.innerText || '';
          var result = (typeof AuditJS !== 'undefined' && AuditJS.detectAiFlavor) ? AuditJS.detectAiFlavor(content) : null;
          if (result && result.score !== undefined) {
            showToast('AI味评分: ' + result.score + '/100 ' + (result.summary || ''));
          } else { showToast('检测完成'); }
        } catch(e) { console.error(e); showToast('检测出错'); }
        this.disabled = false; this.textContent = origText;
      };
      // Update toolbar info
      updateWritingToolbar();
      // 写作步骤时，如果正文为空，在编辑器下方显示大纲参考
      setTimeout(function() {
        var editorEl = document.getElementById('editor-content');
        var editorTitle = document.getElementById('editor-title');
        if (editorEl && (!editorEl.innerText || editorEl.innerText.trim().length < 10)) {
          // 正文为空，显示大纲参考
          var ch = chapters[currentChapterIndex];
          if (ch && ch.outline) {
            var outlineHtml = '<div style="padding:20px;background:var(--bg);border-radius:8px;margin:20px 0;">';
            outlineHtml += '<h3 style="color:var(--accent);margin-bottom:10px;">📋 本章大纲（参考）</h3>';
            outlineHtml += '<div style="color:var(--muted);font-size:13px;line-height:1.8;">';
            var outlineText = typeof ch.outline === 'string' ? ch.outline : ch.outline.map(function(o){return o.text||o;}).join('\n');
            outlineHtml += outlineText.replace(/\n/g, '<br>');
            outlineHtml += '</div></div>';
            editorEl.innerHTML = outlineHtml;
            if (editorTitle) editorTitle.textContent = ch.title || ('第' + (currentChapterIndex + 1) + '章');
          }
        }
      }, 500);
    }, 0);
  }
}

})();