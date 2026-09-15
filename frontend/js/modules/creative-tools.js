// creative-tools.js - 正向创作增强工具 (Describe / Expand / Rewrite / Feedback)
// 参考 Sudowrite 的 Describe/Expand/Rewrite/Feedback 功能
// 依赖: api(), showToast(), esc(), currentChapterIndex (全局)

// ═══════════════════════════════════════════════════════════════
// 全局状态：保存编辑器选区（打开overlay前快照）
// ═══════════════════════════════════════════════════════════════
var _creativeSavedRange = null;   // 保存的选区 Range 对象
var _creativeSelectedText = '';   // 保存的选中文本
var _creativeContextText = '';    // 保存的上下文文本（前后各500字）

// 各工具的当前结果缓存
var _describeResult = '';
var _expandResult = '';
var _rewriteVersions = [];
var _rewriteSelectedIdx = -1;

// ═══════════════════════════════════════════════════════════════
// C5 内联工具条：选中文字后浮现
// ═══════════════════════════════════════════════════════════════
(function() {
  var toolbar = null;
  var hideTimer = null;
  
  function ensureToolbar() {
    if (toolbar) return toolbar;
    toolbar = document.getElementById('inline-toolbar');
    if (!toolbar) return null;
    // 绑定按钮
    toolbar.querySelectorAll('.itool-btn').forEach(function(btn) {
      btn.addEventListener('mouseenter', function() { btn.style.background = 'var(--accent)'; btn.style.color = '#fff'; });
      btn.addEventListener('mouseleave', function() { btn.style.background = 'none'; btn.style.color = 'var(--ink)'; });
      btn.addEventListener('click', function() {
        var tool = btn.getAttribute('data-tool');
        toolbar.style.display = 'none';
        if (tool === 'describe' && typeof openDescribePanel === 'function') openDescribePanel();
        else if (tool === 'expand' && typeof openExpandPanel === 'function') openExpandPanel();
        else if (tool === 'rewrite' && typeof openRewritePanel === 'function') openRewritePanel();
        else if (tool === 'feedback' && typeof openFeedbackPanel === 'function') openFeedbackPanel();
      });
    });
    return toolbar;
  }
  
  function showToolbar(rect) {
    var tb = ensureToolbar();
    if (!tb) return;
    clearTimeout(hideTimer);
    var scrollContainer = document.querySelector('.editor-scroll');
    var scrollTop = scrollContainer ? scrollContainer.scrollTop : 0;
    var containerRect = scrollContainer ? scrollContainer.getBoundingClientRect() : {left:0, top:0};
    // 定位在选区上方
    var left = rect.left - containerRect.left;
    var top = rect.top - containerRect.top - 42; // 42 = toolbar height + gap
    if (top < 0) top = rect.bottom - containerRect.top + 8; // 放下方
    tb.style.display = 'flex';
    tb.style.left = Math.max(4, left) + 'px';
    tb.style.top = top + 'px';
  }
  
  function hideToolbar() {
    hideTimer = setTimeout(function() {
      if (toolbar) toolbar.style.display = 'none';
    }, 200);
  }
  
  document.addEventListener('selectionchange', function() {
    var editor = document.getElementById('editor-content');
    if (!editor) return;
    var sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.rangeCount > 0 && editor.contains(sel.anchorNode)) {
      var text = sel.toString();
      if (text && text.trim().length >= 3) {
        var range = sel.getRangeAt(0);
        var rect = range.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          showToolbar(rect);
        }
      } else {
        hideToolbar();
      }
    } else {
      hideToolbar();
    }
  });
  
  // 工具条鼠标悬停时取消隐藏
  document.addEventListener('DOMContentLoaded', function() {
    var tb = ensureToolbar();
    if (tb) {
      tb.addEventListener('mouseenter', function() { clearTimeout(hideTimer); });
      tb.addEventListener('mouseleave', function() { hideToolbar(); });
    }
  });
})();

// ═══════════════════════════════════════════════════════════════
// 通用辅助函数
// ═══════════════════════════════════════════════════════════════

/**
 * 获取编辑器中选中的文本及上下文
 * 如果没有选中文本，尝试获取光标所在段落
 * 返回 {text, context, range}
 */
