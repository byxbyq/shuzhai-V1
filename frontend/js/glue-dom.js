(function() {
  'use strict';


// 渲染多字段表单
window.renderDetailForm = function(container, fields, itemData) {
  var html = '';
  var currentGroup = '';

  fields.forEach(function(f) {
    if (f.group !== currentGroup) {
      if (currentGroup !== '') html += '</div>';
      if (f.group) {
        html += '<div class="def-field-group">';
        html += '<div class="def-field-group-title">' + f.group + '</div>';
      }
      currentGroup = f.group || '';
    }

    if (f.type === 'char-arc') {
      html += '<div class="def-field" data-field-key="' + f.key + '">';
      html += '<label class="def-field-label">' + (f.label || f.key) + '</label>';
      html += '<div class="def-field-char-arc">';
      html += '<input type="text" class="def-char-name" placeholder="角色名" value="' + esc(f.charName || '') + '" data-sub-key="charName">';
      html += '<span class="def-arc-sep">→</span>';
      html += '<input type="text" class="def-arc-text" placeholder="从X到Y的转变" value="' + esc(f.arcText || '') + '" data-sub-key="arcText">';
      html += '</div>';
      html += '</div>';
    } else if (f.type === 'hook') {
      html += '<div class="def-field" data-field-key="' + f.key + '">';
      html += '<label class="def-field-label">' + (f.label || f.key) + '</label>';
      html += '<input type="text" class="def-hook-text" placeholder="伏笔内容" value="' + esc(f.value || '') + '" data-sub-key="value">';
      html += '</div>';
    } else if (f.type === 'text') {
      html += '<div class="def-field" data-field-key="' + f.key + '">';
      html += '<label class="def-field-label">' + (f.label || f.key) + '</label>';
      html += '<input type="text" class="def-input" value="' + esc(f.value || '') + '" data-sub-key="value">';
      html += '</div>';
    } else {
      // textarea (default)
      html += '<div class="def-field" data-field-key="' + f.key + '">';
      html += '<label class="def-field-label"><span class="def-field-idx"></span>' + (f.label || f.key) + '</label>';
      html += '<textarea class="def-textarea" data-sub-key="value" placeholder="' + (f.placeholder || '') + '">' + esc(f.value || '') + '</textarea>';
      html += '</div>';
    }
  });

  if (currentGroup !== '') html += '</div>';
  container.innerHTML = html;

  // 绑定 input 事件 - 实时同步回源
  container.querySelectorAll('textarea, input').forEach(function(el) {
    el.addEventListener('input', function() {
      syncDetailToSource();
    });
  });
}

window._renderBsGraph = function() {
  var svg = document.getElementById('bs-graph-svg');
  if (!svg) return;
  var container = svg.parentElement;
  var w = container.clientWidth || 600;
  var h = container.clientHeight || 400;
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);

  if (_bsCards.length === 0) {
    svg.innerHTML = '<text x="' + (w/2) + '" y="' + (h/2) + '" text-anchor="middle" fill="var(--muted)" font-size="14">暂无创意卡片，请先生成</text>';
    return;
  }

  // 初始化节点位置（圆形布局）
  var cx = w / 2, cy = h / 2;
  var radius = Math.min(w, h) * 0.3;
  _bsCards.forEach(function(card, i) {
    if (!_bsNodePositions[card.id]) {
      var angle = (i / _bsCards.length) * 2 * Math.PI - Math.PI / 2;
      _bsNodePositions[card.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle)
      };
    }
  });

  var parts = [];
  // 绘制边
  _bsEdges.forEach(function(edge) {
    var src = _bsNodePositions[edge.src];
    var dst = _bsNodePositions[edge.dst];
    if (!src || !dst) return;
    parts.push('<line x1="' + src.x + '" y1="' + src.y + '" x2="' + dst.x + '" y2="' + dst.y + '" stroke="var(--accent)" stroke-width="1.5" opacity="0.4"/>');
  });
  // 绘制节点
  _bsCards.forEach(function(card) {
    var pos = _bsNodePositions[card.id];
    if (!pos) return;
    var idea = card.data || {};
    var title = idea.title || '未命名';
    var impact = idea.impact || 'medium';
    var color = impact === 'high' ? '#e74c3c' : (impact === 'medium' ? '#f39c12' : '#95a5a6');
    var isSource = _bsConnectSource === card.id;
    // 节点圆形
    parts.push('<circle cx="' + pos.x + '" cy="' + pos.y + '" r="30" fill="var(--surface)" stroke="' + color + '" stroke-width="' + (isSource ? '4' : '2') + '" data-bs-node="' + card.id + '" style="cursor:' + (_bsConnectMode ? 'pointer' : 'move') + '"/>');
    // 标题文字
    var shortTitle = title.length > 5 ? title.substring(0, 5) + '…' : title;
    parts.push('<text x="' + pos.x + '" y="' + (pos.y + 3) + '" text-anchor="middle" fill="var(--ink)" font-size="11" font-weight="600" style="pointer-events:none">' + _escapeXml(shortTitle) + '</text>');
  });
  svg.innerHTML = parts.join('');

  // 绑定拖拽和点击
  _bindBsGraphNodes(svg);
}

