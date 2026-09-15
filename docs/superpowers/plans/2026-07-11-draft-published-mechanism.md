# 草稿→成品机制 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为书斋V65添加草稿→成品机制：所有AI产出（生成、修复、选段编辑）先写入草稿区，用户在左右对比面板确认后才替换成品正文。同时改进AI修复策略，按内容类/风格类分批修复。

**Architecture:** 新增 `draft-ui.js` 模块管理草稿状态和对比面板渲染。修改 `init.js` 的修复函数和 `validate-ui.js` 的AI生成回调，使其写入草稿而非直接保存。对比面板复用 `.editor-area` 的 flex 空间，草稿模式下编辑器主区域变为左右分栏。

**Tech Stack:** 原生JS（无框架）、CSS Flexbox、文本diff算法（行级，前端纯JS实现）

---

## 文件结构

| 文件 | 职责 | 操作 |
|-----|------|------|
| `frontend/js/modules/draft-ui.js` | 草稿模式核心逻辑 | **新建** |
| `frontend/js/modules/init.js` | 修复函数改为写草稿 | **修改** |
| `frontend/js/modules/validate-ui.js` | AI生成回调改为写草稿；保存按钮适配 | **修改** |
| `frontend/index.html` | 对比面板HTML模板 | **修改** |
| `frontend/css/style.css` | diff高亮、对比面板样式 | **修改** |

---

### Task 1: 创建 draft-ui.js — 草稿状态管理核心模块

**Files:**
- Create: `frontend/js/modules/draft-ui.js`

- [ ] **Step 1: 创建 draft-ui.js 基础结构和状态管理**

```javascript
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
    enter: function(draftText) {
      var editorEl = document.getElementById('editor-content');
      if (!editorEl) return;
      // 快照当前成品
      _publishedContent = editorEl.innerText || '';
      _draftContent = draftText;
      _draftMode = true;
      // 将草稿内容写入编辑器
      editorEl.innerText = draftText;
      // 显示对比面板
      _showComparePanel();
      // UI标记
      _updateToolbarState();
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

    /** 退出草稿模式（内部用） */
    _exitMode: function() { _exitMode(); },

    /** 强制退出（切章时调用） */
    forceExit: function() {
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
    if (panel) {
      panel.style.display = 'flex';
      _renderDiff();
    }
    // 编辑器区域切换为左右布局
    var editorArea = document.querySelector('.editor-area');
    if (editorArea) editorArea.classList.add('draft-mode');
  }

  function _hideComparePanel() {
    var panel = document.getElementById('draft-compare-panel');
    if (panel) panel.style.display = 'none';
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

  /** 行级diff：逐行对比成品与草稿，返回差异标记数组 */
  function _computeDiff(published, draft) {
    var pubLines = published.split('\n');
    var draftLines = draft.split('\n');
    var result = [];
    // LCS-based行diff简化版：标记删除的行和新增的行
    var pubSet = {};
    pubLines.forEach(function(l) { pubSet[l] = (pubSet[l] || 0) + 1; });
    draftLines.forEach(function(line, i) {
      if (pubSet[line] && pubSet[line] > 0) {
        pubSet[line]--;
        result.push({type: 'equal', line: line, draftIdx: i});
      } else {
        result.push({type: 'add', line: line, draftIdx: i});
      }
    });
    pubLines.forEach(function(line, i) {
      if (pubSet[line] && pubSet[line] > 0) {
        pubSet[line]--;
        result.push({type: 'remove', line: line, pubIdx: i});
      }
    });
    // 按位置排序（remove按pubIdx，其他按出现顺序）
    result.sort(function(a, b) {
      var aIdx = a.type === 'remove' ? a.pubIdx : a.draftIdx;
      var bIdx = b.type === 'remove' ? b.pubIdx : b.draftIdx;
      return aIdx - bIdx;
    });
    return result;
  }

  /** 渲染差异到对比面板 */
  function _renderDiff() {
    var body = document.getElementById('draft-compare-body');
    if (!body || !_publishedContent || !_draftContent) return;
    var editorEl = document.getElementById('editor-content');
    // 获取编辑器最新内容（用户可能手动改过草稿）
    var currentDraft = editorEl ? (editorEl.innerText || '') : (_draftContent || '');
    var diffs = _computeDiff(_publishedContent, currentDraft);
    var html = '';
    diffs.forEach(function(d) {
      if (d.type === 'equal') {
        html += '<div class="diff-line diff-equal">' + _escHtml(d.line) + '</div>';
      } else if (d.type === 'add') {
        html += '<div class="diff-line diff-add">+ ' + _escHtml(d.line) + '</div>';
      } else if (d.type === 'remove') {
        html += '<div class="diff-line diff-remove">- ' + _escHtml(d.line) + '</div>';
      }
    });
    // 统计
    var addCount = diffs.filter(function(d){ return d.type === 'add'; }).length;
    var removeCount = diffs.filter(function(d){ return d.type === 'remove'; }).length;
    var header = document.getElementById('draft-compare-stats');
    if (header) {
      header.textContent = '新增 ' + addCount + ' 行 · 删除 ' + removeCount + ' 行';
    }
    body.innerHTML = html;
  }

  function _escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── 编辑器input事件：用户手动编辑草稿时自动刷新diff ──
  document.addEventListener('input', function(e) {
    if (!_draftMode) return;
    if (e.target && e.target.id === 'editor-content') {
      clearTimeout(window._diffTimer);
      window._diffTimer = setTimeout(_renderDiff, 500);
    }
  });

})();
```

