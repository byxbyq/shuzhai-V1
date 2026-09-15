(function() {
  'use strict';


window.aiGenerateNarrativeStyle = async function() {
  var btn = document.getElementById('btn-ai-gen-narrative');
  if (!btn) return;
  btn.disabled = true; var oldTxt = btn.textContent; btn.textContent = '生成中…';
  try {
    var projGenre = (typeof currentProject !== 'undefined' && currentProject && currentProject.genre) ? currentProject.genre : '小说';
    // 收集已有世界观作为生成上下文
    var worldCtx = '';
    if (typeof worldSettings !== 'undefined' && Array.isArray(worldSettings)) {
      var wItems = worldSettings.filter(function(s) { return s && s.group === '世界观' && s.val; });
      if (wItems.length > 0) {
        worldCtx = '\n参考已有世界观设定：\n' + wItems.slice(0, 30).map(function(s) { return '- ' + s.key + '：' + s.val; }).join('\n');
      }
    }
    var prompt = '请为一部' + projGenre + '小说生成【叙事风格】5项设定，JSON格式返回：{"pov":"视角（选填：第三人称限知/第三人称全知/第一人称/多视角，不匹配可自定义）","tense":"时态（选填：过去时/现在时）","tone":"基调（选填：冷峻/热血/诙谐/沉重/悲壮/轻松，不匹配可自定义）","pacing":"节奏（选填：快节奏/慢热/张弛有度，不匹配可自定义）","description_style":"描写风格（如白描/华丽/意识流/散文式…可自定义）"}。只返回JSON不要解释。' + worldCtx;
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (r && r.ok && r.content) {
      var keyMap = {'视角':'pov','叙事视角':'pov','pov':'pov','时态':'tense','tense':'tense','基调':'tone','语气':'tone','tone':'tone','节奏':'pacing','叙事节奏':'pacing','pacing':'pacing','描写风格':'description_style','描写':'description_style','description_style':'description_style','description':'description_style'};
      var kv = _parseAIKeyValue(r.content, keyMap);
      // 应用到DOM
      if (kv.pov) { var p = document.getElementById('ns-pov'); if (p) { var optExists = false; for (var oi=0;oi<p.options.length;oi++){if(p.options[oi].value===kv.pov){optExists=true;break;}} if (!optExists) { var no = document.createElement('option'); no.value = kv.pov; no.textContent = kv.pov; p.appendChild(no); } p.value = kv.pov; } }
      if (kv.tense) { var t = document.getElementById('ns-tense'); if (t) { var oe2 = false; for (var oi2=0;oi2<t.options.length;oi2++){if(t.options[oi2].value===kv.tense){oe2=true;break;}} if (!oe2) { var no2 = document.createElement('option'); no2.value = kv.tense; no2.textContent = kv.tense; t.appendChild(no2); } t.value = kv.tense; } }
      if (kv.tone) { var to = document.getElementById('ns-tone'); if (to) { var oe3 = false; for (var oi3=0;oi3<to.options.length;oi3++){if(to.options[oi3].value===kv.tone){oe3=true;break;}} if (!oe3) { var no3 = document.createElement('option'); no3.value = kv.tone; no3.textContent = kv.tone; to.appendChild(no3); } to.value = kv.tone; } }
      if (kv.pacing) { var pa = document.getElementById('ns-pacing'); if (pa) { var oe4 = false; for (var oi4=0;oi4<pa.options.length;oi4++){if(pa.options[oi4].value===kv.pacing){oe4=true;break;}} if (!oe4) { var no4 = document.createElement('option'); no4.value = kv.pacing; no4.textContent = kv.pacing; pa.appendChild(no4); } pa.value = kv.pacing; } }
      if (kv.description_style) { var d = document.getElementById('ns-description'); if (d) d.value = kv.description_style; }
      await saveWorldMeta();
      showToast('✅ 叙事风格已生成并保存');
    } else {
      showToast('生成失败' + (r && r.error ? '：' + r.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  btn.disabled = false; btn.textContent = oldTxt;
}

window.aiGenerateEra = async function() {
  var btn = document.getElementById('btn-ai-gen-era');
  if (!btn) return;
  btn.disabled = true; var oldTxt = btn.textContent; btn.textContent = '生成中…';
  try {
    var projGenre = (typeof currentProject !== 'undefined' && currentProject && currentProject.genre) ? currentProject.genre : '小说';
    // 收集已有世界观作为生成上下文
    var worldCtx = '';
    if (typeof worldSettings !== 'undefined' && Array.isArray(worldSettings)) {
      var wItems = worldSettings.filter(function(s) { return s && s.group === '世界观' && s.val; });
      if (wItems.length > 0) {
        worldCtx = '\n参考已有世界观设定：\n' + wItems.slice(0, 30).map(function(s) { return '- ' + s.key + '：' + s.val; }).join('\n');
      }
    }
    // 也参考叙事风格（如果已有）
    if (worldMeta && worldMeta.narrative_style) {
      var ns = worldMeta.narrative_style;
      var nsKeys = Object.keys(ns).filter(function(k){return ns[k];});
      if (nsKeys.length > 0) {
        worldCtx += '\n参考叙事风格：' + nsKeys.map(function(k){return k+':'+ns[k];}).join('，');
      }
    }
    var prompt = '请为一部' + projGenre + '小说生成【时代环境】5项设定，JSON格式返回：{"tech_level":"科技水平（如：冷兵器/蒸汽朋克/赛博朋克/现代都市/修仙灵气…）","society":"社会制度（如：封建帝制/联邦共和/部落联盟/宗门林立…）","geography":"地理特征（如：单一大陆+群岛/地下城+地表/多星系…）","culture":"文化背景（如：儒家礼教+仙道/赛博+街头文化…）","social_attitude":"社会态度（对核心设定元素的态度：崇拜/恐惧/严格管控/猎杀/漠视…）"}。只返回JSON不要解释。' + worldCtx;
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (!r || !r.ok || !r.content) {
      // fallback to /ai/chat (兼容性保留)
      r = await api('/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    }
    if (r && r.ok && r.content) {
      var keyMap = {'科技水平':'tech_level','科技':'tech_level','tech_level':'tech_level','tech':'tech_level','社会制度':'society','制度':'society','society':'society','社会形态':'society','地理特征':'geography','地理':'geography','geography':'geography','文化背景':'culture','文化':'culture','culture':'culture','社会态度':'social_attitude','民众态度':'social_attitude','social_attitude':'social_attitude','attitude':'social_attitude'};
      var kv = _parseAIKeyValue(r.content, keyMap);
      if (kv.tech_level) { var x = document.getElementById('era-tech'); if (x) x.value = kv.tech_level; }
      if (kv.society) { var x = document.getElementById('era-society'); if (x) x.value = kv.society; }
      if (kv.geography) { var x = document.getElementById('era-geography'); if (x) x.value = kv.geography; }
      if (kv.culture) { var x = document.getElementById('era-culture'); if (x) x.value = kv.culture; }
      if (kv.social_attitude) { var x = document.getElementById('era-social-attitude'); if (x) x.value = kv.social_attitude; }
      await saveWorldMeta();
      showToast('✅ 时代环境已生成并保存');
    } else {
      showToast('生成失败' + (r && r.error ? '：' + r.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  btn.disabled = false; btn.textContent = oldTxt;
}

window.applyWorldCore9FieldsToSettings = function(obj) {
  // 把9字段JSON：1) 写入 worldSettings 自由设定列表；2) 智能映射填充到叙事风格+时代环境结构化字段
  if (!obj || typeof obj !== 'object') return 0;
  if (typeof worldSettings === 'undefined') worldSettings = [];
  // ── 第一部分：写入 worldSettings 自由设定列表（重复key覆盖） ──
  // ★ 重要：同时写入 中文label版 + 英文9字段版，确保UI显示和后端检查都通过
  var existingIdx = {};
  for (var i = 0; i < worldSettings.length; i++) {
    var s = worldSettings[i];
    if (s && s.group === '世界观' && s.key) existingIdx[s.key] = i;
  }
  var filled = 0;
  var knownWorld9 = ['core_setting','era_background','overall_style','atmosphere','main_roles_overview','other_settings','perspective_rules','sensory_limits','visual_style'];
  for (var key in obj) {
    if (obj.hasOwnProperty(key) && obj[key]) {
      var label = _labelOfWorldFieldKey(key);
      var val = String(obj[key]).trim();
      if (!val) continue;
      // A) 写中文label版（用于UI显示和自由设定列表）
      if (existingIdx.hasOwnProperty(label)) {
        worldSettings[existingIdx[label]].val = val;
      } else {
        worldSettings.push({key: label, val: val, group: '世界观'});
        existingIdx[label] = worldSettings.length - 1;
      }
      // B) 写英文字段名版（仅当key本身就是9字段之一时，确保后端workflow-step-status能检测到）
      if (knownWorld9.indexOf(key) >= 0 && existingIdx.hasOwnProperty(key) === false) {
        worldSettings.push({key: key, val: val, group: '世界观'});
        existingIdx[key] = worldSettings.length - 1;
      } else if (knownWorld9.indexOf(key) >= 0 && existingIdx.hasOwnProperty(key)) {
        worldSettings[existingIdx[key]].val = val;
      }
      filled++;
    }
  }
  // ── 第二部分：智能映射 → 叙事风格结构化字段（ns-*） ──
  var perspectiveText = obj.perspective_rules ? String(obj.perspective_rules) : '';
  var overallText = obj.overall_style ? String(obj.overall_style) : '';
  var sensoryText = obj.sensory_limits ? String(obj.sensory_limits) : '';
  var visualText = obj.visual_style ? String(obj.visual_style) : '';
  var atmosText = obj.atmosphere ? String(obj.atmosphere) : '';
  // 视角（ns-pov）：优先从 perspective_rules 匹配关键词
  var povMap = {'第三人称限知':['第三人称限知','限知第三人称'],'第三人称全知':['第三人称全知','全知第三人称','上帝视角'],'第一人称':['第一人称','我 视角','以我叙述'],'多视角':['多视角','交替视角','POV切换']};
  function _matchFirst(text, mp) { if (!text) return ''; for (var pk in mp) { var arr = mp[pk]; for (var j=0;j<arr.length;j++){ if (text.indexOf(arr[j]) >= 0) return pk; } } return ''; }
  var povVal = _matchFirst(perspectiveText, povMap) || _matchFirst(overallText, povMap);
  if (povVal) {
    var p = document.getElementById('ns-pov');
    if (p) { var oe=false; for (var oi=0;oi<p.options.length;oi++){if(p.options[oi].value===povVal){oe=true;break;}} if (!oe){var no=document.createElement('option');no.value=povVal;no.textContent=povVal;p.appendChild(no);} p.value = povVal; }
  }
  // 时态（ns-tense）：匹配
  var tenseMap = {'过去时':['过去时','回忆式','叙述过去'],'现在时':['现在时','进行时','实时叙述']};
  var tenseVal = _matchFirst(perspectiveText, tenseMap) || _matchFirst(overallText, tenseMap);
  if (tenseVal) {
    var t = document.getElementById('ns-tense');
    if (t) { var oe2=false; for (var oi2=0;oi2<t.options.length;oi2++){if(t.options[oi2].value===tenseVal){oe2=true;break;}} if (!oe2){var no2=document.createElement('option');no2.value=tenseVal;no2.textContent=tenseVal;t.appendChild(no2);} t.value = tenseVal; }
  }
  // 基调（ns-tone）：从 atmosphere + overall_style 匹配
  var toneMap = {'冷峻':['冷峻','冷酷','清冷','冷冽','肃杀'],'热血':['热血','沸腾','燃','激昂'],'诙谐':['诙谐','幽默','搞笑','轻松戏谑'],'沉重':['沉重','压抑','喘不过气','阴郁'],'悲壮':['悲壮','惨烈','苍凉','悲怆'],'轻松':['轻松','明快','治愈','温馨','甜']};
  var toneVal = _matchFirst(atmosText, toneMap) || _matchFirst(overallText, toneMap) || _matchFirst(visualText, toneMap);
  if (toneVal) {
    var to = document.getElementById('ns-tone');
    if (to) { var oe3=false; for (var oi3=0;oi3<to.options.length;oi3++){if(to.options[oi3].value===toneVal){oe3=true;break;}} if (!oe3){var no3=document.createElement('option');no3.value=toneVal;no3.textContent=toneVal;to.appendChild(no3);} to.value = toneVal; }
  }
  // 节奏（ns-pacing）：从 overall_style 匹配
  var paceMap = {'快节奏':['快节奏','紧凑','爽文','密集'],'慢热':['慢热','铺垫','徐徐展开','循序渐进'],'张弛有度':['张弛有度','松紧结合','有张有弛','跌宕起伏']};
  var paceVal = _matchFirst(overallText, paceMap);
  if (paceVal) {
    var pa = document.getElementById('ns-pacing');
    if (pa) { var oe4=false; for (var oi4=0;oi4<pa.options.length;oi4++){if(pa.options[oi4].value===paceVal){oe4=true;break;}} if (!oe4){var no4=document.createElement('option');no4.value=paceVal;no4.textContent=paceVal;pa.appendChild(no4);} pa.value = paceVal; }
  }
  // 描写风格（ns-description）：拼接 visual_style + sensory_limits + 描写相关关键词
  var descParts = [];
  if (visualText && visualText.length < 80) descParts.push(visualText);
  else if (visualText) { var vSliced = visualText.slice(0, 60); if (visualText.length > 60) vSliced += '…'; descParts.push(vSliced); }
  if (sensoryText && sensoryText.length < 60) descParts.push(sensoryText);
  else if (sensoryText) { var sSliced = sensoryText.slice(0, 40); if (sensoryText.length > 40) sSliced += '…'; descParts.push(sSliced); }
  // 从 overall_style 提取描写风格关键词
  var descKws = ['白描','华丽','意识流','散文式','诗意','电影感','镜头感','细腻','粗犷','极简','繁复'];
  for (var k=0;k<descKws.length;k++){ if ((overallText.indexOf(descKws[k]) >=0 || atmosText.indexOf(descKws[k]) >=0) && descParts.indexOf(descKws[k])<0) descParts.unshift(descKws[k]); }
  var descVal = descParts.join(' · ');
  if (descVal) {
    var d = document.getElementById('ns-description');
    if (d) d.value = descVal.slice(0, 120);
  }
  // ── 第三部分：智能映射 → 时代环境结构化字段（era-*） ──
  var eraText = obj.era_background ? String(obj.era_background) : '';
  var coreText = obj.core_setting ? String(obj.core_setting) : '';
  // era-tech 科技水平：匹配关键词
  var techKws = [['冷兵器',['冷兵器','刀剑','弓矢','古代战争','无科技']],['蒸汽朋克',['蒸汽','蒸汽机','维多利亚','朋克','齿轮']],['赛博朋克',['赛博','义体','黑客','霓虹','都市科技','高科技低生活']],['现代都市',['现代','都市','城市','2000','90年代','80年代','千禧','互联网','智能手机']],['修仙灵气',['修仙','灵气','炼气','筑基','宗门','仙道','修真']],['架空未来',['未来','科幻','星际','太空','机甲','人工智能','AI科技']],['模拟信号',['模拟信号','功能型手机','按键机','传呼机','座机','2000年代初']]];
  function _kwMatch(text, kwList) {
    if (!text) return '';
    for (var k2=0;k2<kwList.length;k2++){
      var pair = kwList[k2];
      for (var k3=0;k3<pair[1].length;k3++){ if (text.indexOf(pair[1][k3])>=0) return pair[0]; }
    }
    return '';
  }
  var techVal = _kwMatch(eraText, techKws) || _kwMatch(coreText, techKws);
  if (techVal) { var et = document.getElementById('era-tech'); if (et) et.value = techVal; }
  // era-society 社会制度：匹配
  var socKws = [['封建帝制',['封建','帝制','皇帝','王朝','皇权','贵族']],['联邦共和',['联邦','共和','议会','民主','总统']],['部落联盟',['部落','氏族','酋长','联盟','原始']],['宗门林立',['宗门','教派','仙门','世家','门阀']],['财团垄断',['财团','财阀','垄断','资本','公司城']],['公社制',['公社','集体','平等','分配']],['地级市企业改制浪潮下的半垄断',['企业改制','下岗','半垄断','90年代末','2000年代初']]];
  var socVal = _kwMatch(eraText, socKws) || _kwMatch(coreText, socKws);
  if (socVal) { var es = document.getElementById('era-society'); if (es) es.value = socVal; }
  // era-geography 地理特征：匹配
  var geoKws = [['单一大陆+群岛',['群岛','海岛','大陆+','港湾','港口','海岸线']],['单一大陆',['大陆','平原','内陆','帝国']],['地下城+地表',['地下','地表','废墟','末日']],['多星系',['星际','星系','太空','殖民','星球']],['单一大陆的临江丘陵老城',['丘陵','临江','江边','老城','港口城镇','雾港']]];
  var geoVal = _kwMatch(eraText, geoKws) || _kwMatch(coreText, geoKws);
  if (geoVal) { var eg = document.getElementById('era-geography'); if (eg) eg.value = geoVal; }
  // era-culture 文化背景：匹配
  var culKws = [['儒家礼教+仙道',['儒家','礼教','科举','仙道','修仙']],['赛博+街头文化',['街头','嘻哈','涂鸦','霓虹','赛博']],['南方沿海小城，工业遗存与渔港',['渔港','工业遗存','沿海','小城','渔轮','修船厂']],['对「旧事」讳莫如深的集体沉默',['旧事','讳莫','沉默','不说','避讳']]];
  var culVal = _kwMatch(eraText, culKws) || _kwMatch(coreText, culKws);
  if (culVal) { var ec = document.getElementById('era-culture'); if (ec) ec.value = culVal; }
  // era-social-attitude 社会态度：匹配
  var attKws = [['崇拜',['崇拜','信仰','狂热']],['恐惧',['恐惧','害怕','禁忌','讳莫']],['严格管控',['管控','审查','监控','高压','不许']],['猎杀',['猎杀','围剿','清除']],['漠视',['漠视','冷漠','事不关己']],['宽容',['包容','多元','自由','开放']]];
  var attVal = _kwMatch(eraText, attKws) || _kwMatch(coreText, attKws) || _kwMatch(obj.other_settings ? String(obj.other_settings) : '', attKws);
  if (attVal) { var ea = document.getElementById('era-social-attitude'); if (ea) ea.value = attVal; }
  // 保存结构化字段到后端
  try {
    // 把 UI 中已填充的叙事风格/时代环境值读出来，一起 POST
    var nsPayload = {};
    var nsMap = {
      'ns-pov': 'pov',
      'ns-tense': 'tense',
      'ns-tone': 'tone',
      'ns-pacing': 'pacing',
      'ns-description': 'description_style'
    };
    for (var nid in nsMap) {
      var nel = document.getElementById(nid);
      if (nel && nel.value && String(nel.value).trim()) {
        nsPayload[nsMap[nid]] = String(nel.value).trim();
      }
    }
    var eraPayload = {};
    var eraMap = {
      'era-tech': 'tech_level',
      'era-society': 'society',
      'era-geography': 'geography',
      'era-culture': 'culture',
      'era-social-attitude': 'social_attitude'
    };
    for (var eid in eraMap) {
      var eel = document.getElementById(eid);
      if (eel && eel.value && String(eel.value).trim()) {
        eraPayload[eraMap[eid]] = String(eel.value).trim();
      }
    }
    var d2 = {};
    worldSettings.filter(function(s2){return s2 && s2.group === '世界观' && s2.key;}).forEach(function(s2){ d2[s2.key] = s2.val || ''; });
    var postBody = {world_settings: d2};
    if (Object.keys(nsPayload).length > 0) postBody.narrative_style = nsPayload;
    if (Object.keys(eraPayload).length > 0) postBody.era = eraPayload;
    if (typeof saveWorldMeta === 'function') {
      try { saveWorldMeta(Object.assign({includeWorldSettings: true}, postBody)); } catch(e) {
        // saveWorldMeta失败就fallback到直接API
        api('/api/project/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(postBody)}).catch(function(){});
      }
    } else {
      // 直接保存 world_settings + 结构化字段
      api('/api/project/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(postBody)}).catch(function(){});
    }
  } catch(eSave){ console.warn('[save world] 保存失败:', eSave); }
  // 刷新设定编辑器UI
  if (typeof renderSettingsEditor === 'function') renderSettingsEditor();
  return filled;
}

window.aiGenerateCharacters = function() {
  var btn = document.getElementById('btn-ai-gen-characters');
  if (!btn) { console.error('[人物生成] 按钮不存在'); return; }
  // 确认覆盖
  var overwrite = false;
  if (characters.length > 0) {
    overwrite = confirm('已有 ' + characters.length + ' 个人物。\n确定 = AI追加生成（不覆盖已有）\n取消 = AI覆盖全部（已有人物会被清空）');
    overwrite = !overwrite;
  }
  btn.disabled = true;
  btn.textContent = '⏳ 生成中…';
  showToast('正在连接AI生成人物…');
  // 读取全书大纲作为上下文
  var olText = '';
  if (typeof _novelOutlineDict !== 'undefined' && Object.keys(_novelOutlineDict).length > 0) {
    olText = JSON.stringify(_novelOutlineDict, null, 2);
  }
  console.log('[人物生成] 开始请求, overwrite:', overwrite, ', 大纲长度:', olText.length);
  api('/api/ai/generate-characters', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({overwrite: overwrite, novel_outline: olText})
  }).then(function(r) {
    console.log('[人物生成] 响应:', JSON.stringify(r).substring(0, 300));
    btn.disabled = false;
    btn.textContent = '🤖 AI生成';
    if (r.ok && r.characters) {
      characters = r.characters;
      api('/api/project/settings', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({characters: characters})
      });
      renderCharacterList();
      showToast('AI生成了 ' + characters.length + ' 个人物档案');
    } else {
      showToast('生成失败: ' + (r.error || '未知错误'));
    }
  }).catch(function(e) {
    console.error('[人物生成] 请求异常:', e);
    btn.disabled = false;
    btn.textContent = '🤖 AI生成';
    showToast('❌ 请求失败: ' + e.message);
  });
}

// AI丰富单个人物详情
window.aiGenCharDetail = function() {
  if (_selectedCharIdx < 0 || _selectedCharIdx >= characters.length) {
    showToast('请先选择一个人物');
    return;
  }
  var char = characters[_selectedCharIdx];
  var btn = document.querySelector('#char-detail-actions button:first-child');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  showToast('正在AI丰富人物详情…');

  // 构建prompt
  var worldPrompt = '';
  if (typeof worldSettings !== 'undefined' && worldSettings.length) {
    worldPrompt = worldSettings.map(function(s) { return s.key + '：' + s.val; }).join('\n');
  }
  var prompt = '你是专业小说角色设计师。请基于世界观设定和现有角色信息，丰富并完善这个角色的详细档案。\n\n' +
    '【世界观设定】\n' + (worldPrompt || '（未设定）') + '\n\n' +
    '【现有角色信息】\n' +
    '姓名：' + (char.name || '') + '\n' +
    '身份：' + (char.identity || '') + '\n' +
    '阵营：' + (char.faction || '') + '\n' +
    '性格：' + (char.personality || '') + '\n' +
    '身世过往：' + (char.background || '') + '\n' +
    '执念：' + (char.obsession || '') + '\n' +
    '软肋：' + (char.weakness || '') + '\n' +
    '目标：' + (char.goal || (char.goals && char.goals.length ? char.goals.map(function(g){return typeof g==='object'?g.text+'（权重'+g.weight+'）':g;}).join('；') : '')) + '\n' +
    '角色定位：' + (char.importance || '') + '\n\n' +
    '要求：\n' +
    '1. 丰富并完善每个字段的内容，使其更具体、更有深度\n' +
    '2. 补充人物外貌、习惯、口头禅、重要经历等细节\n' +
    '3. 人物羁绊要具体，包含目标角色名、关系类型和详细说明\n' +
    '4. 严格遵守世界观设定，不要出现矛盾\n\n' +
    '返回完整的JSON对象（放在```json代码块中），包含以下字段：\n' +
    'name, identity, faction, personality, background, obsession, weakness, goal, importance, appearance, habits, catchphrase, key_events, bonds\n' +
    'bonds是数组，每个元素包含target, relation, note三个字段。';

  api('/api/ai/chat', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({messages: [{role: 'user', content: prompt}], max_tokens: 4096})
  }).then(function(r) {
    if (btn) { btn.disabled = false; btn.textContent = '🤖'; }
    if (r.ok && r.content) {
      // 解析JSON
      var content = r.content.replace(/```json/g, '').replace(/```/g, '').trim();
      try {
        var updated = JSON.parse(content);
        if (updated && typeof updated === 'object') {
          // 合并到现有角色
          Object.assign(char, updated);
          saveCharacters();
          showCharDetail(_selectedCharIdx);
          renderCharacterList();
          showToast('人物详情已丰富');
          return;
        }
      } catch(e) {
        // 尝试提取JSON
        var match = content.match(/\{[\s\S]*\}/);
        if (match) {
          try {
            var updated2 = JSON.parse(match[0]);
            Object.assign(char, updated2);
            saveCharacters();
            showCharDetail(_selectedCharIdx);
            renderCharacterList();
            showToast('人物详情已丰富');
            return;
          } catch(e2) {}
        }
      }
      showToast('解析失败，请重试');
    } else {
      showToast('生成失败: ' + (r.error || '未知错误'));
    }
  }).catch(function(e) {
    if (btn) { btn.disabled = false; btn.textContent = '🤖'; }
    console.error('AI丰富人物失败:', e);
    showToast('❌ 请求失败: ' + e.message);
  });
}

/* ===== Override openSettingsAndHighlight ===== */
window.openSettingsAndHighlight = function(key) {
  L.leftDrawer.classList.remove('collapsed');
  goToStep(STEPS.世界观);
  renderSettingsEditor(key);
};

/* ===== Override original renderOutlineEditor to redirect ===== */
window.renderOutlineEditor = function() {
  // Only chapter outline remains (step 4)
  if (typeof renderChapterOutlineEditor === 'function') renderChapterOutlineEditor();
};

/* ===== Canvas Brainstorm ===== */
var _bsCards = [];
var _bsCardIdCounter = 0;
var _bsGraphView = false;
var _bsNodePositions = {}; // {cardId: {x, y}}
var _bsEdges = []; // [{src: cardId, dst: cardId}]
var _bsConnectMode = false;
var _bsConnectSource = null;

window.toggleBsView = function() {
  _bsGraphView = !_bsGraphView;
  var listCanvas = document.getElementById('brainstorm-canvas');
  var graphCanvas = document.getElementById('brainstorm-graph-canvas');
  var toggleBtn = document.getElementById('bs-view-toggle');
  if (!listCanvas || !graphCanvas) return;
  if (_bsGraphView) {
    listCanvas.style.display = 'none';
    graphCanvas.style.display = 'block';
    if (toggleBtn) toggleBtn.textContent = '📋 列表';
    _renderBsGraph();
  } else {
    listCanvas.style.display = '';
    graphCanvas.style.display = 'none';
    if (toggleBtn) toggleBtn.textContent = '📊 图谱';
  }
}

window.toggleBsConnectMode = function() {
  _bsConnectMode = !_bsConnectMode;
  _bsConnectSource = null;
  var btn = document.getElementById('bs-connect-toggle');
  var hint = document.getElementById('bs-connect-mode-text');
  if (btn) {
    btn.style.background = _bsConnectMode ? 'var(--accent)' : '';
    btn.style.color = _bsConnectMode ? '#fff' : '';
    btn.textContent = _bsConnectMode ? '✓ 连线中' : '🔗 连线';
  }
  if (hint) hint.textContent = _bsConnectMode ? '点击两个节点创建连线' : '点击"连线"进入连接模式';
}
window._saveBrainstormCards = function() {
  if (!_bsCards || _bsCards.length === 0) return;
  var cards = _bsCards.map(function(c) { return c.data; }).filter(function(d) { return d && d.title; });
  try { api('/api/project/brainstorm-cards', {method:'POST', body:JSON.stringify({cards: cards, graph: {positions: _bsNodePositions, edges: _bsEdges}})}); } catch(e) {}
}
window.generateBrainstormIdeas = function() {
  var topic = document.getElementById('bs-topic').value || '';
  var mode = document.getElementById('bs-mode').value || 'plot';
  var btn = document.getElementById('bs-generate-btn');
  var canvas = document.getElementById('brainstorm-canvas');
  var hint = document.getElementById('bs-empty-hint');
  if (hint) hint.style.display = 'none';

  // Loading state
  btn.textContent = '生成中...';
  btn.disabled = true;
  var loadingDiv = document.createElement('div');
  loadingDiv.className = 'bs-loading';
  loadingDiv.id = 'bs-loading';
  loadingDiv.innerHTML = '<svg class="svg-spin" viewBox="0 0 24 24" width="32" height="32" ><path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round"/></svg><p class="mt-2" >AI正在生成创意...</p>';
  canvas.appendChild(loadingDiv);

  var editorContent = '';
  var editorEl = document.getElementById('editor-content');
  if (editorEl) editorContent = editorEl.innerText.substring(0, 1000);

  aiBrainstorm(topic, editorContent, mode).then(function(r) {
    btn.textContent = '生成创意';
    btn.disabled = false;
    var loading = document.getElementById('bs-loading');
    if (loading) loading.remove();

    if (r.ok && r.ideas && r.ideas.length > 0) {
      r.ideas.forEach(function(idea) {
        _addBrainstormCard(idea);
      });
      _updateBsCardCount();
      showToast('生成了 ' + r.ideas.length + ' 个创意');
    } else {
      showToast(r.error || '生成失败');
      if (_bsCards.length === 0 && hint) hint.style.display = 'block';
    }
  });
}
window._addBrainstormCard = function(idea) {
  var canvas = document.getElementById('brainstorm-canvas');
  var hint = document.getElementById('bs-empty-hint');
  if (hint) hint.style.display = 'none';

  var cardId = 'bs-card-' + (++_bsCardIdCounter);
  var card = document.createElement('div');
  card.className = 'bs-card';
  card.id = cardId;
  card.draggable = true;

  var impact = idea.impact || 'medium';
  var tagsHtml = '';
  if (idea.tags && idea.tags.length > 0) {
    tagsHtml = idea.tags.map(function(t) {
      return '<span class="bs-tag">' + esc(t) + '</span>';
    }).join('');
  }
  tagsHtml += '<span class="bs-tag impact-' + impact + '">' + impact + '</span>';

  card.innerHTML =
    '<div class="bs-card-actions">' +
      '<button class="bs-card-btn" onclick="expandBsCard(\'' + cardId + '\')" title="灵感扩展">✨</button>' +
      '<button class="bs-card-btn" onclick="insertBsCardText(\'' + cardId + '\')" title="插入到正文">📥</button>' +
      '<button class="bs-card-btn" onclick="removeBsCard(\'' + cardId + '\')" title="删除">🗑</button>' +
    '</div>' +
    '<div class="bs-card-title">' + esc(idea.title || '无标题') + '</div>' +
    '<div class="bs-card-desc">' + esc(idea.desc || '') + '</div>' +
    '<div class="bs-card-tags">' + tagsHtml + '</div>';

  // Drag events
  card.addEventListener('dragstart', function(e) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', cardId);
    this.classList.add('dragging');
  });
  card.addEventListener('dragend', function(e) {
    this.classList.remove('dragging');
  });

  canvas.appendChild(card);
  _bsCards.push({id: cardId, data: idea});
  _saveBrainstormCards(); // 每次新增卡片自动保存
}
window.expandBsCard = function(cardId) {
  var cardData = _bsCards.find(function(c) { return c.id === cardId; });
  if (!cardData) return;
  var idea = cardData.data;
  var mode = document.getElementById('bs-mode') ? document.getElementById('bs-mode').value : 'plot';

  // 在卡片下方显示加载状态
  var card = document.getElementById(cardId);
  if (!card) return;

  // 移除旧的扩展内容
  var oldExpanded = card.querySelector('.bs-expanded');
  if (oldExpanded) oldExpanded.remove();

  var expandDiv = document.createElement('div');
  expandDiv.className = 'bs-expanded';
  expandDiv.style.cssText = 'margin-top:8px;padding:8px 10px;background:var(--bg);border-radius:6px;border:1px solid var(--accent);font-size:12px;line-height:1.6;color:var(--ink);position:relative';
  expandDiv.innerHTML = '<div style="display:flex;align-items:center;gap:6px;color:var(--accent);font-size:11px;margin-bottom:4px"><svg class="svg-spin" viewBox="0 0 24 24" width="14" height="14" ><path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round"/></svg> 灵感扩展中...</div>';
  card.appendChild(expandDiv);

  // 获取当前章节内容作为上下文
  var editorEl = document.getElementById('editor-content');
  var context = editorEl ? editorEl.innerText.substring(0, 800) : '';

  api('/api/ai/expand-idea', {
    method: 'POST',
    body: JSON.stringify({ title: idea.title || '', desc: idea.desc || '', mode: mode, context: context })
  }).then(function(r) {
    if (r.ok && r.expanded) {
      expandDiv.innerHTML =
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">' +
          '<span style="color:var(--accent);font-size:11px;font-weight:600">✨ 灵感扩展</span>' +
          '<div style="display:flex;gap:4px">' +
            '<button onclick="insertExpandedText(this)" title="插入到正文" style="font-size:10px;padding:2px 6px;border:1px solid var(--accent);border-radius:3px;background:var(--accent);color:#fff;cursor:pointer">📥插入</button>' +
            '<button onclick="this.closest(\'.bs-expanded\').remove()" title="关闭" style="font-size:10px;padding:2px 6px;border:1px solid var(--border);border-radius:3px;background:var(--bg);color:var(--muted);cursor:pointer">✕</button>' +
          '</div>' +
        '</div>' +
        '<div class="bs-expanded-content" style="white-space:pre-wrap">' + esc(r.expanded) + '</div>';
    } else {
      expandDiv.innerHTML = '<div style="color:#c44;font-size:11px">' + esc(r.error || '扩展失败') + ' <button onclick="this.closest(\'.bs-expanded\').remove()" style="font-size:10px;color:var(--muted);border:none;background:none;cursor:pointer">✕</button></div>';
    }
  });
}

window.insertExpandedText = function(btn) {
  var content = btn.closest('.bs-expanded').querySelector('.bs-expanded-content');
  if (!content) return;
  var text = content.textContent;
  var editor = document.getElementById('editor-content');
  if (!editor) { showToast('编辑器未找到'); return; }
  // 直接追加到编辑器末尾（overlay打开时无法获取光标位置）
  var p = document.createElement('p');
  p.style.cssText = 'color:var(--accent);font-style:italic;border-left:3px solid var(--accent);padding-left:10px;margin:8px 0';
  p.textContent = '【灵感扩展】' + text;
  editor.appendChild(p);
  // 滚动到底部
  editor.scrollTop = editor.scrollHeight;
  showToast('已插入到正文末尾');
  // 关闭头脑风暴面板，让用户看到插入效果
  closeBrainstormPanel();
}

window.removeBsCard = function(cardId) {
  var card = document.getElementById(cardId);
  if (card) card.remove();
  _bsCards = _bsCards.filter(function(c) { return c.id !== cardId; });
  _updateBsCardCount();
  if (_bsCards.length === 0) {
    var hint = document.getElementById('bs-empty-hint');
    if (hint) hint.style.display = 'block';
  }
}
window.insertBsCardText = function(cardId) {
  var cardData = _bsCards.find(function(c) { return c.id === cardId; });
  if (!cardData) return;
  var editor = document.getElementById('editor-content');
  if (editor) {
    var text = '\n\n【灵感：' + cardData.data.title + '】\n' + (cardData.data.desc || '') + '\n';
    editor.innerHTML += '<p style="color:var(--accent);font-style:italic">' + esc(text.trim()) + '</p>';
    showToast('已插入到正文');
  }
}
window.clearBrainstormCanvas = function() {
  var canvas = document.getElementById('brainstorm-canvas');
  if (canvas) {
    canvas.querySelectorAll('.bs-card').forEach(function(c) { c.remove(); });
    _bsCards = [];
    _updateBsCardCount();
    var hint = document.getElementById('bs-empty-hint');
    if (hint) hint.style.display = 'block';
    showToast('画板已清空');
  }
}
window._updateBsCardCount = function() {
  var countEl = document.getElementById('bs-card-count');
  if (countEl) countEl.textContent = _bsCards.length + ' 张卡片';
}
window.generateSensoryDesc = function() {
  var scene = document.getElementById('sensory-scene').value || '';
  var style = document.getElementById('sensory-style').value || 'immersive';
  var btn = document.getElementById('sensory-gen-btn');
  var resultsDiv = document.getElementById('sensory-results');

  btn.textContent = '生成中...';
  btn.disabled = true;
  resultsDiv.innerHTML = '<div class="bs-loading"><svg viewBox="0 0 24 24" width="32" height="32" style="stroke:currentColor;fill:none;stroke-width:2;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56" stroke-linecap="round"/></svg><p class="mt-2" >AI正在生成感官描写...</p></div>';

  // If scene is empty, use current editor content
  if (!scene) {
    var editorEl = document.getElementById('editor-content');
    if (editorEl) scene = editorEl.innerText.substring(0, 1500);
  }

  aiSensory(scene, _currentSenseType, style).then(function(r) {
    btn.textContent = '生成描写';
    btn.disabled = false;

    if (r.ok && r.sensory) {
      _renderSensoryResults(r.sensory);
      showToast('感官描写已生成');
    } else {
      resultsDiv.innerHTML = '<div class="sensory-empty svg-spin"><p>' + esc(r.error || '生成失败') + '</p></div>';
      showToast(r.error || '生成失败');
    }
  });
}

})();