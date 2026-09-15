// draft-ui.js — 草稿→成品机制核心模块
(function() {
  'use strict';

  // ── 状态 ──
  var _draftMode = false;        // 是否处于草稿模式
  var _draftContent = null;      // 当前草稿内容
  var _publishedContent = '';     // 进入草稿前的成品快照（用于diff）

  // ── 对外接口 ──
  window.DraftManager = {
    /** 是否处于草稿模式 */
    isActive: function() { return _draftMode; },

    /** 获取草稿内容 */
    getDraft: function() { return _draftContent; },

    /** 进入草稿模式（AI产出调用此方法） */
    enter: async function(draftText, publishedContent) {
      console.log('[DraftManager.enter] called, draftText length=', draftText ? draftText.length : 0, 'publishedContent length=', publishedContent ? publishedContent.length : 0);
      var editorEl = document.getElementById('editor-content');
      if (!editorEl) { console.warn('[DraftManager.enter] editor-content not found'); return; }
      // 防止草稿模式下重复进入（会丢失原始成品快照）
      if (_draftMode) {
        // 已在草稿模式中，只刷新草稿内容和diff，不覆盖成品快照
        _draftContent = draftText;
        editorEl.innerText = draftText;
        requestAnimationFrame(function() { _renderDiff(); });
        if (typeof showToast === 'function') showToast('草稿已更新，请确认后采纳');
        return;
      }
      // 快照当前成品（优先使用传入的原始内容，避免读取到加载提示文字）
      var snapshot = publishedContent !== undefined ? publishedContent : (editorEl.innerText || '');
      // 如果成品快照为空，尝试从 API 加载当前章节的已保存正文
      if (!snapshot && typeof selectChapter === 'function') {
        var chIdx = window.currentChapterIndex || 0;
        try {
          var r = await selectChapter(chIdx);
          if (r && r.ok) snapshot = r.content || '';
          console.log('[DraftManager.enter] loaded publishedContent from API, length=', snapshot ? snapshot.length : 0);
        } catch(e) { console.warn('[DraftManager.enter] load saved content failed:', e); }
      }
      _publishedContent = snapshot;
      _draftContent = draftText;
      _draftMode = true;
      // 将草稿内容写入编辑器
      editorEl.innerText = draftText;
      // 显示对比面板
      _showComparePanel();
      // UI标记
      _updateToolbarState();
      console.log('[DraftManager.enter] draft mode entered, _draftMode=', _draftMode, 'publishedContent length=', _publishedContent ? _publishedContent.length : 0);
    },

    /** 手动触发19维检查（用户点击检查按钮时调用） */
    runCheck: function() {
      if (!_draftMode) {
        if (typeof showToast === 'function') showToast('请先创建草稿');
        return;
      }
      var editorEl = document.getElementById('editor-content');
      var content = editorEl ? (editorEl.innerText || '') : (_draftContent || '');
      if (!content || content.trim().length < 5) {
        if (typeof showToast === 'function') showToast('内容太短，无法检查');
        return;
      }
      var chIdx = window.currentChapterIndex || 0;
      if (typeof showToast === 'function') showToast('🔍 正在执行19维检查...');
      // 更新按钮状态
      var btnCheck = document.getElementById('btn-draft-check');
      if (btnCheck) { btnCheck.textContent = ' 检查中...'; btnCheck.disabled = true; }
      if (typeof api === 'function') {
        api('/api/validate/all-in-one', {
          method: 'POST',
          body: JSON.stringify({
            content: content,
            context: { chapterIndex: chIdx, stage: 'content' },
            index: chIdx
          })
        }).then(function(checkResult) {
          if (btnCheck) { btnCheck.textContent = ' 检查'; btnCheck.disabled = false; }
          if (checkResult && checkResult.ok) {
            window._lastCheckResult = checkResult;
            window._lastCheckChapterIndex = chIdx;
            var issueCount = 0;
            if (checkResult.checks) {
              Object.keys(checkResult.checks).forEach(function(k) {
                if (!checkResult.checks[k].ok) issueCount++;
              });
            }
            if (typeof showToast === 'function') {
              if (issueCount > 0) {
                showToast('19维检查发现 ' + issueCount + ' 个问题，请修复后采纳', 'warning', 5000);
              } else {
                showToast('19维检查通过，可以采纳', 'success');
              }
            }
            if (typeof CheckPanel !== 'undefined' && CheckPanel.showCheckResult) {
              try {
                CheckPanel.showCheckResult(checkResult, chIdx);
              } catch(e) {
                console.error('[工作流] CheckPanel.showCheckResult 报错:', e);
              }
            }
          } else {
            if (typeof showToast === 'function') showToast('检查失败: ' + (checkResult && checkResult.error || ''), 'error');
          }
        }).catch(function(e) {
          if (btnCheck) { btnCheck.textContent = '🔍 检查'; btnCheck.disabled = false; }
          console.error('[工作流] 19维检查API失败:', e);
          if (typeof showToast === 'function') showToast('检查失败: ' + e.message, 'error');
        });
      }
    },

    /** 采纳草稿为成品 */
    accept: async function() {
      if (!_draftMode) return;
      var editorEl = document.getElementById('editor-content');
      // 同步编辑器最新内容（用户可能手动改过草稿）
      _draftContent = editorEl.innerText || '';
      var chIdx = window.currentChapterIndex || 0;
      // 更新内存
      if (typeof chapters !== 'undefined' && chapters[chIdx]) {
        chapters[chIdx].content = _draftContent;
        chapters[chIdx].word_count = _draftContent.length;
      }
      // 保存到后端
      if (typeof saveChapter === 'function') {
        await saveChapter(chIdx, _draftContent);
      }
      // 退出草稿模式
      _exitMode();
      if (typeof updateWordCount === 'function') updateWordCount();
      if (typeof showToast === 'function') showToast('✓ 草稿已采纳为成品');
    },

    /** 丢弃草稿 */
    discard: function() {
      if (!_draftMode) return;
      // 恢复编辑器为成品内容
      var editorEl = document.getElementById('editor-content');
      if (editorEl && _publishedContent) {
        editorEl.innerText = _publishedContent;
      }
      _exitMode();
      if (typeof showToast === 'function') showToast('草稿已丢弃');
    },

    /** 退出草稿模式（保留草稿内容，继续在编辑器中编辑） */
    closeCompare: function() {
      if (!_draftMode) return;
      // 不退出草稿模式，只关闭对比面板
      var editorArea = document.querySelector('.editor-area');
      if (editorArea) editorArea.classList.remove('draft-mode');
      var panel = document.getElementById('draft-compare-panel');
      if (panel) panel.style.display = 'none';
      // 恢复保存按钮文字（但仍是采纳功能）
      var btnSave = document.getElementById('btn-save');
      if (btnSave) btnSave.textContent = '💾 保存';
    },

    /** 强制退出（切章时调用，恢复成品快照防止污染） */
    forceExit: function() {
      // 恢复成品快照到编辑器，防止草稿内容被AutoSave写入其他章节
      if (_draftMode && _publishedContent) {
        var editorEl = document.getElementById('editor-content');
        if (editorEl) {
          editorEl.innerText = _publishedContent;
        }
      }
      _draftMode = false;
      _draftContent = null;
      _publishedContent = '';
      _hideComparePanel();
      _updateToolbarState();
    }
  };

  // ── 内部函数 ──

  function _exitMode() {
    _draftMode = false;
    _draftContent = null;
    _publishedContent = '';
    _hideComparePanel();
    _updateToolbarState();
  }

  function _showComparePanel() {
    var panel = document.getElementById('draft-compare-panel');
    console.log('[DraftManager._showComparePanel] panel=', panel);
    if (panel) {
      panel.style.display = 'flex';
      panel.classList.add('visible');
      // 兜底：直接设置内联样式，确保面板一定可见
      panel.style.width = '42%';
      panel.style.minWidth = '300px';
      panel.style.opacity = '1';
      // 用requestAnimationFrame确保display:flex生效后再渲染diff
      requestAnimationFrame(function() { _renderDiff(); });
      console.log('[DraftManager._showComparePanel] panel shown');
    } else {
      console.warn('[DraftManager._showComparePanel] draft-compare-panel element not found');
    }
    // 隐藏右侧面板，让编辑区扩展
    var main = document.querySelector('.main');
    if (main) main.classList.add('draft-mode-active');
    // 编辑器区域切换为左右布局
    var editorArea = document.querySelector('.editor-area');
    if (editorArea) editorArea.classList.add('draft-mode');
  }

  function _hideComparePanel() {
    var panel = document.getElementById('draft-compare-panel');
    if (panel) {
      panel.style.display = 'none';
      panel.classList.remove('visible');
      panel.style.width = '';
      panel.style.minWidth = '';
      panel.style.opacity = '';
    }
    var main = document.querySelector('.main');
    if (main) main.classList.remove('draft-mode-active');
    var editorArea = document.querySelector('.editor-area');
    if (editorArea) editorArea.classList.remove('draft-mode');
  }

  function _updateToolbarState() {
    // 更新保存按钮状态
    var btnSave = document.getElementById('btn-save');
    if (btnSave) {
      if (_draftMode) {
        btnSave.textContent = '📌 采纳为成品';
        btnSave.classList.add('draft-accept-btn');
      } else {
        btnSave.textContent = '💾 保存';
        btnSave.classList.remove('draft-accept-btn');
      }
    }
    // 更新字数显示
    if (typeof updateWordCount === 'function') updateWordCount();
  }

  /**
   * 行级diff：逐行对比成品与草稿
   * 使用LCS简化算法：先找公共行，标记删除和新增
   */
  function _computeDiff(published, draft) {
    var pubLines = published.split('\n');
    var draftLines = draft.split('\n');
    var result = [];

    // 简化LCS：用多集合计数法
    var pubCount = {};
    pubLines.forEach(function(l) {
      pubCount[l] = (pubCount[l] || 0) + 1;
    });

    // 先标记草稿中的行（equal或add）
    var draftUsed = {};
    draftLines.forEach(function(line, i) {
      if (pubCount[line] && pubCount[line] > 0) {
        pubCount[line]--;
        result.push({type: 'equal', line: line, idx: i});
      } else {
        result.push({type: 'add', line: line, idx: i});
      }
    });

    // 标记成品中被删除的行
    // 重新计算pubCount（因为上面消耗了）
    var pubCount2 = {};
    pubLines.forEach(function(l) {
      pubCount2[l] = (pubCount2[l] || 0) + 1;
    });
    draftLines.forEach(function(line) {
      if (pubCount2[line] && pubCount2[line] > 0) {
        pubCount2[line]--;
      }
    });
    pubLines.forEach(function(line, i) {
      if (pubCount2[line] && pubCount2[line] > 0) {
        pubCount2[line]--;
        result.push({type: 'remove', line: line, idx: i});
      }
    });

    // 按位置排序：按草稿行号和成品行号混合排序
    result.sort(function(a, b) {
      return a.idx - b.idx;
    });

    return result;
  }

  /** 渲染差异到对比面板 */
  function _renderDiff() {
    var body = document.getElementById('draft-compare-body');
    if (!body) return;
    if (!_publishedContent) {
      body.innerHTML = '<div style="padding:14px;color:var(--muted)">无成品内容可对比</div>';
      return;
    }

    var editorEl = document.getElementById('editor-content');
    // 获取编辑器最新内容（用户可能手动改过草稿）
    var currentDraft = editorEl ? (editorEl.innerText || '') : (_draftContent || '');
    var diffs = _computeDiff(_publishedContent, currentDraft);
    var html = '';
    var addCount = 0, removeCount = 0;

    diffs.forEach(function(d) {
      var escaped = _escHtml(d.line);
      if (d.type === 'equal') {
        // 相同行用淡色显示
        html += '<div class="diff-line diff-equal">' + escaped + '</div>';
      } else if (d.type === 'add') {
        addCount++;
        html += '<div class="diff-line diff-add">+ ' + escaped + '</div>';
      } else if (d.type === 'remove') {
        removeCount++;
        html += '<div class="diff-line diff-remove">- ' + escaped + '</div>';
      }
    });

    body.innerHTML = html;
    // 统计
    var header = document.getElementById('draft-compare-stats');
    if (header) {
      header.textContent = '新增 ' + addCount + ' 行 · 删除 ' + removeCount + ' 行';
    }
  }

  function _escHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── 编辑器input事件：用户手动编辑草稿时自动刷新diff ──
  document.addEventListener('input', function(e) {
    if (!_draftMode) return;
    if (e.target && e.target.id === 'editor-content') {
      clearTimeout(window._diffTimer);
      window._diffTimer = setTimeout(_renderDiff, 600);
    }
  });

})();