- [ ] **Step 2: 在 index.html 中加载 draft-ui.js（在 validate-ui.js 之前）**

在 `index.html` 中找到 `validate-ui.js` 的 `<script>` 标签，在其前面添加：
```html
<script src="js/modules/draft-ui.js"></script>
```

---

### Task 2: 对比面板HTML模板和CSS样式

**Files:**
- Modify: `frontend/index.html:1596`（`.editor-area` 内）
- Modify: `frontend/css/style.css:155`

- [ ] **Step 1: 在 index.html 的 .editor-area 末尾添加对比面板HTML**

在 `frontend/index.html` 中找到 `.editor-area` 的关闭标签，在其前面添加：

```html
<!-- 草稿对比面板（草稿模式下显示） -->
<div class="draft-compare-panel" id="draft-compare-panel" style="display:none">
  <div class="compare-header">
    <span class="compare-title">📝 草稿对比</span>
    <span class="compare-stats" id="draft-compare-stats"></span>
    <button class="compare-close-btn" onclick="DraftManager._exitMode()" title="关闭对比">✕</button>
  </div>
  <div class="compare-body" id="draft-compare-body"></div>
  <div class="compare-actions">
    <button class="compare-btn compare-accept" onclick="DraftManager.accept()">
      ✓ 采纳为成品
    </button>
    <button class="compare-btn compare-edit" onclick="DraftManager._exitMode()">
      ✎ 继续编辑
    </button>
    <button class="compare-btn compare-discard" onclick="DraftManager.discard()">
      ✗ 丢弃草稿
    </button>
  </div>
</div>
```

- [ ] **Step 2: 在 style.css 中添加草稿模式和对比面板样式**

在 `frontend/css/style.css` 末尾添加：

