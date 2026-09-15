// Extracted from app.js - AI分析面板 (AI味检测/文风指纹/伏笔引力/线程分布)
// ═══════════════════════════════════════════════════════════════════════
// 6.2 AI分析面板（AI味检测 / 文风指纹 / 伏笔引力 / 线程分布）
// ═══════════════════════════════════════════════════════════════════════

// 获取当前章节正文（编辑器内容优先，回退到 chapters 数组）
function _getCurrentChapterContent() {
  try {
    var editorEl = document.getElementById('editor-content');
    if (editorEl) {
      var txt = editorEl.innerText || '';
      if (txt && txt.trim().length > 20) return txt;
    }
  } catch (e) {}
  try {
    if (typeof chapters !== 'undefined' && typeof currentChapterIndex !== 'undefined'
        && chapters && chapters[currentChapterIndex]) {
      return chapters[currentChapterIndex].content || '';
    }
  } catch (e2) {}
  return '';
}

// 获取当前章节标题
function _getCurrentChapterTitle() {
  try {
    if (typeof chapters !== 'undefined' && typeof currentChapterIndex !== 'undefined'
        && chapters && chapters[currentChapterIndex]) {
      return '第' + (currentChapterIndex + 1) + '章 ' + (chapters[currentChapterIndex].title || '');
    }
  } catch (e) {}
  return '当前章节';
}

