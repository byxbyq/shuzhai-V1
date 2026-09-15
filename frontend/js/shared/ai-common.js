// ════════════════════════════════════════════════════════════════
// 书斋 V65 - AI 通用共享模块 (ai-common.js)
// 从 ai-engine.js 和 offline-ai.js 抽取的共享代码
// 导出：window.AICommon
// ════════════════════════════════════════════════════════════════
(function (global) {
  'use strict';

  // ═══════════════════════════════════════════
  // 禁词表（合并 ai-engine.js 和 offline-ai.js 的并集）
  // ═══════════════════════════════════════════
  var FORBIDDEN_WORDS = [
    '龙傲天', '邪魅一笑', '嘴角上扬', '勾起一抹', '不禁', '竟然', '居然', '赫然',
    '蓦然', '霎时', '须臾', '转念一想', '暗自思忖', '心中暗道', '目光如炬',
    '气宇轩昂', '玉树临风', '倾国倾城', '闭月羞花', '沉鱼落雁', '美若天仙',
    '如花似玉', '冰肌玉骨', '肤若凝脂', '面若桃花', '唇红齿白', '明眸皓齿',
    '眉目如画', '鼻梁挺拔', '身材魁梧', '步履稳健', '声如洪钟', '气吞山河',
    '惊天动地', '排山倒海', '翻江倒海', '铺天盖地', '遮天蔽日', '漫山遍野',
    '不计其数', '数不胜数', '多如牛毛', '汗牛充栋', '罄竹难书', '擢发难数',
    '恒河沙数', '浩如烟海', '灿若繁星', '星罗棋布',
    '突然', '不可思议', '眼中闪过一丝', '不由得', '嘴角微微', '攥紧拳头',
    '瞳孔放大', '倒吸一口凉气', '微微一笑', '他缓缓说道', '她淡淡一笑',
    '不知为何', '莫名地', '一股暖流', '心头一震'
  ];

  var FORBIDDEN_PLOTS = [
    '天降神器', '意外获得传承', '路遇高人指点', '误入秘境', '巧得功法',
    '救人获宝', '比武大会夺冠', '拍卖会捡漏', '仇人上门', '英雄救美',
    '天降救兵', '主角被动等待救援', '未预料的巧合', '机械降神',
    '结尾预告句式', '每段对话以XX说开头'
  ];

  // ═══════════════════════════════════════════
  // 内部工具函数
  // ═══════════════════════════════════════════

  // 统计子串出现次数
  function _countSub(str, sub) {
    if (!str || !sub) return 0;
    var cnt = 0, idx = 0;
    while ((idx = str.indexOf(sub, idx)) !== -1) {
      cnt++;
      idx += sub.length;
    }
    return cnt;
  }

  // 截断文本到指定长度
  function _truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) : str;
  }

  // 判断是否为中文字符
  function _isChinese(ch) {
    if (!ch) return false;
    var code = ch.charCodeAt(0);
    return code >= 0x4e00 && code <= 0x9fa5;
  }

  // 提取中文关键词（2-4字），用于 Lorebook 触发
  function _extractKeywords(text) {
    if (!text) return [];
    var matches = text.match(/[\u4e00-\u9fa5]{2,4}/g);
    return matches || [];
  }

  // 容错 JSON 解析（处理 AI 返回的 JSON 可能不完整 / 带代码块 / 带 think 标签）
  function _parseJSONLenient(raw) {
    if (raw === null || raw === undefined || raw === '') return null;
    var text = String(raw);
    // 剥离 <think>...</think>
    text = text.replace(/<think\b[\s\S]*?<\/think\b\s*>/gi, '');
    // 剥离 markdown 代码块标记
    var clean = text.replace(/```json\s*/gi, '').replace(/```/g, '').trim();

    // 1. 直接解析
    try { return JSON.parse(clean); } catch (e) { /* continue */ }

    // 2. 提取 ```json ... ``` 代码块（可能未闭合）
    var m = text.match(/```json\s*([\s\S]+?)(?:```|$)/i);
    if (m) {
      try { return JSON.parse(m[1].trim()); } catch (e) { /* continue */ }
    }

    // 3. 提取数组 [...]
    var sArr = clean.indexOf('[');
    var eArr = clean.lastIndexOf(']');
    if (sArr >= 0 && eArr > sArr) {
      try { return JSON.parse(clean.substring(sArr, eArr + 1)); } catch (e) { /* continue */ }
    }

    // 4. 提取对象 {...}
    var sObj = clean.indexOf('{');
    var eObj = clean.lastIndexOf('}');
    if (sObj >= 0 && eObj > sObj) {
      try { return JSON.parse(clean.substring(sObj, eObj + 1)); } catch (e) { /* continue */ }
    }

    return null;
  }

  // ═══════════════════════════════════════════
  // 世界观 → Prompt（移植 WorldSettings.to_prompt）
  // ═══════════════════════════════════════════
  function _worldToPrompt(worldSettings) {
    if (!worldSettings) return '';
    var parts = [];

    // 兼容两种传入结构：{ world_meta: {...} } 或直接展开
    var world = worldSettings.world_meta || worldSettings;
    var ns = worldSettings.narrative_style || (world && world.narrative_style) || {};
    var era = worldSettings.era || (world && world.era) || {};

    // 叙事风格
    var nsItems = [];
    if (ns.pov) nsItems.push('视角: ' + ns.pov);
    if (ns.tense) nsItems.push('时态: ' + ns.tense);
    if (ns.tone) nsItems.push('基调: ' + ns.tone);
    if (ns.pacing) nsItems.push('节奏: ' + ns.pacing);
    if (ns.description_style) nsItems.push('描写: ' + ns.description_style);
    if (nsItems.length) parts.push('## 叙事风格\n' + nsItems.join(' | '));

    // 时代环境
    var eraItems = [];
    if (era.tech_level) eraItems.push('科技: ' + era.tech_level);
    if (era.society) eraItems.push('社会: ' + era.society);
    if (era.geography) eraItems.push('地理: ' + era.geography);
    if (era.culture) eraItems.push('文化: ' + era.culture);
    if (era.social_attitude) eraItems.push('社会态度: ' + era.social_attitude);
    if (eraItems.length) parts.push('## 时代环境\n' + eraItems.join(' | '));

    // 灵力体系
    var ms = world.magic_system || {};
    if (ms.name) {
      parts.push('## 灵力体系\n名称: ' + ms.name);
      if (ms.rules && ms.rules.length) parts.push('规则: ' + ms.rules.join('; '));
      if (ms.realms && ms.realms.length) parts.push('境界: ' + ms.realms.join(' → '));
    }

    // 世界规则 + 硬约束
    var allRules = [];
    var wr = worldSettings.world_rules || (world && world.world_rules) || [];
    var hc = world.hard_constraints || [];
    allRules = allRules.concat(wr).concat(hc);
    var ruleLines = [];
    for (var i = 0; i < allRules.length; i++) {
      var r = allRules[i];
      if (r && typeof r === 'object') {
        var rk = r.key || '';
        var rv = r.val || '';
        ruleLines.push(rk ? ('- ' + rk + '：' + rv) : ('- ' + rv));
      } else if (typeof r === 'string' && r) {
        ruleLines.push('- ' + r);
      }
    }
    if (ruleLines.length) parts.push('## 世界规则\n' + ruleLines.join('\n'));

    // 核心设定（world_settings）
    var ws = worldSettings.world_settings_raw || (world && world.world_settings) || worldSettings.world_settings || {};
    if (ws && typeof ws === 'object') {
      var wsLines = [];
      for (var wk in ws) {
        if (ws.hasOwnProperty(wk) && ws[wk]) wsLines.push('- ' + wk + '：' + ws[wk]);
      }
      if (wsLines.length) parts.push('## 核心设定\n' + wsLines.join('\n'));
    }

    // 势力
    var forces = world.forces || [];
    if (forces.length) {
      var forceLines = [];
      for (var fi = 0; fi < forces.length; fi++) {
        var f = forces[fi];
        forceLines.push('- ' + (f.name || '') + ': 领地[' + (f.territory || '') + '] 态度[' + (f.attitude || '') + ']');
      }
      parts.push('## 势力\n' + forceLines.join('\n'));
    }

    // 关键物品
    var items = world.items || [];
    if (items.length) {
      var itemLines = [];
      for (var ii = 0; ii < items.length; ii++) {
        var it = items[ii];
        itemLines.push('- ' + (it.name || '') + '(' + (it.nature || '') + '): ' + (it.description || '') +
          ' [首现第' + (it.first_seen_chapter || 0) + '章]');
      }
      parts.push('## 关键物品\n' + itemLines.join('\n'));
    }

    // freeform 兜底
    var coveredKeys = { '整体风格': 1, '时代背景': 1, '核心设定': 1, '氛围基调': 1, '叙事风格': 1, '时代环境': 1, '世界规则': 1 };
    var freeform = world.freeform || {};
    var extra = [];
    for (var fk in freeform) {
      if (freeform.hasOwnProperty(fk) && !coveredKeys[fk] && freeform[fk]) {
        extra.push('- ' + fk + ': ' + freeform[fk]);
      }
    }
    if (extra.length) parts.push('## 其他设定\n' + extra.join('\n'));

    return parts.length ? parts.join('\n\n') : '';
  }

  // ═══════════════════════════════════════════
  // Lorebook 关键词触发（移植 _trigger_lorebook）
  // ═══════════════════════════════════════════
  function _triggerLorebook(text, worldSettings) {
    if (!text || !worldSettings) return '';
    var world = worldSettings.world_meta || worldSettings;
    var parts = [];
    var coveredKeys = { '整体风格': 1, '时代背景': 1, '核心设定': 1, '氛围基调': 1, '叙事风格': 1, '时代环境': 1, '世界规则': 1 };

    // freeform
    var freeform = world.freeform || {};
    for (var key in freeform) {
      if (!freeform.hasOwnProperty(key) || coveredKeys[key]) continue;
      var val = freeform[key] || '';
      var kws = [key].concat(_extractKeywords(val).slice(0, 5));
      for (var i = 0; i < kws.length; i++) {
        if (kws[i] && kws[i].length >= 2 && text.indexOf(kws[i]) >= 0) {
          parts.push('- ' + key + ': ' + val);
          break;
        }
      }
    }

    // 叙事风格关键词触发
    var ns = worldSettings.narrative_style || (world && world.narrative_style) || {};
    for (var f in ns) {
      if (!ns.hasOwnProperty(f) || !ns[f]) continue;
      var nsKws = _extractKeywords(ns[f]);
      for (var j = 0; j < nsKws.length; j++) {
        if (text.indexOf(nsKws[j]) >= 0) {
          parts.push('- 叙事风格.' + f + ': ' + ns[f]);
          break;
        }
      }
    }

    // 时代环境关键词触发
    var era = worldSettings.era || (world && world.era) || {};
    for (var ef in era) {
      if (!era.hasOwnProperty(ef) || !era[ef]) continue;
      var eraKws = _extractKeywords(era[ef]);
      for (var x = 0; x < eraKws.length; x++) {
        if (text.indexOf(eraKws[x]) >= 0) {
          parts.push('- 时代环境.' + ef + ': ' + era[ef]);
          break;
        }
      }
    }

    // 世界规则关键词触发
    var rules = worldSettings.world_rules || (world && world.world_rules) || [];
    for (var ri = 0; ri < rules.length; ri++) {
      var r = rules[ri];
      var ruleStr = typeof r === 'string' ? r :
        (r && typeof r === 'object' ? (r.key || '') + ' ' + (r.val || '') : String(r));
      var rKws = _extractKeywords(ruleStr);
      for (var y = 0; y < rKws.length; y++) {
        if (text.indexOf(rKws[y]) >= 0) {
          parts.push('- 世界规则: ' + ruleStr);
          break;
        }
      }
    }

    return parts.length ? '## 触发的相关设定（Lorebook）\n' + parts.join('\n') : '';
  }

  // ═══════════════════════════════════════════
  // 构建人物档案上下文（简化版，供 offline-ai 使用）
  // ═══════════════════════════════════════════
  function _buildCharacterContext(characters, outlineText) {
    if (!characters || !characters.length) return '';

    // 按名字出现在大纲中筛选相关角色
    var relevantChars = [];
    for (var i = 0; i < characters.length; i++) {
      var c = characters[i];
      var name = c.name || '';
      if (name && outlineText && outlineText.indexOf(name) >= 0) {
        relevantChars.push(c);
      }
    }
    relevantChars = relevantChars.slice(0, 6);
    if (!relevantChars.length) return '';

    var lines = [];
    for (var j = 0; j < relevantChars.length; j++) {
      var ch = relevantChars[j];
      var cname = ch.name || '';
      var line = '- ' + cname + '（' + (ch.faction || '') + '·' + (ch.importance || '') + '）: ';
      var details = [];
      if (ch.personality) details.push('性格[' + ch.personality + ']');
      if (ch.obsession) details.push('执念[' + ch.obsession + ']');
      if (ch.weakness) details.push('软肋[' + ch.weakness + ']');
      if (ch.goal) details.push('目标[' + ch.goal + ']');
      if (ch.goals && ch.goals.length) details.push('目标[' + ch.goals.map(function(g){return typeof g==='object'?g.text:g;}).join(', ') + ']');
      line += details.join(' ');
      // 羁绊
      var bonds = ch.bonds;
      if (bonds && bonds.length) {
        var bondStrs = [];
        for (var bi = 0; bi < bonds.length; bi++) {
          if (bonds[bi] && typeof bonds[bi] === 'object') {
            bondStrs.push((bonds[bi].target || '') + ':' + (bonds[bi].relation || ''));
          }
        }
        if (bondStrs.length) line += ' | 羁绊[' + bondStrs.join(', ') + ']';
      }
      lines.push(line);
    }

    return '## 本章人物档案（严格遵守人设）\n' + lines.join('\n');
  }

  // ═══════════════════════════════════════════
  // 构建伏笔状态上下文
  // ═══════════════════════════════════════════
  function _buildForeshadowContext(chapterIndex, hooks) {
    if (!hooks || !hooks.length) return '';
    var chNum = chapterIndex + 1;
    var lines = [];

    for (var i = 0; i < hooks.length; i++) {
      var h = hooks[i];
      var status = h.status || '';
      var expected = h.expected_recovery_chapter || 0;
      if (status === 'planted' || status === 'active') {
        if (expected === chNum || (expected > 0 && expected < chNum)) {
          lines.push('- [可回收] 第' + (h.planted_chapter || 0) + '章埋下: ' + (h.content || ''));
        }
      } else if (status === 'recovered' && (h.recovered_chapter || 0) === chNum) {
        lines.push('- [本章已回收] 第' + (h.planted_chapter || 0) + '章埋下: ' + (h.content || ''));
      }
    }

    return lines.length ? '## 伏笔状态（第' + chNum + '章）\n' + lines.join('\n') : '';
  }

  // ═══════════════════════════════════════════
  // 后处理：削减AI味特征（完整移植 _post_process）
  // 注意：只做不破坏语法的替换，不做生硬替换
  // ═══════════════════════════════════════════
  function postProcess(content) {
    if (!content) return content;

    // 0. 去掉开头的章节标题（AI经常错误输出"# 第X章"或"第X章"）
    content = content.replace(/^([#\s]*)第\d+章[：:]*[^\n]*\n+/, '');
    content = content.replace(/^([#\s]*)Chapter\s*\d+[：:]*[^\n]*\n+/i, '');
    // 处理标题和正文在同一行的情况
    content = content.replace(/^第\d+章[：:]*/, '');
    content = content.replace(/^Chapter\s*\d+[：:]*/i, '');
    content = content.replace(/^\n+/, '').replace(/^\s+/, '');

    // 1. 削减"的"字密度：目标 <25/千字
    var charCount = content.length;
    var deCount = _countSub(content, '的');
    var deDensity = charCount > 0 ? deCount / (charCount / 1000) : 0;
    if (deDensity > 25) {
      var excess = Math.floor(deCount - 25 * (charCount / 1000));
      var replacements = [
        ['他的手', '他手'], ['她的手', '她手'], ['他的眼', '他眼'],
        ['他的脸', '他脸'], ['她的脸', '她脸'], ['他的心', '他心'],
        ['他的身', '他身'], ['她的身', '她身'], ['他的脚', '他脚'],
        ['白色的光', '白光'], ['黑色的影', '黑影'], ['蓝色的光', '蓝光'],
        ['红色的光', '红光'], ['银色的光', '银光'], ['金色的光', '金光'],
        ['微弱的光', '微光'], ['刺眼的光', '强光'],
        ['安静的', '寂静'], ['沉默的', '无声'],
        ['巨大的', '极大'], ['强烈的', '猛烈'],
        ['冰冷的', '冰冷'], ['温暖的', '温热'],
        ['熟悉的', '熟稔'], ['陌生的', '生疏'],
        ['缓慢的', '缓缓'], ['迅速的', '急速'],
        ['低沉的', '低哑'], ['尖锐的', '尖利'],
        ['古老的', '古旧'], ['年轻的', '年少'],
        ['深刻的', '深切'], ['明显的', '显著'],
        ['突然的', '骤然'], ['短暂的', '短促'],
        ['不安的', '惴惴'], ['紧张的', '绷紧'],
        ['平静的', '宁和'], ['混乱的', '纷乱'],
        ['空旷的', '空荡'], ['狭窄的', '逼仄'],
        ['的月光', '月华'], ['的阳光', '日光'],
        ['的声音', '声响'], ['的气息', '气息'],
        ['的目光', '视线'], ['的笑容', '笑意'],
        ['的身影', '身形'], ['的动作', '举动'],
        ['的感觉', '感觉'], ['的样子', '模样'],
        ['的时候', '时'], ['的地方', '处'],
        ['的话', '之言'], ['的事', '之事'],
        ['的人', '者'], ['的间', '间'],
        ['的震动', '震颤'], ['的颤栗', '战栗']
      ];
      var replaced = 0;
      for (var i = 0; i < replacements.length && replaced < excess; i++) {
        while (content.indexOf(replacements[i][0]) >= 0 && replaced < excess) {
          content = content.replace(replacements[i][0], replacements[i][1]);
          replaced++;
        }
      }
      // 如还不够，每隔2个"的"将1个替换为"之"（仅当前后均为汉字时）
      if (replaced < excess) {
        var positions = [];
        var pos = 0;
        while ((pos = content.indexOf('的', pos)) !== -1) {
          positions.push(pos);
          pos++;
        }
        for (var k = 0; k < positions.length && replaced < excess; k++) {
          if (k % 3 === 0) {
            var p = positions[k];
            var before = p > 0 ? content.charAt(p - 1) : '';
            var after = p + 1 < content.length ? content.charAt(p + 1) : '';
            if (before && after && _isChinese(before) && _isChinese(after)) {
              content = content.substring(0, p) + '之' + content.substring(p + 1);
              replaced++;
            }
          }
        }
      }
    }

    // 2. 削减连接词
    var connectorMap = {
      '然而，': '但', '然而': '但', '因此，': '所以', '因此': '所以',
      '于是，': '', '于是': '', '紧接着，': '', '紧接着': '随后',
      '与此同时，': '', '与此同时': '', '事实上，': '', '事实上': '',
      '实际上，': '', '实际上': '', '换句话说，': '', '换句话说': '',
      '总而言之，': '', '总而言之': '', '综上所述，': '', '综上所述': '',
      '由此可见，': '', '由此可见': ''
    };
    for (var old in connectorMap) {
      if (connectorMap.hasOwnProperty(old)) {
        content = content.split(old).join(connectorMap[old]);
      }
    }

    // 3. 削减"突然""忽然"等高频AI词（超出限额的用近义词替换）
    var aiWordsLimit = { '突然': 1, '忽然': 1, '仿佛': 1, '似乎': 2, '不禁': 1, '不由得': 1 };
    var synonyms = {
      '突然': ['猛地', '倏地', '骤然', '陡然'],
      '忽然': ['猛然', '倏然', '骤然', '陡然'],
      '仿佛': ['宛若', '恍若', '好似'],
      '似乎': ['好像', '好似', '看样子'],
      '不禁': ['忍不住', '不由'],
      '不由得': ['忍不住', '不由']
    };
    for (var word in aiWordsLimit) {
      if (!aiWordsLimit.hasOwnProperty(word)) continue;
      var count = _countSub(content, word);
      var limit = aiWordsLimit[word];
      if (count > limit) {
        var syns = synonyms[word] || [''];
        var synIdx = 0;
        for (var n = limit; n < count; n++) {
          var findPos = content.indexOf(word);
          if (findPos < 0) break;
          var syn = syns[synIdx % syns.length];
          content = content.substring(0, findPos) + syn + content.substring(findPos + word.length);
          synIdx++;
        }
      }
    }

    // 4. 清理连续空行
    content = content.replace(/\n{3,}/g, '\n\n');

    return content;
  }

  // ═══════════════════════════════════════════
  // 硬校验（基础版：禁词检查 + 长度检查）
  // ═══════════════════════════════════════════
  function runHardChecks(content, forbiddenWords) {
    var issues = [];
    if (!content) {
      issues.push('内容为空');
      return issues;
    }

    var wordList = forbiddenWords && forbiddenWords.length ? forbiddenWords : FORBIDDEN_WORDS;

    // 1. 禁词检查
    var foundWords = [];
    for (var i = 0; i < wordList.length; i++) {
      if (content.indexOf(wordList[i]) >= 0) foundWords.push(wordList[i]);
    }
    if (foundWords.length) {
      issues.push('使用了禁用词汇: ' + foundWords.join(', '));
    }

    // 2. 长度检查
    if (content.length < 500) {
      issues.push('内容过短，不足500字');
    }

    return issues;
  }

  // ═══════════════════════════════════════════
  // 导出为全局对象 window.AICommon
  // ═══════════════════════════════════════════
  global.AICommon = {
    // 常量
    FORBIDDEN_WORDS: FORBIDDEN_WORDS,
    FORBIDDEN_PLOTS: FORBIDDEN_PLOTS,

    // 工具函数
    _countSub: _countSub,
    _truncate: _truncate,
    _isChinese: _isChinese,
    _extractKeywords: _extractKeywords,
    _parseJSONLenient: _parseJSONLenient,

    // Prompt 构建相关
    _worldToPrompt: _worldToPrompt,
    _triggerLorebook: _triggerLorebook,
    _buildCharacterContext: _buildCharacterContext,
    _buildForeshadowContext: _buildForeshadowContext,

    // 后处理与校验
    postProcess: postProcess,
    runHardChecks: runHardChecks
  };

})(typeof window !== 'undefined' ? window : this);