```css
/* ═══════════════════════════════════════════
   草稿→成品机制样式
   ═══════════════════════════════════════════ */

/* 草稿模式：编辑器区域变为左右分栏 */
.editor-area.draft-mode {
  flex-direction: row !important;
}

.editor-area.draft-mode .editor-scroll {
  flex: 1;
  min-width: 0;
  border-right: 1px solid var(--border, rgba(255,255,255,0.08));
}

/* 对比面板 */
.draft-compare-panel {
  width: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel, #1a1a2e);
  border-left: 1px solid var(--border, rgba(255,255,255,0.08));
  opacity: 0;
  overflow: hidden;
  transition: width 0.3s ease, min-width 0.3s ease, opacity 0.3s ease;
}

.draft-compare-panel[style*="display: flex"],
.draft-compare-panel[style*="flex"] {
  width: 40%;
  min-width: 280px;
  max-width: 50%;
  opacity: 1;
}

.compare-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
  font-size: 13px;
  flex-shrink: 0;
}

.compare-title {
  font-weight: 600;
  color: var(--fg, #e0e0e0);
}

.compare-stats {
  color: var(--muted, #888);
  font-size: 12px;
}

.compare-close-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--muted, #888);
  cursor: pointer;
  font-size: 14px;
  padding: 2px 6px;
  border-radius: 4px;
}
.compare-close-btn:hover {
  background: rgba(255,255,255,0.06);
  color: var(--fg, #e0e0e0);
}

/* 对比内容区 */
.compare-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  font-size: 13px;
  line-height: 1.8;
  font-family: var(--display, 'Noto Sans CJK SC', sans-serif);
}

.diff-line {
  padding: 1px 14px;
  white-space: pre-wrap;
  word-break: break-all;
}

.diff-equal {
  color: var(--muted, #777);
}

.diff-add {
  background: rgba(34,197,94,0.12);
  color: #4ade80;
  border-left: 3px solid #22c55e;
  margin: 0 -14px;
  padding-left: 17px;
}

.diff-remove {
  background: rgba(239,68,68,0.12);
  color: #f87171;
  border-left: 3px solid #ef4444;
  margin: 0 -14px;
  padding-left: 17px;
  text-decoration: line-through;
}

/* 操作按钮区 */
.compare-actions {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border, rgba(255,255,255,0.08));
  flex-shrink: 0;
}

.compare-btn {
  flex: 1;
  padding: 7px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.compare-btn:hover { opacity: 0.85; }

.compare-accept {
  background: #22c55e;
  color: #fff;
}

.compare-edit {
  background: rgba(255,255,255,0.08);
  color: var(--fg, #e0e0e0);
}

.compare-discard {
  background: rgba(239,68,68,0.15);
  color: #f87171;
}

/* 草稿模式下保存按钮样式 */
.draft-accept-btn {
  background: #22c55e !important;
  color: #fff !important;
}

/* 草稿模式下编辑器提示条 */
.editor-area.draft-mode .editor-scroll::before {
  content: '📋 草稿模式 — 编辑器中显示的是草稿内容';
  display: block;
  text-align: center;
  padding: 6px;
  font-size: 12px;
  color: #facc15;
  background: rgba(250,204,21,0.08);
  border-bottom: 1px solid rgba(250,204,21,0.15);
  position: sticky;
  top: 0;
  z-index: 10;
}
```

---

### Task 3: 修改 validate-ui.js — 保存按钮适配草稿模式

**Files:**
- Modify: `frontend/js/modules/validate-ui.js:688-711`

- [ ] **Step 1: 修改保存按钮点击事件，草稿模式下走采纳逻辑**

找到 `validate-ui.js` 第688行的 `btnSave.addEventListener('click', async function() {`，修改函数体开头部分：

将原来的：
```javascript
btnSave.addEventListener('click', async function() {
    btnSave.textContent = '⏳ 保存中…';
    btnSave.disabled = true;
    try {
```

改为：
```javascript
btnSave.addEventListener('click', async function() {
    // 草稿模式下，保存按钮=采纳按钮
    if (window.DraftManager && DraftManager.isActive()) {
      await DraftManager.accept();
      return;
    }
    btnSave.textContent = '⏳ 保存中…';
    btnSave.disabled = true;
    try {
```

- [ ] **Step 2: 修改自动保存函数 autoSaveBeforeChapterSwitch，增加草稿检测**

在 `validate-ui.js` 或 `editor.js` 中找到切章前自动保存逻辑，在其前面加入草稿提示：

如果自动保存在 `editor.js` 中（约第12行 `autoSaveBeforeChapterSwitch`），在函数开头添加：
```javascript
// 草稿模式下不自动保存成品，提示用户
if (window.DraftManager && DraftManager.isActive()) {
  if (typeof showToast === 'function') showToast('⚠️ 有未确认草稿，请先采纳或丢弃');
  return false; // 阻止切章
}
```

---

### Task 4: 修改 validate-ui.js — AI生成正文回调改为写草稿

**Files:**
- Modify: `frontend/js/modules/validate-ui.js:834-838`

- [ ] **Step 1: 修改AI生成完成后的自动保存逻辑**

找到 `validate-ui.js` 约第834行的自动保存代码：

