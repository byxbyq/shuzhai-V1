// === 书斋 V65 技能包系统 ===
// 类似灵蟹创作的插件市场，用户可安装/创建/管理技能包
// 四种类型：rules(规则约束) / skill(技能流程) / prompt(提示词模板) / workflow(工作流)


// === 技能包核心逻辑（从 skills.js 拆分） ===
// 依赖 skill-data.js 提供的 SkillData.BUILTIN_SKILLS
var SkillPack = (function() {
  var STORAGE_KEY = 'shuzhai_skills';
  var ENABLED_KEY = 'shuzhai_skills_enabled';

  // 从 skill-data.js 读取内置技能包数据
  var BUILTIN_SKILLS = (typeof SkillData !== 'undefined' && SkillData.BUILTIN_SKILLS) ? SkillData.BUILTIN_SKILLS : [];

  // === 存储 ===
  function _getAll() {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    try { return JSON.parse(raw); } catch(e) { return []; }
  }

  function _saveAll(skills) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(skills));
  }

  function _getEnabled() {
    var raw = localStorage.getItem(ENABLED_KEY);
    if (!raw) return {};
    try { return JSON.parse(raw); } catch(e) { return {}; }
  }

  function _saveEnabled(map) {
    localStorage.setItem(ENABLED_KEY, JSON.stringify(map));
  }

  // === 后端导入的技能包缓存 ===
  // 从后端 /api/skills/list 加载的导入技能包（保存在项目 skills/ 目录）
  var _importedCache = [];

  // 从后端加载导入的技能包到内存缓存
  async function loadImported() {
    try {
      var r = await api('/api/skills/list');
      if (r && r.ok && Array.isArray(r.skills)) {
        _importedCache = r.skills.map(function(s) {
          s.imported = true;
          s.builtin = false;
          return s;
        });
      } else {
        _importedCache = [];
      }
    } catch(e) {
      console.error('[SkillPack] 加载导入技能包失败:', e);
      _importedCache = [];
    }
    return _importedCache;
  }

  // 上传技能包到后端（支持 File 对象或 JSON 字符串）
  async function importToBackend(fileOrText, filename) {
    var formData = new FormData();
    if (typeof fileOrText === 'string') {
      // 粘贴的 JSON 文本，构造为 File 对象
      var blob = new Blob([fileOrText], {type: 'application/json'});
      formData.append('file', blob, filename || ('skill_' + Date.now() + '.json'));
    } else if (fileOrText instanceof File || fileOrText instanceof Blob) {
      formData.append('file', fileOrText, filename || fileOrText.name || 'skill.json');
    } else {
      throw new Error('参数必须是 File 对象或 JSON 字符串');
    }
    // 注意：FormData 不能手动设置 Content-Type，浏览器会自动添加 boundary
    var headers = {};
    var token = (typeof _getToken === 'function') ? _getToken() : (localStorage.getItem('shuzhai_token') || '');
    if (token) headers['Authorization'] = 'Bearer ' + token;
    var serverBase = (typeof _getServerBase === 'function') ? _getServerBase() : '';
    var resp = await fetch(serverBase + '/api/skills/import', {
      method: 'POST',
      headers: headers,
      body: formData
    });
    var data = await resp.json();
    if (!data.ok) {
      throw new Error(data.error || '导入失败');
    }
    // 导入成功后刷新缓存
    await loadImported();
    return data;
  }

  // 从后端删除导入的技能包
  async function removeImported(id) {
    var serverBase = (typeof _getServerBase === 'function') ? _getServerBase() : '';
    var headers = {};
    var token = (typeof _getToken === 'function') ? _getToken() : (localStorage.getItem('shuzhai_token') || '');
    if (token) headers['Authorization'] = 'Bearer ' + token;
    var resp = await fetch(serverBase + '/api/skills/' + encodeURIComponent(id), {
      method: 'DELETE',
      headers: headers
    });
    var data = await resp.json();
    if (!data.ok) {
      throw new Error(data.error || '删除失败');
    }
    // 删除成功后刷新缓存
    await loadImported();
    // 清除启用状态
    var enabled = _getEnabled();
    delete enabled[id];
    _saveEnabled(enabled);
    return data;
  }

  // === API ===
  function listAll() {
    var custom = _getAll();
    // 合并内置、自定义和后端导入的技能包
    var all = BUILTIN_SKILLS.map(function(s) {
      return Object.assign({}, s);
    });
    custom.forEach(function(s) {
      if (!all.find(function(a) { return a.id === s.id; })) {
        all.push(s);
      }
    });
    // 合并后端导入的技能包
    _importedCache.forEach(function(s) {
      if (!all.find(function(a) { return a.id === s.id; })) {
        all.push(Object.assign({}, s));
      }
    });
    // 标记启用状态
    var enabled = _getEnabled();
    all.forEach(function(s) {
      // 优先使用用户设置；未设置过时用 defaultEnabled（默认true）
      if (enabled[s.id] !== undefined && enabled[s.id] !== null) {
        s.enabled = enabled[s.id];
      } else {
        s.enabled = s.defaultEnabled !== false;
      }
    });
    return all;
  }

  function listByType(type) {
    return listAll().filter(function(s) { return s.type === type; });
  }

  function listByScope(scope) {
    return listAll().filter(function(s) {
      return s.scope === scope || s.scope === 'all';
    });
  }

  function getEnabledByScope(scope) {
    return listAll().filter(function(s) {
      return s.enabled && (s.scope === scope || s.scope === 'all');
    });
  }

  function getSkill(id) {
    return listAll().find(function(s) { return s.id === id; });
  }

  function enable(id) {
    var enabled = _getEnabled();
    enabled[id] = true;
    _saveEnabled(enabled);
  }

  function disable(id) {
    var enabled = _getEnabled();
    enabled[id] = false;
    _saveEnabled(enabled);
  }

  function toggle(id) {
    var skill = getSkill(id);
    if (!skill) return;
    if (skill.enabled) disable(id);
    else enable(id);
  }

  function add(skill) {
    if (!skill.id) skill.id = 'custom_' + Date.now();
    if (!skill.version) skill.version = '1.0.0';
    if (!skill.author) skill.author = '用户';
    if (!skill.type) skill.type = 'rules';
    if (!skill.scope) skill.scope = 'generate';
    skill.builtin = false;
    skill.created = new Date().toISOString();
    var skills = _getAll();
    skills.push(skill);
    _saveAll(skills);
    return skill;
  }

  function update(id, data) {
    var skills = _getAll();
    var idx = skills.findIndex(function(s) { return s.id === id; });
    if (idx >= 0) {
      skills[idx] = Object.assign(skills[idx], data);
      _saveAll(skills);
    }
  }

  function remove(id) {
    var skills = _getAll();
    var idx = skills.findIndex(function(s) { return s.id === id; });
    if (idx >= 0) {
      skills.splice(idx, 1);
      _saveAll(skills);
    }
    // 清除启用状态
    var enabled = _getEnabled();
    delete enabled[id];
    _saveEnabled(enabled);
  }

  // === 导入/导出 ===
  function exportSkill(id) {
    var skill = getSkill(id);
    if (!skill) return null;
    return JSON.stringify(skill, null, 2);
  }

  function importSkill(jsonStr) {
    try {
      var skill = JSON.parse(jsonStr);
      if (!skill.name || !skill.content) throw new Error('格式错误：缺少name或content');
      // 重新生成ID避免冲突
      skill.id = 'imported_' + Date.now();
      skill.builtin = false;
      skill.imported = new Date().toISOString();
      return add(skill);
    } catch(e) {
      throw new Error('导入失败：' + e.message);
    }
  }

  // === 获取生效的规则文本（用于生成时注入） ===
  function getActiveRules(scope) {
    var rules = getEnabledByScope(scope);
    var texts = [];
    rules.forEach(function(r) {
      if (r.type === 'rules' && r.content) {
        texts.push(r.content);
      }
    });
    return texts.length > 0 ? texts.join('\n\n---\n\n') : '';
  }

  // 获取指定scope下所有启用技能包的内容（用于生成时注入）
  function getEnabledSkillsContent(scope) {
    var skills = getEnabledByScope(scope);
    var texts = [];
    skills.forEach(function(s) {
      if (s.content) {
        texts.push(s.content);
      }
    });
    return texts.length > 0 ? texts.join('\n\n---\n\n') : '';
  }

  // === 匹配触发词 ===
  function matchTrigger(text) {
    var skills = listAll().filter(function(s) {
      return s.type === 'skill' && s.enabled && s.trigger;
    });
    for (var i = 0; i < skills.length; i++) {
      var triggers = skills[i].trigger.split('|');
      for (var j = 0; j < triggers.length; j++) {
        if (text.indexOf(triggers[j].trim()) >= 0) {
          return skills[i];
        }
      }
    }
    return null;
  }

  // === 获取技能prompt ===
  function getSkillPrompt(id) {
    var skill = getSkill(id);
    if (!skill) return '';
    return skill.content || '';
  }

  return {
    BUILTIN_SKILLS: BUILTIN_SKILLS,
    listAll: listAll,
    listByType: listByType,
    listByScope: listByScope,
    getEnabledByScope: getEnabledByScope,
    getSkill: getSkill,
    enable: enable,
    disable: disable,
    toggle: toggle,
    add: add,
    update: update,
    remove: remove,
    exportSkill: exportSkill,
    importSkill: importSkill,
    getActiveRules: getActiveRules,
    getEnabledSkillsContent: getEnabledSkillsContent,
    matchTrigger: matchTrigger,
    getSkillPrompt: getSkillPrompt,
    // 后端导入技能包相关
    loadImported: loadImported,
    importToBackend: importToBackend,
    removeImported: removeImported
  };
})();
