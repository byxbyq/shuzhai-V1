(function() {
  'use strict';


// ══ 结构化世界观字段 ══
var worldMeta = { narrative_style: {}, era: {}, world_rules: [] };

window.loadWorldMeta = function(data) {
  worldMeta.narrative_style = (data && data.narrative_style) || {};
  worldMeta.era = (data && data.era) || {};
  worldMeta.world_rules = (data && data.world_rules) || [];
  renderWorldMeta();
}

window.renderWorldMeta = function() {
  var ns = worldMeta.narrative_style;
  var era = worldMeta.era;
  // 填充叙事风格
  if (document.getElementById('ns-pov')) document.getElementById('ns-pov').value = ns.pov || '';
  if (document.getElementById('ns-tense')) document.getElementById('ns-tense').value = ns.tense || '';
  if (document.getElementById('ns-tone')) document.getElementById('ns-tone').value = ns.tone || '';
  if (document.getElementById('ns-pacing')) document.getElementById('ns-pacing').value = ns.pacing || '';
  if (document.getElementById('ns-description')) document.getElementById('ns-description').value = ns.description_style || '';
  // 填充时代环境
  if (document.getElementById('era-tech')) document.getElementById('era-tech').value = era.tech_level || '';
  if (document.getElementById('era-society')) document.getElementById('era-society').value = era.society || '';
  if (document.getElementById('era-geography')) document.getElementById('era-geography').value = era.geography || '';
  if (document.getElementById('era-culture')) document.getElementById('era-culture').value = era.culture || '';
  if (document.getElementById('era-social-attitude')) document.getElementById('era-social-attitude').value = era.social_attitude || '';
  // 渲染世界规则列表
  renderWorldRules();
}

window.renderWorldRules = function() {
  var list = document.getElementById('world-rules-list');
  if (!list) return;
  list.innerHTML = '';
  if (!worldMeta.world_rules || worldMeta.world_rules.length === 0) {
    list.innerHTML = '<div class="label-muted-inline-sm" >暂无世界规则，点击添加</div>';
    return;
  }
  worldMeta.world_rules.forEach(function(rule, i) {
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:4px;align-items:center';
    row.innerHTML = '<input type="text" value="' + escapeHtml(rule) + '" onchange="updateWorldRule(' + i + ', this.value)" style="flex:1;padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--ink)">' +
      '<button onclick="removeWorldRule(' + i + ')" style="padding:4px 6px;border:1px solid #e74c3c;color:#e74c3c;background:transparent;border-radius:4px;cursor:pointer;font-size:11px">✕</button>';
    list.appendChild(row);
  });
}

window.addWorldRule = function() {
  if (!worldMeta.world_rules) worldMeta.world_rules = [];
  worldMeta.world_rules.push('新规则');
  renderWorldRules();
  saveWorldMeta();
}

window.updateWorldRule = function(i, val) {
  worldMeta.world_rules[i] = val;
  saveWorldMeta();
}

window.removeWorldRule = function(i) {
  worldMeta.world_rules.splice(i, 1);
  renderWorldRules();
  saveWorldMeta();
}

window.saveWorldMeta = async function(opts) {
  opts = opts || {};
  // 从UI收集值
  var ns = {
    pov: val('ns-pov'), tense: val('ns-tense'), tone: val('ns-tone'),
    pacing: val('ns-pacing'), description_style: val('ns-description')
  };
  var era = {
    tech_level: val('era-tech'), society: val('era-society'),
    geography: val('era-geography'), culture: val('era-culture'),
    social_attitude: val('era-social-attitude')
  };
  worldMeta.narrative_style = ns;
  worldMeta.era = era;
  // 保存到后端（只发送结构化字段，不碰 world_settings，避免时序问题覆盖设定）
  try {
    var payload = {
      narrative_style: ns,
      era: era,
      world_rules: worldMeta.world_rules
    };
    // 仅在显式传入 includeWorldSettings 时才发送 world_settings
    if (opts.includeWorldSettings === true && typeof worldSettings !== 'undefined' && Array.isArray(worldSettings)) {
      var d = {};
      worldSettings.forEach(function(s) { if (s && s.key) d[s.key] = s.val || ''; });
      payload.world_settings = d;
    }
    await api('/api/project/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
  } catch(e) { console.warn('saveWorldMeta failed:', e); }
}

})();