将原来的：
```javascript
// 自动保存到后端
try {
    await saveChapter(currentChapterIndex, r.content);
} catch(e) { console.error('Auto-save chapter failed:', e); }
showToast && showToast('AI生成完成（已自动保存）');
```

改为：
```javascript
// AI生成内容写入草稿，不直接保存为成品
try {
    if (window.DraftManager) {
        DraftManager.enter(r.content);
        showToast && showToast('AI生成完成（草稿模式，请确认后采纳）');
    } else {
        await saveChapter(currentChapterIndex, r.content);
        showToast && showToast('AI生成完成（已自动保存）');
    }
} catch(e) { console.error('Draft enter failed:', e); }
```

---

### Task 5: 修改 init.js — valAIFixAll 改为写草稿 + 分批修复

**Files:**
- Modify: `frontend/js/modules/init.js:1196-1398`

- [ ] **Step 1: 修改问题分类逻辑（在构建prompt之前加入分批）**

找到 `init.js` 约第1196行 `var problemList = '';`，在其前面加入分类逻辑：

将原来的问题列表构建：
```javascript
var problemList = '';
problems.forEach(function(p, i) {
    problemList += (i+1) + '. 【' + p.type + '】' + p.problem + '\n';
});
```

改为分批处理：
```javascript
// 按类型分批：内容类 vs 风格类
var contentTypes = ['drift', 'timeline', 'conflict'];
var styleTypes = ['style', 'duplicate', 'twist'];
var contentProblems = problems.filter(function(p) { return contentTypes.indexOf(p.type) >= 0; });
var styleProblems = problems.filter(function(p) { return styleTypes.indexOf(p.type) >= 0; });
// 构建当前批次问题列表
var currentBatch = contentProblems.length > 0 ? contentProblems : styleProblems;
var batchLabel = contentProblems.length > 0 ? '内容修复' : '风格润色';
var problemList = '';
currentBatch.forEach(function(p, i) {
    problemList += (i+1) + '. 【' + p.type + '】' + p.problem + '\n';
});
```

- [ ] **Step 2: 修改替换逻辑，改为写草稿而非直接保存**

找到 `init.js` 约第1326行的替换保存逻辑：

将原来的：
```javascript
editorEl.innerHTML = textToHTML(newContent);
updateWordCount();
if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
    chapters[currentChapterIndex].content = newContent;
    chapters[currentChapterIndex].word_count = newContent.length;
}
await saveChapter(currentChapterIndex, newContent);
```

改为：
```javascript
// 修复结果写入草稿，不直接替换成品
if (window.DraftManager) {
    DraftManager.enter(newContent);
    showToast && showToast(batchLabel + '完成（' + replaceCount + '处修改，' + skipCount + '处跳过），请对比确认');
} else {
    // 降级：无草稿模块时直接替换（向后兼容）
    editorEl.innerHTML = textToHTML(newContent);
    updateWordCount();
    if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
        chapters[currentChapterIndex].content = newContent;
        chapters[currentChapterIndex].word_count = newContent.length;
    }
    await saveChapter(currentChapterIndex, newContent);
}
```

- [ ] **Step 3: 修改摘要区域，显示分批信息和"修复下一批"按钮**

找到修复摘要渲染部分（约第1343行），在摘要中增加分批信息：

将原来的摘要toast：
```javascript
showToast && showToast('修复完成：' + replaceCount + '处修改，' + skipCount + '处跳过');
```

改为在摘要中追加"下一批"按钮（如果还有另一批问题）：
```javascript
var summaryText = batchLabel + '：' + replaceCount + '处修改，' + skipCount + '处跳过';
showToast && showToast(summaryText);
// 如果还有另一批，追加按钮
var otherBatch = contentProblems.length > 0 ? styleProblems : contentProblems;
if (otherBatch.length > 0) {
    var fixAllBar = document.getElementById('fix-all-bar');
    if (fixAllBar) {
        var nextBtn = document.createElement('button');
        nextBtn.textContent = '🔧 修复下一批（' + (contentProblems.length > 0 ? '风格润色' : '内容修复') + '）';
        nextBtn.style.cssText = 'background:rgba(255,255,255,0.06);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:6px 14px;cursor:pointer;font-size:13px;margin-left:8px';
        nextBtn.onclick = function() {
            window._allValProblems = otherBatch;
            window.valAIFixAll();
        };
        fixAllBar.appendChild(nextBtn);
    }
}
```