window._bindBsGraphNodes = function(svg) {
  svg.querySelectorAll('[data-bs-node]').forEach(function(circle) {
    var cardId = circle.getAttribute('data-bs-node');
    var isDragging = false;
    var dragOffset = {x: 0, y: 0};

    circle.addEventListener('mousedown', function(e) {
      if (_bsConnectMode) return; // 连线模式下不拖拽
      e.preventDefault();
      isDragging = true;
      var pos = _bsNodePositions[cardId];
      var svgRect = svg.getBoundingClientRect();
      dragOffset.x = e.clientX - svgRect.left - pos.x;
      dragOffset.y = e.clientY - svgRect.top - pos.y;
    });

    circle.addEventListener('click', function(e) {
      if (!_bsConnectMode) return;
      e.stopPropagation();
      if (!_bsConnectSource) {
        _bsConnectSource = cardId;
        _renderBsGraph();
      } else if (_bsConnectSource !== cardId) {
        // 创建连线（避免重复）
        var exists = _bsEdges.some(function(ed) {
          return (ed.src === _bsConnectSource && ed.dst === cardId) || (ed.src === cardId && ed.dst === _bsConnectSource);
        });
        if (!exists) {
          _bsEdges.push({src: _bsConnectSource, dst: cardId});
          _saveBrainstormCards();
        }
        _bsConnectSource = null;
        _bsConnectMode = false;
        toggleBsConnectMode(); // 重置按钮状态
        _renderBsGraph();
      }
    });

    document.addEventListener('mousemove', function(e) {
      if (!isDragging) return;
      var svgRect = svg.getBoundingClientRect();
      var x = e.clientX - svgRect.left - dragOffset.x;
      var y = e.clientY - svgRect.top - dragOffset.y;
      x = Math.max(35, Math.min(svgRect.width - 35, x));
      y = Math.max(35, Math.min(svgRect.height - 35, y));
      _bsNodePositions[cardId] = {x: x, y: y};
      _renderBsGraph();
    });

    document.addEventListener('mouseup', function() {
      if (isDragging) {
        isDragging = false;
        _saveBrainstormCards();
      }
    });
  });
}
window.selectSenseTab = function(sense) {
  _currentSenseType = sense;
  document.querySelectorAll('.sense-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.sense === sense);
  });
}
var SENSE_LABELS = {
  visual: '👁️ 视觉',
  auditory: '👂 听觉',
  olfactory: '👃 嗅觉',
  tactile: '✋ 触觉',
  gustatory: '👅 味觉',
};
window._renderSensoryResults = function(sensory) {
  var resultsDiv = document.getElementById('sensory-results');
  var html = '';

  // Individual sense blocks
  ['visual', 'auditory', 'olfactory', 'tactile', 'gustatory'].forEach(function(key) {
    var text = sensory[key];
    if (text && text.trim()) {
      html += '<div class="sense-block">' +
        '<div class="sense-block-header">' +
          '<span class="sense-block-label">' + SENSE_LABELS[key] + '</span>' +
          '<button class="sense-block-copy" onclick="copySensoryText(\'' + key + '\')">复制</button>' +
        '</div>' +
        '<div class="sense-block-text" id="sense-text-' + key + '">' + esc(text) + '</div>' +
      '</div>';
    }
  });

  // Combined text
  if (sensory.combined && sensory.combined.trim()) {
    html += '<div class="sense-combined">' +
      '<div class="sense-combined-header">' +
        '<span class="sense-combined-label">✨ 融合段落</span>' +
        '<button class="sense-block-copy" onclick="copySensoryText(\'combined\')">复制</button>' +
      '</div>' +
      '<div class="sense-combined-text" id="sense-text-combined">' + esc(sensory.combined) + '</div>' +
      '<div style="margin-top:10px;text-align:right">' +
        '<button class="btn-sm accept" onclick="insertSensoryToEditor()">插入到正文</button>' +
      '</div>' +
    '</div>';
  }

  if (!html) {
    html = '<div class="sensory-empty"><p>未生成有效描写，请重试</p></div>';
  }
  resultsDiv.innerHTML = html;
}
window.copySensoryText = function(key) {
  var el = document.getElementById('sense-text-' + key);
  if (el) {
    var text = el.innerText;
    navigator.clipboard.writeText(text).then(function() {
      showToast('已复制到剪贴板');
    }).catch(function() {
      // Fallback
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('已复制到剪贴板');
    });
  }
}
window.insertSensoryToEditor = function() {
  var el = document.getElementById('sense-text-combined');
  if (!el) return;
  var text = el.innerText;
  var editor = document.getElementById('editor-content');
  if (editor) {
    editor.innerHTML += '<p>' + esc(text) + '</p>';
    showToast('已插入到正文');
  }
}
window.renderPluginBar = async function() {
  var inner = document.getElementById('plugin-bar-inner');
  if (!inner) return;
  inner.innerHTML = '';

  // Built-in plugins
  var builtins = [
    {id: 'brainstorm', name: '头脑风暴', icon: '🧠', cb: openBrainstormPanel},
    {id: 'sensory', name: '五感描写', icon: '👁️', cb: openSensoryPanel},
    {id: 'describe', name: '描写增强', icon: '📝', cb: openDescribePanel},
    {id: 'expand', name: '场景扩写', icon: '📏', cb: openExpandPanel},
    {id: 'rewrite', name: '灵活重写', icon: '🔄', cb: openRewritePanel},
    {id: 'feedback', name: '5维反馈', icon: '💡', cb: openFeedbackPanel},
    {id: 'wordcount', name: '字数统计', icon: '📊', cb: function() {
      var editor = document.getElementById('editor-content');
      if (editor) {
        var text = editor.innerText;
        var chars = text.replace(/\s/g, '').length;
        var words = text.length;
        showToast('总字数：' + words + ' | 非空字符：' + chars);
      }
    }},
    {id: 'name-gen', name: '人名生成', icon: '🏷️', cb: function() {
      aiBrainstorm('角色命名', '', 'character').then(function(r) {
        if (r.ok && r.ideas) {
          _addBrainstormCard(r.ideas[0]);
          showToast('人名创意已添加到头脑风暴画板');
        }
      });
    }},
    {id: 'dialogue', name: '对话润色', icon: '💬', cb: function() {
      var editor = document.getElementById('editor-content');
      if (!editor) return;
      var sel = window.getSelection();
      var text = sel.toString();
      if (!text) { showToast('请先选中需要润色的对话文本'); return; }
      callAI([{role: 'user', content: '请润色以下对话，使其更自然生动，保持原意不变：\n\n' + text}]).then(function(r) {
        if (r.ok && r.content) {
          var range = sel.getRangeAt(0);
          range.deleteContents();
          range.insertNode(document.createTextNode(r.content.trim()));
          showToast('对话已润色');
        }
      });
    }},
    {id: 'summary', name: '章节摘要', icon: '📋', cb: function() {
      var editor = document.getElementById('editor-content');
      if (!editor) return;
      var text = editor.innerText.substring(0, 3000);
      if (!text) { showToast('当前章节为空'); return; }
      callAI([{role: 'user', content: '请用100字以内概括以下章节内容的核心事件：\n\n' + text}]).then(function(r) {
        if (r.ok && r.content) {
          showToast(r.content.substring(0, 100));
        }
      });
    }},
  ];

  builtins.forEach(function(p) {
    var btn = document.createElement('button');
    btn.className = 'plugin-btn';
    btn.innerHTML = p.icon + ' ' + p.name;
    btn.onclick = p.cb;
    inner.appendChild(btn);
  });

  // Custom plugins
  _plugins.forEach(function(p) {
    var btn = document.createElement('button');
    btn.className = 'plugin-btn';
    btn.innerHTML = p.icon + ' ' + p.name;
    btn.onclick = p.callback;
    inner.appendChild(btn);
  });

  // Add "manage" button
  var mgmtBtn = document.createElement('button');
  mgmtBtn.className = 'plugin-btn';
  mgmtBtn.style.borderStyle = 'dashed';
  mgmtBtn.innerHTML = '⚙️ 管理';
  mgmtBtn.onclick = function() {
    showToast('已注册 ' + (_plugins.length + 6) + ' 个插件（6 内置 + ' + _plugins.length + ' 自定义）');
  };
  inner.appendChild(mgmtBtn);
}