function _creativeGetSelection() {
  var editor = document.getElementById('editor-content');
  if (!editor) return {text: '', context: '', range: null};

  var sel = window.getSelection();
  var text = '';
  var range = null;

  if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
    // 有选中文本
    text = sel.toString();
    range = sel.getRangeAt(0).cloneRange();
  } else {
    // 没有选中：获取光标所在段落
    if (_creativeSavedRange && _creativeSavedRange.toString()) {
      text = _creativeSavedRange.toString();
      range = _creativeSavedRange.cloneRange();
    }
  }

  // 如果仍然没有文本，尝试取光标所在段落
  if (!text && sel && sel.rangeCount > 0) {
    var node = sel.getRangeAt(0).startContainer;
    // 向上找到块级元素
    while (node && node !== editor) {
      if (node.nodeType === 1 && (node.tagName === 'P' || node.tagName === 'DIV' || node.tagName === 'H1' || node.tagName === 'H2' || node.tagName === 'H3')) {
        text = node.innerText || node.textContent || '';
        range = document.createRange();
        range.selectNodeContents(node);
        break;
      }
      node = node.parentNode;
    }
    // 如果还是没找到，取编辑器最后一段
    if (!text) {
      var paras = editor.querySelectorAll('p, div');
      if (paras.length > 0) {
        var last = paras[paras.length - 1];
        text = last.innerText || last.textContent || '';
        range = document.createRange();
        range.selectNodeContents(last);
      } else {
        text = editor.innerText || '';
        range = document.createRange();
        range.selectNodeContents(editor);
      }
    }
  }

  // 构建上下文：选中文本在编辑器中的前后各500字
  var context = _creativeBuildContext(editor, text);

  return {text: text, context: context, range: range};
}

/**
 * 构建上下文：获取选中文本前后各500字的文本
 */
function _creativeBuildContext(editor, selectedText) {
  if (!editor || !selectedText) return '';
  var fullText = editor.innerText || editor.textContent || '';
  var idx = fullText.indexOf(selectedText);
  if (idx < 0) return fullText.substring(0, 500);
  var before = fullText.substring(Math.max(0, idx - 500), idx);
  var after = fullText.substring(idx + selectedText.length, idx + selectedText.length + 500);
  var parts = [];
  if (before) parts.push('【前文】' + before);
  if (after) parts.push('【后文】' + after);
  return parts.join('\n\n');
}

/**
 * 在打开overlay前保存当前选区
 */
function _creativeSaveSelection() {
  var result = _creativeGetSelection();
  _creativeSavedRange = result.range;
  _creativeSelectedText = result.text;
  _creativeContextText = result.context;
  return result;
}

/**
 * 替换编辑器中选中的文本
 * 使用保存的 Range 对象进行替换
 */
function _creativeReplaceSelection(newText) {
  var editor = document.getElementById('editor-content');
  if (!editor) { showToast('编辑器未找到'); return false; }

  var range = _creativeSavedRange;
  if (!range) {
    // 没有保存的选区，追加到末尾
    var p = document.createElement('p');
    p.textContent = newText;
    editor.appendChild(p);
    showToast('已追加到正文末尾');
    return true;
  }

  // 聚焦编辑器以恢复选区
  editor.focus();
  try {
    range.deleteContents();
    // 将新文本按段落分割，插入多个P节点
    var paragraphs = newText.split(/\n{2,}/).filter(function(p) { return p.trim(); });
    if (paragraphs.length === 0) {
      range.insertNode(document.createTextNode(newText));
    } else if (paragraphs.length === 1) {
      range.insertNode(document.createTextNode(paragraphs[0]));
    } else {
      // 多段落：依次插入
      var lastNode = null;
      for (var i = paragraphs.length - 1; i >= 0; i--) {
        var p = document.createElement('p');
        p.textContent = paragraphs[i];
        range.insertNode(p);
        if (i > 0) {
          range.insertNode(document.createElement('br'));
        }
      }
    }
    showToast('已替换原文');
    return true;
  } catch(e) {
    console.error('[Creative] replaceSelection error:', e);
    // 降级：追加到末尾
    var fallbackP = document.createElement('p');
    fallbackP.textContent = newText;
    editor.appendChild(fallbackP);
    showToast('选区已失效，已追加到末尾');
    return true;
  }
}

/**
 * 在选中文本后追加内容
 */
function _creativeAppendAfter(newText) {
  var editor = document.getElementById('editor-content');
  if (!editor) { showToast('编辑器未找到'); return false; }

  var range = _creativeSavedRange;
  if (!range) {
    var p = document.createElement('p');
    p.textContent = newText;
    editor.appendChild(p);
    showToast('已追加到正文末尾');
    return true;
  }

  editor.focus();
  try {
    // 将range移到选区末尾之后
    range.collapse(false); // collapse to end
    var paragraphs = newText.split(/\n{2,}/).filter(function(p) { return p.trim(); });
    if (paragraphs.length === 0) {
      range.insertNode(document.createTextNode(newText));
    } else {
      for (var i = paragraphs.length - 1; i >= 0; i--) {
        var p = document.createElement('p');
        p.textContent = paragraphs[i];
        range.insertNode(p);
        if (i > 0) {
          range.insertNode(document.createElement('br'));
        }
      }
    }
    showToast('已追加到原文后');
    return true;
  } catch(e) {
    console.error('[Creative] appendAfter error:', e);
    var fallbackP = document.createElement('p');
    fallbackP.textContent = newText;
    editor.appendChild(fallbackP);
    showToast('已追加到正文末尾');
    return true;
  }
}

/**
 * 显示加载中状态
 */
function _creativeShowLoading(containerId, msg) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = '<div class="ct-loading">' +
    '<svg viewBox="0 0 24 24" width="32" height="32" style="stroke:currentColor;fill:none;stroke-width:2;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round"/></svg>' +
    '<p class="mt-2">' + (msg || 'AI正在处理...') + '</p></div>';
}