---

### Task 6: 修改 init.js — valAIFix（单项修复）改为写草稿

**Files:**
- Modify: `frontend/js/modules/init.js:880-1070`

- [ ] **Step 1: 修改单项修复的替换保存逻辑**

找到 `valAIFix` 函数中的替换保存部分（约第1040-1060行），将直接保存改为写草稿。

找到类似代码：
```javascript
editorEl.innerHTML = textToHTML(newContent);
updateWordCount();
if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
    chapters[currentChapterIndex].content = newContent;
    chapters[currentChapterIndex].word_count = newContent.length;
}
await saveChapter(currentChapterIndex, newContent);
```

改为：
```javascript
if (window.DraftManager) {
    DraftManager.enter(newContent);
    showToast && showToast('修复完成，请对比确认');
} else {
    editorEl.innerHTML = textToHTML(newContent);
    updateWordCount();
    if (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
        chapters[currentChapterIndex].content = newContent;
        chapters[currentChapterIndex].word_count = newContent.length;
    }
    await saveChapter(currentChapterIndex, newContent);
}
```

---

### Task 7: 章节切换时的草稿保护

**Files:**
- Modify: `frontend/js/modules/init.js` 或 `validate-ui.js`（找到切章函数）

- [ ] **Step 1: 在切章逻辑中加入草稿检测**

找到章节切换函数（可能在 `init.js` 中的 `selectChapter` 或 `loadChapter` 函数），在加载新章节内容之前加入：

```javascript
// 切章前：如果有未确认草稿，提示用户
if (window.DraftManager && DraftManager.isActive()) {
    var action = confirm('当前章节有未确认的草稿。\n\n点击"确定"丢弃草稿并切换章节\n点击"取消"留在当前章节');
    if (!action) return; // 用户选择留下
    DraftManager.forceExit();
}
```

- [ ] **Step 2: 验证所有入口都受保护**

确认以下场景都会触发草稿检测：
1. 左侧面板点击章节切换
2. AI生成下一章
3. 键盘快捷键切换（如果有）

---

### Task 8: 端到端测试

**Files:** 无新增修改

- [ ] **Step 1: 测试AI生成→草稿→采纳流程**

1. 打开项目，进入写作页
2. 触发AI生成正文
3. 验证：编辑器显示生成内容，对比面板展开，成品正文显示在右侧
4. 验证：保存按钮变为"采纳为成品"
5. 点击"采纳"，验证内容保存到chapter文件
6. 验证：对比面板关闭，编辑器恢复正常模式

- [ ] **Step 2: 测试一键修复→草稿→丢弃流程**

1. 先有成品正文，运行全文检查
2. 有问题后点击"一键全部修复"
3. 验证：只处理内容类问题（drift/timeline/conflict），结果写入草稿
4. 验证：对比面板显示差异高亮
5. 点击"丢弃草稿"
6. 验证：编辑器恢复为修复前的成品内容

- [ ] **Step 3: 测试草稿模式下手动编辑**

1. 进入草稿模式后，在编辑器中手动修改几个字
2. 验证：对比面板自动刷新差异
3. 点击"采纳"
4. 验证：保存的是手动修改后的最终版本

- [ ] **Step 4: 测试切章草稿保护**

1. 进入草稿模式
2. 点击左侧面板切换到另一章
3. 验证：弹出确认对话框
4. 点击"取消"，验证留在当前章
5. 点击"确定"，验证草稿被丢弃并切换

- [ ] **Step 5: 测试分批修复**

1. 运行检查，确保有内容类和风格类问题
2. 点击"一键全部修复"
3. 验证：只修复内容类问题
4. 采纳后，点击"修复下一批（风格润色）"
5. 验证：风格类问题被修复并进入草稿模式

- [ ] **Step 6: 测试向后兼容（无DraftManager时）**

1. 在HTML中注释掉 draft-ui.js 的加载
2. 验证：AI生成和修复仍然正常工作（降级为直接保存）
