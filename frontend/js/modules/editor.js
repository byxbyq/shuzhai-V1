// Extracted from app.js - 章节编辑器 (loadChaptersFromAPI, autoSaveBeforeChapterSwitch, loadChapterContentAPI)
async function loadChaptersFromAPI() {
  try {
    const r = await getChapterList();
    if (r.ok && r.chapters) {
      if (typeof chapters === 'undefined') window.chapters = [];
      chapters = r.chapters;
      if (typeof renderChapterList === 'function') renderChapterList();
    }
  } catch(e) { console.warn('loadChapters', e); }
}

// P0-1: 切章前自动保存当前蓝图/正文/大纲
async function autoSaveBeforeChapterSwitch() {
  try {
    // 先 flush 防抖保存，确保待保存的数据落盘
    if (window.ShuZhai && ShuZhai.autoSave && typeof ShuZhai.autoSave.flushAutoSave === 'function') {
      try { await ShuZhai.autoSave.flushAutoSave(); } catch(e) { console.warn('flushAutoSave failed:', e); }
    }
    // 草稿模式下阻止自动保存成品，提示用户先处理草稿
    if (window.DraftManager && DraftManager.isActive()) {
      if (typeof showToast === 'function') showToast('⚠️ 有未确认草稿，请先采纳或丢弃');
      return false;
    }
    if (currentChapterIndex < 0 || !chapters || !chapters[currentChapterIndex]) return;
    var idx = currentChapterIndex;
    // 保存章节大纲和蓝图（必须传immediate=true，否则防抖回调会在currentChapterIndex更新后执行，导致大纲保存到错误的章节）
    if (typeof saveChapterOutline === 'function' && typeof chOutline !== 'undefined') {
      try { saveChapterOutline(true); } catch(e) { console.warn('autoSave outline failed:', e); }
    }
    // 保存正文（如果编辑器有内容且与已存不同）
    var editorEl = document.getElementById('editor-content');
    if (editorEl) {
      var content = editorEl.innerText || '';
      if (content.trim() && chapters[idx] && chapters[idx].content !== content) {
        try {
          await saveChapter(idx, content);
          chapters[idx].content = content;
        } catch(e) { console.warn('autoSave content failed:', e); }
      }
    }
    // P1-7: 清理切章时的临时建议
    window._aiSuggestions = null;
  } catch(e) {
    console.warn('autoSaveBeforeChapterSwitch error:', e);
  }
}