/**
 * 显示空状态
 */
function _creativeShowEmpty(containerId, msg) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = '<div class="ct-empty"><p>' + esc(msg || '暂无结果') + '</p></div>';
}

/**
 * 显示错误状态
 */
function _creativeShowError(containerId, errMsg) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = '<div class="ct-error"><p>' + esc(errMsg || '处理失败') + '</p></div>';
}

/**
 * 本地 esc 函数（防止全局未加载时出错）
 */
function _ctEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}


// ═══════════════════════════════════════════════════════════════
// A. Describe（描写增强）
// ═══════════════════════════════════════════════════════════════

function openDescribePanel() {
  // 打开前保存选区
  var sel = _creativeSaveSelection();
  if (!sel.text || sel.text.trim().length < 2) {
    showToast('请先在编辑器中选中文本（或定位光标到段落）');
    return;
  }
  // 显示选中文本预览
  var previewEl = document.getElementById('describe-text-preview');
  if (previewEl) {
    previewEl.textContent = sel.text.length > 200 ? sel.text.substring(0, 200) + '...' : sel.text;
  }
  // 重置结果区
  _creativeShowEmpty('describe-results', '选择增强类型，点击"开始增强"');
  // 重置类型选择
  var typeInputs = document.querySelectorAll('input[name="describe-type"]');
  if (typeInputs.length > 0) typeInputs[0].checked = true;
  // 打开overlay
  var overlay = document.getElementById('describe-overlay');
  if (overlay) overlay.classList.add('active');
}

function closeDescribePanel() {
  var overlay = document.getElementById('describe-overlay');
  if (overlay) overlay.classList.remove('active');
  _describeResult = '';
}

function runDescribe() {
  var typeEl = document.querySelector('input[name="describe-type"]:checked');
  var type = typeEl ? typeEl.value : 'sensory';
  var btn = document.getElementById('describe-run-btn');
  if (btn) { btn.textContent = '增强中...'; btn.disabled = true; }

  _creativeShowLoading('describe-results', 'AI正在增强描写...');

  api('/api/creative/describe', {
    method: 'POST',
    body: JSON.stringify({
      text: _creativeSelectedText,
      type: type,
      context: _creativeContextText
    })
  }).then(function(r) {
    if (btn) { btn.textContent = '开始增强'; btn.disabled = false; }
    if (r.ok && r.result) {
      _describeResult = r.result;
      _renderDescribeResult(r.result, r.original);
    } else {
      _creativeShowError('describe-results', r.error || '增强失败');
    }
  }).catch(function(e) {
    if (btn) { btn.textContent = '开始增强'; btn.disabled = false; }
    _creativeShowError('describe-results', e.message || '网络错误');
  });
}

function _renderDescribeResult(result, original) {
  var el = document.getElementById('describe-results');
  if (!el) return;
  var html = '<div class="ct-result-section">' +
    '<div class="ct-result-label">原文</div>' +
    '<div class="ct-original-text">' + _ctEsc(original || _creativeSelectedText) + '</div>' +
    '</div>' +
    '<div class="ct-result-section">' +
    '<div class="ct-result-label">增强后</div>' +
    '<div class="ct-result-text">' + _ctEsc(result) + '</div>' +
    '</div>' +
    '<div class="ct-actions">' +
      '<button class="btn-sm accept" onclick="applyDescribeResult(\'replace\')">替换原文</button>' +
      '<button class="btn-sm accent" onclick="applyDescribeResult(\'append\')">追加到原文后</button>' +
      '<button class="btn-sm" onclick="copyCreativeText(\'' + 'describe' + '\')">复制结果</button>' +
    '</div>';
  el.innerHTML = html;
}

function applyDescribeResult(action) {
  if (!_describeResult) { showToast('没有可应用的结果'); return; }
  if (action === 'replace') {
    _creativeReplaceSelection(_describeResult);
  } else {
    _creativeAppendAfter(_describeResult);
  }
  closeDescribePanel();
}


// ═══════════════════════════════════════════════════════════════
// B. Expand（场景扩写）
// ═══════════════════════════════════════════════════════════════

function openExpandPanel() {
  var sel = _creativeSaveSelection();
  if (!sel.text || sel.text.trim().length < 2) {
    showToast('请先在编辑器中选中文本（或定位光标到段落）');
    return;
  }
  var previewEl = document.getElementById('expand-text-preview');
  if (previewEl) {
    previewEl.textContent = sel.text.length > 200 ? sel.text.substring(0, 200) + '...' : sel.text;
  }
  _creativeShowEmpty('expand-results', '选择扩写方向和倍数，点击"开始扩写"');
  var dirInputs = document.querySelectorAll('input[name="expand-direction"]');
  if (dirInputs.length > 0) dirInputs[0].checked = true;
  var multEl = document.getElementById('expand-multiplier');
  if (multEl) multEl.value = '2';
  var overlay = document.getElementById('expand-overlay');
  if (overlay) overlay.classList.add('active');
}

