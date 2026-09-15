// === 书斋 V65 本地数据存储层 ===
// 替代后端文件I/O，所有数据存localStorage
// 命名空间: shuzhai_db_*

window.LocalDB = (function() {

  // ── 工具函数 ──
  function _key(name) { return 'shuzhai_db_' + name; }
  function _projKey(name) { return 'shuzhai_db_proj_' + encodeURIComponent(name); }
  function _save(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
      return true;
    } catch(e) {
      console.error('[LocalDB] save error:', key, e);
      return false;
    }
  }
  function _load(key, defaultVal) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : (defaultVal !== undefined ? defaultVal : null);
    } catch(e) {
      console.error('[LocalDB] load error:', key, e);
      return defaultVal !== undefined ? defaultVal : null;
    }
  }
  function _remove(key) { localStorage.removeItem(key); }
  function _now() { return new Date().toISOString(); }
  function _uid() { return Date.now().toString(36) + Math.random().toString(36).substr(2, 5); }

  // ── 当前项目 ──
  var _currentProject = null;  // 内存中的项目对象

  function getCurrentProjectName() {
    return _load('shuzhai_current_project', null);
  }
  function setCurrentProjectName(name) {
    _save('shuzhai_current_project', name);
  }

  // ── 项目列表 ──
  function listProjects() {
    return _load('shuzhai_project_list', []);
  }
  function _addProjectToList(name) {
    var list = listProjects();
    if (list.indexOf(name) < 0) list.push(name);
    _save('shuzhai_project_list', list);
  }
  function _removeProjectFromList(name) {
    var list = listProjects().filter(function(n) { return n !== name; });
    _save('shuzhai_project_list', list);
  }

  // ── 项目元数据 (project.json) ──
  function _defaultProjectMeta(title, genre, length) {
    return {
      meta: {
        title: title || '新项目',
        genre: genre || '小说',
        created: _now(),
        modified: _now(),
        current_chapter: 0
      },
      chapters: [],
      volumes: [],
      novel_outline: [],
      world_settings: {},
      character_settings: {},
      characters: [],
      target_length: length || 100000
    };
  }

  function newProject(title, genre, length) {
    var name = title || '新项目';
    // 如果同名项目已存在，加序号
    var list = listProjects();
    var finalName = name;
    var idx = 2;
    while (list.indexOf(finalName) >= 0) {
      finalName = name + '_' + idx++;
    }
    var meta = _defaultProjectMeta(finalName, genre, length);
    _save(_projKey(finalName), meta);
    _addProjectToList(finalName);

    // 初始化空数据
    _save(_projKey(finalName) + '_ledger', _defaultLedger());
    _save(_projKey(finalName) + '_stats', {});
    _save(_projKey(finalName) + '_outline', '');
    _save(_projKey(finalName) + '_world', _defaultWorldMeta());
    _save(_projKey(finalName) + '_workflow', { currentStep: 1, completedSteps: [], stepStatus: {} });

    setCurrentProjectName(finalName);
    _currentProject = meta;
    return { ok: true, project: meta };
  }

  function openProject(name) {
    var meta = _load(_projKey(name), null);
    if (!meta) return { ok: false, error: '项目不存在: ' + name };
    setCurrentProjectName(name);
    _currentProject = meta;
    return { ok: true, project: meta };
  }

  function getProjectInfo() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有打开的项目' };
    var meta = _load(_projKey(name), null);
    if (!meta) return { ok: false, error: '项目不存在' };
    _currentProject = meta;
    return {
      ok: true,
      title: meta.meta.title,
      genre: meta.meta.genre,
      chapter_count: meta.chapters.length,
      current_chapter: meta.meta.current_chapter || 0,
      dir: name
    };
  }

  function getProjectMeta() {
    var name = getCurrentProjectName();
    if (!name) return null;
    return _load(_projKey(name), null);
  }

  function saveProjectMeta(meta) {
    var name = getCurrentProjectName();
    if (!name) return false;
    meta.meta.modified = _now();
    _save(_projKey(name), meta);
    _currentProject = meta;
    return true;
  }

  function getStatus() {
    var name = getCurrentProjectName();
    if (!name) return { ok: true, running: false, project: '' };
    var meta = _load(_projKey(name), null);
    return { ok: true, running: true, project: meta ? meta.meta.title : '' };
  }

  // ── 章节管理 ──
  function getChapterList() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    return {
      ok: true,
      chapters: meta.chapters.map(function(ch) {
        return { index: ch.index, title: ch.title, word_count: ch.word_count || 0 };
      }),
      current: meta.meta.current_chapter || 0,
      volumes: meta.volumes || []
    };
  }

  function addChapter(title, volIndex) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    var idx = meta.chapters.length;
    meta.chapters.push({
      index: idx,
      title: title || ('第' + (idx + 1) + '章'),
      word_count: 0,
      created: _now(),
      modified: _now(),
      outline: '',
      blueprint: {}
    });
    if (typeof volIndex !== 'undefined' && meta.volumes[volIndex]) {
      meta.volumes[volIndex].chapters.push(idx);
    }
    saveProjectMeta(meta);
    // 初始化空章节内容
    _saveChapterContent(idx, '');
    return { ok: true, index: idx };
  }

  function deleteChapter(index) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (index < 0 || index >= meta.chapters.length) return { ok: false, error: '章节索引无效' };
    meta.chapters.splice(index, 1);
    // 重新编号
    meta.chapters.forEach(function(ch, i) { ch.index = i; });
    // 删除章节内容
    var name = getCurrentProjectName();
    _remove(_projKey(name) + '_ch_' + index);
    // 重新排列章节内容键
    var oldContents = {};
    for (var i = index + 1; i <= meta.chapters.length; i++) {
      var content = _load(_projKey(name) + '_ch_' + i, '');
      oldContents[i - 1] = content;
      _remove(_projKey(name) + '_ch_' + i);
    }
    for (var k in oldContents) {
      _save(_projKey(name) + '_ch_' + k, oldContents[k]);
    }
    saveProjectMeta(meta);
    return { ok: true };
  }

  function _saveChapterContent(index, content) {
    var name = getCurrentProjectName();
    _save(_projKey(name) + '_ch_' + index, content);
  }

  function loadChapter(index) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (index < 0 || index >= meta.chapters.length) return { ok: false, error: '章节索引无效' };
    var name = getCurrentProjectName();
    var content = _load(_projKey(name) + '_ch_' + index, '');
    var ch = meta.chapters[index];
    // 更新当前章节
    meta.meta.current_chapter = index;
    saveProjectMeta(meta);
    return {
      ok: true,
      content: content,
      title: ch.title,
      index: index,
      outline: ch.outline || '',
      blueprint: ch.blueprint || {}
    };
  }

  function saveChapter(index, content) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (index < 0 || index >= meta.chapters.length) return { ok: false, error: '章节索引无效' };
    _saveChapterContent(index, content);
    // 更新元数据
    meta.chapters[index].word_count = content.length;
    meta.chapters[index].modified = _now();
    // 写作统计
    _updateStats(content.length);
    // 创建快照
    _createSnapshot(index, content);
    saveProjectMeta(meta);
    return { ok: true };
  }

  function saveChapterOutline(index, outline, blueprint) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (index < 0 || index >= meta.chapters.length) return { ok: false, error: '章节索引无效' };
    if (outline) meta.chapters[index].outline = outline;
    if (blueprint) meta.chapters[index].blueprint = blueprint;
    saveProjectMeta(meta);
    return { ok: true };
  }

  function saveChapterBlueprint(index, blueprint) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (index < 0 || index >= meta.chapters.length) return { ok: false, error: '章节索引无效' };
    var bp = meta.chapters[index].blueprint || {};
    for (var k in blueprint) bp[k] = blueprint[k];
    meta.chapters[index].blueprint = bp;
    saveProjectMeta(meta);
    return { ok: true };
  }

  // ── 大纲管理 ──
  function getOutline() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    return { ok: true, outline: _load(_projKey(name) + '_outline', '') };
  }

  function saveOutline(text) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    _save(_projKey(name) + '_outline', text);
    return { ok: true };
  }

  function getNovelOutlineStructured() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    return { ok: true, outline: meta.novel_outline || [] };
  }

  function saveNovelOutlineStructured(data) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    if (Array.isArray(data)) {
      meta.novel_outline = data;
    } else if (data && data.outline) {
      meta.novel_outline = data.outline;
    } else if (data && data.acts) {
      meta.novel_outline = data.acts;
    }
    saveProjectMeta(meta);
    return { ok: true };
  }

  // ── 卷管理 ──
  function getVolumes() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    return { ok: true, volumes: meta.volumes || [] };
  }

  function saveVolumes(data) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    meta.volumes = Array.isArray(data) ? data : (data.volumes || []);
    saveProjectMeta(meta);
    return { ok: true };
  }

  // ── 世界观设定 ──
  function _defaultWorldMeta() {
    return {
      magic_system: { name: '', rules: [], realms: [] },
      forces: [],
      locations: [],
      items: [],
      hard_constraints: [],
      freeform: {},
      narrative_style: { pov: '', tense: '', tone: '', pacing: '', description_style: '' },
      era: { tech_level: '', society: '', geography: '', culture: '' },
      world_rules: [],
      world_settings: {}
    };
  }

  function getWorldMeta() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    return { ok: true, world: _load(_projKey(name) + '_world', _defaultWorldMeta()) };
  }

  function saveWorldMeta(world) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    // 如果没有传参，从DOM自动收集世界观设定数据
    if (!world) {
      world = _collectWorldMetaFromDOM();
    }
    _save(_projKey(name) + '_world', world);
    return { ok: true };
  }

  function _collectWorldMetaFromDOM() {
    var world = _load(_projKey(getCurrentProjectName()) + '_world', _defaultWorldMeta());
    // 叙事风格
    var nsPov = document.getElementById('ns-pov');
    var nsTense = document.getElementById('ns-tense');
    var nsTone = document.getElementById('ns-tone');
    var nsPacing = document.getElementById('ns-pacing');
    var nsDesc = document.getElementById('ns-description');
    if (!world.narrative_style) world.narrative_style = {};
    if (nsPov) world.narrative_style.pov = nsPov.value;
    if (nsTense) world.narrative_style.tense = nsTense.value;
    if (nsTone) world.narrative_style.tone = nsTone.value;
    if (nsPacing) world.narrative_style.pacing = nsPacing.value;
    if (nsDesc) world.narrative_style.description = nsDesc.value;
    // 时代环境
    var eraTech = document.getElementById('era-tech');
    var eraSocial = document.getElementById('era-society');
    var eraGeo = document.getElementById('era-geography');
    var eraCulture = document.getElementById('era-culture');
    if (!world.era) world.era = {};
    if (eraTech) world.era.tech = eraTech.value;
    if (eraSocial) world.era.society = eraSocial.value;
    if (eraGeo) world.era.geography = eraGeo.value;
    if (eraCulture) world.era.culture = eraCulture.value;
    var eraSocialAttitude = document.getElementById('era-social-attitude');
    if (eraSocialAttitude) world.era.social_attitude = eraSocialAttitude.value;
    return world;
  }

  function getSettings() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    var name = getCurrentProjectName();
    var world = _load(_projKey(name) + '_world', _defaultWorldMeta());
    return {
      ok: true,
      world_settings: meta.world_settings || {},
      character_settings: meta.character_settings || {},
      characters: meta.characters || [],
      world_meta: world,
      narrative_style: world.narrative_style || {},
      era: world.era || {},
      world_rules: world.world_rules || [],
      world_settings_raw: world.world_settings || {}
    };
  }

  function updateSettings(data) {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    // 合并更新
    if (data.world_settings) meta.world_settings = Object.assign(meta.world_settings || {}, data.world_settings);
    if (data.character_settings) meta.character_settings = Object.assign(meta.character_settings || {}, data.character_settings);
    if (data.characters) meta.characters = data.characters;
    if (data.narrative_style || data.era || data.world_rules || data.world_settings_raw) {
      var name = getCurrentProjectName();
      var world = _load(_projKey(name) + '_world', _defaultWorldMeta());
      if (data.narrative_style) world.narrative_style = data.narrative_style;
      if (data.era) world.era = data.era;
      if (data.world_rules) world.world_rules = data.world_rules;
      if (data.world_settings_raw) world.world_settings = data.world_settings_raw;
      _save(_projKey(name) + '_world', world);
    }
    saveProjectMeta(meta);
    return { ok: true };
  }

  // ── Truth Ledger ──
  function _defaultLedger() {
    return {
      character_states: {},
      foreshadowing: [],
      chapter_logs: [],
      updated: _now()
    };
  }

  function getLedger() {
    var name = getCurrentProjectName();
    if (!name) return _defaultLedger();
    return _load(_projKey(name) + '_ledger', _defaultLedger());
  }

  function saveLedger(ledger) {
    var name = getCurrentProjectName();
    if (!name) return false;
    ledger.updated = _now();
    _save(_projKey(name) + '_ledger', ledger);
    return true;
  }

  function getLedgerStats() {
    var ledger = getLedger();
    return {
      ok: true,
      characters: Object.keys(ledger.character_states).length,
      timeline_events: 0,
      hooks_active: ledger.foreshadowing.filter(function(h) { return h.status === 'planted'; }).length,
      hooks_recovered: ledger.foreshadowing.filter(function(h) { return h.status === 'recovered'; }).length,
      hooks_abandoned: ledger.foreshadowing.filter(function(h) { return h.status === 'abandoned'; }).length
    };
  }

  function getCharacters() {
    var ledger = getLedger();
    return { ok: true, characters: ledger.character_states };
  }

  function updateCharacter(name, fields) {
    var ledger = getLedger();
    if (!ledger.character_states[name]) {
      ledger.character_states[name] = { name: name, location: '', emotion: '', health: '健康', realm: '', relationships: {}, possessions: [], secrets_known: [], last_seen_chapter: 0, is_alive: true, arc_stage: '' };
    }
    for (var k in fields) {
      ledger.character_states[name][k] = fields[k];
    }
    saveLedger(ledger);
    return { ok: true };
  }

  function getTimeline(chapterFilter) {
    return { ok: true, events: [] };
  }

  function getHooks() {
    var ledger = getLedger();
    return {
      ok: true,
      active: ledger.foreshadowing.filter(function(h) { return h.status === 'planted'; }),
      recovered: ledger.foreshadowing.filter(function(h) { return h.status === 'recovered'; }),
      abandoned: ledger.foreshadowing.filter(function(h) { return h.status === 'abandoned'; })
    };
  }

  function getProjectHooks() {
    return getHooks();
  }

  function addHook(data) {
    var ledger = getLedger();
    var hook = {
      id: 'hook_' + Date.now().toString(36),
      content: data.content || '',
      planted_chapter: data.planted_chapter || data.chapter_index || 0,
      expected_recovery_chapter: data.expected_recovery_chapter || data.deadline_chapter || 0,
      status: 'planted',
      related_characters: data.related_characters || [],
      related_items: data.related_items || [],
      note: data.note || ''
    };
    ledger.foreshadowing.push(hook);
    saveLedger(ledger);
    return { ok: true, hook: hook };
  }

  function recoverHook(hookId) {
    var ledger = getLedger();
    for (var i = 0; i < ledger.foreshadowing.length; i++) {
      if (ledger.foreshadowing[i].id === hookId) {
        ledger.foreshadowing[i].status = 'recovered';
        saveLedger(ledger);
        return { ok: true };
      }
    }
    return { ok: false, error: '伏笔不存在' };
  }

  function abandonHook(hookId) {
    var ledger = getLedger();
    for (var i = 0; i < ledger.foreshadowing.length; i++) {
      if (ledger.foreshadowing[i].id === hookId) {
        ledger.foreshadowing[i].status = 'abandoned';
        saveLedger(ledger);
        return { ok: true };
      }
    }
    return { ok: false, error: '伏笔不存在' };
  }

  // ── 写作统计 ──
  function _updateStats(wordsAdded) {
    var name = getCurrentProjectName();
    if (!name) return;
    var stats = _load(_projKey(name) + '_stats', {});
    var today = new Date().toISOString().slice(0, 10);
    if (!stats[today]) {
      stats[today] = { words_added: 0, words_total: 0, chapters_touched: [] };
    }
    stats[today].words_added += wordsAdded;
    if (!stats[today].chapters_touched) stats[today].chapters_touched = [];
    _save(_projKey(name) + '_stats', stats);
  }

  function getStatsDaily(range) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var stats = _load(_projKey(name) + '_stats', {});
    var days = range || 30;
    var result = [];
    var now = new Date();
    for (var i = days - 1; i >= 0; i--) {
      var d = new Date(now);
      d.setDate(d.getDate() - i);
      var key = d.toISOString().slice(0, 10);
      result.push({ date: key, words: (stats[key] && stats[key].words_added) || 0 });
    }
    return { ok: true, data: result };
  }

  function getStatsSummary() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var stats = _load(_projKey(name) + '_stats', {});
    var totalWords = 0, writingDays = 0, bestDay = 0, bestDate = '';
    for (var d in stats) {
      var w = stats[d].words_added || 0;
      totalWords += w;
      if (w > 0) writingDays++;
      if (w > bestDay) { bestDay = w; bestDate = d; }
    }
    var meta = getProjectMeta();
    var chapterCount = meta ? meta.chapters.length : 0;
    return {
      ok: true,
      total_words: totalWords,
      chapter_count: chapterCount,
      avg_per_chapter: chapterCount > 0 ? Math.round(totalWords / chapterCount) : 0,
      writing_days: writingDays,
      best_day: bestDate,
      best_day_words: bestDay
    };
  }

  function getStatsWeekly() {
    return getStatsDaily(7);
  }
  function getStatsMonthly() {
    return getStatsDaily(30);
  }

  // ── 快照管理 ──
  function _createSnapshot(chapterIndex, content) {
    var name = getCurrentProjectName();
    if (!name) return;
    var ts = new Date().toISOString().replace(/[:.]/g, '').slice(0, 14);
    var key = _projKey(name) + '_snap_' + chapterIndex + '_' + ts;
    _save(key, { index: chapterIndex, content: content, timestamp: ts });
  }

  function getSnapshots(chapterIndex) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var prefix = _projKey(name) + '_snap_' + chapterIndex + '_';
    var snapshots = [];
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.indexOf(prefix) === 0) {
        var data = _load(key);
        if (data) {
          snapshots.push({ filename: key.replace(prefix, ''), timestamp: data.timestamp, size: data.content.length });
        }
      }
    }
    snapshots.sort(function(a, b) { return b.timestamp.localeCompare(a.timestamp); });
    return { ok: true, snapshots: snapshots };
  }

  function restoreSnapshot(chapterIndex, snapshotName) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var key = _projKey(name) + '_snap_' + chapterIndex + '_' + snapshotName;
    var data = _load(key);
    if (!data) return { ok: false, error: '快照不存在' };
    _saveChapterContent(chapterIndex, data.content);
    return { ok: true, content: data.content };
  }

  function diffSnapshots(chapterIndex, snapA, snapB) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var keyA = _projKey(name) + '_snap_' + chapterIndex + '_' + snapA;
    var keyB = _projKey(name) + '_snap_' + chapterIndex + '_' + snapB;
    var dataA = _load(keyA);
    var dataB = _load(keyB);
    if (!dataA || !dataB) return { ok: false, error: '快照不存在' };
    // 简单diff：按行比较
    var linesA = dataA.content.split('\n');
    var linesB = dataB.content.split('\n');
    var diff = [];
    var maxLen = Math.max(linesA.length, linesB.length);
    for (var i = 0; i < maxLen; i++) {
      if (linesA[i] !== linesB[i]) {
        diff.push({ line: i + 1, a: linesA[i] || '', b: linesB[i] || '' });
      }
    }
    return { ok: true, diff: diff };
  }

  // ── AI配置 ──

  // 异步初始化：从后端获取配置结构（不含 api_key 明文，密钥按需通过 getApiKey 异步获取）
  var _aiConfigInitDone = false;
  function initAIConfigFromBackend() {
    if (_aiConfigInitDone) return;
    _aiConfigInitDone = true;
    // 异步从后端获取配置（api_key 已脱敏为 has_key 标志）
    try {
      fetch('/api/ai/config').then(function(r) { return r.json(); }).then(function(res) {
        if (res && res.ok && res.config) {
          var backendCfg = res.config;
          var cur = _load('shuzhai_ai_config', null) || window.__INITIAL_AI_CONFIG__ || {};
          // 合并配置结构（provider / base_url / model 等），但不持久化 api_key 明文
          for (var prov in backendCfg) {
            if (prov === 'provider' || prov === 'embedding_model') continue;
            if (backendCfg[prov] && typeof backendCfg[prov] === 'object') {
              var merged = Object.assign(cur[prov] || {}, backendCfg[prov]);
              // 后端返回的 api_key 为空字符串（已脱敏），不覆盖前端已有的 key
              if (!merged.api_key) delete merged.api_key;
              // 保留 has_key 标志供 UI 判断是否已配置
              cur[prov] = merged;
            }
          }
          if (backendCfg.provider) cur.provider = backendCfg.provider;
          _save('shuzhai_ai_config', cur);
        }
      }).catch(function() {});
    } catch (e) {}
  }

  function getAIConfig() {
    var cfg = _load('shuzhai_ai_config', null);
    if (!cfg) {
      // 首次启动：使用全局变量结构（不含密钥），触发后端迁移
      if (typeof window !== 'undefined' && window.__INITIAL_AI_CONFIG__) {
        cfg = window.__INITIAL_AI_CONFIG__;
      } else {
        cfg = {
          provider: 'deepseek',
          deepseek: { api_key: '', base_url: 'https://api.deepseek.com', model: 'deepseek-v4-flash', thinking: 'disabled', temperature: 0.7, max_tokens: 4096 },
          ollama: { base_url: 'http://localhost:11434', model: 'qwen2.5:14b', temperature: 0.7, max_tokens: 4096 },
          openai: { api_key: '', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini', temperature: 0.7, max_tokens: 4096 }
        };
      }
      _save('shuzhai_ai_config', cfg);
    }
    return cfg;
  }

  function saveAIConfig(config) {
    var existing = getAIConfig();
    // 深合并
    for (var k in config) {
      if (k === 'deepseek' || k === 'ollama' || k === 'openai') {
        existing[k] = Object.assign(existing[k] || {}, config[k]);
      } else {
        existing[k] = config[k];
      }
    }
    _save('shuzhai_ai_config', existing);
    return { ok: true, config: existing };
  }

  // ── 工作流状态 ──
  function getWorkflow() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    return { ok: true, state: _load(_projKey(name) + '_workflow', { currentStep: 1, completedSteps: [], stepStatus: {} }) };
  }

  function saveWorkflow(state) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    _save(_projKey(name) + '_workflow', state);
    return { ok: true };
  }

  // ── 阅读器数据 ──
  function getBookshelf() {
    var data = _load('shuzhai_reader', { progress: {}, bookshelf: [] });
    return { ok: true, bookshelf: data.bookshelf || [], progress: data.progress || {} };
  }

  function getReaderChapter(projectName, chapterIndex) {
    var meta = _load(_projKey(projectName), null);
    if (!meta) return { ok: false, error: '项目不存在' };
    if (chapterIndex < 0 || chapterIndex >= meta.chapters.length) return { ok: false, error: '章节不存在' };
    var content = _load(_projKey(projectName) + '_ch_' + chapterIndex, '');
    return { ok: true, content: content, title: meta.chapters[chapterIndex].title, chapters: meta.chapters };
  }

  function saveReaderProgress(projectName, chapter, scroll) {
    var data = _load('shuzhai_reader', { progress: {}, bookshelf: [] });
    if (!data.progress) data.progress = {};
    data.progress[projectName] = { chapter: chapter, scroll: scroll, updated: _now() };
    _save('shuzhai_reader', data);
    return { ok: true };
  }

  function getReaderProgress(projectName) {
    var data = _load('shuzhai_reader', { progress: {}, bookshelf: [] });
    return { ok: true, progress: (data.progress && data.progress[projectName]) || null };
  }

  function toggleBookshelf(projectName) {
    var data = _load('shuzhai_reader', { progress: {}, bookshelf: [] });
    if (!data.bookshelf) data.bookshelf = [];
    var idx = data.bookshelf.indexOf(projectName);
    if (idx >= 0) {
      data.bookshelf.splice(idx, 1);
    } else {
      data.bookshelf.push(projectName);
    }
    _save('shuzhai_reader', data);
    return { ok: true, in_bookshelf: idx < 0 };
  }

  // ── 导出 ──
  function exportTXT() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目' };
    var name = getCurrentProjectName();
    var parts = [meta.meta.title + '\n\n'];
    meta.chapters.forEach(function(ch, i) {
      parts.push('\n' + ch.title + '\n\n');
      parts.push(_load(_projKey(name) + '_ch_' + i, ''));
      parts.push('\n');
    });
    return { ok: true, content: parts.join(''), filename: meta.meta.title + '.txt' };
  }

  // ── 知识库（简化版，用localStorage）──
  function getKBTemplates() {
    return { ok: true, templates: [
      { id: 'xiuxian', name: '修仙境界体系', description: '炼气→筑基→金丹→元婴→化神→合体→大乘→渡劫' },
      { id: 'forces', name: '势力架构', description: '宗门/世家/散修/魔道/正道' },
      { id: 'urban', name: '都市异能', description: '觉醒者/异能等级/组织' },
      { id: 'items', name: '奇幻物品', description: '法宝/丹药/功法/灵石' }
    ]};
  }

  function importKBTemplate(templateId) {
    // 简化版：直接返回模板内容
    var templates = {
      xiuxian: { realms: ['炼气', '筑基', '金丹', '元婴', '化神', '合体', '大乘', '渡劫'] },
      forces: { factions: ['正道宗门', '魔道势力', '隐世世家', '散修联盟'] },
      urban: { levels: ['F', 'E', 'D', 'C', 'B', 'A', 'S', 'SS', 'SSS'] },
      items: { types: ['法宝', '丹药', '功法', '灵石', '材料'] }
    };
    return { ok: true, data: templates[templateId] || {} };
  }

  function listKB() {
    return { ok: true, packs: _load('shuzhai_kb_packs', []) };
  }

  function searchKB(query) {
    var packs = _load('shuzhai_kb_packs', []);
    var results = packs.filter(function(p) {
      return p.name && p.name.indexOf(query) >= 0;
    });
    return { ok: true, results: results };
  }

  // ── 记忆系统（简化版，用文本匹配替代向量搜索）──
  function getMemoryStats() {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var memories = _load(_projKey(name) + '_memories', []);
    return { ok: true, count: memories.length, shared_count: _load('shuzhai_shared_memories', []).length };
  }

  function addMemory(data) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var memories = _load(_projKey(name) + '_memories', []);
    var mem = {
      id: _uid(),
      content: data.content || '',
      memory_type: data.memory_type || 'fact',
      importance: data.importance || 5,
      created_at: _now(),
      last_accessed: _now(),
      access_count: 0,
      metadata: data.metadata || {}
    };
    memories.push(mem);
    _save(_projKey(name) + '_memories', memories);
    return { ok: true, memory: mem };
  }

  function searchMemory(query, k) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目', results: [] };
    var memories = _load(_projKey(name) + '_memories', []);
    // 简单文本匹配替代向量搜索
    var scored = memories.map(function(m) {
      var score = 0;
      var q = query.toLowerCase();
      if (m.content.toLowerCase().indexOf(q) >= 0) score += 10;
      // 关键词匹配
      var keywords = query.split(/\s+/);
      keywords.forEach(function(kw) {
        if (kw && m.content.toLowerCase().indexOf(kw.toLowerCase()) >= 0) score += 3;
      });
      score += (m.importance || 5) * 0.1;
      return { memory: m, score: score };
    });
    scored.sort(function(a, b) { return b.score - a.score; });
    var top = scored.slice(0, k || 5).filter(function(s) { return s.score > 0; });
    return { ok: true, results: top.map(function(s) { return s.memory; }) };
  }

  function searchMemoryForGeneration(query, chapter, k) {
    return searchMemory(query, k);
  }

  function deleteMemory(memoryId) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var memories = _load(_projKey(name) + '_memories', []);
    memories = memories.filter(function(m) { return m.id !== memoryId; });
    _save(_projKey(name) + '_memories', memories);
    return { ok: true };
  }

  function importChapterMemory(index, paragraphs) {
    var name = getCurrentProjectName();
    if (!name) return { ok: false, error: '没有项目' };
    var memories = _load(_projKey(name) + '_memories', []);
    paragraphs.forEach(function(p) {
      if (p && p.length > 10) {
        memories.push({
          id: _uid(),
          content: p,
          memory_type: 'event',
          importance: 5,
          created_at: _now(),
          last_accessed: _now(),
          access_count: 0,
          metadata: { chapter: index }
        });
      }
    });
    _save(_projKey(name) + '_memories', memories);
    return { ok: true, count: paragraphs.length };
  }

  // ── 大纲模板 ──
  function getOutlineTemplates() {
    return { ok: true, templates: [
      { id: 'xiuxian', name: '修仙升级流', description: '炼气→筑基→金丹→元婴→化神→合体→大乘→渡劫，每境界3-5章' },
      { id: 'urban', name: '都市异能流', description: '觉醒→F级→S级→SSS级，都市背景' },
      { id: 'fantasy', name: '奇幻冒险流', description: '勇者召唤→冒险→讨伐魔王' },
      { id: 'rebirth', name: '重生流', description: '重生回过去→利用先知→改命' },
      { id: 'system', name: '系统流', description: '获得系统→任务→升级→变强' },
      { id: ' Regents', name: '权谋争霸流', description: '起于微末→积蓄势力→逐鹿天下' }
    ]};
  }

  function applyOutlineTemplate(templateId) {
    var templates = {
      xiuxian: '第一幕：炼气期\n第二幕：筑基期\n第三幕：金丹期\n第四幕：元婴期\n第五幕：化神期\n第六幕：合体期\n第七幕：大乘期\n第八幕：渡劫飞升',
      urban: '第一幕：觉醒\n第二幕：F级异能\n第三幕：E级→D级\n第四幕：C级→B级\n第五幕：A级→S级\n第六幕：SS级→SSS级\n第七幕：终极一战',
      fantasy: '第一幕：勇者召唤\n第二幕：初入异世界\n第三幕：第一场冒险\n第四幕：同伴集结\n第五幕：讨伐魔将\n第六幕：最终决战\n第七幕：回归',
      rebirth: '第一幕：重生回归\n第二幕：利用先知\n第三幕：第一桶金\n第四幕：布局\n第五幕：复仇\n第六幕：巅峰\n第七幕：新的人生',
      system: '第一幕：系统降临\n第二幕：初始任务\n第三幕：第一次升级\n第四幕：隐藏任务\n第五幕：系统进化\n第六幕：终极任务\n第七幕：超脱系统',
      regents: '第一幕：微末起家\n第二幕：积蓄势力\n第三幕：初露锋芒\n第四幕：纵横捭阖\n第五幕：逐鹿天下\n第六幕：问鼎中原\n第七幕：盛世'
    };
    var outline = templates[templateId] || '';
    if (outline) {
      saveOutline(outline);
      return { ok: true, outline: outline };
    }
    return { ok: false, error: '模板不存在' };
  }

  // ── 角色对话 ──
  function getChatCharacters() {
    var meta = getProjectMeta();
    if (!meta) return { ok: false, error: '没有项目', characters: [] };
    var chars = [];
    // 从characters数组获取
    if (meta.characters) {
      meta.characters.forEach(function(c) {
        if (c.name) chars.push(c.name);
      });
    }
    // 从character_settings获取
    if (meta.character_settings) {
      for (var k in meta.character_settings) {
        if (k.indexOf('char_') === 0 && k.indexOf('_name') > 0) {
          var name = meta.character_settings[k];
          if (name && chars.indexOf(name) < 0) chars.push(name);
        }
      }
    }
    // 从meta.characters获取
    if (meta.meta && meta.meta.characters) {
      meta.meta.characters.forEach(function(c) {
        if (c && chars.indexOf(c) < 0) chars.push(c);
      });
    }
    return { ok: true, characters: chars };
  }

  // ── 同步配置（简化版）──
  function getSyncConfig() {
    return { ok: true, config: _load('shuzhai_sync_config', {}) };
  }
  function saveSyncConfig(config) {
    _save('shuzhai_sync_config', config);
    return { ok: true };
  }

  // ── 清理已删除项目的数据 ──
  function deleteProject(name) {
    var prefix = _projKey(name);
    var keysToRemove = [];
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.indexOf(prefix) === 0) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(function(k) { _remove(k); });
    _removeProjectFromList(name);
    if (getCurrentProjectName() === name) {
      setCurrentProjectName(null);
      _currentProject = null;
    }
    return { ok: true };
  }

  // ── 导出/导入项目数据 ──
  function exportProjectData(name) {
    name = name || getCurrentProjectName();
    if (!name) return null;
    var prefix = _projKey(name);
    var data = {};
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.indexOf(prefix) === 0) {
        data[key] = _load(key);
      }
    }
    data['shuzhai_project_name'] = name;
    return data;
  }

  function importProjectData(data) {
    if (!data || !data['shuzhai_project_name']) return { ok: false, error: '无效的项目数据' };
    var name = data['shuzhai_project_name'];
    // 如果同名项目已存在，加序号
    var list = listProjects();
    var finalName = name;
    var idx = 2;
    while (list.indexOf(finalName) >= 0) {
      finalName = name + '_' + idx++;
    }
    // 导入数据
    for (var key in data) {
      if (key === 'shuzhai_project_name') continue;
      var newKey = key.replace(_projKey(name), _projKey(finalName));
      _save(newKey, data[key]);
    }
    _addProjectToList(finalName);
    return { ok: true, name: finalName };
  }

  return {
    // 项目管理
    listProjects: listProjects,
    newProject: newProject,
    openProject: openProject,
    getProjectInfo: getProjectInfo,
    getProjectMeta: getProjectMeta,
    saveProjectMeta: saveProjectMeta,
    getStatus: getStatus,
    deleteProject: deleteProject,
    getCurrentProjectName: getCurrentProjectName,
    setCurrentProjectName: setCurrentProjectName,
    exportProjectData: exportProjectData,
    importProjectData: importProjectData,
    // 章节
    getChapterList: getChapterList,
    addChapter: addChapter,
    deleteChapter: deleteChapter,
    loadChapter: loadChapter,
    saveChapter: saveChapter,
    saveChapterOutline: saveChapterOutline,
    saveChapterBlueprint: saveChapterBlueprint,
    // 大纲
    getOutline: getOutline,
    saveOutline: saveOutline,
    getNovelOutlineStructured: getNovelOutlineStructured,
    saveNovelOutlineStructured: saveNovelOutlineStructured,
    // 卷
    getVolumes: getVolumes,
    saveVolumes: saveVolumes,
    // 设定
    getSettings: getSettings,
    updateSettings: updateSettings,
    getWorldMeta: getWorldMeta,
    saveWorldMeta: saveWorldMeta,
    // Truth Ledger
    getLedger: getLedger,
    saveLedger: saveLedger,
    getLedgerStats: getLedgerStats,
    getCharacters: getCharacters,
    updateCharacter: updateCharacter,
    getTimeline: getTimeline,
    getHooks: getHooks,
    getProjectHooks: getProjectHooks,
    addHook: addHook,
    recoverHook: recoverHook,
    abandonHook: abandonHook,
    // 统计
    getStatsDaily: getStatsDaily,
    getStatsWeekly: getStatsWeekly,
    getStatsMonthly: getStatsMonthly,
    getStatsSummary: getStatsSummary,
    // 快照
    getSnapshots: getSnapshots,
    restoreSnapshot: restoreSnapshot,
    diffSnapshots: diffSnapshots,
    // AI配置
    getAIConfig: getAIConfig,
    saveAIConfig: saveAIConfig,
    initAIConfigFromBackend: initAIConfigFromBackend,
    // 工作流
    getWorkflow: getWorkflow,
    saveWorkflow: saveWorkflow,
    // 阅读器
    getBookshelf: getBookshelf,
    getReaderChapter: getReaderChapter,
    saveReaderProgress: saveReaderProgress,
    getReaderProgress: getReaderProgress,
    toggleBookshelf: toggleBookshelf,
    // 导出
    exportTXT: exportTXT,
    // 知识库
    getKBTemplates: getKBTemplates,
    importKBTemplate: importKBTemplate,
    listKB: listKB,
    searchKB: searchKB,
    // 记忆
    getMemoryStats: getMemoryStats,
    addMemory: addMemory,
    searchMemory: searchMemory,
    searchMemoryForGeneration: searchMemoryForGeneration,
    deleteMemory: deleteMemory,
    importChapterMemory: importChapterMemory,
    // 模板
    getOutlineTemplates: getOutlineTemplates,
    applyOutlineTemplate: applyOutlineTemplate,
    // 角色对话
    getChatCharacters: getChatCharacters,
    // 同步
    getSyncConfig: getSyncConfig,
    saveSyncConfig: saveSyncConfig
  };
})();
