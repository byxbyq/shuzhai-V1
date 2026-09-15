/* V64 State - 深层响应式 Proxy + 全局变量双向同步桥 */
(function() {
  const STORAGE_KEY = 'shuzhai_state_cache';
  const listeners = new Set();
  let rootTarget = null;
  
  function isObject(obj) {
    return obj !== null && typeof obj === 'object';
  }
  
  function notifyChange(path, value, oldValue) {
    listeners.forEach(fn => {
      try { fn(path, value, oldValue); } catch ( e) { console.error('State listener error:', e); }
    });
  }
  
  function saveToLocalStorage() {
    if (!rootTarget) return;
    try {
      const data = {
        project: rootTarget.project,
        chapters: rootTarget.chapters,
        currentChapterIndex: rootTarget.currentChapterIndex,
        worldSettings: rootTarget.worldSettings,
        characterSettings: rootTarget.characterSettings,
        aiConfig: rootTarget.aiConfig
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch ( e) {
      console.warn('Failed to save state to localStorage:', e);
    }
  }
  
  let saveTimeout = null;
  function debouncedSave() {
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(saveToLocalStorage, 500);
  }
  
  function createDeepProxy(target, path) {
    if (!isObject(target)) {
      return target;
    }
    
    return new Proxy(target, {
      get(obj, key, receiver) {
        if (key === '__isProxy__') return true;
        const value = Reflect.get(obj, key, receiver);
        if (isObject(value) && !value.__isProxy__) {
          const childPath = path ? `${path}.${key}` : String(key);
          return createDeepProxy(value, childPath);
        }
        return value;
      },
      set(obj, key, value, receiver) {
        const oldValue = obj[key];
        const fullPath = path ? `${path}.${key}` : String(key);
        const result = Reflect.set(obj, key, value, receiver);
        
        if (oldValue !== value) {
          notifyChange(fullPath, value, oldValue);
          debouncedSave();
          
          if (!path) {
            triggerRender(key, value);
            // 同步 state proxy 到全局变量
            syncStateToGlobals(key, value);
          }
        }
        return result;
      },
      deleteProperty(obj, key) {
        const oldValue = obj[key];
        const fullPath = path ? `${path}.${key}` : String(key);
        const result = Reflect.deleteProperty(obj, key);
        notifyChange(fullPath, undefined, oldValue);
        debouncedSave();
        return result;
      }
    });
  }
  
  // ═══ 双向同步桥：state proxy ↔ 全局变量 ═══
  // state → globals：当 state proxy 属性变化时，同步到全局变量
  function syncStateToGlobals(key, value) {
    try {
      if (key === 'chapters') window.chapters = value;
      if (key === 'currentChapterIndex') window.currentChapterIndex = value;
      if (key === 'worldSettings') window.worldSettings = value;
      if (key === 'outline') window.chOutline = value;
    } catch( e) { /* ignore */ }
  }
  
  // globals → state：供各模块调用，将全局变量写入 state proxy
  window.syncGlobalsToState = function() {
    try {
      if (typeof window.chapters !== 'undefined') state.chapters = window.chapters;
      if (typeof window.currentChapterIndex !== 'undefined') state.currentChapterIndex = window.currentChapterIndex;
      if (typeof window.worldSettings !== 'undefined') state.worldSettings = window.worldSettings;
      if (typeof window.chOutline !== 'undefined') state.outline = window.chOutline;
    } catch( e) { /* ignore */ }
  };
  
  function triggerRender(key, value) {
    if (key === 'chapters' && typeof renderChapterList === 'function') {
      setTimeout(renderChapterList, 0);
    }
    if (key === 'outline' && typeof renderOutlineEditor === 'function') {
      setTimeout(renderOutlineEditor, 0);
    }
    if (key === 'currentChapterIndex') {
      if (typeof renderChapterList === 'function') setTimeout(renderChapterList, 0);
      if (typeof loadEditorContent === 'function') setTimeout(loadEditorContent, 0);
    }
  }
  
  const initialState = {
    project: { title: '', wordCount: 0, chapterCount: 0 },
    chapters: [],
    currentChapterIndex: 0,
    chapterContent: '',
    outline: '',
    worldSettings: [],
    characterSettings: {},
    ledgers: { active: [], recovered: [], abandoned: [] },
    aiConfig: {}
  };
  
  rootTarget = initialState;
  
  try {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (cached) {
      const savedState = JSON.parse(cached);
      Object.assign(initialState, savedState);
    }
  } catch ( e) {
    console.warn('Failed to load state from localStorage:', e);
  }
  
  const state = createDeepProxy(initialState, '');
  
  state._target = initialState;
  
  state.subscribe = function(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  };
  
  state.reset = function() {
    Object.keys(initialState).forEach(key => {
      delete initialState[key];
    });
    const defaults = {
      project: { title: '', wordCount: 0, chapterCount: 0 },
      chapters: [],
      currentChapterIndex: 0,
      chapterContent: '',
      outline: '',
      worldSettings: [],
      characterSettings: {},
      ledgers: { active: [], recovered: [], abandoned: [] },
      aiConfig: {}
    };
    Object.assign(initialState, defaults);
    localStorage.removeItem(STORAGE_KEY);
  };
  
  window.state = state;
})();


/* 全局变量声明（供各模块共享） */
var chapters = [];
var currentChapterIndex = 0;
var worldSettings = [];   // 扁平设定数组 [{key, val, group}]，与 settings.js 和 state.proxy 保持一致
var chOutline = [];
var volumes = [];
var currentSettingsChapter = "all";
var lastValResult = null;  // 检查结果对象（统一在此声明，避免各模块重复声明导致类型不一致）

/* Workflow State (全局工作流状态) */
var workflowState = {
  currentStep: 1,
  stepStatus: {}
};
// 初始化9个步骤状态（对应9步工作流：世界观/全书大纲/人物/分卷/章节大纲/写作/时间线/连线框/草稿定稿）
for (var _si = 1; _si <= 9; _si++) {
  workflowState.stepStatus[_si] = { status: 'locked' };
}
