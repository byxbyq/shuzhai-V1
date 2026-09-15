// Extracted from app.js - 检查按钮UI和报告渲染 (setupCheckButtons, showFlavorReport)
// ── 安全事件绑定helper ──
function $on(id, evt, fn) { var el = document.getElementById(id); if (el) el.addEventListener(evt, fn); }
// ── Validation check buttons ──
function setupCheckButtons() {
  const grid = document.getElementById('check-grid');
  if (!grid) {
    // DOM还没加载，延迟重试
    setTimeout(setupCheckButtons, 500);
    return;
  }

  // 动态添加字数检查按钮（M2字数预算）
  if (!grid.querySelector('[data-check="wordcount"]')) {
    var wcBtn = document.createElement('button');
    wcBtn.className = 'check-btn';
    wcBtn.setAttribute('data-check', 'wordcount');
    wcBtn.title = '字数预算检查';
    wcBtn.innerHTML = '<svg class="check-icon" viewBox="0 0 24 24" width="18" height="18" style="stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>字数';
    grid.appendChild(wcBtn);
  }

  // 维度按钮：点击切换选中/取消
  grid.addEventListener('click', function(e) {
    const btn = e.target.closest('.check-btn');
    if (!btn || btn.disabled) return;
    btn.classList.toggle('selected');
  });

  // 默认全选所有检查维度
  grid.querySelectorAll('.check-btn').forEach(function(btn) { btn.classList.add('selected'); });

  // "开始检查"按钮
  const runBtn = document.getElementById('btn-run-checks');
  if (runBtn) {
    runBtn.addEventListener('click', async function() {
      var selectedBtns = grid.querySelectorAll('.check-btn.selected');
      // 如果没有选中维度，默认全选
      if (selectedBtns.length === 0) {
        grid.querySelectorAll('.check-btn').forEach(function(btn) { btn.classList.add('selected'); });
        selectedBtns = grid.querySelectorAll('.check-btn.selected');
      }

      runBtn.disabled = true;
      runBtn.textContent = '⏳ 检查中…';
      runBtn.style.opacity = '0.6';

      const stageMap = {1:'settings',2:'settings',3:'chapter-outline',4:'content'};
      const currentStage = stageMap[(typeof workflowState !== "undefined" ? workflowState.currentStep : 1)] || 'content';

      var scopeRadio = document.querySelector('input[name="check-scope"]:checked');
      var checkScope = scopeRadio ? scopeRadio.value : 'chapter';

      // 构建检查内容
      var checkContent = '', checkIndex = 0;
      if ((typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 4 || (typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 5 || (typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 7) {
        var editorEl = document.getElementById('editor-content');
        checkContent = editorEl ? (editorEl.innerText || '') : '';
        checkIndex = currentChapterIndex >= 0 ? currentChapterIndex : 0;
        
        // 如果编辑器内容为空（步骤7时编辑器可能被隐藏），从后端API加载当前章节
        if (!checkContent || checkContent.trim().length < 50) {
          try {
            var chData = await api('/api/chapter/load?index=' + checkIndex);
            if (chData && chData.content && chData.content.trim().length > 50) {
              checkContent = chData.content;
            }
          } catch(e) { /* ignore */ }
        }
        
        if (checkScope === 'full') {
          // 全文检查：遍历所有有内容的章节
          // 检查结果会对每一章分别显示
          if (typeof chapters !== 'undefined' && chapters && chapters.length > 0) {
            // 收集所有章节内容
            var allChapterContents = [];
            for (var ci = 0; ci < chapters.length; ci++) {
              var chContent = '';
              // 全文检查：始终从后端API加载最新内容，避免内存缓存过期导致检查结果与后端不一致
              try {
                var chLoad = await api('/api/chapter/load?index=' + ci);
                if (chLoad && chLoad.content && chLoad.content.trim().length > 50) {
                  chContent = chLoad.content;
                  // 同步更新内存
                  if (chapters[ci]) { chapters[ci].content = chContent; chapters[ci].word_count = chContent.length; }
                }
              } catch(e) { /* ignore */ }
              // API加载失败时回退到内存
              if ((!chContent || chContent.trim().length < 50) && chapters[ci] && chapters[ci].content) {
                chContent = chapters[ci].content;
              }
              if (chContent && chContent.trim().length >= 50) {
                allChapterContents.push({index: ci, title: (chapters[ci]&&chapters[ci].title)||('第'+(ci+1)+'章'), content: chContent});
              }
            }
            // 如果有多章，拼接所有章节内容作为检查内容
            if (allChapterContents.length > 0) {
              checkContent = allChapterContents.map(function(c) {
                return '【' + c.title + '】\n' + c.content;
              }).join('\n\n---\n\n');
              // 使用第一章作为checkIndex（连贯性检查会用到）
              checkIndex = allChapterContents[0].index;
            }
          }
        }
      } else {
        switch((typeof workflowState !== "undefined" ? workflowState.currentStep : 1)) {
          case 1: checkContent = worldSettings.map(s=>s.key+'：'+s.val).join('\n'); break;
          case 2: checkContent = novelActs.map(a=>a.title+'\n'+a.events.map(e=>'- '+e.text).join('\n')).join('\n\n'); break;
          case 3: 
            // 三级兜底：chapters存档 → chOutline数组 → 编辑器草稿
            // 优先使用已保存的章节大纲（最可靠），编辑器草稿可能有未保存的旧内容
            if (chapters && chapters[currentChapterIndex] && chapters[currentChapterIndex].outline) {
              checkContent = typeof chapters[currentChapterIndex].outline === 'string' 
                ? chapters[currentChapterIndex].outline 
                : chapters[currentChapterIndex].outline.map(function(o) { return o.text || o; }).join('\n');
            } else if (chOutline && chOutline.length > 0) {
              checkContent = chOutline.map(function(o) { return typeof o === 'string' ? o : (o.text || ''); }).join('\n');
            } else {
              var editorEl3 = document.getElementById('editor-content');
              var draftText = editorEl3 ? (editorEl3.innerText || '').trim() : '';
              if (draftText.length > 20) checkContent = draftText;
            }
            if (!checkContent || checkContent.trim().length < 5) {
              showToast && showToast('⚠️ 当前章节内容为空，无法检查');
              runBtn.disabled = false; runBtn.textContent = '🔍 开始检查'; runBtn.style.opacity = '1';
              return;
            }
            break;
        }
      }

      // 最终检查：如果内容仍为空，给出提示（一致性检查除外，它不需要正文）
      // 先收集选中的检查类型
      var selectedTypes = [];
      selectedBtns.forEach(function(btn) {
        var ct = btn.dataset.check;
        selectedTypes.push(ct);
      });
      var isConsistencyOnly = selectedTypes.length === 1 && selectedTypes[0] === 'consistency';
      if (!checkContent || checkContent.trim().length < 50) {
        if (isConsistencyOnly) {
          // 一致性检查阶段1：无正文，只检查设定层
          checkContent = '';
        } else {
          showToast && showToast('⚠️ 当前章节内容为空，无法检查。请先在编辑器中加载或生成章节内容。');
          runBtn.disabled = false; runBtn.textContent = '🔍 开始检查'; runBtn.style.opacity = '1';
          return;
        }
      }

      var memoryContext = '';
      // 全文模式：记忆包含所有章节；单章模式：只含当前章节之前的记忆
      var memCutoff = (checkScope === 'full') ? 999 : (checkIndex + 1);
      if (typeof buildMemoryContext === 'function') memoryContext = await buildMemoryContext(memCutoff);

      // 构建额外上下文（全书大纲、章节大纲、章节索引）
      var checkContext = null;
      if ((typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 3) {
        // 步骤3：章节大纲阶段
        var novelOutlineText = '';
        if (typeof novelActs !== 'undefined' && novelActs.length > 0) {
          novelOutlineText = novelActs.map(function(act) {
            return act.title + '\n' + (act.events||[]).map(function(ev) { return '- ' + (ev&&ev.text?ev.text:String(ev)); }).join('\n');
          }).join('\n\n');
        }
        checkContext = {
          stage: 'chapter-outline',
          novelOutline: novelOutlineText,
          chapterIndex: currentChapterIndex >= 0 ? currentChapterIndex : 0,
          allSettings: typeof worldSettings !== 'undefined' ? worldSettings : []
        };
      } else if ((typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 4 || (typeof workflowState !== "undefined" ? workflowState.currentStep : 1) === 5) {
        // 步骤4/5：正文写作阶段——需要传全书大纲和章节大纲给后端
        var novelOutlineText2 = '';
        if (typeof novelActs !== 'undefined' && novelActs.length > 0) {
          novelOutlineText2 = novelActs.map(function(act) {
            return act.title + '\n' + (act.events||[]).map(function(ev) { return '- ' + (ev&&ev.text?ev.text:String(ev)); }).join('\n');
          }).join('\n\n');
        }
        // 收集所有章节大纲（全文检查需要）
        var allChapterOutlines = [];
        if (typeof chapters !== 'undefined' && chapters && chapters.length > 0) {
          for (var coi = 0; coi < chapters.length; coi++) {
            var ol = chapters[coi] ? chapters[coi].outline : '';
            if (ol && typeof ol === 'string' && ol.trim().length > 5) {
              allChapterOutlines.push('【' + (chapters[coi].title || ('第'+(coi+1)+'章')) + '】\n' + ol);
            } else if (ol && Array.isArray(ol) && ol.length > 0) {
              var olText = ol.map(function(o) { return typeof o === 'string' ? o : (o.text || ''); }).join('\n');
              if (olText.trim().length > 5) {
                allChapterOutlines.push('【' + (chapters[coi].title || ('第'+(coi+1)+'章')) + '】\n' + olText);
              }
            }
          }
        }
        checkContext = {
          stage: 'content',
          novelOutline: novelOutlineText2,
          chapterOutline: allChapterOutlines.join('\n\n'),
          chapterIndex: currentChapterIndex >= 0 ? currentChapterIndex : 0,
          allSettings: typeof worldSettings !== 'undefined' ? worldSettings : []
        };
      }

      const checkMap = {
        drift: checkDrift,
        twist: checkTwist, duplicate: checkDuplicate,
        style: checkStyle, quality: checkQuality,
        memory: checkMemory, conflict: checkConflicts,
        timeline: checkTimeline,
        completeness: checkCompleteness, continuity: checkContinuity,
        consistency: checkConsistency,
        wordcount: checkTwist, // wordcount通过合并检查返回，用占位函数
      };
      const _checkLabels = {drift:'偏差',twist:'转折',duplicate:'重复',style:'风格',conflict:'冲突',timeline:'时间线',quality:'质量',memory:'记忆',completeness:'完整性',continuity:'连贯性',consistency:'一致性',wordcount:'字数预算'};

      var _negIssuePats = ['不一致','不符合','不连贯','不自然','不协调','不合理','不自洽','不匹配','不对齐'];
      var _negPrefixes = ['无明显','没有','不存在','未发现','未检测到','未发现明显','无'];
      var _noIssuePats = ['无矛盾','无冲突','无偏离','无重复','没有重复','不存在重复','无问题','没有问题','没有发现','未发现','未检测到','未发现问题','没有偏离','未检测到问题','无遗漏','没有遗漏','未发现明显','无明显问题','一致','符合','通过','对齐','无异常','正常','衔接正常','数据一致','未发现偏离','未发现冲突','未发现矛盾','未发现重复','未发现遗漏'];
      var _issuePats = ['偏离','矛盾','冲突','断裂','遗漏','缺乏','缺失','生硬','突兀','混乱','错误','需改进','显著','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
      // 评价类检查用更严格的问题词（不含"冲突""矛盾"等情节描述词）
      var _evalIssuePats = ['生硬','突兀','混乱','错误','需改进','断裂','缺乏','缺失','不一致','不符合','不连贯','不自然','不协调','不合理','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
      var _evalTypes = ['twist','style','quality','memory'];
      function judgeValResult(checkType, resultText) {
        if (!resultText) return false;
        resultText = String(resultText).trim();
        if (resultText.startsWith('[错误]') || resultText.includes('生成失败')) return true;

        var issuePatsToUse = _evalTypes.indexOf(checkType) >= 0 ? _evalIssuePats : _issuePats;

        // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
        var tail = resultText.substring(Math.max(0, resultText.length - 80));
        if (tail.includes('结论') || tail.includes('整体评价') || tail.includes('总结')) {
          // 找到最后一个结论关键词位置，只看结论之后的内容
          var conclStart = Math.max(tail.lastIndexOf('结论'), tail.lastIndexOf('整体评价'), tail.lastIndexOf('总结'));
          var conclText = tail.substring(conclStart);
          // 生成全部否定前缀+问题词的无问题模式
          var tailExtra = [];
          for (var te = 0; te < _issuePats.length; te++) {
            for (var np2 = 0; np2 < _negPrefixes.length; np2++) {
              tailExtra.push(_negPrefixes[np2] + _issuePats[te]);
            }
          }
          var tailAllNo = _noIssuePats.concat(tailExtra);
          var tailHasNo = tailAllNo.some(function(p){ return conclText.includes(p); });
          if (tailHasNo) {
            // 清洗结论句
            var cleanedConcl = conclText;
            var sortedConcl = tailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
            sortedConcl.forEach(function(p) { cleanedConcl = cleanedConcl.split(p).join(''); });
            var conclHasIssue = issuePatsToUse.some(function(p){ return cleanedConcl.includes(p); });
            if (!conclHasIssue) return false;
          }
        }

        // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语（如"无明显风格不一致"）
        var negatedText = resultText;
        // 处理一般问题词
        for (var np4 = 0; np4 < _negPrefixes.length; np4++) {
          for (var ip4 = 0; ip4 < issuePatsToUse.length; ip4++) {
            try {
              var escPrefix = _negPrefixes[np4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
              var escIssue = issuePatsToUse[ip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
              var re = new RegExp(escPrefix + '[^，。！？；]{0,6}' + escIssue, 'g');
              negatedText = negatedText.replace(re, '');
            } catch(e){console.warn('[Audit]', e)}
          }
        }
        // 也处理否定形式问题词（不一致、不符合等）
        for (var np5 = 0; np5 < _negPrefixes.length; np5++) {
          for (var ip5 = 0; ip5 < _negIssuePats.length; ip5++) {
            try {
              var escP2 = _negPrefixes[np5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
              var escI2 = _negIssuePats[ip5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
              var re2 = new RegExp(escP2 + '[^，。！？；]{0,6}' + escI2, 'g');
              negatedText = negatedText.replace(re2, '');
            } catch(e){console.warn('[Audit]', e)}
          }
        }

        // 第1步：检查否定形式的问题词，排除否定前缀（在negatedText上检查）
        for (var i = 0; i < _negIssuePats.length; i++) {
          var p = _negIssuePats[i];
          if (negatedText.includes(p)) return true;
        }

        // 第1.5步：自动检测"否定前缀+问题词"形式（用全部否定前缀）
        var _extraNoIssue = [];
        for (var j = 0; j < _issuePats.length; j++) {
          for (var np3 = 0; np3 < _negPrefixes.length; np3++) {
            _extraNoIssue.push(_negPrefixes[np3] + _issuePats[j]);
          }
        }
        var _allNoIssue = _noIssuePats.concat(_extraNoIssue);

        // 第2步：清洗文本法（使用negatedText）
        var hasNoIssueKW = _allNoIssue.some(function(p){ return negatedText.includes(p); });
        if (hasNoIssueKW) {
          var cleaned = negatedText;
          var sortedPats = _allNoIssue.slice().sort(function(a,b){ return b.length - a.length; });
          sortedPats.forEach(function(p) { cleaned = cleaned.split(p).join(''); });
          return issuePatsToUse.some(function(p){ return cleaned.includes(p); });
        }

        // 第3步：直接检查问题词（使用negatedText）
        var hasIssueKW = issuePatsToUse.some(function(p){ return negatedText.includes(p); });
        if (_evalTypes.indexOf(checkType) >= 0) return hasIssueKW;
        if (negatedText.length < 80 && !hasIssueKW) return false;
        return hasIssueKW;
      }

      // 辅助函数：渲染单项检查结果并更新按钮状态
      function renderSingleResult(checkType, result) {
        var btn = null;
        selectedBtns.forEach(function(b) { if (b.dataset.check === checkType) btn = b; });
        var _labels = {twist:'转折',duplicate:'重复',style:'风格',conflict:'冲突',timeline:'时间线',quality:'质量',memory:'记忆',completeness:'完整性',continuity:'连贯性',consistency:'一致性',wordcount:'字数预算'};
        var checkLabel = _labels[checkType] || checkType;
        if (btn) {
          btn.classList.remove('running');
          if (result && result.ok) {
            var resultText = String(result.result || '').trim();
            var hasIssue = judgeValResult(checkType, resultText);
            btn.classList.add(hasIssue ? 'has-issue' : 'done');
          } else {
            btn.classList.add('has-issue');
          }
          btn.textContent = checkLabel;
        }
        var vDiv2 = document.getElementById('val-results');
        if (vDiv2) {
          // 清除"无校验结果"占位文本
          if (vDiv2.innerText.trim() === '无校验结果' || vDiv2.innerHTML.includes('empty-state')) {
            vDiv2.textContent = '';
          }
          var oldResults2 = vDiv2.querySelectorAll('.check-result-item[data-check="' + checkType + '"]');
          oldResults2.forEach(function(el) { el.remove(); });
          renderValResult(result, true, checkType);
        }
      }

      // 收集选中的检查类型，初始化按钮状态
      selectedTypes = []; // 已在前面定义，这里重置
      selectedBtns.forEach(function(btn) {
        var checkType = btn.dataset.check;
        selectedTypes.push(checkType);
        var vDiv3 = document.getElementById('val-results');
        var oldResults3 = vDiv3.querySelectorAll('.check-result-item[data-check="' + checkType + '"]');
        oldResults3.forEach(function(el) { el.remove(); });
        btn.classList.remove('selected','done','has-issue');
        btn.classList.add('running');
        btn.textContent = '⏳';
      });

      // ===== 第一步：全部检查走合并（1次AI调用完成所有维度） =====
      // 一致性/连贯性/完整性已并入 /all 端点，不再独立调用
      var standaloneTypes = [];
      var combinedTypes = selectedTypes.filter(function(t){ return true; });
      var combinedUsed = false;
      var missingTypes = [];

      if (combinedTypes.length >= 2) {
        try {
          var combinedResult = await checkAllCombined(checkContent, checkIndex, memoryContext, checkContext);
          if (combinedResult && combinedResult.ok && combinedResult.results) {
            combinedUsed = true;
            var parsed = combinedResult.results;
            var parsedCount = combinedResult.parsed_count || 0;

            combinedTypes.forEach(function(checkType) {
              if (parsed[checkType] !== null && parsed[checkType] !== undefined) {
                renderSingleResult(checkType, { ok: true, result: parsed[checkType], check_type: checkType, stage: currentStage });
              } else {
                missingTypes.push(checkType);
              }
            });

            showToast && showToast('合并检查完成 ' + parsedCount + '/' + combinedTypes.length + '项' + (missingTypes.length > 0 ? '，补查' + missingTypes.length + '项' : ''));
          }
        } catch(e) {
          console.error('Combined check failed, falling back:', e);
        }
      }

      // ===== 第二步：补查缺失项 + 独立检查项（完整性/连贯性） =====
      var typesToCheck = combinedUsed ? missingTypes : combinedTypes;
      if (!combinedUsed && combinedTypes.length > 0) {
        showToast && showToast('合并检查失败，回退逐项检查...');
      }
      // 加上独立检查类型
      typesToCheck = typesToCheck.concat(standaloneTypes);

      for (var i = 0; i < typesToCheck.length; i++) {
        var checkType = typesToCheck[i];
        console.log('[runChecks] 处理: ' + checkType + ', typesToCheck=' + JSON.stringify(typesToCheck));
        var btn = null;
        selectedBtns.forEach(function(b) { if (b.dataset.check === checkType) btn = b; });
        if (btn) { btn.classList.add('running'); btn.textContent = '⏳补查'; }

        try {
          var fn = checkMap[checkType];
          var result;
          // 全局一致性检查：根据有无正文自动判断阶段
          if (checkType === 'consistency') {
            // 有正文就阶段2，没有就阶段1
            var consistencyContent = checkContent || '';
            console.log('[一致性] checkContent长度=' + consistencyContent.length + ', checkIndex=' + checkIndex);
            if (consistencyContent.trim().length < 50) {
              // 没正文，阶段1：只检查设定层
              console.log('[一致性] 阶段1（无正文）');
              result = await fn();
            } else {
              // 有正文，阶段2：检查设定层+正文
              console.log('[一致性] 阶段2（有正文）');
              result = await fn(consistencyContent, checkIndex);
            }
            console.log('[一致性] result.ok=' + (result&&result.ok) + ', stage=' + (result&&result.stage));
          }
          // 全文模式下连贯性检查：循环检查所有相邻章节对
          else if (checkType === 'continuity' && checkScope === 'full') {
            // 全文模式：检查所有相邻章节对的连贯性
            var allResults = [];
            var totalScore = 0;
            var scoreCount = 0;
            var allGaps = [];
            var allSuggestions = [];
            var chapterCount = (typeof chapters !== 'undefined' && chapters) ? chapters.length : 0;
            
            for (var ci = 1; ci < chapterCount; ci++) {
              try {
                // 确保章节内容已加载
                if (!chapters[ci] || !chapters[ci].content) {
                  var chData = await api('/api/chapter/load?index=' + ci);
                  if (chData && chData.content) {
                    if (!chapters[ci]) chapters[ci] = {};
                    chapters[ci].content = chData.content;
                    chapters[ci].title = chData.title || ('第' + (ci+1) + '章');
                  }
                }
                if (!chapters[ci-1] || !chapters[ci-1].content) {
                  var prevData = await api('/api/chapter/load?index=' + (ci-1));
                  if (prevData && prevData.content) {
                    if (!chapters[ci-1]) chapters[ci-1] = {};
                    chapters[ci-1].content = prevData.content;
                    chapters[ci-1].title = prevData.title || ('第' + ci + '章');
                  }
                }
                
                var chResult = await fn(chapters[ci] ? chapters[ci].content : '', ci, memoryContext, checkContext);
                if (chResult && chResult.ok && chResult.result) {
                  var rData = typeof chResult.result === 'string' ? JSON.parse(chResult.result) : chResult.result;
                  var score = rData.overall_score || 0;
                  totalScore += score;
                  scoreCount++;
                  allResults.push('第' + ci + '章→第' + (ci+1) + '章: ' + score + '/10 ' + (rData.overall_level || ''));
                  if (rData.gap_points) allGaps = allGaps.concat(rData.gap_points);
                  if (rData.suggestions) allSuggestions = allSuggestions.concat(rData.suggestions);
                }
              } catch(e2) { /* skip this pair */ }
            }
            
            var avgScore = scoreCount > 0 ? (totalScore / scoreCount).toFixed(1) : '0';
            var resultText = '[连贯性]全文检查 ' + avgScore + '/10\n' + allResults.join('\n');
            if (allGaps.length > 0) resultText += '\n⚠️ 断裂点: ' + allGaps.slice(0, 5).join('; ');
            if (allSuggestions.length > 0) resultText += '\n💡 建议: ' + allSuggestions.slice(0, 3).join('; ');
            result = {ok: true, result: resultText};
          } else if (fn) {
            // 确保checkContent不为空
            if (!checkContent || checkContent.trim().length < 50) {
              try {
                var chData = await api('/api/chapter/load?index=' + checkIndex);
                if (chData && chData.content) {
                  checkContent = chData.content;
                }
              } catch(e){console.warn('[Audit]', e)}
            }
            if (!checkContent || checkContent.trim().length < 50) {
              result = {ok: false, error: '章节内容为空，无法检查'};
            } else {
              result = await fn(checkContent, checkIndex, memoryContext, checkContext);
            }
          } else {
            result = await runCheck(checkType, checkContent, currentStage);
          }
          renderSingleResult(checkType, result);
        } catch(e) {
          console.error('Check error for ' + checkType + ':', e);
          renderSingleResult(checkType, {ok:false, error:e.message});
        }
      }

      runBtn.disabled = false;
      runBtn.textContent = '🔍 开始检查';
      runBtn.style.opacity = '1';
      
      // 检查完成后，如果有问题，在结果顶部添加"一键全部修复"按钮
      var vDiv = document.getElementById('val-results');
      if (vDiv) {
        var issueItems = vDiv.querySelectorAll('.check-result-item');
        var hasIssues = false;
        var allProblems = [];
        issueItems.forEach(function(item) {
          var textEl = item.querySelector('.val-text');
          var checkType = item.dataset.check || '';
          if (textEl) {
            var text = textEl.innerText || textEl.textContent || '';
            // v4判断逻辑：结论优先（含问题指示检查）+全部否定前缀+清洗文本法
            var _pNeg = ['不一致','不符合','不连贯','不自然','不协调','不合理','不自洽','不匹配','不对齐'];
            var _pNegPrefixes = ['无明显','没有','不存在','未发现','未发现明显','未检测到','无'];
            var _pNoIssue = ['无矛盾','无冲突','无偏离','无重复','没有重复','不存在重复','无问题','没有问题','没有发现','未发现','未检测到','未检测到问题','无遗漏','没有遗漏','未发现明显','无明显问题','一致','符合','通过','对齐','无异常','正常','衔接正常','数据一致','未发现偏离','未发现冲突','未发现矛盾','未发现重复','未发现遗漏','ok','none'];
            var _pIssue = ['偏离','矛盾','冲突','断裂','遗漏','缺乏','缺失','生硬','突兀','混乱','错误','需改进','显著','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
            // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
            var pTail = text.substring(Math.max(0, text.length - 80));
            var pTailIsNoIssue = false;
            if (pTail.includes('结论') || pTail.includes('整体评价') || pTail.includes('总结')) {
              // 找到最后一个结论关键词位置，只看结论之后的内容
              var pConclStart = Math.max(pTail.lastIndexOf('结论'), pTail.lastIndexOf('整体评价'), pTail.lastIndexOf('总结'));
              var pConclText = pTail.substring(pConclStart);
              // 生成全部否定前缀+问题词的无问题模式
              var pTailExtra = [];
              for (var pte = 0; pte < _pIssue.length; pte++) {
                for (var pnp2 = 0; pnp2 < _pNegPrefixes.length; pnp2++) { pTailExtra.push(_pNegPrefixes[pnp2] + _pIssue[pte]); }
              }
              var pTailAllNo = _pNoIssue.concat(pTailExtra);
              var pTailHasNo = pTailAllNo.some(function(p){ return pConclText.includes(p); });
              if (pTailHasNo) {
                // 清洗结论句
                var pCleanedConcl = pConclText;
                var pSortedConcl = pTailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
                pSortedConcl.forEach(function(p) { pCleanedConcl = pCleanedConcl.split(p).join(''); });
                var pConclHasIssue = _pIssue.some(function(p){ return pCleanedConcl.includes(p); });
                if (!pConclHasIssue) { pTailIsNoIssue = true; }
              }
            }
            var pHasIssue = false;
            if (pTailIsNoIssue) {
              pHasIssue = false;
            } else {
              // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语
              var pNegatedText = text;
              // 处理一般问题词
              for (var pnp4 = 0; pnp4 < _pNegPrefixes.length; pnp4++) {
                for (var pip4 = 0; pip4 < _pIssue.length; pip4++) {
                  try {
                    var pEscPrefix = _pNegPrefixes[pnp4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var pEscIssue = _pIssue[pip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var pRe = new RegExp(pEscPrefix + '[^，。！？；]{0,6}' + pEscIssue, 'g');
                    pNegatedText = pNegatedText.replace(pRe, '');
                  } catch(e){console.warn('[Audit]', e)}
                }
              }
              // 也处理否定形式问题词（不一致、不符合等）
              for (var pnp5 = 0; pnp5 < _pNegPrefixes.length; pnp5++) {
                for (var pnip5 = 0; pnip5 < _pNeg.length; pnip5++) {
                  try {
                    var pEscP2 = _pNegPrefixes[pnp5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var pEscI2 = _pNeg[pnip5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var pRe2 = new RegExp(pEscP2 + '[^，。！？；]{0,6}' + pEscI2, 'g');
                    pNegatedText = pNegatedText.replace(pRe2, '');
                  } catch(e){console.warn('[Audit]', e)}
                }
              }
              // 第1步：检查否定形式的问题词（在negatedText上检查）
              var pNegHit = false;
              for (var pi = 0; pi < _pNeg.length; pi++) {
                if (pNegatedText.includes(_pNeg[pi])) { pNegHit = true; break; }
              }
              if (pNegHit) {
                pHasIssue = true;
              } else {
                var _pExtra = [];
                for (var pe = 0; pe < _pIssue.length; pe++) {
                  for (var penp = 0; penp < _pNegPrefixes.length; penp++) { _pExtra.push(_pNegPrefixes[penp] + _pIssue[pe]); }
                }
                var _pAllNo = _pNoIssue.concat(_pExtra);
                var pNoIssue = _pAllNo.some(function(p){ return pNegatedText.includes(p); });
                if (pNoIssue) {
                  var pCleaned = pNegatedText;
                  var pSorted = _pAllNo.slice().sort(function(a,b){ return b.length - a.length; });
                  pSorted.forEach(function(p) { pCleaned = pCleaned.split(p).join(''); });
                  pHasIssue = _pIssue.some(function(p){ return pCleaned.includes(p); });
                } else {
                  pHasIssue = _pIssue.some(function(p){ return pNegatedText.includes(p); });
                }
              }
            }
            if (pHasIssue) {
              hasIssues = true;
              var structuredIssue = {type: checkType, problem: text.substring(0, 500)};
              if (result && result.structured && result.structured.issues && result.structured.issues.length > 0) {
                structuredIssue.issues = result.structured.issues;
              }
              allProblems.push(structuredIssue);
            }
          }
        });
        if (hasIssues) {
          // 移除旧的修复全部按钮
          var oldFixAll = document.getElementById('fix-all-bar');
          if (oldFixAll) oldFixAll.remove();
          var fixAllBar = document.createElement('div');
          fixAllBar.id = 'fix-all-bar';
          fixAllBar.style.cssText = 'padding:12px;margin-bottom:8px;border-radius:8px;background:var(--panel);border:1px solid var(--border)';

          // 按类型分批：内容类 vs 风格类
          var _contentTypes = ['drift','conflict','consistency','continuity','completeness'];
          var _styleTypes = ['style','duplicate','twist'];
          var _contentProblems = allProblems.filter(function(p){ return _contentTypes.indexOf(p.type) >= 0; });
          var _styleProblems = allProblems.filter(function(p){ return _styleTypes.indexOf(p.type) >= 0; });
          var _otherProblems = allProblems.filter(function(p){ return _contentTypes.indexOf(p.type) < 0 && _styleTypes.indexOf(p.type) < 0; });

          // 构建问题清单HTML
          var summaryHtml = '<div class="mb-2.5">';
          summaryHtml += '<div class="flex-center-sm-mb2">';
          summaryHtml += '<span style="font-size:14px;font-weight:700;color:var(--fg)">📋 问题汇总</span>';
          summaryHtml += '<span class="text-md text-muted">共 ' + allProblems.length + ' 项问题</span>';
          summaryHtml += '</div>';

          // 内容类问题
          if (_contentProblems.length > 0) {
            summaryHtml += '<div class="mb-1.5">';
            summaryHtml += '<div style="font-size:11px;font-weight:600;color:#f87171;margin-bottom:3px">🔴 内容类（' + _contentProblems.length + '项）</div>';
            _contentProblems.forEach(function(p, i) {
              var label = (_checkLabels && _checkLabels[p.type]) ? _checkLabels[p.type] : p.type;
              var shortProblem = p.problem.substring(0, 80) + (p.problem.length > 80 ? '…' : '');
              summaryHtml += '<div style="font-size:11px;color:var(--muted);padding:2px 0 2px 12px;border-left:2px solid rgba(248,113,113,0.3);margin-bottom:2px">';
              summaryHtml += '<strong class="text-ink">' + label + '</strong>: ' + shortProblem;
              summaryHtml += '</div>';
            });
            summaryHtml += '</div>';
          }

          // 风格类问题
          if (_styleProblems.length > 0) {
            summaryHtml += '<div class="mb-1.5">';
            summaryHtml += '<div style="font-size:11px;font-weight:600;color:#facc15;margin-bottom:3px">🟡 风格类（' + _styleProblems.length + '项）</div>';
            _styleProblems.forEach(function(p, i) {
              var label = (_checkLabels && _checkLabels[p.type]) ? _checkLabels[p.type] : p.type;
              var shortProblem = p.problem.substring(0, 80) + (p.problem.length > 80 ? '…' : '');
              summaryHtml += '<div style="font-size:11px;color:var(--muted);padding:2px 0 2px 12px;border-left:2px solid rgba(250,204,21,0.3);margin-bottom:2px">';
              summaryHtml += '<strong class="text-ink">' + label + '</strong>: ' + shortProblem;
              summaryHtml += '</div>';
            });
            summaryHtml += '</div>';
          }

          // 其他问题
          if (_otherProblems.length > 0) {
            summaryHtml += '<div class="mb-1.5">';
            summaryHtml += '<div style="font-size:11px;font-weight:600;color:var(--muted);margin-bottom:3px">⚪ 其他（' + _otherProblems.length + '项）</div>';
            _otherProblems.forEach(function(p, i) {
              var label = (_checkLabels && _checkLabels[p.type]) ? _checkLabels[p.type] : p.type;
              var shortProblem = p.problem.substring(0, 80) + (p.problem.length > 80 ? '…' : '');
              summaryHtml += '<div style="font-size:11px;color:var(--muted);padding:2px 0 2px 12px;border-left:2px solid rgba(255,255,255,0.1);margin-bottom:2px">';
              summaryHtml += '<strong class="text-ink">' + label + '</strong>: ' + shortProblem;
              summaryHtml += '</div>';
            });
            summaryHtml += '</div>';
          }

          summaryHtml += '</div>';

          // 操作按钮区
          summaryHtml += '<div style="display:flex;gap:6px;flex-wrap:wrap">';
          if (_contentProblems.length > 0) {
            summaryHtml += '<button onclick="valAIFixAll()" style="background:#ef4444;color:#fff;border:none;border-radius:4px;padding:5px 12px;font-size:11px;cursor:pointer;font-weight:600">🔧 先修内容（' + _contentProblems.length + '项）</button>';
          }
          if (_styleProblems.length > 0 && _contentProblems.length === 0) {
            summaryHtml += '<button onclick="valAIFixAll()" style="background:#f59e0b;color:#000;border:none;border-radius:4px;padding:5px 12px;font-size:11px;cursor:pointer;font-weight:600">🔧 修风格（' + _styleProblems.length + '项）</button>';
          }
          summaryHtml += '<span style="font-size:10px;color:var(--muted);align-self:center">修复分两批：先内容后风格，每批确认后再修下一批</span>';
          summaryHtml += '</div>';

          fixAllBar.innerHTML = summaryHtml;
          vDiv.insertBefore(fixAllBar, vDiv.firstChild);
          // 保存问题列表供综合修复使用
          window._allValProblems = allProblems;
          // 同时保存到localStorage（供刷新后恢复）
          try {
            var probsKey = 'valProblems_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + checkIndex + '_' + (checkScope || 'chapter');
            localStorage.setItem(probsKey, JSON.stringify(allProblems));
          } catch(e) { /* ignore */ }
        }
      }
      
      showToast && showToast('✅ 检查完成');
      
      // 保存检查结果到localStorage（按章节+范围）
      try {
        var saveKey = 'valResults_' + (typeof currentProjectId !== 'undefined' ? currentProjectId : 'default') + '_ch' + checkIndex + '_' + (checkScope || 'chapter');
        var vDiv2 = document.getElementById('val-results');
        if (vDiv2 && vDiv2.innerHTML.trim()) {
          var saveData = {
            html: vDiv2.innerHTML,
            checkIndex: checkIndex,
            checkScope: checkScope || 'chapter',
            timestamp: Date.now()
          };
          localStorage.setItem(saveKey, JSON.stringify(saveData));
          // 记住上次使用的scope，刷新后优先恢复
          localStorage.setItem('valResults_lastScope', checkScope || 'chapter');
        }
      } catch(e) { console.warn('保存检查结果失败:', e); }
    });
  }

  // "全选"按钮
  const selectAllBtn = document.getElementById('btn-select-all-checks');
  if (selectAllBtn) {
    selectAllBtn.addEventListener('click', function() {
      var allBtns = grid.querySelectorAll('.check-btn');
      var allSelected = true;
      allBtns.forEach(function(btn) {
        if (!btn.classList.contains('selected')) allSelected = false;
      });
      if (allSelected) {
        // 全部已选中，取消全选
        allBtns.forEach(function(btn) { btn.classList.remove('selected'); });
        selectAllBtn.textContent = '☑️ 全选';
      } else {
        // 选中全部
        allBtns.forEach(function(btn) { btn.classList.add('selected'); });
        selectAllBtn.textContent = '☐ 取消';
      }
    });
  }

  // "清空结果"按钮
  const clearBtn = document.getElementById('btn-clear-checks');
  if (clearBtn) {
    clearBtn.addEventListener('click', function() {
      var vDiv = document.getElementById('val-results');
      if (vDiv) vDiv.textContent = '';
      // 重置所有维度按钮状态
      grid.querySelectorAll('.check-btn').forEach(function(btn) {
        btn.classList.remove('selected','done','has-issue','running');
      });
      if (selectAllBtn) selectAllBtn.textContent = '☑️ 全选';
      lastValResult = null;
      window._allValProblems = [];
      // 清除当前章节的所有scope的localStorage检查结果
      try {
        var chIdx = (typeof currentChapterIndex !== 'undefined') ? currentChapterIndex : 0;
        var pid = (typeof currentProjectId !== 'undefined') ? currentProjectId : 'default';
        ['chapter', 'full', 'book'].forEach(function(sc) {
          localStorage.removeItem('valResults_' + pid + '_ch' + chIdx + '_' + sc);
          localStorage.removeItem('valProblems_' + pid + '_ch' + chIdx + '_' + sc);
        });
      } catch(e) { /* ignore */ }
    });
  }
}

// 启动检查按钮绑定
setupCheckButtons();



// ── Editor toolbar: Save + AI ──
(function setupEditorToolbar() {
  // Save button
  var btnSave = document.getElementById('btn-save');
  if (btnSave) {
    btnSave.addEventListener('click', async function() {
      // 草稿模式下，保存按钮=采纳按钮
      if (window.DraftManager && DraftManager.isActive()) {
        await DraftManager.accept();
        return;
      }
      if (currentChapterIndex < 0 || !chapters[currentChapterIndex]) return;
      btnSave.textContent = '⏳ 保存中';
      try {
        var editorEl = document.getElementById('editor-content');
        var content = editorEl ? (editorEl.innerText || '') : '';
        var r = await saveChapter(currentChapterIndex, content);
        if (r.ok) {
          showToast && showToast('已保存');
          document.getElementById('word-count').textContent = (r.word_count || content.length).toLocaleString('zh-CN');
          // P0-4: 同步存储数值到 chapters
          if (chapters[currentChapterIndex]) {
            chapters[currentChapterIndex].words = r.word_count || content.length;
            chapters[currentChapterIndex].word_count = r.word_count || content.length;
          }
          // 审计日志：记录保存章节事件
          if (typeof auditLog === 'function') {
            auditLog('save', '第' + (currentChapterIndex + 1) + '章 ' + (chapters[currentChapterIndex] ? (chapters[currentChapterIndex].title || '') : ''), '手动保存 ' + (r.word_count || content.length) + ' 字');
          }
        } else {
          showToast && showToast('保存失败: ' + (r.error || ''));
        }
      } catch(e) { console.error('Save error:', e); showToast && showToast('保存出错'); }
      finally { btnSave.textContent = '💾 保存'; }
    });
  }

  // 章节暂锁草稿/解锁切换
  $on('btn-chapter-lock', 'click', async function() {
    if (typeof chapters === 'undefined' || !chapters || currentChapterIndex < 0 || currentChapterIndex >= chapters.length) {
      showToast('请先选择章节'); return;
    }
    var ch = chapters[currentChapterIndex];
    if (!ch) return;
    var wasLocked = ch.locked === true;
    if (wasLocked) {
      // 解锁
      ch.locked = false;
      this.textContent = '🔒 暂锁草稿';
      this.style.background = 'rgba(108,92,231,0.05)';
      showToast('🔓 第' + (currentChapterIndex+1) + '章已解锁，可进行AI操作');
      try {
        await api('/api/chapter/outline', { method: 'POST', body: JSON.stringify({ index: currentChapterIndex, locked: false }) });
        await api('/api/chapter/' + currentChapterIndex + '/status', { method: 'POST', body: JSON.stringify({ status: 'revised' }) });
      } catch(e) { console.warn('解锁状态保存失败', e); }
    } else {
      // 暂锁前先保存编辑器最新内容
      var editorEl = document.getElementById('editor-content');
      if (editorEl) {
        var liveContent = editorEl.innerText || '';
        if (liveContent.trim() && ch.content !== liveContent) {
          try {
            await saveChapter(currentChapterIndex, liveContent);
            ch.content = liveContent;
          } catch(e) { console.warn('暂锁前保存失败', e); }
        }
      }
      // 暂锁前确认
      var content = ch.content || '';
      if (!content.trim() && !(ch.word_count > 0)) {
        showToast('⚠️ 该章节没有内容，无法暂锁'); return;
      }
      var ok = confirm('确定要暂锁第' + (currentChapterIndex+1) + '章草稿吗？\n\n暂锁后将自动：\n• 生成时间线并执行AI对照检查\n• 进行章节蒸馏\n• 如发现偏离会提示修改\n\n注意：\n• 禁止：AI生成正文、重新生成、续写（防止覆盖定稿）\n• 允许：AI修复、去AI味（用于修正对照发现的问题，需二次确认）');
      if (!ok) return;
      ch.locked = true;
      this.textContent = '🔓 解锁';
      this.style.background = 'rgba(231,76,60,0.1)';
      showToast('🔒 第' + (currentChapterIndex+1) + '章草稿已暂锁，正在执行检查…');
      // 保存锁定状态 + 触发完整定稿流程（时间线+AI对照+蒸馏）
      try {
        await api('/api/chapter/outline', { method: 'POST', body: JSON.stringify({ index: currentChapterIndex, locked: true }) });
        var statusResult = await api('/api/chapter/' + currentChapterIndex + '/status', { method: 'POST', body: JSON.stringify({ status: 'final' }) });
        if (statusResult && statusResult.ok) {
          showToast('🔒 第' + (currentChapterIndex+1) + '章已定稿，请前往步骤7查看时间线检查结果');
        }
      } catch(e) { console.warn('暂锁/定稿流程失败', e); showToast('⚠️ 暂锁成功但定稿流程异常: ' + e.message); }
    }
    // 更新章节列表显示
    if (typeof renderChapterList === 'function') renderChapterList();
  });

  // 草稿按钮：手动进入草稿模式
  $on('wt-btn-draft', 'click', async function() {
    console.log('[wt-btn-draft] clicked');
    if (!window.DraftManager) {
      if (showToast) showToast('草稿模块未加载');
      return;
    }
    if (DraftManager.isActive()) {
      if (showToast) showToast('已在草稿模式中');
      return;
    }
    var editorEl = document.getElementById('editor-content');
    var currentContent = editorEl ? editorEl.innerText : '';
    if (!currentContent || currentContent.trim().length < 5) {
      if (showToast) showToast('当前内容为空，无法进入草稿模式');
      return;
    }
    // 获取成品内容：chapters 数组不保存正文，必须从 API 加载已保存内容
    var chIdx = window.currentChapterIndex || 0;
    var publishedContent = '';
    if (typeof selectChapter === 'function') {
      try {
        var r = await selectChapter(chIdx);
        if (r && r.ok) publishedContent = r.content || '';
        console.log('[wt-btn-draft] loaded publishedContent length=', publishedContent.length);
      } catch(e) {
        console.warn('[wt-btn-draft] load saved content failed:', e);
        if (showToast) showToast('加载成品内容失败，将以空成品进入草稿模式', 'warning');
      }
    }
    // 进入草稿模式（当前编辑器内容作为草稿，已保存内容作为成品）
    await DraftManager.enter(currentContent, publishedContent);
    if (showToast) showToast('已进入草稿模式，可点击🔍检查按钮进行19维检查');
  });

  // AI Generate chapter
  $on('btn-ai-gen', 'click', async function() {
    // 章节锁定：已完成的章节禁止AI生成（避免覆盖已有正文）
    if (typeof _isChapterLocked === 'function' && _isChapterLocked(currentChapterIndex)) {
      showToast('🔒 第' + (currentChapterIndex+1) + '章已定稿，AI生成仅限当前正在写的章节');
      return;
    }
    // 确保章节数据已加载
    if (!chapters || chapters.length === 0) {
      if (typeof loadChaptersFromAPI === 'function') {
        try { await loadChaptersFromAPI(); } catch(e){console.warn('[Audit]', e)}
      }
    }
    if (!chapters || chapters.length === 0) { showToast && showToast('请先添加章节'); return; }
    var ch = chapters[currentChapterIndex] || chapters[0];
    this.disabled = true; this.classList.add('running');
    // 同步新工具栏按钮状态
    var wtGen = document.getElementById('wt-btn-gen');
    if (wtGen) { wtGen.disabled = true; wtGen.classList.add('running'); wtGen.textContent = '⏳ 生成中…'; }
    // 编辑器显示加载提示
    var editorEl = document.getElementById('editor-content');
    var editorTitle = document.getElementById('editor-title');
    var origContent = editorEl ? editorEl.innerHTML : '';
    var origText = editorEl ? editorEl.innerText : '';
    // 清除可能存在的大纲参考显示（防止AI将其误认为正文）
    if (editorEl && editorEl.innerHTML.indexOf('本章大纲（参考）') !== -1) {
      editorEl.textContent = '';
      origContent = '';
      origText = '';
    }
    if (editorEl) editorEl.innerHTML = '<div style="text-align:center;padding:60px 20px;color:var(--muted)"><div style="font-size:24px;margin-bottom:12px">⏳</div><div>AI 正在生成「' + (ch.title||'') + '」...</div><div style="font-size:11px;margin-top:8px;opacity:.6">预计需要30-60秒，请稍候</div></div>';
    try {
      // 正文生成：以章节大纲为核心，避免重复传入全书大纲/世界观/人物，节省 token
      var outline = '';
      if (ch.outline) {
        var outlineText = '';
        if (Array.isArray(ch.outline)) {
          outlineText = ch.outline.map(function(o) { return '- ' + (o&&(o.text||o)||String(o)); }).join('\n');
        } else if (typeof ch.outline === 'string') {
          outlineText = ch.outline;
        }
        if (outlineText) {
          outline = '本章大纲（必须遵循）：\n' + outlineText;
        }
      }
      if (!outline.trim()) {
        showToast && showToast('请先生成本章章节大纲');
        this.disabled = false; this.classList.remove('running');
        var wtGen = document.getElementById('wt-btn-gen');
        if (wtGen) { wtGen.disabled = false; wtGen.classList.remove('running'); wtGen.textContent = '✨ 生成'; }
        return;
      }
      var context = '';
      // 向量记忆召回 — 替代旧的500字截取
      var chapterIndex = currentChapterIndex >= 0 ? currentChapterIndex : 0;
      var prevChapters = '';
      try {
        var memResult = await searchMemoryForGeneration(outline || ch.title, chapterIndex, 5);
        if (memResult && memResult.ok && memResult.context) {
          prevChapters = memResult.context;
        }
      } catch(e) { console.warn('向量记忆召回失败，使用fallback', e); }
      // Fallback: 如果向量记忆为空（首次使用或无数据），用旧的500字截取
      if (!prevChapters && typeof chapters !== 'undefined' && chapters.length > 0) {
        for (var i = 0; i < currentChapterIndex; i++) {
          var prevCh = chapters[i];
          if (prevCh && prevCh.content) {
            var summary = prevCh.content.length > 500 ? prevCh.content.substring(0, 500) + '...' : prevCh.content;
            prevChapters += '\n\n===== 第' + (i+1) + '章：' + (prevCh.title||'') + ' =====\n' + summary;
          }
        }
      }
      if (prevChapters) {
        context += '\n\n## 前文记忆（当前是第' + (chapterIndex+1) + '章）\n' + prevChapters;
      }
      var r = await generateChapterPreview(ch.title, outline, context, chapterIndex);
      if (r && r.content) {
        // C4 预览确认流程：展示预览，用户确认后保存
        showChapterPreview(r, chapterIndex, ch.title, function(confirmedContent) {
          document.getElementById('editor-title').textContent = ch.title;
          try {
            if (window.DraftManager) {
              DraftManager.enter(confirmedContent, origText || '');
              showToast && showToast('已确认采用，进入草稿模式对比');
            } else {
              var el = document.getElementById('editor-content');
              if (el) el.innerHTML = textToHTML ? textToHTML(confirmedContent) : confirmedContent.replace(/\n/g, '<br>');
              showToast && showToast('已确认采用并保存');
            }
          } catch(e) { console.error('Draft/Save failed:', e); }
          if (typeof updateWordCount === 'function') updateWordCount();
          if (typeof updateToolbarStatus === 'function') updateToolbarStatus();
        });
        // 更新字数和工具栏
        if (typeof updateWordCount === 'function') updateWordCount();
        if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
        // 审计日志：记录生成正文事件
        if (typeof auditLog === 'function') {
          auditLog('generate', '第' + (currentChapterIndex + 1) + '章 ' + (ch.title || ''), 'AI生成正文 ' + (r.content ? r.content.length : 0) + ' 字');
        }
      } else {
        // P1-9: 生成失败时恢复原内容
        if (editorEl && origContent) { editorEl.innerHTML = origContent; }
        showToast && showToast('生成失败: ' + (r && r.error || ''));
      }
    } catch(e) {
      console.error(e);
      // P1-9: 异常时恢复原内容
      if (editorEl && origContent) { editorEl.innerHTML = origContent; }
      showToast && showToast('AI生成出错: ' + e.message);
    }
    finally {
      this.disabled = false; this.classList.remove('running');
      if (wtGen) { wtGen.disabled = false; wtGen.classList.remove('running'); wtGen.textContent = '✨ 生成'; }
    }
  });

  // 重新生成当前章节（覆盖现有内容，直接调用单章API）
  $on('btn-ai-regen', 'click', async function() {
    // 章节锁定：已完成的章节禁止重新生成
    if (typeof _isChapterLocked === 'function' && _isChapterLocked(currentChapterIndex)) {
      showToast('🔒 第' + (currentChapterIndex+1) + '章已定稿，重新生成仅限当前正在写的章节');
      return;
    }
    // 确保章节数据已加载
    if (!chapters || chapters.length === 0) {
      if (typeof loadChaptersFromAPI === 'function') {
        try { await loadChaptersFromAPI(); } catch(e){console.warn('[Audit]', e)}
      }
    }
    if (!chapters || chapters.length === 0) { showToast && showToast('请先添加章节'); return; }
    var ch = chapters[currentChapterIndex] || chapters[0];
    if (!confirm('确定重新生成「' + (ch.title||'') + '」？现有内容将被覆盖。')) return;
    
    this.disabled = true; this.classList.add('running'); this.textContent = '⏳ 生成中…';
    
    var editorEl = document.getElementById('editor-content');
    var origContent = editorEl ? editorEl.innerHTML : '';
    if (editorEl) editorEl.innerHTML = '<div style="text-align:center;padding:60px 20px;color:var(--muted)"><div style="font-size:24px;margin-bottom:12px">⏳</div><div>AI 正在重新生成「' + (ch.title||'') + '」...</div><div style="font-size:11px;margin-top:8px;opacity:.6">预计需要30-60秒，请稍候</div></div>';
    
    try {
      // 构建大纲
      var outline = ch.outline || '';
      // 确保outline是字符串
      if (Array.isArray(outline)) {
        outline = outline.map(function(o) { return (o && (o.text || o)) || String(o); }).join('\n');
      } else if (typeof outline !== 'string') {
        outline = String(outline || '');
      }
      // 如果 outline 是占位符文本则忽略
      var _isPlaceholder = function(t) {
        if (!t || !t.trim()) return true;
        var s = t.trim();
        return s.indexOf('【在此输入') >= 0 || s.indexOf('[在此输入') >= 0 || s.indexOf('大纲要点】') >= 0 || s.indexOf('大纲条目】') >= 0 || s.length < 15;
      };
      if (_isPlaceholder(outline)) outline = '';
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
        if (outline) {
          outline = bpOutline + '\n\n【补充大纲条目】\n' + outline;
        } else {
          outline = bpOutline;
        }
      }
      if (!outline.trim()) {
        outline = '请根据《' + (ch.title || '第' + (chapterIndex+1) + '章') + '》的章节定位自行构思内容';
      }
      
      var chapterIndex = currentChapterIndex >= 0 ? currentChapterIndex : 0;
      
      // 获取启用的技能包规则
      var skillRules = '';
      if (typeof SkillPack !== 'undefined') {
        skillRules = SkillPack.getActiveRules('generate');
      }
      
      // C4 预览确认：先通过 gate 生成（不保存），预览后确认
      var r = await generateChapterPreview(ch.title || ('第' + (chapterIndex+1) + '章'), outline, '', chapterIndex);
      
      if (r && r.content) {
        showChapterPreview(r, chapterIndex, ch.title, function(confirmedContent) {
          if (editorEl) editorEl.innerHTML = textToHTML ? textToHTML(confirmedContent) : confirmedContent.replace(/\n/g, '<br>');
          if (typeof updateWordCount === 'function') updateWordCount();
          if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
          try {
            Object.keys(localStorage).forEach(function(k) {
              if (k.startsWith('valResults_') && k.includes('ch' + chapterIndex)) {
                localStorage.removeItem(k);
              }
            });
          } catch(e){console.warn('[Audit]', e)}
          showToast && showToast('✅ 已确认采用 ' + confirmedContent.length + '字');
        });
      } else {
        if (editorEl && origContent) editorEl.innerHTML = origContent;
        showToast && showToast('重新生成失败: ' + (r && r.error || ''));
      }
    } catch(e) {
      console.error(e);
      if (editorEl && origContent) editorEl.innerHTML = origContent;
      showToast && showToast('重新生成出错: ' + e.message);
    } finally {
      this.disabled = false; this.classList.remove('running'); this.textContent = '🔄 重新生成';
    }
  });

  // AI Optimize
  $on('wt-btn-opt', 'click', async function() {
    // 章节锁定：去AI味允许在锁定章节上执行（修复性操作），但需要确认
    if (typeof _isChapterLocked === 'function' && _isChapterLocked(currentChapterIndex)) {
      if (!confirm('🔒 第' + (currentChapterIndex+1) + '章已锁定（定稿）。\n\n确定要进行去AI味改写吗？\n\n改写将保持剧情不变，但会改变语言风格和表达方式。')) {
        return;
      }
    }
    var el = document.getElementById('editor-content');
    if (!el || !(el.innerText || '').trim()) { showToast && showToast('没有内容可优化'); return; }
    this.disabled = true; this.classList.add('running');
    try {
      var content = el.innerText || '';
      var optPrompt = '请将以下小说正文完全重写。不是微调，不是优化，是用完全不同的语言重新讲同一个故事。\n\n重写规则：\n1. 剧情事件、人物、对话含义保持不变\n2. 但叙事视角、句子结构、用词习惯必须完全不同\n3. 打乱原文的段落结构，重新组织叙事顺序\n4. 用一种粗粝的、不完美的、口语化的风格重写\n5. 大量使用短句、断句、省略号，但破折号（——）每千字最多用2次\n6. 偶尔用方言感或非标准语法\n7. 删掉冗余的修饰性形容词副词，保留必要的动词和名词\n8. 对话用引号（""）或自然嵌入，不要刻意替换为破折号\n9. 段落之间可以跳跃，不需要平滑过渡\n10. 加入一些跟主线无关的细节描写（比如角色的小动作、环境的琐碎细节）\n11. 字数跟原文接近\n\n直接输出重写的正文。';
      var r = await callAI([{role:'user',content: optPrompt + '\n\n原文：\n' + content}], {temperature: 1.3});
      if (r && r.content) {
        el.innerHTML = textToHTML ? textToHTML(r.content) : r.content.replace(/\n/g, '<br>');
        showToast && showToast('人类化改写完成');
        // 审计日志：记录去AI味事件
        if (typeof auditLog === 'function') {
          auditLog('deai', '第' + (currentChapterIndex + 1) + '章', 'AI人类化改写 ' + (r.content ? r.content.length : 0) + ' 字');
        }
      }
    } catch(e) { console.error(e); showToast && showToast('优化出错'); }
    finally { this.disabled = false; this.classList.remove('running'); }
  });

  // 深度去AI味（逐段反检测重写：自家检测达标也能继续，较慢耗Token）
  $on('wt-btn-opt-deep', 'click', async function() {
    if (!state.currentProject) { showToast && showToast('请先创建或打开项目', 'warning'); return; }
    var el = document.getElementById('editor-content');
    if (!el || !(el.innerText || '').trim()) { showToast && showToast('没有可深度清洗的内容', 'warning'); return; }
    if (!window.confirm('深度去AI味会逐段重写全文（约2-4分钟，消耗较多Token），且无法撤销。继续？')) return;
    this.disabled = true;
    this.classList.add('running');
    var origText = this.textContent;
    this.textContent = '🧨 深度清洗中…';
    try {
      var content = el.innerText || '';
      showToast && showToast('深度去AI味进行中：逐段重写，预计2-4分钟…', 'info', 5000);
      var r = await api('/api/validate/deai-deep', {
        method: 'POST',
        body: JSON.stringify({content: content, chapter_index: currentChapterIndex}),
        timeout: 600000
      });
      if (r && r.ok && r.content) {
        el.innerHTML = textToHTML ? textToHTML(r.content) : r.content.replace(/\n/g, '<br>');
        if (typeof updateWordCount === 'function') updateWordCount();
        showToast && showToast('深度去AI味完成：重写 ' + (r.processed || 0) + '/' + (r.total || 0) + ' 段，记得保存');
        if (typeof auditLog === 'function') auditLog('deai-deep', '第' + (currentChapterIndex + 1) + '章', '逐段反检测重写 ' + r.content.length + '字');
      } else {
        showToast && showToast('深度去AI味失败: ' + (r && r.error || '未知错误'), 'error');
      }
    } catch(e) { console.error(e); showToast && showToast('深度去AI味出错: ' + e.message, 'error'); }
    finally { this.disabled = false; this.classList.remove('running'); this.textContent = origText; }
  });

  // AI Continue writing
  $on('wt-btn-cont', 'click', async function() {
    // 章节锁定：已完成的章节禁止续写
    if (typeof _isChapterLocked === 'function' && _isChapterLocked(currentChapterIndex)) {
      showToast('🔒 第' + (currentChapterIndex+1) + '章已定稿，续写仅限当前正在写的章节');
      return;
    }
    var el = document.getElementById('editor-content');
    if (!el || !(el.innerText || '').trim()) { showToast && showToast('没有内容可续写'); return; }
    this.disabled = true; this.classList.add('running');
    try {
      var content = el.innerText || '';
      var lastPara = content.split('\n').pop().slice(-500);
      // 续写：只读前文+章节大纲，不重复传全书设定，节省 token
      var outlineCtx = '';
      var ch = chapters[currentChapterIndex];
      if (ch && ch.outline) {
        var outlineText = '';
        if (Array.isArray(ch.outline)) {
          outlineText = ch.outline.map(function(o) { return '- ' + (o&&(o.text||o)||String(o)); }).join('\n');
        } else if (typeof ch.outline === 'string') {
          outlineText = ch.outline;
        }
        if (outlineText) {
          outlineCtx = '\n\n本章大纲方向（续写需符合）：\n' + outlineText;
        }
      }
      var r = await callAI([{role:'user',content:'请续写以下小说内容（只输出续写部分，不要重复前文）：\n...'+lastPara+outlineCtx}]);
      if (r && r.content) {
        el.innerHTML = (textToHTML ? textToHTML(content) : content.replace(/\n/g, '<br>')) 
          + '<br><br>' + (textToHTML ? textToHTML(r.content) : r.content.replace(/\n/g, '<br>'));
        showToast && showToast('续写完成');
        // 审计日志：记录续写事件
        if (typeof auditLog === 'function') {
          auditLog('continue', '第' + (currentChapterIndex + 1) + '章', 'AI续写 ' + (r.content ? r.content.length : 0) + ' 字');
        }
      }
    } catch(e) { console.error(e); showToast && showToast('续写出错'); }
    finally { this.disabled = false; this.classList.remove('running'); }
  });

  // 智能排版按钮
  $on('btn-ai-format', 'click', function() {
    var el = document.getElementById('editor-content');
    if (!el) { showToast && showToast('编辑器未就绪'); return; }
    var raw = el.innerText || '';
    if (!raw.trim()) { showToast && showToast('没有内容可排版'); return; }
    // 将当前内容转为纯文本，重新智能分段后渲染
    var formatted = smartParagraphSplit(raw);
    el.innerHTML = textToHTML ? textToHTML(formatted) : formatted.replace(/\n/g, '<br>');
    showToast && showToast('排版完成：已自动分段');
    // 标记需要保存
    if (typeof chapterModified !== 'undefined') chapterModified = true;
  });

})();



// ── AI味检测报告 ──
function showFlavorReport(r, content) {
  var levelColors = {'clean': '#27ae60', 'minor': '#f39c12', 'moderate': '#e67e22', 'heavy': '#e74c3c'};
  var levelLabels = {'clean': '干净', 'minor': '轻微', 'moderate': '中等', 'heavy': '严重'};
  var color = levelColors[r.level] || '#999';
  var label = levelLabels[r.level] || r.level;
  var html = '<div style="text-align:center;margin-bottom:12px">' +
    '<div style="font-size:32px;font-weight:700;color:' + color + '">' + r.score + '/100</div>' +
    '<div style="font-size:12px;color:' + color + '">AI味: ' + label + '</div>' +
    '<div class="text-xs text-muted mt-1">字数: ' + content.length + '</div>' +
  '</div>';
  if (r.issues && r.issues.length > 0) {
    html += '<div style="font-size:11px;color:var(--muted);margin-bottom:6px">检测到 ' + r.issues.length + ' 个问题：</div>';
    r.issues.forEach(function(issue) {
      var typeColors = {
        'buzzword_forbidden': '#e74c3c', 'buzzword_density': '#e67e22',
        'formulaic_transition': '#f39c12', 'transition_overuse': '#f39c12',
        'narrator_overreach': '#9b59b6', 'plastic_prose': '#3498db',
        'monotonous_sentence': '#95a5a6'
      };
      var tc = typeColors[issue.type] || '#999';
      html += '<div style="padding:6px 8px;margin-bottom:4px;border-left:3px solid ' + tc + ';background:var(--surface);border-radius:0 4px 4px 0">' +
        '<div style="font-size:11px;color:var(--ink)">' + escapeHtml(issue.message) + '</div>';
      // 定位信息：如果有精确位置，渲染可点击列表
      if (issue.locations && issue.locations.length > 0) {
        html += '<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">';
        issue.locations.forEach(function(loc, idx) {
          var locText = loc.line ? ('第' + loc.line + '行') : ('位置' + loc.offset);
          var snippet = loc.context ? escapeHtml(loc.context) : '';
          html += '<button onclick="window._auditJumpTo(' + (loc.line || 0) + ',' + (loc.offset || 0) + ')" ' +
            'title="' + snippet + '" ' +
            'style="font-size:9px;padding:2px 6px;border:1px solid var(--border-soft);border-radius:999px;background:var(--bg);color:var(--muted);cursor:pointer;transition:all .15s" ' +
            'onmouseover="this.style.borderColor=\'' + tc + '\';this.style.color=\'' + tc + '\'" ' +
            'onmouseout="this.style.borderColor=\'var(--border-soft)\';this.style.color=\'var(--muted)\'"' +
            '>' + locText + '</button>';
        });
        html += '</div>';
      } else if (issue.scope === 'global') {
        html += '<div style="margin-top:2px;font-size:9px;color:var(--muted-deep)">📊 全文统计，无具体位置</div>';
      }
      html += '</div>';
    });
  } else if (r.level === 'clean') {
    html += '<div style="text-align:center;padding:12px;color:#27ae60;font-size:12px">✓ 没有检测到AI味，文笔自然</div>';
  }
  // 弹窗显示
  var dlg = document.getElementById('flavor-report-dialog');
  if (!dlg) {
    dlg = document.createElement('div');
    dlg.id = 'flavor-report-dialog';
    dlg.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9998;display:flex;align-items:center;justify-content:center';
    dlg.onclick = function(e) { if (e.target === dlg) dlg.style.display = 'none'; };
    dlg.innerHTML = '<div style="background:var(--bg);border-radius:12px;width:90%;max-width:400px;max-height:70vh;display:flex;flex-direction:column;overflow:hidden">' +
      '<div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">' +
        '<span style="font-size:14px;font-weight:600;color:var(--ink)">🔍 AI味检测报告</span>' +
        '<button onclick="this.closest(\'#flavor-report-dialog\').style.display=\'none\'" style="border:none;background:none;font-size:18px;cursor:pointer;color:var(--muted)">✕</button>' +
      '</div>' +
      '<div id="flavor-report-body" style="flex:1;overflow-y:auto;padding:12px 16px"></div>' +
    '</div>';
    document.body.appendChild(dlg);
  }
  document.getElementById('flavor-report-body').innerHTML = html;
  dlg.style.display = 'flex';
}


// ═══════════════════════════════════════════
// 审计定位跳转：从检查结果跳转到编辑器对应位置
// ═══════════════════════════════════════════
window._auditJumpTo = function(line, offset) {
  // 1. 关闭报告弹窗
  var dlg = document.getElementById('flavor-report-dialog');
  if (dlg) dlg.style.display = 'none';
  var detailCheck = document.getElementById('detail-check-results');
  if (detailCheck) detailCheck.style.display = 'none';
  // 恢复详情编辑器
  var emptyEl = document.getElementById('detail-editor-empty');
  if (emptyEl) emptyEl.style.display = '';
  var headerEl = document.getElementById('detail-editor-header');
  if (headerEl) headerEl.style.display = '';
  var ta = document.getElementById('detail-editor-textarea');
  if (ta) ta.style.display = '';

  // 2. 获取编辑器内容段落
  var editor = document.getElementById('editor-content');
  if (!editor) return;
  var paragraphs = editor.querySelectorAll('p');
  if (!paragraphs.length) return;

  // 3. 计算目标段落索引（按行号映射到段落）
  // 简单映射：每行 ≈ 一个段落；行号从1开始
  var targetIdx = Math.max(0, Math.min(paragraphs.length - 1, line - 1));
  var targetP = paragraphs[targetIdx];
  if (!targetP) return;

  // 4. 滚动到目标段落
  targetP.scrollIntoView({behavior: 'smooth', block: 'center'});

  // 5. 高亮目标段落（临时添加CSS类）
  paragraphs.forEach(function(p) { p.classList.remove('audit-highlight'); });
  targetP.classList.add('audit-highlight');
  setTimeout(function() {
    targetP.classList.remove('audit-highlight');
  }, 4000);

  // 6. 显示提示
  if (typeof showToast === 'function') {
    showToast('已定位到第' + line + '行');
  }
};


// ── Auto-save model config on field change ──
(function setupModelAutosave() {
  var fields = ['mp-api-key', 'mp-endpoint', 'mp-model-name', 'mp-ollama-host', 'mp-ollama-model', 'mp-temp', 'mp-maxwords'];
  var saveTimer = null;
  fields.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', function() { saveModelConfig(); });
      el.addEventListener('blur', function() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveModelConfig, 500);
      });
    }
  });
})();

// ── Model config buttons ──
(function setupModelButtons() {
  var saveBtn = document.getElementById('mp-save-config');
  if (saveBtn) {
    saveBtn.addEventListener('click', async function() {
      this.textContent = '保存中...';
      this.disabled = true;
      try {
        await saveModelConfig();
        showToast && showToast('配置已保存');
      } catch(e) { showToast && showToast('保存失败'); }
      this.textContent = '保存并加载';
      this.disabled = false;
    });
  }
  var testBtn = document.getElementById('mp-test-conn');
  if (testBtn) {
    testBtn.addEventListener('click', async function() {
      var statusEl = document.getElementById('mp-conn-status');
      if (statusEl) statusEl.innerHTML = '<div class="mp-conn test">测试中...</div>';
      this.textContent = '测试中...';
      this.disabled = true;
      try {
        var r = await testConnection();
        var connected = (r && (r.connected || r.ok));
        if (statusEl) {
          if (r && r.connected !== undefined) {
            statusEl.innerHTML = '<div class="mp-conn ' + (r.connected ? 'ok' : 'fail') + '">' + (r.connected ? '已连接 ✓' : '连接失败 ✗') + '</div>';
          } else if (r && r.ok) {
            statusEl.innerHTML = '<div class="mp-conn ok">已连接 ✓</div>';
          } else {
            statusEl.innerHTML = '<div class="mp-conn fail">连接失败: ' + (r.error || '') + '</div>';
          }
        }
        // Update badge on successful connection
        if (connected && typeof updateModelBadge === 'function') {
          saveModelConfig();
        }
      } catch(e) {
        if (statusEl) statusEl.innerHTML = '<div class="mp-conn fail">请求失败</div>';
      }
      this.textContent = '测试连接';
      this.disabled = false;
    });
  }
})();

// ── Theme toggle ──
(function setupTheme() {
  var btn = document.getElementById('btn-theme');
  if (btn) {
    btn.addEventListener('click', function() {
      var app = document.querySelector('.app');
      if (!app) return;
      if (app.classList.contains('light-theme')) {
        app.classList.remove('light-theme');
        document.documentElement.style.setProperty('--bg','#1a1815');
        document.documentElement.style.setProperty('--surface','#24211d');
        document.documentElement.style.setProperty('--paper','#f5f0e8');
        document.documentElement.style.setProperty('--card','#2a2520');
        document.documentElement.style.setProperty('--bg2','#1e1b17');
        document.documentElement.style.setProperty('--ink','#e8e0d5');
        document.documentElement.style.setProperty('--ink-editor','#2c2416');
        document.documentElement.style.setProperty('--muted','#8b7355');
        document.documentElement.style.setProperty('--muted-deep','#5c4a38');
        document.documentElement.style.setProperty('--border','rgba(255,255,255,0.06)');
        document.documentElement.style.setProperty('--border-soft','rgba(255,255,255,0.04)');
        localStorage.setItem('theme','dark');
      } else {
        app.classList.add('light-theme');
        document.documentElement.style.setProperty('--bg','#f5f0e8');
        document.documentElement.style.setProperty('--surface','#ffffff');
        document.documentElement.style.setProperty('--paper','#ffffff');
        document.documentElement.style.setProperty('--card','#ffffff');
        document.documentElement.style.setProperty('--bg2','#f0ebe3');
        document.documentElement.style.setProperty('--ink','#2c2416');
        document.documentElement.style.setProperty('--ink-editor','#2c2416');
        document.documentElement.style.setProperty('--muted','#8b7355');
        document.documentElement.style.setProperty('--muted-deep','#a09080');
        document.documentElement.style.setProperty('--border','rgba(0,0,0,0.08)');
        document.documentElement.style.setProperty('--border-soft','rgba(0,0,0,0.04)');
        localStorage.setItem('theme','light');
      }
    });
    // Restore saved theme
    if (localStorage.getItem('theme') === 'light') btn.click();
  }
})();

// ── Drawer toggles ──
(function setupDrawers() {
  var btnLeft = document.getElementById('btn-toggle-left');
  var leftDrawer = document.getElementById('left-drawer');
  var btnRight = document.getElementById('btn-toggle-right');
  var rightDrawer = document.getElementById('right-drawer');
  var overlay = document.getElementById('drawer-overlay');

  // 遮罩层显示/隐藏
  function updateOverlay() {
    if (!overlay) return;
    var isMobile = document.body.classList.contains('mobile-mode') || window.innerWidth <= 768;
    if (!isMobile) { overlay.classList.remove('visible'); return; }
    var leftOpen = leftDrawer && !leftDrawer.classList.contains('collapsed');
    var rightOpen = rightDrawer && !rightDrawer.classList.contains('collapsed');
    if (leftOpen || rightOpen) { overlay.classList.add('visible'); }
    else { overlay.classList.remove('visible'); }
  }

  if (btnLeft && leftDrawer) {
    btnLeft.addEventListener('click', function(e) {
      e.stopPropagation();
      // 手机端：开左抽屉前先关右抽屉
      if ((document.body.classList.contains('mobile-mode') || window.innerWidth <= 768) && rightDrawer && !rightDrawer.classList.contains('collapsed')) {
        rightDrawer.classList.add('collapsed');
      }
      leftDrawer.classList.toggle('collapsed');
      updateOverlay();
    });
  }
  if (btnRight && rightDrawer) {
    btnRight.addEventListener('click', function(e) {
      e.stopPropagation();
      // 手机端：开右抽屉前先关左抽屉
      if ((document.body.classList.contains('mobile-mode') || window.innerWidth <= 768) && leftDrawer && !leftDrawer.classList.contains('collapsed')) {
        leftDrawer.classList.add('collapsed');
      }
      rightDrawer.classList.toggle('collapsed');
      updateOverlay();
    });
  }
  // Close buttons inside drawers
  var closeLeft = document.getElementById('btn-close-left');
  if (closeLeft && leftDrawer) {
    closeLeft.addEventListener('click', function() { leftDrawer.classList.add('collapsed'); updateOverlay(); });
  }
  var closeRight = document.getElementById('btn-close-right');
  if (closeRight && rightDrawer) {
    closeRight.addEventListener('click', function() { rightDrawer.classList.add('collapsed'); updateOverlay(); });
  }
  // 点击遮罩层关闭所有抽屉
  if (overlay) {
    overlay.addEventListener('click', function() {
      if (leftDrawer) leftDrawer.classList.add('collapsed');
      if (rightDrawer) rightDrawer.classList.add('collapsed');
      updateOverlay();
    });
  }

  // ── Auto-collapse drawers on small screens ──
  function autoCollapseDrawers() {
    var w = window.innerWidth;
    var isMobile = document.documentElement.classList.contains('mobile-mode') || document.body.classList.contains('mobile-mode') || w < 768;
    if (isMobile) {
      if (leftDrawer && !leftDrawer.classList.contains('collapsed')) {
        leftDrawer.classList.add('collapsed');
      }
      // 判断是否处于写作模式：步骤5/6，或者编辑器有内容
      var currentStep = typeof workflowState !== 'undefined' ? workflowState.currentStep : 1;
      var isWritingStep = currentStep === 5 || currentStep === 6;
      var editorContent = document.getElementById('editor-content');
      var hasEditorContent = editorContent && editorContent.textContent && editorContent.textContent.trim().length > 0;
      var isWritingMode = isWritingStep || hasEditorContent;
      
      if (isWritingMode && rightDrawer && rightDrawer.classList.contains('collapsed')) {
        rightDrawer.classList.remove('collapsed');
        rightDrawer.dataset.keepOpen = 'true';
      } else if (!isWritingMode && rightDrawer && !rightDrawer.classList.contains('collapsed') && rightDrawer.dataset.keepOpen !== 'true') {
        rightDrawer.classList.add('collapsed');
      }
      // 确保body有mobile-mode class
      if (!document.body.classList.contains('mobile-mode')) {
        document.body.classList.add('mobile-mode');
      }
      updateOverlay();
    }
  }
  autoCollapseDrawers();
  // 再次延迟检查（确保DOM完全加载）
  setTimeout(autoCollapseDrawers, 500);
  window.addEventListener('resize', updateOverlay);
})();

// ── Focus mode toggle ──
(function setupFocusMode() {
  var btnFocus = document.getElementById('btn-focus');
  var app = document.getElementById('app');
  if (btnFocus && app) {
    btnFocus.addEventListener('click', function() {
      app.classList.toggle('focus-mode');
      var isFocus = app.classList.contains('focus-mode');
      btnFocus.textContent = isFocus ? '✕ 退出专注' : '⚡ 专注模式';
    });
  }
})();


  // ── Add chapter button ──
  async function doAddChapter(volIndex) {
    // 作为 click 处理器被调用时传入的是事件对象，必须过滤，否则 vol_index 会收到 {isTrusted:...} 导致 422
    if (typeof volIndex !== 'number') volIndex = undefined;
    // 使用内联输入框代替 prompt
    let input = document.getElementById('add-chapter-input');
    let panel = document.getElementById('add-chapter-panel');
    if (!panel) {
      // 创建内联输入面板
      panel = document.createElement('div');
      panel.id = 'add-chapter-panel';
      panel.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,0.2);min-width:320px;';
      var volHint = (typeof volIndex !== 'undefined') ? '（卷' + volIndex + '）' : '';
      panel.innerHTML = `
        <div style="font-size:15px;font-weight:600;color:var(--ink);margin-bottom:12px">添加新章节${escHtml(volHint)}</div>
        <input id="add-chapter-input" type="text" placeholder="输入章节标题..." 
          style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:14px;background:var(--bg);color:var(--ink);outline:none;box-sizing:border-box" 
          value="第${chapters.length + 1}章">
        <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
          <button id="add-ch-cancel" style="padding:6px 16px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--muted);cursor:pointer;font-size:13px">取消</button>
          <button id="add-ch-confirm" style="padding:6px 16px;border:none;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer;font-size:13px;font-weight:600">确定</button>
        </div>
      `;
      document.body.appendChild(panel);
      // 绑定事件
      document.getElementById('add-ch-cancel').onclick = () => panel.remove();
      document.getElementById('add-ch-confirm').onclick = async () => {
        const title = document.getElementById('add-chapter-input').value.trim();
        if (!title) return;
        panel.remove();
        await doAddChapterSubmit(title, volIndex);
      };
      document.getElementById('add-chapter-input').addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
          const title = document.getElementById('add-chapter-input').value.trim();
          if (!title) return;
          panel.remove();
          await doAddChapterSubmit(title, volIndex);
        }
        if (e.key === 'Escape') panel.remove();
      });
    }
    // 显示面板
    panel.style.display = 'block';
    setTimeout(() => document.getElementById('add-chapter-input')?.focus(), 50);
  }

  function escHtml(s) { return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; }

  async function doAddChapterSubmit(title, volIndex) {
    try {
      const r = await addChapter(title, volIndex);
      if (r.ok) {
        await loadChaptersFromAPI();
        await loadVolumesData();
        if (chapters.length > 0) {
          currentChapterIndex = chapters.length - 1;
          // 刷新步骤4（写作）的卷导航
          renderVolumeNav('vol-nav-writing', async function(idx) {
            currentChapterIndex = idx;
            renderVolumeNav('vol-nav-writing', arguments.callee);
            await loadChapterContentAPI(idx);
          });
          // 刷新步骤3（章节大纲）的卷导航
          if (typeof renderChapterOutlineEditor === 'function') {
            renderChapterOutlineEditor();
          }
          await loadChapterContentAPI(chapters.length - 1);
        }
        updateWritingToolbar();
        showToast && showToast('章节已添加：' + title);
      } else {
        showToast && showToast('添加失败: ' + (r.error || ''));
      }
    } catch(e) {
      console.error('Add chapter error:', e);
      showToast && showToast('添加失败: ' + e.message);
    }
  }
  $on('btn-add-chapter', 'click', doAddChapter);
  $on('wt-btn-add-ch', 'click', doAddChapter);
  // 蒸馏记忆按钮：打开章节记忆蒸馏面板
  $on('wt-btn-distill', 'click', function() {
    if (typeof openDistillPanel === 'function') openDistillPanel();
  });

document.addEventListener('click', function(e) {
  const mp = document.getElementById('model-popover');
  const pp = document.getElementById('project-picker');
  if (mp && !e.target.closest('#model-popover') && !e.target.closest('#model-badge')) {
    mp.classList.remove('visible');
  }
  if (pp && !e.target.closest('#project-picker') && !e.target.closest('#btn-open-project')) {
    pp.classList.remove('visible');
  }
});

// ── Truth ledger panel (if not already in JS2) ──

// 清空检查结果（供 goToStep 调用，避免跨步骤/跨章节显示旧结果）
function clearValResults() {
  var vDiv = document.getElementById('val-results');
  if (vDiv) vDiv.innerHTML = '<div class="val-empty-hint" style="padding:12px;color:var(--muted);font-size:12px;text-align:center">点击上方检查按钮或AI责编按钮，结果将在这里显示并保留</div>';
  if (typeof lastValResult !== 'undefined') lastValResult = null;
  // 清除所有检查按钮的状态
  document.querySelectorAll('.check-btn').forEach(function(b) {
    b.classList.remove('has-issue', 'done', 'running');
    var origLabel = b.dataset.check;
    if (origLabel) {
      var labels = {drift:'偏差',twist:'转折',duplicate:'重复',style:'风格',conflict:'冲突',timeline:'时间线',quality:'质量',memory:'记忆',completeness:'完整性',continuity:'连贯性',consistency:'一致性',wordcount:'字数预算'};
      b.textContent = labels[origLabel] || origLabel;
    }
  });
}