function closeExpandPanel() {
  var overlay = document.getElementById('expand-overlay');
  if (overlay) overlay.classList.remove('active');
  _expandResult = '';
}

function runExpand() {
  var dirEl = document.querySelector('input[name="expand-direction"]:checked');
  var direction = dirEl ? dirEl.value : 'dialogue';
  var multEl = document.getElementById('expand-multiplier');
  var multiplier = multEl ? parseFloat(multEl.value) : 2.0;
  var btn = document.getElementById('expand-run-btn');
  if (btn) { btn.textContent = '扩写中...'; btn.disabled = true; }

  _creativeShowLoading('expand-results', 'AI正在扩写场景...');

  api('/api/creative/expand', {
    method: 'POST',
    body: JSON.stringify({
      text: _creativeSelectedText,
      direction: direction,
      multiplier: multiplier,
      context: _creativeContextText
    })
  }).then(function(r) {
    if (btn) { btn.textContent = '开始扩写'; btn.disabled = false; }
    if (r.ok && r.result) {
      _expandResult = r.result;
      _renderExpandResult(r.result, r.original);
    } else {
      _creativeShowError('expand-results', r.error || '扩写失败');
    }
  }).catch(function(e) {
    if (btn) { btn.textContent = '开始扩写'; btn.disabled = false; }
    _creativeShowError('expand-results', e.message || '网络错误');
  });
}

function _renderExpandResult(result, original) {
  var el = document.getElementById('expand-results');
  if (!el) return;
  var html = '<div class="ct-result-section">' +
    '<div class="ct-result-label">原文（' + (original || _creativeSelectedText).length + '字）</div>' +
    '<div class="ct-original-text">' + _ctEsc(original || _creativeSelectedText) + '</div>' +
    '</div>' +
    '<div class="ct-result-section">' +
    '<div class="ct-result-label">扩写后（' + result.length + '字）</div>' +
    '<div class="ct-result-text">' + _ctEsc(result) + '</div>' +
    '</div>' +
    '<div class="ct-actions">' +
      '<button class="btn-sm accept" onclick="applyExpandResult(\'replace\')">替换原文</button>' +
      '<button class="btn-sm accent" onclick="applyExpandResult(\'compare\')">对比查看</button>' +
      '<button class="btn-sm" onclick="copyCreativeText(\'expand\')">复制结果</button>' +
    '</div>';
  el.innerHTML = html;
}

function applyExpandResult(action) {
  if (!_expandResult) { showToast('没有可应用的结果'); return; }
  if (action === 'replace') {
    _creativeReplaceSelection(_expandResult);
    closeExpandPanel();
  } else {
    // 对比查看：切换显示对比视图
    _toggleExpandCompare();
  }
}

function _toggleExpandCompare() {
  var el = document.getElementById('expand-results');
  if (!el) return;
  var compareBtn = el.querySelector('.ct-actions button:nth-child(2)');
  if (el.querySelector('.ct-compare-view')) {
    // 已是对比视图，切回正常
    _renderExpandResult(_expandResult, _creativeSelectedText);
  } else {
    // 切到对比视图
    var html = '<div class="ct-compare-view">' +
      '<div class="ct-compare-col">' +
        '<div class="ct-result-label">原文</div>' +
        '<div class="ct-original-text">' + _ctEsc(_creativeSelectedText) + '</div>' +
      '</div>' +
      '<div class="ct-compare-col">' +
        '<div class="ct-result-label">扩写后</div>' +
        '<div class="ct-result-text">' + _ctEsc(_expandResult) + '</div>' +
      '</div>' +
    '</div>' +
    '<div class="ct-actions">' +
      '<button class="btn-sm accept" onclick="applyExpandResult(\'replace\')">替换原文</button>' +
      '<button class="btn-sm accent" onclick="_toggleExpandCompare()">返回列表</button>' +
      '<button class="btn-sm" onclick="copyCreativeText(\'expand\')">复制结果</button>' +
    '</div>';
    el.innerHTML = html;
  }
}


// ═══════════════════════════════════════════════════════════════
// C. Rewrite（灵活重写）
// ═══════════════════════════════════════════════════════════════

function openRewritePanel() {
  var sel = _creativeSaveSelection();
  if (!sel.text || sel.text.trim().length < 2) {
    showToast('请先在编辑器中选中文本（或定位光标到段落）');
    return;
  }
  var previewEl = document.getElementById('rewrite-text-preview');
  if (previewEl) {
    previewEl.textContent = sel.text.length > 200 ? sel.text.substring(0, 200) + '...' : sel.text;
  }
  _creativeShowEmpty('rewrite-results', '选择重写风格，点击"开始重写"');
  var styleInputs = document.querySelectorAll('input[name="rewrite-style"]');
  if (styleInputs.length > 0) styleInputs[0].checked = true;
  // 隐藏自定义指令输入
  var customWrap = document.getElementById('rewrite-custom-wrap');
  if (customWrap) customWrap.style.display = 'none';
  var customInput = document.getElementById('rewrite-custom-instruction');
  if (customInput) customInput.value = '';
  var overlay = document.getElementById('rewrite-overlay');
  if (overlay) overlay.classList.add('active');
}

