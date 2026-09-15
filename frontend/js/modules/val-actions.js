  /* ---- MANUAL FIX RUNNER ---- */
  function runManualFix(issueType, fieldId){
    const el = document.getElementById(fieldId);
    if(el){el.focus();el.classList.add('conflict-highlight');setTimeout(()=>el.classList.remove('conflict-highlight'),3000);showToast('请手动修复');}
  }

  /* ---- VALIDATION ACTION HANDLERS ---- */
  // ═══ 全局模糊匹配函数（valAIFix和valAIFixAll共用）═══
  // 在原文中模糊查找匹配位置，返回 {index, length}，未找到返回 {index:-1, length:0}
  window._fuzzyFind = function(text, target) {
    if (!target || target.length < 5) return { index: -1, length: 0 };
    // 快速路径：精确匹配
    var idx = text.indexOf(target);
    if (idx >= 0) return { index: idx, length: target.length };
    // 去掉首尾引号和标点后再试
    var cleaned = target.replace(/^["""''《]+/, '').replace(/["""''》]+$/, '').trim();
    if (cleaned.length > 10) {
      idx = text.indexOf(cleaned);
      if (idx >= 0) return { index: idx, length: cleaned.length };
    }
    // 取target的前30个字符做模糊匹配
    var prefix = cleaned.substring(0, Math.min(30, cleaned.length));
    if (prefix.length > 10) {
      idx = text.indexOf(prefix);
      if (idx >= 0) return { index: idx, length: cleaned.length };
    }
    // 去掉所有空格和换行后再匹配
    var textNoSpace = text.replace(/\s+/g, '');
    var targetNoSpace = cleaned.replace(/\s+/g, '');
    if (targetNoSpace.length > 10 && textNoSpace.indexOf(targetNoSpace) !== -1) {
      var posNoSpace = textNoSpace.indexOf(targetNoSpace);
      var realPos = 0;
      for (var i = 0; i < posNoSpace; i++) {
        while (realPos < text.length && /\s/.test(text[realPos])) { realPos++; }
        realPos++;
      }
      var endPos = realPos;
      for (var i = 0; i < targetNoSpace.length; i++) {
        while (endPos < text.length && /\s/.test(text[endPos])) { endPos++; }
        endPos++;
      }
      return { index: realPos, length: endPos - realPos };
    }
    // 取target的前20个字符(去空格)做匹配
    var prefixNoSpace = targetNoSpace.substring(0, Math.min(20, targetNoSpace.length));
    if (prefixNoSpace.length > 8 && textNoSpace.indexOf(prefixNoSpace) !== -1) {
      var pos2 = textNoSpace.indexOf(prefixNoSpace);
      var realPos2 = 0;
      for (var i = 0; i < pos2; i++) {
        while (realPos2 < text.length && /\s/.test(text[realPos2])) { realPos2++; }
        realPos2++;
      }
      return { index: realPos2, length: cleaned.length };
    }
    // 取target的中间20个字符做匹配
    if (cleaned.length > 30) {
      var mid = Math.floor(cleaned.length / 2);
      var midPart = cleaned.substring(mid - 10, mid + 10);
      idx = text.indexOf(midPart);
      if (idx >= 0) return { index: idx, length: cleaned.length };
    }
    // bigram相似度滑动窗口匹配（最后兜底）
    var result = window._bigramMatch(text, target);
    if (result.index >= 0) return result;
    return { index: -1, length: 0 };
  };

  // bigram(二元字符组) Jaccard相似度滑动窗口匹配
  window._bigramMatch = function(text, target) {
    if (!target || target.length < 10) return { index: -1, length: 0 };
    function getBigrams(str) {
      var bigrams = {};
      for (var i = 0; i < str.length - 1; i++) {
        var bg = str.substring(i, i + 2);
        bigrams[bg] = (bigrams[bg] || 0) + 1;
      }
      return bigrams;
    }
    function jaccardSimilarity(a, b) {
      var keysA = Object.keys(a);
      var keysB = Object.keys(b);
      var intersection = 0;
      var bSet = {};
      keysB.forEach(function(k) { bSet[k] = true; });
      keysA.forEach(function(k) { if (bSet[k]) intersection++; });
      var union = keysA.length + keysB.length - intersection;
      return union > 0 ? intersection / union : 0;
    }
    var targetBigrams = getBigrams(target);
    var bestScore = 0;
    var bestIdx = -1;
    var bestLen = target.length;
    var paragraphs = text.split(/\n\s*\n/);
    var charOffset = 0;
    for (var p = 0; p < paragraphs.length; p++) {
      var para = paragraphs[p];
      var paraBigrams = getBigrams(para);
      var paraScore = jaccardSimilarity(targetBigrams, paraBigrams);
      if (paraScore > 0.10) {
        var minLen = Math.floor(target.length * 0.7);
        var maxLen = Math.floor(target.length * 1.3);
        var step = Math.max(3, Math.floor(para.length / 80));
        var lenStep = Math.max(1, Math.floor(target.length * 0.05));
        for (var i = 0; i <= para.length - minLen; i += step) {
          for (var len = minLen; len <= maxLen && i + len <= para.length; len += lenStep) {
            var candidate = para.substring(i, i + len);
            var candBigrams = getBigrams(candidate);
            var score = jaccardSimilarity(targetBigrams, candBigrams);
            if (score > bestScore) {
              bestScore = score;
              bestIdx = charOffset + i;
              bestLen = len;
            }
          }
        }
      }
      charOffset += para.length + 2;
    }
    if (bestScore > 0.35) {
      return { index: bestIdx, length: bestLen };
    }
    return { index: -1, length: 0 };
  };

  // AI修复：针对后端格式检查结果（单条）
  // 章节锁定检查：用户手动"定稿"的章节禁止覆盖性AI操作（生成/续写），但允许修复性操作（修复/去AI味）
  function _isChapterLocked(chIdx) {
    if (typeof chapters === 'undefined' || !chapters || chIdx < 0 || chIdx >= chapters.length) return false;
    var ch = chapters[chIdx];
    if (!ch) return false;
    // 只有用户显式标记 locked=true 的章节才锁定
    return ch.locked === true;
  }
  // 挂载到全局，供 validate-ui.js 等其他模块使用
  window._isChapterLocked = _isChapterLocked;

  window.valAIFix = async function(btn) {
    // 锁定当前章节索引，防止异步修复过程中用户切章导致保存到错误章节
    var _fixChapterIndex = currentChapterIndex;
    // AI修复允许在锁定章节上执行（用于修复时间线对照发现的问题）
    // 但需要二次确认，防止误操作
    if (_isChapterLocked(_fixChapterIndex)) {
      if (!confirm('🔒 第' + (_fixChapterIndex+1) + '章已锁定（定稿）。\n\n确定要进行AI修复吗？\n\n修复将修改正文内容以解决对照发现的问题。')) {
        return;
      }
    }
    // 草稿模式下禁止重复修复，避免丢失成品快照
    if (window.DraftManager && DraftManager.isActive()) {
      showToast('⚠️ 请先采纳或丢弃当前草稿，再进行修复');
      return;
    }
    var row = btn.closest('div[style]') && btn.closest('div[style]').parentNode;
    if (!row) row = btn.closest('div');
    var textEl = row.querySelector('.val-text');
    if (!textEl) return;
    var problemText = textEl.innerText || textEl.textContent;
    var checkType = lastValResult ? lastValResult.check_type : 'unknown';

    btn.disabled = true;
    btn.textContent = '⏳ 修复中…';
    showToast('AI正在修复…');

    // 超时保护：120秒后自动恢复按钮
    var fixTimeout = setTimeout(function() {
      btn.disabled = false;
      btn.textContent = '🤖 AI修复';
      showToast('⚠️ 修复超时（120秒），请重试或手动修复');
    }, 120000);

    // 进度提示：每15秒更新按钮文字
    var elapsed = 0;
    var progressTimer = setInterval(function() {
      elapsed += 15;
      if (elapsed < 120) {
        btn.textContent = '⏳ 修复中…(' + elapsed + 's)';
      }
    }, 15000);

    try {
      var editorEl = document.getElementById('editor-content');
      var currentText = editorEl ? editorEl.innerText : '';
      if (!currentText || currentText.length < 50) {
        showToast('❌ 编辑器中没有正文内容');
        clearTimeout(fixTimeout);
        clearInterval(progressTimer);
        btn.disabled = false;
        btn.textContent = '🤖 AI修复';
        return;
      }

      // 局部修复策略：从 lastValResult.structured.issues 提取位置信息，
      // 调用 /api/validate/fix/chapter 进行段落级精准修复
      var issuesForFix = [];
      if (lastValResult && lastValResult.structured && lastValResult.structured.issues
          && lastValResult.structured.issues.length > 0) {
        // 有结构化 issues：逐项转换
        lastValResult.structured.issues.forEach(function(issue) {
          issuesForFix.push({
            check_type: checkType,
            description: issue.description || issue.type || '',
            location: issue.location || '',
            suggestion: issue.suggestion || '',
            severity: issue.severity || 'medium',
          });
        });
      } else {
        // 兜底：无结构化 issues，把整段问题描述作为一个无 location 的问题
        issuesForFix.push({
          check_type: checkType,
          description: problemText.substring(0, 500),
          location: '',
          suggestion: '',
          severity: 'medium',
        });
      }

      var r = await api('/api/validate/fix/chapter', {
        method: 'POST',
        body: JSON.stringify({
          chapter_index: _fixChapterIndex,
          issues: issuesForFix,
          dry_run: false
        })
      });
      clearTimeout(fixTimeout);
      clearInterval(progressTimer);
      if (r.ok) {
        var fixedCount = r.fixed || 0;
        var skippedLocate = r.skipped_locate || 0;
        var skippedFailed = r.skipped_failed || 0;

        // 重新加载章节内容（修复已在后端保存）
        var newContent = currentText;
        try {
          var loadResult = await api('/api/chapter/load?index=' + _fixChapterIndex);
          if (loadResult && loadResult.ok && loadResult.content) {
            newContent = loadResult.content;
          }
        } catch(e) { console.warn('Reload chapter failed:', e); }

        if (newContent.length < 50) {
          showToast('⚠️ 修复后内容过短，未做修改');
          btn.disabled = false;
          btn.textContent = '🤖 AI修复';
          return;
        }

        // 安全检查：字数变化超过50%则阻止
        var lengthChange = Math.abs(newContent.length - currentText.length) / currentText.length;
        if (lengthChange > 0.5) {
          showToast('⚠️ 修复后字数变化' + Math.round(lengthChange*100) + '%，已阻止保存请检查');
          btn.disabled = false;
          btn.textContent = '🤖 AI修复';
          return;
        }

        if (editorEl) {
          // 修复结果写入草稿，不直接替换成品
          if (window.DraftManager) {
            await DraftManager.enter(newContent);
            showToast('修复完成：修复' + fixedCount + '项' +
                      (skippedLocate > 0 ? '，跳过' + skippedLocate + '项无法定位' : '') +
                      '（草稿模式，请确认）');
          } else {
            editorEl.innerHTML = textToHTML(newContent);
            updateWordCount();
            if (typeof _fixChapterIndex !== 'undefined' && _fixChapterIndex >= 0) {
              try {
                await saveChapter(_fixChapterIndex, newContent);
                showToast('✅ 修复完成：修复' + fixedCount + '项 | ' + currentText.length + '→' + newContent.length + '字');
              } catch(e) {
                showToast('✅ 修复完成并写入编辑器（保存失败：' + e.message + '）');
              }
            } else {
              showToast('✅ 修复完成并写入编辑器');
            }
          }
          row.style.borderLeftColor = 'var(--success)';
          btn.style.background = 'var(--success)';
          btn.textContent = '✅ 已修复';
          // 3秒后恢复按钮文字
          setTimeout(function() {
            btn.textContent = '🤖 AI修复';
            btn.style.background = 'var(--accent)';
          }, 3000);
        }

      } else {
        showToast('❌ 修复失败：' + (r.error || 'AI未返回内容'));
      }
      btn.disabled = false;
      btn.textContent = '🤖 AI修复';
    } catch(e) {
      clearTimeout(fixTimeout);
      clearInterval(progressTimer);
      showToast('❌ ' + e.message);
      btn.disabled = false;
      btn.textContent = '🤖 AI修复';
    }
  };

  // 一键综合修复：把所有检查问题综合起来一次性修复
  window.valAIFixAll = async function() {
    // 锁定当前章节索引，防止异步修复过程中用户切章导致保存到错误章节
    var _fixAllChapterIndex = currentChapterIndex;
    // AI修复允许在锁定章节上执行（用于修复时间线对照发现的问题）
    if (_isChapterLocked(_fixAllChapterIndex)) {
      if (!confirm('🔒 第' + (_fixAllChapterIndex+1) + '章已锁定（定稿）。\n\n确定要进行AI批量修复吗？\n\n修复将修改正文内容以解决对照发现的问题。')) {
        return;
      }
    }
    // 草稿模式下禁止批量修复
    if (window.DraftManager && DraftManager.isActive()) {
      showToast('⚠️ 请先采纳或丢弃当前草稿，再进行批量修复');
      return;
    }
    var problems = window._allValProblems || [];
    
    // 兜底：如果 problems 为空，从当前 DOM 中重新提取问题列表
    if (!problems.length) {
      var vDiv = document.getElementById('val-results');
      if (vDiv) {
        var issueItems = vDiv.querySelectorAll('.check-result-item');
        issueItems.forEach(function(item) {
          var textEl = item.querySelector('.val-text');
          var checkType = item.dataset.check || '';
          if (textEl) {
            var text = textEl.innerText || textEl.textContent || '';
            // v4判断逻辑：结论优先（含问题指示检查）+全部否定前缀+清洗文本法
            var _fNeg = ['不一致','不符合','不连贯','不自然','不协调','不合理','不自洽','不匹配','不对齐'];
            var _fNegPrefixes = ['无明显','没有','不存在','未发现','未发现明显','未检测到','无'];
            var _fNoIssue = ['无矛盾','无冲突','无偏离','无重复','没有重复','不存在重复','无问题','没有问题','没有发现','未发现','未检测到','未检测到问题','无遗漏','没有遗漏','未发现明显','无明显问题','一致','符合','通过','对齐','无异常','正常','衔接正常','数据一致','未发现偏离','未发现冲突','未发现矛盾','未发现重复','未发现遗漏','ok','none'];
            var _fIssue = ['偏离','矛盾','冲突','断裂','遗漏','缺乏','缺失','生硬','突兀','混乱','错误','需改进','显著','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
            // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
            var fTail = text.substring(Math.max(0, text.length - 80));
            var fTailIsNoIssue = false;
            if (fTail.includes('结论') || fTail.includes('整体评价') || fTail.includes('总结')) {
              // 找到最后一个结论关键词位置，只看结论之后的内容
              var fConclStart = Math.max(fTail.lastIndexOf('结论'), fTail.lastIndexOf('整体评价'), fTail.lastIndexOf('总结'));
              var fConclText = fTail.substring(fConclStart);
              // 生成全部否定前缀+问题词的无问题模式
              var fTailExtra = [];
              for (var fte = 0; fte < _fIssue.length; fte++) {
                for (var fnp2 = 0; fnp2 < _fNegPrefixes.length; fnp2++) { fTailExtra.push(_fNegPrefixes[fnp2] + _fIssue[fte]); }
              }
              var fTailAllNo = _fNoIssue.concat(fTailExtra);
              var fTailHasNo = fTailAllNo.some(function(p){ return fConclText.includes(p); });
              if (fTailHasNo) {
                // 清洗结论句
                var fCleanedConcl = fConclText;
                var fSortedConcl = fTailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
                fSortedConcl.forEach(function(p) { fCleanedConcl = fCleanedConcl.split(p).join(''); });
                var fConclHasIssue = _fIssue.some(function(p){ return fCleanedConcl.includes(p); });
                if (!fConclHasIssue) { fTailIsNoIssue = true; }
              }
            }
            var fHasIssue = false;
            if (fTailIsNoIssue) {
              fHasIssue = false;
            } else {
              // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语
              var fNegatedText = text;
              // 处理一般问题词
              for (var fnp4 = 0; fnp4 < _fNegPrefixes.length; fnp4++) {
                for (var fip4 = 0; fip4 < _fIssue.length; fip4++) {
                  try {
                    var fEscPrefix = _fNegPrefixes[fnp4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var fEscIssue = _fIssue[fip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var fRe = new RegExp(fEscPrefix + '[^，。！？；]{0,6}' + fEscIssue, 'g');
                    fNegatedText = fNegatedText.replace(fRe, '');
                  } catch(e){console.warn('[Audit]', e)}
                }
              }
              // 也处理否定形式问题词（不一致、不符合等）
              for (var fnp5 = 0; fnp5 < _fNegPrefixes.length; fnp5++) {
                for (var fnip5 = 0; fnip5 < _fNeg.length; fnip5++) {
                  try {
                    var fEscP2 = _fNegPrefixes[fnp5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var fEscI2 = _fNeg[fnip5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var fRe2 = new RegExp(fEscP2 + '[^，。！？；]{0,6}' + fEscI2, 'g');
                    fNegatedText = fNegatedText.replace(fRe2, '');
                  } catch(e){console.warn('[Audit]', e)}
                }
              }
              // 第1步：检查否定形式的问题词（在negatedText上检查）
              var fNegHit = false;
              for (var fi = 0; fi < _fNeg.length; fi++) {
                if (fNegatedText.includes(_fNeg[fi])) { fNegHit = true; break; }
              }
              if (fNegHit) {
                fHasIssue = true;
              } else {
                var _fExtra = [];
                for (var fe = 0; fe < _fIssue.length; fe++) {
                  for (var fenp = 0; fenp < _fNegPrefixes.length; fenp++) { _fExtra.push(_fNegPrefixes[fenp] + _fIssue[fe]); }
                }
                var _fAllNo = _fNoIssue.concat(_fExtra);
                var fNoIssue = _fAllNo.some(function(p){ return fNegatedText.includes(p); });
                if (fNoIssue) {
                  var fCleaned = fNegatedText;
                  var fSorted = _fAllNo.slice().sort(function(a,b){ return b.length - a.length; });
                  fSorted.forEach(function(p) { fCleaned = fCleaned.split(p).join(''); });
                  fHasIssue = _fIssue.some(function(p){ return fCleaned.includes(p); });
                } else {
                  fHasIssue = _fIssue.some(function(p){ return fNegatedText.includes(p); });
                }
              }
            }
            if (fHasIssue) {
              problems.push({type: checkType, problem: text.substring(0, 500)});
            }
          }
        });
        // 保存到全局变量供后续使用
        window._allValProblems = problems;
      }
    }
    
    if (!problems.length) { showToast('没有需要修复的问题'); return; }
    
    var editorEl = document.getElementById('editor-content');
    if (!editorEl) { showToast('找不到编辑器'); return; }
    var currentText = editorEl.innerText || '';
    
    // 如果编辑器里没有内容，从后端加载
    if (!currentText.trim()) {
      try {
        var chIdx = typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0;
        var loaded = await api('/api/chapter/load?index=' + chIdx);
        if (loaded && loaded.ok && loaded.content) {
          currentText = loaded.content;
          // 同时把内容显示到编辑器
          if (editorEl) editorEl.innerHTML = textToHTML ? textToHTML(currentText) : currentText.replace(/\n/g, '<br>');
        }
      } catch(e) { console.error('Load chapter for fix failed:', e); }
    }
    if (!currentText.trim()) { showToast('没有正文内容，请先生成正文'); return; }
    
    // 按类型分批修复：内容类 vs 风格类
    var contentTypes = ['drift', 'timeline', 'conflict', 'consistency', 'continuity', 'completeness'];
    var styleTypes = ['style', 'duplicate', 'twist'];
    var contentProblems = problems.filter(function(p) { return contentTypes.indexOf(p.type) >= 0; });
    var styleProblems = problems.filter(function(p) { return styleTypes.indexOf(p.type) >= 0; });
    // 兜底：未分类的问题归入当前批次
    var unclassified = problems.filter(function(p) { return contentTypes.indexOf(p.type) < 0 && styleTypes.indexOf(p.type) < 0; });
    if (unclassified.length > 0) {
      if (contentProblems.length > 0) contentProblems = contentProblems.concat(unclassified);
      else styleProblems = styleProblems.concat(unclassified);
    }
    // 当前批次：优先处理内容类（更关键）
    var currentBatch = contentProblems.length > 0 ? contentProblems : styleProblems;
    var batchLabel = contentProblems.length > 0 ? '内容修复' : '风格润色';

    // 构建当前批次问题列表
    var problemList = '';
    currentBatch.forEach(function(p, i) {
      problemList += (i+1) + '. 【' + p.type + '】' + p.problem + '\n';
    });

    // 找到按钮并禁用
    var fixAllBtn = document.querySelector('#fix-all-bar button');
    if (fixAllBtn) { fixAllBtn.disabled = true; fixAllBtn.textContent = '⏳ ' + batchLabel + '中…'; }
    showToast('AI正在' + batchLabel + '（' + currentBatch.length + '项问题）…');

    // 超时保护：180秒后自动恢复按钮（多问题需要更长时间）
    var fixAllTimeout = setTimeout(function() {
      if (fixAllBtn) { fixAllBtn.disabled = false; fixAllBtn.textContent = '🤖 一键全部修复'; }
      showToast('⚠️ 综合修复超时（180秒），请重试');
    }, 180000);

    // 进度提示
    var allElapsed = 0;
    var allProgressTimer = setInterval(function() {
      allElapsed += 15;
      if (allElapsed < 180 && fixAllBtn) {
        fixAllBtn.textContent = '⏳ 综合修复中…(' + allElapsed + 's)';
      }
    }, 15000);

    try {
      // 收集当前章节大纲，供修复时参考
      var chapterOutlineText = '';
      try {
        var chIdx2 = typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0;
        if (typeof chapters !== 'undefined' && chapters && chapters[chIdx2]) {
          var ol2 = chapters[chIdx2].outline || '';
          if (ol2 && typeof ol2 === 'string' && ol2.trim().length > 5) {
            chapterOutlineText = ol2;
          } else if (ol2 && Array.isArray(ol2) && ol2.length > 0) {
            chapterOutlineText = ol2.map(function(o) { return typeof o === 'string' ? o : (o.text || ''); }).join('\n');
          }
        }
      } catch(e){console.warn('[Audit]', e)}

      // 构建结构化问题列表（转换为局部修复所需格式）
      var issuesForFix = [];
      currentBatch.forEach(function(p) {
        if (p.issues && p.issues.length > 0) {
          p.issues.forEach(function(issue) {
            issuesForFix.push({
              check_type: p.type,
              description: issue.description || issue.type || '',
              location: issue.location || '',
              suggestion: issue.suggestion || '',
              severity: issue.severity || 'medium',
            });
          });
        } else {
          issuesForFix.push({
            check_type: p.type,
            description: p.problem || '',
            location: '',
            suggestion: '',
            severity: 'medium',
          });
        }
      });

      var r = await api('/api/validate/fix/chapter', {
        method: 'POST',
        body: JSON.stringify({
          chapter_index: _fixAllChapterIndex,
          issues: issuesForFix,
          dry_run: false
        })
      });
      clearTimeout(fixAllTimeout);
      clearInterval(allProgressTimer);
      if (r.ok) {
        var fixedCount = r.fixed || 0;
        var skippedLocate = r.skipped_locate || 0;
        var skippedCross = r.skipped_cross || 0;
        var skippedFailed = r.skipped_failed || 0;
        
        // 重新加载章节内容（修复已在后端保存）
        try {
          var loadResult = await api('/api/chapter/load?index=' + _fixAllChapterIndex);
          if (loadResult && loadResult.ok && loadResult.content) {
            var newContent = loadResult.content;
            var oldWordCount = currentText.length;
            var newWordCount = newContent.length;
            var wordChange = newWordCount - oldWordCount;
            
            if (window.DraftManager) {
              await DraftManager.enter(newContent);
              showToast(batchLabel + '完成：修复' + fixedCount + '项，跳过' + skippedLocate + '项无法定位（草稿模式，请确认）');
              if (fixAllBtn) { fixAllBtn.disabled = false; fixAllBtn.textContent = '✅ ' + batchLabel + '完成'; fixAllBtn.style.background = 'var(--success)'; }
            } else {
              editorEl.innerHTML = textToHTML(newContent);
              updateWordCount();
              if (typeof chapters !== 'undefined' && chapters[_fixAllChapterIndex]) {
                chapters[_fixAllChapterIndex].content = newContent;
                chapters[_fixAllChapterIndex].word_count = newContent.length;
              }
              showToast('✅ ' + batchLabel + '完成：修复' + fixedCount + '项，跳过' + skippedLocate + '项无法定位 | ' + oldWordCount + '→' + newWordCount + '字');
              if (fixAllBtn) { fixAllBtn.disabled = false; fixAllBtn.textContent = '✅ ' + batchLabel + '完成'; fixAllBtn.style.background = 'var(--success)'; }
            }
            
            var vDivFix = document.getElementById('val-results');
            if (vDivFix) {
              var summaryBar = document.createElement('div');
              summaryBar.style.cssText = 'padding:10px 12px;margin:4px 0 8px;border-radius:6px;background:var(--accent-soft);border:1px solid var(--accent);font-size:12px';
              var summaryHtml = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">';
              summaryHtml += '<strong class="text-accent">' + batchLabel + '摘要</strong>';
              summaryHtml += '<span>已修复' + fixedCount + '项</span>';
              if (skippedLocate > 0) summaryHtml += '<span style="color:var(--warn)">跳过' + skippedLocate + '项无法定位</span>';
              if (skippedCross > 0) summaryHtml += '<span class="text-muted">跳过' + skippedCross + '项跨章节问题</span>';
              if (skippedFailed > 0) summaryHtml += '<span class="text-danger">失败' + skippedFailed + '项</span>';
              summaryHtml += '<span style="color:' + (Math.abs(wordChange) > oldWordCount * 0.1 ? 'var(--danger)' : 'var(--muted)') + '">字数: ' + oldWordCount + '→' + newWordCount + (wordChange >= 0 ? '(+' + wordChange + ')' : '(' + wordChange + ')') + '</span>';
              if (Math.abs(wordChange) > oldWordCount * 0.1) {
                summaryHtml += '<span style="color:var(--danger);font-weight:600">⚠ 字数变化超10%</span>';
              }
              var otherBatch = contentProblems.length > 0 ? styleProblems : contentProblems;
              if (otherBatch.length > 0) {
                var nextLabel = contentProblems.length > 0 ? '风格润色' : '内容修复';
                summaryHtml += '<button id="btn-fix-next-batch" style="background:var(--warn);color:#000;border:none;border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">🔧 ' + nextLabel + '（' + otherBatch.length + '项）</button>';
              }
              summaryHtml += '<button id="btn-recheck" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer;margin-left:auto">🔍 重新检查</button>';
              summaryHtml += '</div>';
              summaryBar.innerHTML = summaryHtml;
              vDivFix.insertBefore(summaryBar, vDivFix.firstChild);
              
              var recheckBtn = document.getElementById('btn-recheck');
              if (recheckBtn) {
                recheckBtn.addEventListener('click', function() {
                  var runBtn = document.getElementById('btn-run-checks');
                  if (runBtn) runBtn.click();
                });
              }
          // 绑定"修复下一批"按钮
          var nextBatchBtn = document.getElementById('btn-fix-next-batch');
          if (nextBatchBtn) {
            nextBatchBtn.addEventListener('click', function() {
              window._allValProblems = otherBatch;
              window.valAIFixAll && valAIFixAll();
            });
          }

          // 自动复检：修复完成3秒后自动触发重新检查（检测→修复→复检闭环）
          // 如果修复后还有未解决的问题，显示提示
          var autoRecheckTimer = setTimeout(function() {
            // 只在无其他待处理批次时自动复检
            if (otherBatch.length === 0) {
              var runBtn = document.getElementById('btn-run-checks');
              if (runBtn) {
                // 在复检按钮旁显示自动复检提示
                var autoTag = document.createElement('span');
                autoTag.style.cssText = 'font-size:10px;color:var(--accent);opacity:0.7;margin-left:4px';
                autoTag.textContent = '🔄 自动复检中…';
                recheckBtn.parentNode.insertBefore(autoTag, recheckBtn.nextSibling);
                runBtn.click();
                // 复检完成后移除提示
                setTimeout(function() { if (autoTag.parentNode) autoTag.remove(); }, 60000);
              }
            }
          }, 3000);
          // 结束 if(vDivFix)
          }
          // 结束 if(loadResult && loadResult.ok)
          }
        } catch(e) { console.warn('Load chapter for fix failed:', e); }
      } else {
        showToast('❌ 修复失败: ' + (r.error || '未知错误'));
        if (fixAllBtn) { fixAllBtn.disabled = false; fixAllBtn.textContent = '🤖 一键全部修复'; }
      }
    } catch(e) {
      clearTimeout(fixAllTimeout);
      clearInterval(allProgressTimer);
      showToast('❌ ' + e.message);
      if (fixAllBtn) { fixAllBtn.disabled = false; fixAllBtn.textContent = '🤖 一键全部修复'; }
    }
  };
  window.valManualFix = function(btn) {
    var row = btn.closest('div[style]') && btn.closest('div[style]').parentNode;
    if (!row) row = btn.closest('div');
    var textEl = row.querySelector('.val-text');
    var problemText = textEl ? (textEl.innerText || textEl.textContent).trim() : '';
    
    // 先定位
    window.valLocate(btn);
    
    // 聚焦编辑器
    var editorEl = document.getElementById('editor-content');
    if (editorEl) {
      editorEl.focus();
      editorEl.classList.add('conflict-highlight');
      setTimeout(function() { editorEl.classList.remove('conflict-highlight'); }, 3000);
      showToast('✏️ 请手动修改，完成后保存');
    }
    
    // 按钮状态更新
    btn.textContent = '✏️ 修改中…';
    btn.style.background = 'var(--success)';
  };

  // 定位：在编辑器中高亮问题文本（支持全文模式跨章节跳转）
  window.valLocate = async function(btn) {
    var row = btn.closest('div[style]') && btn.closest('div[style]').parentNode;
    if (!row) row = btn.closest('div');
    var textEl = row.querySelector('.val-text');
    if (!textEl) return;
    var problemText = (textEl.innerText || textEl.textContent).trim();

    // 判断当前步骤：步骤4使用editor-content，步骤1-3使用detail-editor-textarea
    var currentStep = typeof workflowState !== 'undefined' ? workflowState.currentStep : 4;
    var isDetailMode = currentStep !== 4;
    var editorEl = document.getElementById(isDetailMode ? 'detail-editor-textarea' : 'editor-content');
    if (!editorEl) { showToast('编辑器未找到'); return; }

    // 提取候选关键词（与原逻辑一致）
    var candidates = [];
    var quotePatterns = [
      /"([^"]{3,80})"/g,
      /"([^"]{3,80})"/g,
      /「([^」]{3,80})」/g,
      /『([^』]{3,80})』/g,
      /\*\*([^*]{3,80})\*\*/g
    ];
    quotePatterns.forEach(function(re) {
      var m;
      while ((m = re.exec(problemText)) !== null) {
        candidates.push(m[1].trim());
      }
    });
    var descRe = /(?:写道|提到|描写|说道|指出|明确)[：:]\s*["「『]?([^"\n]{3,60})/g;
    var dm;
    while ((dm = descRe.exec(problemText)) !== null) {
      candidates.push(dm[1].trim());
    }
    var listRe = /[-•]\s*([^\n]{3,60})/g;
    var lm;
    while ((lm = listRe.exec(problemText)) !== null) {
      candidates.push(lm[1].trim());
    }
    var exampleRe = /(?:如|例如|比如)[：:]\s*["「『]?([^"\n]{3,60})/g;
    var em;
    while ((em = exampleRe.exec(problemText)) !== null) {
      candidates.push(em[1].trim());
    }
    var seen = {};
    candidates = candidates.filter(function(c) {
      var key = c.substring(0, 20);
      if (seen[key]) return false;
      seen[key] = true;
      return c.length >= 3;
    });

    // 清理候选词的标点
    var cleanCandidates = candidates.map(function(c) {
      return c.replace(/[。，；：！？、]/g, '');
    }).filter(function(c) { return c.length >= 3; });

    // 第1步：在当前章节编辑器中搜索
    var editorText = isDetailMode ? editorEl.value : editorEl.innerText;
    if (!isDetailMode) _clearHighlights(editorEl);

    var matchCount = 0;
    for (var i = 0; i < cleanCandidates.length; i++) {
      var phrase = cleanCandidates[i];
      var idx = editorText.indexOf(phrase);
      if (idx >= 0) {
        matchCount++;
        _highlightInEditor(editorEl, phrase, matchCount === 1);
      } else {
        var short = phrase.substring(0, 10);
        if (short.length >= 3) {
          idx = editorText.indexOf(short);
          if (idx >= 0) {
            matchCount++;
            _highlightInEditor(editorEl, short, matchCount === 1);
          }
        }
      }
    }
    if (matchCount > 0) {
      showToast('📍 已定位 ' + matchCount + ' 处问题位置');
      return;
    }

    // 第2步：当前章节没找到 → 优先从结果项的chapterIndex标记获取
    var targetChapterIdx = -1;
    if (row && row.dataset && row.dataset.chapterIndex !== undefined) {
      targetChapterIdx = parseInt(row.dataset.chapterIndex);
      if (isNaN(targetChapterIdx)) targetChapterIdx = -1;
    }
    
    // 如果没有标记，从问题文本提取章节号
    if (targetChapterIdx < 0) {
      var chapterNumMatch = problemText.match(/第\s*([0-9一二三四五六七八九十百]+)\s*[章节幕]/);
      if (chapterNumMatch) {
        var numStr = chapterNumMatch[1];
        var num = 0;
        if (/^[0-9]+$/.test(numStr)) {
          num = parseInt(numStr);
        } else {
          var cnMap = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10};
          if (numStr === '十') num = 10;
          else if (numStr.length === 2 && numStr[0] === '十') num = 10 + (cnMap[numStr[1]]||0);
          else if (numStr.length === 2 && numStr[1] === '十') num = (cnMap[numStr[0]]||0) * 10;
          else if (numStr.length === 3 && numStr[1] === '十') num = (cnMap[numStr[0]]||0) * 10 + (cnMap[numStr[2]]||0);
          else num = cnMap[numStr] || 0;
        }
        if (num > 0) targetChapterIdx = num - 1;
      }
    }

    // 第3步：如果有目标章节且不是当前章节，切换并搜索
    if (targetChapterIdx >= 0 && targetChapterIdx !== currentChapterIndex && typeof chapters !== 'undefined' && targetChapterIdx < chapters.length) {
      showToast('📍 跳转到第' + (targetChapterIdx + 1) + '章定位…');
      // 切换章节
      if (typeof loadChapterContentAPI === 'function') {
        await loadChapterContentAPI(targetChapterIdx);
        await new Promise(function(r) { setTimeout(r, 800); }); // 等待内容加载
      }
      editorEl = document.getElementById(isDetailMode ? 'detail-editor-textarea' : 'editor-content');
      if (!editorEl) return;
      editorText = isDetailMode ? editorEl.value : editorEl.innerText;
      if (!isDetailMode) _clearHighlights(editorEl);
      for (var i2 = 0; i2 < cleanCandidates.length; i2++) {
        var phrase2 = cleanCandidates[i2];
        var idx2 = editorText.indexOf(phrase2);
        if (idx2 >= 0) {
          matchCount++;
          _highlightInEditor(editorEl, phrase2, matchCount === 1);
        } else {
          var short2 = phrase2.substring(0, 10);
          if (short2.length >= 3) {
            idx2 = editorText.indexOf(short2);
            if (idx2 >= 0) {
              matchCount++;
              _highlightInEditor(editorEl, short2, matchCount === 1);
            }
          }
        }
      }
      if (matchCount > 0) {
        showToast('📍 已在第' + (targetChapterIdx + 1) + '章定位 ' + matchCount + ' 处问题');
        return;
      }
    }

    // 第4步：没有明确章节号，遍历所有章节搜索
    if (typeof chapters !== 'undefined' && chapters.length > 1 && cleanCandidates.length > 0) {
      var bestChapter = -1;
      var bestMatchPhrase = '';
      for (var ci = 0; ci < chapters.length; ci++) {
        if (ci === currentChapterIndex) continue; // 当前章节已搜过
        try {
          var chData = await api('/api/chapter/load?index=' + ci);
          if (chData && chData.content) {
            for (var ci2 = 0; ci2 < cleanCandidates.length; ci2++) {
              if (chData.content.indexOf(cleanCandidates[ci2]) >= 0) {
                bestChapter = ci;
                bestMatchPhrase = cleanCandidates[ci2];
                break;
              }
            }
          }
        } catch(e){console.warn('[Audit]', e)}
        if (bestChapter >= 0) break;
      }
      if (bestChapter >= 0) {
        showToast('📍 跳转到第' + (bestChapter + 1) + '章定位…');
        if (typeof loadChapterContentAPI === 'function') {
          await loadChapterContentAPI(bestChapter);
          await new Promise(function(r) { setTimeout(r, 800); });
        }
        editorEl = document.getElementById(isDetailMode ? 'detail-editor-textarea' : 'editor-content');
        if (editorEl) {
          if (!isDetailMode) _clearHighlights(editorEl);
          _highlightInEditor(editorEl, bestMatchPhrase, true);
          showToast('📍 已在第' + (bestChapter + 1) + '章定位到问题');
          return;
        }
      }
    }

    // 第5步：所有策略都失败，回退到关键词搜索（当前章节）
    showToast('未在当前章节中找到匹配，尝试关键词搜索…');
    var keywords = [];
    if (typeof worldSettings !== 'undefined' && worldSettings.length) {
      worldSettings.forEach(function(s) {
        if (s.key && s.key.length >= 2 && s.key.length <= 10) keywords.push(s.key);
      });
    }
    if (typeof chapters !== 'undefined' && chapters.length) {
      chapters.forEach(function(ch) {
        var title = ch.title || '';
        var m = title.match(/·([^·]+)$/);
        if (m && m[1]) keywords.push(m[1]);
      });
    }
    var cnWordRe = /[\u4e00-\u9fa5]{2,4}/g;
    var wm;
    while ((wm = cnWordRe.exec(problemText)) !== null) {
      if (keywords.indexOf(wm[0]) < 0) keywords.push(wm[0]);
    }

    editorText = isDetailMode ? editorEl.value : editorEl.innerText;
    for (var j = 0; j < keywords.length; j++) {
      var kidx = editorText.indexOf(keywords[j]);
      if (kidx >= 0) {
        matchCount++;
        _highlightInEditor(editorEl, keywords[j], matchCount === 1);
      }
    }

    if (matchCount > 0) {
      showToast('📍 已定位 ' + matchCount + ' 处关键词位置');
    } else {
      showToast('未找到匹配文本，可能问题在其他章节');
    }
  };

  // 清除高亮
  function _clearHighlights(editorEl) {
    editorEl.querySelectorAll('.locate-highlight').forEach(function(el) {
      var parent = el.parentNode;
      if (parent) {
        parent.insertBefore(document.createTextNode(el.textContent), el);
        parent.removeChild(el);
        parent.normalize();
      }
    });
  }

  // 在编辑器中高亮指定文本（scroll=true时滚动到第一个）
  function _highlightInEditor(editorEl, phrase, scroll) {
    // 如果是textarea（详情编辑器模式），使用selectionStart/End高亮
    if (editorEl.tagName === 'TEXTAREA') {
      var val = editorEl.value;
      var pos = val.indexOf(phrase);
      if (pos >= 0) {
        editorEl.focus();
        editorEl.setSelectionRange(pos, pos + phrase.length);
        // 计算滚动位置，使选中文本居中
        if (scroll) {
          var lineHeight = parseInt(getComputedStyle(editorEl).lineHeight) || 20;
          var linesBefore = val.substring(0, pos).split('\n').length - 1;
          editorEl.scrollTop = Math.max(0, linesBefore * lineHeight - editorEl.clientHeight / 2);
        }
      }
      return;
    }
    
    // contenteditable模式（步骤4写作编辑器）
    var walker = document.createTreeWalker(editorEl, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode()) !== null) {
      var pos = node.textContent.indexOf(phrase);
      if (pos >= 0) {
        var range = document.createRange();
        range.setStart(node, pos);
        range.setEnd(node, pos + phrase.length);

        var span = document.createElement('span');
        span.className = 'locate-highlight';
        span.style.cssText = 'background:var(--warn);color:#000;padding:1px 2px;border-radius:2px;font-weight:600';
        try {
          range.surroundContents(span);
          if (scroll) {
            span.scrollIntoView({behavior:'smooth', block:'center'});
          }
        } catch(e) {
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          if (scroll) {
            node.parentElement.scrollIntoView({behavior:'smooth', block:'center'});
          }
        }
        return;
      }
    }
  }

  // AI修复：针对旧格式多条结果
  window.valAIFixItem = async function(btn, idx) {
    if (window.DraftManager && DraftManager.isActive()) {
      showToast('⚠️ 请先采纳或丢弃当前草稿，再进行修复');
      return;
    }
    if (!lastValResult || !lastValResult.results) return;
    var item = lastValResult.results[idx];
    if (!item) return;
    var _fixChapterIndex = currentChapterIndex;

    btn.disabled = true;
    btn.textContent = '⏳';
    showToast('AI修复中…');

    try {
      var editorEl = document.getElementById('editor-content');
      var currentText = editorEl ? editorEl.innerText : '';

      // 局部修复策略：构造结构化问题，调用 /api/validate/fix/chapter
      var checkType = item.check || item.label || 'unknown';
      var problemDesc = item.msg || item.description || '';
      var location = item.location || '';
      var issuesForFix = [{
        check_type: checkType,
        description: problemDesc,
        location: location,
        suggestion: item.suggestion || '',
        severity: item.severity || 'medium',
      }];

      var r = await api('/api/validate/fix/chapter', {
        method: 'POST',
        body: JSON.stringify({
          chapter_index: _fixChapterIndex,
          issues: issuesForFix,
          dry_run: false
        })
      });

      if (r.ok && editorEl) {
        var fixedCount = r.fixed || 0;
        // 重新加载章节内容（修复已在后端保存）
        var newContent = currentText;
        try {
          var loadResult = await api('/api/chapter/load?index=' + _fixChapterIndex);
          if (loadResult && loadResult.ok && loadResult.content) {
            newContent = loadResult.content;
          }
        } catch(e) { console.warn('Reload chapter failed:', e); }

        if (newContent.length < currentText.length * 0.7) {
          showToast('⚠️ AI修复后内容大幅缩短（' + currentText.length + '→' + newContent.length + '字），已保留原文');
          btn.disabled = false;
          btn.textContent = '🤖';
          return;
        }
        // 通过DraftManager进入草稿模式，避免AutoSave直接覆盖成品
        if (window.DraftManager) {
          await DraftManager.enter(newContent);
        } else {
          editorEl.innerHTML = textToHTML(newContent);
        }
        updateWordCount();
        showToast('✅ AI已修复' + fixedCount + '项（草稿模式，请确认采纳）');
        btn.textContent = '✓';
        btn.style.background = 'var(--success)';
      } else {
        showToast('❌ 修复失败：' + (r.error || '未知错误'));
        btn.disabled = false;
        btn.textContent = '🤖';
      }
    } catch(e) {
      showToast('❌ ' + e.message);
      btn.disabled = false;
      btn.textContent = '🤖';
    }
  };

  // 手动修复：针对旧格式
  window.valManualFixItem = function(btn, idx) {
    if (!lastValResult || !lastValResult.results) return;
    var item = lastValResult.results[idx];
    if (!item) return;
    
    // 先定位
    window.valLocateItem(btn, idx);
    
    // 聚焦编辑器
    var editorEl = document.getElementById('editor-content');
    if (editorEl) {
      editorEl.focus();
      editorEl.classList.add('conflict-highlight');
      setTimeout(function() { editorEl.classList.remove('conflict-highlight'); }, 3000);
      showToast('✏️ 请手动修改');
    }
    
    btn.textContent = '✏️';
    btn.style.background = 'var(--success)';
  };

  // 定位：针对旧格式
  window.valLocateItem = function(btn, idx) {
    if (!lastValResult || !lastValResult.results) return;
    var item = lastValResult.results[idx];
    if (!item) return;
    
    var keywords = (item.msg || '').replace(/^[：:：\s]*/, '').substring(0, 30);
    var editorEl = document.getElementById('editor-content');
    if (!editorEl) return;
    
    var editorText = editorEl.innerText;
    var idx2 = editorText.indexOf(keywords);
    if (idx2 >= 0) {
      var textNode = editorEl.firstChild;
      while (textNode) {
        if (textNode.nodeType === 3 && textNode.textContent.indexOf(keywords) >= 0) {
          var charIdx = textNode.textContent.indexOf(keywords);
          var range = document.createRange();
          range.setStart(textNode, charIdx);
          range.setEnd(textNode, charIdx + keywords.length);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          range.startContainer.parentElement.scrollIntoView({behavior:'smooth', block:'center'});
          showToast('📍 已定位');
          break;
        }
        textNode = textNode.nextSibling;
      }
    } else {
      showToast('未找到匹配文本');
    }
  };


  window.runManualFix = runManualFix;
// 页面卸载时清理所有进度定时器
window.addEventListener('beforeunload', function() {
  // val-actions.js 中的定时器会在操作完成后自动清理
  // 此处为兜底，防止页面在操作进行中关闭
});
