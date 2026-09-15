// ════════════════════════════════════════════════════════════════
// 书斋 V65 - 离线 APK AI 调用层 (offline-ai.js)
// 直接从前端 fetch 调用大模型 API（DeepSeek / OpenAI / Ollama）
// 替代后端 ai_client.py 和 generator.py
// 纯 JavaScript（ES5 兼容，无 async/await，使用 Promise）
// 导出：window.OfflineAI
// 配置存储：localStorage 的 'shuzhai_ai_config' 键
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
  var _isChinese = Common._isChinese || function () { return false; };
  var _extractKeywords = Common._extractKeywords || function () { return []; };
  var _parseJSONLenient = Common._parseJSONLenient || function () { return null; };
  var _worldToPrompt = Common._worldToPrompt || function () { return ''; };
  var _triggerLorebook = Common._triggerLorebook || function () { return ''; };
  var _buildCharacterContext = Common._buildCharacterContext || function () { return ''; };
  var _buildForeshadowContext = Common._buildForeshadowContext || function () { return ''; };
  var postProcess = Common.postProcess || function (s) { return s; };
  var runHardChecks = Common.runHardChecks || function () { return []; };

  // ═══════════════════════════════════════════
  // 常量
  // ═══════════════════════════════════════════

  // localStorage 键名（与后端 ai_config.json 格式一致）
  var STORAGE_KEY = 'shuzhai_ai_config';

  // 默认配置（与后端 ai_client.py 的 _ensure_defaults 一致）
  var DEFAULT_CONFIG = {
    provider: 'deepseek',
    deepseek: {
      api_key: '',
      base_url: 'https://api.deepseek.com',
      model: 'deepseek-v4-flash',
      thinking: 'disabled',
      temperature: 0.7,
      max_tokens: 8192
    },
    ollama: {
      base_url: 'http://127.0.0.1:11434',
      model: 'qwen3:14b',
      temperature: 0.7,
      max_tokens: 4096
    },
    openai: {
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
      temperature: 0.7,
      max_tokens: 4096
    }
  };

  // ═══════════════════════════════════════════
  // 内部工具函数
  // ═══════════════════════════════════════════

  // 安全访问 localStorage（容错：某些 WebView 环境可能禁用）
  function _ls() {
    try {
      if (typeof localStorage !== 'undefined') return localStorage;
      if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
    } catch (e) { /* 隐私模式可能抛异常 */ }
    return null;
  }

  // 规范化 base_url，返回 OpenAI 兼容的 chat completions 端点
  function _buildChatEndpoint(baseUrl) {
    var base = (baseUrl || 'https://api.deepseek.com').replace(/\/+$/, '');
    // 若已含 /v1 则直接追加 /chat/completions，否则追加 /v1/chat/completions
    if (/\/v\d+$/.test(base)) {
      return base + '/chat/completions';
    }
    return base + '/v1/chat/completions';
  }

  // 规范化 base_url，返回 ollama generate 端点
  function _buildOllamaEndpoint(baseUrl) {
    var base = (baseUrl || 'http://127.0.0.1:11434').replace(/\/+$/, '');
    return base + '/api/generate';
  }

  // 深拷贝（简易版，用于配置对象）
  function _clone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (typeof JSON !== 'undefined' && JSON.parse) {
      try { return JSON.parse(JSON.stringify(obj)); } catch (e) { /* fallthrough */ }
    }
    var copy = {};
    for (var k in obj) {
      if (obj.hasOwnProperty(k)) copy[k] = obj[k];
    }
    return copy;
  }

  // 浅合并（兼容 Object.assign 不存在的环境）
  function _merge(target, source) {
    target = target || {};
    source = source || {};
    for (var k in source) {
      if (source.hasOwnProperty(k)) target[k] = source[k];
    }
    return target;
  }

  // ═══════════════════════════════════════════
  // 配置管理（移植 ai_client.py 的 _load_config / _save_config / _ensure_defaults）
  // ═══════════════════════════════════════════

  // 确保配置包含所有必要字段和默认值
  function _ensureDefaults(config) {
    config = config || {};
    if (!config.provider) config.provider = 'deepseek';

    if (!config.deepseek) {
      config.deepseek = _clone(DEFAULT_CONFIG.deepseek);
    } else {
      var ds = _clone(DEFAULT_CONFIG.deepseek);
      config.deepseek = _merge(ds, config.deepseek);
    }

    // 兼容修复：如果 deepseek.api_key 为空或无效，但顶层 api_key 有效，则同步
    var topKey = config.api_key || '';
    var dsKey = (config.deepseek && config.deepseek.api_key) || '';
    if (topKey && topKey.indexOf('sk-') === 0 && (!dsKey || dsKey.indexOf('sk-') !== 0)) {
      config.deepseek.api_key = topKey;
    }

    if (!config.ollama) {
      config.ollama = _clone(DEFAULT_CONFIG.ollama);
    } else {
      var ol = _clone(DEFAULT_CONFIG.ollama);
      config.ollama = _merge(ol, config.ollama);
    }

    if (!config.openai) {
      config.openai = _clone(DEFAULT_CONFIG.openai);
    } else {
      var oa = _clone(DEFAULT_CONFIG.openai);
      config.openai = _merge(oa, config.openai);
    }

    return config;
  }

  // 从 localStorage 读取 AI 配置（格式与后端 ai_config.json 一致）
  function getConfig() {
    var ls = _ls();
    if (!ls) return _ensureDefaults({});
    var raw = null;
    try { raw = ls.getItem(STORAGE_KEY); } catch (e) { raw = null; }
    if (!raw) {
      // 首次启动：尝试从全局变量迁移
      if (typeof window !== 'undefined' && window.__INITIAL_AI_CONFIG__) {
        return _ensureDefaults(window.__INITIAL_AI_CONFIG__);
      }
      return _ensureDefaults({});
    }
    var cfg = null;
    try { cfg = JSON.parse(raw); } catch (e) { cfg = {}; }
    return _ensureDefaults(cfg);
  }

  // 保存 AI 配置到 localStorage
  function saveConfig(config) {
    var ls = _ls();
    if (!ls) return { ok: false, error: 'localStorage 不可用' };
    var existing = getConfig();
    // 深合并：对 deepseek/ollama/openai 子对象做字段级合并
    config = config || {};
    for (var k in config) {
      if (!config.hasOwnProperty(k)) continue;
      if (k === 'deepseek' || k === 'ollama' || k === 'openai') {
        existing[k] = _merge(existing[k] || {}, config[k]);
      } else {
        existing[k] = config[k];
      }
    }
    existing = _ensureDefaults(existing);
    try {
      ls.setItem(STORAGE_KEY, JSON.stringify(existing));
      return { ok: true, config: existing };
    } catch (e) {
      return { ok: false, error: '保存失败: ' + (e.message || String(e)) };
    }
  }

  // ═══════════════════════════════════════════
  // AI 调用层（移植 ai_client.py）
  // ═══════════════════════════════════════════

  // 获取当前 provider 的配置（允许调用方覆盖 temperature / max_tokens）
  function _getProviderCfg(temperature, maxTokens) {
    var config = getConfig();
    var provider = config.provider || 'deepseek';
    var cfg = config[provider] || config.deepseek || {};
    cfg = _clone(cfg); // 浅拷贝避免修改原配置
    if (temperature !== undefined && temperature !== null) {
      cfg.temperature = temperature;
    }
    if (maxTokens !== undefined && maxTokens !== null) {
      cfg.max_tokens = maxTokens;
    }
    return { provider: provider, cfg: cfg, config: config };
  }

  // ═══════════════════════════════════════════
  // API Key 异步获取（内存缓存 + TTL，不写入 localStorage）
  // ═══════════════════════════════════════════

  var _apiKeyCache = null;      // { key, provider, ts }
  var _APIKEY_TTL = 30 * 60 * 1000; // 30 分钟过期

  function getApiKey(provider) {
    // 离线模式：后端不可用，直接返回 localStorage 中的 key（如有）
    if (window._isOfflineMode) {
      var cfg = getConfig();
      var prov = provider || cfg.provider || 'deepseek';
      var provCfg = cfg[prov] || {};
      return _resolve(provCfg.api_key || '');
    }

    // 在线模式：检查内存缓存
    var now = Date.now();
    if (_apiKeyCache && _apiKeyCache.key && (now - _apiKeyCache.ts) < _APIKEY_TTL) {
      if (!provider || provider === _apiKeyCache.provider) {
        return _resolve(_apiKeyCache.key);
      }
    }

    // 从后端异步获取
    var server = (window._shuzhaiServer || '') + '/api/ai/api-key';
    return fetch(server).then(function (resp) {
      return resp.json();
    }).then(function (data) {
      if (data && data.ok && data.api_key) {
        _apiKeyCache = { key: data.api_key, provider: data.provider, ts: Date.now() };
        return data.api_key;
      }
      return '';
    }).catch(function () {
      return '';
    });
  }

  function clearApiKeyCache() {
    _apiKeyCache = null;
  }

  // 调用 AI 生成文本（主入口）
  // onChunk 为函数时启用流式，否则非流式
  // 返回 Promise<string>，错误时 resolve "[生成失败: 错误信息]"
  function generate(prompt, onChunk, temperature, maxTokens) {
    // 在线模式：通过后端代理调用 AI，API Key 不暴露给前端
    if (!window._isOfflineMode) {
      return _callBackendProxy(prompt, temperature, maxTokens);
    }

    var bundle = _getProviderCfg(temperature, maxTokens);
    var provider = bundle.provider;
    var cfg = bundle.cfg;

    if (provider === 'ollama') {
      return _callOllama(prompt, cfg, onChunk);
    } else if (provider === 'deepseek' || provider === 'openai') {
      // 离线模式直连：先尝试 localStorage 中的 key，没有则异步从后端获取
      var localKey = cfg.api_key || '';
      if (localKey) {
        return _callOpenAICompatible(prompt, cfg, onChunk, localKey);
      }
      // localStorage 无 key，异步从后端获取（在线但需要直连的场景）
      return getApiKey(provider).then(function (key) {
        if (!key) return _resolve('[错误] 未配置 API Key，请在设置中配置或设置环境变量');
        return _callOpenAICompatible(prompt, cfg, onChunk, key);
      });
    } else {
      return _resolve('[错误] 不支持的 provider: ' + provider);
    }
  }

  // 通过后端代理调用 AI（安全：API Key 仅存后端）
  function _callBackendProxy(prompt, temperature, maxTokens) {
    var body = { prompt: prompt };
    if (temperature !== undefined && temperature !== null) body.temperature = temperature;
    if (maxTokens !== undefined && maxTokens !== null) body.max_tokens = maxTokens;

    var server = (window._shuzhaiServer || '') + '/api/ai/proxy';
    return fetch(server, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) {
        return resp.text().then(function (errText) {
          return '[生成失败: HTTP ' + resp.status + ' ' + _truncate(errText, 300) + ']';
        }, function () {
          return '[生成失败: HTTP ' + resp.status + ']';
        });
      }
      return resp.json().then(function (data) {
        if (data.ok && data.content !== undefined) {
          return data.content;
        }
        return '[生成失败: ' + ((data.error && data.error.message) || '未知错误') + ']';
      });
    }).catch(function (e) {
      return '[生成失败: 网络错误 - ' + (e.message || String(e)) + ']';
    });
  }

  // 流式生成（强制 stream:true）
  function generateStream(prompt, onChunk, temperature, maxTokens) {
    // onChunk 必须是函数
    if (typeof onChunk !== 'function') {
      onChunk = function () {};
    }
    return generate(prompt, onChunk, temperature, maxTokens);
  }

  // 调用 OpenAI 兼容接口（DeepSeek / OpenAI）
  function _callOpenAICompatible(prompt, cfg, onChunk, explicitKey) {
    var baseUrl = cfg.base_url || 'https://api.deepseek.com';
    var apiKey = explicitKey || cfg.api_key || '';
    var model = cfg.model || 'deepseek-v4-flash';
    var temperature = cfg.temperature !== undefined ? cfg.temperature : 0.7;
    var maxTokens = cfg.max_tokens !== undefined ? cfg.max_tokens : 4096;
    var useStream = typeof onChunk === 'function';

    if (!apiKey) {
      return _resolve('[错误] 未配置 API Key');
    }

    var endpoint = _buildChatEndpoint(baseUrl);

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

    return fetch(endpoint, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) {
        // 读取错误响应文本
        return resp.text().then(function (errText) {
          return '[生成失败: HTTP ' + resp.status + ' ' + _truncate(errText, 300) + ']';
        }, function () {
          return '[生成失败: HTTP ' + resp.status + ']';
        });
      }

      if (useStream) {
        // 流式响应：使用 ReadableStream 逐行解析
        return _readSSEStream(resp, onChunk);
      } else {
        // 非流式响应
        return resp.json().then(function (data) {
          var choice = (data.choices && data.choices[0]) || {};
          var msg = choice.message || {};
          var content = msg.content || '';
          if (!content) {
            // 某些推理模型把内容放在 reasoning_content 里
            content = msg.reasoning_content || '';
          }
          return content;
        }, function (e) {
          return '[生成失败: JSON解析错误 ' + (e.message || String(e)) + ']';
        });
      }
    }, function (e) {
      return '[生成失败: ' + (e.message || String(e)) + ']';
    });
  }

  // 读取 SSE 流（data: 前缀的 JSON，提取 choices[0].delta.content）
  function _readSSEStream(resp, onChunk) {
    var reader = null;
    try {
      reader = resp.body.getReader();
    } catch (e) {
      // 某些环境不支持 ReadableStream，降级为文本读取
      return resp.text().then(function (text) {
        return _parseSSEText(text, onChunk);
      }, function (e2) {
        return '[生成失败: ' + (e2.message || String(e2)) + ']';
      });
    }

    var decoder = null;
    try {
      decoder = new TextDecoder('utf-8');
    } catch (e) {
      decoder = null;
    }

    var result = [];
    var buffer = '';

    // 递归读取流（ES5 兼容，无 async/await）
    function readNext() {
      return reader.read().then(function (chunk) {
        if (chunk.done) {
          // 处理 buffer 中剩余内容
          if (buffer) {
            _processSSELine(buffer, result, onChunk);
          }
          return result.join('');
        }
        var text = '';
        if (decoder) {
          text = decoder.decode(chunk.value, { stream: true });
        } else if (chunk.value && chunk.value.toString) {
          text = chunk.value.toString();
        }
        buffer += text;
        var lines = buffer.split('\n');
        buffer = lines.pop(); // 保留最后不完整的行
        for (var i = 0; i < lines.length; i++) {
          _processSSELine(lines[i], result, onChunk);
        }
        return readNext();
      }, function (e) {
        return '[生成失败: 流读取错误 ' + (e.message || String(e)) + ']';
      });
    }

    return readNext();
  }

  // 处理单行 SSE 数据
  function _processSSELine(line, result, onChunk) {
    line = (line || '').trim();
    if (line.indexOf('data: ') !== 0) return;
    if (line === 'data: [DONE]') return;
    var jsonStr = line.substring(6);
    try {
      var parsed = JSON.parse(jsonStr);
      var delta = (parsed.choices && parsed.choices[0] && parsed.choices[0].delta) || {};
      var token = delta.content || '';
      if (token) {
        if (typeof onChunk === 'function') {
          try { onChunk(token); } catch (e) { /* 回调异常不影响主流程 */ }
        }
        result.push(token);
      }
    } catch (e) { /* skip invalid JSON */ }
  }

  // 降级解析：将完整 SSE 文本按行处理
  function _parseSSEText(text, onChunk) {
    var result = [];
    var lines = text.split('\n');
    for (var i = 0; i < lines.length; i++) {
      _processSSELine(lines[i], result, onChunk);
    }
    return result.join('');
  }

  // 调用 Ollama 接口
  function _callOllama(prompt, cfg, onChunk) {
    var baseUrl = cfg.base_url || 'http://127.0.0.1:11434';
    var model = cfg.model || 'qwen3:14b';
    var temperature = cfg.temperature !== undefined ? cfg.temperature : 0.7;
    var maxTokens = cfg.max_tokens !== undefined ? cfg.max_tokens : 4096;
    var useStream = typeof onChunk === 'function';

    var endpoint = _buildOllamaEndpoint(baseUrl);

    var body = {
      model: model,
      prompt: prompt,
      stream: useStream,
      options: {
        temperature: temperature,
        num_predict: maxTokens
      }
    };

    var headers = { 'Content-Type': 'application/json' };

    return fetch(endpoint, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (!resp.ok) {
        return resp.text().then(function (errText) {
          return '[生成失败: HTTP ' + resp.status + ' ' + _truncate(errText, 300) + ']';
        }, function () {
          return '[生成失败: HTTP ' + resp.status + ']';
        });
      }

      if (useStream) {
        // Ollama 流式：NDJSON（每行一个完整 JSON，含 response 字段）
        return _readOllamaStream(resp, onChunk);
      } else {
        // 非流式：单个 JSON
        return resp.text().then(function (rawText) {
          try {
            var data = JSON.parse(rawText);
            return data.response || '';
          } catch (e) {
            return '[生成失败: JSON解析错误 ' + (e.message || String(e)) + ']';
          }
        }, function (e) {
          return '[生成失败: ' + (e.message || String(e)) + ']';
        });
      }
    }, function (e) {
      return '[生成失败: ' + (e.message || String(e)) + ']';
    });
  }

  // 读取 Ollama NDJSON 流（每行 JSON，提取 response 字段）
  function _readOllamaStream(resp, onChunk) {
    var reader = null;
    try {
      reader = resp.body.getReader();
    } catch (e) {
      return resp.text().then(function (text) {
        return _parseOllamaText(text, onChunk);
      }, function (e2) {
        return '[生成失败: ' + (e2.message || String(e2)) + ']';
      });
    }

    var decoder = null;
    try {
      decoder = new TextDecoder('utf-8');
    } catch (e) {
      decoder = null;
    }

    var result = [];
    var buffer = '';

    function readNext() {
      return reader.read().then(function (chunk) {
        if (chunk.done) {
          if (buffer) {
            _processOllamaLine(buffer, result, onChunk);
          }
          return result.join('');
        }
        var text = '';
        if (decoder) {
          text = decoder.decode(chunk.value, { stream: true });
        } else if (chunk.value && chunk.value.toString) {
          text = chunk.value.toString();
        }
        buffer += text;
        var lines = buffer.split('\n');
        buffer = lines.pop();
        for (var i = 0; i < lines.length; i++) {
          _processOllamaLine(lines[i], result, onChunk);
        }
        return readNext();
      }, function (e) {
        return '[生成失败: 流读取错误 ' + (e.message || String(e)) + ']';
      });
    }

    return readNext();
  }

  // 处理单行 Ollama NDJSON
  function _processOllamaLine(line, result, onChunk) {
    line = (line || '').trim();
    if (!line) return;
    try {
      var chunk = JSON.parse(line);
      var token = chunk.response || '';
      if (token) {
        if (typeof onChunk === 'function') {
          try { onChunk(token); } catch (e) { /* ignore */ }
        }
        result.push(token);
      }
    } catch (e) { /* skip invalid JSON */ }
  }

  // 降级解析 Ollama 文本
  function _parseOllamaText(text, onChunk) {
    var result = [];
    var lines = text.split('\n');
    for (var i = 0; i < lines.length; i++) {
      _processOllamaLine(lines[i], result, onChunk);
    }
    return result.join('');
  }

  // 测试 AI 连接（发送简短 prompt "回复'OK'"，检查返回）
  function testConnection() {
    var config = getConfig();
    var provider = config.provider || 'deepseek';

    return generate("回复'OK'", null).then(function (result) {
      if (result && result.length > 0 && result.indexOf('失败') < 0 && result.indexOf('错误') < 0) {
        return { ok: true, message: '连接成功', provider: provider, response: _truncate(result, 100) };
      }
      return { ok: false, message: '连接失败: ' + _truncate(result, 200), provider: provider, response: result };
    });
  }

  // ═══════════════════════════════════════════
  // Prompt 构建（移植 generator.py 的 _build_generation_prompt 等）
  // ═══════════════════════════════════════════

  // 构建章节生成 Prompt（移植 _build_generation_prompt）
  // 参数：
  //   title         - 章节标题
  //   outline       - 章节大纲
  //   context       - 上下文（前文摘要等）
  //   chapterIndex  - 章节索引（0-based）
  //   worldSettings - 世界观设定对象
  //   characters    - 角色档案数组
  //   hooks         - 伏笔状态数组
  function buildChapterPrompt(title, outline, context, chapterIndex, worldSettings, characters, hooks) {
    var parts = [];

    var outlineStr = outline ? String(outline) : '';
    var titleStr = title ? String(title) : '';
    var ctxStr = context ? String(context) : '';

    // 世界观约束
    var worldText = _worldToPrompt(worldSettings);
    if (worldText) parts.push(worldText);

    // Lorebook 关键词触发
    var lorebookText = _triggerLorebook(outlineStr + ' ' + titleStr, worldSettings);
    if (lorebookText) parts.push(lorebookText);

    // 角色档案
    var charText = _buildCharacterContext(characters, outlineStr + ' ' + titleStr);
    if (charText) parts.push(charText);

    // 伏笔状态
    var hookText = _buildForeshadowContext(chapterIndex, hooks);
    if (hookText) parts.push(hookText);

    var forbiddenSample = FORBIDDEN_WORDS.slice(0, 10).join(', ');

    // 写作规范 + 章节信息（完整移植 generator.py 的 _build_generation_prompt）
    parts.push(
      '你是专业小说作家。请根据大纲和设定写作章节。\n\n' +
      '## 章节标题\n' + titleStr + '\n\n' +
      '## 当前章节\n第' + (chapterIndex + 1) + '章（共若干章）\n\n' +
      '## 章节大纲（严格按此结构写作）\n' + outlineStr + '\n\n' +
      '## 上下文\n' + ctxStr + '\n\n' +
      '## 终极通用写作规范（必须严格遵守）\n\n' +
      '### 一、整体剧情逻辑\n' +
      '1. 全篇内容连贯、主题层层递进，主线清晰不跑偏\n' +
      '2. 情节衔接自然，剧情推进有序，人物成长、世界观揭露、冲突升级全程稳步递进\n' +
      '3. 强化逻辑闭环，所有转折、设定、行为都有铺垫、有呼应，杜绝断层、突兀、逻辑矛盾\n' +
      '4. 所有段落、场景、副本、对话之间过渡顺滑，无生硬跳转\n' +
      '5. 严格遵循大纲中的剧情走向，不得偏离章节定位\n' +
      '6. 承接前文剧情，保持角色状态、时间线的连续性\n\n' +
      '### 二、文字表达精度\n' +
      '1. 表达精准克制，不用模糊虚词、笼统描述，每一句描写、设定、动作、心理都清晰落地\n' +
      '2. 统一设定口径，前后表述一致，不出现自我冲突设定\n' +
      '3. 句式灵活多变，长短句交替，杜绝重复单调句式，保持持续阅读节奏感\n' +
      '4. 感官细节 > 形容词堆砌，对白有潜台词，不要"XX说："开头\n\n' +
      '### 三、场景与语气适配\n' +
      '1. 随场景切换实时调整文风语气：对峙冷硬、打斗急促、幻境压抑、现实沉静、悬念留白\n' +
      '2. 不同角色严格区分语调、话术风格、思维方式，系统机械、反派狂傲、主角内敛、路人通俗，人设绝不同质化\n' +
      '3. 角色每个选择必须有代价，对白推动剧情而非填充字数\n\n' +
      '### 四、叙事节奏与张力\n' +
      '1. 把控叙事快慢：打戏、冲突、反转用短句提速；铺垫、心境、世界观揭秘用长句放缓沉淀\n' +
      '2. 强化剧情起伏，转折前预埋细节暗示，转折后自然缓冲，节奏松紧有度\n' +
      '3. 全程维持剧情张力，不灌水、不拖沓、不生硬科普，信息交付自然融入剧情\n\n' +
      '### 五、人物与成长线\n' +
      '1. 人物心境、认知、能力成长全程连贯，随剧情自然变化，不跳脱、不割裂\n' +
      '2. 每段剧情皆服务于主线推进、人物蜕变、真相揭露，保证整体递进感\n' +
      '3. 按四段结构写：引入(20%) / 展开(50%) / 高潮(20%) / 收尾(10%)\n\n' +
      '### 六、反AI检测规范\n' +
      '1. 句子长短交错：短句（3-8字）和长句（20-40字）交替，偶尔用单字独立段落\n' +
      '2. 段落长短不均：有的一句话，有的五六句，不要每段差不多长\n' +
      '3. 少用"的"字：每千字不超过20个"的"，多用"之"或重写句子去掉\n' +
      '4. 禁用连接词：不用"然而""因此""于是""紧接着""事实上"。用动作切换代替\n' +
      '5. 句首要多样：不连续两句以同一词开头\n' +
      '6. 口语化：用碎句、省略号、破折号、半句话\n' +
      '7. 少用"突然""忽然""仿佛""似乎"，每章最多各1次\n' +
      '8. 具体化：不写"一股寒意"，写"后脖颈汗毛竖起"\n' +
      '9. 不写AI总结句："这意味着…""不难看出…""这证明了…"\n' +
      '10. 禁用词汇：' + forbiddenSample + '\n' +
      '11. 禁用情节：' + FORBIDDEN_PLOTS.join(', ') + '\n' +
      '12. 必须写到2000字以上，目标字数 2000-4000 字\n\n' +
      '直接输出章节正文，不要标题。'
    );

    return parts.join('\n\n');
  }

  // 构建全书大纲生成 Prompt（移植 generate_outline）
  // 参数：
  //   worldSettings - 世界观设定对象
  //   characters    - 角色档案数组（可选）
  //   chapterCount  - 目标章节数
  function buildOutlinePrompt(worldSettings, characters, chapterCount) {
    var length = parseInt(chapterCount, 10) || 10;

    // 世界观
    var worldText = _worldToPrompt(worldSettings);
    var worldPart = worldText ? ('\n\n【世界观设定】\n' + worldText) : '';

    // 角色设定
    var charPart = '';
    if (characters && characters.length) {
      var charLines = [];
      for (var i = 0; i < characters.length; i++) {
        var c = characters[i];
        var name = c.name || '';
        var desc = c.description || c.background || c.personality || '';
        charLines.push('- ' + name + '：' + desc);
      }
      if (charLines.length) {
        charPart = '\n\n【已有角色设定】\n' + charLines.join('\n');
      }
    }

    var prompt =
      '生成全书大纲，约' + length + '章完结。\n' +
      worldPart + charPart + '\n\n' +
      '要求：\n' +
      '- 以' + length + '章为基准，根据故事节奏可±1章调整\n' +
      '- 最后一章必须是完结章，给出明确结局\n' +
      '- 每章必须有具体事件\n' +
      '- 【重要】如果已有世界观和角色设定，大纲必须基于这些设定生成，使用相同的角色名和世界观\n\n' +
      '输出格式：\n' +
      '## 核心世界观设定\n' +
      '## 总纲\n' +
      '## 各章节大纲\n' +
      '（每章一行：第X章·章名 | 核心冲突 | 关键转折 | 信息释放）\n\n' +
      '禁止：概述/总结/比喻/套话。每章必须有具体事件。';

    return prompt;
  }

  // 构建章节大纲生成 Prompt（移植 generate_chapter_outline）
  // 参数：
  //   chapterIndex       - 章节索引（0-based）
  //   chapterTitle       - 章节标题
  //   novelOutline       - 全书大纲
  //   prevChapterOutline - 前一章大纲（可选）
  function buildChapterOutlinePrompt(chapterIndex, chapterTitle, novelOutline, prevChapterOutline, volText, actText, context) {
    var title = chapterTitle || ('第' + (chapterIndex + 1) + '章');
    var ctx = '';
    // 当前卷纲要（最高优先级，前置）
    if (volText) ctx += volText + '\n\n';
    // 当前幕事件（强制约束）
    if (actText) ctx += actText + '\n\n【强制约束】本章大纲必须严格基于上方"当前幕"中的事件来规划。\n\n';
    if (novelOutline) ctx += '【全书大纲】\n' + _truncate(novelOutline, 3000) + '\n\n';
    if (prevChapterOutline) ctx += '【前一章大纲】\n' + _truncate(prevChapterOutline, 1500) + '\n\n';
    if (context) ctx += '【补充上下文】\n' + context + '\n\n';
    ctx += '【当前章节】第' + (chapterIndex + 1) + '章';

    var forbiddenSample = FORBIDDEN_WORDS.slice(0, 8).join(', ');

    var prompt =
      '为章节《' + title + '》生成详细大纲。这是第' + (chapterIndex + 1) + '章的专属大纲，内容必须与其他章节不同。\n\n' +
      '上下文：' + ctx + '\n\n' +
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

    return prompt;
  }

  // 构建人物档案生成 Prompt（移植 generate_characters）
  // 参数：
  //   worldSettings - 世界观设定对象
  //   genre         - 小说类型
  function buildCharacterPrompt(worldSettings, genre) {
    var worldText = _worldToPrompt(worldSettings);

    var prompt =
      '你是专业小说角色设计师。基于世界观设定，预生成一套完整的角色库。' +
      '要求：1个主角、2-3个核心配角（盟友/同伴）、1-2个核心反派、2-3个次要配角。' +
      '角色之间要有羁绊关系。角色要符合世界观设定，不要违反禁止事项。\n\n' +
      '【世界观设定】\n' + (worldText || '（未设定）') + '\n\n' +
      '要求：\n' +
      '1. 为每个角色生成完整档案：姓名/身份/阵营(主角/配角/反派/中立)/性格/身世过往/执念/软肋/目标/人物羁绊/角色定位(核心/次要)\n' +
      '2. 人物羁绊用结构化格式：[{"target":"角色名","relation":"仇恨/信任/爱慕/利用/师徒","note":"说明"}]\n' +
      '3. 核心人物至少1个主角、1个核心反派\n' +
      '4. 性格、执念、软肋必须具体，不要泛泛而谈\n' +
      '5. 人物不得违背世界观设定（时代环境、世界规则）\n\n' +
      '返回JSON数组（放在```json代码块中），格式：\n' +
      '```json\n[{"name":"","identity":"","faction":"","personality":"","background":"","obsession":"","weakness":"","goal":"","goals":[{"text":"","weight":1.0}],"bonds":[{"target":"","relation":"","note":""}],"importance":"","cognitive_boundary":""}]\n```';

    return prompt;
  }

  // ═══════════════════════════════════════════
  // Gate 闭环：生成 → 校验 → 修订（最多3轮）
  // 移植 generator.py 的 generate_and_validate
  // 参数：
  //   title        - 章节标题
  //   outline      - 章节大纲
  //   context      - 上下文
  //   chapterIndex - 章节索引（0-based）
  //   options      - { worldSettings, characters, hooks, maxRetries, onChunk, temperature, maxTokens, forbiddenWords }
  // 返回 Promise<{ok, content, validation_log, attempts, warning?}>
  function generateAndValidate(title, outline, context, chapterIndex, options) {
    options = options || {};
    var worldSettings = options.worldSettings;
    var characters = options.characters;
    var hooks = options.hooks;
    var maxRetries = options.maxRetries || 3;
    var onChunk = typeof options.onChunk === 'function' ? options.onChunk : null;
    var temperature = options.temperature !== undefined ? options.temperature : 0.75;
    var maxTokens = options.maxTokens !== undefined ? options.maxTokens : 8192;
    var forbiddenWords = options.forbiddenWords;

    var validationLog = [];
    var content = '';
    var localContext = context || '';

    // 递归执行每一轮（ES5 兼容，使用 Promise 链）
    function attemptRound(round) {
      if (round >= maxRetries) {
        // 达到最大重试次数 — 返回尽力结果
        if (content && content.length >= 200) {
          content = postProcess(content);
          return _resolve({
            ok: true,
            content: content,
            validation_log: validationLog,
            attempts: maxRetries,
            warning: '经过' + maxRetries + '轮修订，内容已生成但仍有' + validationLog.length + '条建议'
          });
        }
        return _resolve({
          ok: false,
          content: content,
          validation_log: validationLog,
          attempts: maxRetries,
          warning: '经过' + maxRetries + '轮修订仍未完全通过校验'
        });
      }

      // 构建 prompt
      var prompt = buildChapterPrompt(title, outline, localContext, chapterIndex, worldSettings, characters, hooks);
      // 如果有上一版问题，追加到 prompt 末尾
      if (validationLog.length) {
        var issueLines = [];
        for (var i = 0; i < validationLog.length; i++) {
          issueLines.push('- ' + validationLog[i]);
        }
        prompt += '\n\n## 上一版需要修复的问题\n' + issueLines.join('\n');
      }

      // 生成（仅第一轮使用流式回调，后续轮次静默重试）
      var chunkCb = (round === 0 && onChunk) ? onChunk : null;

      return generate(prompt, chunkCb, temperature, maxTokens).then(function (result) {
        // 检查生成是否失败
        if (result && result.indexOf && result.indexOf('[生成失败') === 0) {
          return {
            ok: false,
            content: '',
            validation_log: validationLog,
            attempts: round + 1,
            warning: result
          };
        }
        content = result || '';

        // 跑硬校验
        var issues = runHardChecks(content, forbiddenWords);
        validationLog = validationLog.concat(issues);

        if (issues.length === 0) {
          // 校验通过 — 后处理并返回
          content = postProcess(content);
          return {
            ok: true,
            content: content,
            validation_log: validationLog,
            attempts: round + 1
          };
        }

        // 反馈问题用于下一轮重写
        var issueText = [];
        for (var j = 0; j < issues.length; j++) {
          issueText.push('- ' + issues[j]);
        }
        localContext += '\n\n[上一版问题]\n' + issueText.join('\n');

        // 继续下一轮
        return attemptRound(round + 1);
      });
    }

    return attemptRound(0);
  }

  // ═══════════════════════════════════════════
  // 辅助：将值包装为已 resolved 的 Promise（兼容非 Promise 环境）
  // ═══════════════════════════════════════════
  function _resolve(value) {
    if (typeof Promise !== 'undefined') {
      return Promise.resolve(value);
    }
    // 极端降级：返回 thenable 对象
    return {
      then: function (onFulfilled) {
        return _resolve(onFulfilled ? onFulfilled(value) : value);
      },
      catch: function () { return _resolve(value); }
    };
  }

  // ═══════════════════════════════════════════
  // 导出为全局对象 window.OfflineAI
  // ═══════════════════════════════════════════
  global.OfflineAI = {
    // 常量
    FORBIDDEN_WORDS: FORBIDDEN_WORDS,
    FORBIDDEN_PLOTS: FORBIDDEN_PLOTS,
    STORAGE_KEY: STORAGE_KEY,

    // 配置管理
    getConfig: getConfig,
    saveConfig: saveConfig,

    // API Key 异步获取（内存缓存，不写 localStorage）
    getApiKey: getApiKey,
    clearApiKeyCache: clearApiKeyCache,

    // AI 调用
    generate: generate,
    generateStream: generateStream,
    testConnection: testConnection,

    // Prompt 构建
    buildChapterPrompt: buildChapterPrompt,
    buildOutlinePrompt: buildOutlinePrompt,
    buildChapterOutlinePrompt: buildChapterOutlinePrompt,
    buildCharacterPrompt: buildCharacterPrompt,

    // 后处理与校验
    postProcess: postProcess,
    runHardChecks: runHardChecks,
    generateAndValidate: generateAndValidate,

    // 辅助（暴露供外部调用）
    _worldToPrompt: _worldToPrompt,
    _triggerLorebook: _triggerLorebook,
    _buildCharacterContext: _buildCharacterContext,
    _buildForeshadowContext: _buildForeshadowContext,
    _parseJSONLenient: _parseJSONLenient
  };

})(typeof window !== 'undefined' ? window : this);
