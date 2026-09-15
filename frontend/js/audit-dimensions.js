// ════════════════════════════════════════════════════════════════
// 维度 14-27+：从 audit.py 移植的规则检测函数
// 追加到现有 AuditJS 对象中
// ════════════════════════════════════════════════════════════════

// ─── 内部工具（仅本模块使用）───
var _lineNr = function(content, pos) {
  return content.substring(0, pos).split('\n').length;
};
var _ctx = function(content, pos, span) {
  span = span || 20;
  return content.substring(Math.max(0, pos - span), Math.min(content.length, pos + span));
};

// ─── 维度21: 对话碎片化 ───
var _detectDialogueFragmentation = function(content) {
  var issues = [];
  var matches = content.match(/[""\u201c\u201d\u300c\u300d\u300e\u300f\u2018\u2019](.*?)[""\u201c\u201d\u300c\u300d\u300e\u300f\u2018\u2019]/g);
  if (!matches || matches.length < 5) return issues;
  var total = matches.length;
  var shortCount = 0;
  var shortSamples = [];
  for (var i = 0; i < matches.length; i++) {
    // strip quotes
    var inner = matches[i].replace(/^[""\u201c\u300c\u300e\u2018]/, '').replace(/[""\u201d\u300d\u300f\u2019]$/, '');
    if (inner.length < 10) {
      shortCount++;
      if (shortSamples.length < 5) {
        var pos = content.indexOf(matches[i]);
        shortSamples.push({ line: _lineNr(content, pos), offset: pos, matched: inner.slice(0,20), context: _ctx(content, pos) });
      }
    }
  }
  var ratio = shortCount / total;
  if (ratio > 0.8) {
    issues.push({
      type: 'dialogue_fragmentation', dimension: 21, category: 'character',
      total_dialogues: total, short_ratio: Math.round(ratio * 100),
      locations: shortSamples,
      message: '对话过于碎片化：' + Math.round(ratio*100) + '%的对话长度<10字（' + shortCount + '条/' + total + '条），建议丰富对话内容'
    });
  }
  return issues;
};

// ─── 维度22: 情感悬浮 ───
var _detectEmotionSuspension = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var words = ['感到','觉得','认为','心想','感觉','想着','思考','思索','意识到','明白到'];
  var total = 0, locs = [];
  words.forEach(function(w) {
    var idx = 0;
    while ((idx = content.indexOf(w, idx)) !== -1) {
      total++; locs.push({ line: _lineNr(content, idx), offset: idx, matched: w, context: _ctx(content, idx) });
      idx += w.length;
    }
  });
  var density = total / (cc / 1000);
  if (density > 5) {
    issues.push({
      type: 'emotion_suspension', dimension: 22, category: 'character',
      count: total, density: roundN(density, 1), locations: locs.slice(0, 10),
      message: '缺乏情境化情感表达：抽象心理词密度' + density.toFixed(1) + '/千字，建议用动作/场景/对话替代'
    });
  }
  return issues;
};

// ─── 维度23: 描写单调 ───
var _detectDescriptionMonotony = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var visual = ['看到','看见','望去','望见','瞧见','看去','盯着','注视','目光','眼中','眼帘','映入','眼前','看起来','看上去'];
  var auditory = ['听到','听见','聆听','耳边','声音','传来','响起','回荡','响彻','嗡嗡','震耳'];
  var olfactory = ['闻到','嗅到','气味','香味','臭味','芬芳','清新','刺鼻','腥味','香气'];
  var tactile = ['摸到','触到','碰到','凉意','温热','冰冷','粗糙','光滑','柔软','坚硬','刺痛','麻木'];
  var vc = 0, ac = 0, oc = 0, tc = 0;
  visual.forEach(function(w) { vc += countSub(content, w); });
  auditory.forEach(function(w) { ac += countSub(content, w); });
  olfactory.forEach(function(w) { oc += countSub(content, w); });
  tactile.forEach(function(w) { tc += countSub(content, w); });
  var total = vc + ac + oc + tc;
  if (total > 0 && vc / total > 0.9) {
    issues.push({
      type: 'description_monotony', dimension: 23, category: 'language',
      visual_ratio: Math.round(vc/total*100), visual: vc, auditory: ac, olfactory: oc, tactile: tc,
      message: '描写单调：视觉描写占比' + Math.round(vc/total*100) + '%（视觉' + vc + '次/听觉' + ac + '次/嗅觉' + oc + '次/触觉' + tc + '次），建议增加多感官描写'
    });
  }
  return issues;
};

