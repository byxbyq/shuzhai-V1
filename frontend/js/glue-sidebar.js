(function() {
  'use strict';


window.renderVolumeNav = function(containerId, onItemClick) {
  var container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';

  if (!volumesData || volumesData.length === 0) {
    // 无卷数据，回退到扁平章节列表
    if (typeof chapters !== 'undefined' && chapters.length > 0) {
      // 章节超过80时启用虚拟滚动
      if (chapters.length > 80 && typeof VirtualList === 'function') {
        var vlData = chapters.map(function(ch, i) {
          var words = (containerId === 'vol-nav-timeline') ? (ch._has_content ? (ch._actual_words || 0) : 0) : (ch.word_count || ch.words || 0);
          return { title: ch.title || ('第' + (i + 1) + '章'), words: words, chIndex: i };
        });
        new VirtualList(container, {
          itemHeight: 36,
          items: vlData,
          selectedIdx: currentChapterIndex,
          className: 'ch-directory-item',
          renderFn: function(item, idx, isSelected) {
            return '<div class="ch-directory-item' + (isSelected ? ' active' : '') + '">' +
              '<span class="cd-num">' + (idx + 1) + '</span>' +
              '<span class="cd-title">' + escapeHtml(item.title) + '</span>' +
              (item.words ? '<span class="cd-wc">' + item.words + '字</span>' : '') +
              '</div>';
          },
          onSelect: function(item, idx) { onItemClick(item.chIndex); }
        });
      } else {
        // 章节少于80，直接渲染
        chapters.forEach(function(ch, i) {
          var item = document.createElement('div');
          item.className = 'ch-directory-item' + (i === currentChapterIndex ? ' active' : '');
          var words = (containerId === 'vol-nav-timeline') ? (ch._has_content ? (ch._actual_words || 0) : 0) : (ch.word_count || ch.words || 0);
          item.innerHTML = '<span class="cd-num">' + (i + 1) + '</span><span class="cd-title">' + escapeHtml(ch.title || ('第' + (i + 1) + '章')) + '</span>' + (words ? '<span class="cd-wc">' + words + '字</span>' : '') + '<button class="ch-del-btn" data-idx="' + i + '" title="删除本章" onclick="event.stopPropagation();deleteChapter(' + i + ')">&times;</button>';
          item.addEventListener('click', function() { onItemClick(i); });
          container.appendChild(item);
        });
      }
    }
    return;
  }

  // 有卷数据，渲染卷/章层级
  volumesData.forEach(function(vol) {
    var volItem = document.createElement('div');
    volItem.className = 'vol-item';

    var header = document.createElement('div');
    header.className = 'vol-header';
    // P3-18: 卷管理按钮（重命名/删除）
    var volActions = '';
    if (containerId === 'vol-nav-outline' || containerId === 'vol-nav-writing') {
      volActions = '<span class="vol-actions" style="margin-left:auto;display:flex;gap:2px;opacity:0.65;transition:opacity 0.2s">';
      volActions += '<button class="sra-btn vol-outline-edit text-sm" title="编辑卷纲要" >📋</button>';
      volActions += '<button class="sra-btn vol-rename text-sm" title="重命名卷" >✏️</button>';
      volActions += '<button class="sra-btn vol-delete text-sm" title="删除卷" 🗑</button>';
      volActions += '</span>';
    }
    header.innerHTML = '<span class="vol-arrow text-sm">▶</span><span class="vol-num">卷' + vol.index + '</span><span class="vol-title">' + vol.title + '</span><span class="vol-count">' + vol.chapter_count + '章</span>' + volActions;

    // P3-18: 卷操作事件
    if (containerId === 'vol-nav-outline' || containerId === 'vol-nav-writing') {
      header.addEventListener('mouseenter', function() { var a = header.querySelector('.vol-actions'); if (a) a.style.opacity = '1'; });
      header.addEventListener('mouseleave', function() { var a = header.querySelector('.vol-actions'); if (a) a.style.opacity = '0'; });
      var renameBtn = header.querySelector('.vol-rename');
      if (renameBtn) {
        renameBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          customPrompt('重命名卷', vol.title, function(newTitle) {
            if (newTitle && newTitle.trim()) {
              api('/api/project/volume/rename', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({vol_index: vol.index, title: newTitle.trim()})
              }).then(function(data) {
                if (data.ok) { loadVolumesData(); renderVolumeNav(containerId, onItemClick); showToast('卷已重命名'); }
                else { showToast('重命名失败'); }
              }).catch(function(e) { showToast('重命名失败: ' + e.message); });
            }
          });
        });
      }
      var deleteBtn = header.querySelector('.vol-delete');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          customConfirm('确定删除「' + vol.title + '」？卷内章节将移到前一卷。', function(ok) {
            if (!ok) return;
            api('/api/project/volume/delete', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({vol_index: vol.index})
            }).then(function(data) {
              if (data.ok) { loadVolumesData(); renderVolumeNav(containerId, onItemClick); showToast('卷已删除'); }
              else { showToast('删除失败：' + (data.error || '至少保留一卷')); }
            }).catch(function(e) { showToast('删除失败: ' + e.message); });
          });
        });
      }
      var outlineEditBtn = header.querySelector('.vol-outline-edit');
      if (outlineEditBtn) {
        outlineEditBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          openVolumeOutlineDialog(vol.index, vol.title);
        });
      }
    }

    var chContainer = document.createElement('div');
    chContainer.className = 'vol-chapters';

    // 找到当前卷是否包含当前章节，如果是则展开
    var containsCurrent = false;

    (vol.chapters || []).forEach(function(chIdx) {
      var idx = chIdx - 1; // 转为0-based
      if (idx >= 0 && idx < chapters.length) {
        var ch = chapters[idx];
        var item = document.createElement('div');
        item.className = 'ch-directory-item' + (idx === currentChapterIndex ? ' active' : '');
        var words = (containerId === 'vol-nav-timeline') ? (ch._has_content ? (ch._actual_words || 0) : 0) : (ch.word_count || ch.words || 0);
        var delBtn = (containerId === 'vol-nav-timeline') ? '' : '<button class="ch-del-btn" data-idx="' + idx + '" title="删除本章" onclick="event.stopPropagation();deleteChapter(' + idx + ')">&times;</button>';
        var compareBtn = (containerId === 'vol-nav-timeline') ? '<button class="ch-compare-btn" data-vol="' + (vol.index || 0) + '" data-ch="' + chIdx + '" title="AI对照本章" onclick="event.stopPropagation();Timeline.compareOne(' + (vol.index || 0) + ',' + chIdx + ')" style="font-size:10px;padding:1px 5px;border:1px solid var(--accent);border-radius:3px;background:transparent;color:var(--accent);cursor:pointer;margin-right:3px;white-space:nowrap">对照</button>' : '';
        item.innerHTML = '<span class="cd-num">' + chIdx + '</span><span class="cd-title">' + escapeHtml(ch.title || ('第' + chIdx + '章')) + '</span>' + (words ? '<span class="cd-wc">' + words + '字</span>' : '') + compareBtn + delBtn;
        item.addEventListener('click', function(e) {
          e.stopPropagation();
          onItemClick(idx);
        });
        chContainer.appendChild(item);
        if (idx === currentChapterIndex) containsCurrent = true;
      }
    });

    // 如果包含当前章节则展开
    if (containsCurrent) {
      chContainer.classList.add('open');
      header.querySelector('.vol-arrow').classList.add('open');
    }

    // 在步骤4（章节大纲）的卷导航中，添加"+ 新章节"按钮
    if (containerId === 'vol-nav-outline') {
      var addBtn = document.createElement('div');
      addBtn.className = 'ch-directory-item add-ch-btn';
      addBtn.style.cssText = 'border:1px dashed var(--border);color:var(--muted);font-size:12px;justify-content:center;cursor:pointer;opacity:0.7;transition:opacity 0.2s';
      addBtn.innerHTML = '+ 新章节';
      addBtn.addEventListener('mouseenter', function() { addBtn.style.opacity = '1'; addBtn.style.borderColor = 'var(--accent)'; addBtn.style.color = 'var(--accent)'; });
      addBtn.addEventListener('mouseleave', function() { addBtn.style.opacity = '0.7'; addBtn.style.borderColor = 'var(--border)'; addBtn.style.color = 'var(--muted)'; });
      addBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        if (typeof doAddChapter === 'function') {
          doAddChapter(vol.index);
        }
      });
      chContainer.appendChild(addBtn);
    }

    header.addEventListener('click', function() {
      var arrow = header.querySelector('.vol-arrow');
      arrow.classList.toggle('open');
      chContainer.classList.toggle('open');
    });

    volItem.appendChild(header);
    volItem.appendChild(chContainer);
    container.appendChild(volItem);
  });

  // P3-18: "+ 新卷"按钮
  if (containerId === 'vol-nav-outline' || containerId === 'vol-nav-writing') {
    var addVolBtn = document.createElement('div');
    addVolBtn.style.cssText = 'padding:6px 12px;border:1px dashed var(--border);color:var(--muted);font-size:12px;cursor:pointer;opacity:0.7;transition:opacity 0.2s;border-radius:4px;margin-top:4px;text-align:center';
    addVolBtn.innerHTML = '+ 新卷';
    addVolBtn.addEventListener('mouseenter', function() { addVolBtn.style.opacity = '1'; addVolBtn.style.borderColor = 'var(--accent)'; addVolBtn.style.color = 'var(--accent)'; });
    addVolBtn.addEventListener('mouseleave', function() { addVolBtn.style.opacity = '0.7'; addVolBtn.style.borderColor = 'var(--border)'; addVolBtn.style.color = 'var(--muted)'; });
    addVolBtn.addEventListener('click', function() {
      customPrompt('新建卷', '', function(title) {
        if (title && title.trim()) {
          api('/api/project/volume/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: title.trim(), outline: ''})
          }).then(function(data) {
            if (data.ok) { loadVolumesData(); renderVolumeNav(containerId, onItemClick); showToast('新卷已添加'); }
            else { showToast('添加失败'); }
          }).catch(function(e) { showToast('添加失败: ' + e.message); });
        }
      });
    });
    container.appendChild(addVolBtn);
  }
}

