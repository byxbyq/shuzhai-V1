// ═══════════════════════════════════════════
// 阅读器模块 - reader.js
// ═══════════════════════════════════════════

var Reader = (function() {
  // ── 状态 ──
  var currentProject = '';      // 当前阅读的项目路径
  var currentChapter = 0;        // 当前章节索引
  var chapterList = [];          // 章节列表
  var chapterVL = null;          // VirtualList 实例（章节目录）
  var projectTitle = '';         // 项目标题
  var totalChapters = 0;
  
  // ── 阅读设置（localStorage持久化）──
  var settings = {
    fontSize: 18,        // 字号
    lineHeight: 1.8,     // 行距
    theme: 'day',        // day / night / sepia
    fontFamily: 'system' // system / serif / sans
  };
  
  // ── 初始化 ──
  function init() {
    loadSettings();
    bindEvents();
  }
  
  function loadSettings() {
    try {
      var saved = localStorage.getItem('reader-settings');
      if (saved) settings = Object.assign(settings, JSON.parse(saved));
    } catch(e) {}
  }
  
  function saveSettings() {
    localStorage.setItem('reader-settings', JSON.stringify(settings));
  }
  
  function applySettings() {
    var content = document.getElementById('reader-content');
    if (!content) return;
    content.style.fontSize = settings.fontSize + 'px';
    content.style.lineHeight = settings.lineHeight;
    
    // 字体
    var fonts = { system: '', serif: 'Georgia, "Noto Serif SC", serif', sans: '"Noto Sans SC", sans-serif' };
    content.style.fontFamily = fonts[settings.fontFamily] || '';
    
    // 主题
    var overlay = document.getElementById('reader-overlay');
    overlay.classList.remove('reader-theme-day', 'reader-theme-night', 'reader-theme-sepia');
    overlay.classList.add('reader-theme-' + settings.theme);
    
    // 更新UI控件
    var fsVal = document.getElementById('reader-fontsize-val');
    if (fsVal) fsVal.textContent = settings.fontSize;
    var lhVal = document.getElementById('reader-lineheight-val');
    if (lhVal) lhVal.textContent = settings.lineHeight.toFixed(1);
  }
  
  // ── 打开/关闭阅读器 ──
  function open(projectPath, chapter) {
    currentProject = projectPath;
    currentChapter = chapter || 0;
    var overlay = document.getElementById('reader-overlay');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    applySettings();
    loadChapter(currentChapter);
  }
  
  function close() {
    saveProgress();
    var overlay = document.getElementById('reader-overlay');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  }
  
  // ── 加载章节 ──
  function loadChapter(index) {
    if (!currentProject) return;
    currentChapter = index;
    
    var contentEl = document.getElementById('reader-content');
    contentEl.innerHTML = '<div class="reader-loading">加载中...</div>';
    document.getElementById('reader-chapter-title').textContent = '';
    
    api('/api/reader/chapter?project=' + encodeURIComponent(currentProject) + '&index=' + index)
      .then(function(r) {
        if (!r.ok) {
          contentEl.innerHTML = '<div class="reader-error">' + escapeHtml(r.error || '加载失败') + '</div>';
          return;
        }
        
        projectTitle = r.project_title;
        chapterList = r.chapter_list || [];
        totalChapters = r.total_chapters;
        
        document.getElementById('reader-project-title').textContent = projectTitle;
        document.getElementById('reader-chapter-title').textContent = r.title;
        document.getElementById('reader-chapter-info').textContent = '第' + (index + 1) + '章 / 共' + totalChapters + '章';
        
        // 渲染正文
        contentEl.innerHTML = textToHTML(r.content);
        
        // 更新导航按钮状态
        document.getElementById('reader-prev-btn').disabled = (index <= 0);
        document.getElementById('reader-next-btn').disabled = (index >= totalChapters - 1);
        
        // 渲染章节目录
        renderChapterList();
        
        // 滚动到顶部
        document.getElementById('reader-scroll').scrollTop = 0;
        
        // 保存进度
        saveProgress();
      })
      .catch(function(err) {
        contentEl.innerHTML = '<div class="reader-error">网络错误</div>';
      });
  }
  
  // ── 章节目录 ──
  function renderChapterList() {
    var listEl = document.getElementById('reader-chapter-list');
    listEl.textContent = '';

    // 章节超过50时启用虚拟滚动，否则直接渲染
    if (chapterList.length > 50 && typeof VirtualList === 'function') {
      chapterVL = new VirtualList(listEl, {
        itemHeight: 36,
        items: chapterList,
        selectedIdx: currentChapter,
        className: 'reader-chapter-item',
        renderFn: function(ch, i, isSelected) {
          return '<div class="reader-chapter-item' + (isSelected ? ' active' : '') + '">' +
            '<span class="reader-chapter-num">' + (i + 1) + '</span>' +
            '<span class="reader-chapter-name">' + escapeHtml(ch.title) + '</span></div>';
        },
        onSelect: function(ch, idx) {
          loadChapter(idx);
          toggleChapterList(false);
        }
      });
    } else {
      // 章节少于50，直接渲染（更快、更简单）
      chapterVL = null;
      chapterList.forEach(function(ch, i) {
        var item = document.createElement('div');
        item.className = 'reader-chapter-item' + (i === currentChapter ? ' active' : '');
        item.innerHTML = '<span class="reader-chapter-num">' + (i + 1) + '</span><span class="reader-chapter-name">' + escapeHtml(ch.title) + '</span>';
        item.addEventListener('click', function() {
          loadChapter(i);
          toggleChapterList(false);
        });
        listEl.appendChild(item);
      });
    }
  }
  
  function toggleChapterList(force) {
    var panel = document.getElementById('reader-chapter-panel');
    if (force === undefined) {
      panel.classList.toggle('active');
    } else if (force) {
      panel.classList.add('active');
    } else {
      panel.classList.remove('active');
    }
  }
  
  // ── 阅读进度 ──
  function saveProgress() {
    if (!currentProject) return;
    var scrollEl = document.getElementById('reader-scroll');
    var scrollPercent = scrollEl ? (scrollEl.scrollTop / (scrollEl.scrollHeight - scrollEl.clientHeight || 1)) : 0;
    
    api('/api/reader/progress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project: currentProject,
        chapter: currentChapter,
        scroll: scrollPercent
      })
    }).catch(function(){});
  }
  
  // ── 上一章/下一章 ──
  function prevChapter() {
    if (currentChapter > 0) loadChapter(currentChapter - 1);
  }
  
  function nextChapter() {
    if (currentChapter < totalChapters - 1) loadChapter(currentChapter + 1);
  }
  
  // ── 设置面板 ──
  function toggleSettings(force) {
    var panel = document.getElementById('reader-settings-panel');
    if (force === undefined) {
      panel.classList.toggle('active');
    } else if (force) {
      panel.classList.add('active');
    } else {
      panel.classList.remove('active');
    }
  }
  
  function changeFontSize(delta) {
    settings.fontSize = Math.max(12, Math.min(32, settings.fontSize + delta));
    applySettings();
    saveSettings();
  }
  
  function changeLineHeight(delta) {
    settings.lineHeight = Math.max(1.2, Math.min(3.0, Math.round((settings.lineHeight + delta) * 10) / 10));
    applySettings();
    saveSettings();
  }
  
  function setTheme(theme) {
    settings.theme = theme;
    applySettings();
    saveSettings();
    // 更新按钮状态
    document.querySelectorAll('.reader-theme-btn').forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.theme === theme);
    });
  }
  
  function setFontFamily(font) {
    settings.fontFamily = font;
    applySettings();
    saveSettings();
    document.querySelectorAll('.reader-font-btn').forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.font === font);
    });
  }
  
  // ── 写作位置追踪（书架首页用）──
  var _curDir = null; // 当前打开项目的目录（懒加载）

  function ensureCurDir() {
    if (_curDir !== null) return Promise.resolve(_curDir);
    return api('/api/project/info')
      .then(function(r) { _curDir = (r && r.ok) ? (r.project_dir || '') : ''; return _curDir; })
      .catch(function() { _curDir = ''; return _curDir; });
  }

  function _loadWriteMap() {
    try { return JSON.parse(localStorage.getItem('shuzhai_last_chapters') || '{}'); } catch(e) { return {}; }
  }

  // 记住某书写到哪一章（loadChapterContentAPI 每次切章时调用）
  function rememberWriteChapter(index) {
    ensureCurDir().then(function(dir) {
      if (!dir) return;
      var m = _loadWriteMap();
      m[dir] = index;
      try { localStorage.setItem('shuzhai_last_chapters', JSON.stringify(m)); } catch(e) {}
    });
  }

  function getWriteChapter(dir) {
    var m = _loadWriteMap();
    var ch = m[dir];
    return (typeof ch === 'number' && ch >= 0) ? ch : 0;
  }

  // 继续写：打开项目并跳到上次写到的章节（同项目直接切章，异项目重载）
  function continueWriting(book) {
    var ch = getWriteChapter(book.path);
    closeBookshelf();
    ensureCurDir().then(function(dir) {
      if (dir && dir === book.path) {
        if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(ch);
      } else {
        // 需要切换项目：记下恢复点，重载后 initApp 会自动跳到该章节
        try { localStorage.setItem('shuzhai_resume', JSON.stringify({dir: book.path, chapter: ch})); } catch(e) {}
        api('/api/project/open', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({path: book.path})
        }).then(function(r) {
          if (r && r.ok) {
            setTimeout(function() { location.reload(); }, 300);
          } else {
            localStorage.removeItem('shuzhai_resume');
            if (typeof showToast === 'function') showToast('打开失败: ' + (r && r.error || '未知错误'), 'error', 3000);
          }
        }).catch(function(e) {
          localStorage.removeItem('shuzhai_resume');
          if (typeof showToast === 'function') showToast('打开失败: ' + e.message, 'error', 3000);
        });
      }
    });
  }

  // ── 书架 ──
  function openBookshelf() {
    close();
    var bsOverlay = document.getElementById('bookshelf-overlay');
    bsOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    loadBookshelf();
  }
  
  function closeBookshelf() {
    var bsOverlay = document.getElementById('bookshelf-overlay');
    bsOverlay.classList.remove('active');
    document.body.style.overflow = '';
  }
  
  function loadBookshelf(filter) {
    var listEl = document.getElementById('bookshelf-list');
    listEl.innerHTML = '<div class="reader-loading">加载书架...</div>';
    
    api('/api/reader/bookshelf')
      .then(function(r) {
        if (!r.ok || !r.books || r.books.length === 0) {
          listEl.innerHTML = '<div class="bookshelf-empty"><div class="bookshelf-empty-icon">📚</div><p>书架还是空的</p><p class="bookshelf-empty-hint">创建项目写点东西，或者打开已有项目来阅读</p></div>';
          return;
        }
        
        var books = r.books;
        if (filter === 'favorite') {
          books = books.filter(function(b) { return b.is_favorite; });
          if (books.length === 0) {
            listEl.innerHTML = '<div class="bookshelf-empty"><div class="bookshelf-empty-icon">⭐</div><p>没有收藏的作品</p><p class="bookshelf-empty-hint">点击作品右下角的星标来收藏</p></div>';
            return;
          }
        }
        
        listEl.textContent = '';
        books.forEach(function(book) {
          var card = document.createElement('div');
          card.className = 'book-card';
          
          var progressText = '';
          if (book.reading && book.reading.chapter !== undefined && book.chapter_count > 0) {
            var pct = Math.round((book.reading.chapter / book.chapter_count) * 100);
            progressText = '读到第' + (book.reading.chapter + 1) + '章 (' + pct + '%)';
          }

          // 写作位置：上次写到的章节
          var writeCh = getWriteChapter(book.path);
          var writeText = '写到第' + (writeCh + 1) + '章';

          card.innerHTML = 
            '<div class="book-cover">' +
              '<div class="book-cover-title">' + escapeHtml(book.title) + '</div>' +
              '<div class="book-cover-genre">' + escapeHtml(book.genre || '原创') + '</div>' +
            '</div>' +
            '<div class="book-info">' +
              '<div class="book-title">' + escapeHtml(book.title) + '</div>' +
              '<div class="book-meta">' +
                '<span>' + book.chapter_count + '章</span>' +
                '<span>' + (book.total_words > 10000 ? Math.round(book.total_words / 10000) + '万字' : book.total_words + '字') +
                ' · ' + writeText + '</span>' +
              '</div>' +
              (progressText ? '<div class="book-progress">' + progressText + '</div>' : '') +
              '<div class="book-actions">' +
                '<button class="book-write-btn">继续写</button>' +
                '<button class="book-read-btn">阅读</button>' +
                '<button class="book-fav-btn' + (book.is_favorite ? ' active' : '') + '" data-path="' + encodeURIComponent(book.path) + '">⭐</button>' +
                '<button class="book-del-btn" data-path="' + encodeURIComponent(book.path) + '" title="删除">🗑</button>' +
              '</div>' +
            '</div>';

          card.querySelector('.book-write-btn').addEventListener('click', function() {
            continueWriting(book);
          });

          card.querySelector('.book-read-btn').addEventListener('click', function() {
            closeBookshelf();
            var startChapter = (book.reading && book.reading.chapter) || 0;
            setTimeout(function() { open(book.path, startChapter); }, 100);
          });
          
          card.querySelector('.book-fav-btn').addEventListener('click', function() {
            toggleFavorite(book.path, this);
          });
          
          var delBtnEl = card.querySelector('.book-del-btn');
          if (delBtnEl) {
            delBtnEl.addEventListener('click', function(e) {
              e.stopPropagation();
              if (confirm('确定删除项目「' + book.title + '」？\n此操作不可恢复！')) {
                api('/api/project/delete', {
                  method: 'POST',
                  headers: {'Content-Type':'application/json'},
                  body: JSON.stringify({project_dir: book.path})
                }).then(function(r) {
                  if (r && r.ok) {
                    showToast('已删除: ' + book.title, 'success', 2000);
                    loadBookshelf();
                  } else {
                    showToast('删除失败: ' + (r && r.error || '未知错误'), 'error', 3000);
                  }
                }).catch(function(e) {
                  showToast('删除失败: ' + e.message, 'error', 3000);
                });
              }
            });
          }
          
          listEl.appendChild(card);
        });
      })
      .catch(function() {
        listEl.innerHTML = '<div class="reader-error">加载失败</div>';
      });
  }
  
  function toggleFavorite(projectPath, btn) {
    api('/api/reader/bookshelf/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project: projectPath })
    }).then(function(r) {
      if (r.ok) {
        btn.classList.toggle('active', r.in_bookshelf);
      }
    }).catch(function(){});
  }
  
  // ── 工具函数 ──
  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  
  // ── 事件绑定 ──
  function bindEvents() {
    document.getElementById('reader-close-btn').addEventListener('click', close);
    document.getElementById('reader-prev-btn').addEventListener('click', prevChapter);
    document.getElementById('reader-next-btn').addEventListener('click', nextChapter);
    document.getElementById('reader-toc-btn').addEventListener('click', function() { toggleChapterList(); });
    document.getElementById('reader-settings-btn').addEventListener('click', function() { toggleSettings(); });
    document.getElementById('reader-chapter-close').addEventListener('click', function() { toggleChapterList(false); });
    document.getElementById('reader-settings-close').addEventListener('click', function() { toggleSettings(false); });
    
    // topbar阅读按钮：直接打开书架
    var btnReader = document.getElementById('btn-reader');
    if (btnReader) {
      btnReader.addEventListener('click', function() {
        Reader.openBookshelf();
      });
    }
    
    // 设置控件
    document.getElementById('reader-fontsize-minus').addEventListener('click', function() { changeFontSize(-1); });
    document.getElementById('reader-fontsize-plus').addEventListener('click', function() { changeFontSize(1); });
    document.getElementById('reader-lineheight-minus').addEventListener('click', function() { changeLineHeight(-0.1); });
    document.getElementById('reader-lineheight-plus').addEventListener('click', function() { changeLineHeight(0.1); });
    
    document.querySelectorAll('.reader-theme-btn').forEach(function(btn) {
      btn.addEventListener('click', function() { setTheme(btn.dataset.theme); });
    });
    document.querySelectorAll('.reader-font-btn').forEach(function(btn) {
      btn.addEventListener('click', function() { setFontFamily(btn.dataset.font); });
    });
    
    // 书架
    document.getElementById('reader-bookshelf-btn').addEventListener('click', openBookshelf);
    document.getElementById('bookshelf-close-btn').addEventListener('click', closeBookshelf);
    // 书架顶栏：开新书（复用新建项目对话框）
    var btnShelfNew = document.getElementById('bookshelf-new-btn');
    if (btnShelfNew) {
      btnShelfNew.addEventListener('click', function() {
        closeBookshelf();
        var ov = document.getElementById('new-project-overlay');
        if (ov) {
          ov.classList.add('active');
          var inp = document.getElementById('new-project-title');
          if (inp) { inp.value = ''; inp.focus(); }
        }
      });
    }
    document.querySelectorAll('.bookshelf-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.bookshelf-tab').forEach(function(t) { t.classList.remove('active'); });
        tab.classList.add('active');
        loadBookshelf(tab.dataset.filter);
      });
    });
    
    // 点击遮罩关闭面板
    document.getElementById('reader-chapter-panel').addEventListener('click', function(e) {
      if (e.target === this) toggleChapterList(false);
    });
    document.getElementById('reader-settings-panel').addEventListener('click', function(e) {
      if (e.target === this) toggleSettings(false);
    });
    
    // 滚动时保存进度（防抖）
    var saveTimer = null;
    document.getElementById('reader-scroll').addEventListener('scroll', function() {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(saveProgress, 1000);
    });
    
    // 键盘快捷键
    document.addEventListener('keydown', function(e) {
      var overlay = document.getElementById('reader-overlay');
      if (!overlay.classList.contains('active')) return;
      if (e.key === 'ArrowLeft') prevChapter();
      else if (e.key === 'ArrowRight') nextChapter();
      else if (e.key === 'Escape') close();
    });
  }
  
  return {
    init: init,
    open: open,
    close: close,
    openBookshelf: openBookshelf,
    rememberWriteChapter: rememberWriteChapter,
    getCurrentProject: function() { return currentProject; }
  };
})();

// 启动阅读器
document.addEventListener('DOMContentLoaded', function() { Reader.init(); });