// ─── 维度24: 成语滥用 ───
var _detectIdiomAbuse = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var idioms = ['不可思议','天衣无缝','显而易见','不言而喻','众所周知','毋庸置疑','无与伦比','无可厚非','不可否认','毫无疑问','前所未有','史无前例','惊天动地','翻天覆地','铺天盖地','势不可挡','势如破竹','一鸣惊人','一帆风顺','一石二鸟','一举两得','一箭双雕','万无一失','千钧一发','千载难逢','百折不挠','百思不得其解'];
  var total = 0, locs = [];
  idioms.forEach(function(w) {
    var cnt = countSub(content, w);
    if (cnt > 0) {
      total += cnt;
      var idx = 0;
      while ((idx = content.indexOf(w, idx)) !== -1 && locs.length < 10) {
        locs.push({ line: _lineNr(content, idx), offset: idx, matched: w, context: _ctx(content, idx) });
        idx += w.length;
      }
    }
  });
  var density = total / (cc / 1000);
  if (density > 3) {
    issues.push({
      type: 'idiom_abuse', dimension: 24, category: 'language',
      count: total, density: roundN(density, 1), locations: locs,
      message: '成语俗语滥用：常见成语密度' + density.toFixed(1) + '/千字，建议用原创表达替代惯用成语'
    });
  }
  return issues;
};

// ─── 维度25: 过度修饰 ───
var _detectOverModification = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var matches = content.match(/[\u4e00-\u9fa5]{1,3}地/g);
  if (!matches) return issues;
  var deCount = matches.length;
  var density = deCount / (cc / 1000);
  if (density > 15) {
    var locs = [];
    var idx = 0, re = /[\u4e00-\u9fa5]{1,3}地/g, m;
    while ((m = re.exec(content)) && locs.length < 10) {
      locs.push({ line: _lineNr(content, m.index), offset: m.index, matched: m[0], context: _ctx(content, m.index) });
    }
    issues.push({
      type: 'over_modification', dimension: 25, category: 'language',
      count: deCount, density: roundN(density, 1), locations: locs,
      message: '修饰过度："地"字副词密度' + density.toFixed(1) + '/千字，建议用动作描写替代副词修饰'
    });
  }
  return issues;
};

// ─── 维度26: 视角漂移 ───
var _detectPovDrift = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var firstPerson = (content.match(/我(?!们)/g) || []).length;
  var secondPerson = (content.match(/你(?!们)/g) || []).length;
  var thirdHe = (content.match(/他(?!们)/g) || []).length;
  var thirdShe = (content.match(/她(?!们)/g) || []).length;
  var thirdPerson = thirdHe + thirdShe;

  // 第一/第三混用
  if (firstPerson > 5 && thirdPerson > 5) {
    var ratio = firstPerson / Math.max(thirdPerson, 1);
    if (ratio > 0.3 && ratio < 3.0) {
      issues.push({
        type: 'pov_drift', dimension: 26, category: 'language',
        first_person_count: firstPerson, third_person_count: thirdPerson,
        message: '视角漂移：第一人称"我"(' + firstPerson + '次)与第三人称"他/她"(' + thirdPerson + '次)混用，建议统一叙述视角'
      });
    }
  }

  // 他/她段落内混用
  var paras = content.split('\n').filter(function(p) { return p.trim().length > 30; });
  var mixedCount = 0;
  paras.forEach(function(p) {
    var he = (p.match(/他(?!们)/g) || []).length;
    var she = (p.match(/她(?!们)/g) || []).length;
    if (he >= 1 && she >= 1 && he + she >= 3) mixedCount++;
  });
  if (mixedCount > 0) {
    issues.push({
      type: 'pov_drift', dimension: 26, category: 'language',
      message: '视角漂移：' + mixedCount + '个段落内"他"与"她"性别视角混用，可能视角切换过于频繁'
    });
  }

  // 第二人称混入
  if (secondPerson > 3) {
    issues.push({
      type: 'pov_drift', dimension: 26, category: 'language',
      second_person_count: secondPerson,
      message: '视角漂移：第二人称"你"出现' + secondPerson + '次，非第二人称小说中可能破坏代入感'
    });
  }
  return issues;
};

