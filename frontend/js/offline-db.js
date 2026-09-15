// === 书斋 V65 离线存储层 (IndexedDB) ===
// 在APK环境中替代后端文件系统，使用IndexedDB存储所有项目数据

var OfflineDB = (function() {
  var DB_NAME = 'shuzhai_offline';
  var DB_VERSION = 1;
  var db = null;

  function open() {
    return new Promise(function(resolve, reject) {
      var req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onerror = function() { reject(req.error); };
      req.onsuccess = function() { db = req.result; resolve(db); };
      req.onupgradeneeded = function(e) {
        var d = e.target.result;
        // 项目存储：key=项目路径, value=project.json内容
        if (!d.objectStoreNames.contains('projects')) {
          d.createObjectStore('projects', {keyPath: 'path'});
        }
        // 章节正文：key=项目路径+章节索引, value=正文文本
        if (!d.objectStoreNames.contains('chapters')) {
          d.createObjectStore('chapters', {keyPath: 'id'});
        }
        // 配置存储：key=配置名, value=JSON
        if (!d.objectStoreNames.contains('config')) {
          d.createObjectStore('config', {keyPath: 'key'});
        }
        // 事实账本：key=项目路径, value=truth_ledger.json
        if (!d.objectStoreNames.contains('ledger')) {
          d.createObjectStore('ledger', {keyPath: 'path'});
        }
        // 世界观：key=项目路径, value=world_meta.json
        if (!d.objectStoreNames.contains('world')) {
          d.createObjectStore('world', {keyPath: 'path'});
        }
        // 快照：key=项目路径+章节+时间, value=正文
        if (!d.objectStoreNames.contains('snapshots')) {
          d.createObjectStore('snapshots', {keyPath: 'id'});
        }
        // 写作统计：key=项目路径, value=writing_stats.json
        if (!d.objectStoreNames.contains('stats')) {
          d.createObjectStore('stats', {keyPath: 'path'});
        }
      };
    });
  }

  function _tx(store, mode) {
    return db.transaction(store, mode).objectStore(store);
  }

  function _promisify(req) {
    return new Promise(function(resolve, reject) {
      req.onsuccess = function() { resolve(req.result); };
      req.onerror = function() { reject(req.error); };
    });
  }

  // === 项目操作 ===
  function listProjects() {
    return _promisify(_tx('projects', 'readonly').getAll()).then(function(arr) {
      return arr || [];
    });
  }

  function getProject(path) {
    return _promisify(_tx('projects', 'readonly').get(path));
  }

  function saveProject(path, data) {
    data.path = path;
    return _promisify(_tx('projects', 'readwrite').put(data));
  }

  function deleteProject(path) {
    return Promise.all([
      _promisify(_tx('projects', 'readwrite').delete(path)),
      // 删除关联的章节数据
      _clearChapters(path)
    ]);
  }

  // === 章节操作 ===
  function getChapter(path, index) {
    var id = path + '/ch_' + index;
    return _promisify(_tx('chapters', 'readonly').get(id)).then(function(r) {
      return r ? r.content : '';
    });
  }

  function saveChapter(path, index, content) {
    var id = path + '/ch_' + index;
    return _promisify(_tx('chapters', 'readwrite').put({id: id, path: path, index: index, content: content}));
  }

  function _clearChapters(path) {
    return new Promise(function(resolve) {
      var store = _tx('chapters', 'readwrite');
      var idx = store.index('path');
      if (!idx) { resolve(); return; }
      var req = idx.openCursor(IDBKeyRange.only(path));
      req.onsuccess = function(e) {
        var cursor = e.target.result;
        if (cursor) { cursor.delete(); cursor.continue(); }
        else { resolve(); }
      };
      req.onerror = function() { resolve(); };
    });
  }

  // === 事实账本 ===
  function getLedger(path) {
    return _promisify(_tx('ledger', 'readonly').get(path)).then(function(r) {
      return r ? r.data : null;
    });
  }

  function saveLedger(path, data) {
    return _promisify(_tx('ledger', 'readwrite').put({path: path, data: data}));
  }

  // === 世界观 ===
  function getWorld(path) {
    return _promisify(_tx('world', 'readonly').get(path)).then(function(r) {
      return r ? r.data : null;
    });
  }

  function saveWorld(path, data) {
    return _promisify(_tx('world', 'readwrite').put({path: path, data: data}));
  }

  // === 快照 ===
  function saveSnapshot(path, index, content, type) {
    var ts = new Date().toISOString().replace(/[:.]/g, '').substring(0, 15);
    var id = path + '/snap_' + (type || 'chap') + '_' + index + '_' + ts;
    return _promisify(_tx('snapshots', 'readwrite').put({
      id: id, path: path, index: index, content: content, type: type || 'chap', time: ts
    }));
  }

  function listSnapshots(path, index) {
    return new Promise(function(resolve) {
      var store = _tx('snapshots', 'readonly');
      var req = store.getAll();
      req.onsuccess = function() {
        var all = req.result || [];
        resolve(all.filter(function(s) {
          return s.path === path && (index === undefined || s.index === index);
        }));
      };
      req.onerror = function() { resolve([]); };
    });
  }

  // === 写作统计 ===
  function getStats(path) {
    return _promisify(_tx('stats', 'readonly').get(path)).then(function(r) {
      return r ? r.data : {};
    });
  }

  function saveStats(path, data) {
    return _promisify(_tx('stats', 'readwrite').put({path: path, data: data}));
  }

  // === 配置 ===
  function getConfig(key) {
    return _promisify(_tx('config', 'readonly').get(key)).then(function(r) {
      return r ? r.value : null;
    });
  }

  function saveConfig(key, value) {
    return _promisify(_tx('config', 'readwrite').put({key: key, value: value}));
  }

  // === 导出/导入 ===
  function exportProject(path) {
    return Promise.all([
      getProject(path),
      getLedger(path),
      getWorld(path),
      getStats(path)
    ]).then(function(results) {
      var project = results[0];
      if (!project) return null;
      return {
        project: project,
        ledger: results[1],
        world: results[2],
        stats: results[3],
        chapters: {} // 章节正文在下面填充
      };
    }).then(function(exportData) {
      if (!exportData) return null;
      // 获取所有章节正文
      return new Promise(function(resolve) {
        var store = _tx('chapters', 'readonly');
        var req = store.getAll();
        req.onsuccess = function() {
          (req.result || []).forEach(function(ch) {
            if (ch.path === path) {
              exportData.chapters[ch.index] = ch.content;
            }
          });
          resolve(exportData);
        };
        req.onerror = function() { resolve(exportData); };
      });
    });
  }

  function importProject(path, data) {
    var promises = [saveProject(path, data.project)];
    if (data.ledger) promises.push(saveLedger(path, data.ledger));
    if (data.world) promises.push(saveWorld(path, data.world));
    if (data.stats) promises.push(saveStats(path, data.stats));
    if (data.chapters) {
      Object.keys(data.chapters).forEach(function(idx) {
        promises.push(saveChapter(path, parseInt(idx), data.chapters[idx]));
      });
    }
    return Promise.all(promises);
  }

  return {
    open: open,
    listProjects: listProjects,
    getProject: getProject,
    saveProject: saveProject,
    deleteProject: deleteProject,
    getChapter: getChapter,
    saveChapter: saveChapter,
    getLedger: getLedger,
    saveLedger: saveLedger,
    getWorld: getWorld,
    saveWorld: saveWorld,
    saveSnapshot: saveSnapshot,
    listSnapshots: listSnapshots,
    getStats: getStats,
    saveStats: saveStats,
    getConfig: getConfig,
    saveConfig: saveConfig,
    exportProject: exportProject,
    importProject: importProject
  };
})();