window._renderGraphSVG = function() {
  var container = document.getElementById('graph-svg-container');
  if (!container) return;
  var w = container.clientWidth || 800;
  var h = container.clientHeight || 600;
  var cx = w / 2;
  var cy = h / 2;
  var radius = Math.min(w, h) * 0.35;

  // 圆形布局
  var nodePositions = {};
  var n = _graphNodes.length;
  _graphNodes.forEach(function(node, i) {
    var angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    nodePositions[node.id] = {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle)
    };
  });

  // 构建 SVG
  var svgParts = ['<svg width="' + w + '" height="' + h + '" style="display:block" id="graph-svg">'];

  // 定义箭头
  svgParts.push('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="20" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke-width="1" opacity="0.5"/></marker></defs>');

  // 绘制边
  _graphEdges.forEach(function(edge) {
    var src = nodePositions[edge.src];
    var dst = nodePositions[edge.dst];
    if (!src || !dst) return;
    var color = _getEdgeColor(edge);
    // 计算控制点（曲线）
    var midX = (src.x + dst.x) / 2;
    var midY = (src.y + dst.y) / 2;
    var dx = dst.x - src.x;
    var dy = dst.y - src.y;
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 1) dist = 1;
    // 偏移控制点使曲线弯曲
    var offset = 30;
    var perpX = -dy / dist * offset;
    var perpY = dx / dist * offset;
    var ctrlX = midX + perpX;
    var ctrlY = midY + perpY;
    var pathD = 'M ' + src.x + ' ' + src.y + ' Q ' + ctrlX + ' ' + ctrlY + ' ' + dst.x + ' ' + dst.y;
    var opacity = Math.min(0.8, 0.3 + (edge.weight || 1) * 0.3);
    svgParts.push('<path d="' + pathD + '" fill="none" stroke="' + color + '" stroke-width="2" opacity="' + opacity + '" data-edge="' + edge.src + '->' + edge.dst + '" style="cursor:pointer"/>');
  });

  // 绘制节点
  _graphNodes.forEach(function(node) {
    var pos = nodePositions[node.id];
    if (!pos) return;
    var nodeRadius = 28;
    // 节点底色
    svgParts.push('<circle cx="' + pos.x + '" cy="' + pos.y + '" r="' + nodeRadius + '" fill="var(--surface)" stroke="var(--accent)" stroke-width="2" style="cursor:pointer" data-node="' + node.id + '"/>');
    // 节点文字
    var displayName = node.id.length > 4 ? node.id.substring(0, 4) + '…' : node.id;
    svgParts.push('<text x="' + pos.x + '" y="' + (pos.y + 4) + '" text-anchor="middle" fill="var(--ink)" font-size="13" font-weight="600" style="pointer-events:none">' + _escapeXml(displayName) + '</text>');
  });

  svgParts.push('</svg>');
  container.innerHTML = svgParts.join('');

  // 更新节点计数
  var countEl = document.getElementById('graph-node-count');
  if (countEl) countEl.textContent = n + ' 个角色 / ' + _graphEdges.length + ' 条关系';

  // 绑定交互
  _bindGraphInteractions(nodePositions);
}

