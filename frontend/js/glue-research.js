(function() {
  'use strict';


window.aiWorldInspirationToStructured = async function() {
  var btn = document.getElementById('btn-world-inspiration-to-structured');
  if (!btn) return;
  var input = document.getElementById('world-inspiration-input');
  var inspiration = input ? input.value.trim() : '';
  if (!inspiration) { showToast('⚠️ 请先输入灵感碎片内容'); if (input) input.focus(); return; }
  btn.disabled = true; var oldTxt = btn.textContent; btn.textContent = '🧠 拆解中…';
  try {
    var title = (document.getElementById('project-name') && document.getElementById('project-name').textContent) || '小说';
    var genre = (typeof currentProject !== 'undefined' && currentProject && currentProject.genre) ? currentProject.genre : '小说';
    var prompt = '以下是用户对一部【' + genre + '】小说《' + title + '》的碎片想法，请你拆解并生成9个世界观结构化字段，严格用JSON对象返回（只返回JSON不要解释，不要Markdown代码块也可以）：\n' +
      '字段说明：\n' +
      '- core_setting：核心设定（世界运行的底层规则，如"全民力场泡泡架空世界，泡泡层级即隐形阶级…"）\n' +
      '- era_background：时代背景整体描述（什么时代、什么社会、城市/环境整体感觉）\n' +
      '- overall_style：整体风格（题材气质+感情基调+有无狗血/逆袭/第三者+结构特点）\n' +
      '- atmosphere：氛围基调（场景关键词+情感温度+适合写的场景类型）\n' +
      '- main_roles_overview：主要角色概览（3-5个人，每人一句话：姓名/性别/阶层/身份/核心性格）\n' +
      '- other_settings：其他设定（篇幅结构/伏笔策略/Slogan/结局方式 等）\n' +
      '- perspective_rules：视角规则（第几人称/限知还是全知/主视角/辅助视角 等）\n' +
      '- sensory_limits：感官限制（重点写的感官/身体细节/禁写哪些感觉 等）\n' +
      '- visual_style：视觉风格（光影+画面元素+颜色基调+重点镜头）\n\n' +
      '用户的灵感碎片原文：\n"""\n' + inspiration + '\n"""';
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (!r || !r.ok || !r.content) {
      r = await api('/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    }
    if (r && r.ok && r.content) {
      var fields = _parseAIObjectJSON(r.content);
      var filled = applyWorldCore9FieldsToSettings(fields);
      if (filled > 0) {
        showToast('✅ 已拆解生成 ' + filled + '/9 个世界观设定条目，已写入世界观设定栏');
      } else {
        showToast('⚠️ 解析结果为空，请检查AI返回格式');
      }
    } else {
      showToast('生成失败' + (r && r.error ? '：' + r.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  btn.disabled = false; btn.textContent = oldTxt;
}

window.aiExpandWorldField = function(fieldKey) {
  // 9字段卡已删除，此函数保留为空（兼容历史代码引用）。如需扩展单个设定项可在设定编辑器中手动点击AI优化。
  showToast('提示：请在右侧世界观设定栏选择对应设定项，点击"AI优化"按钮进行扩展。');
}

// ══ 人物：灵感碎片→人物卡数组 ══
window.aiCharacterInspirationToCards = async function() {
  var btn = document.getElementById('btn-character-inspiration-to-cards');
  if (!btn) return;
  var input = document.getElementById('character-inspiration-input');
  var inspiration = input ? input.value.trim() : '';
  if (!inspiration) { showToast('⚠️ 请先输入人物灵感碎片'); if (input) input.focus(); return; }
  btn.disabled = true; var oldTxt = btn.textContent; btn.textContent = '🧠 拆解中…';
  try {
    var title = (document.getElementById('project-name') && document.getElementById('project-name').textContent) || '小说';
    var genre = (typeof currentProject !== 'undefined' && currentProject && currentProject.genre) ? currentProject.genre : '小说';
    var prompt = '以下是用户对一部【' + genre + '】小说《' + title + '》的人物灵感碎片，请你拆解并生成3-5个完整人物档案，严格用JSON数组返回（只返回数组不要任何解释，不要代码块也可以）。\n' +
      '每个人物对象字段：\n' +
      '- name：姓名（2-4字）\n' +
      '- identity：身份（职业/阶层/地位，一句话）\n' +
      '- camp：阵营（男主/女主/男配/女配/反派/路人 等）\n' +
      '- personality：性格（3-5个核心性格词+简单解释，80字以内）\n' +
      '- backstory：背景（成长经历/关键事件/家庭，100字以内）\n' +
      '- obsession：执念（最放不下的一件事/东西/人，一句话）\n' +
      '- weakness：弱点（性格/身体/心理/禁忌，一句话）\n' +
      '- goal：目标（故事开始时的主要目标，一句话；多个目标用 goals 数组，如 [{"text":"通过考核","weight":0.8}]）\n' +
      '- cognitive_boundary：认知边界（角色不知道的信息/领域限制，如"不知道幕后主使是谁"）\n' +
      '- character_position：定位（核心男主/核心女主/主要配角/次要配角 等）\n\n' +
      '用户的人物灵感碎片原文：\n"""\n' + inspiration + '\n"""';
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (!r || !r.ok || !r.content) {
      r = await api('/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    }
    if (r && r.ok && r.content) {
      var list = [];
      // 尝试JSON解析
      try {
        var raw = String(r.content).replace(/```json|```/gi, '').trim();
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) list = parsed;
        else if (parsed && parsed.characters && Array.isArray(parsed.characters)) list = parsed.characters;
        else if (parsed && typeof parsed === 'object') list = [parsed];
      } catch(e) {
        // 失败就走已有 aiGenerateCharacters 逻辑兜底
        console.warn('[人物灵感] JSON解析失败，尝试通用AI生成人物接口', e);
      }
      if (Array.isArray(list) && list.length > 0) {
        // 标准化字段 + 合并到 characters（不覆盖已有，而是追加）
        var normalizeMap = {
          '姓名':'name','名字':'name','name':'name',
          '身份':'identity','职业':'identity','定位':'identity','identity':'identity',
          '阵营':'camp','归属':'camp','角色分类':'camp','camp':'camp',
          '性格':'personality','性格特点':'personality','personality':'personality',
          '背景':'backstory','成长背景':'backstory','经历':'backstory','backstory':'backstory',
          '执念':'obsession','核心执念':'obsession','obsession':'obsession',
          '弱点':'weakness','缺点':'weakness','软肋':'weakness','weakness':'weakness',
          '目标':'goal','人生目标':'goal','goal':'goal',
          '认知边界':'cognitive_boundary','不知道的事':'cognitive_boundary','cognitive_boundary':'cognitive_boundary',
          '人物定位':'character_position','定位':'character_position','角色定位':'character_position','character_position':'character_position'
        };
        var existing = new Set((characters || []).map(function(c){return c && c.name;}));
        var added = 0;
        for (var i = 0; i < list.length; i++) {
          var raw = list[i] || {};
          var norm = {};
          for (var k in raw) {
            if (raw.hasOwnProperty(k)) {
              var nk = normalizeMap[k] || k;
              norm[nk] = raw[k];
            }
          }
          if (!norm.name) norm.name = '人物' + (characters.length + 1);
          if (existing.has(norm.name)) continue; // 跳过已有的
          if (!norm.identity) norm.identity = '';
          if (!norm.camp) norm.camp = norm.character_position || '配角';
          if (!norm.personality) norm.personality = '';
          if (!norm.backstory) norm.backstory = '';
          if (!norm.obsession) norm.obsession = '';
          if (!norm.weakness) norm.weakness = '';
          if (!norm.goal) norm.goal = '';
          if (!norm.goals) norm.goals = [];
          if (!norm.cognitive_boundary) norm.cognitive_boundary = '';
          if (!norm.character_position) norm.character_position = '次要配角';
          characters.push(norm);
          existing.add(norm.name);
          added++;
        }
        if (added > 0) {
          if (typeof saveCharacters === 'function') await saveCharacters();
          if (typeof renderCharacterList === 'function') renderCharacterList();
          showToast('✅ 已从灵感生成 ' + added + ' 个新人物档案并保存');
        } else {
          showToast('⚠️ 生成的人物都已存在或无有效数据');
        }
      } else {
        // 兜底：调用通用 AI生成人物 逻辑（如果已实现）
        if (typeof aiGenerateCharacters === 'function') {
          btn.disabled = false; btn.textContent = oldTxt;
          await aiGenerateCharacters();
          return;
        }
        showToast('⚠️ 解析人物数据失败，请检查AI返回格式');
      }
    } else {
      showToast('生成失败' + (r && r.error ? '：' + r.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  btn.disabled = false; btn.textContent = oldTxt;
}

// ══════════════════════════════════════════════════════════════
// 阶段一8：统一样式的灵感碎片拆解函数（步骤2/4/5新增的3个按钮）
// ══════════════════════════════════════════════════════════════

// ══ 步骤2：灵感碎片 → 全书大纲 ══
window.aiNovelInspirationToOutline = async function() {
  var btn = document.getElementById('btn-novel-inspiration-to-outline');
  var inp = document.getElementById('novel-inspiration-input');
  var inspiration = inp ? inp.value.trim() : '';
  if (!inspiration) { showToast('⚠️ 请先输入灵感碎片内容'); if (inp) inp.focus(); return; }
  if (btn) { btn.disabled = true; btn._old = btn.textContent; btn.textContent = '⏳ 生成中…'; }
  try {
    // 从现有 novel outline 绑定复用：触发旧绑定的点击事件（保证逻辑一致），否则走新逻辑
    var oldBtn = document.getElementById('btn-inspiration-to-novel-ol');
    if (oldBtn && typeof oldBtn.click === 'function') {
      // 如果旧按钮存在，复用其事件处理（但要先把inp的值写进去——但其实inp是同一个id，novel-inspiration-input，所以旧逻辑会读到同一个textarea，不用管）
      try {
        var fake = document.createEvent('MouseEvents'); fake.initEvent('click', true, true);
        oldBtn.dispatchEvent(fake);
        if (btn) { btn.disabled = false; btn.textContent = btn._old; }
        return;
      } catch(e) { console.warn('旧按钮点击失败，走新逻辑', e); }
    }
    // 新兜底逻辑：调 AI chat 生成 全书大纲 JSON 并写入 novel_outline
    var prompt = '请将以下灵感碎片拆解为「全书大纲」结构化 JSON，字段为：{theme, core_conflict, story_arc, structure, overall_description, character_arcs, tone, ending, hook}。\n\n用户的灵感碎片原文：\n"""\n' + inspiration + '\n"""';
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (!r || !r.ok || !r.content) r = await api('/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (r && r.ok && r.content) {
      var dict = null;
      try {
        var raw = String(r.content).replace(/```json|```/gi, '').trim();
        dict = JSON.parse(raw);
        if (!dict || typeof dict !== 'object') throw new Error('not-object');
      } catch(e) { dict = { overall_description: String(r.content), theme: '', core_conflict: '', story_arc: '', hook: '', ending: '', tone: '' }; }
      await api('/api/project/novel-outline', {method: 'POST', body: JSON.stringify({novel_outline: dict || {}})});
      if (typeof renderNovelOutlineEditor === 'function') try { renderNovelOutlineEditor(); } catch(e) {}
      showToast('✅ 全书大纲已生成，已写入编辑面板（若未显示请切到📝编辑视图）');
    } else {
      showToast('生成失败' + (r && r.error ? '：' + r.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  if (btn) { btn.disabled = false; btn.textContent = btn._old; }
}

// ══ 步骤4：灵感碎片 → 分卷纲要 ══
window.aiVolumesInspirationToOutline = async function() {
  var btn = document.getElementById('btn-vol-inspiration-to-outline');
  var inp = document.getElementById('volume-inspiration-input');
  var inspiration = inp ? inp.value.trim() : '';
  if (!inspiration) { showToast('⚠️ 请先输入分卷灵感碎片内容'); if (inp) inp.focus(); return; }
  if (btn) { btn.disabled = true; btn._old = btn.textContent; btn.textContent = '⏳ 拆解中…'; }
  try {
    // 直接调后端 ai-split-volumes 接口，它支持带 inspiration 参数
    var d = await api('/api/project/ai-split-volumes', {
      method: 'POST',
      body: JSON.stringify({inspiration: inspiration})
    });
    if (d && d.ok) {
      var vols = d.volumes || [];
      showToast('✅ 分卷拆解完成，共' + vols.length + '卷，' + (d.chapter_count || 0) + '章，已写入 volumes.outline');
      if (typeof loadVolumesData === 'function') try { await loadVolumesData(); } catch(e) {}
      if (typeof renderVolumeOutlineList === 'function') try { renderVolumeOutlineList(); } catch(e) {}
    } else {
      showToast('生成失败' + (d && d.error ? '：' + d.error : ''));
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  if (btn) { btn.disabled = false; btn.textContent = btn._old; }
}

// ══ 步骤5：灵感碎片 → 全书章节大纲（3章结构化蓝图+连线框画布）══
window.aiAllChaptersInspirationToOutline = async function() {
  var btn = document.getElementById('btn-chapter-inspiration-to-outline');
  var inp = document.getElementById('chapter-inspiration-input');
  var inspiration = inp ? inp.value.trim() : '';
  if (!inspiration) { showToast('⚠️ 请先输入章节灵感碎片内容'); if (inp) inp.focus(); return; }
  if (btn) { btn.disabled = true; btn._old = btn.textContent; btn.textContent = '⏳ 拆解中…'; }
  try {
    // 提示：让后端AI分支识别"全书章节大纲"，返回 {chapters:[...], planning_cards:{nodes,edges}} 结构
    var prompt = '请根据以下灵感，生成「全书章节大纲」：\n要求：\n1) 返回 JSON 格式 { "chapters": [ {"chapter":1,"title":"xxx","outline":"...（包含intro/development/climax/ending四段+scenes数组）","word_count_target":3000}, ...], "planning_cards": {"nodes":[{"id":"n1","type":"chapter","title":"...","summary":"...","x":620,"y":80,"color":"#10b981","chapter_ref":"第1章"}, ...], "edges":[{"id":"e1","from":"n1","to":"n2","label":"承接"}]} }\n2) 章节数量从原文推断，若未明确默认3章完结\n3) planning_cards 必须至少为每一章生成 1 个节点，相邻章节必须有连线\n\n用户的章节结构灵感碎片原文：\n"""\n' + inspiration + '\n"""';
    var r = await api('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    if (!r || !r.ok || !r.content) r = await api('/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages:[{role:'user',content:prompt}]})});
    var parsedChapters = null;
    var planningCards = null;
    if (r && r.ok && r.content) {
      try {
        var raw = String(r.content).replace(/```json|```/gi, '').trim();
        var obj = JSON.parse(raw);
        if (obj && Array.isArray(obj.chapters)) parsedChapters = obj.chapters;
        if (obj && obj.planning_cards && typeof obj.planning_cards === 'object') planningCards = obj.planning_cards;
      } catch(e) { console.warn('[步骤5] JSON解析失败，尝试章节文本解析', e); }
    }
    if (parsedChapters && parsedChapters.length > 0) {
      // 写入 chapters（调标准API：POST /api/chapter/outline 带 index/outline/blueprint）
      for (var _ci = 0; _ci < parsedChapters.length; _ci++) {
        var ch = parsedChapters[_ci];
        var chIdx = (ch.chapter && parseInt(ch.chapter) > 0) ? (parseInt(ch.chapter) - 1) : _ci;
        // 尝试解析蓝图JSON（ch.outline可能包含JSON）
        var blueprintObj = null;
        var outlineRaw = ch.outline || '';
        try {
          var stripped = String(outlineRaw).replace(/```json|```/gi, '').trim();
          if (stripped.startsWith('{')) blueprintObj = JSON.parse(stripped);
        } catch(e) { blueprintObj = null; }
        try {
          await api('/api/chapter/outline', {
            method: 'POST',
            body: JSON.stringify({
              index: chIdx,
              outline: String((ch.outline || JSON.stringify(ch, null, 2) || '')),
              blueprint: blueprintObj
            })
          });
        } catch(e) { console.warn('写入章节outline失败 idx=' + chIdx, e); }
      }
      // 写入 planning_cards 画布
      if (planningCards && planningCards.nodes && planningCards.nodes.length > 0) {
        try {
          await api('/api/project/planning-cards', {
            method: 'POST',
            body: JSON.stringify({
              nodes: planningCards.nodes,
              edges: planningCards.edges || [],
              meta: { last_saved: new Date().toISOString(), source: 'inspiration-to-outline' }
            })
          });
        } catch(e) { console.warn('写入planning_cards失败', e); }
      }
      // 刷新章节列表和章节大纲视图
      if (typeof loadChaptersFromAPI === 'function') try { await loadChaptersFromAPI(); } catch(e) {}
      if (typeof renderChapterOutlineForIndex === 'function' && typeof currentChapterIndex !== 'undefined') {
        try { renderChapterOutlineForIndex(currentChapterIndex); } catch(e) {}
      }
      if (typeof renderChapterOutlineEditor === 'function') try { renderChapterOutlineEditor(); } catch(e) {}
      showToast('✅ 章节大纲拆解完成，共' + parsedChapters.length + '章，已写入 chapters.outline' + (planningCards && planningCards.nodes ? ' 和 planning_cards 连线框画布（节点数=' + planningCards.nodes.length + '）' : '') + '。现在可以切到步骤8确认画布布局！');
    } else {
      showToast('⚠️ 未能解析出章节结构，请在原文中明确列出每一章的情节要点，或重试');
    }
  } catch(e) { showToast('生成异常：' + e.message); }
  if (btn) { btn.disabled = false; btn.textContent = btn._old; }
}

})();