// Load chapter content on select
async function loadChapterContentAPI(index) {
  // 草稿模式下阻止切章
  if (window.DraftManager && DraftManager.isActive()) {
    var action = confirm('当前章节有未确认的草稿。\n\n点击"确定"丢弃草稿并切换章节\n点击"取消"留在当前章节');
    if (!action) return;
    DraftManager.forceExit();
  }
  // 借鉴 inkos 设计：OperationContext 冲突检测
  // 如果有活跃的异步AI操作正在进行（如AI修复、生成正文），阻止切章
  if (window.OperationContext && OperationContext.hasActiveWrite()) {
    var ctx = OperationContext.getActive();
    var action2 = confirm(
      '当前正在进行「' + ctx.operation + '」（第' + (ctx.chapterIndex + 1) + '章）。\n\n' +
      '切换章节可能导致AI操作结果保存到错误的章节！\n\n' +
      '点击"确定"强制切换（可能丢失AI结果）\n' +
      '点击"取消"等待操作完成'
    );
    if (!action2) return;
    // 用户选择强制切换，释放操作上下文
    OperationContext.release(ctx);
  }
  // P0-1: 切章前自动保存
  if (index !== currentChapterIndex) {
    await autoSaveBeforeChapterSwitch();
  }
  // 更新当前章节索引
  currentChapterIndex = index;
  // 书架首页：记住本书写到的章节（供"继续写"恢复）
  if (window.Reader && typeof Reader.rememberWriteChapter === 'function') {
    Reader.rememberWriteChapter(index);
  }
  // Fix 3: 跨章节上下文校验 — 清空旧检查结果对象和UI
  if (typeof lastValResult !== 'undefined' && lastValResult && lastValResult.chapterIndex !== index) {
    lastValResult = null;
    var vDiv3 = document.getElementById('val-results');
    if (vDiv3) vDiv3.innerHTML = '<div class="val-empty-hint" style="padding:12px;color:var(--muted);font-size:12px;text-align:center">点击上方检查按钮或AI责编按钮，结果将在这里显示并保留</div>';
  }
  try {
    const r = await selectChapter(index);
    if (r.ok) {
      document.getElementById('editor-title').textContent = r.title || ('第' + (index + 1) + '章');
      document.getElementById('editor-content').innerHTML = textToHTML(r.content || '');
      document.getElementById('word-count').textContent = (r.word_count || 0).toLocaleString('zh-CN');
      // 更新写作工具栏
      if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
      // 更新定稿按钮状态
      var lockBtn = document.getElementById('btn-chapter-lock');
      if (lockBtn && typeof chapters !== 'undefined' && chapters[index]) {
        if (chapters[index].locked === true) {
          lockBtn.textContent = '🔓 解锁';
          lockBtn.style.background = 'rgba(231,76,60,0.1)';
        } else {
          lockBtn.textContent = '🔒 暂锁草稿';
          lockBtn.style.background = 'rgba(108,92,231,0.05)';
        }
      }
      
      // 加载章节大纲
      if (r.outline) {
        // 如果outline是JSON格式，用正则提取关键字段（避免JSON解析失败）
        var isJsonOutline = (window.JsonParser && JsonParser.isJsonFormat) ? JsonParser.isJsonFormat(r.outline)
          : (r.outline.trim().startsWith('```json') || r.outline.trim().startsWith('{'));
        if (isJsonOutline) {
          // 使用统一的 JSON 解析工具（任务4：去重）
          if (window.JsonParser && JsonParser.extractOutlineFromJSON) {
            chOutline = JsonParser.extractOutlineFromJSON(r.outline);
          } else {
            // fallback: 内联实现（兼容未加载 utils 的情况）
            var textLinesFb = [];
            function _ef(text, field) {
              var pat = '"' + field + '"\\s*:\\s*"([^"]*(?:\\\\.[^"]*)*)"';
              var ms = [], re = new RegExp(pat, 'g'), m;
              while ((m = re.exec(text)) !== null) ms.push(m[1].replace(/\\"/g, '"').replace(/\\n/g, ' '));
              return ms;
            }
            var sc = _ef(r.outline, 'scene'), at = _ef(r.outline, 'atmosphere');
            var tr = _ef(r.outline, 'trigger'), ev = _ef(r.outline, 'event');
            var cf = _ef(r.outline, 'conflict'), tw = _ef(r.outline, 'twist');
            var ns = _ef(r.outline, 'new_state'), nh = _ef(r.outline, 'next_hook');
            if (sc.length > 0) textLinesFb.push('【起】' + sc[0]);
            if (at.length > 0) textLinesFb.push('氛围：' + at[0]);
            if (tr.length > 0) textLinesFb.push('触发：' + tr[0]);
            ev.forEach(function(e, i) { if (e) textLinesFb.push('【承' + (i+1) + '】' + e); });
            if (cf.length > 0) textLinesFb.push('【转】' + cf[0]);
            if (tw.length > 0) textLinesFb.push('转折：' + tw[0]);
            if (ns.length > 0) textLinesFb.push('【合】' + ns[0]);
            if (nh.length > 0) textLinesFb.push('钩子：' + nh[0]);
            if (textLinesFb.length > 0) {
              chOutline = textLinesFb.map(function(l, i) { return {text: l.trim(), current: i === 0, source: 'parsed'}; });
            } else {
              var rawL = r.outline.split('\n').filter(function(l) {
                var t = l.trim();
                return t && !t.startsWith('"') && !t.startsWith('{') && !t.startsWith('}') && !t.startsWith('[') && !t.startsWith(']') && !t.startsWith('```');
              });
              chOutline = rawL.map(function(l, i) { return {text: l.trim(), current: i === 0, source: 'saved'}; });
            }
          }
        } else {
          // 普通文本大纲
          var lines = r.outline.split('\n').filter(function(l) { return l.trim(); });
          chOutline = lines.map(function(l, i) {
            return {text: l.trim(), current: i === 0, source: 'saved'};
          });
        }
      } else {
        // 没有保存的大纲，尝试从全书大纲中提取对应章节的事件
        chOutline = extractOutlineFromNovelActs(index);
      }
      // 恢复结构化蓝图（如果已保存）
      if (r.blueprint) {
        window._currentBlueprint = r.blueprint;
      } else if (chapters && chapters[index] && chapters[index].blueprint) {
        window._currentBlueprint = chapters[index].blueprint;
      } else {
        window._currentBlueprint = null;
      }
      // 如果blueprint为空但outline是JSON格式，用正则提取关键字段
      if (!window._currentBlueprint && r.outline) {
        var isJsonOL = (window.JsonParser && JsonParser.isJsonFormat) ? JsonParser.isJsonFormat(r.outline)
          : (r.outline.trim().startsWith('```json') || r.outline.trim().startsWith('{'));
        if (isJsonOL) {
          // 使用统一的 JSON 解析工具（任务4：去重）
          if (window.JsonParser && JsonParser.parseBlueprintFromJSON) {
            var bp = JsonParser.parseBlueprintFromJSON(r.outline);
            if (bp) {
              window._currentBlueprint = bp;
            }
          } else {
            // fallback: 内联实现（兼容未加载 utils 的情况）
            function _ef2(text, field) {
              var pat = '"' + field + '"\\s*:\\s*"([^"]*(?:\\\\.[^"]*)*)"';
              var ms = [], re = new RegExp(pat, 'g'), m;
              while ((m = re.exec(text)) !== null) ms.push(m[1].replace(/\\"/g, '"').replace(/\\n/g, ' '));
              return ms;
            }
            var bpS = _ef2(r.outline, 'scene'), bpE = _ef2(r.outline, 'event');
            var bpC = _ef2(r.outline, 'characters'), bpCf = _ef2(r.outline, 'conflict');
            var bpT = _ef2(r.outline, 'twist'), bpTr = _ef2(r.outline, 'trigger');
            var bpN = _ef2(r.outline, 'new_state'), bpH = _ef2(r.outline, 'next_hook');
            if (bpS.length > 0 || bpE.length > 0 || bpC.length > 0) {
              var devA = [];
              var mL = Math.max(bpS.length, bpE.length, bpC.length);
              for (var di = 0; di < mL; di++) {
                devA.push({ scene: bpS[di] || '', event: bpE[di] || '', characters: bpC[di] ? [bpC[di]] : [] });
              }
              window._currentBlueprint = {
                intro: {scene: bpS[0] || '', trigger: bpTr[0] || ''},
                development: devA,
                climax: {conflict: bpCf[0] || '', twist: bpT[0] || ''},
                ending: {new_state: bpN[0] || '', next_hook: bpH[0] || ''}
              };
            }
          }
        }
      }
      // 如果当前在章节大纲步骤，刷新编辑器
      if (typeof workflowState !== 'undefined' && currentWorkflowStep === STEPS.章节大纲 && typeof renderChapterOutlineEditor === 'function') {
        renderChapterOutlineEditor();
      }
      
      // 恢复该章节的检查结果
      try {
        var curScope = (document.querySelector('input[name="check-scope"]:checked') || {}).value || 'chapter';
        // 先尝试当前scope，再尝试full，再尝试chapter
        var scopes = [curScope, 'full', 'chapter'];
        var restored = false;
        for (var si = 0; si < scopes.length && !restored; si++) {
          var restoreKey = 'valResults_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + index + '_' + scopes[si];
          var saved = localStorage.getItem(restoreKey);
          if (saved) {
            var savedData = JSON.parse(saved);
            // Fix 4: 校验章节上下文，不匹配则跳过
            if (savedData.chapterIndex !== undefined && savedData.chapterIndex !== index) {
              continue;
            }
            var vDiv = document.getElementById('val-results');
            if (vDiv && savedData.html) {
              vDiv.innerHTML = savedData.html;
              // 不将HTML字符串赋值给lastValResult（类型不兼容），保留null
              restored = true;
              // 恢复问题列表和"一键修复"按钮
              var probsKey = 'valProblems_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + index + '_' + scopes[si];
              var savedProbs = localStorage.getItem(probsKey);
              if (savedProbs) {
                try {
                  window._allValProblems = JSON.parse(savedProbs);
                  // 重新绑定"一键修复"按钮事件（恢复的HTML中onclick可能失效）
                  var fixBtn = vDiv.querySelector('#fix-all-bar button');
                  if (fixBtn) {
                    fixBtn.onclick = function() { valAIFixAll(); };
                  }
                } catch(e2) { /* ignore */ }
              }
              // 恢复scope单选按钮状态
              var scopeRadio = document.querySelector('input[name="check-scope"][value="' + scopes[si] + '"]');
              if (scopeRadio) scopeRadio.checked = true;
            }
          }
        }
      } catch(e) { /* ignore */ }
    }
    // 刷新上下文面板（根据当前章节的blueprint显示本章角色、场景、写作建议）
    if (typeof loadContextPanel === 'function') loadContextPanel();
  } catch(e) { console.error('loadChapter', e); }
}

// extractOutlineFromNovelActs 定义在 init.js 中（函数体过大，属于初始化流程）
