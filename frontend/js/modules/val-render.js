  /* ---- VALIDATION RESULTS RENDERER ---- */
  // lastValResult 已在 state.js 中统一声明为全局变量（var lastValResult = null）
  // 此处不再重复声明，避免类型不一致

  /**
   * 解析AI返回的结构化检查结果
   * 格式：【问题】xxx【位置】xxx【建议】xxx
   * 返回：[{problem, location, suggestion}, ...]
   */
  function _parseStructuredResult(text) {
    if (!text) return [];
    var issues = [];
    // 匹配【问题】...【位置】...【建议】... 模式
    var pattern = /【问题】([\s\S]*?)(?=【位置】|【建议】|【问题】|$)/g;
    var matches = [];
    var m;
    while ((m = pattern.exec(text)) !== null) {
      matches.push({ problem: m[1].trim() });
    }
    if (matches.length === 0) return [];

    // 提取位置和建议
    var locPattern = /【位置】([\s\S]*?)(?=【问题】|【建议】|【位置】|$)/g;
    var sugPattern = /【建议】([\s\S]*?)(?=【问题】|【位置】|【建议】|$)/g;
    var locs = [];
    var sugs = [];
    while ((m = locPattern.exec(text)) !== null) locs.push(m[1].trim());
    while ((m = sugPattern.exec(text)) !== null) sugs.push(m[1].trim());

    matches.forEach(function(mt, i) {
      issues.push({
        problem: mt.problem,
        location: locs[i] || '',
        suggestion: sugs[i] || ''
      });
    });
    return issues;
  }

  function renderValResult(raw, append, checkType){
    // 保存结果
    if (raw) lastValResult = raw;
    
    // 1. 渲染到右侧面板（原有逻辑）
    const vDiv = document.getElementById('val-results');
    if(vDiv) {
      if(!append) vDiv  .textContent='';
      _renderValResultToDiv(vDiv, raw, checkType);
    }
    
    // 2. 渲染到中间详情编辑器（如果当前不是步骤4）
    var currentStep = typeof workflowState !== 'undefined' ? workflowState.currentStep : 4;
    if (currentStep !== 4) {
      var detailPanel = document.getElementById('detail-editor-panel');
      if (detailPanel) {
        // 清空详情编辑器并显示检查结果
        var emptyEl = document.getElementById('detail-editor-empty');
        if (emptyEl) emptyEl.style.display = 'none';
        var headerEl = document.getElementById('detail-editor-header');
        if (headerEl) headerEl.style.display = 'none';
        var ta = document.getElementById('detail-editor-textarea');
        if (ta) ta.style.display = 'none';
        
        // 创建或获取检查结果容器
        var checkContainer = document.getElementById('detail-check-results');
        if (!checkContainer) {
          checkContainer = document.createElement('div');
          checkContainer.id = 'detail-check-results';
          checkContainer.style.cssText = 'flex:1;overflow-y:auto;padding:16px 24px;';
          detailPanel.appendChild(checkContainer);
        }
        if (!append) checkContainer.textContent = '';
        checkContainer.style.display = 'block';
        
        // 仅在首次（无标题时）添加检查结果标题，避免append模式下重复
        if (!checkContainer.querySelector('.check-results-title')) {
          var titleDiv = document.createElement('div');
          titleDiv.className = 'check-results-title';
          titleDiv.style.cssText = 'font-size:18px;font-weight:600;color:var(--ink);margin-bottom:16px;font-family:var(--serif);border-bottom:1px solid var(--border-soft);padding-bottom:8px;';
          titleDiv.textContent = '🔍 检查结果';
          checkContainer.appendChild(titleDiv);
        }
        
        _renderValResultToDiv(checkContainer, raw, checkType);
      }
    }
  }
  
  // 辅助函数：渲染检查结果到指定容器
  function _renderValResultToDiv(vDiv, raw, checkType){
    if(!vDiv) return;
    
    // ── 完整性/连贯性检查结果特殊渲染 ──
    if (raw && raw.ok && raw.result && (checkType === 'completeness' || checkType === 'continuity')) {
      var r = raw.result;
      // 如果result是字符串（如"第一章无需连贯性检查"），直接显示文本
      if (typeof r === 'string') {
        var label = checkType === 'completeness' ? '完整性' : '连贯性';
        var safeText = String(r).replace(/</g,'&lt;').replace(/>/g,'&gt;');
        var html = '<div class="check-result-item" data-check="'+checkType+'" style="padding:10px 12px;margin:4px 0;border-radius:6px;border-left:3px solid var(--success);background:var(--bg);line-height:1.6">';
        html += '<div class="flex-center-sm">';
        html += '<strong class="text-accent">['+label+']</strong>';
        html += '<span style="color:var(--success);font-size:12px">✓ ' + safeText + '</span>';
        html += '</div></div>';
        vDiv.insertAdjacentHTML('beforeend', html);
        return;
      }
      var score = r.overall_score !== undefined ? r.overall_score : '?';
      var level = r.overall_level || '';
      var label = checkType === 'completeness' ? '完整性' : '连贯性';
      
      // 如果AI返回格式异常（没有score），显示错误信息
      if (r.error) {
        var errHtml = '<div class="check-result-item" data-check="'+checkType+'" style="padding:10px 12px;margin:4px 0;border-radius:6px;border-left:3px solid var(--warn);background:var(--bg);line-height:1.6">';
        errHtml += '<div class="flex-center-sm-mb2">';
        errHtml += '<strong class="text-accent">['+label+']</strong>';
        errHtml += '<span style="color:var(--warn);font-size:12px">⚠ ' + String(r.error).replace(/</g,'&lt;') + '</span>';
        if (r.word_count) errHtml += '<span style="font-size:11px;color:var(--muted);margin-left:auto">'+r.word_count+'字</span>';
        errHtml += '</div>';
        if (r.raw) errHtml += '<div style="font-size:11px;color:var(--muted);padding:4px 8px;background:var(--bg2);border-radius:4px">'+String(r.raw).replace(/</g,'&lt;').substring(0,300)+'</div>';
        errHtml += '</div>';
        vDiv.insertAdjacentHTML('beforeend', errHtml);
        return;
      }
      
      var scoreColor = score >= 8 ? 'var(--success)' : score >= 6 ? 'var(--warn)' : 'var(--danger)';
      var hasIssue = score < 8;
      
      var html = '<div class="check-result-item" data-check="'+checkType+'" style="padding:10px 12px;margin:4px 0;border-radius:6px;border-left:3px solid '+scoreColor+';background:var(--bg);line-height:1.6">';
      html += '<div class="flex-center-sm-mb2">';
      html += '<strong class="text-accent">['+label+']</strong>';
      html += '<span style="font-size:20px;font-weight:700;color:'+scoreColor+'">'+score+'</span>';
      html += '<span class="text-md text-muted">/10 '+level+'</span>';
      if (r.word_count) html += '<span style="font-size:11px;color:var(--muted);margin-left:auto">'+r.word_count+'字</span>';
      if (hasIssue) {
        html += '<div style="margin-left:auto">';
        html += '<button class="val-btn" onclick="valAIFix(this)" title="AI自动修复此问题" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;margin-left:4px">🤖 AI修复</button>';
        html += '</div>';
      }
      html += '</div>';
      
      if (r.dimensions) {
        var dimLabels = {
          structure: '结构完整度', emotion_curve: '情绪曲线', info_density: '信息密度',
          length_health: '字数健康', readability: '可读性',
          plot_flow: '情节衔接', character_consistency: '角色一致',
          scene_transition: '场景过渡', foreshadowing: '伏笔承接', pacing: '节奏衔接'
        };
        for (var dim in r.dimensions) {
          var d = r.dimensions[dim];
          var dScore = d.score !== undefined ? d.score : '?';
          var dColor = dScore >= 8 ? 'var(--success)' : dScore >= 6 ? 'var(--warn)' : 'var(--danger)';
          html += '<div style="display:flex;align-items:flex-start;gap:6px;margin:4px 0;padding:4px 8px;background:var(--bg2);border-radius:4px">';
          html += '<span style="color:'+dColor+';font-weight:600;min-width:28px">'+dScore+'</span>';
          html += '<span style="color:var(--muted);min-width:70px;font-size:11px">'+(dimLabels[dim]||dim)+'</span>';
          html += '<span style="color:var(--ink);font-size:11px;flex:1">'+esc(d.comment||'')+'</span>';
          html += '</div>';
          if (d.issues && d.issues.length) {
            d.issues.forEach(function(iss) {
              html += '<div class="text-xs-danger-indent">⚠ '+esc(iss)+'</div>';
            });
          }
          if (d.gap) html += '<div class="text-xs-danger-indent">⚠ 断裂: '+esc(d.gap)+'</div>';
          if (d.conflict) html += '<div class="text-xs-danger-indent">⚠ 矛盾: '+esc(d.conflict)+'</div>';
        }
      }
      
      if (r.summary) html += '<div style="margin-top:6px;font-size:11px;color:var(--ink);padding:4px 8px;background:var(--surface);border-radius:4px">'+esc(r.summary)+'</div>';
      if (r.suggestions && r.suggestions.length) {
        html += '<div style="margin-top:6px"><strong style="font-size:11px;color:var(--accent)">改进建议:</strong>';
        r.suggestions.forEach(function(s) { html += '<div style="font-size:11px;color:var(--muted);padding:2px 0 2px 12px">• '+esc(s)+'</div>'; });
        html += '</div>';
      }
      if (r.gap_points && r.gap_points.length) {
        html += '<div style="margin-top:6px"><strong style="font-size:11px;color:var(--danger)">断裂点:</strong>';
        r.gap_points.forEach(function(g) { html += '<div style="font-size:11px;color:var(--danger);padding:2px 0 2px 12px">⚡ '+esc(g)+'</div>'; });
        html += '</div>';
      }
      // 添加隐藏的val-text，供一键修复收集问题使用
      if (hasIssue) {
        var problemSummary = label + '评分' + score + '/10。';
        if (r.dimensions) {
          var lowDims = [];
          for (var dim in r.dimensions) {
            var dScore = r.dimensions[dim].score;
            if (dScore !== undefined && dScore < 8) {
              lowDims.push(dim + '(' + dScore + '分): ' + (r.dimensions[dim].comment || ''));
            }
          }
          if (lowDims.length) problemSummary += ' 低分维度: ' + lowDims.join('; ');
        }
        if (r.suggestions && r.suggestions.length) {
          problemSummary += ' 建议: ' + r.suggestions.join('; ');
        }
        html += '<div class="val-text" class="hidden">' + esc(problemSummary) + '</div>';
      }
      html += '</div>';
      vDiv.insertAdjacentHTML('beforeend', html);
      return;
    }
    
    // 全局一致性检查：返回results对象（多项子检查）
    if (raw && raw.ok && raw.results && checkType === 'consistency') {
      var label2 = '全局一致性';
      var _cNegPats = ['不一致','不符合','不连贯','不自然','不协调','不合理','不自洽','不匹配','不对齐'];
      var _cNegPrefixes = ['无明显','没有','不存在','未发现','未检测到','未发现明显','无'];
      var _cNoIssuePats = ['无矛盾','无冲突','无偏离','无重复','没有重复','不存在重复','无问题','没有问题','没有发现','未发现','未检测到','未发现问题','没有偏离','未检测到问题','无遗漏','没有遗漏','未发现明显','无明显问题','一致','符合','通过','对齐','无异常','正常','衔接正常','数据一致','未发现偏离','未发现冲突','未发现矛盾','未发现重复','未发现遗漏'];
      var _cIssuePats = ['偏离','矛盾','冲突','断裂','遗漏','缺乏','缺失','生硬','突兀','混乱','错误','需改进','显著','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
      var results2 = raw.results;
      var parsedCount2 = raw.parsed_count || 0;
      var totalCount2 = raw.total || Object.keys(results2).length;
      var stageNum = raw.stage || 1;
      var subLabelsFromBackend = raw.sub_labels || {};
      
      // 检查是否有问题（v3：结论优先+否定前缀+清洗文本法）
      var issueCount = 0;
      var allIssueText = [];
      for (var k in results2) {
        if (results2[k]) {
          var text2 = results2[k];
          // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
          var cTail = text2.substring(Math.max(0, text2.length - 80));
          if (cTail.includes('结论') || cTail.includes('整体评价') || cTail.includes('总结')) {
            // 找到最后一个结论关键词位置，只看结论之后的内容
            var cConclStart = Math.max(cTail.lastIndexOf('结论'), cTail.lastIndexOf('整体评价'), cTail.lastIndexOf('总结'));
            var cConclText = cTail.substring(cConclStart);
            var cTailExtra = [];
            for (var cte = 0; cte < _cIssuePats.length; cte++) {
              for (var cnp2 = 0; cnp2 < _cNegPrefixes.length; cnp2++) { cTailExtra.push(_cNegPrefixes[cnp2] + _cIssuePats[cte]); }
            }
            var cTailAllNo = _cNoIssuePats.concat(cTailExtra);
            var cTailHasNo = cTailAllNo.some(function(p){ return cConclText.includes(p); });
            if (cTailHasNo) {
              // 清洗结论句
              var cCleanedConcl = cConclText;
              var cSortedConcl = cTailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
              cSortedConcl.forEach(function(p) { cCleanedConcl = cCleanedConcl.split(p).join(''); });
              var cConclHasIssue = _cIssuePats.some(function(p){ return cCleanedConcl.includes(p); });
              if (!cConclHasIssue) {
                continue; // 结论中只有无问题短语，跳过
              }
            }
          }
          // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语
          var negatedText = text2;
          for (var cnp4 = 0; cnp4 < _cNegPrefixes.length; cnp4++) {
            for (var cip4 = 0; cip4 < _cIssuePats.length; cip4++) {
              try {
                var cEscPrefix = _cNegPrefixes[cnp4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var cEscIssue = _cIssuePats[cip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var cRe = new RegExp(cEscPrefix + '[^，。！？；]{0,6}' + cEscIssue, 'g');
                negatedText = negatedText.replace(cRe, '');
              } catch(e) {}
            }
          }
          for (var cnp5 = 0; cnp5 < _cNegPrefixes.length; cnp5++) {
            for (var cip5 = 0; cip5 < _cNegPats.length; cip5++) {
              try {
                var cEscP2 = _cNegPrefixes[cnp5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var cEscI2 = _cNegPats[cip5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var cRe2 = new RegExp(cEscP2 + '[^，。！？；]{0,6}' + cEscI2, 'g');
                negatedText = negatedText.replace(cRe2, '');
              } catch(e) {}
            }
          }
          // 第1步：检查否定形式的问题词（在negatedText上检查）
          var cNegHit = false;
          for (var cni = 0; cni < _cNegPats.length; cni++) {
            if (negatedText.includes(_cNegPats[cni])) { cNegHit = true; break; }
          }
          var cHasIssue = false;
          if (cNegHit) {
            cHasIssue = true;
          } else {
            // 自动补充"否定前缀+问题词"形式（用全部否定前缀）
            var _cExtra = [];
            for (var ce = 0; ce < _cIssuePats.length; ce++) {
              for (var cenp = 0; cenp < _cNegPrefixes.length; cenp++) { _cExtra.push(_cNegPrefixes[cenp] + _cIssuePats[ce]); }
            }
            var _cAllNo = _cNoIssuePats.concat(_cExtra);
            var cNoIssue = _cAllNo.some(function(p){ return negatedText.includes(p); });
            if (cNoIssue) {
              var cleaned2 = negatedText;
              var cSorted = _cAllNo.slice().sort(function(a,b){ return b.length - a.length; });
              cSorted.forEach(function(p) { cleaned2 = cleaned2.split(p).join(''); });
              cHasIssue = _cIssuePats.some(function(p){ return cleaned2.includes(p); });
            } else {
              cHasIssue = _cIssuePats.some(function(p){ return negatedText.includes(p); });
            }
          }
          if (cHasIssue) {
            issueCount++;
            allIssueText.push((subLabelsFromBackend[k]||k) + ': ' + text2);
          }
        }
      }
      var hasIssue2 = issueCount > 0;
      var borderColor = hasIssue2 ? 'var(--danger)' : 'var(--success)';
      var stageLabel = stageNum === 2 ? '阶段2：全文一致性' : '阶段1：设定层一致性';
      
      var html2 = '<div class="check-result-item" data-check="'+checkType+'" style="padding:10px 12px;margin:4px 0;border-radius:6px;border-left:3px solid '+borderColor+';background:var(--bg);line-height:1.6">';
      html2 += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">';
      html2 += '<strong class="text-accent">['+label2+']</strong>';
      html2 += '<span class="text-muted-sm">'+stageLabel+'</span>';
      if (hasIssue2) {
        html2 += '<span style="color:var(--danger);font-size:12px">⚠ '+issueCount+'项不一致</span>';
        html2 += '<button class="val-btn" onclick="valAIFix(this)" title="AI修复此问题" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;margin-left:auto">🤖 AI修复</button>';
      } else {
        html2 += '<span style="color:var(--success);font-size:12px">✓ 全部一致</span>';
      }
      html2 += '<span class="text-muted-sm">'+parsedCount2+'/'+totalCount2+'项已解析</span>';
      html2 += '</div>';
      
      // 逐项展示
      for (var k2 in results2) {
        if (results2[k2]) {
          var subText = results2[k2];
          // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
          var subTail = subText.substring(Math.max(0, subText.length - 80));
          var subTailIsNoIssue = false;
          if (subTail.includes('结论') || subTail.includes('整体评价') || subTail.includes('总结')) {
            // 找到最后一个结论关键词位置，只看结论之后的内容
            var subConclStart = Math.max(subTail.lastIndexOf('结论'), subTail.lastIndexOf('整体评价'), subTail.lastIndexOf('总结'));
            var subConclText = subTail.substring(subConclStart);
            var subTailExtra = [];
            for (var ste2 = 0; ste2 < _cIssuePats.length; ste2++) {
              for (var snp2 = 0; snp2 < _cNegPrefixes.length; snp2++) { subTailExtra.push(_cNegPrefixes[snp2] + _cIssuePats[ste2]); }
            }
            var subTailAllNo = _cNoIssuePats.concat(subTailExtra);
            var subTailHasNo = subTailAllNo.some(function(p){ return subConclText.includes(p); });
            if (subTailHasNo) {
              // 清洗结论句
              var subCleanedConcl = subConclText;
              var subSortedConcl = subTailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
              subSortedConcl.forEach(function(p) { subCleanedConcl = subCleanedConcl.split(p).join(''); });
              var subConclHasIssue = _cIssuePats.some(function(p){ return subCleanedConcl.includes(p); });
              if (!subConclHasIssue) { subTailIsNoIssue = true; }
            }
          }
          var subHasIssue = false;
          if (subTailIsNoIssue) {
            subHasIssue = false;
          } else {
            // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语
            var negatedText = subText;
            for (var snp4 = 0; snp4 < _cNegPrefixes.length; snp4++) {
              for (var sip4 = 0; sip4 < _cIssuePats.length; sip4++) {
                try {
                  var sEscPrefix = _cNegPrefixes[snp4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                  var sEscIssue = _cIssuePats[sip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                  var sRe = new RegExp(sEscPrefix + '[^，。！？；]{0,6}' + sEscIssue, 'g');
                  negatedText = negatedText.replace(sRe, '');
                } catch(e) {}
              }
            }
            for (var snp5 = 0; snp5 < _cNegPrefixes.length; snp5++) {
              for (var sip5 = 0; sip5 < _cNegPats.length; sip5++) {
                try {
                  var sEscP2 = _cNegPrefixes[snp5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                  var sEscI2 = _cNegPats[sip5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                  var sRe2 = new RegExp(sEscP2 + '[^，。！？；]{0,6}' + sEscI2, 'g');
                  negatedText = negatedText.replace(sRe2, '');
                } catch(e) {}
              }
            }
            // 第1步：检查否定形式的问题词（在negatedText上检查）
            var subNegHit = false;
            for (var sni = 0; sni < _cNegPats.length; sni++) {
              if (negatedText.includes(_cNegPats[sni])) { subNegHit = true; break; }
            }
            if (subNegHit) {
              subHasIssue = true;
            } else {
              var _sExtra = [];
              for (var se = 0; se < _cIssuePats.length; se++) {
                for (var senp = 0; senp < _cNegPrefixes.length; senp++) { _sExtra.push(_cNegPrefixes[senp] + _cIssuePats[se]); }
              }
              var _sAllNo = _cNoIssuePats.concat(_sExtra);
              var subNoIssue = _sAllNo.some(function(p){ return negatedText.includes(p); });
              if (subNoIssue) {
                var subCleaned = negatedText;
                var subSorted = _sAllNo.slice().sort(function(a,b){ return b.length - a.length; });
                subSorted.forEach(function(p) { subCleaned = subCleaned.split(p).join(''); });
                subHasIssue = _cIssuePats.some(function(p){ return subCleaned.includes(p); });
              } else {
                subHasIssue = _cIssuePats.some(function(p){ return negatedText.includes(p); });
              }
            }
          }
          var subColor = subHasIssue ? 'var(--danger)' : 'var(--success)';
          var subIcon = subHasIssue ? '⚠' : '✓';
          html2 += '<div style="padding:6px 8px;margin:4px 0;background:var(--surface);border-radius:4px;font-size:12px">';
          html2 += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">';
          html2 += '<span style="color:'+subColor+';font-weight:600">'+subIcon+'</span>';
          html2 += '<strong class="text-ink">'+(subLabelsFromBackend[k2]||k2)+'</strong>';
          html2 += '</div>';
          html2 += '<div style="color:var(--muted);padding-left:20px;white-space:pre-wrap">'+esc(subText)+'</div>';
          html2 += '</div>';
        }
      }
      
      // 隐藏的val-text供一键修复收集
      if (hasIssue2) {
        html2 += '<div class="val-text" class="hidden">'+esc(allIssueText.join('\n'))+'</div>';
      }
      html2 += '</div>';
      vDiv.insertAdjacentHTML('beforeend', html2);
      return;
    }
    
    // Handle backend format: {ok: true, result: "text", check_type: "drift"}
    if (raw && raw.ok && raw.result) {
      const resultText = String(raw.result).trim();
      // 使用v2判断逻辑：优先否定词+清洗文本法
      var _rNeg = ['不一致','不符合','不连贯','不自然','不协调','不合理','不自洽','不匹配','不对齐'];
      var _rNegPrefixes = ['无明显','没有','不存在','未发现','未检测到','未发现明显','无'];
      var _rNoIssue = ['无矛盾','无冲突','无偏离','无重复','没有重复','不存在重复','无问题','没有问题','没有发现','未发现','未检测到','未发现问题','没有偏离','未检测到问题','无遗漏','没有遗漏','未发现明显','无明显问题','一致','符合','通过','对齐','无异常','正常','衔接正常','数据一致','未发现偏离','未发现冲突','未发现矛盾','未发现重复','未发现遗漏','ok','none'];
      var _rIssue = ['偏离','矛盾','冲突','断裂','遗漏','缺乏','缺失','生硬','突兀','混乱','错误','需改进','显著','存在重复','重复描写','重复内容','高度相似','完全相同','雷同'];
      // 优先用issues数组判断
      var issueCount = (raw.issues && raw.issues.length) ? raw.issues.length : 0;
      var hasNoIssue;
      if (issueCount > 0) {
        hasNoIssue = false;
      } else {
        // 第0步：结论优先 — 提取结论句，清洗后检查是否还有问题词
        var rTail = resultText.substring(Math.max(0, resultText.length - 80));
        var rTailIsNoIssue = false;
        if (rTail.includes('结论') || rTail.includes('整体评价') || rTail.includes('总结')) {
          // 找到最后一个结论关键词位置，只看结论之后的内容
          var rConclStart = Math.max(rTail.lastIndexOf('结论'), rTail.lastIndexOf('整体评价'), rTail.lastIndexOf('总结'));
          var rConclText = rTail.substring(rConclStart);
          // 生成全部否定前缀+问题词的无问题模式
          var rTailExtra = [];
          for (var rte = 0; rte < _rIssue.length; rte++) {
            for (var rnp2 = 0; rnp2 < _rNegPrefixes.length; rnp2++) { rTailExtra.push(_rNegPrefixes[rnp2] + _rIssue[rte]); }
          }
          var rTailAllNo = _rNoIssue.concat(rTailExtra);
          var rTailHasNo = rTailAllNo.some(function(p){ return rConclText.includes(p); });
          if (rTailHasNo) {
            // 清洗结论句
            var rCleanedConcl = rConclText;
            var rSortedConcl = rTailAllNo.slice().sort(function(a,b){ return b.length - a.length; });
            rSortedConcl.forEach(function(p) { rCleanedConcl = rCleanedConcl.split(p).join(''); });
            var rConclHasIssue = _rIssue.some(function(p){ return rCleanedConcl.includes(p); });
            if (!rConclHasIssue) { rTailIsNoIssue = true; }
          }
        }
        if (rTailIsNoIssue) {
          hasNoIssue = true;
        } else {
          // 第0.5步：用正则移除"否定前缀+少量字符+问题词"的否定短语（如"无明显风格不一致"）
          var rNegatedText = resultText;
          // 处理一般问题词
          for (var rnp4 = 0; rnp4 < _rNegPrefixes.length; rnp4++) {
            for (var rip4 = 0; rip4 < _rIssue.length; rip4++) {
              try {
                var rEscPrefix = _rNegPrefixes[rnp4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var rEscIssue = _rIssue[rip4].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var rRe = new RegExp(rEscPrefix + '[^，。！？；]{0,6}' + rEscIssue, 'g');
                rNegatedText = rNegatedText.replace(rRe, '');
              } catch(e) {}
            }
          }
          // 也处理否定形式问题词（不一致、不符合等）
          for (var rnp5 = 0; rnp5 < _rNegPrefixes.length; rnp5++) {
            for (var rin5 = 0; rin5 < _rNeg.length; rin5++) {
              try {
                var rEscP2 = _rNegPrefixes[rnp5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var rEscI2 = _rNeg[rin5].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                var rRe2 = new RegExp(rEscP2 + '[^，。！？；]{0,6}' + rEscI2, 'g');
                rNegatedText = rNegatedText.replace(rRe2, '');
              } catch(e) {}
            }
          }
          // 第1步：检查否定形式的问题词（在rNegatedText上检查）
          var rNegHit = false;
          for (var ri = 0; ri < _rNeg.length; ri++) {
            if (rNegatedText.includes(_rNeg[ri])) { rNegHit = true; break; }
          }
          if (rNegHit) {
            hasNoIssue = false;
          } else {
            // 第1.5步：自动补充"否定前缀+问题词"形式（用全部否定前缀）
            var _rExtra = [];
            for (var re = 0; re < _rIssue.length; re++) {
              for (var renp = 0; renp < _rNegPrefixes.length; renp++) { _rExtra.push(_rNegPrefixes[renp] + _rIssue[re]); }
            }
            var _rAllNo = _rNoIssue.concat(_rExtra);
            // 第2步：清洗文本法（使用rNegatedText）
            var rNoMatch = _rAllNo.some(function(p){ return rNegatedText.includes(p); });
            if (rNoMatch) {
              var rCleaned = rNegatedText;
              var rSorted = _rAllNo.slice().sort(function(a,b){ return b.length - a.length; });
              rSorted.forEach(function(p) { rCleaned = rCleaned.split(p).join(''); });
              hasNoIssue = !_rIssue.some(function(p){ return rCleaned.includes(p); });
            } else {
              // 第3步：直接检查问题词（使用rNegatedText）
              hasNoIssue = !_rIssue.some(function(p){ return rNegatedText.includes(p); });
            }
          }
        }
      }
      
      const row = document.createElement('div');
      row.className = 'check-result-item';
      if (checkType) row.dataset.check = checkType;
      // 全文模式下记录章节索引，供定位使用
      if (typeof checkScope !== 'undefined' && checkScope === 'full') {
        row.dataset.chapterIndex = (typeof checkIndex !== 'undefined') ? checkIndex : '0';
      }
      row.style.cssText = 'padding:8px 12px;margin:4px 0;border-radius:6px;font-size:12px;border-left:3px solid '+(hasNoIssue?'var(--success)':'var(--warn)')+';background:var(--bg);line-height:1.6';
      
      var titleHTML = '<strong class="text-accent">['+(raw.check_type||checkType||'检查')+']</strong> ';
      
      if (!hasNoIssue) {
        titleHTML += '<div style="float:right;margin-top:-2px">';
        titleHTML += '<button class="val-btn" onclick="valAIFix(this)" title="AI自动修复此问题" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;margin-left:4px">🤖 AI修复</button>';
        titleHTML += '<button class="val-btn" onclick="valManualFix(this)" title="手动修改此问题" style="background:var(--warn);color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;margin-left:4px">✏️ 手动修复</button>';
        titleHTML += '<button class="val-btn" onclick="valLocate(this)" title="在编辑器中定位问题位置" style="background:var(--info);color:#fff;border:none;border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;margin-left:4px">📍 定位</button>';
        titleHTML += '</div>';
      }
      
      // 解析结构化格式：提取【问题】【位置】【建议】
      var parsedIssues = _parseStructuredResult(resultText);
      var bodyHTML;
      if (parsedIssues.length > 0) {
        // 有结构化问题：渲染为卡片
        bodyHTML = '';
        parsedIssues.forEach(function(pi, pii) {
          bodyHTML += '<div style="padding:6px 8px;margin:4px 0;background:var(--surface);border-radius:4px;border-left:2px solid var(--warn)">';
          bodyHTML += '<div style="color:var(--fg);font-size:12px;margin-bottom:3px"><strong>问题' + (pii+1) + '</strong>：' + esc(pi.problem) + '</div>';
          if (pi.location) bodyHTML += '<div class="text-muted-sm">📍 ' + esc(pi.location) + '</div>';
          if (pi.suggestion) bodyHTML += '<div style="color:var(--info);font-size:11px">💡 ' + esc(pi.suggestion) + '</div>';
          bodyHTML += '</div>';
        });
      } else {
        // 无法解析结构化格式：降级为原始文本
        bodyHTML = resultText.replace(/\n/g,'<br>');
      }
      row.innerHTML = titleHTML + '<div class="val-text" style="margin-top:'+(hasNoIssue?'0':'18')+'px">' + bodyHTML + '</div>';
      vDiv.appendChild(row);
      return;
    }
    
    // Handle error format
    if (raw && raw.ok === false && raw.error) {
      const row = document.createElement('div');
      row.className = 'check-result-item';
      if (checkType) row.dataset.check = checkType;
      row.style.cssText = 'padding:8px 12px;margin:4px 0;border-radius:6px;font-size:12px;border-left:3px solid var(--danger);background:var(--bg);line-height:1.6';
      row.innerHTML = '<strong class="text-danger">[错误]</strong> ' + esc(raw.error);
      vDiv.appendChild(row);
      return;
    }
    
    // Handle old format
    const results = raw && raw.results ? raw.results : (Array.isArray(raw) ? raw : []);
    if(!results || results.length===0){
      vDiv.innerHTML='<div style="padding:8px;color:var(--muted);text-align:center;font-size:11px">无校验结果</div>';
      return;
    }
    results.forEach((res, idx)=>{
      const isError = res.type === 'error' || res.type === 'warning';
      const row = document.createElement('div');
      row.style.cssText = 'padding:4px 8px;margin:2px 0;border-radius:4px;font-size:11px;border-left:3px solid '+(res.type==='error'?'var(--danger)':res.type==='warning'?'var(--warn)':'var(--info)')+';background:var(--bg2)';
      
      var btns = '';
      if (isError) {
        btns = '<div style="float:right;margin-top:-2px">';
        btns += '<button class="val-btn" onclick="valAIFixItem(this,'+idx+')" title="AI自动修复" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:1px 6px;font-size:10px;cursor:pointer;margin-left:3px">🤖 AI修复</button>';
        btns += '<button class="val-btn" onclick="valManualFixItem(this,'+idx+')" title="手动修改" style="background:var(--warn);color:#fff;border:none;border-radius:4px;padding:1px 6px;font-size:10px;cursor:pointer;margin-left:3px">✏️ 手动</button>';
        btns += '<button class="val-btn" onclick="valLocateItem(this,'+idx+')" title="定位到编辑器" style="background:var(--info);color:#fff;border:none;border-radius:4px;padding:1px 6px;font-size:10px;cursor:pointer;margin-left:3px">📍 定位</button>';
        btns += '</div>';
      }
      
      row.innerHTML = btns + '<strong>'+(res.label||res.check||'')+':</strong> <span class="val-text">'+esc(res.msg)+'</span>';
      vDiv.appendChild(row);
    });
  }

// Export to global scope
window.renderValResult = renderValResult;
