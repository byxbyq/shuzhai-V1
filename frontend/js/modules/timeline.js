/* ===== 时间线模块（步骤7）===== */

window.Timeline = (function() {
  'use strict';

  var api = function(u, opts) {
    return window.api(u, opts);
  };

  var timelineData = null;
  var chaptersInfo = null;
  var _selectedChapter = null;

  function _getArrayIndex(chIdx) {
    var info = chaptersInfo && chaptersInfo[chIdx];
    return (info && typeof info.array_index === 'number') ? info.array_index : (parseInt(chIdx) - 1);
  }

  function load() {
    return new Promise(function(resolve) {
      var tree = document.getElementById('timeline-tree');
      var treeWide = document.getElementById('timeline-tree-wide');
      // 不移除早期返回：即使没有tree元素也要加载数据（selectChapter需要timelineData）

      if (tree) tree.innerHTML = '<div class="timeline-placeholder">加载中...</div>';
      if (treeWide) treeWide.innerHTML = '<div class="timeline-placeholder">加载中...</div>';

      api('/api/timeline').then(function(res) {
        console.log('[Timeline.load] /api/timeline res=', res);
        if (!res || !res.ok) {
          var errMsg = '加载失败：' + (res && res.message || '请确认已打开项目');
          if (tree) tree.innerHTML = '<div class="timeline-placeholder error">' + errMsg + '</div>';
          if (treeWide) treeWide.innerHTML = '<div class="timeline-placeholder error">' + errMsg + '</div>';
          if (window.showToast) showToast('时间线加载失败：' + errMsg, 'error');
          resolve({ok: false, error: errMsg});
          return;
        }
        timelineData = res.timeline;
        chaptersInfo = res.chapters || {};
        console.log('[Timeline.load] timelineData volumes keys=', Object.keys((timelineData || {}).volumes || {}));
        if (tree || treeWide) { render(); _clearEditor(); }
        // 加载完成后，如果有选中的章节，重新渲染详情
        if (_selectedChapter) {
          selectChapter(_selectedChapter.volume_index, _selectedChapter.chapter_index);
        }
        resolve({ok: true, data: res});
      }).catch(function(e) {
        console.error('[Timeline.load] /api/timeline error:', e);
        var errMsg = '网络错误：' + e.message;
        if (tree) tree.innerHTML = '<div class="timeline-placeholder error">' + errMsg + '</div>';
        if (treeWide) treeWide.innerHTML = '<div class="timeline-placeholder error">' + errMsg + '</div>';
        if (window.showToast) showToast('时间线加载失败：' + errMsg, 'error');
        resolve({ok: false, error: errMsg});
      });
    });
  }

  function render() {
    var tree = document.getElementById('timeline-tree');
    var treeWide = document.getElementById('timeline-tree-wide');
    if (!tree && !treeWide) return;

    var vols = timelineData.volumes || {};
    var volKeys = Object.keys(vols).sort(function(a, b) { return parseInt(a) - parseInt(b); });

    if (volKeys.length === 0) {
      if (tree) tree.innerHTML = '<div class="timeline-placeholder">暂无时间线数据。</div>';
      if (treeWide) treeWide.innerHTML = '<div class="timeline-placeholder">暂无时间线数据。</div>';
      return;
    }

    var html = '';
    for (var vi = 0; vi < volKeys.length; vi++) {
      var vk = volKeys[vi];
      var vol = vols[vk];
      var chKeys = Object.keys(vol.chapters || {}).sort(function(a, b) { return parseInt(a) - parseInt(b); });
      var hasCompare = false;
      var divCount = 0;
      for (var cj = 0; cj < chKeys.length; cj++) {
        var ch = vol.chapters[chKeys[cj]];
        if (ch && ch.divergences && ch.divergences.length > 0) {
          hasCompare = true;
          divCount += ch.divergences.length;
        }
      }

      html += '<div class="timeline-volume">';
      html += '<div class="timeline-volume-header" onclick="Timeline.toggleVolume(this)">';
      html += '<span class="timeline-caret">▶</span>';
      html += '<span class="timeline-volume-title">' + escHtml(vol.title || '第' + parseInt(vk) + '卷') + '</span>';
      html += '<span class="timeline-volume-count">(' + chKeys.length + '章)</span>';
      html += '</div>';
      html += '<div class="timeline-chapters" style="display:block">';

      for (var ci = 0; ci < chKeys.length; ci++) {
        var ck = chKeys[ci];
        var ch = vol.chapters[ck];
        var info = chaptersInfo && chaptersInfo[ck];
        var hasContent = info && info.has_content;
        var chDivs = ch && ch.divergences ? ch.divergences : [];
        var hasDivs = chDivs.length > 0;
        var hasCompared = ch && ch.last_compared;
        var badge = hasDivs ? '<span class="timeline-badge timeline-badge-warn">' + chDivs.length + '</span>' : (hasContent ? (hasCompared ? '<span class="timeline-badge timeline-badge-done">✓</span>' : '<span class="timeline-badge timeline-badge-pending">○</span>') : '<span class="timeline-badge timeline-badge-pending">○</span>');

        html += '<div class="timeline-chapter" onclick="Timeline.selectChapter(' + vk + ',' + ck + ')">';
        html += '<div class="timeline-chapter-header">';
        html += '<span class="timeline-chapter-num">第' + parseInt(ck) + '章</span>';
        html += '<span class="timeline-chapter-title">' + escHtml(ch && ch.title || '') + '</span>';
        html += badge;
        if (hasContent) {
          var compareBtnClass = hasCompared ? 'timeline-btn-compare timeline-btn-compare-done' : 'timeline-btn-compare';
          html += '<div class="timeline-chapter-actions"><button class="' + compareBtnClass + '" onclick="event.stopPropagation(); Timeline.compareOne(' + vk + ',' + ck + ')">' + (hasCompared ? '✓ 已对照' : '对照') + '</button></div>';
        }
        html += '</div>';
        html += '</div>';
      }
      html += '</div>';
      html += '</div>';
    }

    var compareBtn = document.getElementById('btn-timeline-compare-all');
    var compareBtnWide = document.getElementById('btn-timeline-compare-all-wide');
    if (compareBtn) compareBtn.style.display = hasCompare ? 'inline-block' : 'none';
    if (compareBtnWide) compareBtnWide.style.display = hasCompare ? 'inline-block' : 'none';

    if (tree) tree.innerHTML = html;
    if (treeWide) treeWide.innerHTML = html;
  }

  function selectChapter(volIdx, chIdx) {
    console.log('[Timeline.selectChapter] called volIdx=', volIdx, 'chIdx=', chIdx, 'currentWorkflowStep=', (typeof currentWorkflowStep !== 'undefined' ? currentWorkflowStep : 'undefined'), 'timelineData=', !!timelineData);
    if (typeof currentWorkflowStep !== 'undefined' && currentWorkflowStep !== 7) {
      console.warn('[Timeline.selectChapter] currentWorkflowStep is', currentWorkflowStep, ', expected 7; still rendering to avoid blank panel');
    }

    // 如果 timelineData 尚未加载，先加载再选择
    if (!timelineData) {
      console.log('[Timeline.selectChapter] timelineData empty, loading first');
      load();
      // 等待数据加载完成后重试
      setTimeout(function() { selectChapter(volIdx, chIdx); }, 500);
      return;
    }

    var detail = document.getElementById('timeline-detail');
    var detailWide = document.getElementById('timeline-detail-wide');
    var panelTitle = document.getElementById('timeline-panel-title');
    var panelTitleWide = document.getElementById('timeline-panel-title-wide');
    var panelSubtitle = document.getElementById('timeline-panel-subtitle');
    var panelSubtitleWide = document.getElementById('timeline-panel-subtitle-wide');
    
    if (!detail && !detailWide) {
      console.warn('[Timeline.selectChapter] neither timeline-detail nor timeline-detail-wide found');
      return;
    }

    var vols = timelineData.volumes || {};
    var vol = vols[volIdx];
    var ch = vol && vol.chapters && vol.chapters[chIdx];
    console.log('[Timeline.selectChapter] vol=', !!vol, 'ch=', !!ch, 'volumes keys=', Object.keys(vols));
    if (!ch) {
      var msg = '<div class="timeline-detail-placeholder">章节数据不存在（volIdx=' + volIdx + ', chIdx=' + chIdx + '）</div>';
      if (detail) detail.innerHTML = msg;
      if (detailWide) detailWide.innerHTML = msg;
      return;
    }

    _selectedChapter = { volume_index: volIdx, chapter_index: chIdx };

    var info = chaptersInfo && chaptersInfo[chIdx];
    var hasContent = info && info.has_content;
    var hasDivergences = (ch.divergences || []).length > 0;
    var divCount = hasDivergences ? (ch.divergences || []).length : 0;

    if (panelTitle) panelTitle.textContent = ch.title || '第' + parseInt(chIdx) + '章';
    if (panelTitleWide) panelTitleWide.textContent = ch.title || '第' + parseInt(chIdx) + '章';
    if (panelSubtitle) panelSubtitle.textContent = hasContent ? '有正文' : '无正文';
    if (panelSubtitleWide) panelSubtitleWide.textContent = hasContent ? '有正文' : '无正文';

    var html = '';

    if (divCount > 0) {
      html += '<div class="timeline-divergences-main">';
      html += '<div class="timeline-section-title">';
      html += '<span class="timeline-label">偏离 (' + divCount + '处)</span>';
      html += '<button class="timeline-btn-aifix-all" onclick="Timeline.fixAllDivs(' + volIdx + ',' + chIdx + ',this)">🤖 一键修复</button>';
      html += '<button class="timeline-btn-add-div" onclick="Timeline.addDiv(' + volIdx + ',' + chIdx + ')">+ 新增</button>';
      html += '</div>';
      html += '<div class="timeline-divergences">';
      for (var di = 0; di < ch.divergences.length; di++) {
        var d = ch.divergences[di];
        html += '<div class="timeline-divergence timeline-divergence-main" data-div="' + di + '">';
        html += '<div class="div-view-mode">';
        html += '<div class="div-header">';
        html += '<span class="div-type div-type-' + escHtml(d.type || '') + '">' + escHtml(d.type || '') + '</span>';
        html += '<span class="div-item-main">' + escHtml(d.item || '') + '</span>';
        html += '<div class="div-actions">';
        html += '<button class="div-action-btn div-action-locate" onclick="Timeline.jumpToParagraph(' + volIdx + ',' + chIdx + ',' + di + ')" title="定位到正文">📍</button>';
        html += '<button class="div-action-btn" onclick="Timeline.editDiv(' + volIdx + ',' + chIdx + ',' + di + ')" title="编辑">✏️</button>';
        html += '<button class="div-action-btn" onclick="Timeline.deleteDiv(' + volIdx + ',' + chIdx + ',' + di + ')" title="删除">🗑️</button>';
        html += '<button class="div-action-btn div-action-aifix" onclick="Timeline.aiFixDiv(' + volIdx + ',' + chIdx + ',' + di + ',this)" title="AI修复">🤖</button>';
        html += '</div>';
        html += '</div>';
        if (d.note) html += '<div class="div-note-main">' + escHtml(d.note) + '</div>';
        html += '<div class="div-footer">';
        html += '<select class="div-status" onchange="Timeline.updateDivStatus(' + volIdx + ',' + chIdx + ',' + di + ',this.value)">';
        html += '<option value="待处理"' + (d.status === '待处理' ? ' selected' : '') + '>待处理</option>';
        html += '<option value="已接受"' + (d.status === '已接受' ? ' selected' : '') + '>已接受</option>';
        html += '<option value="已修复"' + (d.status === '已修复' ? ' selected' : '') + '>已修复</option>';
        html += '</select>';
        html += '</div>';
        html += '</div>';
        html += '<div class="div-edit-mode" class="hidden">';
        html += '<div class="div-edit-row">';
        html += '<select class="div-edit-type">';
        var divTypes = ['修改', '推迟', '提前', '新增', '删除', '冲突', '重复', '战力', 'AI味', '逻辑', '人设', '连贯'];
        for (var ti = 0; ti < divTypes.length; ti++) {
          html += '<option value="' + divTypes[ti] + '"' + (d.type === divTypes[ti] ? ' selected' : '') + '>' + divTypes[ti] + '</option>';
        }
        html += '</select>';
        html += '<input type="text" class="div-edit-item" value="' + escAttr(d.item || '') + '" placeholder="具体内容...">';
        html += '</div>';
        html += '<div class="div-edit-row">';
        html += '<input type="text" class="div-edit-note" value="' + escAttr(d.note || '') + '" placeholder="说明（可选）...">';
        html += '</div>';
        html += '<div class="div-edit-row div-edit-actions">';
        html += '<button class="div-save-btn" onclick="Timeline.saveDivEdit(' + volIdx + ',' + chIdx + ',' + di + ',this)">保存</button>';
        html += '<button class="div-cancel-btn" onclick="Timeline.cancelDivEdit(' + volIdx + ',' + chIdx + ',' + di + ',this)">取消</button>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
      }
      html += '</div>';
      html += '</div>';
    }

    if (!hasDivergences && hasContent) {
      var hasCompared = ch && ch.last_compared;
      html += '<div class="timeline-compare-area">';
      if (hasCompared) {
        html += '<div class="timeline-compare-done-msg" style="text-align:center;padding:12px;color:#16a34a;font-size:14px">✓ 已对照，未发现偏离</div>';
        html += '<button class="timeline-btn-compare-large" onclick="Timeline.compareOne(' + volIdx + ',' + chIdx + ')" style="font-size:12px;padding:6px 16px;opacity:0.7">🔄 重新对照</button>';
      } else {
        html += '<button class="timeline-btn-compare-large" onclick="Timeline.compareOne(' + volIdx + ',' + chIdx + ')">⚡ AI对照</button>';
      }
      html += '<span class="timeline-compare-hint">自动分析计划与实际的差异</span>';
      html += '</div>';
    }

    html += '<div class="timeline-reference-section">';
    html += '<div class="timeline-ref-header" onclick="Timeline.toggleReference(this)">';
    html += '<span class="timeline-caret-small">▶</span>';
    html += '<span class="timeline-ref-title">参考内容（计划 vs 实际）</span>';
    html += '</div>';
    html += '<div class="timeline-ref-content" class="hidden">';

    var hasPlanned = ch.planned && ch.planned.trim();
    html += '<div class="timeline-row">';
    html += '<span class="timeline-label">计划：</span>';
    html += '<span class="timeline-text timeline-text-ref' + (hasPlanned ? '' : ' timeline-text-empty') + '">' + escHtml(hasPlanned ? ch.planned : '（未填写）') + '</span>';
    html += '</div>';

    var hasActual = ch.actual && ch.actual.trim();
    var actualValue = '';
    if (ch.events && ch.events.length > 0) {
        actualValue = ch.events.join('；');
    } else if (hasActual) {
        actualValue = ch.actual;
    }
    html += '<div class="timeline-row">';
    html += '<span class="timeline-label">实际：</span>';
    html += '<textarea class="timeline-actual-input timeline-actual-ref" data-vol="' + volIdx + '" data-ch="' + chIdx + '" onchange="Timeline.saveActual(' + volIdx + ',' + chIdx + ',this.value)" placeholder="（待蒸馏，可手动输入实际内容）">' + escHtml(actualValue) + '</textarea>';
    html += '</div>';

    if (ch.events && ch.events.length > 0) {
      html += '<div class="timeline-row"><span class="timeline-label">事件：</span></div>';
      html += '<div class="timeline-distill-events">';
      for (var ei = 0; ei < ch.events.length; ei++) {
        html += '<div class="distill-event">• ' + escHtml(ch.events[ei]) + '</div>';
      }
      html += '</div>';
    }

    var characters = ch.characters || [];
    if (characters.length > 0) {
      html += '<div class="timeline-row"><span class="timeline-label">角色：</span></div>';
      html += '<div class="timeline-distill-chars">';
      for (var ci2 = 0; ci2 < characters.length; ci2++) {
        var c = characters[ci2];
        var cname = c.name || c.character || '?';
        var cstate = c.state || c.location || '';
        if (!cstate && (c.mood || c.realm || c.items)) {
          var parts = [];
          if (c.location) parts.push('位置:' + c.location);
          if (c.mood) parts.push('心绪:' + c.mood);
          if (c.realm) parts.push('境界:' + c.realm);
          if (c.items && c.items.length) parts.push('持有:' + c.items.join(','));
          if (c.alive === false) parts.push('已死亡');
          cstate = parts.join(' | ');
        }
        html += '<div class="distill-char"><span class="distill-char-name">' + escHtml(cname) + '</span><span class="distill-char-state">' + escHtml(cstate) + '</span></div>';
      }
      html += '</div>';
    }

    var fs = ch.foreshadowing || {};
    var planted = fs.planted || [];
    var resolved = fs.resolved || [];
    if (planted.length > 0 || resolved.length > 0) {
      html += '<div class="timeline-row"><span class="timeline-label">伏笔：</span></div>';
      html += '<div class="timeline-distill-foreshadowing">';
      for (var pi = 0; pi < planted.length; pi++) {
        var p = planted[pi];
        var pcontent = typeof p === 'string' ? p : (p.content || '');
        var pchap = typeof p === 'string' ? '' : (p.expected_chapter || '');
        html += '<div class="distill-fs distill-fs-planted"><span class="fs-tag fs-tag-planted">种</span>' + escHtml(pcontent) + (pchap ? '<span class="fs-chap">→' + escHtml(pchap) + '</span>' : '') + '</div>';
      }
      for (var ri = 0; ri < resolved.length; ri++) {
        var r = resolved[ri];
        var rcontent = typeof r === 'string' ? r : (r.content || '');
        var rmethod = typeof r === 'string' ? '' : (r.method || r.resolved_by || '');
        html += '<div class="distill-fs distill-fs-resolved"><span class="fs-tag fs-tag-resolved">收</span>' + escHtml(rcontent) + (rmethod ? '<span class="fs-method">(' + escHtml(rmethod) + ')</span>' : '') + '</div>';
      }
      html += '</div>';
    }

    var newSettings = ch.new_settings || [];
    if (newSettings.length > 0) {
      html += '<div class="timeline-row"><span class="timeline-label">新设定：</span></div>';
      html += '<div class="timeline-distill-settings">';
      for (var si = 0; si < newSettings.length; si++) {
        html += '<div class="distill-setting">+ ' + escHtml(newSettings[si]) + '</div>';
      }
      html += '</div>';
    }

    var bridge = ch.bridge || {};
    if ((bridge.from_prev || bridge.to_next) && (bridge.from_prev || bridge.to_next).toString().trim()) {
      html += '<div class="timeline-row"><span class="timeline-label">衔接：</span></div>';
      html += '<div class="timeline-distill-bridge">';
      if (bridge.from_prev) html += '<div class="distill-bridge-from"><span class="bridge-tag">承上</span>' + escHtml(bridge.from_prev) + '</div>';
      if (bridge.to_next) html += '<div class="distill-bridge-to"><span class="bridge-tag">启下</span>' + escHtml(bridge.to_next) + '</div>';
      html += '</div>';
    }

    html += '<div class="timeline-row">';
    html += '<span class="timeline-label">注释：</span>';
    html += '<textarea class="timeline-annotation" data-vol="' + volIdx + '" data-ch="' + chIdx + '" onchange="Timeline.saveAnnotation(' + volIdx + ',' + chIdx + ',this.value)" placeholder="手工添加注释...">' + escHtml(ch.annotation || '') + '</textarea>';
    html += '</div>';

    html += '</div></div>';

    if (detail) detail.innerHTML = html;
    if (detailWide) detailWide.innerHTML = html;

    _renderEditorContent(volIdx, chIdx, ch);
  }

  function _clearEditor() {
  }

  function _renderEditorContent(volIdx, chIdx, ch) {
    var contentArea = document.getElementById('timeline-content-area');
    var contentAreaWide = document.getElementById('timeline-content-area-wide');
    var contentTitle = document.getElementById('timeline-content-title');
    var contentTitleWide = document.getElementById('timeline-content-title-wide');
    
    if (!contentArea && !contentAreaWide) return;

    if (contentTitle) contentTitle.textContent = '章节正文';
    if (contentTitleWide) contentTitleWide.textContent = '章节正文';

    var divergences = ch.divergences || [];

    api('/api/chapter/load?index=' + _getArrayIndex(chIdx)).then(function(res) {
      if (!res || !res.ok || !res.content) {
        var errHtml = '<div class="empty-state-lg-alt2">无法加载正文</div>';
        if (contentArea) contentArea.innerHTML = errHtml;
        if (contentAreaWide) contentAreaWide.innerHTML = errHtml;
        return;
      }

      var content = res.content;
      var lines = content.split('\n');

      // 检查是否全空
      var hasContent = false;
      for (var ci = 0; ci < lines.length; ci++) {
        if (lines[ci].trim()) { hasContent = true; break; }
      }
      if (!hasContent) {
        var emptyHtml = '<div class="empty-state-lg-alt2">该章节暂无正文内容</div>';
        if (contentArea) contentArea.innerHTML = emptyHtml;
        if (contentAreaWide) contentAreaWide.innerHTML = emptyHtml;
        return;
      }

      var html = '<div class="timeline-full-content">';

      // 用非空段落计数器作为ID索引，与后端 para_index 一致
      var nonEmptyIdx = 0;
      for (var pi = 0; pi < lines.length; pi++) {
        var para = lines[pi].trim();
        if (!para) continue; // 跳过空行

        var matchedDivs = [];
        for (var di = 0; di < divergences.length; di++) {
          var d = divergences[di];
          if (d.para_index === nonEmptyIdx) {
            matchedDivs.push(d);
          }
        }

        if (matchedDivs.length > 0) {
          var tags = '';
          for (var ti = 0; ti < matchedDivs.length; ti++) {
            tags += '<span class="div-type div-type-' + escHtml(matchedDivs[ti].type || '') + '">' + escHtml(matchedDivs[ti].type || '') + '</span>';
          }

          html += '<div class="problem-card" id="problem-card-' + volIdx + '-' + chIdx + '-' + nonEmptyIdx + '">';
          html += '<div class="problem-card-header">';
          html += tags;
          html += '<span class="problem-card-hint">段落 ' + (nonEmptyIdx + 1) + '</span>';
          html += '</div>';
          html += '<textarea class="problem-card-textarea" id="problem-textarea-' + volIdx + '-' + chIdx + '-' + nonEmptyIdx + '" data-pidx="' + nonEmptyIdx + '" placeholder="在此编辑正文...">' + escHtml(para) + '</textarea>';
          html += '<div class="problem-card-footer">';
          html += '<button class="problem-card-save-btn" onclick="Timeline.saveParagraph(' + volIdx + ',' + chIdx + ',' + nonEmptyIdx + ',this)">💾 保存</button>';
          html += '</div>';
          html += '</div>';
        } else {
          html += '<div class="timeline-normal-paragraph" id="normal-para-' + volIdx + '-' + chIdx + '-' + nonEmptyIdx + '">';
          html += '<span class="timeline-para-num">' + (nonEmptyIdx + 1) + '</span>';
          html += '<div class="timeline-para-text">' + escHtml(para) + '</div>';
          html += '</div>';
        }
        nonEmptyIdx++;
      }

      html += '</div>';
      if (contentArea) contentArea.innerHTML = html;
      if (contentAreaWide) contentAreaWide.innerHTML = html;

    }).catch(function(e) {
      var errHtml = '<div class="empty-state-lg-alt2">加载正文失败：' + e.message + '</div>';
      if (contentArea) contentArea.innerHTML = errHtml;
      if (contentAreaWide) contentAreaWide.innerHTML = errHtml;
    });
  }

  function saveParagraph(volIdx, chIdx, pidx, btn) {
    var textarea = document.getElementById('problem-textarea-' + volIdx + '-' + chIdx + '-' + pidx);
    if (!textarea) return;

    var newText = textarea.value;

    api('/api/chapter/load?index=' + _getArrayIndex(chIdx)).then(function(res) {
      if (!res || !res.ok || !res.content) {
        if (window.showToast) showToast('无法加载正文', 'error');
        return;
      }

      var content = res.content;
      var lines = content.split('\n');

      // 将过滤后的 para_index 映射回原始行索引
      var nonEmptyCount = 0;
      var targetLineIdx = -1;
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trim()) {
          if (nonEmptyCount === pidx) { targetLineIdx = i; break; }
          nonEmptyCount++;
        }
      }

      if (targetLineIdx >= 0) {
        lines[targetLineIdx] = newText;
        var newContent = lines.join('\n');

        api('/api/chapter/save', {
          method: 'POST',
          body: JSON.stringify({ index: _getArrayIndex(chIdx), content: newContent })
        }).then(function(res) {
          if (res && res.ok) {
            btn.textContent = '✓ 已保存';
            btn.style.backgroundColor = '#4caf50';
            setTimeout(function() {
              btn.textContent = '💾 保存';
              btn.style.backgroundColor = '';
            }, 2000);
            if (window.showToast) showToast('正文已保存', 'success');
          } else {
            if (window.showToast) showToast('保存失败：' + (res && res.message || ''), 'error');
          }
        }).catch(function(e) {
          if (window.showToast) showToast('保存失败：' + e.message, 'error');
        });
      } else {
        if (window.showToast) showToast('段落索引无效', 'error');
      }
    }).catch(function(e) {
      if (window.showToast) showToast('加载正文失败：' + e.message, 'error');
    });
  }

  function jumpToParagraph(volIdx, chIdx, divIdx) {
    var vols = timelineData.volumes || {};
    var vol = vols[volIdx];
    var ch = vol && vol.chapters && vol.chapters[chIdx];
    if (!ch) return;
    var d = ch.divergences && ch.divergences[divIdx];
    if (!d) return;

    // 策略1: 通过段落索引ID定位（最精确）
    var paraIdx = d.para_index;
    if (paraIdx !== undefined && paraIdx !== null) {
      var problemCard = document.getElementById('problem-card-' + volIdx + '-' + chIdx + '-' + paraIdx);
      var normalPara = document.getElementById('normal-para-' + volIdx + '-' + chIdx + '-' + paraIdx);
      var el = problemCard || normalPara;
      if (el) {
        _scrollToElement(el);
        if (window.showToast) showToast('已定位到段落 ' + (paraIdx + 1), 'success');
        return;
      }
    }

    // 策略2: 通过段落编号定位（para_index可能因内容重生成而偏移）
    if (paraIdx !== undefined && paraIdx !== null) {
      var allParas = document.querySelectorAll('.timeline-normal-paragraph, .problem-card');
      for (var i = 0; i < allParas.length; i++) {
        var numEl = allParas[i].querySelector('.timeline-para-num, .problem-card-hint');
        if (numEl) {
          var num = parseInt(numEl.textContent.replace(/[^0-9]/g, ''));
          if (num === paraIdx + 1) {
            _scrollToElement(allParas[i]);
            if (window.showToast) showToast('已定位到段落 ' + (paraIdx + 1), 'success');
            return;
          }
        }
      }
    }

    // 策略3: 通过关键词重新匹配段落（para_index 失效时使用）
    var searchText = d.item || d.note || '';
    if (searchText) {
      var allParagraphs = document.querySelectorAll('.timeline-normal-paragraph, .problem-card');
      // 提取中文关键词（2-6字）
      var keywords = [];
      var text = searchText.slice(0, 120);
      for (var i = 0; i < text.length - 1; i++) {
        for (var len = 2; len <= 6; len++) {
          if (i + len <= text.length) {
            var word = text.slice(i, i + len);
            if (/^[\u4e00-\u9fa5]+$/.test(word)) {
              keywords.push(word);
            }
          }
        }
      }
      // 去重并按长度降序（优先匹配长词）
      var seen = {};
      var uniqueKeywords = [];
      for (var i = 0; i < keywords.length; i++) {
        if (!seen[keywords[i]]) {
          seen[keywords[i]] = true;
          uniqueKeywords.push(keywords[i]);
        }
      }
      uniqueKeywords.sort(function(a, b) { return b.length - a.length; });

      var bestEl = null;
      var bestScore = 0;
      for (var i = 0; i < allParagraphs.length; i++) {
        var el = allParagraphs[i];
        var textContent = el.textContent || '';
        var score = 0;
        for (var k = 0; k < uniqueKeywords.length; k++) {
          if (textContent.indexOf(uniqueKeywords[k]) >= 0) {
            score += uniqueKeywords[k].length;  // 长词权重更高
          }
        }
        if (score > bestScore) {
          bestScore = score;
          bestEl = el;
        }
      }

      if (bestEl && bestScore >= 4) {
        _scrollToElement(bestEl);
        if (window.showToast) showToast('已定位到相关段落', 'success');
        return;
      }

      // 退化：直接子串匹配前10个字符
      var snippet = searchText.replace(/\s/g, '').slice(0, 10);
      if (snippet.length >= 4) {
        for (var i = 0; i < allParagraphs.length; i++) {
          var el = allParagraphs[i];
          var textContent = el.textContent || '';
          if (textContent.indexOf(snippet) >= 0) {
            _scrollToElement(el);
            if (window.showToast) showToast('已定位到相关段落', 'success');
            return;
          }
        }
      }
    }

    // 策略4: 如果以上都失败，尝试滚动到右侧面板顶部并提示
    var contentAreaWide = document.getElementById('timeline-content-area-wide');
    if (contentAreaWide) {
      contentAreaWide.scrollTop = 0;
    }
    if (window.showToast) showToast('未在正文中找到对应内容，请手动查找', 'info');
  }

  function _scrollToElement(el) {
    // 高亮元素
    el.classList.add('timeline-highlight');
    setTimeout(function() { el.classList.remove('timeline-highlight'); }, 3000);
    // 固定使用右侧正文滚动容器
    var scrollContainer = document.querySelector('.timeline-content-scroll');
    if (!scrollContainer) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    // 用 getBoundingClientRect 计算元素相对于滚动容器的精确位置
    var containerRect = scrollContainer.getBoundingClientRect();
    var elRect = el.getBoundingClientRect();
    var relativeTop = elRect.top - containerRect.top + scrollContainer.scrollTop;
    var containerHeight = scrollContainer.clientHeight;
    var targetTop = relativeTop - (containerHeight / 2) + (elRect.height / 2);
    scrollContainer.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
  }

  function compareOne(volIdx, chIdx, callback) {
    console.log('[Timeline.compareOne] called volIdx=', volIdx, 'chIdx=', chIdx);
    var btn = event ? event.target : null;
    if (btn) {
      btn.disabled = true;
      var originalText = btn.textContent;
      btn.textContent = '⏳ 对照中...';
      btn.style.opacity = '0.7';
    }

    // 显示加载提示
    if (window.showToast) showToast('AI正在分析计划与实际的差异，请稍候...', 'info');

    return api('/api/timeline/' + volIdx + '/' + chIdx + '/compare', {
      method: 'POST',
      body: JSON.stringify({})
    }).then(function(res) {
      console.log('[Timeline.compareOne] /api/timeline/' + volIdx + '/' + chIdx + '/compare res=', res);
      if (!res || !res.ok) {
        if (window.showToast) showToast('对照失败：' + (res && res.message || ''), 'error');
        if (btn) {
          btn.disabled = false;
          btn.textContent = originalText || '对照';
          btn.style.opacity = '1';
        }
        if (typeof callback === 'function') callback(null);
        return;
      }
      var divCount = res.divergences ? res.divergences.length : 0;
      if (window.showToast) showToast('✓ 对照完成，发现 ' + divCount + ' 处问题', 'success');
      // 先恢复按钮状态
      if (btn) {
        btn.disabled = false;
        btn.textContent = '✓ 已对照';
        btn.style.opacity = '1';
        btn.classList.add('timeline-btn-compare-done');
      }
      // 先设置选中章节，load完成后会自动调用selectChapter刷新主面板
      _selectedChapter = { volume_index: volIdx, chapter_index: chIdx };
      load();
      if (typeof callback === 'function') callback(res);
    }).catch(function(e) {
      console.error('[Timeline.compareOne] error:', e);
      if (window.showToast) showToast('对照失败：' + e.message, 'error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = originalText || '对照';
        btn.style.opacity = '1';
      }
      if (typeof callback === 'function') callback(null);
    });
  }

  function compareAll() {
    var btn = event ? event.target : null;
    if (btn) {
      btn.disabled = true;
      btn.textContent = '对照中...';
    }

    api('/api/timeline/compare-all', {
      method: 'POST',
      body: JSON.stringify({})
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('全部对照失败：' + (res && res.message || ''), 'error');
        if (btn) {
          btn.disabled = false;
          btn.textContent = '全部对照';
        }
        return;
      }
      if (window.showToast) showToast('全部对照完成', 'success');
      // 先恢复按钮状态，再异步刷新列表和详情面板
      if (btn) {
        btn.disabled = false;
        btn.textContent = '全部对照';
        btn.style.opacity = '1';
      }
      load();
    }).catch(function(e) {
      if (window.showToast) showToast('全部对照失败：' + e.message, 'error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '全部对照';
        btn.style.opacity = '1';
      }
    });
  }

  function finalizeChapter() {
    if (!_selectedChapter) {
      if (window.showToast) showToast('请先选择章节', 'error');
      return;
    }
    if (!confirm('确定要将当前章节定稿吗？定稿后将进入下一章。')) return;
    
    var volIdx = _selectedChapter.volume_index;
    var chIdx = _selectedChapter.chapter_index;
    
    api('/api/timeline/' + volIdx + '/' + chIdx + '/finalize', {
      method: 'POST',
      body: JSON.stringify({})
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('定稿失败：' + (res && res.message || ''), 'error');
        return;
      }
      if (window.showToast) showToast('定稿成功！', 'success');
      load();
    }).catch(function(e) {
      if (window.showToast) showToast('定稿失败：' + e.message, 'error');
    });
  }

  function saveActual(volIdx, chIdx, value) {
    api('/api/timeline/' + volIdx + '/' + chIdx + '/actual', {
      method: 'PUT',
      body: JSON.stringify({ actual: value })
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('保存失败：' + (res && res.message || ''), 'error');
      }
    }).catch(function(e) {
      if (window.showToast) showToast('保存失败：' + e.message, 'error');
    });
  }

  function saveAnnotation(volIdx, chIdx, value) {
    api('/api/timeline/' + volIdx + '/' + chIdx + '/annotation', {
      method: 'PUT',
      body: JSON.stringify({ annotation: value })
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('保存失败：' + (res && res.message || ''), 'error');
      }
    }).catch(function(e) {
      if (window.showToast) showToast('保存失败：' + e.message, 'error');
    });
  }

  function updateDivStatus(volIdx, chIdx, divIdx, status) {
    api('/api/timeline/' + volIdx + '/' + chIdx + '/divergence', {
      method: 'PUT',
      body: JSON.stringify({ divergence_index: divIdx, status: status })
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('更新失败：' + (res && res.message || ''), 'error');
      }
    }).catch(function(e) {
      if (window.showToast) showToast('更新失败：' + e.message, 'error');
    });
  }

  function editDiv(volIdx, chIdx, divIdx) {
    var divEl = document.querySelector('.timeline-divergence[data-div="' + divIdx + '"]');
    if (!divEl) return;
    divEl.querySelector('.div-view-mode').style.display = 'none';
    divEl.querySelector('.div-edit-mode').style.display = 'block';
  }

  function saveDivEdit(volIdx, chIdx, divIdx, btn) {
    var divEl = document.querySelector('.timeline-divergence[data-div="' + divIdx + '"]');
    if (!divEl) return;

    var type = divEl.querySelector('.div-edit-type').value;
    var item = divEl.querySelector('.div-edit-item').value;
    var note = divEl.querySelector('.div-edit-note').value;

    api('/api/timeline/' + volIdx + '/' + chIdx + '/divergence', {
      method: 'PUT',
      body: JSON.stringify({ divergence_index: divIdx, type: type, item: item, note: note })
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('保存失败：' + (res && res.message || ''), 'error');
        return;
      }
      cancelDivEdit(volIdx, chIdx, divIdx);
      // 不重新加载整个章节，只更新当前 divergence 的显示
      var divEl = document.querySelector('.timeline-divergence[data-div="' + divIdx + '"]');
      if (divEl) {
        var viewMode = divEl.querySelector('.div-view-mode');
        if (viewMode) {
          // 更新显示内容
          var typeSpan = viewMode.querySelector('.div-type-display');
          if (typeSpan) typeSpan.textContent = type;
          var itemSpan = viewMode.querySelector('.div-item-display');
          if (itemSpan) itemSpan.textContent = item;
          var noteSpan = viewMode.querySelector('.div-note-display');
          if (noteSpan) noteSpan.textContent = note;
        }
      }
      if (window.showToast) showToast('保存成功', 'success');
    }).catch(function(e) {
      if (window.showToast) showToast('保存失败：' + e.message, 'error');
    });
  }

  function cancelDivEdit(volIdx, chIdx, divIdx) {
    var divEl = document.querySelector('.timeline-divergence[data-div="' + divIdx + '"]');
    if (!divEl) return;
    divEl.querySelector('.div-view-mode').style.display = 'block';
    divEl.querySelector('.div-edit-mode').style.display = 'none';
  }

  function aiFixDiv(volIdx, chIdx, divIdx, btn) {
    var vols = timelineData.volumes || {};
    var vol = vols[volIdx];
    var ch = vol && vol.chapters && vol.chapters[chIdx];
    if (!ch) return;
    var d = ch.divergences && ch.divergences[divIdx];
    if (!d) return;

    var btnEl = btn || event.target;
    var origText = btnEl.textContent;
    btnEl.textContent = '⏳';
    btnEl.disabled = true;

    api('/api/timeline/' + volIdx + '/' + chIdx + '/divergence/' + divIdx + '/fix', {
      method: 'POST',
      body: JSON.stringify({})
    }).then(function(res) {
      btnEl.textContent = origText;
      btnEl.disabled = false;
      if (!res || !res.ok) {
        if (window.showToast) showToast(res && res.detail || 'AI修复失败', 'error');
        return;
      }
      showAiFixPreview(volIdx, chIdx, divIdx, res.original, res.fixed, res.para_index, d.type, d.item, d.note);
    }).catch(function(err) {
      btnEl.textContent = origText;
      btnEl.disabled = false;
      if (window.showToast) showToast('AI修复请求失败: ' + err.message, 'error');
    });
  }

  function showAiFixPreview(volIdx, chIdx, divIdx, original, fixed, para_index, divType, divItem, divNote) {
    var overlay = document.createElement('div');
    overlay.className = 'ai-fix-overlay';
    var origEsc = original.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var fixedEsc = fixed.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var q = String.fromCharCode(39);
    var html = '<div class="ai-fix-dialog">';
    html += '<div class="ai-fix-header"><span>🤖 AI修复预览</span>';
    html += '<button class="ai-fix-close" onclick="this.parentElement.parentElement.remove()">✕</button></div>';
    html += '<div class="ai-fix-body">';
    if (divType || divItem) {
      html += '<div class="ai-fix-issue">';
      if (divType) html += '<span class="ai-fix-issue-type">' + divType + '</span>';
      if (divItem) html += '<span class="ai-fix-issue-item">' + divItem.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>';
      if (divNote) html += '<div class="ai-fix-issue-note">' + divNote.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
      html += '</div>';
    }
    html += '<div class="ai-fix-section"><div class="ai-fix-label">原文：</div>';
    html += '<div class="ai-fix-text ai-fix-original">' + origEsc + '</div></div>';
    html += '<div class="ai-fix-arrow">↓</div>';
    html += '<div class="ai-fix-section"><div class="ai-fix-label">AI修正：</div>';
    html += '<textarea class="ai-fix-text ai-fix-edited">' + fixedEsc + '</textarea></div>';
    html += '</div>';
    html += '<div class="ai-fix-footer">';
    html += '<button class="ai-fix-btn ai-fix-cancel" onclick="this.parentElement.parentElement.parentElement.remove()">取消</button>';
    html += '<button class="ai-fix-btn ai-fix-apply" onclick="Timeline.applyAiFix(' + volIdx + ',' + chIdx + ',' + divIdx + ',' + para_index + ',this.parentElement.parentElement.querySelector(' + q + '.ai-fix-edited' + q + ').value)">应用修改</button>';
    html += '</div></div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
  }

  function applyAiFix(volIdx, chIdx, divIdx, para_index, newText) {
    // 先关闭对话框
    var overlay = document.querySelector('.ai-fix-overlay');
    if (overlay) overlay.remove();

    api('/api/chapter/load?index=' + _getArrayIndex(chIdx)).then(function(res) {
      if (!res || !res.ok || !res.content) {
        if (window.showToast) showToast('无法加载正文', 'error');
        return;
      }
      var content = res.content;
      var lines = content.split('\n');
      // 将过滤后的 para_index 映射回原始行索引
      var nonEmptyCount = 0;
      var targetLineIdx = -1;
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trim()) {
          if (nonEmptyCount === para_index) { targetLineIdx = i; break; }
          nonEmptyCount++;
        }
      }
      if (targetLineIdx >= 0) {
        lines[targetLineIdx] = newText;
        var newContent = lines.join('\n');
        api('/api/chapter/save', {
          method: 'POST',
          body: JSON.stringify({ index: _getArrayIndex(chIdx), content: newContent })
        }).then(function(saveRes) {
          if (saveRes && saveRes.ok) {
            if (window.showToast) showToast('✓ AI修复已应用，正在重新对照…', 'success');
            // 单条修复后也重新 AI 对照，而不是简单刷新
            if (typeof Timeline.compareOne === 'function') {
              Timeline.compareOne(volIdx, chIdx);
            } else if (typeof Timeline.load === 'function') {
              Timeline.load();
            }
          } else {
            if (window.showToast) showToast('保存失败', 'error');
          }
        }).catch(function(err) {
          if (window.showToast) showToast('保存出错: ' + err.message, 'error');
        });
      }
    }).catch(function(err) {
      if (window.showToast) showToast('加载正文出错: ' + err.message, 'error');
    });
  }

  function fixAllDivs(volIdx, chIdx, btn) {
    var vols = timelineData.volumes || {};
    var vol = vols[volIdx];
    var ch = vol && vol.chapters && vol.chapters[chIdx];
    if (!ch || !ch.divergences || ch.divergences.length === 0) {
      if (window.showToast) showToast('没有偏离项需要修复', 'info');
      return;
    }

    var btnEl = btn || (event && event.target);
    var origText = btnEl ? btnEl.textContent : '';
    if (btnEl) {
      btnEl.textContent = '⏳ 修复中...';
      btnEl.disabled = true;
    }
    if (window.showToast) showToast('AI正在综合修复' + ch.divergences.length + '处偏离，请稍候...', 'info');

    api('/api/timeline/' + volIdx + '/' + chIdx + '/fix-all', {
      method: 'POST',
      body: JSON.stringify({}),
      timeout: 180000,  // AI综合修复整个章节可能需要较长时间
      retries: 0        // 不重试：避免长时间无反馈且AI生成不适合盲重试
    }).then(function(res) {
      if (btnEl) {
        btnEl.textContent = origText || '🤖 一键修复';
        btnEl.disabled = false;
      }
      if (!res || !res.ok) {
        var errMsg = (res && (res.detail || res.message || res.error)) || 'AI综合修复失败';
        console.error('[Timeline.fixAllDivs] fix-all failed:', res);
        if (window.showToast) showToast('一键修复失败：' + errMsg, 'error');
        return;
      }
      // 检查 AI 是否返回了空内容
      var fixedTrim = (res.fixed || '').replace(/\s+/g, '');
      var origTrim = (res.original || '').replace(/\s+/g, '');
      if (!fixedTrim) {
        console.warn('[Timeline.fixAllDivs] AI 返回的修正内容为空');
        if (window.showToast) showToast('AI 未能生成修正内容，请尝试逐条编辑或重新对照', 'warning');
        return;
      }
      // 相似度过高时给出警告，但仍显示预览让用户自行判断
      if (res.high_similarity) {
        var simInfo = res.similarity ? '（相似度 ' + (res.similarity * 100).toFixed(1) + '%）' : '';
        console.warn('[Timeline.fixAllDivs] AI 修改幅度较小' + simInfo);
        if (window.showToast) showToast('AI 修改幅度较小' + simInfo + '，请仔细核对后再应用', 'warning');
      }
      showFixAllPreview(volIdx, chIdx, res.original, res.fixed, res.divergence_count, res.high_similarity, res.similarity);
    }).catch(function(err) {
      if (btnEl) {
        btnEl.textContent = origText || '🤖 一键修复';
        btnEl.disabled = false;
      }
      console.error('[Timeline.fixAllDivs] fix-all request error:', err);
      if (window.showToast) showToast('一键修复请求失败: ' + (err.message || err), 'error');
    });
  }

  function showFixAllPreview(volIdx, chIdx, original, fixed, divCount, highSimilarity, similarity) {
    var overlay = document.createElement('div');
    overlay.className = 'ai-fix-overlay';
    overlay.id = 'ai-fix-overlay-active';

    var origEsc = original.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var fixedEsc = fixed.replace(/</g, '&lt;').replace(/>/g, '&gt;');

    var textareaId = 'ai-fix-fulltext-' + volIdx + '-' + chIdx;

    var html = '<div class="ai-fix-dialog ai-fix-dialog-wide">';
    html += '<div class="ai-fix-header"><span>🤖 AI综合修复预览（' + divCount + '处偏离）</span>';
    html += '<button class="ai-fix-close" onclick="this.parentElement.parentElement.remove()">✕</button></div>';
    if (highSimilarity) {
      var simText = similarity ? '（相似度 ' + (similarity * 100).toFixed(1) + '%）' : '';
      html += '<div class="ai-fix-warning-banner">⚠️ AI 修改幅度较小' + simText + '，请仔细核对修正后的内容，确认无误后再点击「应用全部修改」</div>';
    }
    html += '<div class="ai-fix-body">';

    // 偏离项列表（紧凑显示）
    var vols = timelineData.volumes || {};
    var vol = vols[volIdx];
    var ch = vol && vol.chapters && vol.chapters[chIdx];
    if (ch && ch.divergences) {
      html += '<div class="ai-fix-issues-list">';
      for (var i = 0; i < ch.divergences.length; i++) {
        var d = ch.divergences[i];
        html += '<div class="ai-fix-issue-row">';
        html += '<span class="div-type div-type-' + escHtml(d.type || '') + '">' + escHtml(d.type || '') + '</span>';
        html += '<span class="ai-fix-issue-item">' + escHtml(d.item || '') + '</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    html += '<div class="ai-fix-section"><div class="ai-fix-label">原文（只读）：</div>';
    html += '<div class="ai-fix-text ai-fix-original ai-fix-fulltext">' + origEsc + '</div></div>';
    html += '<div class="ai-fix-arrow">↓ AI综合修正</div>';
    html += '<div class="ai-fix-section"><div class="ai-fix-label">修正后（可编辑）：</div>';
    html += '<textarea id="' + textareaId + '" class="ai-fix-text ai-fix-edited ai-fix-fulltext-edit">' + fixedEsc + '</textarea></div>';
    html += '</div>';
    html += '<div class="ai-fix-footer">';
    html += '<button class="ai-fix-btn ai-fix-cancel" onclick="this.parentElement.parentElement.parentElement.remove()">取消</button>';
    html += '<button class="ai-fix-btn ai-fix-apply" onclick="Timeline.applyFixAll(' + volIdx + ',' + chIdx + ',\'' + textareaId + '\',this)">应用全部修改</button>';
    html += '</div></div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
  }

  function applyFixAll(volIdx, chIdx, textareaId, btn) {
    // 通过 id 获取 textarea 值，避免 DOM 遍历问题
    var textarea = document.getElementById(textareaId);
    var newText = textarea ? textarea.value : '';
    if (!newText || !newText.trim()) {
      if (window.showToast) showToast('修正内容为空，无法保存', 'error');
      return;
    }

    // 按钮显示保存中状态
    var btnEl = btn || (event && event.target);
    var origText = btnEl ? btnEl.textContent : '';
    if (btnEl) {
      btnEl.textContent = '⏳ 保存中...';
      btnEl.disabled = true;
    }

    var arrIdx = _getArrayIndex(chIdx);
    console.log('[Timeline.applyFixAll] volIdx=' + volIdx + ' chIdx=' + chIdx + ' arrIdx=' + arrIdx + ' contentLen=' + newText.length);

    api('/api/chapter/save', {
      method: 'POST',
      body: JSON.stringify({ index: arrIdx, content: newText }),
      timeout: 120000,  // 保存正文时后端还会做状态提取+向量注入，给足时间
      retries: 0        // 保存请求不重试：避免重复向量注入和长时间无反馈卡死
    }).then(function(res) {
      console.log('[Timeline.applyFixAll] /api/chapter/save response:', res);
      if (!res || !res.ok) {
        if (btnEl) { btnEl.textContent = origText || '应用全部修改'; btnEl.disabled = false; }
        var errMsg = (res && (res.message || res.detail || res.error)) || '未知错误';
        if (window.showToast) showToast('保存失败：' + errMsg, 'error');
        return;
      }

      // 正文保存成功，更新偏离项状态
      var vols = timelineData.volumes || {};
      var vol = vols[volIdx];
      var ch = vol && vol.chapters && vol.chapters[chIdx];
      var divergences = ch && ch.divergences ? ch.divergences : [];
      var fixedDivergences = [];
      for (var i = 0; i < divergences.length; i++) {
        var d = JSON.parse(JSON.stringify(divergences[i]));
        d.status = '已修复';
        fixedDivergences.push(d);
      }

      var actualValue = ch && ch.actual ? ch.actual : '';

      api('/api/timeline/' + volIdx + '/' + chIdx + '/actual', {
        method: 'PUT',
        body: JSON.stringify({ actual: actualValue, divergences: fixedDivergences }),
        timeout: 30000,
        retries: 0
      }).then(function(statusRes) {
        console.log('[Timeline.applyFixAll] update divergences response:', statusRes);
        // 关闭对话框
        var overlay = document.getElementById('ai-fix-overlay-active');
        if (overlay) overlay.remove();
        if (statusRes && statusRes.ok) {
          if (window.showToast) showToast('✓ 综合修复已应用，正在重新对照…', 'success');
        } else {
          if (window.showToast) showToast('正文已保存，但偏离项状态更新失败', 'warning');
        }
        // 重新运行 AI 对照，而不是简单刷新，这样偏离项会真实更新
        if (typeof Timeline.compareOne === 'function') {
          Timeline.compareOne(volIdx, chIdx, function(compareRes) {
            if (compareRes && compareRes.divergences) {
              var newCount = compareRes.divergences.length;
              if (newCount === 0) {
                if (window.showToast) showToast('✓ 综合修复完成，重新对照后无新问题', 'success');
              } else {
                if (window.showToast) showToast('✓ 综合修复已应用，重新对照后发现 ' + newCount + ' 处新问题', 'warning');
              }
            }
          });
        } else if (typeof Timeline.load === 'function') {
          Timeline.load();
        }
      }).catch(function(err) {
        console.error('[Timeline.applyFixAll] update divergences status error:', err);
        var overlay = document.getElementById('ai-fix-overlay-active');
        if (overlay) overlay.remove();
        if (btnEl) { btnEl.textContent = origText || '应用全部修改'; btnEl.disabled = false; }
        if (window.showToast) showToast('正文已保存，但偏离项状态更新失败: ' + err.message, 'warning');
        if (typeof Timeline.load === 'function') Timeline.load();
      });
    }).catch(function(err) {
      console.error('[Timeline.applyFixAll] save chapter error:', err);
      if (btnEl) { btnEl.textContent = origText || '应用全部修改'; btnEl.disabled = false; }
      if (window.showToast) showToast('保存出错: ' + (err.message || err), 'error');
    });
  }

  function deleteDiv(volIdx, chIdx, divIdx) {
    if (!confirm('确定删除这条偏离吗？')) return;

    api('/api/timeline/' + volIdx + '/' + chIdx + '/divergence/' + divIdx, {
      method: 'DELETE'
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('删除失败：' + (res && res.message || ''), 'error');
        return;
      }
      selectChapter(volIdx, chIdx);
      if (window.showToast) showToast('删除成功', 'success');
    }).catch(function(e) {
      if (window.showToast) showToast('删除失败：' + e.message, 'error');
    });
  }

  function addDiv(volIdx, chIdx) {
    api('/api/timeline/' + volIdx + '/' + chIdx + '/divergence', {
      method: 'POST',
      body: JSON.stringify({ type: '修改', item: '', note: '', status: '待处理' })
    }).then(function(res) {
      if (!res || !res.ok) {
        if (window.showToast) showToast('添加失败：' + (res && res.message || ''), 'error');
        return;
      }
      selectChapter(volIdx, chIdx);
      if (window.showToast) showToast('添加成功', 'success');
    }).catch(function(e) {
      if (window.showToast) showToast('添加失败：' + e.message, 'error');
    });
  }

  function toggleVolume(el) {
    var content = el.nextElementSibling;
    var caret = el.querySelector('.timeline-caret');
    if (!content || !caret) return;
    var isVisible = content.style.display !== 'none';
    content.style.display = isVisible ? 'none' : 'block';
    caret.textContent = isVisible ? '▶' : '▼';
  }

  function toggleReference(el) {
    var content = el.nextElementSibling;
    var caret = el.querySelector('.timeline-caret-small');
    if (!content || !caret) return;
    var isVisible = content.style.display !== 'none';
    content.style.display = isVisible ? 'none' : 'block';
    caret.textContent = isVisible ? '▶' : '▼';
  }

  function escHtml(s) {
    if (s == null) return '';
    if (typeof s !== 'string') s = String(s);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escAttr(s) {
    if (s == null) return '';
    if (typeof s !== 'string') s = String(s);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  return {
    load: load,
    toggleVolume: toggleVolume,
    selectChapter: selectChapter,
    compareOne: compareOne,
    compareAll: compareAll,
    finalizeChapter: finalizeChapter,
    saveActual: saveActual,
    saveAnnotation: saveAnnotation,
    updateDivStatus: updateDivStatus,
    jumpToParagraph: jumpToParagraph,
    editDiv: editDiv,
    saveDivEdit: saveDivEdit,
    cancelDivEdit: cancelDivEdit,
    aiFixDiv: aiFixDiv,
    applyAiFix: applyAiFix,
    fixAllDivs: fixAllDivs,
    applyFixAll: applyFixAll,
    deleteDiv: deleteDiv,
    addDiv: addDiv,
    toggleReference: toggleReference,
    saveParagraph: saveParagraph
  };
})();