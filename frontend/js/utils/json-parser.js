// ═══════════════════════════════════════════
// JSON 解析工具函数
// 从 JSON/Markdown 代码块中提取字段，用于解析章节蓝图、大纲等
// 统一去重：替代 editor.js 中的 extractField / extField 等重复函数
// ═══════════════════════════════════════════
(function(global) {
  'use strict';

  /**
   * 从 JSON 文本中提取指定字段的所有值
   * 匹配 "field": "value" 格式，支持转义字符
   * @param {string} jsonText - JSON 文本（可以是不完整的或被 markdown 包裹的）
   * @param {string} field - 字段名
   * @returns {string[]} 匹配到的字段值数组
   */
  function extractField(jsonText, field) {
    if (!jsonText || !field) return [];
    // 匹配 "field": "value" 或 "field": "value",
    // 支持转义引号和转义换行
    var pattern = '"' + field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '"\\s*:\\s*"([^"]*(?:\\\\.[^"]*)*)"';
    var matches = [];
    var re = new RegExp(pattern, 'g');
    var m;
    while ((m = re.exec(jsonText)) !== null) {
      // 处理转义字符：\" -> ", \n -> 空格
      var val = m[1].replace(/\\"/g, '"').replace(/\\n/g, ' ');
      matches.push(val);
    }
    return matches;
  }

  /**
   * 判断文本是否为 JSON 格式（可能被 markdown 代码块包裹）
   * @param {string} text
   * @returns {boolean}
   */
  function isJsonFormat(text) {
    if (!text) return false;
    var trimmed = text.trim();
    return trimmed.startsWith('```json') || trimmed.startsWith('{');
  }

  /**
   * 从 JSON 文本中提取章节大纲文本行
   * 提取 scene, atmosphere, trigger, event, conflict, twist, new_state, next_hook 等字段
   * 并格式化为章节大纲列表
   * @param {string} jsonText - JSON 格式的大纲文本
   * @returns {Array<{text: string, current: boolean, source: string}>} 大纲项数组
   */
  function extractOutlineFromJSON(jsonText) {
    if (!jsonText) return [];

    var textLines = [];
    var scenes = extractField(jsonText, 'scene');
    var atmospheres = extractField(jsonText, 'atmosphere');
    var triggers = extractField(jsonText, 'trigger');
    var events = extractField(jsonText, 'event');
    var conflicts = extractField(jsonText, 'conflict');
    var twists = extractField(jsonText, 'twist');
    var newStates = extractField(jsonText, 'new_state');
    var nextHooks = extractField(jsonText, 'next_hook');

    if (scenes.length > 0) textLines.push('【起】' + scenes[0]);
    if (atmospheres.length > 0) textLines.push('氛围：' + atmospheres[0]);
    if (triggers.length > 0) textLines.push('触发：' + triggers[0]);
    events.forEach(function(ev, i) {
      if (ev) textLines.push('【承' + (i+1) + '】' + ev);
    });
    if (conflicts.length > 0) textLines.push('【转】' + conflicts[0]);
    if (twists.length > 0) textLines.push('转折：' + twists[0]);
    if (newStates.length > 0) textLines.push('【合】' + newStates[0]);
    if (nextHooks.length > 0) textLines.push('钩子：' + nextHooks[0]);

    if (textLines.length > 0) {
      return textLines.map(function(l, i) {
        return { text: l.trim(), current: i === 0, source: 'parsed' };
      });
    }

    // 正则也提取不到，按行分割但过滤JSON语法行
    var rawLines = jsonText.split('\n').filter(function(l) {
      var t = l.trim();
      return t && !t.startsWith('"') && !t.startsWith('{') && !t.startsWith('}') &&
             !t.startsWith('[') && !t.startsWith(']') && !t.startsWith('```');
    });
    return rawLines.map(function(l, i) {
      return { text: l.trim(), current: i === 0, source: 'saved' };
    });
  }

  /**
   * 从 JSON 文本中解析结构化蓝图（blueprint）
   * 提取 intro, development, climax, ending 四个部分
   * @param {string} jsonText - JSON 格式的大纲/蓝图文本
   * @returns {Object|null} 蓝图对象，格式：
   *   {
   *     intro: { scene, trigger },
   *     development: [ { scene, event, characters: [] } ],
   *     climax: { conflict, twist },
   *     ending: { new_state, next_hook }
   *   }
   *   提取不到有效字段时返回 null
   */
  function parseBlueprintFromJSON(jsonText) {
    if (!jsonText) return null;

    var bpScenes = extractField(jsonText, 'scene');
    var bpEvents = extractField(jsonText, 'event');
    var bpChars = extractField(jsonText, 'characters');
    var bpConflicts = extractField(jsonText, 'conflict');
    var bpTwists = extractField(jsonText, 'twist');
    var bpTriggers = extractField(jsonText, 'trigger');
    var bpNewStates = extractField(jsonText, 'new_state');
    var bpNextHooks = extractField(jsonText, 'next_hook');

    // 至少要有一些有效字段才认为是蓝图
    if (bpScenes.length === 0 && bpEvents.length === 0 && bpChars.length === 0 &&
        bpConflicts.length === 0 && bpTwists.length === 0) {
      return null;
    }

    var devArr = [];
    var maxLen = Math.max(bpScenes.length, bpEvents.length, bpChars.length);
    for (var di = 0; di < maxLen; di++) {
      devArr.push({
        scene: bpScenes[di] || '',
        event: bpEvents[di] || '',
        characters: bpChars[di] ? [bpChars[di]] : []
      });
    }

    return {
      intro: {
        scene: bpScenes[0] || '',
        trigger: bpTriggers[0] || ''
      },
      development: devArr,
      climax: {
        conflict: bpConflicts[0] || '',
        twist: bpTwists[0] || ''
      },
      ending: {
        new_state: bpNewStates[0] || '',
        next_hook: bpNextHooks[0] || ''
      }
    };
  }

  // 暴露到全局
  global.JsonParser = {
    extractField: extractField,
    isJsonFormat: isJsonFormat,
    extractOutlineFromJSON: extractOutlineFromJSON,
    parseBlueprintFromJSON: parseBlueprintFromJSON
  };

  console.log('[JsonParser] loaded');

})(window);