// 打开AI分析综合面板
function openAIAnalysisPanel() {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  if (!document.getElementById('ai-analysis-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'ai-analysis-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1200';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1201;width:94%;max-width:820px;height:88vh;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);display:flex;flex-direction:column;overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">🔬</span><span class="title-accent-md-xl">AI分析面板</span></div>'
      + '    <button onclick="closeOverlay(\'ai-analysis-overlay\')" class="btn-ghost-icon-xl-alt">✕</button>'
      + '  </div>'
      + '  <div style="display:flex;gap:2px;padding:8px 12px 0;border-bottom:1px solid var(--border);background:var(--surface)">'
      + '    <button class="ai-tab active" data-tab="flavor" onclick="switchAITab(\'flavor\')">AI味检测</button>'
      + '    <button class="ai-tab" data-tab="style" onclick="switchAITab(\'style\')">文风指纹</button>'
      + '    <button class="ai-tab" data-tab="pull" onclick="switchAITab(\'pull\')">伏笔引力</button>'
      + '    <button class="ai-tab" data-tab="strand" onclick="switchAITab(\'strand\')">线程分布</button>'
      + '  </div>'
      + '  <div id="ai-analysis-body" style="flex:1;overflow-y:auto;padding:16px"></div>'
      + '</div>';
    document.body.appendChild(overlay);
    // 初始化标签页样式
    document.querySelectorAll('.ai-tab').forEach(function(btn) {
      btn.style.cssText = btn.classList.contains('active')
        ? 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid var(--accent);background:none;color:var(--accent);cursor:pointer'
        : 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid transparent;background:none;color:var(--muted);cursor:pointer';
    });
  } else {
    document.getElementById('ai-analysis-overlay').style.display = 'flex';
  }
  // 默认加载第一个标签页
  switchAITab('flavor');
}

var _aiCurrentTab = 'flavor';
function switchAITab(tab) {
  _aiCurrentTab = tab;
  document.querySelectorAll('.ai-tab').forEach(function(btn) {
    var active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    btn.style.cssText = active
      ? 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid var(--accent);background:none;color:var(--accent);cursor:pointer'
      : 'padding:6px 14px;font-size:12px;border:none;border-bottom:2px solid transparent;background:none;color:var(--muted);cursor:pointer';
  });
  var body = document.getElementById('ai-analysis-body');
  if (!body) return;
  if (tab === 'flavor') renderAIFlavor(body);
  else if (tab === 'style') renderStyleFingerprint(body);
  else if (tab === 'pull') renderReadPull(body);
  else if (tab === 'strand') renderStrandStats(body);
}

// ── 标签1: AI味检测（7Gate）──
function renderAIFlavor(body) {
  var content = _getCurrentChapterContent();
  var title = _getCurrentChapterTitle();
  body.innerHTML = '<div class="empty-state-sm-alt">⏳ 正在检测「' + title.replace(/</g, '&lt;') + '」的AI味...</div>';
  if (!content || content.length < 100) {
    body.innerHTML = '<div class="empty-warn-lg">⚠️ 当前章节内容不足100字，无法进行AI味检测<br><span class="text-md text-muted">请先在编辑器中写入或生成正文</span></div>';
    return;
  }
  try {
    var result = (typeof AuditJS !== 'undefined' && AuditJS.detectAiFlavor)
      ? AuditJS.detectAiFlavor(content)
      : null;
    if (!result) {
      body.innerHTML = '<div class="empty-danger-lg">❌ AuditJS 模块未加载</div>';
      return;
    }
    // 将 issues 按 7Gate 分类
    var gates = _classifyAIIssuesToGates(result.issues || []);
    var score = result.score || 0;
    var level = result.level || '';
    var levelColor = score === 0 ? 'var(--success, #10b981)' : (score <= 20 ? 'var(--warn)' : 'var(--danger, #ef4444)');
    var levelText = {ok: '✓ 通过', warning: '⚠ 警告', serious: '✗ 严重', clean: '✓ 干净'}[level] || level;

    var html = ''
      + '<div style="display:flex;align-items:center;gap:16px;padding:14px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:14px">'
      + '  <div style="text-align:center">'
      + '    <div style="font-size:32px;font-weight:700;color:' + levelColor + '">' + score + '</div>'
      + '    <div class="text-sm text-muted">扣分 / 100</div>'
      + '  </div>'
      + '  <div class="flex-1">'
      + '    <div style="font-size:14px;font-weight:600;color:' + levelColor + '">' + levelText + '</div>'
      + '    <div style="font-size:11px;color:var(--muted);margin-top:4px">' + (result.summary || '').replace(/</g, '&lt;') + '</div>'
      + '    <div style="font-size:11px;color:var(--muted);margin-top:2px">检测章节: ' + title.replace(/</g, '&lt;') + ' · 字数: ' + content.length + '</div>'
      + '  </div>'
      + '</div>';
    // 7Gate 展示
    html += '<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">7Gate 检测明细</div>';
    gates.forEach(function(g) {
      var hasIssue = g.issues.length > 0;
      var headerColor = hasIssue ? 'var(--warn)' : 'var(--success, #10b981)';
      var icon = hasIssue ? '⚠️' : '✅';
      html += '<div style="margin-bottom:8px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden">'
        + '<div style="padding:10px 12px;background:var(--surface);display:flex;align-items:center;justify-content:space-between">'
        + '  <div><span style="margin-right:6px">' + icon + '</span><span class="text-base font-semibold">' + g.label + '</span></div>'
        + '  <span style="font-size:11px;color:' + headerColor + '">' + (hasIssue ? g.issues.length + ' 项问题' : '通过') + '</span>'
        + '</div>';
      if (hasIssue) {
        html += '<div style="padding:8px 12px;background:var(--bg)">';
        g.issues.forEach(function(iss) {
          html += '<div style="padding:4px 0;font-size:11px;color:var(--muted);border-bottom:1px solid var(--border-soft)">· ' + (iss.message || '').replace(/</g, '&lt;') + '</div>';
        });
        html += '</div>';
      }
      html += '</div>';
    });
    // 一键优化建议按钮
    html += '<div class="mt-4 pt-3.5 separator">'
      + '  <button onclick="requestOptimizationSuggestions(\'flavor\')" class="btn-accent-full-lg" onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'" onmouseout="this.style.background=\'transparent\'">💡 一键优化建议</button>'
      + '  <div id="ai-opt-suggestions-flavor" class="mt-2.5"></div>'
      + '</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="empty-danger-lg">❌ 检测出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// 将 AuditJS 检测出的问题分类到 7Gate
function _classifyAIIssuesToGates(issues) {
  var gates = [
    {key: 'A', label: 'Gate A · 禁用词', types: ['buzzword_forbidden', 'buzzword_density'], issues: []},
    {key: 'B', label: 'Gate B · 句式套路', types: ['formulaic_transition', 'transition_overuse', 'pattern_repetition', 'monotonous_sentence', 'connector_overuse'], issues: []},
    {key: 'C', label: 'Gate C · 心理描写', types: ['plastic_prose'], issues: []},
    {key: 'D', label: 'Gate D · 节奏', types: ['low_burstiness', 'uniform_paragraphs'], issues: []},
    {key: 'E', label: 'Gate E · 对话腔调', types: ['plastic_prose'], issues: []},
    {key: 'F', label: 'Gate F · 结尾升华', types: ['narrator_overreach'], issues: []},
    {key: 'G', label: 'Gate G · 解释腔上帝感', types: ['narrator_overreach', 'high_de_density'], issues: []},
  ];
  issues.forEach(function(iss) {
    var t = iss.type || '';
    gates.forEach(function(g) {
      if (g.types.indexOf(t) >= 0) g.issues.push(iss);
    });
  });
  return gates;
}

// ── 标签2: 文风指纹（8维）──
async function renderStyleFingerprint(body) {
  var content = _getCurrentChapterContent();
  var title = _getCurrentChapterTitle();
  if (!content || content.length < 200) {
    body.innerHTML = '<div class="empty-warn-lg">⚠️ 当前章节内容不足200字，无法提取文风指纹<br><span class="text-md text-muted">文风指纹分析需≥200字</span></div>';
    return;
  }
  body.innerHTML = '<div class="empty-state-sm-alt">⏳ 正在提取文风指纹...</div>';
  try {
    // 后端 style-extract 端点期望 text 字段
    var r = await api('/api/validate/style-extract', {
      method: 'POST',
      body: JSON.stringify({text: content, source_name: title})
    });
    if (!r.ok || !r.fingerprint) {
      body.innerHTML = '<div class="empty-danger-lg">❌ 提取失败: ' + (r.error || '后端无响应').replace(/</g, '&lt;') + '</div>';
      return;
    }
    var fp = r.fingerprint;
    if (fp.error) {
      body.innerHTML = '<div class="empty-warn-lg">⚠️ ' + fp.error.replace(/</g, '&lt;') + '</div>';
      return;
    }
    // 8维指纹展示
    var dims = [
      {label: '平均句长', value: fp.avg_sentence_length + ' 字', sub: '标准差 ' + fp.sentence_length_std},
      {label: '平均段长', value: fp.avg_paragraph_length + ' 字', sub: '范围 ' + (fp.paragraph_length_range ? fp.paragraph_length_range.min + '-' + fp.paragraph_length_range.max : '-')},
      {label: '词汇多样性 TTR', value: fp.vocabulary_diversity, sub: fp.vocabulary_diversity < 0.45 ? '偏低-偏AI' : (fp.vocabulary_diversity < 0.5 ? '偏低' : '自然-人类风格')},
      {label: '开头模式', value: (fp.top_opening_patterns && fp.top_opening_patterns.length) ? fp.top_opening_patterns.length + ' 种高频' : '无明显高频', sub: (fp.top_opening_patterns || []).join(', ').replace(/</g, '&lt;')},
      {label: '修辞特征', value: (fp.rhetorical_features && fp.rhetorical_features.length) ? fp.rhetorical_features.length + ' 类' : '无', sub: (fp.rhetorical_features || []).join(', ').replace(/</g, '&lt;')},
      {label: '"的"字密度', value: fp.de_density + ' /千字', sub: fp.de_density > 30 ? '偏高' : '正常'},
      {label: '对话密度', value: fp.dialogue_density + ' /10句', sub: fp.dialogue_density > 3 ? '对话较多' : '叙述为主'},
      {label: '长度分布', value: fp.sentence_count + ' 句', sub: _formatLenDist(fp.length_distribution)},
    ];
    var html = ''
      + '<div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:14px;font-size:12px">'
      + '  <span class="text-muted">分析章节:</span> ' + title.replace(/</g, '&lt;') + ' · '
      + '  <span class="text-muted">总字数:</span> ' + (fp.text_length || content.length) + ' · '
      + '  <span class="text-muted">句数:</span> ' + fp.sentence_count + ' · '
      + '  <span class="text-muted">段数:</span> ' + fp.paragraph_count
      + '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    dims.forEach(function(d) {
      html += '<div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm)">'
        + '<div style="font-size:11px;color:var(--muted);margin-bottom:4px">' + d.label + '</div>'
        + '<div style="font-size:18px;font-weight:600;color:var(--accent)">' + d.value + '</div>'
        + '<div class="text-xs text-muted mt-1">' + (d.sub || '') + '</div>'
        + '</div>';
    });
    html += '</div>';
    // 句长CV 特别提示
    if (fp.sentence_length_cv !== undefined) {
      var cvColor = fp.sentence_length_cv < 0.4 ? 'var(--warn)' : 'var(--success, #10b981)';
      html += '<div style="margin-top:12px;padding:10px 12px;background:var(--bg);border:1px solid var(--border-soft);border-radius:var(--radius-sm);font-size:11px">'
        + '<span class="text-muted">句长变异系数 CV:</span> <span style="color:' + cvColor + ';font-weight:600">' + fp.sentence_length_cv + '</span> '
        + '<span class="text-muted">(' + (fp.sentence_length_cv < 0.4 ? '均匀-偏AI风格' : '自然-人类风格') + ')</span></div>';
    }
    // 一键优化建议按钮
    html += '<div class="mt-4 pt-3.5 separator">'
      + '  <button onclick="requestOptimizationSuggestions(\'style\')" class="btn-accent-full-lg" onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'" onmouseout="this.style.background=\'transparent\'">💡 一键优化建议</button>'
      + '  <div id="ai-opt-suggestions-style" class="mt-2.5"></div>'
      + '</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="empty-danger-lg">❌ 提取出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// 格式化长度分布
function _formatLenDist(dist) {
  if (!dist) return '';
  var parts = [];
  Object.keys(dist).forEach(function(k) {
    if (dist[k] > 0) parts.push(k.split('(')[0] + ':' + dist[k]);
  });
  return parts.join(' · ') || '无';
}

// ── 标签3: 伏笔引力（追读力4维评分）──
async function renderReadPull(body) {
  body.innerHTML = '<div class="empty-state-sm-alt">⏳ 正在计算伏笔引力...</div>';
  try {
    var r = await api('/api/ledger/read-pull');
    if (!r.ok) {
      body.innerHTML = '<div class="empty-danger-lg">❌ 获取失败: ' + (r.error || '请先打开项目').replace(/</g, '&lt;') + '</div>';
      return;
    }
    var score = r.score || 0;
    var level = r.level || '';
    var levelColor = score >= 70 ? 'var(--success, #10b981)' : (score >= 40 ? 'var(--warn)' : (score >= 20 ? 'var(--warn)' : 'var(--danger, #ef4444)'));
    var levelText = {strong: '🔥 追读力强劲', moderate: '✓ 追读力适中', weak: '⚠ 追读力偏弱', empty: '❌ 追读力不足'}[level] || level;

    var html = ''
      + '<div style="display:flex;align-items:center;gap:16px;padding:14px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:14px">'
      + '  <div style="text-align:center">'
      + '    <div style="font-size:36px;font-weight:700;color:' + levelColor + '">' + score + '</div>'
      + '    <div class="text-sm text-muted">总分 / 100</div>'
      + '  </div>'
      + '  <div class="flex-1">'
      + '    <div style="font-size:14px;font-weight:600;color:' + levelColor + '">' + levelText + '</div>'
      + '    <div style="font-size:11px;color:var(--muted);margin-top:4px">' + (r.summary || '').replace(/</g, '&lt;') + '</div>'
      + '    <div style="font-size:11px;color:var(--muted);margin-top:2px">开放悬念: ' + (r.active_count || 0) + ' 个</div>'
      + '  </div>'
      + '</div>';
    // 4维评分
    var dims = [
      {label: '数量分', value: r.count_score || 0, max: 30, desc: '开放悬念数量加权'},
      {label: '强度分', value: r.strength_score || 0, max: 30, desc: '悬念强度(1-5级)加权'},
      {label: '弧线分', value: r.arc_score || 0, max: 21, desc: 'short/medium/long 弧线覆盖'},
      {label: '迫近分', value: r.imminent_score || 0, max: 20, desc: '即将到期/已逾期悬念'},
    ];
    html += '<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">4维评分明细</div>';
    dims.forEach(function(d) {
      var pct = Math.round(d.value / d.max * 100);
      var barColor = pct >= 70 ? 'var(--success, #10b981)' : (pct >= 40 ? 'var(--accent)' : 'var(--warn)');
      html += '<div class="mb-2.5">'
        + '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">'
        + '  <span class="text-ink">' + d.label + '</span>'
        + '  <span class="text-muted">' + d.value + '/' + d.max + ' · ' + d.desc + '</span>'
        + '</div>'
        + '<div class="progress-track">'
        + '  <div style="height:100%;width:' + pct + '%;background:' + barColor + '"></div>'
        + '</div>'
        + '</div>';
    });
    // 弧线分布
    if (r.arc_distribution) {
      html += '<div style="margin-top:14px;padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px">'
        + '<span class="text-muted">弧线分布:</span> '
        + 'short=' + (r.arc_distribution.short || 0) + ' · '
        + 'medium=' + (r.arc_distribution.medium || 0) + ' · '
        + 'long=' + (r.arc_distribution.long || 0) + ' · '
        + '未标注=' + (r.arc_distribution.untyped || 0)
        + '</div>';
    }
    // 警告
    if (r.warnings && r.warnings.length) {
      html += '<div style="margin-top:10px;padding:10px 12px;background:var(--bg);border:1px solid var(--warn);border-radius:var(--radius-sm);font-size:11px">';
      r.warnings.forEach(function(w) {
        html += '<div style="color:var(--warn);padding:2px 0">⚠ ' + w.replace(/</g, '&lt;') + '</div>';
      });
      html += '</div>';
    }
    // 一键优化建议按钮
    html += '<div class="mt-4 pt-3.5 separator">'
      + '  <button onclick="requestOptimizationSuggestions(\'pull\')" class="btn-accent-full-lg" onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'" onmouseout="this.style.background=\'transparent\'">💡 一键优化建议</button>'
      + '  <div id="ai-opt-suggestions-pull" class="mt-2.5"></div>'
      + '</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="empty-danger-lg">❌ 计算出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// ── 标签4: 线程分布（Strand Weave 三线比例+红线检查）──
async function renderStrandStats(body) {
  body.innerHTML = '<div class="empty-state-sm-alt">⏳ 正在统计线程分布...</div>';
  try {
    var r = await api('/api/ledger/strand-stats');
    if (!r.ok && r.total === undefined) {
      body.innerHTML = '<div class="empty-danger-lg">❌ 获取失败: ' + (r.error || '请先打开项目').replace(/</g, '&lt;') + '</div>';
      return;
    }
    var dist = r.distribution || {};
    var pct = r.percentages || {};
    var target = r.target || {Q: 60, F: 20, C: 20};
    var redLines = r.red_lines || [];

    var html = ''
      + '<div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:14px;font-size:12px">'
      + '  <span class="text-muted">已记录章节:</span> ' + (r.total || 0) + ' · '
      + '  <span class="text-muted">已标注:</span> ' + (r.typed || 0) + ' · '
      + '  <span class="text-muted">未标注:</span> ' + (dist.untyped || 0)
      + '</div>';
    // 三线分布条形图
    var strands = [
      {key: 'Q', name: 'Quest 主线', color: '#4a90d9', count: dist.Q || 0, pct: pct.Q || 0, target: target.Q || 60},
      {key: 'F', name: 'Fire 爽点线', color: '#e74c3c', count: dist.F || 0, pct: pct.F || 0, target: target.F || 20},
      {key: 'C', name: 'Constellation 设定线', color: '#27ae60', count: dist.C || 0, pct: pct.C || 0, target: target.C || 20},
    ];
    html += '<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:10px">三线分布</div>';
    strands.forEach(function(s) {
      html += '<div style="margin-bottom:12px">'
        + '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">'
        + '  <span class="text-ink">' + s.name + '</span>'
        + '  <span class="text-muted">' + s.count + ' 章 · ' + s.pct + '% (目标 ' + s.target + '%)</span>'
        + '</div>'
        + '<div style="height:10px;background:var(--bg);border-radius:5px;overflow:hidden;position:relative">'
        + '  <div style="height:100%;width:' + s.pct + '%;background:' + s.color + '"></div>'
        + '  <div style="position:absolute;top:0;bottom:0;left:' + s.target + '%;width:1px;background:var(--muted);opacity:0.5"></div>'
        + '</div>'
        + '</div>';
    });
    // 红线检查
    html += '<div style="font-size:12px;font-weight:600;color:var(--text);margin:16px 0 8px">红线检查</div>';
    if (redLines.length === 0) {
      html += '<div style="padding:12px;background:var(--surface);border:1px solid var(--success, #10b981);border-radius:var(--radius-sm);font-size:12px;color:var(--success, #10b981)">✅ 无红线告警，节奏分布健康</div>';
    } else {
      redLines.forEach(function(rl) {
        html += '<div style="padding:10px 12px;margin-bottom:6px;background:var(--bg);border:1px solid var(--danger, #ef4444);border-radius:var(--radius-sm);font-size:11px;color:var(--danger, #ef4444)">🚨 ' + rl.replace(/</g, '&lt;') + '</div>';
      });
    }
    // 连续统计
    html += '<div style="margin-top:14px;padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px">'
      + '<div style="color:var(--muted);margin-bottom:4px">连续性指标</div>'
      + 'Quest最长连续: ' + (r.max_consecutive_q || 0) + ' 章 (红线5)<br>'
      + 'Fire最长断档: ' + (r.max_fire_gap || 0) + ' 章 (红线10)<br>'
      + 'Constellation最长断档: ' + (r.max_c_gap || 0) + ' 章 (红线15)'
      + '</div>';
    // 摘要
    if (r.summary) {
      html += '<div style="margin-top:10px;padding:10px 12px;background:var(--bg);border:1px solid var(--border-soft);border-radius:var(--radius-sm);font-size:11px;color:var(--muted)">' + r.summary.replace(/</g, '&lt;') + '</div>';
    }
    // 一键优化建议按钮
    html += '<div class="mt-4 pt-3.5 separator">'
      + '  <button onclick="requestOptimizationSuggestions(\'strand\')" class="btn-accent-full-lg" onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'" onmouseout="this.style.background=\'transparent\'">💡 一键优化建议</button>'
      + '  <div id="ai-opt-suggestions-strand" class="mt-2.5"></div>'
      + '</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="empty-danger-lg">❌ 统计出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// ── 一键优化建议：根据当前标签页检测数据调用AI生成修改建议 ──
async function requestOptimizationSuggestions(tabName) {
  // 获取建议显示容器
  var container = document.getElementById('ai-opt-suggestions-' + tabName);
  if (!container) return;
  // 防止重复点击
  if (container.dataset.loading === '1') return;
  container.dataset.loading = '1';
  container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--muted);font-size:12px">⏳ AI正在分析并生成优化建议...</div>';

  try {
    // 收集当前标签页的检测数据（从面板已有的body内容中提取）
    var body = document.getElementById('ai-analysis-body');
    if (!body) { container.textContent = ''; container.dataset.loading = '0'; return; }
    // 提取面板中的文本内容（去掉HTML标签，获取纯文本数据摘要）
    var dataSummary = body.innerText || body.textContent || '';

    // 构建针对不同标签页的优化prompt
    var promptMap = {
      flavor: '你是一位资深网文编辑，专精"去AI味"。以下是当前章节的AI味检测结果（7Gate评分）。\n\n' +
        '【检测数据】\n' + dataSummary + '\n\n' +
        '请针对每项被检出的问题，给出具体可操作的修改建议。要求：\n' +
        '1. 指出原文中的问题句子或段落（如果数据中有）\n' +
        '2. 给出"建议改成xxx"的具体修改方案，而不是泛泛而谈\n' +
        '3. 每条建议包含：问题位置 → 问题描述 → 建议改法\n' +
        '4. 用简洁的列表格式输出，每条建议一行',
      style: '你是一位资深网文编辑，专精文风分析。以下是当前章节的文风指纹数据（8维分析）。\n\n' +
        '【检测数据】\n' + dataSummary + '\n\n' +
        '请基于这些文风指纹数据，给出具体可操作的文风优化建议。要求：\n' +
        '1. 针对偏离正常范围的维度（如TTR偏低、CV偏低、"的"字密度偏高等）给出修改方向\n' +
        '2. 给出"建议改成xxx"的具体句式或段落示例\n' +
        '3. 每条建议包含：维度 → 当前值 → 目标值 → 具体修改方案\n' +
        '4. 用简洁的列表格式输出',
      pull: '你是一位资深网文编辑，专精伏笔和悬念设计。以下是当前作品的伏笔引力数据（追读力4维评分）。\n\n' +
        '【检测数据】\n' + dataSummary + '\n\n' +
        '请基于这些伏笔引力数据，给出具体可操作的优化建议。要求：\n' +
        '1. 针对追读力薄弱的维度给出改进方案\n' +
        '2. 给出"建议在下一章加入xxx悬念"或"建议将xxx伏笔提前回收"的具体操作\n' +
        '3. 如果有警告项，优先处理\n' +
        '4. 用简洁的列表格式输出，每条建议一行',
      strand: '你是一位资深网文编辑，专精三线织法（Quest主线/Fire爽点线/Constellation设定线）。以下是当前作品的线程分布数据。\n\n' +
        '【检测数据】\n' + dataSummary + '\n\n' +
        '请基于这些线程分布数据，给出具体可操作的调整建议。要求：\n' +
        '1. 针对偏离目标比例的线程给出调整方案\n' +
        '2. 如有红线告警，给出紧急处理方案\n' +
        '3. 给出"建议在第x章切换到xxx线"或"建议在xxx章加入Fire爽点"的具体操作\n' +
        '4. 用简洁的列表格式输出，每条建议一行'
    };

    var prompt = promptMap[tabName] || promptMap.flavor;
    var r = await api('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({messages: [{role: 'user', content: prompt}]})
    });

    if (!r.ok || !r.content) {
      container.innerHTML = '<div style="padding:10px 12px;background:var(--bg);border:1px solid var(--danger, #ef4444);border-radius:var(--radius-sm);font-size:12px;color:var(--danger, #ef4444)">❌ 获取优化建议失败: ' + (r.error || 'AI无响应').replace(/</g, '&lt;') + '</div>';
      container.dataset.loading = '0';
      return;
    }

    // 将AI返回的建议内容格式化显示
    var suggestions = r.content.trim();
    // 将换行转为HTML换行，将**加粗**转为<b>标签
    suggestions = suggestions.replace(/</g, '&lt;').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
    container.innerHTML = ''
      + '<div style="padding:12px;background:var(--surface);border:1px solid var(--accent);border-radius:var(--radius-sm);font-size:12px;line-height:1.7">'
      + '  <div style="font-size:11px;font-weight:600;color:var(--accent);margin-bottom:8px">🎯 AI优化建议</div>'
      + '  <div class="text-ink">' + suggestions + '</div>'
      + '</div>';
  } catch (e) {
    container.innerHTML = '<div style="padding:10px 12px;background:var(--bg);border:1px solid var(--danger, #ef4444);border-radius:var(--radius-sm);font-size:12px;color:var(--danger, #ef4444)">❌ 请求出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
  container.dataset.loading = '0';
}

// ── 快速模式：简化创建+一键生成全部章节 ──
function openQuickModePanel() {
  var dd = document.getElementById('toolbox-dropdown');
  if (dd) dd.style.display = 'none';
  if (!document.getElementById('quick-mode-overlay')) {
    var overlay = document.createElement('div');
    overlay.id = 'quick-mode-overlay';
    overlay.className = 'overlay-backdrop';
    overlay.style.cssText = 'display:flex;z-index:1200';
    overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1201;width:94%;max-width:480px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);overflow:hidden">'
      + '  <div class="row-between-lg">'
      + '    <div class="flex-center-sm"><span class="text-xl">⚡</span><span class="title-accent-md-xl">快速模式</span></div>'
      + '    <button onclick="closeOverlay(\'quick-mode-overlay\')" class="btn-ghost-icon-xl-alt">✕</button>'
      + '  </div>'
      + '  <div style="padding:20px 18px">'
      // 说明文字
      + '    <div style="font-size:12px;color:var(--muted);margin-bottom:16px;line-height:1.6">跳过世界观设定步骤，只需填写基本信息，AI一键生成全部章节正文。</div>'
      // 标题输入
      + '    <div style="margin-bottom:14px">'
      + '      <label class="label-muted-sm">小说标题</label>'
      + '      <input type="text" id="quick-mode-title" placeholder="输入小说标题" style="width:100%;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--ink);font-size:14px;font-family:var(--display);outline:none">'
      + '    </div>'
      // 类型选择
      + '    <div style="margin-bottom:14px">'
      + '      <label class="label-muted-sm">题材类型</label>'
      + '      <select id="quick-mode-genre" style="width:100%;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--ink);font-size:13px;font-family:var(--sans);outline:none">'
      + '        <option>玄幻</option><option selected>都市</option><option>悬疑</option><option>科幻</option>'
      + '        <option>古言</option><option>克苏鲁</option><option>赛博朋克</option><option>末世</option>'
      + '        <option>无限流</option><option>种田文</option><option>轻小说</option><option>其他</option>'
      + '      </select>'
      + '    </div>'
      // 章节数
      + '    <div style="margin-bottom:20px">'
      + '      <label class="label-muted-sm">章节数量</label>'
      + '      <input type="number" id="quick-mode-chapters" min="1" max="50" value="3" style="width:100%;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--ink);font-size:14px;font-family:var(--sans);outline:none">'
      + '      <div class="text-xs text-muted mt-1">建议3-10章，快速模式下AI将一次性生成全部章节</div>'
      + '    </div>'
      // 一键生成按钮
      + '    <button id="quick-mode-generate" onclick="executeQuickModeGenerate()" style="width:100%;padding:12px;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#fff;font-size:14px;font-weight:600;cursor:pointer;font-family:var(--sans);transition:opacity var(--motion-fast)">⚡ 一键生成</button>'
      // 进度区域
      + '    <div id="quick-mode-progress" style="margin-top:14px;display:none">'
      + '      <div style="font-size:12px;color:var(--muted);margin-bottom:6px" id="quick-mode-status">正在创建项目...</div>'
      + '      <div style="height:4px;background:var(--bg);border-radius:2px;overflow:hidden">'
      + '        <div id="quick-mode-bar" style="height:100%;width:0%;background:var(--accent);transition:width 0.3s"></div>'
      + '      </div>'
      + '    </div>'
      // 结果提示
      + '    <div id="quick-mode-result" class="mt-2.5"></div>'
      + '  </div>'
      + '</div>';
    document.body.appendChild(overlay);
    // 回车触发生成
    document.getElementById('quick-mode-title').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') executeQuickModeGenerate();
    });
  } else {
    document.getElementById('quick-mode-overlay').style.display = 'flex';
  }
  // 自动聚焦标题输入框
  setTimeout(function() {
    var ti = document.getElementById('quick-mode-title');
    if (ti) ti.focus();
  }, 100);
}

// 快速模式：一键生成执行逻辑
async function executeQuickModeGenerate() {
  var titleEl = document.getElementById('quick-mode-title');
  var genreEl = document.getElementById('quick-mode-genre');
  var chaptersEl = document.getElementById('quick-mode-chapters');
  var progressEl = document.getElementById('quick-mode-progress');
  var statusEl = document.getElementById('quick-mode-status');
  var barEl = document.getElementById('quick-mode-bar');
  var resultEl = document.getElementById('quick-mode-result');
  var btnEl = document.getElementById('quick-mode-generate');

  var title = titleEl ? titleEl.value.trim() : '';
  var genre = genreEl ? genreEl.value : '都市';
  var chapterCount = chaptersEl ? parseInt(chaptersEl.value, 10) || 3 : 3;
  if (chapterCount < 1) chapterCount = 1;
  if (chapterCount > 50) chapterCount = 50;

  if (!title) {
    showToast('请输入小说标题');
    if (titleEl) titleEl.focus();
    return;
  }

  // 禁用按钮，显示进度
  if (btnEl) { btnEl.disabled = true; btnEl.style.opacity = '0.6'; btnEl.textContent = '⏳ 生成中...'; }
  if (progressEl) progressEl.style.display = 'block';
  if (resultEl) resultEl.textContent = '';
  if (barEl) barEl.style.width = '0%';

  try {
    // 步骤1：创建项目
    if (statusEl) statusEl.textContent = '正在创建项目...';
    var r = await newProject(title, genre, chapterCount);
    if (!r.ok) {
      if (statusEl) statusEl.textContent = '创建失败: ' + (r.error || '未知错误');
      if (resultEl) resultEl.innerHTML = '<div style="padding:8px;color:var(--danger);font-size:12px">❌ ' + (r.error || '创建失败') + '</div>';
      if (btnEl) { btnEl.disabled = false; btnEl.style.opacity = '1'; btnEl.textContent = '⚡ 一键生成'; }
      return;
    }
    if (barEl) barEl.style.width = '10%';

    // 步骤2：添加章节
    if (statusEl) statusEl.textContent = '正在创建' + chapterCount + '个章节...';
    for (var i = 1; i <= chapterCount; i++) {
      await addChapter('第' + i + '章');
      if (barEl) barEl.style.width = (10 + Math.round(i / chapterCount * 20)) + '%';
    }

    // 步骤3：重新加载数据
    if (statusEl) statusEl.textContent = '正在加载数据...';
    if (barEl) barEl.style.width = '35%';
    // 清空旧数据并更新界面
    worldSettings = [];
    novelActs = [];
    chOutline = [];
    chapters = [];
    currentChapterIndex = 0;
    currentProject = { title: title, genre: genre, chapters: [], created: new Date().toLocaleString('zh-CN', { hour12: false }) };
    document.getElementById('project-name').textContent = title;
    document.getElementById('editor-title').textContent = '第1章';
    document.getElementById('current-chapter-label').textContent = '第1章';
    document.getElementById('editor-content').innerHTML = '<p></p>';
    document.getElementById('word-count').textContent = '0';
    await reloadAllProjectData(true);
    if (barEl) barEl.style.width = '40%';

    // 步骤4：调用AI一次性生成全部章节
    if (statusEl) statusEl.textContent = 'AI正在生成全部章节（共' + chapterCount + '章）...';
    var genR = await api('/api/generate/all-chapters', { method: 'POST' });
    if (barEl) barEl.style.width = '90%';

    if (!genR || !genR.ok) {
      if (statusEl) statusEl.textContent = '生成完成（部分章节可能生成失败）';
      if (resultEl) resultEl.innerHTML = '<div style="padding:8px;color:var(--warn);font-size:12px">⚠️ 生成完成，但部分章节可能失败: ' + ((genR && genR.error) || '请检查章节内容') + '</div>';
    } else {
      if (statusEl) statusEl.textContent = '全部章节生成完成！';
      if (resultEl) resultEl.innerHTML = '<div style="padding:8px;color:var(--success, #10b981);font-size:12px">✅ 全部' + chapterCount + '章已生成完成！</div>';
    }

    // 步骤5：刷新章节列表
    await reloadAllProjectData(false);
    if (barEl) barEl.style.width = '100%';

    // 步骤6：关闭弹窗，跳转到写作步骤
    setTimeout(function() {
      closeOverlay('quick-mode-overlay');
      if (typeof goToStep === 'function') goToStep(STEPS.分卷);
      // 加载第一章
      if (typeof selectChapter === 'function') selectChapter(0);
    }, 800);

  } catch (e) {
    if (statusEl) statusEl.textContent = '出错: ' + (e.message || '');
    if (resultEl) resultEl.innerHTML = '<div style="padding:8px;color:var(--danger);font-size:12px">❌ 出错: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
    if (btnEl) { btnEl.disabled = false; btnEl.style.opacity = '1'; btnEl.textContent = '⚡ 一键生成'; }
  }
}

// ── 新手引导弹窗：新项目首次进入步骤1时显示 ──
function showWelcomeGuide() {
  // 检查是否已设置"不再显示"
  if (localStorage.getItem('shuzhai_welcome_guide_dismissed') === '1') return;
  // 如果已存在则不重复显示
  if (document.getElementById('welcome-guide-overlay')) return;

  var overlay = document.createElement('div');
  overlay.id = 'welcome-guide-overlay';
  overlay.className = 'overlay-backdrop';
  overlay.style.cssText = 'display:flex;z-index:1300';
  overlay.innerHTML = ''
      + '<div style="position:relative;z-index:1301;width:94%;max-width:460px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:0 12px 48px rgba(0,0,0,0.5);overflow:hidden">'
    // 标题栏
    + '  <div style="padding:20px 20px 0;text-align:center">'
    + '    <div style="font-size:28px;margin-bottom:8px">📖</div>'
    + '    <div style="font-size:18px;font-weight:700;color:var(--accent)">欢迎使用书斋！</div>'
    + '    <div style="font-size:12px;color:var(--muted);margin-top:6px">AI驱动的网文创作工作台</div>'
    + '  </div>'
    // 工作流说明
    + '  <div style="padding:16px 20px">'
    + '    <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px">写作工作流</div>'
    + '    <div class="flex-col-md">'
    // 步骤1
    + '      <div class="card-flex-sm">'
    + '        <div class="circle-accent">1</div>'
    + '        <div><div class="title-semibold-md-alt">设定世界观</div><div class="text-xs text-muted">搭建故事舞台、设定规则</div></div>'
    + '      </div>'
    // 步骤2
    + '      <div class="card-flex-sm">'
    + '        <div class="circle-accent">2</div>'
    + '        <div><div class="title-semibold-md-alt">生成大纲</div><div class="text-xs text-muted">AI辅助规划故事走向</div></div>'
    + '      </div>'
    // 步骤3
    + '      <div class="card-flex-sm">'
    + '        <div class="circle-accent">3</div>'
    + '        <div><div class="title-semibold-md-alt">创建人物</div><div class="text-xs text-muted">设定角色性格、关系</div></div>'
    + '      </div>'
    // 步骤4
    + '      <div class="card-flex-sm">'
    + '        <div class="circle-accent">4</div>'
    + '        <div><div class="title-semibold-md-alt">章节大纲</div><div class="text-xs text-muted">逐章细化剧情蓝图</div></div>'
    + '      </div>'
    // 步骤5
    + '      <div class="card-flex-sm">'
    + '        <div class="circle-accent">5</div>'
    + '        <div><div class="title-semibold-md-alt">写正文</div><div class="text-xs text-muted">AI生成 + 人工精修</div></div>'
    + '      </div>'
    + '    </div>'
    // 提示信息
    + '    <div style="margin-top:12px;padding:10px 12px;background:var(--bg);border:1px solid var(--border-soft);border-radius:var(--radius-sm);font-size:11px;color:var(--muted);line-height:1.6">'
    + '      每步都有守门保护，不用担心跳步。<br>'
    + '      高级功能：检查 / 蒸馏 / 诊断 / 伏笔管理<br>'
    + '      技能包面板提供28+个写作技巧模板'
    + '    </div>'
    + '  </div>'
    // 底部按钮
    + '  <div style="padding:0 20px 20px;display:flex;gap:10px">'
    + '    <button onclick="dismissWelcomeGuide(true)" style="flex:1;padding:10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--muted);font-size:12px;cursor:pointer;font-family:var(--sans)">不再显示</button>'
    + '    <button onclick="dismissWelcomeGuide(false)" style="flex:1;padding:10px;border:none;border-radius:var(--radius-sm);background:var(--accent);color:#fff;font-size:12px;font-weight:600;cursor:pointer;font-family:var(--sans)">开始创作</button>'
    + '  </div>'
    + '</div>';
  document.body.appendChild(overlay);
}

// 关闭新手引导弹窗
// permanent: true=不再显示, false=本次关闭
function dismissWelcomeGuide(permanent) {
  if (permanent) {
    localStorage.setItem('shuzhai_welcome_guide_dismissed', '1');
  }
  var overlay = document.getElementById('welcome-guide-overlay');
  if (overlay) {
    overlay.style.display = 'none';
    overlay.remove();
  }
}