// ─── 维度27: 水文检测 ───
var _detectWaterContent = function(content) {
  var issues = [];
  var paras = content.split('\n').filter(function(p) { return p.trim().length > 20; });
  if (paras.length < 3) return issues;

  var hasDialogue = function(p) { return /[""\u201c\u201d\u300c\u300d\u300e\u300f]/.test(p); };
  var actionWords = ['打','走','跑','跳','飞','杀','砍','刺','击','挥','踢','推','拉','站','坐','躺','冲','退','闪','躲','拍','敲','拔','抽','举','拿','放','扔','丢','砸','摔','开','关','进','出'];
  var hasAction = function(p) { return actionWords.some(function(kw) { return p.indexOf(kw) !== -1; }); };

  var waterIdx = [];
  for (var i = 0; i < paras.length; i++) {
    if (!hasDialogue(paras[i]) && !hasAction(paras[i]) && paras[i].length > 50) waterIdx.push(i);
  }

  var groups = [], cur = [];
  for (var j = 0; j < waterIdx.length; j++) {
    if (cur.length === 0 || waterIdx[j] === cur[cur.length-1] + 1) {
      cur.push(waterIdx[j]);
    } else {
      if (cur.length >= 3) groups.push(cur.slice());
      cur = [waterIdx[j]];
    }
  }
  if (cur.length >= 3) groups.push(cur);

  groups.forEach(function(g) {
    var locs = g.map(function(pi) {
      var pos = content.indexOf(paras[pi].substring(0, 30));
      return { line: _lineNr(content, pos>=0?pos:0), offset: pos>=0?pos:0, matched: paras[pi].substring(0,30), context: _ctx(content, pos>=0?pos:0) };
    });
    issues.push({
      type: 'water_content', dimension: 27, category: 'language',
      count: g.length, locations: locs,
      message: '可能存在水文：连续' + g.length + '段（段落' + (g[0]+1) + '-' + (g[g.length-1]+1) + '）无对话/无动作推进，建议精简或增加情节'
    });
  });
  return issues;
};

// ─── 维度17: 逻辑漏洞 ───
var _detectLogicGaps = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var gapPatterns = [
    { re: /.{1,8}(突然|忽然|莫名其妙|无缘无故|凭空).{1,10}(出现|消失|来|去)/g, label: '事件因果缺失' },
    { re: /.{1,4}(明明|显然|显然地).{1,10}(却|但|然而)/g, label: '矛盾未解释' },
    { re: /.{1,4}(怎么|为何|为什么)(会|能|可以)/g, label: '未解释的动机' }
  ];
  var total = 0, locs = [];
  gapPatterns.forEach(function(pt) {
    pt.re.lastIndex = 0;
    var m;
    while ((m = pt.re.exec(content)) && locs.length < 10) {
      total++;
      locs.push({ line: _lineNr(content, m.index), offset: m.index, matched: m[0], context: _ctx(content, m.index, 30), label: pt.label });
    }
  });
  if (total > 3) {
    issues.push({
      type: 'logic_gaps', dimension: 17, category: 'plot',
      count: total, locations: locs,
      message: '逻辑漏洞嫌疑：检测到' + total + '处因果缺失/矛盾未解释/未解释动机，请确认情节合理性'
    });
  }
  return issues;
};