function closeRewritePanel() {
  var overlay = document.getElementById('rewrite-overlay');
  if (overlay) overlay.classList.remove('active');
  _rewriteVersions = [];
  _rewriteSelectedIdx = -1;
}

function onRewriteStyleChange() {
  var styleEl = document.querySelector('input[name="rewrite-style"]:checked');
  var style = styleEl ? styleEl.value : 'literary';
  var customWrap = document.getElementById('rewrite-custom-wrap');
  if (customWrap) {
    customWrap.style.display = (style === 'custom') ? 'block' : 'none';
  }
}

function runRewrite() {
  var styleEl = document.querySelector('input[name="rewrite-style"]:checked');
  var style = styleEl ? styleEl.value : 'literary';
  var customInput = document.getElementById('rewrite-custom-instruction');
  var customInstruction = (style === 'custom' && customInput) ? customInput.value.trim() : '';
  if (style === 'custom' && !customInstruction) {
    showToast('请输入自定义重写指令');
    return;
  }
  var btn = document.getElementById('rewrite-run-btn');
  if (btn) { btn.textContent = '重写中...'; btn.disabled = true; }

  _creativeShowLoading('rewrite-results', 'AI正在生成3个重写版本...');

  api('/api/creative/rewrite', {
    method: 'POST',
    body: JSON.stringify({
      text: _creativeSelectedText,
      style: style,
      custom_instruction: customInstruction,
      context: _creativeContextText
    })
  }).then(function(r) {
    if (btn) { btn.textContent = '开始重写'; btn.disabled = false; }
    if (r.ok && r.versions && r.versions.length > 0) {
      _rewriteVersions = r.versions;
      _rewriteSelectedIdx = -1;
      _renderRewriteVersions(r.versions, r.original);
    } else {
      _creativeShowError('rewrite-results', r.error || '重写失败');
    }
  }).catch(function(e) {
    if (btn) { btn.textContent = '开始重写'; btn.disabled = false; }
    _creativeShowError('rewrite-results', e.message || '网络错误');
  });
}

function _renderRewriteVersions(versions, original) {
  var el = document.getElementById('rewrite-results');
  if (!el) return;
  var html = '<div class="ct-result-section">' +
    '<div class="ct-result-label">原文</div>' +
    '<div class="ct-original-text">' + _ctEsc(original || _creativeSelectedText) + '</div>' +
    '</div>';

  versions.forEach(function(v, i) {
    var isSelected = (i === _rewriteSelectedIdx);
    html += '<div class="ct-rewrite-card' + (isSelected ? ' selected' : '') + '" id="rewrite-card-' + i + '" onclick="selectRewriteVersion(' + i + ')">' +
      '<div class="ct-rewrite-card-header">' +
        '<span class="ct-rewrite-version-label">版本 ' + (i + 1) + '</span>' +
        (isSelected ? '<span class="ct-rewrite-badge">已选中</span>' : '<span class="ct-rewrite-hint">点击选择</span>') +
      '</div>' +
      '<div class="ct-rewrite-text">' + _ctEsc(v) + '</div>' +
      '<div class="ct-rewrite-card-actions">' +
        '<button class="btn-sm" onclick="event.stopPropagation();copyCreativeVersion(' + i + ')">复制</button>' +
      '</div>' +
    '</div>';
  });

  html += '<div class="ct-actions">' +
    '<button class="btn-sm accept" id="rewrite-apply-btn" onclick="applyRewriteResult()" ' + (_rewriteSelectedIdx < 0 ? 'disabled' : '') + '>替换原文</button>' +
  '</div>';
  el.innerHTML = html;
}

function selectRewriteVersion(idx) {
  if (idx < 0 || idx >= _rewriteVersions.length) return;
  _rewriteSelectedIdx = idx;
  // 更新UI
  _renderRewriteVersions(_rewriteVersions, _creativeSelectedText);
}

function applyRewriteResult() {
  if (_rewriteSelectedIdx < 0 || !_rewriteVersions[_rewriteSelectedIdx]) {
    showToast('请先选择一个版本');
    return;
  }
  _creativeReplaceSelection(_rewriteVersions[_rewriteSelectedIdx]);
  closeRewritePanel();
}


// ═══════════════════════════════════════════════════════════════
// D. Feedback（5维反馈）
// ═══════════════════════════════════════════════════════════════

function openFeedbackPanel() {
  // Feedback 可以不选中文本，默认使用当前章节
  var sel = _creativeSaveSelection();
  var overlay = document.getElementById('feedback-overlay');
  if (overlay) overlay.classList.add('active');

  // 显示评估范围提示
  var scopeEl = document.getElementById('feedback-scope');
  if (scopeEl) {
    if (sel.text && sel.text.trim().length > 10) {
      scopeEl.textContent = '选中文本（' + sel.text.length + '字）';
    } else {
      scopeEl.textContent = '当前章节全部内容';
    }
  }
  _creativeShowEmpty('feedback-results', '点击"开始评估"运行5维分析');
}