window._bindGraphInteractions = function(nodePositions) {
  var svg = document.getElementById('graph-svg');
  var tooltip = document.getElementById('graph-tooltip');
  if (!svg || !tooltip) return;

  // 节点悬停
  svg.querySelectorAll('[data-node]').forEach(function(circle) {
    var nodeId = circle.getAttribute('data-node');
    circle.addEventListener('mouseenter', function(e) {
      // 高亮关联边
      svg.querySelectorAll('[data-edge]').forEach(function(path) {
        var edgeId = path.getAttribute('data-edge');
        if (edgeId.indexOf(nodeId) >= 0) {
          path.setAttribute('stroke-width', '4');
          path.setAttribute('opacity', '1');
        } else {
          path.setAttribute('opacity', '0.15');
        }
      });
      // 显示工具提示
      var relatedEdges = _graphEdges.filter(function(e) { return e.src === nodeId || e.dst === nodeId; });
      var html = '<b style="color:var(--accent)">' + _escapeXml(nodeId) + '</b>';
      if (relatedEdges.length > 0) {
        html += '<div style="margin-top:4px;border-top:1px solid var(--border-soft);padding-top:4px">';
        relatedEdges.forEach(function(e) {
          var target = e.src === nodeId ? e.dst : e.src;
          html += '<div style="margin:2px 0"><span style="color:' + _getEdgeColor(e) + '">●</span> ' + _escapeXml(target) + ': ' + _escapeXml(_getEdgeLabel(e)) + '</div>';
        });
        html += '</div>';
      }
      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      var rect = svg.getBoundingClientRect();
      tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
      tooltip.style.top = (e.clientY - rect.top + 12) + 'px';
    });
    circle.addEventListener('mouseleave', function() {
      svg.querySelectorAll('[data-edge]').forEach(function(path) {
        path.setAttribute('stroke-width', '2');
        path.setAttribute('opacity', Math.min(0.8, 0.3 + 1 * 0.3));
      });
      tooltip.style.display = 'none';
    });
  });

  // 边悬停
  svg.querySelectorAll('[data-edge]').forEach(function(path) {
    var edgeId = path.getAttribute('data-edge');
    var parts = edgeId.split('->');
    var edge = _graphEdges.find(function(e) { return e.src === parts[0] && e.dst === parts[1]; });
    if (!edge) return;
    path.addEventListener('mouseenter', function(e) {
      path.setAttribute('stroke-width', '4');
      path.setAttribute('opacity', '1');
      var html = '<b>' + _escapeXml(edge.src) + ' → ' + _escapeXml(edge.dst) + '</b>';
      html += '<div style="margin-top:4px">' + _escapeXml(_getEdgeLabel(edge)) + '</div>';
      if (edge.metadata && edge.metadata.relationship_text) {
        html += '<div style="margin-top:2px;color:var(--muted);font-size:11px">原始描述: ' + _escapeXml(edge.metadata.relationship_text) + '</div>';
      }
      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      var rect = svg.getBoundingClientRect();
      tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
      tooltip.style.top = (e.clientY - rect.top + 12) + 'px';
    });
    path.addEventListener('mouseleave', function() {
      path.setAttribute('stroke-width', '2');
      path.setAttribute('opacity', Math.min(0.8, 0.3 + (edge.weight || 1) * 0.3));
      tooltip.style.display = 'none';
    });
  });
}

})();