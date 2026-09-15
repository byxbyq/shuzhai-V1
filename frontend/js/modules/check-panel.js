
/**
 * 检查面板模块
 * 显示批量检查结果，支持段落定位和 AI 修复
 */

var CheckPanel = (function() {
  var _results = null;
  var _currentChapter = null;

  function init() {
    var timelineContainer = document.querySelector('.timeline-container');
    if (timelineContainer && !document.getElementById('check-panel-btn')) {
      var btn = document.createElement('button');
      btn.id = 'check-panel-btn';
      btn.className = 'check-panel-btn';
      btn.textContent = '检查面板';
      btn.onclick = togglePanel;
      timelineContainer.appendChild(btn);
    }
  }

  function togglePanel() {
    var panel = document.getElementById('check-panel');
    if (panel) {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    } else {
      createPanel();
    }
  }

  function createPanel() {
    var panel = document.createElement('div');
    panel.id = 'check-panel';
    panel.className = 'check-panel';
    panel.innerHTML = '<div class="check-panel-header"><h3>检查问题面板</h3><div class="check-panel-actions"><button class="fix-all-btn" onclick="CheckPanel.fixAll()" title="基于所有检查结果进行综合修复">综合修复</button><button class="close-btn" onclick="CheckPanel.close()">x</button></div></div><div class="check-panel-content" id="check-panel-content"><p class="empty-state">请先运行批量检查</p></div>';
    document.body.appendChild(panel);
  }

  function close() {
    var panel = document.getElementById('check-panel');
    if (panel) panel.style.display = 'none';
  }

  function loadResults(results) {
    _results = results;
    renderPanel();
  }

  function renderPanel() {
    var content = document.getElementById('check-panel-content');
    if (!content) return;

    if (!_results || !_results.results || _results.results.length === 0) {
      content.innerHTML = '<p class="empty-state">暂无检查结果</p>';
      return;
    }

    var html = '';
    _results.results.forEach(function(chResult) {
      var chIdx = chResult.chapter_index;
      var title = chResult.title || '第' + (chIdx + 1) + '章';
      var checks = chResult.checks || {};
      
      var hasIssues = false;
      var issuesHtml = '';
      
      Object.keys(checks).forEach(function(checkType) {
        var check = checks[checkType];
        if (!check.ok) {
          hasIssues = true;
          var paragraphs = check.paragraphs || [];
          
          issuesHtml += '<div class="check-issue-group">';
          issuesHtml += '<div class="check-issue-header">' + getCheckTypeName(checkType) + '</div>';
          issuesHtml += '<div class="check-issue-result">' + (check.content || check.result || '') + '</div>';
          
          if (paragraphs.length > 0) {
            paragraphs.forEach(function(para) {
              issuesHtml += '<div class="problem-card" id="problem-' + chIdx + '-' + para.index + '">';
              issuesHtml += '<div class="problem-card-header"><span class="problem-index">段落 ' + (para.index + 1) + '</span></div>';
              issuesHtml += '<div class="problem-issue">' + esc(para.issue || '') + '</div>';
              issuesHtml += '<div class="problem-suggestion">建议：' + esc(para.suggestion || '') + '</div>';
              issuesHtml += '<div class="problem-card-footer">';
              issuesHtml += '<button class="fix-btn" onclick="CheckPanel.aiFix(' + chIdx + ',' + para.index + ',\'' + esc(checkType).replace(/'/g, "\\'") + '\')">AI 修复</button>';
              issuesHtml += '<button class="ignore-btn" onclick="CheckPanel.ignore(' + chIdx + ',' + para.index + ')">忽略</button>';
              issuesHtml += '</div></div>';
            });
          } else {
            issuesHtml += '<div class="no-paragraph">未定位到具体段落</div>';
          }
          
          issuesHtml += '</div>';
        }
      });
      
      if (hasIssues) {
        html += '<div class="check-chapter-group">';
        html += '<div class="check-chapter-header" onclick="CheckPanel.toggleChapter(' + chIdx + ')">';
        html += '<span class="chapter-title">' + title + '</span>';
        html += '<span class="toggle-icon">v</span>';
        html += '</div>';
        html += '<div class="check-chapter-content" id="chapter-content-' + chIdx + '">';
        html += issuesHtml;
        html += '</div></div>';
      }
    });
    
    if (!html) {
      html = '<p class="empty-state">所有检查项均通过！</p>';
    }
    
    content.innerHTML = html;
  }

  function toggleChapter(chIdx) {
    var content = document.getElementById('chapter-content-' + chIdx);
    if (content) {
      content.style.display = content.style.display === 'none' ? 'block' : 'none';
    }
  }

  function getCheckTypeName(type) {
    var names = {
      'drift': '偏离检查', 'twist': '转折检查', 'duplicate': '重复检查',
      'style': '风格检查', 'timeline': '时间线检查', 'conflict': '冲突检查',
      'quality': '质量检查', 'memory': '记忆检查', 'ai-flavor': 'AI 味检查',
      'outline': '大纲质量', 'setting': '设定质量', 'character': '人物质量',
      'wordcount': '字数检查', 'completeness': '完整性检查',
      'continuity': '连贯性检查', 'consistency': '一致性检查'
    };
    return names[type] || type;
  }

  function aiFix(chIdx, paraIdx, issueType) {
    if (!_results) return;
    
    var chResult = _results.results.find(function(r) { return r.chapter_index === chIdx; });
    if (!chResult) return;
    
    var check = chResult.checks[issueType];
    if (!check || !check.paragraphs) return;
    
    var para = check.paragraphs.find(function(p) { return p.index === paraIdx; });
    if (!para) return;
    
    var card = document.getElementById('problem-' + chIdx + '-' + paraIdx);
    var btn = card ? card.querySelector('.fix-btn') : null;
    if (btn) { btn.textContent = '修复中...'; btn.disabled = true; }
    
    api('/api/validate/fix', {
      method: 'POST',
      body: JSON.stringify({
        chapter_index: chIdx, paragraph_index: paraIdx,
        issue_type: issueType, issue: para.issue || '', suggestion: para.suggestion || ''
      })
    }).then(function(res) {
      if (!res || !res.ok) {
        showToast('修复失败：' + (res && res.message || ''), 'error');
        if (btn) { btn.textContent = 'AI 修复'; btn.disabled = false; }
        return;
      }
      showFixResult(chIdx, paraIdx, res.original, res.fixed);
    }).catch(function(e) {
      showToast('修复失败：' + e.message, 'error');
      if (btn) { btn.textContent = 'AI 修复'; btn.disabled = false; }
    });
  }

  function showFixResult(chIdx, paraIdx, original, fixed) {
    var modal = document.createElement('div');
    modal.className = 'fix-result-modal';
    modal.innerHTML = '<div class="fix-result-content"><h3>修复结果对比</h3><div class="fix-result-body"><div class="fix-result-original"><h4>修改前</h4><p>' + esc(original || '') + '</p></div><div class="fix-result-fixed"><h4>修改后</h4><p>' + esc(fixed || '').substring(0, 2000) + '</p></div></div><div class="fix-result-footer"><button class="confirm-btn" onclick="CheckPanel.confirmFix(' + chIdx + ',' + paraIdx + ')">确认采纳</button><button class="cancel-btn" onclick="CheckPanel.closeFixResult()">取消</button></div></div>';
    document.body.appendChild(modal);
  }

  function confirmFix(chIdx, paraIdx) {
    closeFixResult();
    showToast('已采纳修复', 'success');
    var card = document.getElementById('problem-' + chIdx + '-' + paraIdx);
    if (card) card.classList.add('resolved');
  }

  function closeFixResult() {
    var modal = document.querySelector('.fix-result-modal');
    if (modal) modal.remove();
  }

  function ignore(chIdx, paraIdx) {
    var card = document.getElementById('problem-' + chIdx + '-' + paraIdx);
    if (card) card.classList.add('ignored');
  }

  // 综合修复：基于所有检查结果一次性修复
  function fixAll() {
    if (!_results || !_results.results || _results.results.length === 0) {
      showToast('没有检查结果可供修复');
      return;
    }
    
    // 获取当前章节内容
    var chIdx = _currentChapter !== null ? _currentChapter : 0;
    var chResult = _results.results.find(function(r) { return r.chapter_index === chIdx; });
    if (!chResult) {
      showToast('找不到章节检查结果');
      return;
    }
    
    // 获取章节内容
    var content = '';
    if (typeof chapters !== 'undefined' && chapters[chIdx]) {
      content = chapters[chIdx].content || '';
    }
    if (!content) {
      showToast('章节内容为空');
      return;
    }
    
    // 显示修复中状态
    var contentDiv = document.getElementById('check-panel-content');
    var originalHtml = contentDiv.innerHTML;
    contentDiv.innerHTML = '<div class="fix-all-loading"><div class="loading-spinner"></div><p>正在进行综合修复，请稍候...</p><p class="loading-hint">AI将综合考虑所有问题进行修复</p></div>';
    
    // 调用综合修复API
    api('/api/validate/fix-all', {
      method: 'POST',
      body: JSON.stringify({
        content: content,
        check_result: chResult.checks || {},
        chapter_index: chIdx
      })
    }).then(function(res) {
      if (!res || !res.ok) {
        contentDiv.innerHTML = originalHtml;
        showToast('综合修复失败：' + (res && res.error || '未知错误'), 'error');
        return;
      }
      
      if (res.message === '没有需要修复的问题') {
        contentDiv.innerHTML = originalHtml;
        showToast('检查结果中没有发现需要修复的问题', 'success');
        return;
      }
      
      // 显示修复结果对比
      showFixAllResult(chIdx, res.original, res.fixed, res.issues_fixed, res.issues_summary, res.changed_paragraphs);
    }).catch(function(e) {
      contentDiv.innerHTML = originalHtml;
      showToast('综合修复失败：' + e.message, 'error');
    });
  }
  
  // 显示综合修复结果
  function showFixAllResult(chIdx, original, fixed, issuesFixed, issuesSummary, changedParagraphs) {
    var modal = document.createElement('div');
    modal.className = 'fix-result-modal fix-all-modal';
    
    var summaryHtml = '';
    if (issuesSummary && issuesSummary.length > 0) {
      summaryHtml = '<div class="fix-summary"><h4>修复的问题：</h4><ul>';
      issuesSummary.forEach(function(issue) {
        summaryHtml += '<li>' + issue + '</li>';
      });
      summaryHtml += '</ul></div>';
    }
    
    modal.innerHTML = '<div class="fix-result-content fix-all-content">'
      + '<h3>综合修复结果</h3>'
      + '<p class="fix-stats">共修复 ' + (issuesFixed || 0) + ' 个问题（混合模式：仅修改问题段落）</p>'
      + (changedParagraphs && changedParagraphs.length > 0 
        ? '<p class="fix-paragraphs-info">修改了第 ' + changedParagraphs.join(', ') + ' 段</p>' 
        : '')
      + summaryHtml
      + '<div class="fix-result-body">'
      + '<div class="fix-result-original"><h4>修改前</h4><div class="fix-text">' + (original || '').substring(0, 2000) + '...</div></div>'
      + '<div class="fix-result-fixed"><h4>修改后</h4><div class="fix-text">' + (fixed || '').substring(0, 2000) + '...</div></div>'
      + '</div>'
      + '<div class="fix-result-footer">'
      + '<button class="confirm-btn" onclick="CheckPanel.confirmFixAll(' + chIdx + ')">确认采纳</button>'
      + '<button class="cancel-btn" onclick="CheckPanel.closeFixResult()">取消</button>'
      + '</div></div>';
    
    document.body.appendChild(modal);
    
    // 存储修复结果供确认时使用
    window._pendingFixAll = { chIdx: chIdx, fixed: fixed };
  }
  
  // 确认综合修复
  function confirmFixAll(chIdx) {
    closeFixResult();
    
    if (!window._pendingFixAll) {
      showToast('修复结果已丢失');
      return;
    }
    
    var fixed = window._pendingFixAll.fixed;
    
    // 更新章节内容
    if (typeof chapters !== 'undefined' && chapters[chIdx]) {
      chapters[chIdx].content = fixed;
      chapters[chIdx].word_count = fixed.length;
    }
    
    // 保存到后端
    if (typeof saveChapter === 'function') {
      saveChapter(chIdx, fixed).then(function() {
        showToast('综合修复已采纳并保存', 'success');
        // 更新编辑器显示
        var editorEl = document.getElementById('editor-content');
        if (editorEl) {
          editorEl.innerText = fixed;
        }
        if (typeof updateWordCount === 'function') updateWordCount();
      }).catch(function(e) {
        showToast('保存失败：' + e.message, 'error');
      });
    }
    
    window._pendingFixAll = null;
  }
  
  // 显示单个章节的检查结果（供工作流调用）
  function showCheckResult(checkResult, chapterIndex) {
    _currentChapter = chapterIndex;
    
    // 构造与批量检查相同的数据结构
    _results = {
      ok: true,
      results: [{
        chapter_index: chapterIndex,
        title: '第' + (chapterIndex + 1) + '章',
        checks: checkResult.checks || {}
      }]
    };
    
    // 确保面板已创建
    var panel = document.getElementById('check-panel');
    if (!panel) {
      createPanel();
      panel = document.getElementById('check-panel');  // 重新获取引用
    }
    
    // 显示面板
    if (panel) panel.style.display = 'block';
    
    // 渲染结果
    renderPanel();
  }

  // ═══ 30维全书检查结果展示 ═══
  function showProjectReview(reviewResult) {
    if (!panel) init();
    var contentDiv = document.getElementById('check-panel-content');
    if (!contentDiv) return;

    var categories = [
      {key: 'outline_quality', name: '大纲质量（10维）', icon: '📖'},
      {key: 'settings_quality', name: '设定质量（10维）', icon: '🌍'},
      {key: 'characters_quality', name: '人物质量（10维）', icon: '👤'}
    ];

    var html = '<div class="project-review-result">';
    html += '<h3 style="margin:8px 0;color:#4a90d9">📊 30维全书检查报告</h3>';

    var totalIssues = 0;
    var totalScore = 0;
    var totalDims = 0;

    categories.forEach(function(cat) {
      var data = reviewResult[cat.key];
      if (!data || !data.dimensions) return;

      var catScore = 0;
      var catDims = 0;
      html += '<div class="review-category" style="margin:10px 0;padding:10px;background:rgba(74,144,217,0.05);border-radius:8px;border-left:3px solid #4a90d9">';
      html += '<h4 style="margin:0 0 8px 0">' + cat.icon + ' ' + cat.name + '</h4>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:13px">';

      data.dimensions.forEach(function(dim) {
        var score = dim.score || 0;
        var statusIcon = score >= 9 ? '✅' : score >= 7 ? '✓' : score >= 5 ? '⚠️' : '❌';
        var scoreColor = score >= 9 ? '#4CAF50' : score >= 7 ? '#8BC34A' : score >= 5 ? '#FF9800' : '#f44336';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0">';
        html += '<span>' + statusIcon + ' ' + esc(dim.name) + '</span>';
        html += '<span style="color:' + scoreColor + ';font-weight:bold">' + score + '分</span>';
        html += '</div>';
        catScore += score;
        catDims++;
        if (score <= 4) totalIssues++;
      });

      html += '</div>';
      var catAvg = catDims > 0 ? (catScore / catDims).toFixed(1) : 0;
      html += '<div style="text-align:right;margin-top:6px;font-size:12px;color:#888">均分: <b style="color:#4a90d9">' + catAvg + '</b>/10</div>';
      if (data.summary) {
        html += '<div style="margin-top:4px;font-size:12px;color:#666;padding:4px 8px;background:rgba(0,0,0,0.03);border-radius:4px">' + esc(data.summary) + '</div>';
      }
      html += '</div>';
      totalScore += catScore;
      totalDims += catDims;
    });

    var overallAvg = totalDims > 0 ? (totalScore / totalDims).toFixed(1) : 0;
    html = html.replace('</h3>', ' — 总均分 <b>' + overallAvg + '</b></h3>');

    if (totalIssues > 0) {
      html += '<div style="margin:10px 0;padding:8px 12px;background:rgba(255,152,0,0.1);border-radius:6px;font-size:13px">';
      html += '⚠️ 发现 <b>' + totalIssues + '</b> 个低分项（≤4分），建议在写正文前优先改进</div>';
    } else {
      html += '<div style="margin:10px 0;padding:8px 12px;background:rgba(76,175,80,0.1);border-radius:6px;font-size:13px">';
      html += '✅ 全部维度均分≥5，可以开始写正文了！</div>';
    }

    html += '</div>';
    contentDiv.innerHTML = html;
    panel.style.display = 'block';
  }

  return {
    init: init, togglePanel: togglePanel, close: close,
    loadResults: loadResults, renderPanel: renderPanel,
    toggleChapter: toggleChapter, aiFix: aiFix,
    confirmFix: confirmFix, closeFixResult: closeFixResult, ignore: ignore,
    fixAll: fixAll, showCheckResult: showCheckResult, confirmFixAll: confirmFixAll,
    showProjectReview: showProjectReview
  };
})();

document.addEventListener('DOMContentLoaded', function() { CheckPanel.init(); });