/* ===== Chapter Dropdown Selector ===== */
window.updateWritingToolbar = function() {
  var label = document.getElementById('wt-chapter-label');
  var wc = document.getElementById('wt-word-count');
  // P3-17: 章节状态标签
  var statusBtn = document.getElementById('writing-ch-status');
  if (label && typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
    label.textContent = '第' + (currentChapterIndex + 1) + '章 · ' + (chapters[currentChapterIndex].title || '');
  }
  if (wc) {
    var editorEl = document.getElementById('editor-content');
    var text = editorEl ? editorEl.innerText || '' : '';
    wc.textContent = text.replace(/\s/g, '').length + ' 字';
  }
  // P3-17: 更新状态按钮
  if (statusBtn && chapters && currentChapterIndex >= 0 && chapters[currentChapterIndex]) {
    var status = chapters[currentChapterIndex].status || 'draft';
    statusBtn.textContent = status === 'done' ? '✅ 完成' : '📝 草稿';
    statusBtn.dataset.status = status;
  }
}

// P3-17: 切换章节状态
window.toggleChapterStatus = function() {
  if (!chapters || currentChapterIndex < 0 || !chapters[currentChapterIndex]) return;
  var ch = chapters[currentChapterIndex];
  ch.status = (ch.status === 'done') ? 'draft' : 'done';
  updateWritingToolbar();
  // 保存到后端
  if (typeof api === 'function') {
    api('/api/chapter/outline', {
      method: 'POST', body: JSON.stringify({index: currentChapterIndex, outline: '', status: ch.status})
    }).catch(function(e) { console.warn('Save status failed:', e); });
  }
  showToast(ch.status === 'done' ? '已标记为完成' : '已标记为草稿');
}

