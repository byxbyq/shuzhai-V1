// ════════════════════════════════════════════════════════════════
// 书斋 V65 - 前端 AI 引擎 (ai-engine.js)
// 替代后端 generator.py + ai_client.py
// 所有 AI 调用通过 fetch 直连 DeepSeek / OpenAI 兼容 API
// 依赖：window.LocalDB（数据）、window.AuditJS（检测）、window.AICommon（共享代码）
// 导出：window.AIEngine
// ════════════════════════════════════════════════════════════════
(function (global) {
  'use strict';

  // ═══════════════════════════════════════════
  // 共享代码引用（来自 ai-common.js）
  // ═══════════════════════════════════════════
  var Common = global.AICommon || {};
  var FORBIDDEN_WORDS = Common.FORBIDDEN_WORDS || [];
  var FORBIDDEN_PLOTS = Common.FORBIDDEN_PLOTS || [];
  var _countSub = Common._countSub || function () { return 0; };
  var _truncate = Common._truncate || function (s) { return s || ''; };
  var _extractKeywords = Common._extractKeywords || function () { return []; };
  var _parseJSONLenient = Common._parseJSONLenient || function () { return null; };
  var _worldToPrompt = Common._worldToPrompt || function () { return ''; };
  var _triggerLorebook = Common._triggerLorebook || function () { return ''; };
  var _buildForeshadowContextCommon = Common._buildForeshadowContext || function () { return ''; };
  var postProcess = Common.postProcess || function (s) { return s; };

  function _buildForeshadowContext(chapterIndex, ledger) {
    var hooks = (ledger && ledger.foreshadowing) ? ledger.foreshadowing : [];
    return _buildForeshadowContextCommon(chapterIndex, hooks);
  }

  // ═══════════════════════════════════════════
  // 内部工具函数
  // ═══════════════════════════════════════════

  // 安全获取 LocalDB（容错）
  function _db() {
    if (global.LocalDB) return global.LocalDB;
    console.warn('[AIEngine] window.LocalDB 未加载');
    return null;
  }

  // 安全获取 AuditJS
  function _audit() {
    if (global.AuditJS) return global.AuditJS;
    console.warn('[AIEngine] window.AuditJS 未加载');
    return null;
  }



  // 规范化 base_url，返回完整的 chat completions 端点
  function _buildEndpoint(base_url) {
    var base = (base_url || 'https://api.deepseek.com').replace(/\/+$/, '');
    // 若已含 /v1 则直接追加 /chat/completions，否则追加 /v1/chat/completions
    if (/\/v\d+$/.test(base)) {
      return base + '/chat/completions';
    }
    return base + '/v1/chat/completions';
  }

  // 通过后端代理调用 AI（安全：API Key 仅存后端，前端不持有）
  async function _callBackendProxy(prompt, opts) {
    opts = opts || {};
    var server = (window._shuzhaiServer || '') + '/api/ai/proxy';
    try {
      var body = { prompt: prompt };
      if (opts.temperature !== undefined && opts.temperature !== null) body.temperature = opts.temperature;
      if (opts.max_tokens !== undefined && opts.max_tokens !== null) body.max_tokens = opts.max_tokens;
      var resp = await fetch(server, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!resp.ok) {
        var errText = '';
        try { errText = await resp.text(); } catch (e) {}
        return { ok: false, error: 'HTTP ' + resp.status + ': ' + _truncate(errText, 300) };
      }
      var data = await resp.json();
      if (data.ok && data.content !== undefined) {
        return { ok: true, reply: data.content };
      }
      return { ok: false, error: (data.error && data.error.message) || '代理返回异常' };
    } catch (e) {
      return { ok: false, error: '网络错误: ' + (e.message || String(e)) };
    }
  }





  // ═══════════════════════════════════════════
  // 从文本提取相关角色名（移植 _extract_relevant_characters）
  // ═══════════════════════════════════════════
  function _extractRelevantCharacters(text, ledger) {
    if (!ledger || !ledger.character_states) return [];
    var relevant = [];
    var names = Object.keys(ledger.character_states);
    for (var i = 0; i < names.length; i++) {
      if (text && text.indexOf(names[i]) >= 0) relevant.push(names[i]);
    }
    return relevant.slice(0, 8);
  }

  // ═══════════════════════════════════════════
  // Truth Ledger → 上下文（移植 TruthLedger.build_context）
  // ═══════════════════════════════════════════
  function _ledgerToContext(currentChapter, relevantChars, ledger) {
    var parts = [];
    if (!ledger) return '';

    // 角色当前状态
    if (relevantChars && relevantChars.length) {
      var charTexts = [];
      relevantChars.forEach(function (name) {
        var cs = ledger.character_states[name];
        if (!cs) return;
        var items = (cs.possessions && cs.possessions.length) ? cs.possessions.join(', ') : '无';
        charTexts.push(
          '【' + name + '】位置:' + (cs.location || '') + ' | 心绪:' + (cs.emotion || '') +
          ' | 健康:' + (cs.health || '正常') + ' | 境界:' + (cs.realm || '') +
          ' | 持有:' + items + ' | 最后出现:第' + (cs.last_seen_chapter || 0) + '章'
        );
      });
      if (charTexts.length) parts.push('## 角色当前状态\n' + charTexts.join('\n'));
    }

    // 待回收伏笔
    var activeHooks = (ledger.foreshadowing || []).filter(function (h) {
      return h.status === 'planted' || h.status === 'active';
    });
    if (activeHooks.length) {
      var hooksText = activeHooks.map(function (h) {
        return '- [' + (h.id || '') + '] (埋于第' + (h.planted_chapter || 0) + '章): ' + (h.content || '');
      }).join('\n');
      parts.push('## 待回收伏笔（' + activeHooks.length + '个）\n' + hooksText);
    }

    return parts.length ? parts.join('\n\n') : '';
  }

  // ═══════════════════════════════════════════
  // 构建人物档案上下文（移植 _build_character_context）
  // ═══════════════════════════════════════════
  function _buildCharacterContext(chapterIndex, outlineText, meta) {
    if (!meta) return '';
    var chars = meta.characters || [];
    if (!chars.length) return '';

    // 获取本章 blueprint 的 character_nodes
    var charNodes = [];
    if (meta.chapters && chapterIndex < meta.chapters.length) {
      var ch = meta.chapters[chapterIndex];
      var bp = ch && ch.blueprint ? ch.blueprint : {};
      charNodes = bp.character_nodes || [];
    }

    // 筛选相关角色
    var relevantChars = [];
    if (charNodes.length) {
      var nodeNames = {};
      charNodes.forEach(function (n) { nodeNames[n.name || ''] = 1; });
      relevantChars = chars.filter(function (c) { return nodeNames[c.name || '']; });
    } else {
      relevantChars = chars.filter(function (c) {
        return c.name && outlineText && outlineText.indexOf(c.name) >= 0;
      }).slice(0, 6);
    }
    if (!relevantChars.length) return '';

    var lines = relevantChars.map(function (c) {
      var name = c.name || '';
      var line = '- ' + name + '（' + (c.faction || '') + '·' + (c.importance || '') + '）: ';
      var details = [];
      if (c.personality) details.push('性格[' + c.personality + ']');
      if (c.obsession) details.push('执念[' + c.obsession + ']');
      if (c.weakness) details.push('软肋[' + c.weakness + ']');
      if (c.goal) details.push('目标[' + c.goal + ']');
      if (c.goals && c.goals.length) details.push('目标[' + c.goals.map(function(g){return typeof g==='object'?g.text:g;}).join(', ') + ']');
      line += details.join(' ');
      // 羁绊
      var bonds = c.bonds;
      if (bonds && bonds.length) {
        var bondStrs = bonds.filter(function (b) { return b && typeof b === 'object'; }).map(function (b) {
          return (b.target || '') + ':' + (b.relation || '');
        });
        if (bondStrs.length) line += ' | 羁绊[' + bondStrs.join(', ') + ']';
      }
      // 动态节点
      for (var i = 0; i < charNodes.length; i++) {
        if (charNodes[i].name === name) {
          if (charNodes[i].appearance === 'first') line += ' | ⚠️本章首次登场';
          else if (charNodes[i].appearance === 'exit') line += ' | ⚠️本章退场';
          if (charNodes[i].status_change) line += ' | 本章变化[' + charNodes[i].status_change + ']';
          break;
        }
      }
      return line;
    });

    return '## 本章人物档案（严格遵守人设）\n' + lines.join('\n');
  }

  // ═══════════════════════════════════════════
  // 记忆召回（移植 vector_memory.search_for_generation_combined）
  // ═══════════════════════════════════════════
  function _buildMemoryRecall(outline, chapterIndex) {
    var db = _db();
    if (!db || !outline) return '';
    try {
      var result = db.searchMemoryForGeneration(outline, chapterIndex, 5);
      if (result && result.ok && result.results && result.results.length) {
        var texts = result.results.map(function (m) {
          return '- ' + (m.content || '');
        });
        return '## 相关前文记忆（向量召回）\n' + texts.join('\n');
      }
    } catch (e) {
      // 记忆系统不可用时静默跳过
    }
    return '';
  }

  // ═══════════════════════════════════════════
  // 硬校验（移植 _run_hard_checks）
  // ═══════════════════════════════════════════
  function _runHardChecks(content, title, outline, ledger) {
    var issues = [];

    // 1. 禁词检查
    var foundWords = FORBIDDEN_WORDS.filter(function (w) { return content.indexOf(w) >= 0; });
    if (foundWords.length) {
      issues.push('使用了禁用词汇: ' + foundWords.join(', '));
    }

    // 2. 长度检查
    if (content.length < 500) {
      issues.push('内容过短，不足500字');
    }

    // 3. 角色一致性：已死亡角色不应再次出现
    if (ledger && ledger.character_states) {
      for (var name in ledger.character_states) {
        if (!ledger.character_states.hasOwnProperty(name)) continue;
        var cs = ledger.character_states[name];
        if (cs.is_alive === false && content.indexOf(name) >= 0) {
          issues.push('已死亡角色 ' + name + ' 再次出现');
        }
      }
    }

    // 4. 扩展审计：AI味检测 + 战力崩坏检测（纯规则，不消耗Token）
    var audit = _audit();
    if (audit && audit.runExtendedAudit) {
      try {
        // 构建角色状态列表
        var charList = [];
        if (ledger && ledger.character_states) {
          for (var cn in ledger.character_states) {
            if (!ledger.character_states.hasOwnProperty(cn)) continue;
            var cstate = ledger.character_states[cn];
            charList.push({
              name: cn,
              realm: cstate.realm || '',
              prev_realm: cstate.prev_realm || '',
              status: cstate.is_alive === false ? 'dead' : 'alive'
            });
          }
        }
        // 获取逾期伏笔
        var overdueHooks = [];
        if (ledger && ledger.foreshadowing) {
          ledger.foreshadowing.forEach(function (h) {
            if ((h.status === 'planted' || h.status === 'active') && h.expected_recovery_chapter) {
              // 无法精确知道当前章，保守地标记 expected > 0 且超期的
              // 这里简化：不传 current_chapter，跳过逾期判断
            }
          });
        }
        var auditResult = audit.runExtendedAudit(content, 0, charList, overdueHooks);
        if (auditResult.overall_level === 'fail') {
          var topIssues = auditResult.all_issues.slice(0, 3);
          topIssues.forEach(function (iss) {
            issues.push('[扩展审计] ' + (iss.message || ''));
          });
        } else if (auditResult.overall_level === 'review') {
          var severe = auditResult.all_issues.filter(function (iss) {
            return iss.type === 'buzzword_forbidden' || iss.type === 'dead_revival' || iss.type === 'realm_jump';
          }).slice(0, 2);
          severe.forEach(function (iss) {
            issues.push('[扩展审计] ' + (iss.message || ''));
          });
        }
      } catch (e) {
        // 审计异常时静默跳过
      }
    }

    return issues;
  }

  // ═══════════════════════════════════════════
  // 构建生成章节的 Prompt（移植 _build_generation_prompt）
  // ═══════════════════════════════════════════
  function _buildGenerationPrompt(title, outline, context, chapterIndex, issues, deps) {
    var parts = [];
    var db = _db();
    var settings = deps.settings;
    var meta = deps.meta;
    var ledger = deps.ledger;

    // 世界观
    var worldText = _worldToPrompt(settings);
    if (worldText) parts.push(worldText);

    // Lorebook 关键词触发
    var outlineStr = outline ? String(outline) : '';
    var titleStr = title ? String(title) : '';
    var lorebookText = _triggerLorebook(outlineStr + ' ' + titleStr, settings);
    if (lorebookText) parts.push(lorebookText);

    // Truth Ledger 角色状态
    var relevantChars = _extractRelevantCharacters(outlineStr + ' ' + titleStr + ' ' + (context || ''), ledger);
    var ledgerText = _ledgerToContext(chapterIndex, relevantChars, ledger);
    if (ledgerText) parts.push(ledgerText);

    // 人物档案
    var charText = _buildCharacterContext(chapterIndex, outlineStr + ' ' + titleStr, meta);
    if (charText) parts.push(charText);

    // 伏笔状态
    var hookText = _buildForeshadowContext(chapterIndex, ledger);
    if (hookText) parts.push(hookText);

    // 记忆召回
    var recallText = _buildMemoryRecall(outlineStr, chapterIndex);
    if (recallText) parts.push(recallText);

    // 剧情线提示
    var plotLineHint = '';
    try {
      if (meta && meta.chapters && chapterIndex < meta.chapters.length) {
        var bp = meta.chapters[chapterIndex].blueprint || {};
        var pl = bp.plot_line || ['主线'];
        if (Array.isArray(pl) && pl.length) {
          plotLineHint = '\n## 剧情线\n本章属于: ' + pl.join(', ') + '\n';
          if (pl.some(function (p) { return p.indexOf('支线') >= 0; })) {
            plotLineHint += '注意: 支线章节节奏可放缓，侧重人物铺垫和情感刻画\n';
          } else {
            plotLineHint += '注意: 主线章节节奏紧凑，推进核心剧情\n';
          }
        }
      }
    } catch (e) { /* ignore */ }

    var forbiddenSample = FORBIDDEN_WORDS.slice(0, 10).join(', ');

    parts.push(
      '你是专业小说作家。请根据大纲和设定写作章节。\n' +
      plotLineHint + '\n' +
      '## 章节标题\n' + title + '\n\n' +
      '## 当前章节\n第' + (chapterIndex + 1) + '章（共若干章）\n\n' +
      '## 章节大纲（严格按此结构写作）\n' + outline + '\n\n' +
      '## 上下文\n' + (context || '') + '\n\n' +
      '## 写作要求\n' +
      '1. 按四段结构写：引入(20%) / 展开(50%) / 高潮(20%) / 收尾(10%)\n' +
      '2. 角色每个选择必须有代价\n' +
      '3. 感官细节 > 形容词堆砌\n' +
      '4. 对白有潜台词，不要"XX说："开头\n' +
      '5. 禁用词汇：' + forbiddenSample + '\n' +
      '6. 禁用情节：' + FORBIDDEN_PLOTS.join(', ') + '\n' +
      '7. 目标字数 2000-4000 字\n' +
      '8. 严格遵循大纲中的剧情走向，不得偏离章节定位\n' +
      '9. 承接前文剧情，保持角色状态、时间线的连续性\n\n' +
      '## 反AI检测写作规范（必须严格遵守）\n' +
      '1. 句子长短交错：短句（3-8字）和长句（20-40字）交替，偶尔用单字独立段落\n' +
      '2. 段落长短不均：有的一句话，有的五六句，不要每段差不多长\n' +
      '3. 少用"的"字：每千字不超过20个"的"，多用"之"或重写句子去掉\n' +
      '4. 禁用连接词：不用"然而""因此""于是""紧接着""事实上"。用动作切换代替\n' +
      '5. 句首要多���：不连续两句以同一词开头\n' +
      '6. 口语化：用碎句、省略号、破折号、半句话。对话可以打断、回避、言不由衷\n' +
      '7. 不规则节奏：高潮连用短句快切，平静处长句慢铺。一章至少3次明显变速\n' +
      '8. 少用"突然""忽然""仿佛""似乎"，每章最多各1次\n' +
      '9. 具体化：不写"一股寒意"，写"后脖颈汗毛竖起"\n' +
      '10. 不写AI总结句："这意味着…""不难看出…""这证明了…"\n' +
      '11. 允许无用闲笔：穿插无推进作用的碎片细节（墙皮、滴水声、手机电量、傍晚光线）每章至少2处\n' +
      '12. 情绪多层错位：表面行为和内心感受必须错位。嘴上说没事，手在发抖\n' +
      '13. 对话不规整：30%的对话不完整——半句、停顿、转移话题、用沉默代替回答\n' +
      '14. 世界观禁止旁白说明：所有设定必须通过角色身体感受、他人反应、冲突展现、对话间接提及来展示\n' +
      '15. 必须写到2000字以上\n\n' +
      '直接输出章节正文，不要标题。'
    );

    if (issues && issues.length) {
      parts.push('\n## 上一版需要修复的问题\n' + issues.map(function (i) { return '- ' + i; }).join('\n'));
    }

    return parts.join('\n\n');
  }

  // ════════════════════════════════════════════════════════════════
  // 1. 直连 AI API（移植 ai_client.py）
  //    P0修复：在线模式走后端代理，离线模式保留直连兜底
  // ════════════════════════════════════════════════════════════════
  async function callAI(prompt, opts) {
    opts = opts || {};

    // 在线模式：通过后端代理调用，API Key 不暴露给前端 JS
    if (!window._isOfflineMode) {
      return _callBackendProxy(prompt, opts);
    }

    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };

    var config = db.getAIConfig();
    var provider = config.provider || 'deepseek';
    var cfg = config[provider] || config.deepseek || {};

    var apiKey = cfg.api_key || '';
    var baseUrl = cfg.base_url || 'https://api.deepseek.com';
    var model = cfg.model || 'deepseek-v4-flash';
    var temperature = opts.temperature !== undefined ? opts.temperature : (cfg.temperature !== undefined ? cfg.temperature : 0.7);
    var maxTokens = opts.max_tokens !== undefined ? opts.max_tokens : (cfg.max_tokens !== undefined ? cfg.max_tokens : 8192);
    var useStream = typeof opts.on_chunk === 'function';

    if (!apiKey && provider !== 'ollama') {
      return { ok: false, error: '未配置 API Key' };
    }

    var endpoint = _buildEndpoint(baseUrl);

    var body = {
      model: model,
      messages: [{ role: 'user', content: prompt }],
      temperature: temperature,
      max_tokens: maxTokens,
      stream: useStream
    };
    // DeepSeek thinking 模式
    if (cfg.thinking === 'enabled') {
      body.thinking = { type: 'enabled' };
    }

    var headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;

    try {
      var resp = await fetch(endpoint, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(body)
      });

      if (!resp.ok) {
        var errText = '';
        try { errText = await resp.text(); } catch (e) {}
        return { ok: false, error: 'HTTP ' + resp.status + ': ' + _truncate(errText, 300) };
      }

      // 流式响应
      if (useStream) {
        var result = [];
        var reader = resp.body.getReader();
        var decoder = new TextDecoder('utf-8');
        var buffer = '';
        while (true) {
          var chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          var lines = buffer.split('\n');
          buffer = lines.pop(); // 保留最后不完整的行
          for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (line.indexOf('data: ') === 0 && line !== 'data: [DONE]') {
              try {
                var parsed = JSON.parse(line.substring(6));
                var delta = parsed.choices && parsed.choices[0] && parsed.choices[0].delta ? parsed.choices[0].delta : {};
                var token = delta.content || '';
                if (token) {
                  opts.on_chunk(token);
                  result.push(token);
                }
              } catch (e) { /* skip invalid JSON */ }
            }
          }
        }
        return { ok: true, content: result.join('') };
      }

      // 非流式响应
      var data = await resp.json();
      var choice = (data.choices && data.choices[0]) || {};
      var msg = choice.message || {};
      var content = msg.content || '';
      if (!content) {
        // 某些推理模型把内容放在 reasoning_content 里
        content = msg.reasoning_content || '';
      }
      return { ok: true, content: content };
    } catch (e) {
      return { ok: false, error: '请求失败: ' + (e.message || String(e)) };
    }
  }

  // ════════════════════════════════════════════════════════════════
  // 2. 生成章节（移植 generate_and_validate + _build_generation_prompt）
  // Gate 闭环：生成 → 硬校验 → 不通过则反馈问题重写（最多3轮）
  // ════════════════════════════════════════════════════════════════
  async function generateChapter(title, outline, context, chapterIndex, on_chunk) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载', content: '', validation_log: [], attempts: 0 };

    var maxRetries = 3;
    var validationLog = [];
    var content = '';
    var localContext = context || '';

    // 预加载依赖
    var settings = db.getSettings();
    var meta = db.getProjectMeta();
    var ledger = db.getLedger();
    var deps = { settings: settings, meta: meta, ledger: ledger };

    for (var attempt = 0; attempt < maxRetries; attempt++) {
      // 构建 prompt
      var prompt = _buildGenerationPrompt(title, outline, localContext, chapterIndex, validationLog, deps);

      // 生成（仅第一轮使用流式回调）
      var genResult = await callAI(prompt, {
        temperature: 0.75,
        max_tokens: 8192,
        on_chunk: (attempt === 0 && typeof on_chunk === 'function') ? on_chunk : undefined
      });

      if (!genResult.ok) {
        return { ok: false, error: genResult.error, content: '', validation_log: validationLog, attempts: attempt + 1 };
      }
      content = genResult.content || '';

      // 跑硬校验
      var issues = _runHardChecks(content, title, outline, ledger);
      validationLog = validationLog.concat(issues);

      if (issues.length === 0) {
        content = postProcess(content);
        return { ok: true, content: content, validation_log: validationLog, attempts: attempt + 1 };
      }

      // 反馈问题用于下一轮重写
      localContext += '\n\n[上一版问题]\n' + issues.map(function (i) { return '- ' + i; }).join('\n');
    }

    // 达到最大重试次数 — 返回尽力结果
    if (content && content.length >= 200) {
      content = postProcess(content);
      return {
        ok: true,
        content: content,
        validation_log: validationLog,
        attempts: maxRetries,
        warning: '经过' + maxRetries + '轮修订，内容已生成但仍有' + validationLog.length + '条建议'
      };
    }
    return {
      ok: false,
      content: content,
      validation_log: validationLog,
      attempts: maxRetries,
      warning: '经过' + maxRetries + '轮修订仍未完全通过校验'
    };
  }

  // ════════════════════════════════════════════════════════════════
  // 3. 生成全书大纲（移植 generate_outline）
  // ════════════════════════════════════════════════════════════════
  async function generateOutline(title, genre, length) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };

    // 根据规模决定章数/幕数
    var scale, actCount;
    if (typeof length === 'string') {
      scale = length;
    } else {
      var n = parseInt(length, 10) || 10;
      if (n <= 8) scale = 'short';
      else if (n <= 12) scale = 'mid';
      else if (n <= 20) scale = 'long';
      else scale = 'epic';
    }
    var scaleMap = { short: [6, 8], mid: [10, 12], long: [16, 20], epic: [24, 30] };
    var range = scaleMap[scale] || scaleMap.mid;
    actCount = Math.round((range[0] + range[1]) / 2);

    // 注入世界观设定
    var settings = db.getSettings();
    var worldText = _worldToPrompt(settings);

    var prompt =
      '为' + (genre || '') + '小说《' + title + '》生成全书大纲，共' + actCount + '个幕。\n\n' +
      (worldText ? ('【世界观设定】\n' + worldText + '\n\n') : '') +
      '类型指南：' + (genre || '小说') + '\n\n' +
      '输出格式：\n' +
      '## 核心世界观设定\n' +
      '## 总纲\n' +
      '## 各幕大纲\n' +
      '（每幕一行：第X幕·幕名 | 核心冲突 | 关键转折 | 信息释放）\n\n' +
      '禁止：概述/总结/比喻/套话。每幕必须有具体事件。';

    var result = await callAI(prompt, { temperature: 0.8, max_tokens: 8192 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var outlineText = result.content || '';

    // 解析 acts
    var acts = [];
    var lines = outlineText.split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      // 匹配 "第X幕·幕名 | ..." 或 "第X章·章名 | ..."
      var m = line.match(/^第([一二三四五六七八九十百零\d]+)[幕章][·•・:：]?\s*(.+)/);
      if (m) {
        var idx = _chineseToInt(m[1]);
        var rest = m[2];
        var segs = rest.split('|').map(function (s) { return s.trim(); });
        acts.push({
          index: idx,
          title: segs[0] || '',
          summary: segs.slice(1).join(' | ') || segs[0] || ''
        });
      }
    }
    // 若未解析到 acts，按行构建
    if (!acts.length) {
      var actIdx = 1;
      for (var j = 0; j < lines.length; j++) {
        var ln = lines[j].trim();
        if (ln && (ln.indexOf('幕') >= 0 || ln.indexOf('第') === 0) && ln.length > 2) {
          acts.push({ index: actIdx++, title: ln, summary: ln });
        }
      }
    }

    return { ok: true, outline: outlineText, acts: acts };
  }

  // 中文数字转整数（简易版）
  function _chineseToInt(s) {
    if (/^\d+$/.test(s)) return parseInt(s, 10);
    var map = { '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };
    if (map[s] !== undefined) return map[s];
    if (s.length === 2 && s.charAt(0) === '十') return 10 + (map[s.charAt(1)] || 0);
    if (s.length === 2 && s.charAt(1) === '十') return (map[s.charAt(0)] || 0) * 10;
    if (s.length === 3 && s.charAt(1) === '十') return (map[s.charAt(0)] || 0) * 10 + (map[s.charAt(2)] || 0);
    return s.length; // fallback
  }

  // ════════════════════════════════════════════════════════════════
  // 4. 生成人物档案（移植 generate_characters）
  // ════════════════════════════════════════════════════════════════
  async function generateCharacters(novelOutline) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载', characters: [] };

    var settings = db.getSettings();
    var worldText = _worldToPrompt(settings);

    var outlinePart = '';
    var modeHint;
    if (novelOutline) {
      outlinePart = '\n\n【全书大纲】\n' + _truncate(novelOutline, 3000);
      modeHint = '仔细阅读大纲，提取大纲中出现的所有角色（包括只提到名字的角色），为每个角色生成完整人物档案。不要遗漏任何角色。';
    } else {
      modeHint = '基于世界观设定，预生成一套完整的角色库。要求：1个主角、2-3个核心配角（盟友/同伴）、1-2个核心反派、2-3个次要配角。角色之间要有羁绊关系。角色要符合世界观设定，不要违反禁止事项。';
    }

    var prompt =
      '你是专业小说角色设计师。' + modeHint + '\n\n' +
      '【世界观设定】\n' + (worldText || '（未设定）') + outlinePart + '\n\n' +
      '要求：\n' +
      '1. 为每个角色生成完整档案：姓名/身份/阵营(主角/配角/反派/中立)/性格/身世过往/执念/软肋/目标/人物羁绊/角色定位(核心/次要)\n' +
      '2. 人物羁绊用结构化格式：[{"target":"角色名","relation":"仇恨/信任/爱慕/利用/师徒","note":"说明"}]\n' +
      '3. 核心人物至少1个主角、1个核心反派\n' +
      '4. 性格、执念、软肋必须具体，不要泛泛而谈\n' +
      '5. 人物不得违背世界观设定（时代环境、世界规则）\n' +
      '6. 主角的性格、执念、软肋必须与世界观的力量体系形成闭环绑定：力量来源绑定个人创伤，能力越强越暴露弱点，力量的代价必须具体不可逆\n' +
      '7. 每个核心配角必须有独立于主角的欲望、秘密和行动动机\n' +
      '8. 如果主角有特殊能力，必须明确cost（使用代价）和curse（能力带来的诅咒）\n\n' +
      '返回JSON数组（放在```json代码块中），格式：\n' +
      '```json\n[{"name":"","identity":"","faction":"","personality":"","background":"","obsession":"","weakness":"","goal":"","goals":[{"text":"","weight":1.0}],"bonds":[{"target":"","relation":"","note":""}],"importance":"","cognitive_boundary":"","cost":"","curse":""}]\n```';

    var result = await callAI(prompt, { temperature: 0.8, max_tokens: 8192 });
    if (!result.ok) {
      return { ok: false, error: result.error, characters: [] };
    }

    var chars = _parseJSONLenient(result.content);
    if (!Array.isArray(chars)) {
      return { ok: false, error: 'AI返回的JSON无法解析', characters: [], raw: result.content };
    }

    // 人物羁绊交叉校验
    _validateCharacterBonds(chars);

    return { ok: true, characters: chars };
  }

  // 人物羁绊矛盾校验（移植 _validate_character_bonds）
  function _validateCharacterBonds(chars) {
    var opposite = {
      '仇恨': ['信任', '爱慕', '师徒'],
      '信任': ['仇恨', '利用'],
      '爱慕': ['仇恨'],
      '利用': ['信任', '师徒']
    };
    for (var i = 0; i < chars.length; i++) {
      var a = chars[i];
      var aBonds = a.bonds;
      if (!Array.isArray(aBonds)) continue;
      for (var bi = 0; bi < aBonds.length; bi++) {
        var bond = aBonds[bi] || {};
        var targetName = bond.target || '';
        var relation = bond.relation || '';
        for (var j = 0; j < chars.length; j++) {
          if (j === i) continue;
          var b = chars[j];
          if (b.name !== targetName) continue;
          var bBonds = b.bonds;
          if (!Array.isArray(bBonds)) break;
          for (var bb = 0; bb < bBonds.length; bb++) {
            var bBond = bBonds[bb] || {};
            if (bBond.target === a.name) {
              var bRel = bBond.relation || '';
              var opposites = opposite[relation] || [];
              if (opposites.indexOf(bRel) >= 0) {
                var note = bond.note || '';
                bond.note = '[⚠️羁绊矛盾: ' + targetName + '对' + a.name + '=' + bRel + '] ' + note;
              }
              break;
            }
          }
          break;
        }
      }
    }
  }

  // ════════════════════════════════════════════════════════════════
  // 5. 生成章节大纲（移植 generate_chapter_outline）
  // ════════════════════════════════════════════════════════════════
  async function generateChapterOutline(title, context, chapterIndex) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };

    var forbiddenSample = FORBIDDEN_WORDS.slice(0, 8).join(', ');
    chapterIndex = chapterIndex || 0;

    // 注入当前卷纲要和当前幕事件（与后端 generate_chapter_outline 逻辑一致）
    var volText = '';
    var actText = '';
    try {
      var meta = db.getProjectMeta();
      if (meta) {
        var chNum = chapterIndex + 1;
        // 当前卷纲要
        if (meta.volumes && meta.volumes.length) {
          var curVol = null;
          for (var i = 0; i < meta.volumes.length; i++) {
            var v = meta.volumes[i];
            var vc = v.chapters || [];
            if (vc.indexOf(chNum) >= 0 || (vc.length && vc[0] <= chNum && chNum <= vc[vc.length - 1])) {
              curVol = v; break;
            }
          }
          if (!curVol) curVol = meta.volumes[0];
          if (curVol) {
            var vo = curVol.outline || {};
            var vp = ['## 当前卷纲要：' + (curVol.title || '')];
            if (vo.summary) vp.push('卷概要：' + vo.summary);
            if (vo.theme) vp.push('卷主题：' + vo.theme);
            if (vo.key_events && vo.key_events.length) {
              vp.push('卷关键事件：');
              vo.key_events.forEach(function (ke) { vp.push('  · ' + ke); });
            }
            volText = vp.join('\n') + '\n\n';
          }
        }
        // 当前幕事件
        if (meta.novel_outline && meta.novel_outline.length) {
          var targetAct = null;
          for (var j = 0; j < meta.novel_outline.length; j++) {
            var act = meta.novel_outline[j];
            var actTitle = act.title || '';
            var m = actTitle.match(/第(\d+)-(\d+)章/);
            if (m) {
              var s = parseInt(m[1]), e = parseInt(m[2]);
              if (s <= chNum && chNum <= e) { targetAct = act; break; }
            }
          }
          if (!targetAct) targetAct = meta.novel_outline[0];
          if (targetAct) {
            var ap = ['## 当前幕：' + (targetAct.title || '')];
            (targetAct.events || []).forEach(function (ev) {
              if (typeof ev === 'object') {
                ap.push('- 第' + (ev.chapter || '?') + '章 ' + (ev.text || ev.content || '') + (ev.chapter === chNum ? ' ← 当前章' : ''));
              } else { ap.push('- ' + ev); }
            });
            actText = ap.join('\n') + '\n\n【强制约束】本章大纲必须严格基于上方"当前幕"中的事件来规划。\n\n';
          }
        }
      }
    } catch (e) { /* 忽略，回退到纯 context */ }

    var fullContext = volText + actText + (context || '');

    var prompt =
      '为章节《' + title + '》生成详细大纲。这是第' + (chapterIndex + 1) + '章的专属大纲，内容必须与其他章节不同。\n\n' +
      '上下文：' + fullContext + '\n\n' +
      '重要要求：\n' +
      '1. 必须根据上下文中的章节序号生成对应章节的剧情\n' +
      '2. 如果有前一章内容，必须自然衔接，不要重复前一章的场景和事件\n' +
      '3. 每章的开场场景、触发事件、关键转折都必须不同\n' +
      '4. 按照全书大纲的进度推进剧情\n' +
      '5. 严格基于上方"当前卷纲要"和"当前幕"事件来规划本章剧情\n\n' +
      '请返回以下JSON格式（放在 ```json 代码块中），然后附上可读说明：\n\n' +
      '```json\n' +
      '{\n' +
      '  "title": "' + title + '",\n' +
      '  "plot_line": ["主线"],\n' +
      '  "intro": {"scene":"场景描述","atmosphere":"氛围","trigger":"触发事件","word_count":500},\n' +
      '  "development": [{"scene":"场景1","location":"地点","characters":["角色名"],"event":"关键事件","choice":"角色选择","cost":"代价","info_reveal":"信息释放"}],\n' +
      '  "climax": {"conflict":"冲突最大化描述","key_choice":"关键选择","cost":"代价","twist":"转折点"},\n' +
      '  "ending": {"new_state":"新状态","info_reveal":"信息揭露","next_hook":"下一章钩子"},\n' +
      '  "word_target": 3000\n' +
      '}\n' +
      '```\n\n' +
      '禁止词汇：' + forbiddenSample + '\n\n' +
      '要求：\n' +
      '1. 每个场景必须有具体事件，不要概述\n' +
      '2. 角色选择必须有代价\n' +
      '3. 信息释放要服务于总纲\n' +
      '4. plot_line标注本章所属剧情线（主线/支线A/支线B等），一章可属多条线';

    var result = await callAI(prompt, { temperature: 0.75, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var raw = result.content || '';

    // 解析 JSON 蓝图
    var blueprint = _parseJSONLenient(raw);
    if (!blueprint || typeof blueprint !== 'object' || Array.isArray(blueprint)) {
      blueprint = null;
    }

    // 从蓝图提取纯文本大纲
    var outlineText = '';
    if (blueprint) {
      var parts = [];
      var intro = blueprint.intro || {};
      if (intro && Object.keys(intro).length) {
        parts.push('【起】' + (intro.scene || '') + ' — ' + (intro.trigger || ''));
      }
      var dev = blueprint.development || [];
      dev.forEach(function (d) {
        parts.push('【承】' + (d.scene || '') + '：' + (d.event || ''));
      });
      var climax = blueprint.climax || {};
      if (climax && Object.keys(climax).length) {
        parts.push('【转】' + (climax.conflict || '') + ' — ' + (climax.twist || ''));
      }
      var ending = blueprint.ending || {};
      if (ending && Object.keys(ending).length) {
        parts.push('【合】' + (ending.new_state || '') + ' → ' + (ending.next_hook || ''));
      }
      outlineText = parts.join('\n');
    }
    if (!outlineText) outlineText = raw;

    return { ok: true, raw: raw, blueprint: blueprint, outline_text: outlineText };
  }

  // ════════════════════════════════════════════════════════════════
  // 6. 通用对话（移植 chat）
  // ════════════════════════════════════════════════════════════════
  async function chat(messages, opts) {
    opts = opts || {};
    if (!messages || !messages.length) {
      return { ok: false, error: '消息列表为空' };
    }
    var msgsText = messages.map(function (m) {
      return (m.role || 'user') + ': ' + (m.content || '');
    }).join('\n');

    var result = await callAI(msgsText, {
      temperature: opts.temperature !== undefined ? opts.temperature : 0.7
    });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    return { ok: true, content: result.content };
  }

  // ════════════════════════════════════════════════════════════════
  // 7. 头脑风暴（移植 ai_router.brainstorm）
  // ════════════════════════════════════════════════════════════════
  async function brainstorm(topic, context, mode, opts) {
    opts = opts || {};
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载', ideas: [] };

    var meta = db.getProjectMeta() || {};
    var genre = (meta.meta && meta.meta.genre) || '小说';
    var title = (meta.meta && meta.meta.title) || '';

    // 获取当前章节信息作为上下文
    var curIdx = (meta.meta && meta.meta.current_chapter) || 0;
    var chapterTitle = '';
    var chapterContent = '';
    if (meta.chapters && curIdx < meta.chapters.length) {
      chapterTitle = meta.chapters[curIdx].title || '';
      var chLoad = db.loadChapter(curIdx);
      if (chLoad && chLoad.ok) chapterContent = _truncate(chLoad.content, 2000);
    }

    var modePrompts = {
      'plot': '请生成12个不同的情节发展方向，每个方向需要出人意料但又合乎逻辑。考虑伏笔回收、角色弧光和节奏控制。确保方向多样化，涵盖主线推进、支线展开、意外转折等。',
      'character': '请生成12个角色发展的可能性，包括角色关系的转变、内心冲突的展开、角色成长的契机、以及角色暗面的揭示。',
      'conflict': '请生成12个冲突升级方案，包括人际冲突、环境冲突和内心冲突的交织。考虑利益对立、价值观碰撞和资源争夺。',
      'theme': '请生成12个主题深化的方向，将故事的核心主题通过具体事件、象征隐喻和角色选择表达出来。',
      'reverse': '请生成12个反常识发展方向——读者最不可能预期的走向，但细想又在情理之中。打破套路，颠覆预期。',
      'foreshadowing': '请生成12个伏笔回收方案——检查前文埋设的伏笔（如神秘物件、未解对话、异常能力），设计出人意料的回收方式。',
      'arc': '请生成12个角色弧光发展方向——角色在认知、情感、价值观层面的成长或堕落轨迹，通过具体事件体现转变。',
      'pacing': '请生成12个节奏调控方案——包括加速/减速/转折/留白等节奏变化，通过场景切换、信息释放速率和情绪起伏来实现。'
    };

    var count = opts.count || 12;
    var modeLabel;
    if (mode === 'custom' && opts.custom_prompt) {
      modeLabel = '请生成' + count + '个方向，要求：' + opts.custom_prompt;
    } else {
      modeLabel = modePrompts[mode] || modePrompts.plot;
      modeLabel = modeLabel.replace(/12个/g, count + '个');
    }

    var userTopic = (topic && topic.trim()) ? topic.trim() : '基于当前故事进展';
    var userContext = (context && context.trim()) ? _truncate(context.trim(), 1000) : '';

    var prompt =
      '你是一位创意写作顾问。正在为一部' + genre + '小说《' + title + '》进行头脑风暴。\n\n' +
      '【当前章节】第' + (curIdx + 1) + '章 - ' + chapterTitle + '\n' +
      '【当前章节内容摘要】\n' + _truncate(chapterContent, 1500) + '\n\n' +
      '【用户关注点】' + userTopic + '\n' +
      (userContext ? '【额外上下文】' + userContext + '\n' : '') + '\n' +
      modeLabel + '\n\n' +
      '请以JSON数组格式返回，每个元素包含：\n' +
      '- "title": 创意标题（10字以内）\n' +
      '- "desc": 详细描述（50-100字）\n' +
      '- "tags": 标签数组（如"伏笔"、"高潮"、"转折"、"反常识"等）\n' +
      '- "impact": 影响等级（high/medium/low）\n\n' +
      '要求：\n' +
      '1. 每个方向必须独特且不重复\n' +
      '2. 兼顾大胆创新和逻辑自洽\n' +
      '3. 标注好每个方向的影响等级\n' +
      '4. 至少包含3个high影响的方向\n\n' +
      '只返回JSON数组，不要其他解释。';

    var result = await callAI(prompt, { temperature: 0.9, max_tokens: 8192 });
    if (!result.ok) {
      return { ok: false, error: result.error, ideas: [] };
    }

    var ideas = _parseJSONLenient(result.content);
    if (!Array.isArray(ideas)) {
      // 降级：按行解析
      ideas = [];
      var lines = result.content.split('\n');
      lines.forEach(function (line) {
        line = line.trim();
        if (line && line.length > 5) {
          ideas.push({ title: line.substring(0, 20), desc: line, tags: [], impact: 'medium' });
        }
      });
    }
    return { ok: true, ideas: ideas.slice(0, count), mode: mode, count: Math.min(ideas.length, count) };
  }

  // ════════════════════════════════════════════════════════════════
  // 8. 灵感扩展（移植 ai_router.expand_idea）
  // ════════════════════════════════════════════════════════════════
  async function expandIdea(title, desc, mode, context) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };

    var meta = db.getProjectMeta() || {};
    var genre = (meta.meta && meta.meta.genre) || '小说';
    var novelTitle = (meta.meta && meta.meta.title) || '';

    var curIdx = (meta.meta && meta.meta.current_chapter) || 0;
    var chapterContent = '';
    if (meta.chapters && curIdx < meta.chapters.length) {
      var chLoad = db.loadChapter(curIdx);
      if (chLoad && chLoad.ok) chapterContent = _truncate(chLoad.content, 1500);
    }

    var modeHints = {
      'plot': '将这个创意展开为一段详细的情节大纲（200-300字），包含具体场景、人物行动、冲突细节',
      'character': '将这个创意展开为角色发展详细方案（200-300字），包含角色心理变化、关系演变、关键对话',
      'conflict': '将这个创意展开为冲突场景详细描写（200-300字），包含对立双方立场、冲突升级过程、后果',
      'theme': '将这个创意展开为主题表达方案（200-300字），包含象征意象、角色选择、读者感受设计',
      'reverse': '将这个反常识创意展开为详细走向（200-300字），包含反转铺垫、揭示时机、读者冲击点',
      'foreshadowing': '将这个伏笔回收创意展开为详细方案（200-300字），包含前文伏笔位置、回收方式、情感冲击',
      'arc': '将这个角色弧光创意展开为详细轨迹（200-300字），包含转变契机、中间挣扎、最终状态',
      'pacing': '将这个节奏调控创意展开为详细方案（200-300字），包含场景切换点、信息释放节奏、情绪起伏曲线'
    };
    var modeHint = modeHints[mode] || modeHints.plot;

    var prompt =
      '你是一位创意写作顾问。正在为一部' + genre + '小说《' + novelTitle + '》扩展灵感碎片。\n\n' +
      '【当前章节内容摘要】\n' + chapterContent + '\n\n' +
      '【灵感碎片】\n标题：' + (title || '') + '\n描述：' + (desc || '') + '\n\n' +
      '【额外上下文】' + (context || '') + '\n\n' +
      modeHint + '\n\n' +
      '要求：\n1. 内容要具体、可操作，不要空泛描述\n2. 与当前章节内容自然衔接\n3. 保持与已有设定的一致性\n\n' +
      '直接输出扩展内容，不要解释。';

    var result = await callAI(prompt, { temperature: 0.85, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    var expanded = (result.content || '').trim();
    if (!expanded) {
      return { ok: false, error: '扩展失败：AI返回为空' };
    }
    return { ok: true, expanded: expanded, original_title: title };
  }

  // ════════════════════════════════════════════════════════════════
  // 9. 五感描写（移植 ai_router.sensory）
  // ════════════════════════════════════════════════════════════════
  async function sensory(scene, senseType, style) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };

    var meta = db.getProjectMeta() || {};
    var genre = (meta.meta && meta.meta.genre) || '小说';

    var sceneText = scene ? _truncate(scene.trim(), 2000) : '';
    if (!sceneText) {
      // 使用当前章节内容
      var curIdx = (meta.meta && meta.meta.current_chapter) || 0;
      if (meta.chapters && curIdx < meta.chapters.length) {
        var chLoad = db.loadChapter(curIdx);
        if (chLoad && chLoad.ok) sceneText = _truncate(chLoad.content, 1500);
      }
    }
    if (!sceneText) {
      return { ok: false, error: '请提供场景描述' };
    }

    var senseMap = {
      'visual': '视觉（光影、色彩、动态画面）',
      'auditory': '听觉（声音、节奏、静默）',
      'olfactory': '嗅觉（气味、空气质感）',
      'tactile': '触觉（温度、质感、力度）',
      'gustatory': '味觉（味道、口感）'
    };
    var styleMap = {
      'immersive': '沉浸式（细腻丰富，适合重要场景）',
      'subtle': '克制式（点到为止，适合快节奏段落）',
      'poetic': '诗意式（意境化，适合抒情段落）'
    };
    var styleLabel = styleMap[style] || styleMap.immersive;

    var senseInstruction, senseFields;
    if (senseType === 'all' || !senseType) {
      senseInstruction = '请分别为以下五种感官各生成2-3句描写';
      senseFields = Object.keys(senseMap);
    } else {
      senseInstruction = '请重点生成' + (senseMap[senseType] || '综合感官') + '的描写，3-5句';
      senseFields = [senseType];
    }

    var prompt =
      '你是一位精通感官描写的小说家。正在为' + genre + '小说生成感官细节。\n\n' +
      '【场景/上下文】\n' + sceneText + '\n\n' +
      '【描写风格】' + styleLabel + '\n' +
      '【任务】' + senseInstruction + '，使其自然融入故事，避免堆砌形容词。\n\n' +
      '请以JSON格式返回：\n' +
      '{\n' +
      '  "visual": "视觉描写段落",\n' +
      '  "auditory": "听觉描写段落",\n' +
      '  "olfactory": "嗅觉描写段落",\n' +
      '  "tactile": "触觉描写段落",\n' +
      '  "gustatory": "味觉描写段落",\n' +
      '  "combined": "将以上感官自然融合的完整段落（150-300字）"\n' +
      '}\n\n' +
      '如果某感官不适合当前场景，可用空字符串。只返回JSON，不要解释。';

    var result = await callAI(prompt, { temperature: 0.8, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var sensoryData = _parseJSONLenient(result.content);
    if (!sensoryData || typeof sensoryData !== 'object') {
      return { ok: false, error: 'AI返回结果无法解析', raw: result.content };
    }
    return { ok: true, sensory: sensoryData, senses: senseFields };
  }

  // ════════════════════════════════════════════════════════════════
  // 10. AI检测（调用 AuditJS）
  // ════════════════════════════════════════════════════════════════
  function validateAiFlavor(content) {
    var audit = _audit();
    if (!audit || !audit.detectAiFlavor) {
      return { ok: false, error: 'AuditJS 未加载', score: 0, level: 'unknown', issues: [] };
    }
    try {
      var result = audit.detectAiFlavor(content);
      result.ok = true;
      return result;
    } catch (e) {
      return { ok: false, error: '检测失败: ' + (e.message || String(e)), score: 0, level: 'unknown', issues: [] };
    }
  }

  // ════════════════════════════════════════════════════════════════
  // 11. 状态提取（移植 extract_state）
  // ════════════════════════════════════════════════════════════════
  async function extractState(content, chapterIdx) {
    if (!content) {
      return { ok: false, error: '内容为空' };
    }

    var prompt =
      '分析以下小说章节，提取结构化信息。只返回JSON，不要解释。\n\n' +
      _truncate(content, 4000) + '\n\n' +
      'JSON格式：\n' +
      '{\n' +
      '  "foreshadowing": [{"content": "伏笔描述", "expected_recovery": 预计回收章号}],\n' +
      '  "character_changes": {"角色名": {"field": "new_value"}},\n' +
      '  "new_items": [{"name": "物品名", "nature": "性质", "owner": "持有人"}]\n' +
      '}\n\n' +
      '字段说明：\n' +
      '- foreshadowing: 疑似伏笔（未解答对话/奇怪物件/灵异预兆/异常能力）\n' +
      '- character_changes: 角色状态变化（health/emotion/realm/location/possessions）\n' +
      '- new_items: 新出现的重要物品';

    var result = await callAI(prompt, { temperature: 0.3, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var state = _parseJSONLenient(result.content);
    if (!state || typeof state !== 'object') {
      return {
        ok: true,
        state: { foreshadowing: [], character_changes: {}, new_items: [] }
      };
    }
    // 确保字段完整
    if (!state.foreshadowing) state.foreshadowing = [];
    if (!state.character_changes) state.character_changes = {};
    if (!state.new_items) state.new_items = [];
    return { ok: true, state: state };
  }

  // ════════════════════════════════════════════════════════════════
  // 12. AI校验检查（移植 validate.all — 一次AI调用检查6项）
  // ════════════════════════════════════════════════════════════════
  async function validateAll(content, index, memory, context) {
    if (!content) {
      return { ok: false, error: '内容为空' };
    }
    context = context || {};
    var stage = context.stage || 'content';
    var memorySection = memory ? '\n\n【全文记忆参考】\n' + memory + '\n\n请结合以上记忆进行检查。' : '';

    var novelOutline = context.novelOutline || '';
    var chapterOutline = context.chapterOutline || '';
    var chapterIndex = context.chapterIndex !== undefined ? context.chapterIndex : (index || 0);

    var checksBlock, contextBlock, outlineSection;
    if (stage === 'chapter-outline') {
      checksBlock =
        '### 检查项（请逐项检查，每项用XML标签输出结果）\n\n' +
        '1. <drift>偏差检查：严格审查章节大纲，找出逻辑漏洞、遗漏和矛盾。无问题返回"无偏离"</drift>\n\n' +
        '2. <twist>转折检查：分析章节大纲的转折设计是否合理自然。给出评价</twist>\n\n' +
        '3. <duplicate>重复检查：检查章节大纲是否有重复内容。无重复返回"无重复"</duplicate>\n\n' +
        '4. <timeline>时间线检查：检查章节大纲内部的时间线是否连贯合理。无问题返回"无矛盾"</timeline>\n\n' +
        '5. <conflict>冲突检查：检查章节大纲是否存在设定冲突。无冲突返回"无冲突"</conflict>\n\n' +
        '6. <style>风格检查：评价章节大纲的文笔风格一致性。指出不一致之处</style>';
      contextBlock =
        '【第' + (chapterIndex + 1) + '章大纲】\n' + content;
      outlineSection = '';
    } else {
      checksBlock =
        '### 检查项（请逐项检查，每项用XML标签输出结果）\n\n' +
        '1. <drift>偏差检查：严格对比"当前章节大纲"与"当前章节正文"，只报告两者之间的直接矛盾。"记忆参考"是其他章节摘要，不属于当前章节正文，不得作为判断依据。以下情况不算偏差：正文措辞与大纲不同但情节相同、细节在正文中被换场景呈现、角色心理描写侧重点不同。如果大纲中的核心事件和角色都已在正文中有实质性出现，返回"无偏离"</drift>\n\n' +
        '2. <twist>转折检查：分析正文的转折设计是否合理自然，评价转折的合理性和冲击力</twist>\n\n' +
        '3. <duplicate>重复检查：检查正文是否有重复内容。无重复返回"无重复"</duplicate>\n\n' +
        '4. <timeline>时间线检查：检查正文的时间线逻辑是否合理。无问题返回"无矛盾"</timeline>\n\n' +
        '5. <conflict>冲突检查：检查正文是否存在设定冲突。无冲突返回"无冲突"</conflict>\n\n' +
        '6. <style>风格检查：评价正文的文笔风格一致性，指出风格不一致的地方</style>';
      contextBlock = '【正文内容（共' + content.length + '字）】\n' + content;
      // 注入当前章节大纲，供偏差检查对比
      if (chapterOutline) {
        var currentChapterOutline = '';
        var chapters = chapterOutline.split('\n\n');
        for (var ci = 0; ci < chapters.length; ci++) {
          if (chapters[ci].indexOf('第' + (chapterIndex + 1) + '章') >= 0 || ci === chapterIndex) {
            currentChapterOutline = chapters[ci];
            break;
          }
        }
        if (!currentChapterOutline && chapters[chapterIndex]) {
          currentChapterOutline = chapters[chapterIndex];
        }
        outlineSection = currentChapterOutline
          ? '\n\n【当前章节大纲（用于偏差检查对比）】\n' + currentChapterOutline
          : '';
      } else {
        outlineSection = '';
      }
    }

    var prompt =
      '你是小说审核专家。请对以下内容进行6项检查，一次性返回所有结果。\n\n' +
      contextBlock + outlineSection + memorySection + '\n\n' +
      checksBlock + '\n\n' +
      '重要要求：\n' +
      '1. 每项检查结果必须包裹在对应的XML标签内\n' +
      '2. 如果某项检查无问题，在标签内返回对应的"无xxx"\n' +
      '3. 不要在标签外输出多余内容\n' +
      '4. 保持每项检查的独立性和专业性';

    var result = await callAI(prompt, { temperature: 0.3, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var rawResult = result.content || '';
    var results = {};
    var tags = ['drift', 'twist', 'duplicate', 'timeline', 'conflict', 'style'];
    for (var i = 0; i < tags.length; i++) {
      var tag = tags[i];
      var re = new RegExp('<' + tag + '>([\\s\\S]*?)</' + tag + '>', 'i');
      var m = rawResult.match(re);
      results[tag] = m ? m[1].trim() : null;
    }

    var parsedCount = 0;
    for (var k in results) {
      if (results[k] !== null) parsedCount++;
    }

    return {
      ok: true,
      results: results,
      parsed_count: parsedCount,
      total: tags.length,
      raw: parsedCount < 4 ? rawResult : null,
      stage: stage
    };
  }

  // ════════════════════════════════════════════════════════════════
  // 13. 章节完整性检查（移植 chapter_check.check_completeness）
  // ════════════════════════════════════════════════════════════════
  async function checkCompleteness(content, title) {
    if (!content || content.trim().length < 100) {
      return { ok: false, error: '内容太短，至少100字' };
    }

    var chTitle = title || '当前章节';
    var expected = '2000-4000字';

    var prompt =
      '你是资深小说编辑。请对以下章节正文进行完整性分析。\n\n' +
      '## 章节标题\n' + chTitle + '\n\n' +
      '## 目标字数\n' + expected + '\n\n' +
      '## 章节正文\n' + _truncate(content, 5000) + '\n\n' +
      '## 分析要求\n' +
      '从以下5个维度评估，每个维度给0-10分，并给出具体说明：\n\n' +
      '1. **结构完整度**：是否有清晰的开头（引入情境）、发展（推进事件）、结尾（收束或钩子）？是否有明显的截断感？\n' +
      '2. **情绪曲线**：情绪是否有起伏变化？是否有低谷和高峰？是否一直平铺直叙？\n' +
      '3. **信息密度**：是否有足够的情节推进/角色发展/世界观展示？是否有明显的水文段落？\n' +
      '4. **字数健康度**：与目标字数是否匹配？是否过短或过长？\n' +
      '5. **可读性**：段落结构是否合理？对话和描写的比例是否恰当？\n\n' +
      '## 输出格式\n' +
      '严格输出JSON，不要任何解释：\n' +
      '{\n' +
      '  "overall_score": 平均分,\n' +
      '  "overall_level": "优秀/良好/一般/需改进",\n' +
      '  "word_count": 实际字数,\n' +
      '  "dimensions": {\n' +
      '    "structure": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "emotion_curve": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "info_density": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "length_health": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "readability": {"score": 分数, "comment": "说明", "issues": []}\n' +
      '  },\n' +
      '  "summary": "总体一句话评价",\n' +
      '  "suggestions": []\n' +
      '}';

    var result = await callAI(prompt, { temperature: 0.3, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var parsed = _parseJSONLenient(result.content);
    if (!parsed || typeof parsed !== 'object') {
      return { ok: false, error: 'AI返回格式异常', raw: _truncate(result.content, 500) };
    }
    parsed.word_count = content.length;
    return { ok: true, result: parsed };
  }

  // ════════════════════════════════════════════════════════════════
  // 14. 章节连贯性检查（移植 chapter_check.check_continuity）
  // ════════════════════════════════════════════════════════════════
  async function checkContinuity(chapterA, chapterB, titleA, titleB) {
    var a = (chapterA || '').trim();
    var b = (chapterB || '').trim();
    if (a.length < 100 || b.length < 100) {
      return { ok: false, error: '两章内容都至少100字' };
    }

    var ta = titleA || '前一章';
    var tb = titleB || '后一章';

    var prompt =
      '你是资深小说编辑。请检查以下两章之间的连贯性和衔接质量。\n\n' +
      '## 前一章：' + ta + '\n' + _truncate(a, 3000) + '\n\n' +
      '## 后一章：' + tb + '\n' + _truncate(b, 3000) + '\n\n' +
      '## 分析要求\n' +
      '从以下6个维度评估连贯性，每维度0-10分：\n\n' +
      '1. **情节衔接**：后一章是否自然承接前一章的结尾？是否有跳跃或断裂？\n' +
      '2. **时间线一致**：时间推进是否合理？有没有时间矛盾？\n' +
      '3. **角色一致性**：同一角色的行为/性格/状态是否连贯？有没有突然转变？\n' +
      '4. **地点/场景过渡**：场景切换是否合理？有没有凭空瞬移？\n' +
      '5. **伏笔/信息承接**：前一章埋的伏笔/信息在后一章是否有呼应或推进？\n' +
      '6. **情绪/节奏衔接**：两章之间的情绪和节奏是否顺畅过渡？\n\n' +
      '## 输出格式\n' +
      '严格输出JSON：\n' +
      '{\n' +
      '  "overall_score": 平均分,\n' +
      '  "overall_level": "优秀/良好/一般/需改进",\n' +
      '  "dimensions": {\n' +
      '    "plot_flow": {"score": 分数, "comment": "说明", "gap": ""},\n' +
      '    "timeline": {"score": 分数, "comment": "说明", "conflict": ""},\n' +
      '    "character_consistency": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "scene_transition": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "foreshadowing": {"score": 分数, "comment": "说明", "issues": []},\n' +
      '    "pacing": {"score": 分数, "comment": "说明", "issues": []}\n' +
      '  },\n' +
      '  "summary": "总体一句话评价",\n' +
      '  "suggestions": [],\n' +
      '  "gap_points": []\n' +
      '}';

    var result = await callAI(prompt, { temperature: 0.3, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    var parsed = _parseJSONLenient(result.content);
    if (!parsed || typeof parsed !== 'object') {
      return { ok: false, error: 'AI返回格式异常', raw: _truncate(result.content, 500) };
    }
    return { ok: true, result: parsed };
  }

  // ════════════════════════════════════════════════════════════════
  // 15. 角色对话（移植 chat.chat_talk）
  // ════════════════════════════════════════════════════════════════
  async function chatTalk(character, message, history) {
    var db = _db();
    if (!db) return { ok: false, error: 'LocalDB 未加载' };
    if (!character || !character.trim()) return { ok: false, error: '缺少角色名' };
    if (!message || !message.trim()) return { ok: false, error: '缺少消息内容' };

    character = character.trim();
    message = message.trim();

    // 查找角色设定描述
    var desc = '';
    var meta = db.getProjectMeta() || {};
    var chars = meta.characters || [];
    for (var i = 0; i < chars.length; i++) {
      if (chars[i].name === character) {
        desc = chars[i].description || chars[i].role || chars[i].background || '';
        // 拼接更多角色信息
        var info = [];
        if (chars[i].personality) info.push('性格：' + chars[i].personality);
        if (chars[i].obsession) info.push('执念：' + chars[i].obsession);
        if (chars[i].weakness) info.push('软肋：' + chars[i].weakness);
        if (chars[i].goal) info.push('目标：' + chars[i].goal);
        if (chars[i].goals && chars[i].goals.length) info.push('目标：' + chars[i].goals.map(function(g){return typeof g==='object'?g.text:g;}).join('；'));
        if (info.length) desc = desc + '。' + info.join('；');
        break;
      }
    }

    // 从 character_settings 提取
    if (!desc && meta.character_settings) {
      var cs = meta.character_settings;
      for (var key in cs) {
        if (cs.hasOwnProperty(key) && key.indexOf('_name') >= 0 && cs[key] === character) {
          var prefix = key.replace('_name', '');
          desc = cs[prefix + '_role'] || cs[prefix + '_description'] || '';
          break;
        }
      }
    }

    // 世界观背景
    var world = '';
    if (meta.world_settings) {
      var wsParts = [];
      for (var wk in meta.world_settings) {
        if (meta.world_settings.hasOwnProperty(wk)) wsParts.push(wk + '：' + meta.world_settings[wk]);
      }
      world = wsParts.join('\n');
    }

    // 格式化历史对话
    var historyText = '';
    if (history && history.length) {
      var lines = [];
      history.forEach(function (h) {
        if (!h || typeof h !== 'object') return;
        var role = h.role || '';
        var c = h.content || '';
        if (role === 'user') lines.push('用户：' + c);
        else if (role === 'assistant') lines.push(character + '：' + c);
        else if (role) lines.push(role + '：' + c);
      });
      historyText = lines.join('\n');
    }

    var prompt =
      '你是小说中的角色【' + character + '】。你的设定：' + (desc || '（无详细设定，请根据角色名合理推断）') + '。\n' +
      '世界观背景：' + (world || '（无）') + '\n\n' +
      '以下是之前的对话：\n' + (historyText || '（无）') + '\n\n' +
      '用户（读者/作者）说：' + message + '\n' +
      '请以' + character + '的身份、性格和说话风格回复，保持第一人称，不要出戏。直接回复内容，不要解释。';

    var result = await callAI(prompt, { temperature: 0.8, max_tokens: 4096 });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    var reply = (result.content || '').trim();
    if (!reply) {
      return { ok: false, error: 'AI 未返回内容' };
    }
    return { ok: true, reply: reply };
  }

  // ═══════════════════════════════════════════
  // 导出为全局对象 window.AIEngine
  // ═══════════════════════════════════════════
  global.AIEngine = {
    // 常量
    FORBIDDEN_WORDS: FORBIDDEN_WORDS,
    FORBIDDEN_PLOTS: FORBIDDEN_PLOTS,

    // 核心函数
    callAI: callAI,
    postProcess: postProcess,

    // 生成类
    generateChapter: generateChapter,
    generateOutline: generateOutline,
    generateCharacters: generateCharacters,
    generateChapterOutline: generateChapterOutline,

    // 对话类
    chat: chat,
    chatTalk: chatTalk,
    brainstorm: brainstorm,
    expandIdea: expandIdea,

    // 描写类
    sensory: sensory,

    // 检测/校验类
    validateAiFlavor: validateAiFlavor,
    extractState: extractState,
    validateAll: validateAll,
    checkCompleteness: checkCompleteness,
    checkContinuity: checkContinuity,

    // 辅助（暴露供外部调用）
    _parseJSONLenient: _parseJSONLenient,
    _worldToPrompt: _worldToPrompt,
    _runHardChecks: _runHardChecks
  };

})(typeof window !== 'undefined' ? window : this);