function closeFeedbackPanel() {
  var overlay = document.getElementById('feedback-overlay');
  if (overlay) overlay.classList.remove('active');
}

function runFeedback() {
  var content = _creativeSelectedText;
  var chapterIndex = -1;
  // 如果没有选中文本，使用当前章节
  if (!content || content.trim().length < 10) {
    content = '';
    if (typeof currentChapterIndex !== 'undefined') {
      chapterIndex = currentChapterIndex;
    }
  }
  var btn = document.getElementById('feedback-run-btn');
  if (btn) { btn.textContent = '评估中...'; btn.disabled = true; }

  _creativeShowLoading('feedback-results', 'AI正在从5个维度评估文本...');

  api('/api/creative/feedback', {
    method: 'POST',
    body: JSON.stringify({
      content: content,
      chapter_index: chapterIndex
    })
  }).then(function(r) {
    if (btn) { btn.textContent = '开始评估'; btn.disabled = false; }
    if (r.ok && r.dimensions) {
      _renderFeedbackResult(r);
    } else {
      _creativeShowError('feedback-results', r.error || '评估失败');
    }
  }).catch(function(e) {
    if (btn) { btn.textContent = '开始评估'; btn.disabled = false; }
    _creativeShowError('feedback-results', e.message || '网络错误');
  });
}

function _renderFeedbackResult(data) {
  var el = document.getElementById('feedback-results');
  if (!el) return;
  var dims = data.dimensions || [];
  var overall = data.overall_score || 0;
  var summary = data.summary || '';

  var html = '<div class="ct-feedback-overview">' +
    '<div class="ct-feedback-score-ring" style="--score:' + overall + '">' +
      '<div class="ct-feedback-score-num">' + overall.toFixed(1) + '</div>' +
      '<div class="ct-feedback-score-label">综合评分</div>' +
    '</div>' +
    '<div class="ct-feedback-summary">' + _ctEsc(summary) + '</div>' +
  '</div>';

  // 雷达图
  html += _renderFeedbackRadar(dims);

  // 维度卡片
  html += '<div class="ct-feedback-cards">';
  dims.forEach(function(d, i) {
    var score = d.score || 0;
    var scoreClass = score >= 8 ? 'high' : (score >= 6 ? 'mid' : 'low');
    var scoreColor = score >= 8 ? 'var(--success)' : (score >= 6 ? 'var(--warn)' : 'var(--danger)');
    html += '<div class="ct-feedback-card">' +
      '<div class="ct-feedback-card-header">' +
        '<span class="ct-feedback-dim-name">' + _ctEsc(d.name) + '</span>' +
        '<span class="ct-feedback-dim-score ' + scoreClass + '">' + score.toFixed(1) + '/10</span>' +
      '</div>' +
      '<div class="ct-feedback-bar">' +
        '<div class="ct-feedback-bar-fill" style="width:' + (score * 10) + '%;background:' + scoreColor + '"></div>' +
      '</div>' +
      '<div class="ct-feedback-suggestion">' + _ctEsc(d.suggestion || '暂无建议') + '</div>' +
    '</div>';
  });
  html += '</div>';

  // 不修改原文，只提供反馈
  html += '<div class="ct-actions">' +
    '<button class="btn-sm" onclick="copyFeedbackReport()">复制反馈报告</button>' +
  '</div>';

  el.innerHTML = html;

  // 保存数据供复制使用
  window._lastFeedbackData = data;
}

/**
 * 渲染5维雷达图（纯SVG实现）
 */
