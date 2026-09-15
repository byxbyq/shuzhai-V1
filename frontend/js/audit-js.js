// ════════════════════════════════════════════════════════════════
// 书斋 V65 - 扩展审计模块 (JS 版)
// 移植自 backend/services/audit.py
// 纯规则检测，不消耗 Token
// 包含：1. AI味检测  2. 战力崩坏检测  3. 综合审计
// 导出：window.AuditJS
// ════════════════════════════════════════════════════════════════
(function (global) {
  'use strict';

  // ═══════════════════════════════════════════
  // 常量：AI味检测词表
  // ═══════════════════════════════════════════

  // AI 高频词 -> 每3千字最大允许次数（0 表示禁止出现）
  var AI_BUZZWORDS = {
    '忽然': 3, '突然': 3, '竟然': 2, '不禁': 2, '仿佛': 3,
    '似乎': 4, '不由得': 2, '莫名地': 1, '不知为何': 1,
    '一股暖流': 0, '心头一震': 0, '倒吸一口凉气': 1,
    '瞳孔放大': 0, '嘴角微微': 1, '微微一笑': 1,
    '眼中闪过一丝': 0, '攥紧拳头': 1
  };

  // 公式化转折（带 g 标志的正则数组）
  var FORMULAIC_TRANSITIONS = [
    /就在这时[，,]/g,
    /话音刚落[，,]/g,
    /话音未落[，,]/g,
    /还没等.{1,6}反应/g,
    /下一秒[，,]/g,
    /刹那间[，,]/g,
    /一瞬间[，,]/g,
    /电光火石之间/g
  ];

  // 叙述者越权（替读者下结论）
  var NARRATOR_OVERREACH = [
    /这证明了[，,]?/g,
    /这意味着[，,]?/g,
    /这说明了[，,]?/g,
    /不难看出[，,]?/g,
    /显然[，,]/g,
    /毫无疑问[，,]/g,
    /不言而喻[，,]/g,
    /可想而知[，,]/g
  ];

  // 塑料描写（过度对仗 / 排比，句式过于工整）
  var PLASTIC_PATTERNS = [
    /[，,].{2,8}[，,].{2,8}[，,].{2,8}[。.]/g
  ];

  // ═══════════════════════════════════════════
  // 常量：战力崩坏检测
  // ═══════════════════════════════════════════

  // 境界层级（18级，索引越大境界越高）
  var REALM_HIERARCHY = [
    '凡人', '觉醒', '入门', '初级', '中级', '高级',
    '超凡', '蜕变', '蜕变期', '入微', '化境', '巅峰',
    '仙', '神', '圣', '至尊', '创世', '归零'
  ];

  // 连接词表（AI 过度使用）
  var CONNECTORS = [
    '然而', '因此', '但是', '不过', '于是', '随后', '紧接着',
    '与此同时', '不仅如此', '事实上', '实际上', '换句话说',
    '总而言之', '综上所述', '由此可见'
  ];

  // 复活关键词
  var REVIVAL_KEYWORDS = ['复活', '重生', '苏醒', '诈尸', '未死', '还活着'];

  // 战胜句式（含两个捕获组：胜者、败者）
  var VICTORY_PATTERNS = [
    /(.{1,8})击败了(.{1,8})/g,
    /(.{1,8})战胜了(.{1,8})/g,
    /(.{1,8})杀了(.{1,8})/g
  ];

  // ─── 内部工具函数 ───

  // 保留 n 位小数（近似 Python round）
  function roundN(x, n) {
    if (!isFinite(x)) return 0;
    var p = Math.pow(10, n);
    return Math.round(x * p) / p;
  }

  // 统计子串出现次数（非重叠，等价 Python str.count）
  function countSub(str, sub) {
    if (!sub) return 0;
    var cnt = 0, idx = 0;
    while ((idx = str.indexOf(sub, idx)) !== -1) {
      cnt++;
      idx += sub.length;
    }
    return cnt;
  }

  // 用带 g 标志的正则统计匹配次数（不改变正则的 lastIndex）
  function countRegex(content, regex) {
    var m = content.match(regex);
    return m ? m.length : 0;
  }

  // 取带 g 标志正则的全部完整匹配字符串数组
  function matchAllStr(content, regex) {
    var m = content.match(regex);
    return m ? m : [];
  }

  // ════════════════════════════════════════════════════════════════
  // 1. AI 味检测
  // 输入：content (string)
  // 输出：{ score, level, ai_probability, ai_level, issues, summary, stats }
  // ════════════════════════════════════════════════════════════════
  function detectAiFlavor(content) {
    if (!content || content.length < 100) {
      return {
        score: 0, level: 'clean', issues: [], summary: 'content too short',
        stats: {}, ai_probability: 0, ai_level: 'minimal'
      };
    }

    var charCount = content.length;
    var scale = Math.max(charCount / 3000.0, 1.0);
    var issues = [];
    var totalDeduction = 0;

    // 统计变量提前声明（供末尾 stats 使用，等价 Python 的函数级作用域）
    var cv = 0;              // 突发性变异系数
    var ttr = 0;             // 2-gram 词汇多样性
    var paraCv = 0;          // 段落长度变异系数
    var meanLen = 0;         // 平均句长
    var connectorDensity = 0;
    var deDensity = 0;
    var transitionCount = 0;
    var overreachCount = 0;
    var plasticCount = 0;
    var charsClean = '';

    // ═══ Part A: 统计特征分析 ═══

    // 按句号/感叹号/问号/换行分句
    var rawSentences = content.split(/[。！？\n]+/);
    var sentences = [];
    for (var i = 0; i < rawSentences.length; i++) {
      var s = rawSentences[i].replace(/^\s+|\s+$/g, '');
      if (s.length > 2) sentences.push(s);
    }
    var sentenceLengths = [];
    for (var j = 0; j < sentences.length; j++) {
      sentenceLengths.push(sentences[j].length);
    }
    var nSentences = sentenceLengths.length;

    // A1. 突发性 Burstiness：人类写作句长差异大，AI 趋于均匀
    var burstinessScore = 0;
    if (nSentences > 10) {
      var sumLen = 0;
      for (var k = 0; k < sentenceLengths.length; k++) sumLen += sentenceLengths[k];
      meanLen = sumLen / nSentences;
      var variance = 0;
      for (var k2 = 0; k2 < sentenceLengths.length; k2++) {
        variance += Math.pow(sentenceLengths[k2] - meanLen, 2);
      }
      variance /= nSentences;
      var stdDev = Math.sqrt(variance);
      cv = meanLen > 0 ? stdDev / meanLen : 0;  // 变异系数

      // 人类写作 CV 通常 > 0.6，AI 通常 < 0.4
      if (cv < 0.3) {
        burstinessScore = 25;
        issues.push({
          type: 'low_burstiness',
          cv: roundN(cv, 3),
          message: '句子长度过于均匀(变异系数' + cv.toFixed(2) + ')，AI特征明显'
        });
      } else if (cv < 0.45) {
        burstinessScore = 15;
        issues.push({
          type: 'low_burstiness',
          cv: roundN(cv, 3),
          message: '句子长度较均匀(变异系数' + cv.toFixed(2) + ')，偏AI风格'
        });
      } else if (cv < 0.6) {
        burstinessScore = 7;
      }
      // cv >= 0.6 人类风格，不扣分
    }
    totalDeduction += burstinessScore;

    // A2. 词汇多样性 Type-Token Ratio（字符级 2-gram）
    charsClean = content.replace(/[^\u4e00-\u9fa5a-zA-Z]/g, '');
    if (charsClean.length > 200) {
      var bigrams = [];
      for (var bi = 0; bi < charsClean.length - 1; bi++) {
        bigrams.push(charsClean.substring(bi, bi + 2));
      }
      var uniqueBigrams = new Set(bigrams).size;
      var totalBigrams = bigrams.length;
      ttr = totalBigrams > 0 ? uniqueBigrams / totalBigrams : 0;

      // 中文文本 2-gram TTR 通常 0.55-0.75，AI 偏低
      if (ttr < 0.45) {
        totalDeduction += 15;
        issues.push({
          type: 'low_ttr',
          ttr: roundN(ttr, 3),
          message: '词汇多样性低(2-gram TTR=' + ttr.toFixed(2) + ')，用词重复率高'
        });
      } else if (ttr < 0.50) {
        totalDeduction += 8;
        issues.push({
          type: 'low_ttr',
          ttr: roundN(ttr, 3),
          message: '词汇多样性偏低(2-gram TTR=' + ttr.toFixed(2) + ')'
        });
      }
    }

    // A3. 段落长度均匀性：AI 段落长度趋同
    var rawParas = content.split('\n');
    var paragraphs = [];
    for (var pi = 0; pi < rawParas.length; pi++) {
      var p = rawParas[pi].replace(/^\s+|\s+$/g, '');
      if (p.length > 20) paragraphs.push(p);
    }
    var paraUniformityScore = 0;
    if (paragraphs.length > 5) {
      var paraLens = [];
      var paraSum = 0;
      for (var pl = 0; pl < paragraphs.length; pl++) {
        paraLens.push(paragraphs[pl].length);
        paraSum += paragraphs[pl].length;
      }
      var paraMean = paraSum / paragraphs.length;
      var paraVar = 0;
      for (var pv = 0; pv < paraLens.length; pv++) {
        paraVar += Math.pow(paraLens[pv] - paraMean, 2);
      }
      paraVar /= paragraphs.length;
      paraCv = paraMean > 0 ? Math.sqrt(paraVar) / paraMean : 0;

      if (paraCv < 0.25) {
        paraUniformityScore = 12;
        issues.push({
          type: 'uniform_paragraphs',
          cv: roundN(paraCv, 3),
          message: '段落长度过于均匀(变异系数' + paraCv.toFixed(2) + ')，AI排版特征'
        });
      } else if (paraCv < 0.40) {
        paraUniformityScore = 6;
      }
    }
    totalDeduction += paraUniformityScore;

    // A4. 句式重复度：AI 倾向使用相似句首结构
    var patternRepetitionScore = 0;
    if (nSentences > 15) {
      var sentenceStarts = [];
      for (var ss = 0; ss < sentences.length; ss++) {
        if (sentences[ss].length >= 3) sentenceStarts.push(sentences[ss].substring(0, 3));
      }
      // 等价 Python collections.Counter
      var startCounter = {};
      for (var sc = 0; sc < sentenceStarts.length; sc++) {
        var key = sentenceStarts[sc];
        startCounter[key] = (startCounter[key] || 0) + 1;
      }
      var repeatedStarts = 0;
      var counterKeys = Object.keys(startCounter);
      for (var ck = 0; ck < counterKeys.length; ck++) {
        if (startCounter[counterKeys[ck]] >= 3) repeatedStarts++;
      }
      if (repeatedStarts >= 3) {
        patternRepetitionScore = 10;
        // 找最高频句首（等价 Counter.most_common(1)[0]）
        var topPattern = null, topCount = 0;
        for (var tk = 0; tk < counterKeys.length; tk++) {
          if (startCounter[counterKeys[tk]] > topCount) {
            topCount = startCounter[counterKeys[tk]];
            topPattern = counterKeys[tk];
          }
        }
        issues.push({
          type: 'pattern_repetition',
          message: '句首模式重复过多，"' + topPattern + '…"出现' + topCount + '次'
        });
      } else if (repeatedStarts >= 2) {
        patternRepetitionScore = 5;
      }
    }
    totalDeduction += patternRepetitionScore;

    // A5. 连接词密度：AI 过度使用连接词
    var connectorCount = 0;
    for (var ci = 0; ci < CONNECTORS.length; ci++) {
      connectorCount += countSub(content, CONNECTORS[ci]);
    }
    connectorDensity = connectorCount / (charCount / 1000);
    var connectorScore = 0;
    if (connectorDensity > 5) {
      connectorScore = Math.min(12, Math.floor((connectorDensity - 5) * 3));
      issues.push({
        type: 'connector_overuse',
        count: connectorCount,
        density: roundN(connectorDensity, 1),
        message: '连接词密度过高(' + connectorDensity.toFixed(1) + '/千字)，AI行文特征'
      });
    }
    totalDeduction += connectorScore;

    // A6. "的"字密度：AI 生成中文 "的" 字频率偏高
    var deCount = countSub(content, '的');
    deDensity = deCount / (charCount / 1000);
    var deScore = 0;
    if (deDensity > 35) {
      deScore = Math.min(10, Math.floor((deDensity - 35) * 1.5));
      issues.push({
        type: 'high_de_density',
        density: roundN(deDensity, 1),
        message: '"的"字密度过高(' + deDensity.toFixed(1) + '/千字)，AI行文特征'
      });
    }
    totalDeduction += deScore;

    // ═══ Part B: 规则检测 ═══

    // B1. Buzzword 密度
    var buzzKeys = Object.keys(AI_BUZZWORDS);
    for (var bw = 0; bw < buzzKeys.length; bw++) {
      var word = buzzKeys[bw];
      var maxPer3k = AI_BUZZWORDS[word];
      var wCount = countSub(content, word);
      if (wCount === 0) continue;
      var allowed = maxPer3k * scale;
      if (maxPer3k === 0 && wCount > 0) {
        // 禁用词，出现即扣分
        var deductionF = Math.min(15, 5 + wCount * 3);
        issues.push({
          type: 'buzzword_forbidden',
          word: word,
          count: wCount,
          message: '[forbidden] word "' + word + '" appears ' + wCount + ' times'
        });
        totalDeduction += deductionF;
      } else if (wCount > allowed) {
        var excess = Math.floor(wCount - allowed);
        var deductionN = Math.min(10, excess * 2);
        issues.push({
          type: 'buzzword_density',
          word: word,
          count: wCount,
          limit: Math.floor(allowed),
          message: 'word "' + word + '" appears ' + wCount + ' times (limit ' + Math.floor(allowed) + ' per 3k chars)'
        });
        totalDeduction += deductionN;
      }
    }

    // B2. 公式化转折
    transitionCount = 0;
    for (var ti = 0; ti < FORMULAIC_TRANSITIONS.length; ti++) {
      var tRe = FORMULAIC_TRANSITIONS[ti];
      tRe.lastIndex = 0;  // 重置，避免 g 标志残留
      var tMatches = matchAllStr(content, tRe);
      if (tMatches.length > 0) {
        transitionCount += tMatches.length;
        if (tMatches.length > 1) {
          issues.push({
            type: 'formulaic_transition',
            pattern: tRe.source,
            count: tMatches.length,
            message: 'formulaic transition repeated ' + tMatches.length + ' times'
          });
          totalDeduction += Math.min(5, tMatches.length * 2);
        }
      }
    }
    if (transitionCount > 3 * scale) {
      issues.push({
        type: 'transition_overuse',
        count: transitionCount,
        message: 'total formulaic transitions: ' + transitionCount + ', density too high'
      });
      totalDeduction += 5;
    }

    // B3. 叙述者越权
    overreachCount = 0;
    for (var ni = 0; ni < NARRATOR_OVERREACH.length; ni++) {
      var nRe = NARRATOR_OVERREACH[ni];
      nRe.lastIndex = 0;
      var nMatches = matchAllStr(content, nRe);
      if (nMatches.length > 0) {
        overreachCount += nMatches.length;
        issues.push({
          type: 'narrator_overreach',
          pattern: nMatches[0],
          count: nMatches.length,
          message: 'narrator overreach: "' + nMatches[0] + '" draws conclusion for reader'
        });
        totalDeduction += Math.min(8, nMatches.length * 3);
      }
    }

    // B4. 塑料描写
    plasticCount = 0;
    for (var pp = 0; pp < PLASTIC_PATTERNS.length; pp++) {
      var pRe = PLASTIC_PATTERNS[pp];
      pRe.lastIndex = 0;
      plasticCount += countRegex(content, pRe);
    }
    if (plasticCount > 5 * scale) {
      issues.push({
        type: 'plastic_prose',
        count: plasticCount,
        message: 'parallel/antithesis patterns: ' + plasticCount + ', too uniform'
      });
      totalDeduction += 5;
    }

    // B5. 单调句首（相邻句子句首相同）
    if (nSentences > 10) {
      var sameStart = 0;
      for (var si = 1; si < nSentences; si++) {
        if (sentences[si].substring(0, 2) === sentences[si - 1].substring(0, 2)) {
          sameStart++;
        }
      }
      if (sameStart > nSentences * 0.2) {
        var ratio = roundN(sameStart / nSentences, 2);
        issues.push({
          type: 'monotonous_sentence',
          count: sameStart,
          ratio: ratio,
          message: sameStart + ' consecutive sentences with same start (' + Math.floor(ratio * 100) + '%)'
        });
        totalDeduction += 5;
      }
    }

    // ═══ Part C: 综合评分 ═══

    var score = Math.min(100, totalDeduction);

    // 估算 AI 概率（基于统计特征）
    var aiProb = 0;
    if (nSentences > 10) {
      // CV 越低 AI 概率越高
      if (cv < 0.3) aiProb += 40;
      else if (cv < 0.4) aiProb += 25;
      else if (cv < 0.5) aiProb += 15;
      else if (cv < 0.6) aiProb += 5;
    }
    // TTR
    if (charsClean.length > 200) {
      if (ttr < 0.45) aiProb += 25;
      else if (ttr < 0.50) aiProb += 15;
      else if (ttr < 0.55) aiProb += 8;
    }
    // 段落均匀性
    if (paragraphs.length > 5) {
      if (paraCv < 0.25) aiProb += 15;
      else if (paraCv < 0.35) aiProb += 8;
    }
    // 连接词
    if (connectorDensity > 5) aiProb += 10;
    // "的"字密度
    if (deDensity > 35) aiProb += 8;

    aiProb = Math.min(99, aiProb);

    // 评分等级
    var level;
    if (score === 0) level = 'clean';
    else if (score <= 15) level = 'minor';
    else if (score <= 35) level = 'moderate';
    else level = 'heavy';

    // AI 概率等级
    var aiLevel;
    if (aiProb >= 70) aiLevel = 'high';
    else if (aiProb >= 40) aiLevel = 'medium';
    else if (aiProb >= 20) aiLevel = 'low';
    else aiLevel = 'minimal';

    // 摘要
    var summary = 'AI味评分: ' + score + '/100 (' + level + ')';
    summary += ' | 预估AI概率: ' + aiProb + '% (' + aiLevel + ')';
    if (issues.length > 0) {
      var topIssues = [];
      for (var ti2 = 0; ti2 < Math.min(3, issues.length); ti2++) {
        topIssues.push(issues[ti2].message);
      }
      summary += '. 主要问题: ' + topIssues.join('; ');
    }

    // 统计 buzzword 问题数
    var buzzwordTotal = 0;
    for (var bi3 = 0; bi3 < issues.length; bi3++) {
      if (issues[bi3].type.indexOf('buzzword') !== -1) buzzwordTotal++;
    }

    return {
      score: score,
      level: level,
      ai_probability: aiProb,
      ai_level: aiLevel,
      issues: issues,
      summary: summary,
      stats: {
        burstiness_cv: nSentences > 10 ? roundN(cv, 3) : 0,
        ttr: charsClean.length > 200 ? roundN(ttr, 3) : 0,
        para_cv: paragraphs.length > 5 ? roundN(paraCv, 3) : 0,
        connector_density: roundN(connectorDensity, 1),
        de_density: roundN(deDensity, 1),
        sentence_count: nSentences,
        avg_sentence_len: nSentences > 0 ? roundN(meanLen, 1) : 0,
        buzzword_total: buzzwordTotal,
        transition_total: transitionCount,
        overreach_total: overreachCount,
        plastic_total: plasticCount
      }
    };
  }

  // ════════════════════════════════════════════════════════════════
  // 2. 战力崩坏检测
  // 输入：content, chapterIndex, characters (Array<{name,realm,prev_realm,status}>)
  // 输出：{ score, level, issues, summary, realm_mentions }
  // ════════════════════════════════════════════════════════════════
  function detectPowerCollapse(content, chapterIndex, characters) {
    chapterIndex = chapterIndex || 0;
    characters = characters || null;

    if (!content) {
      return {
        score: 0, level: 'ok', issues: [],
        summary: 'no content', realm_mentions: {}
      };
    }

    var issues = [];
    var totalDeduction = 0;

    // 1. 境界跳跃 + 死亡角色复活
    if (characters && characters.length) {
      for (var ci = 0; ci < characters.length; ci++) {
        var ch = characters[ci] || {};
        var name = ch.name || '';
        var realm = ch.realm || '';
        var prevRealm = ch.prev_realm || '';

        // 境界跳跃检测
        if (realm && prevRealm) {
          var currIdx = REALM_HIERARCHY.indexOf(realm);
          var prevIdx = REALM_HIERARCHY.indexOf(prevRealm);
          if (currIdx >= 0 && prevIdx >= 0) {
            var jump = currIdx - prevIdx;
            if (jump > 2) {
              issues.push({
                type: 'realm_jump',
                character: name,
                from: prevRealm,
                to: realm,
                jump: jump,
                message: name + ' realm jumped from ' + prevRealm + ' to ' + realm + ' (' + jump + ' levels)'
              });
              totalDeduction += Math.min(20, jump * 5);
            }
          }
        }

        // 死亡角色复活检测
        var status = ch.status || '';
        if (status === 'dead' && name && content.indexOf(name) !== -1) {
          var hasRevival = false;
          for (var rk = 0; rk < REVIVAL_KEYWORDS.length; rk++) {
            if (content.indexOf(REVIVAL_KEYWORDS[rk]) !== -1) { hasRevival = true; break; }
          }
          if (!hasRevival) {
            issues.push({
              type: 'dead_revival',
              character: name,
              message: 'dead character ' + name + ' appears without revival description'
            });
            totalDeduction += 15;
          }
        }
      }
    }

    // 3. 正文境界提及统计
    var realmMentions = {};
    for (var ri = 0; ri < REALM_HIERARCHY.length; ri++) {
      var realmName = REALM_HIERARCHY[ri];
      var cnt = countSub(content, realmName);
      if (cnt > 0) realmMentions[realmName] = cnt;
    }

    // 4. 越级战胜检测
    for (var vi = 0; vi < VICTORY_PATTERNS.length; vi++) {
      var vRe = VICTORY_PATTERNS[vi];
      vRe.lastIndex = 0;
      var vm;
      // exec 循环提取捕获组（等价 Python re.findall 返回元组列表）
      while ((vm = vRe.exec(content)) !== null) {
        var winner = vm[1];
        var loser = vm[2];
        var winnerRealm = null;
        var loserRealm = null;
        for (var rli = 0; rli < REALM_HIERARCHY.length; rli++) {
          var rn = REALM_HIERARCHY[rli];
          if (winner.indexOf(rn) !== -1) winnerRealm = rn;
          if (loser.indexOf(rn) !== -1) loserRealm = rn;
        }
        if (winnerRealm && loserRealm) {
          var wIdx = REALM_HIERARCHY.indexOf(winnerRealm);
          var lIdx = REALM_HIERARCHY.indexOf(loserRealm);
          if (lIdx - wIdx > 2) {
            var wTrim = winner.replace(/^\s+|\s+$/g, '');
            var lTrim = loser.replace(/^\s+|\s+$/g, '');
            issues.push({
              type: 'power_mismatch',
              winner: wTrim,
              loser: lTrim,
              winner_realm: winnerRealm,
              loser_realm: loserRealm,
              message: wTrim + '(' + winnerRealm + ') defeated ' + lTrim + '(' + loserRealm + ') - cross-level victory'
            });
            totalDeduction += 10;
          }
        }
      }
    }

    var score = Math.min(100, totalDeduction);
    var level;
    if (score === 0) level = 'ok';
    else if (score <= 20) level = 'warning';
    else level = 'serious';

    var summary = 'Power consistency: ' + (100 - score) + '/100 (' + level + ')';
    if (issues.length > 0) {
      var top = [];
      for (var it = 0; it < Math.min(3, issues.length); it++) top.push(issues[it].message);
      summary += '. Issues: ' + top.join('; ');
    }

    return {
      score: score,
      level: level,
      issues: issues,
      summary: summary,
      realm_mentions: realmMentions
    };
  }

  // ════════════════════════════════════════════════════════════════
  // 3. 综合审计
  // 输入：content, chapterIndex, characters, overdueHooks (Array<{content,chapter}>)
  //   权重：AI味(0.5) + 战力(0.3) + 逾期伏笔(0.2)
  // 输出：{ ai_flavor, power_collapse, overdue_hooks, overall_score,
  //        overall_level, all_issues, summary }
  // ════════════════════════════════════════════════════════════════
  function runExtendedAudit(content, chapterIndex, characters, overdueHooks) {
    chapterIndex = chapterIndex || 0;
    characters = characters || null;
    overdueHooks = overdueHooks || null;

    var aiResult = detectAiFlavor(content);
    var powerResult = detectPowerCollapse(content, chapterIndex, characters);

    var allIssues = aiResult.issues.concat(powerResult.issues);

    // ─── 调用全部移植的 _detect_* 维度 ───
    var dimFns = [
      _detectDialogueFragmentation,
      _detectEmotionSuspension,
      _detectDescriptionMonotony,
      _detectIdiomAbuse,
      _detectOverModification,
      _detectPovDrift,
      _detectWaterContent,
      _detectLogicGaps,
      _detectClimaxMissing,
      _detectToolCharacter,
      _detectParagraphHealth,
      _detectInfoDensity
    ];
    if (typeof _detectCharacterBreak === 'function') {
      allIssues = allIssues.concat(_detectCharacterBreak(content, characters));
    }
    if (typeof _detectOpeningEngagement === 'function') {
      allIssues = allIssues.concat(_detectOpeningEngagement(content));
    }
    dimFns.forEach(function(fn) {
      if (typeof fn === 'function') {
        try { allIssues = allIssues.concat(fn(content)); } catch (e) {}
      }
    });

    // 逾期伏笔
    var hookIssues = [];
    if (overdueHooks && overdueHooks.length) {
      for (var hi = 0; hi < overdueHooks.length; hi++) {
        var hook = overdueHooks[hi] || {};
        var hookText = (hook.content || '').substring(0, 30);
        var hookCh = (hook.chapter !== undefined && hook.chapter !== null) ? hook.chapter : '?';
        hookIssues.push({
          type: 'overdue_foreshadowing',
          hook: hookText,
          set_at: hookCh,
          message: 'overdue foreshadowing from chapter ' + hookCh + ': ' + hookText + '...'
        });
      }
    }
    allIssues = allIssues.concat(hookIssues);

    // 综合评分
    var aiScore = aiResult.score;
    var powerScore = powerResult.score;
    var hookPenalty = hookIssues.length * 5;
    var overall = Math.min(100, aiScore * 0.5 + powerScore * 0.3 + hookPenalty * 0.2);

    var level;
    if (overall <= 15) level = 'pass';
    else if (overall <= 40) level = 'review';
    else level = 'fail';

    var summary = 'Extended audit: ' + roundN(overall, 1) + '/100 (' + level + ')';
    summary += ' | AI flavor: ' + aiResult.score;
    summary += ' | Power: ' + powerResult.score;
    summary += ' | Hooks: ' + hookIssues.length;

    return {
      ai_flavor: aiResult,
      power_collapse: powerResult,
      overdue_hooks: hookIssues,
      overall_score: roundN(overall, 1),
      overall_level: level,
      all_issues: allIssues,
      summary: summary
    };
  }

  // ═══════════════════════════════════════════
  // 导出为全局对象
  // ═══════════════════════════════════════════
  global.AuditJS = {
    // 检测函数
    detectAiFlavor: detectAiFlavor,
    detectPowerCollapse: detectPowerCollapse,
    runExtendedAudit: runExtendedAudit,
    // 暴露常量便于外部引用
    AI_BUZZWORDS: AI_BUZZWORDS,
    FORMULAIC_TRANSITIONS: FORMULAIC_TRANSITIONS,
    NARRATOR_OVERREACH: NARRATOR_OVERREACH,
    PLASTIC_PATTERNS: PLASTIC_PATTERNS,
    REALM_HIERARCHY: REALM_HIERARCHY,
    CONNECTORS: CONNECTORS
  };

})(typeof window !== 'undefined' ? window : this);