// 章节下拉选择器渲染
window.renderChapterDropdown = function(selectId, currentIdx, onChange) {
  var sel = document.getElementById(selectId);
  if (!sel) return;
  sel.innerHTML = '';
  if (typeof chapters === 'undefined' || !chapters || chapters.length === 0) {
    sel.innerHTML = '<option value="">暂无章节</option>';
    return;
  }
  chapters.forEach(function(ch, i) {
    var opt = document.createElement('option');
    opt.value = i;
    opt.textContent = '第' + (i+1) + '章 ' + (ch.title || ('第' + (i+1) + '章'));
    if (i === currentIdx) opt.selected = true;
    sel.appendChild(opt);
  });
  sel._onChange = onChange;
}
window.onChapterDropdownChange = function(val) {
  var idx = parseInt(val);
  if (isNaN(idx)) return;
  var sel = document.getElementById('chapter-dropdown-outline');
  if (sel && sel._onChange) sel._onChange(idx);
}

window.renderChapterMiniList = async function() {
  // 渲染卷导航（替代旧的章节下拉选择器和目录列表）
  renderVolumeNav('vol-nav-writing', async function(idx) {
    syncChapterAcrossPanels(idx);
    if (typeof updateWritingToolbar === 'function') updateWritingToolbar();
  });
  // Update bottom label
  var curCh = (typeof chapters !== 'undefined' && chapters[currentChapterIndex]) ? chapters[currentChapterIndex] : null;
  var label = document.getElementById('writing-current-ch');
  if (label && curCh) label.textContent = curCh.title || ('第' + (currentChapterIndex + 1) + '章');
}

})();