function _renderFeedbackRadar(dims) {
  if (!dims || dims.length < 3) return '';
  var n = dims.length;
  var size = 240;  // SVG 尺寸
  var cx = size / 2;
  var cy = size / 2;
  var maxR = 90;   // 最大半径
  var levels = 5;  // 网格层数

  // 计算每个维度的角度（从顶部开始，顺时针）
  var angles = [];
  for (var i = 0; i < n; i++) {
    angles.push(-Math.PI / 2 + (i * 2 * Math.PI / n));
  }

  // 生成网格多边形
  var gridPolygons = '';
  for (var l = 1; l <= levels; l++) {
    var r = (maxR * l / levels);
    var pts = [];
    for (var i = 0; i < n; i++) {
      pts.push((cx + r * Math.cos(angles[i])).toFixed(1) + ',' + (cy + r * Math.sin(angles[i])).toFixed(1));
    }
    gridPolygons += '<polygon points="' + pts.join(' ') + '" class="ct-radar-grid" />';
  }

  // 生成轴线
  var axisLines = '';
  for (var i = 0; i < n; i++) {
    axisLines += '<line x1="' + cx + '" y1="' + cy + '" ' +
      'x2="' + (cx + maxR * Math.cos(angles[i])).toFixed(1) + '" ' +
      'y2="' + (cy + maxR * Math.sin(angles[i])).toFixed(1) + '" class="ct-radar-axis" />';
  }

  // 生成数据多边形
  var dataPts = [];
  var dataDots = '';
  for (var i = 0; i < n; i++) {
    var score = dims[i].score || 0;
    var r = (maxR * score / 10);
    var x = cx + r * Math.cos(angles[i]);
    var y = cy + r * Math.sin(angles[i]);
    dataPts.push(x.toFixed(1) + ',' + y.toFixed(1));
    dataDots += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3" class="ct-radar-dot" />';
  }

  // 生成标签
  var labels = '';
  for (var i = 0; i < n; i++) {
    var labelR = maxR + 18;
    var lx = cx + labelR * Math.cos(angles[i]);
    var ly = cy + labelR * Math.sin(angles[i]);
    var score = dims[i].score || 0;
    var anchor = 'middle';
    if (Math.abs(Math.cos(angles[i])) > 0.5) {
      anchor = (Math.cos(angles[i]) > 0) ? 'start' : 'end';
    }
    labels += '<text x="' + lx.toFixed(1) + '" y="' + ly.toFixed(1) + '" ' +
      'text-anchor="' + anchor + '" dominant-baseline="middle" class="ct-radar-label">' +
      dims[i].name + '</text>';
    labels += '<text x="' + lx.toFixed(1) + '" y="' + (ly + 12).toFixed(1) + '" ' +
      'text-anchor="' + anchor + '" dominant-baseline="middle" class="ct-radar-score">' +
      score.toFixed(1) + '</text>';
  }

  return '<div class="ct-radar-container">' +
    '<svg viewBox="0 0 ' + size + ' ' + size + '" class="ct-radar-svg">' +
      gridPolygons +
      axisLines +
      '<polygon points="' + dataPts.join(' ') + '" class="ct-radar-data" />' +
      dataDots +
      labels +
    '</svg>' +
  '</div>';
}


// ═══════════════════════════════════════════════════════════════
// 通用：复制功能
// ═══════════════════════════════════════════════════════════════

function copyCreativeText(tool) {
  var text = '';
  if (tool === 'describe') text = _describeResult;
  else if (tool === 'expand') text = _expandResult;
  if (!text) { showToast('没有可复制的内容'); return; }
  _copyToClipboard(text);
}

function copyCreativeVersion(idx) {
  if (idx < 0 || idx >= _rewriteVersions.length) return;
  _copyToClipboard(_rewriteVersions[idx]);
}

function copyFeedbackReport() {
  var data = window._lastFeedbackData;
  if (!data) { showToast('没有可复制的反馈'); return; }
  var text = '5维写作反馈报告\n';
  text += '综合评分: ' + (data.overall_score || 0).toFixed(1) + '/10\n\n';
  if (data.dimensions) {
    data.dimensions.forEach(function(d) {
      text += '【' + d.name + '】' + (d.score || 0).toFixed(1) + '/10\n';
      text += (d.suggestion || '') + '\n\n';
    });
  }
  if (data.summary) text += '总体评价: ' + data.summary;
  _copyToClipboard(text);
}

function _copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      showToast('已复制到剪贴板');
    }).catch(function() {
      _fallbackCopy(text);
    });
  } else {
    _fallbackCopy(text);
  }
}

function _fallbackCopy(text) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); showToast('已复制到剪贴板'); }
  catch(e) { showToast('复制失败，请手动选择复制'); }
  document.body.removeChild(ta);
}


// ═══════════════════════════════════════════════════════════════
// 单选卡片选中状态回退（兼容不支持 :has() 的浏览器）
// ═══════════════════════════════════════════════════════════════
function _creativeInitRadioCards() {
  var groups = ['describe-type', 'expand-direction', 'rewrite-style'];
  groups.forEach(function(name) {
    var inputs = document.querySelectorAll('input[name="' + name + '"]');
    inputs.forEach(function(input) {
      function sync() {
        inputs.forEach(function(other) {
          var card = other.closest('.ct-radio-card');
          if (card) {
            if (other.checked) card.classList.add('ct-checked');
            else card.classList.remove('ct-checked');
          }
        });
      }
      input.addEventListener('change', sync);
      if (input.checked) {
        var card = input.closest('.ct-radio-card');
        if (card) card.classList.add('ct-checked');
      }
    });
  });
}

// 页面加载后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _creativeInitRadioCards);
} else {
  _creativeInitRadioCards();
}

// ═══════════════════════════════════════════════════════════════
// 暴露到全局作用域（供 HTML onclick 调用）
// ═══════════════════════════════════════════════════════════════
window.openDescribePanel = openDescribePanel;
window.closeDescribePanel = closeDescribePanel;
window.runDescribe = runDescribe;
window.applyDescribeResult = applyDescribeResult;

window.openExpandPanel = openExpandPanel;
window.closeExpandPanel = closeExpandPanel;
window.runExpand = runExpand;
window.applyExpandResult = applyExpandResult;
window._toggleExpandCompare = _toggleExpandCompare;

