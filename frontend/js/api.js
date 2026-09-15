// ══════════════════════════════════════════
// Service Worker 版本协调
// ══════════════════════════════════════════
const SW_CACHE_VERSION = 'shuzhai-v1';

// 检测 SW 更新并提示用户
function checkServiceWorkerUpdate() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistration().then(function(reg) {
      if (reg && reg.waiting) {
        console.log('[API] SW 更新就绪，刷新页面以应用新版本');
      }
    });
  }
}

// === 书斋 V65 后端 API 桥接 ===
// 优先使用用户配置的服务器地址（APK模式），否则用当前页面地址
function _getServerBase() {
  var saved = localStorage.getItem('shuzhai_server');
  if (saved) return saved.replace(/\/+$/, '');
  // Capacitor/Android环境：从本地assets加载，API调用本地服务器
  if (window.location.protocol === 'file:' ||
      (typeof Capacitor !== 'undefined' && Capacitor.isNative) ||
      window.location.hostname === 'localhost' && window.location.port === '') {
    return 'http://127.0.0.1:8888';
  }
  return window.location.origin;
}

const API_BASE = _getServerBase();

// 单用户模式 — 无认证，直接返回请求头
function _authHeaders(extra) {
  return extra || {};
}

// 工具函数：智能分段（中文语义）
function smartParagraphSplit(text) {
  if (!text || text.includes('\n\n')) return text;
  var sentences = text.split(/([。！？…]+(?:」|』|"|')?)/);
  var result = '';
  var para = '';
  var count = 0;
  for (var i = 0; i < sentences.length; i += 2) {
    var s = (sentences[i] || '') + (sentences[i + 1] || '');
    if (!s.trim()) continue;
    para += s;
    count++;
    var isDialogueEnd = /[。！？…][」'"']$/.test(s.trim());
    var isSceneShift = false;
    var next = sentences[i + 2] || '';
    if (next && /^\s*(此时|忽然|突然|就在这时|与此同时|另一边|远处|翌日|次日|数日后|当晚|夜深|清晨|午后|傍晚|那|这|只见|但|然而|不过|可是|原来)/.test(next)) {
      isSceneShift = true;
    }
    if (isDialogueEnd || isSceneShift || count >= 5) {
      result += para.trim() + '\n\n';
      para = '';
      count = 0;
    }
  }
  if (para.trim()) result += para.trim();
  return result;
}

// 工具函数：将纯文本转换为HTML段落
function textToHTML(text) {
  if (!text) return '<p></p>';
  // 清除AI编辑批注，防止混入正文
  if (typeof _stripEditAnnotations === 'function') text = _stripEditAnnotations(text);
  // 如果文本已经是HTML（包含<p>标签），直接返回，避免二次包裹
  if (/<p[\s>]/i.test(text) || /<h[1-6][\s>]/i.test(text) || /<br[\s\/>]/i.test(text)) {
    return text;
  }
  // 如果文本没有段落分隔，自动按中文语义分段
  text = smartParagraphSplit(text);
  const paragraphs = text.split(/\n\s*\n/);
  return paragraphs.map(p => {
    const trimmed = p.trim();
    if (!trimmed) return '';
    // 处理markdown标题 (# → h2, ## → h3)
    if (/^#{1,3}\s/.test(trimmed)) {
      var level = (trimmed.match(/^#+/) || [''])[0].length;
      var titleText = trimmed.replace(/^#+\s/, '');
      return '<h' + (level + 1) + ' class="md-heading">' + titleText + '</h' + (level + 1) + '>';
    }
    const withBr = trimmed.replace(/\n/g, '<br>');
    return '<p>' + withBr + '</p>';
  }).filter(p => p).join('\n');
}

// 把 error 字段统一转为可读字符串
function _flattenError(obj) {
  if (!obj) return '';
  if (typeof obj === 'string') return obj;
  if (typeof obj === 'object') {
    if (obj.message) return obj.message;
    if (obj.error) return _flattenError(obj.error);
    try { return JSON.stringify(obj); } catch(_) { return String(obj); }
  }
  return String(obj);
}

// === 超时与重试配置 ===
var _API_DEFAULT_TIMEOUT = 30000; // 30秒超时
var _API_MAX_RETRIES = 2;         // 最多重试2次（首次+2次重试=共3次请求）
var _API_RETRY_DELAY_BASE = 1000; // 指数退避基数（毫秒）

// 判断是否应该重试
function _apiShouldRetry(error, attempt, status, maxRetries) {
  var limit = (typeof maxRetries === 'number') ? maxRetries : _API_MAX_RETRIES;
  if (attempt >= limit) return false;
  if (!status) return true; // 网络错误（无 status）重试
  if (status >= 500 && status < 600) return true; // 5xx 服务端错误重试
  if (status === 429) return true; // 429 限流重试
  return false; // 4xx 客户端错误不重试
}

// 指数退避等待
function _apiWait(attempt) {
  var delay = _API_RETRY_DELAY_BASE * Math.pow(2, attempt - 1);
  return new Promise(function(resolve) {
    setTimeout(resolve, delay);
  });
}

async function api(path, opts={}) {
  // 离线模式：APK环境且配置了离线模式
  if (window._isOfflineMode && window.OfflineAPI) {
    try {
      return await OfflineAPI.handle(path, opts || {});
    } catch(e) {
      console.error('[OfflineAPI]', path, e);
      return {ok: false, error: e.message};
    }
  }

  var timeout = opts.timeout || _API_DEFAULT_TIMEOUT;
  var maxRetries = opts.retries !== undefined ? opts.retries : _API_MAX_RETRIES;
  var attempt = 0;
  var lastError = null;

  function doRequest() {
    attempt++;
    return new Promise(function(resolve) {
      var controller = new AbortController();
      var timeoutId = setTimeout(function() {
        controller.abort();
      }, timeout);

      try {
        var headers = _authHeaders({'Content-Type': 'application/json'});
        if (opts.headers) Object.assign(headers, opts.headers);
        var fetchOpts = Object.assign({}, opts, {
          headers: headers,
          signal: controller.signal
        });

        fetch(API_BASE + path, fetchOpts)
          .then(function(res) {
            clearTimeout(timeoutId);

            if (res.status === 401) {
              // 单用户模式不再有401，如果出现说明服务异常
              resolve({ok:false, error:'服务异常(status 401)'});
              return;
            }

            if (!res.ok) {
              // 判断是否重试
              if (_apiShouldRetry(null, attempt, res.status, maxRetries)) {
                _apiWait(attempt).then(function() {
                  doRequest().then(resolve);
                });
                return;
              }

              var errBody = '';
              try {
                res.json().then(function(errData) {
                  try { errBody = JSON.stringify(errData); } catch(_) {}
                  var errMsg = res.status + ' ' + res.statusText + (errBody ? ' ' + errBody.substring(0, 200) : '');
                  resolve({ok: false, error: errMsg});
                }).catch(function() {
                  resolve({ok: false, error: res.status + ' ' + res.statusText});
                });
              } catch(_) {
                resolve({ok: false, error: res.status + ' ' + res.statusText});
              }
              return;
            }

            res.json().then(function(data) {
              // 统一处理：把 error 字段转为字符串，避免 [object Object]
              if (data && data.ok === false && data.error) {
                data.error = _flattenError(data.error);
              }
              resolve(data);
            }).catch(function(e) {
              // JSON 解析失败
              if (_apiShouldRetry(e, attempt, res.status, maxRetries)) {
                _apiWait(attempt).then(function() {
                  doRequest().then(resolve);
                });
                return;
              }
              resolve({ok: false, error: '响应解析失败: ' + e.message});
            });
          })
          .catch(function(e) {
            clearTimeout(timeoutId);
            var isTimeout = e.name === 'AbortError';
            var errorMsg = isTimeout ? '请求超时（' + (timeout/1000) + '秒）' : (e.message || '网络错误');
            lastError = errorMsg;

            // 判断是否重试
            if (_apiShouldRetry(e, attempt, isTimeout ? 0 : null, maxRetries)) {
              console.warn('[API] 第' + attempt + '次失败，重试中...', path, errorMsg);
              _apiWait(attempt).then(function() {
                doRequest().then(resolve);
              });
              return;
            }

            console.error('[API]', path, errorMsg);
            resolve({ok: false, error: errorMsg});
          });
      } catch(e) {
        clearTimeout(timeoutId);
        console.error('[API]', path, e);
        resolve({ok: false, error: e.message});
      }
    });
  }

  return doRequest();
}

// 通过后端调用 AI（后端版本）
async function callAI(messages, opts={}) {
  return await api('/api/ai/chat', {
    method: 'POST',
    body: JSON.stringify({messages, ...opts})
  });
}

// 覆盖原型函数，对接真实后端
let _realProject = null;
async function newProject(title, genre, length) {
  const r = await api('/api/project/new', {
    method: 'POST', body: JSON.stringify({title, genre, length})
  });
  if (r.ok) _realProject = r;
  return r;
}
async function saveCurrentProject() {
  return await api('/api/project/save', {method: 'POST'});
}
async function loadProjectInfo() {
  return await api('/api/project/info');
}
async function addChapter(title, volIndex) {
  var body = {title};
  if (typeof volIndex !== 'undefined') body.vol_index = volIndex;
  return await api('/api/chapter/add', {
    method: 'POST', body: JSON.stringify(body)
  });
}
async function getChapterList() {
  var allChapters = [];
  var page = 1;
  var pageSize = 100;
  var totalPages = 1;
  var firstResp = null;
  
  while (page <= totalPages) {
    var r = await api('/api/chapter/list?page=' + page + '&page_size=' + pageSize);
    if (!r || !r.ok) return r || { ok: false, error: '获取章节列表失败' };
    if (!firstResp) firstResp = r;
    if (r.data) allChapters = allChapters.concat(r.data);
    if (r.pagination && r.pagination.total_pages) {
      totalPages = r.pagination.total_pages;
    } else {
      totalPages = 0;
    }
    page++;
  }
  
  firstResp.data = allChapters;
  firstResp.chapters = allChapters;
  return firstResp;
}
async function selectChapter(index) {
  return await api('/api/chapter/load?index=' + index);
}
async function saveChapter(index, content) {
  // 保存前清除AI编辑批注
  if (content && typeof _stripEditAnnotations === 'function') content = _stripEditAnnotations(content);
  return await api('/api/chapter/save', {
    method: 'POST', body: JSON.stringify({index, content})
  });
}
async function generateOutline(title, genre, length) {
  return await api('/api/generate/outline', {
    method: 'POST', body: JSON.stringify({title, genre, length}),
    timeout: 120000  // 全书大纲生成可能需要较长时间
  });
}
async function generateChapterOutline(title, context, chapterIndex) {
  return await api('/api/generate/chapter-outline', {
    method: 'POST', body: JSON.stringify({title, context: context||'', chapter_index: chapterIndex||0}),
    timeout: 120000  // 章节大纲生成可能需要较长时间，设置120秒超时
  });
}
async function generateChapter(title, outline, context, chapterIndex) {
  // 获取启用的技能包规则（polish和generate scope）
  var skillRules = '';
  if (typeof SkillPack !== 'undefined') {
    var polishRules = SkillPack.getEnabledSkillsContent('polish') || '';
    var generateRules = SkillPack.getEnabledSkillsContent('generate') || '';
    var rules = [];
    if (polishRules) rules.push(polishRules);
    if (generateRules) rules.push(generateRules);
    skillRules = rules.join('\n\n---\n\n');
  }
  return await api('/api/generate/chapter', {
    method: 'POST', body: JSON.stringify({title, outline, context: context||'', chapter_index: chapterIndex||0, skill_rules: skillRules}),
    timeout: 180000  // 正文生成通常需要较长时间，设置180秒超时
  });
}

// C4 预览确认：先通过 gate 生成（不保存），返回内容+审计结果
async function generateChapterPreview(title, outline, context, chapterIndex) {
  var skillRules = '';
  if (typeof SkillPack !== 'undefined') {
    var polishRules = SkillPack.getEnabledSkillsContent('polish') || '';
    var generateRules = SkillPack.getEnabledSkillsContent('generate') || '';
    var rules = [];
    if (polishRules) rules.push(polishRules);
    if (generateRules) rules.push(generateRules);
    skillRules = rules.join('\n\n---\n\n');
  }
  return await api('/api/generate/gate', {
    method: 'POST', body: JSON.stringify({title, outline, context: context||'', chapter_index: chapterIndex||0, skill_rules: skillRules}),
    timeout: 180000
  });
}

// C4 确认保存：将预览内容写入磁盘
async function confirmChapterSave(content, chapterIndex, title, validationLog) {
  return await api('/api/generate/confirm', {
    method: 'POST', body: JSON.stringify({content, chapter_index: chapterIndex, title: title||'', validation_log: validationLog||[]}),
    timeout: 30000
  });
}
async function checkConflicts(content, index=-1, memory='', context=null) {
  return await api('/api/validate/conflict', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkTimeline(content, index=-1, memory='', context=null) {
  return await api('/api/validate/timeline', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkTwist(content, index=-1, memory='', context=null) {
  return await api('/api/validate/twist', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkDrift(content, index=-1, memory='', context=null) {
  return await api('/api/validate/drift', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkDuplicate(content, index=-1, memory='', context=null) {
  return await api('/api/validate/duplicate', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkStyle(content, index=-1, memory='', context=null) {
  return await api('/api/validate/style', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkQuality(content, index=-1, memory='', context=null) {
  return await api('/api/validate/quality', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}
async function checkMemory(content, index=-1, memory='', context=null) {
  return await api('/api/validate/memory', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}

// ── 章节完整性+连贯性检查（集成到主页检查面板）──
async function checkCompleteness(content, index=-1, memory='', context=null) {
  // 获取当前章节标题
  var title = '';
  if (typeof chapters !== 'undefined' && chapters && chapters[index] && chapters[index].title) {
    title = chapters[index].title;
  } else if (typeof currentChapterIndex !== 'undefined') {
    title = '第' + (index + 1) + '章';
  }
  return await api('/api/check/completeness', {
    method: 'POST', body: JSON.stringify({content: content, title: title})
  });
}

async function checkContinuity(content, index=-1, memory='', context=null) {
  // 连贯性需要前后两章，自动获取前一章内容
  var prevContent = '';
  var prevTitle = '';
  var currTitle = '';
  
  // 优先从前端chapters数组获取
  if (typeof chapters !== 'undefined' && chapters && index > 0 && chapters[index-1] && chapters[index-1].content) {
    prevContent = chapters[index-1].content;
    prevTitle = chapters[index-1].title || ('第' + index + '章');
    currTitle = (chapters[index] && chapters[index].title) || ('第' + (index+1) + '章');
  }
  
  // 如果前端没有content，从后端API加载前一章
  if (!prevContent && index > 0) {
    try {
      var prevCh = await api('/api/chapter/load?index=' + (index - 1));
      if (prevCh && prevCh.content && prevCh.content.trim().length > 50) {
        prevContent = prevCh.content;
        prevTitle = prevCh.title || ('第' + index + '章');
      }
    } catch(e) { /* ignore */ }
    // 获取当前章标题
    if (typeof chapters !== 'undefined' && chapters && chapters[index]) {
      currTitle = chapters[index].title || ('第' + (index+1) + '章');
    } else {
      currTitle = '第' + (index+1) + '章';
    }
  }
  
  if (!prevContent) {
    // 第一章没有前一章，不报错，返回提示信息
    if (index <= 0) {
      return {ok: true, result: '第一章无需连贯性检查，连贯性检查从第二章开始。'};
    }
    return {ok: false, error: '前一章内容为空，请确认前一章已生成正文。'};
  }
  return await api('/api/check/continuity', {
    method: 'POST', body: JSON.stringify({
      chapter_a: prevContent,
      chapter_b: content,
      title_a: prevTitle,
      title_b: currTitle
    })
  });
}
async function checkAllCombined(content, index=-1, memory='', context=null) {
  return await api('/api/validate/all', {
    method: 'POST', body: JSON.stringify({content, index, memory, context: context||undefined})
  });
}

// ── 全局一致性检查（世界观↔人物↔章节大纲）──
async function checkConsistency(content='', index=-1) {
  // 一致性检查需要调用多次AI，给300秒超时
  var controller = new AbortController();
  var timeoutId = setTimeout(function() { controller.abort(); }, 300000);
  try {
    var headers = _authHeaders({'Content-Type': 'application/json'});
    const res = await fetch(API_BASE + '/api/validate/consistency', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({content: content, index: index}),
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    if (res.status === 401) { return {ok:false, error:'服务异常(401)'}; }
    if (!res.ok) {
      var errBody = '';
      try { errBody = await res.text(); } catch(e) {}
      return {ok:false, error: 'HTTP ' + res.status + ': ' + errBody.substring(0,200)};
    }
    return await res.json();
  } catch(e) {
    clearTimeout(timeoutId);
    if (e.name === 'AbortError') return {ok:false, error:'一致性检查超时（300秒），请减少检查项或重试'};
    return {ok:false, error: e.message};
  }
}

// ── 章节大纲↔正文对齐检查 ──
async function checkChapterAlignment(content, index=-1, chapterOutline='') {
  return await api('/api/validate/chapter-alignment', {
    method: 'POST', body: JSON.stringify({content, index, chapter_outline: chapterOutline})
  });
}
async function getSettings() {
  return await api('/api/project/settings');
}
async function updateSettings(data) {
  return await api('/api/project/settings', {
    method: 'POST', body: JSON.stringify(data)
  });
}
async function getStatus() {
  return await api('/api/project/status');
}

// ========== AI Model Config ==========
let currentProvider = 'deepseek';

function switchModelProvider(prov) {
  currentProvider = prov;
  document.querySelectorAll('.mp-tab').forEach(t => t.classList.toggle('active', t.dataset.provider === prov));
  // Toggle panels in top-right popover
  var panels = ['deepseek', 'ollama', 'openai', 'doubao', 'kimi'];
  panels.forEach(p => {
    var panel = document.getElementById('mp-' + p + '-panel');
    if (panel) panel.style.display = prov === p ? 'block' : 'none';
  });
  saveModelConfig();
}

async function testConnection() {
  try { return await api('/api/ai/test'); } catch(e) { return {ok:false,error:e.message}; }
}

function fillTaskProviderOptions() {
  const ids = ['mp-task-writing', 'mp-task-architecture', 'mp-task-check', 'mp-task-summary', 'mp-task-chat'];
  const opts = [
    ['', '跟随默认'],
    ['deepseek', 'DeepSeek'],
    ['ollama', 'Ollama'],
    ['openai', 'OpenAI'],
    ['doubao', '豆包'],
    ['kimi', 'Kimi']
  ];
  ids.forEach(id => {
    const s = document.getElementById(id);
    if (!s || s.options.length > 0) return;
    opts.forEach(([v, label]) => {
      const o = document.createElement('option');
      o.value = v; o.textContent = label;
      s.appendChild(o);
    });
  });
}

function getModelConfig() {
  const el = (id) => document.getElementById(id);
  // 任务路由：只提交显式配置的项，留空=跟随全局 provider
  const task_provider = {};
  ['writing', 'architecture', 'check', 'summary', 'chat'].forEach(t => {
    const v = el('mp-task-' + t)?.value;
    if (v) task_provider[t] = v;
  });
  return {
    provider: currentProvider,
    task_provider: task_provider,
    deepseek: {
      api_key: el('mp-api-key')?.value || '',
      base_url: el('mp-endpoint')?.value || 'https://api.deepseek.com',
      model: el('mp-model-name')?.value || 'deepseek-v4-flash',
      thinking: 'disabled',
      temperature: parseFloat(el('mp-temp')?.value || 0.7),
      max_tokens: parseInt(el('mp-maxwords')?.value || 4096)
    },
    ollama: {
      base_url: el('mp-ollama-host')?.value || 'http://localhost:11434',
      model: el('mp-ollama-model')?.value || 'qwen2.5:14b',
      temperature: parseFloat(el('mp-temp')?.value || 0.7),
      max_tokens: parseInt(el('mp-maxwords')?.value || 4096)
    },
    openai: {
      api_key: el('mp-openai-key')?.value || '',
      base_url: el('mp-openai-endpoint')?.value || 'https://api.openai.com/v1',
      model: el('mp-openai-model')?.value || 'gpt-4o-mini',
      temperature: parseFloat(el('mp-temp')?.value || 0.7),
      max_tokens: parseInt(el('mp-maxwords')?.value || 4096)
    },
    doubao: {
      api_key: el('mp-doubao-key')?.value || '',
      base_url: el('mp-doubao-endpoint')?.value || 'https://ark.cn-beijing.volces.com/api/v3',
      model: el('mp-doubao-model')?.value || 'doubao-seed-2.0-pro',
      temperature: parseFloat(el('mp-temp')?.value || 0.7),
      max_tokens: parseInt(el('mp-maxwords')?.value || 4096)
    },
    kimi: {
      api_key: el('mp-kimi-key')?.value || '',
      base_url: el('mp-kimi-endpoint')?.value || 'https://api.moonshot.cn/v1',
      model: el('mp-kimi-model')?.value || 'moonshot-v1-32k',
      temperature: parseFloat(el('mp-temp')?.value || 0.7),
      max_tokens: parseInt(el('mp-maxwords')?.value || 4096)
    }
  };
}

function updateModelBadge(cfg) {
  const badge = document.getElementById('model-badge');
  if (!badge) return;
  const provider = cfg.provider || currentProvider || 'deepseek';
  let hasKey = false, label = '未配置', dotClass = '';
  if (provider === 'ollama') {
    hasKey = true;
    label = (cfg.ollama && cfg.ollama.model) || 'Ollama';
    dotClass = ' ok';
  } else if (provider === 'deepseek') {
    hasKey = !!(cfg.deepseek && cfg.deepseek.api_key);
    // Also mark as configured if base_url is set (user may use env var for key)
    if (!hasKey && cfg.deepseek && cfg.deepseek.base_url) hasKey = true;
    label = hasKey ? ((cfg.deepseek && cfg.deepseek.model) || 'DeepSeek') : '未配置';
    dotClass = hasKey ? ' ok' : '';
  } else if (provider === 'openai') {
    hasKey = !!(cfg.openai && cfg.openai.api_key);
    if (!hasKey && cfg.openai && cfg.openai.base_url) hasKey = true;
    label = hasKey ? 'OpenAI' : '未配置';
    dotClass = hasKey ? ' ok' : '';
  } else if (provider === 'doubao') {
    hasKey = !!(cfg.doubao && cfg.doubao.api_key);
    if (!hasKey && cfg.doubao && cfg.doubao.base_url) hasKey = true;
    label = hasKey ? '豆包' : '未配置';
    dotClass = hasKey ? ' ok' : '';
  } else if (provider === 'kimi') {
    hasKey = !!(cfg.kimi && cfg.kimi.api_key);
    if (!hasKey && cfg.kimi && cfg.kimi.base_url) hasKey = true;
    label = hasKey ? 'Kimi' : '未配置';
    dotClass = hasKey ? ' ok' : '';
  } else {
    hasKey = false;
    label = '未配置';
    dotClass = '';
  }
  badge.className = 'model-badge' + (hasKey ? ' configured' : ' unconfigured');
  badge.innerHTML = '<span class="conn-dot' + dotClass + '"></span>' + label;
}

async function saveModelConfig() {
  const cfg = getModelConfig();
  try {
    await fetch(API_BASE + '/api/ai/config', {
      method: 'POST', headers: _authHeaders({'Content-Type':'application/json'}),
      body: JSON.stringify(cfg)
    });
    updateModelBadge(cfg);
  } catch(e) { console.error('saveModelConfig error:', e); }
}

async function loadModelConfig() {
  let cfg = null;
  try {
    const r = await fetch(API_BASE + '/api/ai/config', {
      headers: _authHeaders()
    });
    if (r.status === 401) { return; }
    const d = await r.json();
    if (d.ok && d.config) {
      cfg = d.config;
      currentProvider = cfg.provider || 'deepseek';
      const el = (id) => document.getElementById(id);
      // DeepSeek
      if (cfg.deepseek) {
        el('mp-api-key') && (el('mp-api-key').value = cfg.deepseek.api_key || '');
        el('mp-endpoint') && (el('mp-endpoint').value = cfg.deepseek.base_url || 'https://api.deepseek.com');
        el('mp-model-name') && (el('mp-model-name').value = cfg.deepseek.model || 'deepseek-v4-flash');
      }
      // Ollama
      if (cfg.ollama) {
        el('mp-ollama-host') && (el('mp-ollama-host').value = cfg.ollama.base_url || 'http://localhost:11434');
        el('mp-ollama-model') && (el('mp-ollama-model').value = cfg.ollama.model || 'qwen2.5:14b');
      }
      // OpenAI
      if (cfg.openai) {
        el('mp-openai-key') && (el('mp-openai-key').value = cfg.openai.api_key || '');
        el('mp-openai-endpoint') && (el('mp-openai-endpoint').value = cfg.openai.base_url || 'https://api.openai.com/v1');
        el('mp-openai-model') && (el('mp-openai-model').value = cfg.openai.model || 'gpt-4o-mini');
      }
      // Doubao
      if (cfg.doubao) {
        el('mp-doubao-key') && (el('mp-doubao-key').value = cfg.doubao.api_key || '');
        el('mp-doubao-endpoint') && (el('mp-doubao-endpoint').value = cfg.doubao.base_url || 'https://ark.cn-beijing.volces.com/api/v3');
        el('mp-doubao-model') && (el('mp-doubao-model').value = cfg.doubao.model || 'doubao-seed-2.0-pro');
      }
      // Kimi
      if (cfg.kimi) {
        el('mp-kimi-key') && (el('mp-kimi-key').value = cfg.kimi.api_key || '');
        el('mp-kimi-endpoint') && (el('mp-kimi-endpoint').value = cfg.kimi.base_url || 'https://api.moonshot.cn/v1');
        el('mp-kimi-model') && (el('mp-kimi-model').value = cfg.kimi.model || 'moonshot-v1-32k');
      }
      // Temperature & max_tokens
      const temp = cfg.deepseek?.temperature ?? cfg.ollama?.temperature ?? cfg.openai?.temperature ?? cfg.doubao?.temperature ?? cfg.kimi?.temperature ?? 0.7;
      const maxTok = cfg.deepseek?.max_tokens ?? cfg.ollama?.max_tokens ?? cfg.openai?.max_tokens ?? cfg.doubao?.max_tokens ?? cfg.kimi?.max_tokens ?? 4096;
      el('mp-temp') && (el('mp-temp').value = temp);
      el('mp-temp-val') && (el('mp-temp-val').textContent = temp);
      el('mp-maxwords') && (el('mp-maxwords').value = maxTok);
      // Task routing selects
      fillTaskProviderOptions();
      const tp = cfg.task_provider || {};
      ['writing', 'architecture', 'check', 'summary', 'chat'].forEach(t => {
        const s = el('mp-task-' + t);
        if (s && tp[t]) s.value = tp[t];
      });
      // Switch provider tab
      switchModelProvider(currentProvider);
    }
  } catch(e) { console.error('loadModelConfig error:', e); }

  // Update badge using loaded config or fallback
  updateModelBadge(cfg || getModelConfig());
}

async function loadAIUsage(showRefresh) {
  const body = document.getElementById('mp-usage-body');
  if (!body) return;
  if (showRefresh) body.innerHTML = '<span style="opacity:0.5">加载中…</span>';
  try {
    const r = await fetch(API_BASE + '/api/ai/usage', { headers: _authHeaders() });
    const d = await r.json();
    if (d.ok && d.usage) {
      const u = d.usage;
      const fmt = function(n) { return n >= 10000 ? (n/10000).toFixed(1) + '万' : n.toLocaleString(); };
      let html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px">';
      html += '<span>调用: <b>' + u.total_calls + '</b> 次</span>';
      html += '<span>Token: <b>' + fmt(u.total_tokens) + '</b></span>';
      html += '<span>估算费用: <b style="color:var(--accent)">\u00a5' + u.total_cost_cny.toFixed(2) + '</b></span>';
      html += '</div>';
      if (u.by_day && Object.keys(u.by_day).length > 0) {
        const days = Object.entries(u.by_day).sort(function(a,b){ return b[0].localeCompare(a[0]); }).slice(0, 7);
        html += '<div style="opacity:0.7;font-size:11px;margin-bottom:4px">近 ' + days.length + ' 天:</div>';
        html += '<div style="display:flex;gap:4px;flex-direction:column">';
        days.forEach(function(day) {
          var dt = day[1];
          html += '<div style="display:flex;justify-content:space-between;font-size:11px;opacity:0.8">';
          html += '<span>' + day[0] + '</span>';
          html += '<span>' + dt.calls + ' 次 / ' + fmt(dt.tokens) + ' token / \u00a5' + dt.cost.toFixed(2) + '</span>';
          html += '</div>';
        });
        html += '</div>';
      }
      if (u.total_calls > 0) {
        html += '<button class="btn-sm" style="margin-top:4px;font-size:11px;padding:2px 8px;opacity:0.6" onclick="resetAIUsage()">清空记录</button>';
      }
      body.innerHTML = html;
    } else {
      body.innerHTML = '<span style="opacity:0.5">暂无用量数据</span>';
    }
  } catch(e) {
    body.innerHTML = '<span style="opacity:0.5">加载失败</span>';
  }
}

async function resetAIUsage() {
  if (!confirm('确定清空所有用量记录？')) return;
  try {
    await fetch(API_BASE + '/api/ai/usage/reset', { method: 'POST', headers: _authHeaders() });
    loadAIUsage(true);
    showToast('已清空');
  } catch(e) { showToast('清空失败'); }
}

// ========== 结构化大纲 & 卷 API ==========
async function saveNovelOutlineStructured(data) {
  return await api('/api/project/novel-outline', {
    method: 'POST', body: JSON.stringify(data)
  });
}

async function loadNovelOutlineStructured() {
  return await api('/api/project/novel-outline', { method: 'GET' });
}

async function saveVolumes(data) {
  return await api('/api/project/volumes', {
    method: 'POST', body: JSON.stringify(data)
  });
}

async function loadVolumes() {
  return await api('/api/project/volumes', { method: 'GET' });
}

// ========== 向量记忆 API ==========
async function searchMemoryForGeneration(query, chapter, k) {
  return await api('/api/memory/search-for-generation', {
    method: 'POST', body: JSON.stringify({query: query, chapter: chapter||0, k: k||5})
  });
}

async function getMemoryStats() {
  return await api('/api/memory/stats');
}

// ========== AI 辅助写作工具 API ==========
async function aiBrainstorm(topic, context, mode, opts) {
  var body = {topic: topic||'', context: context||'', mode: mode||'plot'};
  if (opts) {
    if (opts.custom_prompt) body.custom_prompt = opts.custom_prompt;
    if (opts.count) body.count = opts.count;
  }
  return await api('/api/ai/brainstorm', {
    method: 'POST', body: JSON.stringify(body)
  });
}

async function aiSensory(scene, senseType, style) {
  return await api('/api/ai/sensory', {
    method: 'POST', body: JSON.stringify({scene: scene||'', sense_type: senseType||'all', style: style||'immersive'})
  });
}

// ========== 嵌入模型管理 API ==========
async function getEmbeddingModels() {
  return await api('/api/memory/embedding-models');
}

async function switchEmbeddingModel(modelName) {
  return await api('/api/memory/switch-embedding-model', {
    method: 'POST', body: JSON.stringify({model_name: modelName})
  });
}

// ========== 世界观知识库 API ==========
async function getKBTemplates() {
  return await api('/api/kb/templates');
}

async function importKBTemplate(templateId, targetProject) {
  return await api('/api/kb/import-template', {
    method: 'POST', body: JSON.stringify({template_id: templateId, target_project: targetProject !== false})
  });
}

async function importKBCustom(name, description, entries, memType) {
  return await api('/api/kb/import-custom', {
    method: 'POST', body: JSON.stringify({name: name, description: description||'', entries: entries, memory_type: memType||'knowledge'})
  });
}

async function listKB() {
  var r = await api('/api/kb/list');
  if (r && r.data) { r.packs = r.data; }
  return r;
}

async function searchKB(query, k) {
  return await api('/api/kb/search?q=' + encodeURIComponent(query) + '&k=' + (k||10));
}

async function exportKBPack(name, memTypes) {
  return await api('/api/kb/export-pack', {
    method: 'POST', body: JSON.stringify({name: name||'书斋设定包', memory_types: memTypes||[]})
  });
}

async function importKBPack(packData) {
  return await api('/api/kb/import-pack', {
    method: 'POST', body: JSON.stringify({pack_data: packData})
  });
}

// ========== 导出功能 API ==========
async function exportBook(format) {
  try {
    var r = await fetch(API_BASE + '/api/export/' + format, {
      headers: _authHeaders()
    });
    if (r.status === 401) { return; }
    if (!r.ok) { console.error('Export failed:', r.status); return; }
    var blob = await r.blob();
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    var ext = format === 'epub' ? 'epub' : (format === 'pdf' ? 'pdf' : 'txt');
    a.download = 'shuzhai-export.' + ext;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) { console.error('Export error:', e); }
}

// ========== 平台模板导出 API ==========
async function exportByPlatform() {
  var select = document.getElementById('export-platform-select');
  var resultEl = document.getElementById('export-platform-result');
  if (!select || !resultEl) return;
  var platform = select.value;
  try {
    resultEl.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:4px">⏳ 正在生成平台模板...</div>';
    var r = await fetch(API_BASE + '/api/export/platform', {
      method: 'POST',
      headers: Object.assign({'Content-Type': 'application/json'}, _authHeaders()),
      body: JSON.stringify({platform: platform})
    });
    if (r.status === 401) { return; }
    // 检查返回是否为 JSON 错误（而非文件下载）
    var contentType = r.headers.get('content-type') || '';
    if (contentType.indexOf('application/json') !== -1) {
      var errData = await r.json();
      resultEl.innerHTML = '<div class="text-sm-danger">❌ ' + ((errData && errData.error) || '导出失败').replace(/</g, '&lt;') + '</div>';
      return;
    }
    if (!r.ok) {
      resultEl.innerHTML = '<div class="text-sm-danger">❌ 导出失败 (HTTP ' + r.status + ')</div>';
      return;
    }
    // 下载文件
    var blob = await r.blob();
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    var platformNames = {fanqie: '番茄小说', qidian: '起点', qimao: '七猫', generic: '通用'};
    var suffix = platformNames[platform] || platform;
    a.download = 'shuzhai-export_' + suffix + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    resultEl.innerHTML = '<div style="font-size:11px;color:var(--success, #10b981);padding:4px">✅ 已导出' + (platformNames[platform] || platform) + '模板</div>';
  } catch(e) {
    resultEl.innerHTML = '<div class="text-sm-danger">❌ 网络错误: ' + (e.message || '').replace(/</g, '&lt;') + '</div>';
  }
}

// ========== 快照 Diff API ==========
async function getSnapshots(index) {
  var r = await api('/api/chapter/snapshots?index=' + index);
  if (r && r.data) { r.snapshots = r.data; }
  return r;
}
async function diffSnapshots(index, snapshotA, snapshotB) {
  return await api('/api/chapter/snapshot/diff', {
    method: 'POST', body: JSON.stringify({index: index, snapshot_a: snapshotA, snapshot_b: snapshotB})
  });
}

// ========== 角色对话模拟 API ==========
async function getChatCharacters() {
  var r = await api('/api/chat/characters');
  if (r && r.data) { r.characters = r.data; }
  return r;
}
async function chatTalk(character, message, history) {
  return await api('/api/chat/talk', {
    method: 'POST', body: JSON.stringify({character: character, message: message, history: history||[]})
  });
}

// ========== 云同步 WebDAV API ==========
async function getSyncConfig() {
  return await api('/api/sync/config');
}
async function saveSyncConfig(config) {
  return await api('/api/sync/config', {
    method: 'POST', body: JSON.stringify(config)
  });
}
async function testSync(config) {
  return await api('/api/sync/test', {
    method: 'POST', body: JSON.stringify(config)
  });
}
async function syncPush(config) {
  return await api('/api/sync/push', {
    method: 'POST', body: JSON.stringify(config)
  });
}
async function syncPull(config) {
  return await api('/api/sync/pull', {
    method: 'POST', body: JSON.stringify(config)
  });
}

// ========== 大纲模板 API ==========
async function getOutlineTemplates() {
  return await api('/api/templates/list');
}
async function applyOutlineTemplate(templateId) {
  return await api('/api/templates/apply', {
    method: 'POST', body: JSON.stringify({template_id: templateId})
  });
}

// ========== 批量检查 API ==========
async function batchValidate(checkTypes, chapterIndices) {
  return await api('/api/validate/batch', {
    method: 'POST', body: JSON.stringify({check_types: checkTypes||[], chapter_indices: chapterIndices||[]})
  });
}

// ========== 写作统计 API ==========
async function getStatsDaily(range) {
  return await api('/api/stats/daily?range=' + (range||30));
}
async function getStatsWeekly() {
  return await api('/api/stats/weekly');
}
async function getStatsMonthly() {
  return await api('/api/stats/monthly');
}
async function getStatsSummary() {
  return await api('/api/stats/summary');
}

// 单用户模式 — 无需认证检查

// === === === 双模式：电脑端走后端，手机端走本地 === === ===
// 检测是否在Capacitor(APK)环境中运行
// 有Python后端时(Chaquopy)禁用本地模式，使用API
var _HAS_PY_BACKEND = (typeof window.Capacitor !== 'undefined') ||
                      (window.location.protocol === 'https:' && window.location.hostname === 'localhost' && !window.location.port);
var _IS_MOBILE = _HAS_PY_BACKEND ? false :
                 (typeof window.Capacitor !== 'undefined') ||
                 (window.location.protocol === 'file:') ||
                 (navigator.userAgent.indexOf('Android') >= 0 && window.location.hostname === 'localhost' && !window.location.port);
if (_HAS_PY_BACKEND) {
  console.log('[双模式] 检测到内嵌Python后端，使用API模式+重试');
  var _apiRetry = api;
  window.api = async function(path, opts) {
    for (var i = 0; i < 60; i++) {
      try { return await _apiRetry(path, opts); }
      catch(e) { if (i < 59) { await new Promise(r => setTimeout(r, 1000)); } else throw e; }
    }
  };
}

// 如果是手机端模式，且本地模块已加载，覆盖api()函数为本地路由
if (_IS_MOBILE && typeof LocalDB !== 'undefined' && typeof AIEngine !== 'undefined') {
  console.log('[双模式] 检测到手机端环境，切换到本地模式');
  
  // 保存原始api函数（用于fallback）
  var _origApi = api;

  // 覆盖api函数：路由到LocalDB/AIEngine
  window.api = async function(path, opts) {
    opts = opts || {};
    var method = (opts.method || 'GET').toUpperCase();
    var body = opts.body ? JSON.parse(opts.body) : {};

    // ── 认证 ──
    if (path === '/api/auth/status') return { auth_required: false, username: 'local' };
    if (path === '/api/auth/login') return { ok: true, token: 'local', username: body.username || 'local' };
    if (path === '/api/auth/register') return { ok: true, token: 'local', username: body.username || 'local' };
    if (path === '/api/auth/logout') return { ok: true };

    // ── 项目管理 ──
    if (path === '/api/project/status') return LocalDB.getStatus();
    if (path === '/api/project/new' && method === 'POST') return LocalDB.newProject(body.title, body.genre, body.length);
    if (path === '/api/project/info') return LocalDB.getProjectInfo();
    if (path === '/api/project/save' && method === 'POST') return { ok: true };
    if (path === '/api/project/list') return { ok: true, projects: LocalDB.listProjects() };
    if (path === '/api/project/settings') {
      if (method === 'GET') return LocalDB.getSettings();
      return LocalDB.updateSettings(body);
    }
    if (path === '/api/project/outline') {
      if (method === 'GET') return LocalDB.getOutline();
      return LocalDB.saveOutline(body.outline || body.text || '');
    }
    if (path === '/api/project/novel-outline') {
      if (method === 'GET') return LocalDB.getNovelOutlineStructured();
      return LocalDB.saveNovelOutlineStructured(body);
    }
    if (path === '/api/project/volumes') {
      if (method === 'GET') return LocalDB.getVolumes();
      return LocalDB.saveVolumes(body);
    }
    if (path === '/api/project/volume/add' && method === 'POST') {
      var meta = LocalDB.getProjectMeta();
      if (!meta) return { ok: false, error: '没有项目' };
      if (!meta.volumes) meta.volumes = [];
      meta.volumes.push({index: meta.volumes.length + 1, title: body.title || '新卷', outline: '', chapters: []});
      LocalDB.saveProjectMeta(meta);
      return { ok: true, volumes: meta.volumes };
    }
    if (path === '/api/project/volume/delete' && method === 'POST') {
      var meta = LocalDB.getProjectMeta();
      if (!meta) return { ok: false, error: '没有项目' };
      var vi = body.vol_index || body.index || 0;
      if (meta.volumes && meta.volumes[vi]) {
        var moveChs = meta.volumes[vi].chapters || [];
        if (vi > 0 && meta.volumes[vi-1]) {
          meta.volumes[vi-1].chapters = (meta.volumes[vi-1].chapters || []).concat(moveChs);
        }
        meta.volumes.splice(vi, 1);
        meta.volumes.forEach(function(v, i) { v.index = i + 1; });
        LocalDB.saveProjectMeta(meta);
      }
      return { ok: true, volumes: meta ? meta.volumes : [] };
    }
    if (path === '/api/project/volume/rename' && method === 'POST') {
      var meta = LocalDB.getProjectMeta();
      if (!meta) return { ok: false, error: '没有项目' };
      var vi = body.vol_index || body.index || 0;
      if (meta.volumes && meta.volumes[vi]) {
        meta.volumes[vi].title = body.title || '未命名';
        LocalDB.saveProjectMeta(meta);
      }
      return { ok: true, volumes: meta ? meta.volumes : [] };
    }
    if (path === '/api/project/auto-volumes' && method === 'POST') {
      var meta = LocalDB.getProjectMeta();
      if (!meta) return { ok: false, error: '没有项目' };
      var ol = LocalDB.getOutline();
      var lines = (ol.outline || '').split('\n');
      var volumes = [];
      var currVol = null;
      lines.forEach(function(line) {
        var m = line.match(/第[一二三四五六七八九十百\d]+[卷幕部]/);
        if (m) {
          currVol = {index: volumes.length + 1, title: line.trim(), outline: '', chapters: []};
          volumes.push(currVol);
        } else if (currVol && line.trim()) {
          currVol.outline += line.trim() + '\n';
        }
      });
      if (volumes.length === 0) volumes = [{index: 1, title: '第一卷', outline: ol.outline || '', chapters: []}];
      meta.volumes = volumes;
      LocalDB.saveProjectMeta(meta);
      return { ok: true, volumes: volumes };
    }
    if (path === '/api/project/hooks' && method === 'GET') return LocalDB.getProjectHooks();
    if (path === '/api/project/hooks/add' && method === 'POST') return LocalDB.addHook(body);
    if (path === '/api/project/hooks/recover') return LocalDB.recoverHook(body.hook_id || body.id);
    if (path === '/api/project/hooks/abandon') return LocalDB.abandonHook(body.hook_id || body.id);

    // ── 章节 ──
    if (path === '/api/chapter/list') return LocalDB.getChapterList();
    if (path === '/api/chapter/add' && method === 'POST') return LocalDB.addChapter(body.title, body.vol_index);
    if (path === '/api/chapter/delete' && method === 'POST') return LocalDB.deleteChapter(body.index);
    if (path.indexOf('/api/chapter/load') === 0) {
      var idx = new URLSearchParams(path.split('?')[1] || '').get('index');
      return LocalDB.loadChapter(parseInt(idx));
    }
    if (path === '/api/chapter/save' && method === 'POST') return LocalDB.saveChapter(body.index, body.content);
    if (path.indexOf('/api/chapter/') >= 0 && path.indexOf('/blueprint') >= 0 && method === 'POST') {
      var bi = parseInt(path.match(/\d+/)[0]);
      return LocalDB.saveChapterBlueprint(bi, body);
    }
    if (path === '/api/chapter/outline' && method === 'POST') return LocalDB.saveChapterOutline(body.index, body.outline, body.blueprint);
    if (path.indexOf('/api/chapter/snapshots') === 0) {
      var si = new URLSearchParams(path.split('?')[1] || '').get('index');
      return LocalDB.getSnapshots(parseInt(si));
    }
    if (path === '/api/chapter/snapshot/restore' && method === 'POST') return LocalDB.restoreSnapshot(body.index, body.snapshot);
    if (path === '/api/chapter/snapshot/diff' && method === 'POST') return LocalDB.diffSnapshots(body.index, body.snapshot_a, body.snapshot_b);

    // ── AI配置 ──
    if (path === '/api/ai/config') {
      if (method === 'GET') return { ok: true, config: LocalDB.getAIConfig() };
      return LocalDB.saveAIConfig(body);
    }
    if (path.indexOf('/api/ai/test') === 0) {
      try {
        var r = await AIEngine.callAI('你好');
        return { ok: r.ok, message: r.ok ? '连接成功' : (r.error || '连接失败') };
      } catch(e) { return { ok: false, error: e.message }; }
    }

    // ── AI功能 ──
    if (path === '/api/ai/chat' && method === 'POST') return await AIEngine.chat(body.messages, { temperature: body.temperature });
    if (path === '/api/ai/brainstorm' && method === 'POST') return await AIEngine.brainstorm(body.topic, body.context, body.mode, body);
    if (path === '/api/ai/expand-idea' && method === 'POST') return await AIEngine.expandIdea(body.title, body.desc, body.mode, body.context);
    if (path === '/api/ai/sensory' && method === 'POST') return await AIEngine.sensory(body.scene, body.sense_type, body.style);
    if (path === '/api/ai/analyze-content' && method === 'POST') return await AIEngine.chat([{role:'user', content:'分析以下文本的世界观设定：\n' + body.content}]);
    if (path === '/api/ai/extract-settings' && method === 'POST') return await AIEngine.chat([{role:'user', content:'从大纲提取结构化世界观：\n' + body.outline}]);
    if (path === '/api/ai/generate-characters' && method === 'POST') return await AIEngine.generateCharacters(body.novel_outline || '');

    // ── 生成 ──
    if (path === '/api/generate/outline' && method === 'POST') return await AIEngine.generateOutline(body.title, body.genre, body.length);
    if (path === '/api/generate/chapter-outline' && method === 'POST') return await AIEngine.generateChapterOutline(body.title, body.context, body.chapter_index || 0);
    if (path === '/api/generate/chapter' && method === 'POST') return await AIEngine.generateChapter(body.title, body.outline, body.context, body.chapter_index || 0);
    if (path === '/api/generate/gate' && method === 'POST') return await AIEngine.generateChapter(body.title, body.outline, body.context, body.chapter_index || 0);
    if (path === '/api/generate/extract-state' && method === 'POST') return await AIEngine.extractState(body.content, body.chapter_idx);
    if (path === '/api/generate/next-chapter-outline' && method === 'POST') return await AIEngine.generateChapterOutline(body.title, body.context, body.chapter_index || 0);

    // ── 校验 ──
    if (path === '/api/validate/ai-flavor') return AuditJS.detectAiFlavor(body.content);
    if (path === '/api/validate/power-collapse') return AuditJS.detectPowerCollapse(body.content, body.chapter_index || 0, body.characters);
    if (path === '/api/validate/extended-audit') return AuditJS.runExtendedAudit(body.content, body.chapter_index || 0, body.characters, body.overdue_hooks);
    if (path === '/api/validate/all') return await AIEngine.validateAll(body.content, body.index, body.memory, body.context);
    if (path === '/api/validate/batch') return { ok: true, results: {} };
    if (path.indexOf('/api/validate/') === 0) return await AIEngine.validateAll(body.content, body.index, body.memory, body.context);

    // ── Ledger ──
    if (path === '/api/ledger/stats') return LocalDB.getLedgerStats();
    if (path === '/api/ledger/characters') return LocalDB.getCharacters();
    if (path === '/api/ledger/character/update' && method === 'POST') return LocalDB.updateCharacter(body.name, body);
    if (path.indexOf('/api/ledger/timeline') === 0) {
      var tch = new URLSearchParams(path.split('?')[1] || '').get('chapter');
      return LocalDB.getTimeline(tch ? parseInt(tch) : null);
    }
    if (path === '/api/ledger/hooks') return LocalDB.getHooks();
    if (path === '/api/ledger/hook/add' && method === 'POST') return LocalDB.addHook(body);
    if (path === '/api/ledger/hook/recover' && method === 'POST') return LocalDB.recoverHook(body.id || body.hook_id);
    if (path === '/api/ledger/hook/abandon' && method === 'POST') return LocalDB.abandonHook(body.id || body.hook_id);

    // ── 世界观 ──
    if (path === '/api/world/' || path === '/api/world') return LocalDB.getWorldMeta();
    if (path === '/api/world/stats') {
      var w = LocalDB.getWorldMeta();
      return { ok: true, stats: { forces: (w.world.forces||[]).length, locations: (w.world.locations||[]).length, items: (w.world.items||[]).length, constraints: (w.world.hard_constraints||[]).length } };
    }

    // ── 工作流 ──
    if (path === '/api/workflow') {
      if (method === 'GET') return LocalDB.getWorkflow();
      return LocalDB.saveWorkflow(body);
    }

    // ── 记忆 ──
    if (path === '/api/memory/stats') return LocalDB.getMemoryStats();
    if (path === '/api/memory/add' && method === 'POST') return LocalDB.addMemory(body);
    if (path === '/api/memory/search' && method === 'POST') return LocalDB.searchMemory(body.query, body.k);
    if (path === '/api/memory/search-for-generation' && method === 'POST') return LocalDB.searchMemoryForGeneration(body.query, body.chapter, body.k);
    if (path === '/api/memory/import-chapter' && method === 'POST') return LocalDB.importChapterMemory(body.index, body.paragraphs);
    if (path.indexOf('/api/memory/') === 0 && method === 'DELETE') return LocalDB.deleteMemory(path.split('/').pop());

    // ── 知识库 ──
    if (path === '/api/kb/templates') return LocalDB.getKBTemplates();
    if (path === '/api/kb/import-template' && method === 'POST') return LocalDB.importKBTemplate(body.template_id);
    if (path === '/api/kb/list') return LocalDB.listKB();
    if (path.indexOf('/api/kb/search') === 0) return LocalDB.searchKB(new URLSearchParams(path.split('?')[1]||'').get('q')||'');

    // ── 完整性/连贯性检查 ──
    if (path === '/api/check/completeness' && method === 'POST') return await AIEngine.checkCompleteness(body.content, body.title);
    if (path === '/api/check/continuity' && method === 'POST') return await AIEngine.checkContinuity(body.chapter_a, body.chapter_b, body.title_a, body.title_b);

    // ── 统计 ──
    if (path.indexOf('/api/stats/daily') === 0) return LocalDB.getStatsDaily(parseInt(new URLSearchParams(path.split('?')[1]||'').get('range')||30));
    if (path === '/api/stats/weekly') return LocalDB.getStatsWeekly();
    if (path === '/api/stats/monthly') return LocalDB.getStatsMonthly();
    if (path === '/api/stats/summary') return LocalDB.getStatsSummary();

    // ── 模板 ──
    if (path === '/api/templates/list') return LocalDB.getOutlineTemplates();
    if (path === '/api/templates/apply' && method === 'POST') return LocalDB.applyOutlineTemplate(body.template_id);

    // ── 角色对话 ──
    if (path === '/api/chat/characters') return LocalDB.getChatCharacters();
    if (path === '/api/chat/talk' && method === 'POST') return await AIEngine.chatTalk(body.character, body.message, body.history);

    // ── 阅读器 ──
    if (path === '/api/reader/bookshelf') return LocalDB.getBookshelf();
    if (path.indexOf('/api/reader/chapter') === 0) {
      var rp = new URLSearchParams(path.split('?')[1] || '');
      return LocalDB.getReaderChapter(rp.get('project'), parseInt(rp.get('chapter')));
    }
    if (path === '/api/reader/progress' && method === 'POST') return LocalDB.saveReaderProgress(body.project, body.chapter, body.scroll);
    if (path === '/api/reader/progress') return LocalDB.getReaderProgress(new URLSearchParams(path.split('?')[1]||'').get('project'));
    if (path === '/api/reader/bookshelf/toggle') return LocalDB.toggleBookshelf(body.project);

    // ── 同步 ──
    if (path === '/api/sync/config') {
      if (method === 'GET') return LocalDB.getSyncConfig();
      return LocalDB.saveSyncConfig(body);
    }
    if (path.indexOf('/api/sync/') === 0) return { ok: false, error: '单机模式不支持WebDAV同步' };

    // ── 导出 ──
    if (path.indexOf('/api/export/txt') === 0) return LocalDB.exportTXT();
    if (path.indexOf('/api/export/') === 0) return { ok: false, error: '单机模式仅支持TXT导出' };

    // ── 不支持的接口 ──
    if (path === '/api/file/parse') return { ok: false, error: '单机模式不支持文件上传解析' };
    if (path.indexOf('/api/deconstruct/') === 0) return { ok: false, error: '单机模式暂不支持拆书' };
    if (path.indexOf('/api/storyboard/') === 0) return { ok: false, error: '单机模式暂不支持分镜' };
    if (path === '/api/agent/chat' && method === 'POST') {
      var ar = await AIEngine.chat(body.messages || [{role:'user', content: body.message || body.query || ''}]);
      return { ok: true, reply: ar, action: null };
    }

    console.warn('[本地模式] 未匹配路径:', path);
    return { ok: false, error: '未知API: ' + path };
  };

  // 覆盖callAI为本地调用
  window.callAI = async function(messages, opts) {
    opts = opts || {};
    var msgsText = messages.map(function(m) { return m.role + ': ' + m.content; }).join('\n');
    var r = await AIEngine.callAI(msgsText, { temperature: opts.temperature });
    if (r.ok) return { ok: true, content: r.content };
    return r;
  };

  // fetch拦截器：处理index.html/app.js中残留的fetch()调用
  var _origFetch = window.fetch;
  window.fetch = async function(input, init) {
    var url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
    if (url && url.indexOf('/api/') >= 0) {
      var path = url.replace(/^https?:\/\/[^\/]+/, '');
      var idx = path.indexOf('/api/');
      if (idx >= 0) path = path.substring(idx);
      var method = (init && init.method) || 'GET';
      var body = null;
      if (init && init.body) {
        try {
          if (typeof init.body === 'string') body = JSON.parse(init.body);
          else if (init.body instanceof FormData) return new Response(JSON.stringify({ok:false,error:'单机模式不支持文件上传'}), {status:200,headers:{'Content-Type':'application/json'}});
          else body = {};
        } catch(e) { body = {}; }
      }
      try {
        var result = await window.api(path, {method: method, body: body ? JSON.stringify(body) : null});
        return new Response(JSON.stringify(result), {status: 200, headers: {'Content-Type': 'application/json'}});
      } catch(e) {
        return new Response(JSON.stringify({ok:false, error: e.message}), {status: 500, headers: {'Content-Type': 'application/json'}});
      }
    }
    return _origFetch.call(window, input, init);
  };

  // 跳过认证检查
  window._checkAuth = async function() { return true; };

  console.log('[双模式] 本地模式已激活');
} else {
  console.log('[双模式] 检测到电脑端环境，使用后端模式');
}
