// 扫榜分析面板 JavaScript（多平台版）

var _platformConfig = null;

function openRankingPanel() {
  var overlay = document.getElementById('ranking-overlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  loadPlatformConfig();
  loadRankingData();
}

async function loadPlatformConfig() {
  if (_platformConfig) return _platformConfig;
  try {
    var resp = await fetch('/api/ranking/platforms');
    var data = await resp.json();
    if (data && data.platforms) {
      _platformConfig = data.platforms;
      updatePlatformSelectors('qidian');
    }
  } catch(e) {
    console.warn('加载平台配置失败', e);
  }
  return _platformConfig;
}

function updatePlatformSelectors(platform) {
  if (!_platformConfig || !_platformConfig[platform]) return;
  var config = _platformConfig[platform];

  var typeSelect = document.getElementById('ranking-type-select');
  if (typeSelect && config.rank_types) {
    typeSelect.textContent = '';
    for (var key in config.rank_types) {
      if (config.rank_types.hasOwnProperty(key)) {
        var opt = document.createElement('option');
        opt.value = key;
        opt.textContent = config.rank_types[key];
        typeSelect.appendChild(opt);
      }
    }
  }

  var catSelect = document.getElementById('ranking-category-select');
  if (catSelect && config.categories) {
    catSelect.textContent = '';
    for (var key in config.categories) {
      if (config.categories.hasOwnProperty(key)) {
        var opt2 = document.createElement('option');
        opt2.value = key;
        opt2.textContent = config.categories[key];
        catSelect.appendChild(opt2);
      }
    }
  }
}

function onPlatformChange() {
  var platform = document.getElementById('ranking-platform-select').value;
  updatePlatformSelectors(platform);
  loadRankingList();
  loadRankingGenreChart();
  loadRankingTrends();
}

async function loadRankingData() {
  await loadPlatformConfig();
  await Promise.all([
    loadRankingGenreChart(),
    loadRankingTrends(),
    loadRankingList(),
  ]);
}

function getCurrentPlatform() {
  var el = document.getElementById('ranking-platform-select');
  return el ? el.value : 'qidian';
}

function getCurrentRankType() {
  var el = document.getElementById('ranking-type-select');
  return el ? el.value : 'hot';
}

function getCurrentCategory() {
  var el = document.getElementById('ranking-category-select');
  return el ? el.value : 'all';
}

function showSourceInfo(data) {
  var el = document.getElementById('ranking-source-info');
  if (!el) return;
  if (!data || !data.source) {
    el.style.display = 'none';
    return;
  }
  var sourceLabels = {
    'live': '🟢 实时数据',
    'cache': '🟡 缓存数据',
    'fallback': '🔴 内置参考数据'
  };
  var sourceText = sourceLabels[data.source] || data.source;
  var timeText = data.scanned_at ? ' · ' + data.scanned_at : '';
  var noteText = data.note ? ' · ' + data.note : '';
  el.innerHTML = sourceText + timeText + noteText;
  el.style.display = 'block';
}

async function loadRankingGenreChart() {
  var el = document.getElementById('ranking-genre-chart');
  if (!el) return;
  el.innerHTML = '<div class="empty-state-md">加载中...</div>';

  var platform = getCurrentPlatform();
  try {
    var resp = await fetch('/api/ranking/trends?days=7&platform=' + encodeURIComponent(platform));
    var data = await resp.json();
    if (!data.ok || !data.genre_analysis) {
      el.innerHTML = '<div class="empty-state-md">暂无数据</div>';
      return;
    }

    var genres = data.genre_analysis;
    var sorted = Object.entries(genres).sort(function(a, b) { return b[1].popularity - a[1].popularity; });

    var maxPop = sorted.length > 0 ? sorted[0][1].popularity : 100;
    var colors = ['#e74c3c', '#e67e22', '#f39c12', '#2ecc71', '#1abc9c', '#3498db', '#9b59b6', '#34495e', '#e91e63', '#00bcd4', '#ff5722', '#795548', '#607d8b', '#4caf50'];

    var html = '';
    for (var i = 0; i < sorted.length; i++) {
      var genre = sorted[i][0];
      var info = sorted[i][1];
      var height = Math.max(20, (info.popularity / maxPop) * 140);
      var color = colors[i % colors.length];
      var trendIcon = info.trend === 'rising' ? '\u25B2' : info.trend === 'declining' ? '\u25BC' : '\u2500';
      var trendColor = info.trend === 'rising' ? '#2ecc71' : info.trend === 'declining' ? '#e74c3c' : '#95a5a6';
      html += '<div style="display:flex;flex-direction:column;align-items:center;min-width:55px">';
      html += '<span style="font-size:11px;font-weight:600;margin-bottom:4px">' + info.popularity + '</span>';
      html += '<div style="width:32px;height:' + height + 'px;background:' + color + ';border-radius:4px 4px 0 0;transition:height 0.3s"></div>';
      html += '<span style="font-size:10px;margin-top:4px;color:var(--ink)">' + genre + '</span>';
      html += '<span style="font-size:9px;color:' + trendColor + '">' + trendIcon + '</span>';
      html += '</div>';
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="empty-state-md">加载失败</div>';
  }
}

async function loadRankingTrends() {
  var el = document.getElementById('ranking-trends');
  if (!el) return;
  el.innerHTML = '<div class="empty-state-md">加载中...</div>';

  var platform = getCurrentPlatform();
  try {
    var resp = await fetch('/api/ranking/trends?days=14&platform=' + encodeURIComponent(platform));
    var data = await resp.json();
    if (!data.ok || !data.trends || data.trends.length === 0) {
      el.innerHTML = '<div class="empty-state-md">暂无趋势数据</div>';
      return;
    }

    var trends = data.trends;
    var topGenres = ['玄幻', '都市', '仙侠', '科幻', '轻小说'];
    var colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6'];

    var html = '<div style="font-size:12px;color:var(--muted);margin-bottom:8px">近14天热度趋势</div>';
    html += '<div style="display:flex;gap:4px;align-items:flex-end;min-height:100px">';

    var recentTrends = trends.slice(-7);
    for (var i = 0; i < recentTrends.length; i++) {
      var t = recentTrends[i];
      var dateLabel = t.date ? t.date.slice(5) : '';
      html += '<div style="flex:1;display:flex;flex-direction:column;align-items:center;min-width:30px">';
      html += '<div style="display:flex;gap:1px;align-items:flex-end;height:80px">';
      for (var j = 0; j < topGenres.length; j++) {
        var g = topGenres[j];
        var val = t[g] || 0;
        var h = Math.max(2, (val / 100) * 80);
        html += '<div style="width:5px;height:' + h + 'px;background:' + colors[j] + ';border-radius:1px 1px 0 0;opacity:0.8" title="' + g + ': ' + val + '"></div>';
      }
      html += '</div>';
      html += '<span style="font-size:8px;color:var(--muted);margin-top:2px;writing-mode:vertical-rl">' + dateLabel + '</span>';
      html += '</div>';
    }
    html += '</div>';

    html += '<div style="display:flex;gap:12px;margin-top:8px;flex-wrap:wrap">';
    for (var k = 0; k < topGenres.length; k++) {
      html += '<span style="font-size:10px;display:flex;align-items:center;gap:3px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + colors[k] + '"></span>' + topGenres[k] + '</span>';
    }
    html += '</div>';

    if (data.note) {
      html += '<div style="font-size:10px;color:var(--muted);margin-top:8px">' + data.note + '</div>';
    }

    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="empty-state-md">加载失败</div>';
  }
}

async function loadRankingList() {
  var el = document.getElementById('ranking-list');
  var titleEl = document.getElementById('ranking-list-title');
  if (!el) return;
  el.innerHTML = '<div class="empty-state-md">加载中...</div>';

  var platform = getCurrentPlatform();
  var rankType = getCurrentRankType();
  var category = getCurrentCategory();

  try {
    var url = '/api/ranking/scan?platform=' + encodeURIComponent(platform)
              + '&rank_type=' + encodeURIComponent(rankType)
              + '&category=' + encodeURIComponent(category);
    var resp = await fetch(url);
    var data = await resp.json();
    if (!data.ok || !data.data || data.data.length === 0) {
      el.innerHTML = '<div class="empty-state-md">暂无榜单数据</div>';
      return;
    }

    showSourceInfo(data);

    if (titleEl) {
      var pfName = data.platform_name || platform;
      var rtName = data.rank_type_name || rankType;
      titleEl.textContent = '🏆 ' + pfName + ' · ' + rtName + ' TOP ' + Math.min(data.total, 20);
    }

    var rankColors = {1: '#FFD700', 2: '#C0C0C0', 3: '#CD7F32'};
    var html = '<table style="width:100%;font-size:12px;border-collapse:collapse">';
    html += '<tr style="border-bottom:1px solid var(--border);color:var(--muted);font-size:11px"><th style="padding:6px 8px;text-align:left;width:40px">#</th><th class="p-1.5 text-left">书名</th><th class="p-1.5 text-left">作者</th><th class="p-1.5 text-left">题材</th><th style="padding:6px 8px;text-align:right">热度</th></tr>';

    for (var i = 0; i < Math.min(data.data.length, 20); i++) {
      var book = data.data[i];
      var rank = book.rank || (i + 1);
      var rankStyle = rank <= 3 ? 'color:' + (rankColors[rank] || 'var(--ink)') + ';font-weight:700' : '';
      html += '<tr style="border-bottom:1px solid var(--border-soft)">';
      html += '<td style="padding:6px 8px;' + rankStyle + '">' + rank + '</td>';
      html += '<td style="padding:6px 8px">' + (book.title || '') + '</td>';
      html += '<td style="padding:6px 8px;color:var(--muted)">' + (book.author || '') + '</td>';
      html += '<td style="padding:6px 8px"><span style="background:var(--bg);padding:1px 6px;border-radius:10px;font-size:10px">' + (book.genre || '') + '</span></td>';
      html += '<td style="padding:6px 8px;text-align:right">' + (book.popularity || '') + '</td>';
      html += '</tr>';
    }
    html += '</table>';
    if (data.note) {
      html += '<div style="font-size:10px;color:var(--muted);margin-top:8px">' + data.note + '</div>';
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="empty-state-md">加载失败</div>';
  }
}

async function loadRankingSuggestions() {
  var el = document.getElementById('ranking-suggestions');
  if (!el) return;

  var genre = document.getElementById('ranking-genre-select').value;
  if (!genre) {
    el.innerHTML = '<div class="empty-state-xs">选择题材后显示创作建议</div>';
    return;
  }

  el.innerHTML = '<div class="empty-state-xs">加载中...</div>';

  var platform = getCurrentPlatform();
  try {
    var resp = await fetch('/api/ranking/suggestions?genre=' + encodeURIComponent(genre) + '&platform=' + encodeURIComponent(platform));
    var data = await resp.json();
    if (!data.ok || !data.suggestions) {
      el.innerHTML = '<div class="empty-state-xs">暂无建议</div>';
      return;
    }

    var html = '';
    if (data.market && data.market.popularity) {
      var ctx = data.market;
      var trendLabel = ctx.trend === 'rising' ? '\u2191上升' : ctx.trend === 'declining' ? '\u2193下降' : '\u2192平稳';
      var compLabel = ctx.competition === 'intense' ? '激烈' : ctx.competition === 'moderate' ? '适中' : '较低';
      html += '<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">';
      html += '<span class="badge-accent-xs">热度: ' + ctx.popularity + '</span>';
      html += '<span class="badge-accent-xs">趋势: ' + trendLabel + '</span>';
      html += '<span class="badge-accent-xs">竞争: ' + compLabel + '</span>';
      html += '<span class="badge-accent-xs">均读者: ' + (ctx.avg_readers || 0).toLocaleString() + '</span>';
      html += '</div>';
    }

    html += '<ul style="margin:0;padding-left:18px;line-height:1.8">';
    for (var i = 0; i < data.suggestions.length; i++) {
      html += '<li style="font-size:12px;margin-bottom:4px">' + data.suggestions[i] + '</li>';
    }
    html += '</ul>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="empty-state-xs">加载失败</div>';
  }
}

async function refreshRanking() {
  loadRankingData();
  var genre = document.getElementById('ranking-genre-select').value;
  if (genre) loadRankingSuggestions();
}