window.openRewritePanel = openRewritePanel;
window.closeRewritePanel = closeRewritePanel;
window.runRewrite = runRewrite;
window.onRewriteStyleChange = onRewriteStyleChange;
window.selectRewriteVersion = selectRewriteVersion;
window.applyRewriteResult = applyRewriteResult;
window.copyCreativeVersion = copyCreativeVersion;

window.openFeedbackPanel = openFeedbackPanel;
window.closeFeedbackPanel = closeFeedbackPanel;
window.runFeedback = runFeedback;
window.copyFeedbackReport = copyFeedbackReport;
window.copyCreativeText = copyCreativeText;

// ═════════════════════════════════════════════════════════════
// E 连线框 ↔ C5 协作草稿联动 + AI修改统一队列
// ═════════════════════════════════════════════════════════════

/**
 * 连线框唤起C5改写（从连线框"需更新"段落触发）
 * @param {object} node - 连线框节点（含设定信息）
 * 联动规则：连线框不自动改正文，需用户在编辑器选中段落后用C5改写
 */
function invokeC5FromWireframe(node) {
  if (!node) return;
  // 构建设定上下文提示
  var settingCtx = '【连线框设定参考】\n' +
    '类型：' + (node.type || '自由') + '\n' +
    '标题：' + (node.title || '') + '\n' +
    '摘要：' + (node.summary || '') + '\n' +
    '关键引用：' + (node.quotes || '') + '\n' +
    '章节引用：' + (node.chapter_ref || '');

  // 存入全局供C5改写时读取
  window._wireframeC5Context = settingCtx;

  if (typeof showToast === 'function') {
    showToast('已加载连线框设定，请在编辑器中选中需修改的段落，点击🔄重写');
  }

  // 如果编辑器有焦点，尝试自动触发重写面板
  var editor = document.getElementById('editor-content');
  if (editor) {
    editor.focus();
  }
}

/**
 * AI修改统一队列：聚合时间线+连线框的校验问题，按段落一次修
 * 避免两个校验来源对同一段落分别发AI请求导致冲突
 *
 * @param {object} issues - { timeline: [...], wireframe: [...] }
 * @returns {Promise} 修改结果
 */
async function unifiedAIRewrite(issues) {
  issues = issues || {};
  var timelineIssues = issues.timeline || [];
  var wireframeIssues = issues.wireframe || [];

  if (timelineIssues.length === 0 && wireframeIssues.length === 0) {
    return { ok: false, message: '无待修改问题' };
  }

  // 按段落聚合：同一段落的多个问题合并
  var byParagraph = {};
  timelineIssues.forEach(function(item) {
    var key = item.paragraph_idx || item.chapter_idx || 'default';
    if (!byParagraph[key]) byParagraph[key] = { timeline: [], wireframe: [] };
    byParagraph[key].timeline.push(item.desc || item.message || '');
  });
  wireframeIssues.forEach(function(item) {
    var key = item.paragraph_idx || item.chapter_idx || 'default';
    if (!byParagraph[key]) byParagraph[key] = { timeline: [], wireframe: [] };
    byParagraph[key].wireframe.push(item.desc || item.setting || '');
  });

  // 构建统一修改指令
  var instructions = [];
  Object.keys(byParagraph).forEach(function(key) {
    var p = byParagraph[key];
    var parts = [];
    if (p.timeline.length > 0) {
      parts.push('【时间线校验问题】\n' + p.timeline.join('\n'));
    }
    if (p.wireframe.length > 0) {
      parts.push('【连线框设定校验问题】\n' + p.wireframe.join('\n'));
    }
    instructions.push('段落' + key + '需修改：\n' + parts.join('\n\n'));
  });

  var combinedInstruction = instructions.join('\n---\n');
  var wireframeCtx = window._wireframeC5Context || '';

  var prompt = '请根据以下校验问题统一修改正文（同一段落的多个问题一次性修，不要分次修）：\n\n' +
    combinedInstruction +
    (wireframeCtx ? '\n\n' + wireframeCtx : '') +
    '\n\n要求：\n1. 保持原文风格和叙事连贯\n2. 仅修改有问题的部分，不改动正常内容\n3. 修改后确保时间线顺序和设定一致性都满足';

  try {
    if (typeof api === 'undefined') {
      return { ok: false, error: 'api未定义' };
    }
    // 后端端点为 /api/ai/chat（ChatRequest: messages 数组）；旧的 /api/ai/chat-stream 路径不存在
    var res = await api('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ messages: [{ role: 'user', content: prompt }] })
    });
    if (!res || !res.ok) {
      return { ok: false, error: (res && res.error) || 'AI修改失败' };
    }
    // 清除连线框上下文
    window._wireframeC5Context = null;
    return { ok: true, result: res.content };
  } catch (e) {
    console.error('[unifiedAIRewrite] 失败:', e);
    return { ok: false, error: e.message };
  }
}

window.invokeC5FromWireframe = invokeC5FromWireframe;
window.unifiedAIRewrite = unifiedAIRewrite;