// ─── 维度16: 高潮缺失 ───
var _detectClimaxMissing = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 500) return issues;
  var climaxWords = ['决战','决斗','对决','死战','拼命','全力','巅峰','最强','终局','最终','决战','爆发','炸裂','轰然','倾尽','燃烧'];
  var found = climaxWords.some(function(w) { return content.indexOf(w) !== -1; });
  if (!found) {
    var emotionalPeaks = (content.match(/[！!]{2,}/g) || []).length;
    var actionDensity = (content.match(/(打|杀|砍|刺|爆|炸|裂)/g) || []).length / (cc / 1000);
    if (emotionalPeaks < 3 && actionDensity < 5) {
      issues.push({
        type: 'climax_missing', dimension: 16, category: 'plot',
        emotional_peaks: emotionalPeaks, action_density: roundN(actionDensity, 1),
        message: '高潮缺失嫌疑：未检测到高潮标志词，且情绪峰点(' + emotionalPeaks + ')和动作密度(' + actionDensity.toFixed(1) + '/千字)偏低，建议加强冲突场面或情感爆发'
      });
    }
  }
  return issues;
};

// ─── 维度20: 工具人 ───
var _detectToolCharacter = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 300) return issues;
  // 检测"突然走了"/"说完就走了"/"只负责"类短命角色模式
  var toolPatterns = [
    /.{1,5}(说完|说完后|之后|之后便).{1,8}(走|离开|消失|不见)/g,
    /(一个|一位|有个).{1,6}(路人|路人甲|跟班|手下|随从|摊主|店主|老汉|老妇|侍女|丫鬟|门卫|守卫|杂役)/g,
    /.{1,10}(只负责|只管|只是|纯粹).{1,10}(传话|带路|送信|通报|把风)/g
  ];
  var total = 0;
  toolPatterns.forEach(function(pt) {
    pt.lastIndex = 0;
    var m;
    while ((m = pt.re.exec(content)) && total < 5) { total++; }
  });
  if (total >= 2) {
    issues.push({
      type: 'tool_character', dimension: 20, category: 'character',
      count: total,
      message: '工具人嫌疑：检测到' + total + '处工具人模式（说完就走/纯路人/只负责XX），建议给配角增加独立动机或性格'
    });
  }
  return issues;
};

// ─── 维度18: 角色崩坏 ───
var _detectCharacterBreak = function(content, characters) {
  var issues = [];
  if (!characters || !characters.length) return issues;
  var cc = content.length;
  if (cc < 200) return issues;

  characters.forEach(function(ch) {
    var name = ch.name;
    if (!name || content.indexOf(name) === -1) return;
    var traits = (ch.traits || '').split(/[，,、]/);
    if (!traits.length || !traits[0].trim()) return;

    // 检测与特性的矛盾搭配
    var contradictions = [];
    traits.forEach(function(t) {
      t = t.trim();
      if (!t) return;
      if (t.indexOf('冷静') !== -1) {
        var cnt = (content.match(new RegExp(name + '.{0,20}(暴怒|失控|疯狂|崩溃)', 'g')) || []).length;
        if (cnt > 2) contradictions.push('冷静↔情绪失控(' + cnt + '处)');
      }
      if (t.indexOf('善良') !== -1) {
        var cnt = (content.match(new RegExp(name + '.{0,20}(残忍|狠毒|冷血|无情)', 'g')) || []).length;
        if (cnt > 0) contradictions.push('善良↔残忍行为(' + cnt + '处)');
      }
      if (t.indexOf('懦弱') !== -1 || t.indexOf('胆小') !== -1) {
        var cnt = (content.match(new RegExp(name + '.{0,20}(勇敢|无畏|果断|毫不', 'g')) || []).length;
        if (cnt > 2) contradictions.push('懦弱↔勇敢行为(' + cnt + '处)');
      }
    });

    if (contradictions.length) {
      issues.push({
        type: 'character_break', dimension: 18, category: 'character',
        character: name, contradictions: contradictions,
        message: '角色崩坏嫌疑：「' + name + '」行为与设定矛盾：' + contradictions.join(', ')
      });
    }
  });
  return issues;
};

