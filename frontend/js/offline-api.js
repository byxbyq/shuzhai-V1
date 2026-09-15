// ════════════════════════════════════════════════════════════════
// 书斋 V65 - 离线 APK API 兼容层 (offline-api.js)
// 拦截所有后端 API 请求在本地处理，使用 OfflineDB (IndexedDB) 存储数据，
// 使用 OfflineAI 调用大模型。纯 JavaScript（ES5 兼容）。
// 导出：window.OfflineAPI
// 核心方法：OfflineAPI.handle(path, options) → Promise<响应对象>
// ════════════════════════════════════════════════════════════════
(function (global) {
  'use strict';

  // localStorage 键名（当前项目路径）
  var CURRENT_PROJECT_KEY = 'shuzhai_current_project';

  // ════════════════════════════════════════
  // 工具函数
  // ════════════════════════════════════════

  // 安全访问 localStorage
  function _ls() {
    try {
      if (typeof localStorage !== 'undefined') return localStorage;
      if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
    } catch (e) { /* 隐私模式可能抛异常 */ }
    return null;
  }

  // 获取当前项目路径
  function _getCurrentPath() {
    var ls = _ls();
    if (!ls) return null;
    try { return ls.getItem(CURRENT_PROJECT_KEY) || null; } catch (e) { return null; }
  }

  // 设置当前项目路径
  function _setCurrentPath(path) {
    var ls = _ls();
    if (!ls) return;
    try {
      if (path) ls.setItem(CURRENT_PROJECT_KEY, path);
      else ls.removeItem(CURRENT_PROJECT_KEY);
    } catch (e) { /* ignore */ }
  }

  // 解析 body（可能是字符串或对象）
  function _parseBody(body) {
    if (!body) return {};
    if (typeof body === 'string') {
      try { return JSON.parse(body); } catch (e) { return {}; }
    }
    // 已经是对象，浅拷贝避免修改原始引用
    if (typeof body === 'object') {
      var copy = {};
      for (var k in body) {
        if (body.hasOwnProperty(k)) copy[k] = body[k];
      }
      return copy;
    }
    return {};
  }

  // 从 path 中提取查询参数
  function _getQuery(path, key) {
    var qIndex = path.indexOf('?');
    if (qIndex < 0) return null;
    var query = path.substring(qIndex + 1);
    var pairs = query.split('&');
    for (var i = 0; i < pairs.length; i++) {
      var kv = pairs[i].split('=');
      if (decodeURIComponent(kv[0].replace(/\+/g, ' ')) === key) {
        return decodeURIComponent((kv[1] || '').replace(/\+/g, ' '));
      }
    }
    return null;
  }

  // 去掉查询字符串，只保留路径
  function _pathOnly(path) {
    var qIndex = path.indexOf('?');
    return qIndex >= 0 ? path.substring(0, qIndex) : path;
  }

  // 获取当前时间字符串 "YYYY-MM-DD HH:MM"
  function _now() {
    var d = new Date();
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  // 获取今天的日期字符串 "YYYY-MM-DD"
  function _today() {
    var d = new Date();
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  // Promise 包装：始终 resolve（失败也返回 {ok:false}）
  function _resolve(value) {
    return Promise.resolve(value);
  }

  // 获取当前项目数据
  function _getCurrentProject() {
    var path = _getCurrentPath();
    if (!path) return _resolve(null);
    return OfflineDB.getProject(path);
  }

  // 统计字数
  function _countWords(str) {
    if (!str) return 0;
    return String(str).length;
  }

  // 更新写作统计
  function _updateStats(path, chapterIndex, wordsDiff, wordsTotal) {
    return OfflineDB.getStats(path).then(function (stats) {
      stats = stats || {};
      var today = _today();
      var day = stats[today] || {};
      day.words_added = (day.words_added || 0) + wordsDiff;
      day.words_total = wordsTotal;
      var touched = day.chapters_touched || [];
      if (touched.indexOf(chapterIndex) < 0) touched.push(chapterIndex);
      day.chapters_touched = touched;
      stats[today] = day;
      return OfflineDB.saveStats(path, stats);
    });
  }

  // 构建空项目数据
  function _newProjectData(title, genre) {
    var now = _now();
    return {
      meta: {
        title: title || '未命名',
        genre: genre || '',
        created: now,
        modified: now,
        current_chapter: 0
      },
      chapters: [],
      volumes: [],
      novel_outline: [],
      world_settings: {},
      character_settings: {},
      characters: []
    };
  }

  // 从项目数据中收集所有章节大纲文本
  function _collectChapterOutlines(chapters) {
    chapters = chapters || [];
    var parts = [];
    for (var i = 0; i < chapters.length; i++) {
      var ol = chapters[i].outline || '';
      if (ol && ol.trim()) {
        var title = chapters[i].title || ('第' + (i + 1) + '章');
        parts.push('【' + title + '】\n' + ol);
      }
    }
    return parts.join('\n\n');
  }

  // ════════════════════════════════════════
  // 项目管理端点
  // ════════════════════════════════════════

  // GET /api/project/list - 列出所有项目
  function projectList() {
    return OfflineDB.listProjects().then(function (arr) {
      arr = arr || [];
      var projects = [];
      for (var i = 0; i < arr.length; i++) {
        var p = arr[i];
        var meta = (p && p.meta) || {};
        projects.push({
          path: p.path,
          title: meta.title || '未命名',
          genre: meta.genre || '',
          chapters: (p.chapters || []).length,
          modified: meta.modified || ''
        });
      }
      return { ok: true, projects: projects };
    });
  }

  // POST /api/project/new - 新建项目
  function projectNew(body) {
    var title = body.title || '未命名';
    var genre = body.genre || '';
    var chapterCount = parseInt(body.chapter_count || body.length, 10) || 10;
    var path = title; // 用标题作为路径标识

    var project = _newProjectData(title, genre);
    project.meta.chapter_count = chapterCount;
    project.path = path;

    // 创建章节元数据
    var chapters = [];
    for (var i = 0; i < chapterCount; i++) {
      chapters.push({
        index: i,
        title: '第' + (i + 1) + '章',
        word_count: 0,
        created: _now(),
        modified: _now(),
        outline: '',
        blueprint: null
      });
    }
    project.chapters = chapters;

    return OfflineDB.saveProject(path, project).then(function () {
      _setCurrentPath(path);
      return { ok: true, title: title, path: path };
    });
  }

  // GET /api/project/info - 获取当前项目信息
  function projectInfo() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var meta = project.meta || {};
      return {
        ok: true,
        title: meta.title || '',
        genre: meta.genre || '',
        chapters: (project.chapters || []).length,
        current_chapter: meta.current_chapter || 0,
        project_dir: path
      };
    });
  }

  // POST /api/project/save - 保存当前项目
  function projectSave() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      project.meta.modified = _now();
      return OfflineDB.saveProject(path, project).then(function () {
        return { ok: true };
      });
    });
  }

  // GET /api/project/settings - 获取项目设定
  function projectSettingsGet() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      return OfflineDB.getWorld(path).then(function (world) {
        world = world || {};
        var ws = project.world_settings || {};
        // world_settings 优先从 world_meta 读取，fallback 到 project.json
        if (world.world_settings) ws = world.world_settings;
        return {
          ok: true,
          world_settings: ws,
          character_settings: project.character_settings || {},
          characters: project.characters || [],
          narrative_style: world.narrative_style || {},
          era: world.era || {},
          world_rules: world.world_rules || [],
          world_meta: world,
          structured_settings: {
            magic_system: world.magic_system,
            forces: world.forces,
            locations: world.locations,
            items: world.items,
            constraints: world.hard_constraints,
            freeform: world.freeform,
            narrative_style: world.narrative_style,
            era: world.era,
            world_rules: world.world_rules
          }
        };
      });
    });
  }

  // POST /api/project/settings - 保存项目设定
  function projectSettingsPost(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };

      // 更新 project.json 中的字段
      if (body.world_settings !== undefined) {
        project.world_settings = body.world_settings;
      }
      if (body.character_settings !== undefined) {
        project.character_settings = body.character_settings;
      }
      if (body.characters !== undefined) {
        project.characters = body.characters;
      }
      project.meta.modified = _now();

      // 保存 world_meta
      var worldPromise = OfflineDB.getWorld(path).then(function (world) {
        world = world || {};
        var changed = false;
        if (body.narrative_style) {
          world.narrative_style = world.narrative_style || {};
          for (var k in body.narrative_style) {
            if (body.narrative_style.hasOwnProperty(k)) {
              var v = body.narrative_style[k];
              var normalizedV = (v === null || v === undefined) ? '' : String(v).trim();
              if (world.narrative_style[k] !== normalizedV) {
                world.narrative_style[k] = normalizedV;
                changed = true;
              }
            }
          }
        }
        if (body.era) {
          world.era = world.era || {};
          for (var ke in body.era) {
            if (body.era.hasOwnProperty(ke)) {
              var ve = body.era[ke];
              var normalizedVe = (ve === null || ve === undefined) ? '' : String(ve).trim();
              if (world.era[ke] !== normalizedVe) {
                world.era[ke] = normalizedVe;
                changed = true;
              }
            }
          }
        }
        if (body.world_rules !== undefined && Array.isArray(body.world_rules)) {
          world.world_rules = body.world_rules;
          changed = true;
        }
        if (body.world_settings !== undefined) {
          world.world_settings = body.world_settings;
          changed = true;
        }
        if (body.world_meta) {
          // 完整替换 world_meta
          world = body.world_meta;
          changed = true;
        }
        if (changed) {
          return OfflineDB.saveWorld(path, world);
        }
        return null;
      });

      return Promise.all([
        OfflineDB.saveProject(path, project),
        worldPromise
      ]).then(function () {
        return { ok: true };
      });
    });
  }

  // GET /api/project/status - 返回项目状态
  function projectStatus() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: true, title: null, project: null, version: '6.5' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: true, title: null, project: null, version: '6.5' };
      return {
        ok: true,
        title: (project.meta || {}).title || null,
        project: (project.meta || {}).title || null,
        version: '6.5'
      };
    });
  }

  // GET /api/project/outline - 获取全书大纲文本
  function projectOutlineGet() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var text = project.outline_text || '';
      return { ok: true, outline: text, length: text.length };
    });
  }

  // POST /api/project/outline - 保存全书大纲
  function projectOutlinePost(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      project.outline_text = body.outline || body.text || '';
      project.meta.modified = _now();
      return OfflineDB.saveProject(path, project).then(function () {
        return { ok: true };
      });
    });
  }

  // GET /api/project/novel-outline - 获取结构化全书大纲
  function projectNovelOutlineGet() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      return { ok: true, novel_outline: project.novel_outline || [] };
    });
  }

  // POST /api/project/novel-outline - 保存结构化全书大纲
  function projectNovelOutlinePost(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var outlineData = Array.isArray(body) ? body : (body.novel_outline || []);
      project.novel_outline = outlineData;
      project.meta.modified = _now();
      return OfflineDB.saveProject(path, project).then(function () {
        return { ok: true, novel_outline: outlineData };
      });
    });
  }

  // ════════════════════════════════════════
  // 章节管理端点
  // ════════════════════════════════════════

  // GET /api/chapter/list - 章节列表
  function chapterList() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      return {
        ok: true,
        chapters: project.chapters || [],
        current: (project.meta || {}).current_chapter || 0
      };
    });
  }

  // POST /api/chapter/add - 新增章节
  function chapterAdd(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var chapters = project.chapters || [];
      var idx = chapters.length;
      var now = _now();
      var ch = {
        index: idx,
        title: body.title || ('第' + (idx + 1) + '章'),
        word_count: 0,
        created: now,
        modified: now,
        outline: ''
      };
      chapters.push(ch);
      project.chapters = chapters;
      project.meta.modified = now;
      return OfflineDB.saveProject(path, project).then(function () {
        return { ok: true, index: idx };
      });
    });
  }

  // GET /api/chapter/load?index=N - 加载章节
  function chapterLoad(path) {
    var projectPath = _getCurrentPath();
    if (!projectPath) return _resolve({ ok: false, error: '没有打开的项目' });
    var index = parseInt(_getQuery(path, 'index') || '0', 10);
    return OfflineDB.getProject(projectPath).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var chapters = project.chapters || [];
      if (index < 0 || index >= chapters.length) {
        return { ok: false, error: '章节索引超出范围' };
      }
      var chMeta = chapters[index];
      var title = chMeta.title || '';
      var outline = chMeta.outline || '';
      var blueprint = chMeta.blueprint || null;
      return OfflineDB.getChapter(projectPath, index).then(function (content) {
        content = content || '';
        return {
          ok: true,
          title: title,
          content: content,
          word_count: content.length,
          outline: outline,
          blueprint: blueprint
        };
      });
    });
  }

  // POST /api/chapter/save - 保存章节正文
  function chapterSave(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    var index = parseInt(body.index, 10);
    var content = body.content || '';
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var chapters = project.chapters || [];
      if (index < 0 || index >= chapters.length) {
        return { ok: false, error: '章节索引超出范围' };
      }
      var now = _now();
      var oldWordCount = chapters[index].word_count || 0;
      chapters[index].word_count = content.length;
      chapters[index].modified = now;
      project.meta.modified = now;

      // 统计字数变化
      var wordsDiff = content.length - oldWordCount;
      var wordsTotal = 0;
      for (var i = 0; i < chapters.length; i++) {
        wordsTotal += chapters[i].word_count || 0;
      }

      return Promise.all([
        OfflineDB.saveProject(path, project),
        OfflineDB.saveChapter(path, index, content)
      ]).then(function () {
        if (wordsDiff !== 0) {
          return _updateStats(path, index, wordsDiff, wordsTotal);
        }
        return null;
      }).then(function () {
        return { ok: true };
      });
    });
  }

  // POST /api/chapter/outline - 保存章节大纲
  function chapterOutlineSave(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    var index = parseInt(body.index, 10);
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var chapters = project.chapters || [];
      if (index < 0 || index >= chapters.length) {
        return { ok: false, error: '章节索引超出范围' };
      }
      chapters[index].outline = body.outline || '';
      if (body.blueprint) {
        chapters[index].blueprint = body.blueprint;
      }
      chapters[index].modified = _now();
      project.meta.modified = _now();
      return OfflineDB.saveProject(path, project).then(function () {
        return { ok: true };
      });
    });
  }

  // ════════════════════════════════════════
  // AI 服务端点
  // ════════════════════════════════════════

  // GET /api/ai/config - 读取AI配置
  function aiConfigGet() {
    var config = OfflineAI.getConfig();
    return _resolve({ ok: true, config: config });
  }

  // POST /api/ai/config - 保存AI配置
  function aiConfigPost(body) {
    var result = OfflineAI.saveConfig(body);
    return _resolve(result);
  }

  // POST /api/ai/test - 测试AI连接
  function aiTest() {
    return OfflineAI.testConnection().then(function (result) {
      return result;
    });
  }

  // POST /api/ai/chat - AI对话
  function aiChat(body) {
    var messages = body.messages || [];
    // 将 messages 数组转换为单个 prompt
    var prompt = '';
    for (var i = 0; i < messages.length; i++) {
      var m = messages[i];
      prompt += (m.role || 'user') + ': ' + (m.content || '') + '\n';
    }
    var onChunk = typeof body.on_chunk === 'function' ? body.on_chunk : null;
    var temperature = body.temperature;
    var maxTokens = body.max_tokens;
    return OfflineAI.generate(prompt, onChunk, temperature, maxTokens).then(function (content) {
      if (content && content.indexOf && content.indexOf('[生成失败') === 0) {
        return { ok: false, error: content };
      }
      return { ok: true, content: content };
    });
  }

  // POST /api/ai/generate-characters - AI生成人物档案
  function generateCharacters(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var genre = (project.meta || {}).genre || '小说';
      var overwrite = body.overwrite || false;
      var novelOutline = body.novel_outline || '';

      return OfflineDB.getWorld(path).then(function (world) {
        var worldSettings = world || project.world_settings || {};
        var prompt = OfflineAI.buildCharacterPrompt(worldSettings, genre);
        // 如果有大纲，追加到prompt中
        if (novelOutline) {
          prompt = prompt.replace(
            '基于世界观设定，预生成一套完整的角色库。',
            '仔细阅读大纲，提取大纲中出现的所有角色（包括只提到名字的角色），为每个角色生成完整人物档案。不要遗漏任何角色。'
          );
          prompt += '\n\n【全书大纲】\n' + novelOutline.substring(0, 3000);
        }
        var onChunk = typeof body.on_chunk === 'function' ? body.on_chunk : null;
        return OfflineAI.generate(prompt, onChunk, undefined, 4096);
      }).then(function (raw) {
        if (raw && raw.indexOf && raw.indexOf('[生成失败') === 0) {
          return { ok: false, error: raw };
        }
        // 解析JSON
        var chars = OfflineAI._parseJSONLenient(raw);
        if (!chars || !Array.isArray(chars)) {
          return { ok: false, error: 'AI生成人物档案失败，请检查AI配置' };
        }
        // 过滤掉非dict元素
        chars = chars.filter(function (c) { return c && typeof c === 'object'; });
        if (!chars || chars.length === 0) {
          return { ok: false, error: 'AI生成人物档案失败，请检查AI配置' };
        }

        // 合并模式：默认追加，overwrite=true时覆盖
        var existing = project.characters || [];
        var resultChars;
        if (overwrite) {
          resultChars = chars;
        } else {
          var existingNames = {};
          existing.forEach(function (c) { existingNames[c.name || ''] = true; });
          resultChars = existing.slice();
          chars.forEach(function (c) {
            if (!existingNames[c.name || '']) {
              resultChars.push(c);
            }
          });
        }
        project.characters = resultChars;
        project.meta.modified = _now();
        return OfflineDB.saveProject(path, project).then(function () {
          return { ok: true, characters: resultChars, count: chars.length };
        });
      });
    });
  }

  // ════════════════════════════════════════
  // 内容生成端点
  // ════════════════════════════════════════

  // POST /api/generate/outline - 生成全书大纲
  function generateOutline(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var title = body.title || (project.meta || {}).title || '';
      var genre = body.genre || (project.meta || {}).genre || '';
      var length = parseInt(body.chapter_count || body.length, 10) || 10;

      return OfflineDB.getWorld(path).then(function (world) {
        var worldSettings = world || project.world_settings || {};
        var characters = project.characters || [];
        var prompt = OfflineAI.buildOutlinePrompt(worldSettings, characters, length);
        var onChunk = typeof body.on_chunk === 'function' ? body.on_chunk : null;
        return OfflineAI.generate(prompt, onChunk);
      }).then(function (outline) {
        if (outline && outline.indexOf && outline.indexOf('[生成失败') === 0) {
          return { ok: false, error: outline };
        }
        // 保存大纲到项目
        project.outline_text = outline;
        project.meta.modified = _now();
        return OfflineDB.saveProject(path, project).then(function () {
          return { ok: true, outline: outline };
        });
      });
    });
  }

  // POST /api/generate/chapter-outline - 生成章节大纲
  function generateChapterOutline(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var title = body.title || '';
      var context = body.context || '';
      var chapterIndex = parseInt(body.chapter_index, 10) || 0;
      var novelOutline = project.outline_text || '';
      var volumes = project.volumes || [];
      var novelActs = project.novel_outline || [];

      // 构建当前卷纲要文本
      var volText = '';
      var chNum = chapterIndex + 1;
      var curVol = null;
      for (var i = 0; i < volumes.length; i++) {
        var vc = volumes[i].chapters || [];
        if (vc.indexOf(chNum) >= 0 || (vc.length && vc[0] <= chNum && chNum <= vc[vc.length - 1])) {
          curVol = volumes[i]; break;
        }
      }
      if (!curVol && volumes.length) curVol = volumes[0];
      if (curVol) {
        var vo = curVol.outline || {};
        var vp = ['## 当前卷纲要：' + (curVol.title || '')];
        if (vo.summary) vp.push('卷概要：' + vo.summary);
        if (vo.theme) vp.push('卷主题：' + vo.theme);
        if (vo.key_events && vo.key_events.length) {
          vp.push('卷关键事件：');
          vo.key_events.forEach(function (ke) { vp.push('  · ' + ke); });
        }
        volText = vp.join('\n');
      }

      // 构建当前幕事件文本
      var actText = '';
      var targetAct = null;
      for (var j = 0; j < novelActs.length; j++) {
        var actTitle = (novelActs[j].title || '');
        var m = actTitle.match(/第(\d+)-(\d+)章/);
        if (m) {
          var s = parseInt(m[1]), e = parseInt(m[2]);
          if (s <= chNum && chNum <= e) { targetAct = novelActs[j]; break; }
        }
      }
      if (!targetAct && novelActs.length) targetAct = novelActs[0];
      if (targetAct) {
        var ap = ['## 当前幕：' + (targetAct.title || '')];
        (targetAct.events || []).forEach(function (ev) {
          if (typeof ev === 'object') {
            ap.push('- 第' + (ev.chapter || '?') + '章 ' + (ev.text || ev.content || '') + (ev.chapter === chNum ? ' ← 当前章' : ''));
          } else { ap.push('- ' + ev); }
        });
        actText = ap.join('\n');
      }

      // 获取前一章大纲
      var prevOutline = '';
      var chapters = project.chapters || [];
      if (chapterIndex > 0 && chapters[chapterIndex - 1]) {
        prevOutline = chapters[chapterIndex - 1].outline || '';
      }

      var prompt = OfflineAI.buildChapterOutlinePrompt(chapterIndex, title, novelOutline, prevOutline, volText, actText, context);
      var onChunk = typeof body.on_chunk === 'function' ? body.on_chunk : null;
      return OfflineAI.generate(prompt, onChunk).then(function (raw) {
        if (raw && raw.indexOf && raw.indexOf('[生成失败') === 0) {
          return { ok: false, error: raw };
        }
        // 尝试解析 blueprint
        var blueprint = OfflineAI._parseJSONLenient(raw);
        var outlineText = raw;
        // 如果有 context，附加到大纲文本
        if (context) outlineText = context + '\n\n' + raw;
        return {
          ok: true,
          outline: outlineText,
          blueprint: blueprint,
          raw: raw
        };
      });
    });
  }

  // POST /api/generate/chapter - 生成章节正文（Gate闭环）
  function generateChapter(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var title = body.title || '';
      var outline = body.outline || '';
      var context = body.context || '';
      var chapterIndex = parseInt(body.chapter_index, 10) || 0;

      // 获取世界观和角色
      return OfflineDB.getWorld(path).then(function (world) {
        var worldSettings = world || project.world_settings || {};
        var characters = project.characters || [];

        // 获取伏笔状态
        return OfflineDB.getLedger(path).then(function (ledger) {
          var hooks = (ledger && ledger.foreshadowing) || [];

          // 如果没有 context，尝试获取前一章末尾
          var ctx = context;
          if (!ctx && chapterIndex > 0) {
            return OfflineDB.getChapter(path, chapterIndex - 1).then(function (prevContent) {
              if (prevContent && prevContent.length > 200) {
                ctx = '前一章末尾：\n' + prevContent.substring(prevContent.length - 800);
              }
              return _doGenerateChapter(path, project, title, outline, ctx, chapterIndex, worldSettings, characters, hooks, body);
            });
          }
          return _doGenerateChapter(path, project, title, outline, ctx, chapterIndex, worldSettings, characters, hooks, body);
        });
      });
    });
  }

  // 内部：执行章节生成与保存
  function _doGenerateChapter(path, project, title, outline, context, chapterIndex, worldSettings, characters, hooks, body) {
    var onChunk = typeof body.on_chunk === 'function' ? body.on_chunk : null;
    var options = {
      worldSettings: worldSettings,
      characters: characters,
      hooks: hooks,
      maxRetries: body.max_retries || 2,
      onChunk: onChunk,
      temperature: body.temperature,
      maxTokens: body.max_tokens
    };

    return OfflineAI.generateAndValidate(title, outline, context, chapterIndex, options).then(function (result) {
      var content = result.content || '';
      // 保存章节正文
      if (content) {
        var chapters = project.chapters || [];
        var now = _now();
        var oldWordCount = (chapters[chapterIndex] && chapters[chapterIndex].word_count) || 0;
        if (chapters[chapterIndex]) {
          chapters[chapterIndex].word_count = content.length;
          chapters[chapterIndex].modified = now;
        }
        project.meta.modified = now;

        var wordsDiff = content.length - oldWordCount;
        var wordsTotal = 0;
        for (var i = 0; i < chapters.length; i++) {
          wordsTotal += chapters[i].word_count || 0;
        }

        return Promise.all([
          OfflineDB.saveProject(path, project),
          OfflineDB.saveChapter(path, chapterIndex, content)
        ]).then(function () {
          if (wordsDiff !== 0) {
            return _updateStats(path, chapterIndex, wordsDiff, wordsTotal);
          }
          return null;
        }).then(function () {
          return {
            ok: result.ok,
            content: content,
            word_count: content.length,
            warning: result.warning || '',
            validation_log: result.validation_log || [],
            attempts: result.attempts || 0
          };
        });
      }
      return {
        ok: result.ok,
        content: content,
        word_count: 0,
        warning: result.warning || ''
      };
    });
  }

  // POST /api/generate/extract-state - 提取章节状态
  function generateExtractState(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    var content = body.content || '';
    var chapterIdx = parseInt(body.chapter_idx || body.chapter_index, 10) || 1;
    var title = body.title || '';

    // 构建提取 prompt
    var prompt = '请从以下章节内容中提取角色状态变更、伏笔埋设/回收、关键事件：\n\n' +
      '【第' + chapterIdx + '章 ' + title + '】\n' + content.substring(0, 5000) +
      '\n\n请以JSON格式返回：\n' +
      '{"characters": [{"name":"","changes":""}], "hooks": [{"content":"","action":"planted|recovered","chapter":' + chapterIdx + '}], "events": [""]}';

    return OfflineAI.generate(prompt).then(function (result) {
      if (result && result.indexOf && result.indexOf('[生成失败') === 0) {
        return { ok: false, error: result };
      }
      var extracted = OfflineAI._parseJSONLenient(result);
      return { ok: true, extracted: extracted || {}, raw: result };
    });
  }

  // ════════════════════════════════════════
  // 校验端点
  // ════════════════════════════════════════

  // POST /api/validate/all - 一次AI调用完成6维检查
  function validateAll(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var content = body.content || '';
      var ctx = body.context || {};
      var stage = ctx.stage || 'content';
      var chapterIndex = ctx.chapterIndex !== undefined ? ctx.chapterIndex : (body.index !== undefined ? body.index : 0);
      var novelOutline = ctx.novelOutline || project.outline_text || '';
      var chapterOutline = ctx.chapterOutline || '';

      // 获取章节大纲
      var chapters = project.chapters || [];
      if (chapterIndex >= 0 && chapterIndex < chapters.length && !chapterOutline) {
        chapterOutline = chapters[chapterIndex].outline || '';
      }

      // 根据阶段构建上下文
      var contextBlock;
      if (stage === 'chapter-outline') {
        contextBlock = '【全书大纲】\n' + (novelOutline || '（未提供）') +
          '\n\n【第' + (chapterIndex + 1) + '章大纲】\n' + content;
      } else {
        contextBlock = '【全书大纲】\n' + (novelOutline || '（未提供）') +
          '\n\n【第' + (chapterIndex + 1) + '章大纲】\n' + (chapterOutline || '（未提供）') +
          '\n\n【正文内容（共' + content.length + '字）】\n' + content.substring(0, 5000);
      }

      var prompt = '你是小说审核专家。请对以下内容进行6项检查，一次性返回所有结果。\n\n' +
        contextBlock + '\n\n' +
        '### 检查项（请逐项检查，每项用XML标签输出结果）\n\n' +
        '1. <drift>偏差检查：检查内容是否有偏离、遗漏和矛盾。无问题返回"无偏离"</drift>\n\n' +
        '2. <twist>转折检查：分析转折设计是否合理自然。给出评价</twist>\n\n' +
        '3. <duplicate>重复检查：检查内容是否有重复。无重复返回"无重复"</duplicate>\n\n' +
        '4. <timeline>时间线检查：检查时间线是否一致。无问题返回"无矛盾"</timeline>\n\n' +
        '5. <conflict>冲突检查：检查是否存在设定冲突。无冲突返回"无冲突"</conflict>\n\n' +
        '6. <style>风格检查：评价文笔风格一致性。指出不一致之处</style>\n\n' +
        '重要要求：\n1. 每项检查结果必须包裹在对应的XML标签内\n' +
        '2. 如果某项检查无问题，在标签内返回对应的"无xxx"\n' +
        '3. 不要在标签外输出多余内容\n4. 保持每项检查的独立性和专业性';

      return OfflineAI.generate(prompt).then(function (rawResult) {
        if (rawResult && rawResult.indexOf && rawResult.indexOf('[生成失败') === 0) {
          return { ok: false, error: rawResult };
        }
        // 解析 XML 标签
        var results = {};
        var tags = ['drift', 'twist', 'duplicate', 'timeline', 'conflict', 'style'];
        for (var i = 0; i < tags.length; i++) {
          var tag = tags[i];
          var regex = new RegExp('<' + tag + '>([\\s\\S]*?)</' + tag + '>', 'i');
          var match = rawResult.match(regex);
          results[tag] = match ? match[1].trim() : null;
        }
        var parsedCount = 0;
        for (var k in results) {
          if (results.hasOwnProperty(k) && results[k] !== null) parsedCount++;
        }
        return {
          ok: true,
          results: results,
          parsed_count: parsedCount,
          total: tags.length,
          raw: parsedCount < 4 ? rawResult : null,
          stage: stage
        };
      });
    });
  }

  // POST /api/validate/consistency - 一致性检查
  function validateConsistency(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var content = body.content || '';
      var chapterIndex = body.index !== undefined ? body.index : -1;

      var worldSettings = project.world_settings || {};
      var characters = project.characters || [];
      var novelOutline = project.outline_text || '';
      var chapters = project.chapters || [];

      // 构建世界观文本
      var worldText = '';
      if (typeof worldSettings === 'object') {
        var lines = [];
        for (var wk in worldSettings) {
          if (worldSettings.hasOwnProperty(wk)) {
            lines.push('- ' + wk + '：' + worldSettings[wk]);
          }
        }
        worldText = lines.join('\n');
      }

      // 构建人物档案文本
      var charText = '';
      if (characters && characters.length) {
        var clines = [];
        for (var ci = 0; ci < characters.length; ci++) {
          var c = characters[ci];
          clines.push('- ' + (c.name || '') + '（' + (c.faction || '') + '）：' + (c.identity || ''));
        }
        charText = clines.join('\n');
      }

      // 构建章节大纲文本
      var chapterOutlinesText = _collectChapterOutlines(chapters);

      if (!novelOutline.trim()) {
        return { ok: false, error: '全书大纲为空，无法检查一致性' };
      }

      var hasContent = content && content.trim();
      var stageLabel = hasContent ? '阶段2：全文一致性检查' : '阶段1：设定层一致性检查';

      var prompt = '你是小说设定一致性审核专家。请进行' + stageLabel + '。\n\n' +
        '【世界观设定】\n' + (worldText || '（无）') + '\n\n' +
        '【人物档案】\n' + (charText || '（无）') + '\n\n' +
        '【全书大纲】\n' + novelOutline.substring(0, 3000) + '\n\n' +
        '【已有章节大纲】\n' + (chapterOutlinesText.substring(0, 3000) || '（暂无）');

      if (hasContent) {
        prompt += '\n\n【当前章节正文（第' + (chapterIndex + 1) + '章，共' + content.length + '字）】\n' + content.substring(0, 5000);
      }

      prompt += '\n\n请检查世界观、人物、全书大纲、章节大纲' + (hasContent ? '、正文' : '') + '之间的对齐一致性。\n' +
        '用XML标签输出结果：<consistency>检查结果</consistency>\n' +
        '如无问题返回"一致"，有问题列出具体不一致之处。';

      return OfflineAI.generate(prompt).then(function (rawResult) {
        if (rawResult && rawResult.indexOf && rawResult.indexOf('[生成失败') === 0) {
          return { ok: false, error: rawResult };
        }
        var regex = /<consistency>([\s\S]*?)<\/consistency>/i;
        var match = rawResult.match(regex);
        var result = match ? match[1].trim() : rawResult;
        return {
          ok: true,
          result: result,
          raw: rawResult,
          stage: hasContent ? 2 : 1
        };
      });
    });
  }

  // POST /api/check/completeness - 单章完整性检查
  function checkCompleteness(body) {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '没有打开的项目' });
    var content = body.content || '';
    var title = body.title || '';

    var prompt = '请检查以下章节内容的完整性：\n\n' +
      '【章节标题】' + title + '\n\n' +
      '【正文内容（共' + content.length + '字）】\n' + content.substring(0, 5000) + '\n\n' +
      '请检查：\n1. 情节是否完整（有开头、发展、高潮、结尾）\n' +
      '2. 是否有未交代的悬念\n3. 角色行为是否合理\n' +
      '4. 字数是否达标（建议2000字以上）\n\n' +
      '用XML标签输出：<completeness>检查结果</completeness>';

    return OfflineAI.generate(prompt).then(function (rawResult) {
      if (rawResult && rawResult.indexOf && rawResult.indexOf('[生成失败') === 0) {
        return { ok: false, error: rawResult };
      }
      var regex = /<completeness>([\s\S]*?)<\/completeness>/i;
      var match = rawResult.match(regex);
      var result = match ? match[1].trim() : rawResult;
      return { ok: true, result: result, raw: rawResult };
    });
  }

  // ════════════════════════════════════════
  // 认证端点（离线模式免认证）
  // ════════════════════════════════════════

  function authStatus() {
    return _resolve({ ok: true, need_login: false, auth_required: false, username: 'offline' });
  }

  function authLogin() {
    return _resolve({ ok: true, token: 'offline', username: 'offline' });
  }

  function authRegister() {
    return _resolve({ ok: true, token: 'offline', username: 'offline' });
  }

  // ════════════════════════════════════════
  // 内置网文模板（6种，移植自 backend/routers/templates.py）
  // ════════════════════════════════════════

  var TEMPLATES = [
    {
      id: 'xuanhuan',
      name: '玄幻升级流',
      genre: '玄幻',
      description: '金手指→宗门→秘境→渡劫→飞升，经典修仙升级路线，20章骨架',
      chapters: [
        { title: '废柴觉醒', summary: '主角遭族人欺辱，濒死之际意外觉醒神秘传承金手指，命运转折' },
        { title: '初露锋芒', summary: '利用金手指快速修炼，在家族比武中一鸣惊人，扬眉吐气' },
        { title: '离乡入世', summary: '告别家族，怀揣修仙之志踏上广阔天地，结识同道中人' },
        { title: '拜入宗门', summary: '通过层层考核加入修仙大宗，成为外门弟子，初窥修真门径' },
        { title: '外门风云', summary: '在外门脱颖而出，结交挚友亦树立强敌，暗流涌动' },
        { title: '内门试炼', summary: '闯过内门试炼晋升内门弟子，接触更高深功法与资源' },
        { title: '师承机缘', summary: '得到宗门长老青睐，获传核心功法，实力突飞猛进' },
        { title: '灵脉秘境', summary: '宗门百年秘境开启，主角随队进入寻宝，危机四伏' },
        { title: '秘境奇遇', summary: '秘境深处获得上古传承，实力暴涨，却也引来觊觎' },
        { title: '突破筑基', summary: '借秘境收获一举突破筑基期，奠定修仙根基' },
        { title: '宗门大比', summary: '代表宗门参加修仙界青年大比，与各路天骄争锋' },
        { title: '名震一方', summary: '大比夺魁扬名修仙界，成为新生代领军人物' },
        { title: '仙魔之战', summary: '魔道突袭，主角被卷入仙魔两道旷世纷争' },
        { title: '深入魔渊', summary: '为救同门单闯魔渊，力挽狂澜，尽显英雄本色' },
        { title: '结丹大成', summary: '血战中突破瓶颈，结成金丹，踏入修仙新境界' },
        { title: '渡劫之劫', summary: '修为圆满引发天劫，九死一生渡劫成功' },
        { title: '仇家上门', summary: '旧日仇家联合围攻，主角陷入十死无生之局' },
        { title: '绝地反击', summary: '以一敌众浴血奋战，反杀强敌，威震四方' },
        { title: '巅峰之战', summary: '与幕后黑手展开宿命决战，了结所有恩怨' },
        { title: '飞升仙界', summary: '大道圆满，白日飞升，开启仙界新篇章' }
      ]
    },
    {
      id: 'urban_system',
      name: '都市系统流',
      genre: '都市',
      description: '系统激活→新手任务→商城→排行榜→终极任务，爽文升级节奏，15章',
      chapters: [
        { title: '系统降临', summary: '主角人生跌入谷底，神秘系统突然激活，发布首个任务' },
        { title: '新手任务', summary: '完成新手任务，获得第一桶金与初始技能点' },
        { title: '初尝甜头', summary: '用系统奖励改善生活，惊艳周围众人' },
        { title: '技能获取', summary: '商城解锁，兑换第一个特殊技能，实力质变' },
        { title: '崭露头角', summary: '凭技能在职场/校园强势逆袭，打脸众人' },
        { title: '暗流涌动', summary: '出众表现引来他人觊觎，遭人暗中算计' },
        { title: '反杀逆袭', summary: '利用系统洞察先机化解危机，漂亮反杀' },
        { title: '排行榜现', summary: '系统排行榜开启，主角发现众多隐藏竞争者' },
        { title: '巅峰对决', summary: '与排行榜顶尖高手正面交锋，险胜晋级' },
        { title: '隐藏任务', summary: '触发隐藏剧情，逐步揭开系统背后秘密' },
        { title: '势力扩张', summary: '整合资源建立自己的势力版图，影响力倍增' },
        { title: '商城升级', summary: '解锁高级商城，获得逆天道具与传承' },
        { title: '终极危机', summary: '系统发布终极任务，失败即被抹杀，生死倒计时' },
        { title: '绝境破局', summary: '集结所有资源与人脉应对终极考验，破局而出' },
        { title: '登顶封神', summary: '完成终极任务，登顶排行榜第一，掌控系统' }
      ]
    },
    {
      id: 'rebirth_revenge',
      name: '重生复仇流',
      genre: '重生',
      description: '重生→布局→收服→复仇→新局，步步为营的复仇爽文，18章',
      chapters: [
        { title: '含恨重生', summary: '主角被害家破人亡，重生回到十年前命运转折点' },
        { title: '重整旗鼓', summary: '利用前世记忆重新规划人生，避开前世覆辙' },
        { title: '暗中布局', summary: '提前布局关键产业与人脉，埋下复仇棋子' },
        { title: '初次交锋', summary: '与前世的仇人首次正面过招，小试牛刀' },
        { title: '收服旧将', summary: '收拢前世忠诚却遭排挤的部下，组建班底' },
        { title: '商战初胜', summary: '在商战中精准打击仇人羽翼，初战告捷' },
        { title: '招揽人才', summary: '挖角仇人核心团队，釜底抽薪削弱对手' },
        { title: '设局诱敌', summary: '精心设下陷阱，引诱仇人入彀' },
        { title: '釜底抽薪', summary: '切断仇人资金命脉，令其陷入困局' },
        { title: '离间之计', summary: '施离间计瓦解仇人内部联盟，分而治之' },
        { title: '旧情难断', summary: '与前世恋人重逢，情感纠葛牵动布局' },
        { title: '危机反扑', summary: '仇人察觉反扑，主角陷入前世重演的危机' },
        { title: '绝处逢生', summary: '凭前世记忆预判先机，化险为夷' },
        { title: '全面反击', summary: '多线并进全面反攻，仇人节节败退' },
        { title: '仇人末路', summary: '主要仇人接连落网落败，大势已定' },
        { title: '终极对决', summary: '与幕后主使展开终极对决，了结宿怨' },
        { title: '真相大白', summary: '揭开前世被害的全部真相，沉冤得雪' },
        { title: '新局开启', summary: '复仇完成，主角开启全新人生格局' }
      ]
    },
    {
      id: 'palace_intrigue',
      name: '女频宫斗流',
      genre: '女频宫斗',
      description: '入宫→初斗→结盟→危机→翻盘，深宫权谋步步惊心，16章',
      chapters: [
        { title: '选秀入宫', summary: '主角选秀入宫，初识后宫波谲云诡的险恶' },
        { title: '初承恩宠', summary: '因偶然机缘承宠，却引来众妃嫉妒' },
        { title: '第一次暗算', summary: '遭人设计陷害，险些失宠获罪' },
        { title: '化解危机', summary: '凭机智与细心化解危机，初显心机' },
        { title: '结识盟友', summary: '与其他同样受压的低位妃嫔结成同盟' },
        { title: '培植势力', summary: '暗中收服宫女太监，编织自己的情报网' },
        { title: '对抗贵妃', summary: '与宠冠六宫的贵妃正面交锋，不落下风' },
        { title: '借刀杀人', summary: '巧妙借皇后之手打压对手，藏锋守拙' },
        { title: '步步晋升', summary: '位份渐升，对贵妃地位形成威胁' },
        { title: '盟友反水', summary: '盟友被重利收买，背后捅刀陷害' },
        { title: '跌入低谷', summary: '被构陷禁足冷宫，失去恩宠与自由' },
        { title: '韬光养晦', summary: '在冷宫隐忍筹谋，寻找翻盘契机' },
        { title: '抓住把柄', summary: '掌握对手致命把柄，时机成熟' },
        { title: '一击必杀', summary: '借力打力连环出手，扳倒主要对手' },
        { title: '登顶后位', summary: '击败所有对手，登上母仪天下的后位' },
        { title: '盛世承平', summary: '稳固后位整顿后宫，开启太平盛世' }
      ]
    },
    {
      id: 'infinite_flow',
      name: '无限流',
      genre: '无限流',
      description: '进入→首局→队友→规则→通关，生死副本智斗求生，12章',
      chapters: [
        { title: '诡异邀请', summary: '主角收到神秘邀请，被卷入无限轮回空间' },
        { title: '首局游戏', summary: '被投入第一个恐怖副本，险象环生' },
        { title: '生死一线', summary: '在副本中几度濒死，摸索求生之道' },
        { title: '破局通关', summary: '发现规则漏洞，艰难通关首局副本' },
        { title: '结识队友', summary: '遇到其他轮回者，组队共御强敌' },
        { title: '团队磨合', summary: '在第二个副本中磨合团队，建立信任' },
        { title: '规则解析', summary: '逐渐掌握副本规则体系，化被动为主动' },
        { title: '队友牺牲', summary: '副本中队友为掩护主角慷慨赴死' },
        { title: '单人副本', summary: '独自面对高难度单人副本，挑战极限' },
        { title: '隐藏真相', summary: '发现无限空间背后的惊天真相' },
        { title: '终极副本', summary: '挑战最终副本，直面幕后黑手' },
        { title: '通关自由', summary: '通关所有副本，赢得自由与新生' }
      ]
    },
    {
      id: 'farming',
      name: '种田文流',
      genre: '种田',
      description: '穿越→基建→经商→争霸→盛世，温馨升级到争霸天下，15章',
      chapters: [
        { title: '穿越异世', summary: '主角穿越到古代贫苦农家，一穷二白' },
        { title: '白手起家', summary: '利用现代知识改善生活，初见成效' },
        { title: '第一桶金', summary: '发明小物什赚到第一笔钱，生活转机' },
        { title: '开荒种田', summary: '改良农耕技术，粮食大丰收，温饱无忧' },
        { title: '兴修水利', summary: '带领村民修筑水利，声名鹊起' },
        { title: '经商之道', summary: '开办作坊打通商路，富甲乡里' },
        { title: '遭遇豪强', summary: '地方豪强觊觎产业，强取豪夺' },
        { title: '智斗豪强', summary: '凭智慧与官府背景挫败豪强，保住家业' },
        { title: '扩大版图', summary: '产业不断扩张，成为一方巨贾' },
        { title: '遇乱世', summary: '天下大乱烽烟四起，流民涌入乡里' },
        { title: '组建民团', summary: '为保境安民组建武装民团，自保一方' },
        { title: '逐鹿中原', summary: '被迫卷入诸侯争霸，左右天下大势' },
        { title: '运筹帷幄', summary: '以雄厚经济实力为后盾，运筹帷幄决胜千里' },
        { title: '一统天下', summary: '辅佐明主平定天下，终结乱世' },
        { title: '盛世繁华', summary: '开创太平盛世，造福万民青史留名' }
      ]
    }
  ];

  // ════════════════════════════════════════
  // 其他端点
  // ════════════════════════════════════════

  // GET /api/templates/list - 返回6种内置网文模板
  function templatesList() {
    var items = [];
    for (var i = 0; i < TEMPLATES.length; i++) {
      var tpl = TEMPLATES[i];
      items.push({
        id: tpl.id,
        name: tpl.name,
        genre: tpl.genre,
        description: tpl.description,
        chapter_count: tpl.chapters.length,
        chapters: tpl.chapters
      });
    }
    return _resolve({ ok: true, templates: items, count: items.length });
  }

  // GET /api/stats/daily?range=N - 写作统计
  function statsDaily(path) {
    var projectPath = _getCurrentPath();
    if (!projectPath) return _resolve({ ok: false, error: '未打开项目' });
    var range = parseInt(_getQuery(path, 'range') || '30', 10) || 30;
    return OfflineDB.getStats(projectPath).then(function (stats) {
      stats = stats || {};
      var data = [];
      var today = new Date();
      var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
      for (var i = 0; i < range; i++) {
        var d = new Date(today);
        d.setDate(d.getDate() - (range - 1 - i));
        var ds = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
        var day = stats[ds] || {};
        data.push({
          date: ds,
          words_added: day.words_added || 0,
          words_total: day.words_total || 0
        });
      }
      return { ok: true, data: data };
    });
  }

  // GET /api/stats/summary - 统计汇总
  function statsSummary() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '未打开项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      return OfflineDB.getStats(path).then(function (stats) {
        stats = stats || {};
        var chapters = project.chapters || [];
        var totalWords = 0;
        for (var i = 0; i < chapters.length; i++) {
          totalWords += chapters[i].word_count || 0;
        }
        var totalChapters = chapters.length;
        var avgChapterWords = totalChapters ? Math.round(totalWords / totalChapters) : 0;
        var writingDays = 0;
        for (var k in stats) {
          if (stats.hasOwnProperty(k)) writingDays++;
        }
        var bestDay = { date: '', words: 0 };
        for (var kd in stats) {
          if (stats.hasOwnProperty(kd)) {
            var wa = stats[kd].words_added || 0;
            if (wa > bestDay.words) bestDay = { date: kd, words: wa };
          }
        }
        // 连续写作天数
        var streakDays = 0;
        var today = new Date();
        var padFn = function (n) { return n < 10 ? '0' + n : '' + n; };
        var d = new Date(today);
        var todayStr = d.getFullYear() + '-' + padFn(d.getMonth() + 1) + '-' + padFn(d.getDate());
        if (!stats[todayStr]) {
          d.setDate(d.getDate() - 1);
        }
        while (true) {
          var ds = d.getFullYear() + '-' + padFn(d.getMonth() + 1) + '-' + padFn(d.getDate());
          if (stats[ds]) {
            streakDays++;
            d.setDate(d.getDate() - 1);
          } else {
            break;
          }
        }
        return {
          ok: true,
          total_words: totalWords,
          total_chapters: totalChapters,
          avg_chapter_words: avgChapterWords,
          writing_days: writingDays,
          best_day: bestDay,
          streak_days: streakDays
        };
      });
    });
  }

  // GET /api/export/txt - 导出TXT
  function exportTxt() {
    var path = _getCurrentPath();
    if (!path) return _resolve({ ok: false, error: '未打开项目' });
    return OfflineDB.getProject(path).then(function (project) {
      if (!project) return { ok: false, error: '项目不存在' };
      var chapters = project.chapters || [];
      var promises = [];
      for (var i = 0; i < chapters.length; i++) {
        promises.push(OfflineDB.getChapter(path, i));
      }
      return Promise.all(promises).then(function (contents) {
        var parts = [];
        for (var j = 0; j < chapters.length; j++) {
          var title = chapters[j].title || ('第' + (j + 1) + '章');
          parts.push(title + '\n\n' + (contents[j] || ''));
        }
        var fullText = parts.join('\n\n');
        var blob = new Blob([fullText], { type: 'text/plain;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        return { ok: true, url: url, text: fullText };
      });
    });
  }

  // ════════════════════════════════════════
  // 主路由方法
  // ════════════════════════════════════════

  // handle(path, options) - 处理API请求，返回Promise<响应对象>
  // path: API路径（如'/api/project/list'）
  // options: {method, body, headers}
  function handle(path, options) {
    options = options || {};
    var method = (options.method || 'GET').toUpperCase();
    var body = _parseBody(options.body);
    var pathOnly = _pathOnly(path);

    // 注入流式回调：如果 options.body 是对象且含 on_chunk 函数，传给生成端点
    if (typeof options.body === 'object' && options.body && typeof options.body.on_chunk === 'function') {
      body.on_chunk = options.body.on_chunk;
    }

    try {
      // ── 认证（离线模式免认证）──
      if (pathOnly === '/api/auth/status') return authStatus();
      if (pathOnly === '/api/auth/login') return authLogin();
      if (pathOnly === '/api/auth/register') return authRegister();
      if (pathOnly === '/api/auth/logout') return _resolve({ ok: true });

      // ── 项目管理 ──
      if (pathOnly === '/api/project/list') return projectList();
      if (pathOnly === '/api/project/new' && method === 'POST') return projectNew(body);
      if (pathOnly === '/api/project/info') return projectInfo();
      if (pathOnly === '/api/project/save' && method === 'POST') return projectSave();
      if (pathOnly === '/api/project/settings') {
        if (method === 'GET') return projectSettingsGet();
        return projectSettingsPost(body);
      }
      if (pathOnly === '/api/project/status') return projectStatus();
      if (pathOnly === '/api/project/outline') {
        if (method === 'GET') return projectOutlineGet();
        return projectOutlinePost(body);
      }
      if (pathOnly === '/api/project/novel-outline') {
        if (method === 'GET') return projectNovelOutlineGet();
        return projectNovelOutlinePost(body);
      }

      // ── 章节管理 ──
      if (pathOnly === '/api/chapter/list') return chapterList();
      if (pathOnly === '/api/chapter/add' && method === 'POST') return chapterAdd(body);
      if (path.indexOf('/api/chapter/load') === 0) return chapterLoad(path);
      if (pathOnly === '/api/chapter/save' && method === 'POST') return chapterSave(body);
      if (pathOnly === '/api/chapter/outline' && method === 'POST') return chapterOutlineSave(body);

      // ── AI 服务 ──
      if (pathOnly === '/api/ai/config') {
        if (method === 'GET') return aiConfigGet();
        return aiConfigPost(body);
      }
      if (pathOnly === '/api/ai/test') return aiTest();
      if (pathOnly === '/api/ai/chat' && method === 'POST') return aiChat(body);
      if (pathOnly === '/api/ai/generate-characters' && method === 'POST') return generateCharacters(body);

      // ── 内容生成 ──
      if (pathOnly === '/api/generate/outline' && method === 'POST') return generateOutline(body);
      if (pathOnly === '/api/generate/chapter-outline' && method === 'POST') return generateChapterOutline(body);
      if (pathOnly === '/api/generate/chapter' && method === 'POST') return generateChapter(body);
      if (pathOnly === '/api/generate/extract-state' && method === 'POST') return generateExtractState(body);

      // ── 校验 ──
      if (pathOnly === '/api/validate/all' && method === 'POST') return validateAll(body);
      if (pathOnly === '/api/validate/consistency' && method === 'POST') return validateConsistency(body);
      if (pathOnly === '/api/check/completeness' && method === 'POST') return checkCompleteness(body);

      // ── 其他 ──
      if (pathOnly === '/api/templates/list') return templatesList();
      if (path.indexOf('/api/stats/daily') === 0) return statsDaily(path);
      if (pathOnly === '/api/stats/summary') return statsSummary();
      if (path.indexOf('/api/export/txt') === 0) return exportTxt();

      // ── 不支持的端点 ──
      console.warn('[OfflineAPI] 未匹配路径:', path);
      return _resolve({ ok: false, error: '离线模式不支持此功能' });
    } catch (e) {
      console.error('[OfflineAPI] 处理异常:', path, e);
      return _resolve({ ok: false, error: '处理异常: ' + (e.message || String(e)) });
    }
  }

  // ════════════════════════════════════════
  // 导出
  // ════════════════════════════════════════
  global.OfflineAPI = {
    handle: handle
  };

})(typeof window !== 'undefined' ? window : this);