// ─── 维度19: 开场吸引力 ───
var _detectOpeningEngagement = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;
  var first300 = content.substring(0, Math.min(300, cc));

  var hookWords = ['突然','忽然','砰','轰','啊','救命','死','血','刀','剑','杀','跑','追','喊','叫','冲','闯','破'];
  var hookCount = 0;
  hookWords.forEach(function(w) { hookCount += countSub(first300, w); });

  var boringStarts = [/天色.{1,20}(亮|晚|清晨)/.test(first300), /^(在|位于|处于|坐落)/.test(first300.trim()), /很久.{1,10}以前/.test(first300)];
  var boringCount = boringStarts.filter(Boolean).length;

  if (hookCount < 2 && boringCount > 0) {
    issues.push({
      type: 'opening_engagement', dimension: 19, category: 'plot',
      hook_words: hookCount, boring_patterns: boringCount,
      message: '开场吸引力不足：前300字检测到冲击性词汇仅' + hookCount + '个，且存在平淡开头模式，建议用冲突/悬念/冲击性画面开场'
    });
  }
  return issues;
};

// ─── 维度: 段落健康 ───
var _detectParagraphHealth = function(content) {
  var issues = [];
  var paras = content.split('\n').filter(function(p) { return p.trim().length > 0; });
  if (paras.length < 3) return issues;

  var overlong = paras.filter(function(p) { return p.trim().length > 400; });
  var tooShort = paras.filter(function(p) { var t = p.trim(); return t.length > 0 && t.length < 30; });
  var total = paras.length;

  if (overlong.length > total * 0.15) {
    issues.push({
      type: 'paragraph_health', dimension: 29, category: 'language',
      overlong_count: overlong.length, overlong_ratio: Math.round(overlong.length/total*100),
      message: '段落过长：' + overlong.length + '/' + total + '段超过400字（' + Math.round(overlong.length/total*100) + '%），建议拆分以提升可读性'
    });
  }
  if (tooShort.length > total * 0.3) {
    issues.push({
      type: 'paragraph_health', dimension: 29, category: 'language',
      tooshort_count: tooShort.length, tooshort_ratio: Math.round(tooShort.length/total*100),
      message: '段落过碎：' + tooShort.length + '/' + total + '段不足30字（' + Math.round(tooShort.length/total*100) + '%），建议合并以保持阅读节奏'
    });
  }
  return issues;
};

// ─── 维度: 信息密度 ───
var _detectInfoDensity = function(content) {
  var issues = [];
  var cc = content.length;
  if (cc < 200) return issues;

  var dialogueChars = 0;
  var m, re = /[""\u201c\u201d\u300c\u300d\u300e\u300f\u2018\u2019]/g;
  var inDialogue = false;
  var lastQuote = -1;
  // 简单估算对话比例
  var quotes = content.match(/[""\u201c\u300c\u300e\u2018]/g) || [];
  var closeQ = content.match(/[""\u201d\u300d\u300f\u2019]/g) || [];
  var dialogueRatio = Math.min(1, (quotes.length + closeQ.length) * 30 / cc); // 粗略估算

  var sceneChanges = (content.match(/[\*\-]{3,}|#{1,3}\s|——{3,}|…{3,}/g) || []).length;
  var density = (sceneChanges + 1) / (cc / 1000);

  if (density > 3) {
    issues.push({
      type: 'info_density', dimension: 30, category: 'structure',
      scene_changes: sceneChanges, density: roundN(density, 1),
      message: '场景切换过频：' + sceneChanges + '次场景切换，密度' + density.toFixed(1) + '/千字，可能影响叙事连贯性'
    });
  }
  return issues;
};

// ─── 注册到 AuditJS ───
(function() {
  if (typeof window === 'undefined' || !window.AuditJS) return;
  var A = window.AuditJS;
  A._detectDialogueFragmentation = _detectDialogueFragmentation;
  A._detectEmotionSuspension = _detectEmotionSuspension;
  A._detectDescriptionMonotony = _detectDescriptionMonotony;
  A._detectIdiomAbuse = _detectIdiomAbuse;
  A._detectOverModification = _detectOverModification;
  A._detectPovDrift = _detectPovDrift;
  A._detectWaterContent = _detectWaterContent;
  A._detectLogicGaps = _detectLogicGaps;
  A._detectClimaxMissing = _detectClimaxMissing;
  A._detectToolCharacter = _detectToolCharacter;
  A._detectCharacterBreak = _detectCharacterBreak;
  A._detectOpeningEngagement = _detectOpeningEngagement;
  A._detectParagraphHealth = _detectParagraphHealth;
  A._detectInfoDensity = _detectInfoDensity;
})();
