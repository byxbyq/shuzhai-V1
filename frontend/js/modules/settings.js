// ── 解析纯文本大纲为 novelActs 数组 ──
function parseOutline(text) {
  if (!text || !text.trim()) {
    novelActs = [];
    return;
  }
  var lines = text.split('\n');
  var acts = [];
  var currentAct = null;
  lines.forEach(function(line) {
    var trimmed = line.trim();
    if (!trimmed) return;
    // 识别幕标题（如 "第一幕：xxx" 或 "## 第一幕"）
    var actMatch = trimmed.match(/^(?:##\s*)?第[一二三四五六七八九十百\d]+[幕卷部篇](?:[：:\s])/i);
    if (actMatch) {
      if (currentAct) acts.push(currentAct);
      currentAct = {
        title: trimmed.replace(/^##\s*/, ''),
        range: '',
        events: []
      };
    } else if (currentAct) {
      currentAct.events.push({ text: trimmed, ch: '', checked: false });
    } else {
      // 没有幕标题，创建一个默认幕
      if (!acts.length) {
        currentAct = { title: '第一幕', range: '', events: [] };
      }
      if (currentAct) {
        currentAct.events.push({ text: trimmed, ch: '', checked: false });
      }
    }
  });
  if (currentAct) acts.push(currentAct);
  novelActs = acts.length > 0 ? acts : [];
}

// Extracted from app.js - 项目设置/大纲加载保存
// ── Load project settings from backend ──
async function loadProjectSettings() {
  try {
    var r = await api('/api/project/settings');
    if (r.ok) {
      // Convert backend settings to worldSettings format
      var newSettings = [];
      if (r.world_settings) {
        Object.entries(r.world_settings).forEach(function([key, val]) {
          if (val && typeof val === 'string') {
            newSettings.push({key: key, val: val, group: '世界观'});
          }
        });
      }
      if (r.character_settings) {
        Object.entries(r.character_settings).forEach(function([key, val]) {
          if (val && typeof val === 'string') {
            newSettings.push({key: key, val: val, group: '角色'});
          } else if (val && typeof val === 'object' && val.description) {
            newSettings.push({key: key, val: val.description, group: '角色'});
          }
        });
      }
      if (r.structured_settings) {
        var ss = r.structured_settings;
        if (ss.magic_system && ss.magic_system.name) {
          newSettings.push({key: '修炼体系', val: ss.magic_system.name, group: '世界观'});
        }
        if (ss.forces && ss.forces.length) {
          var forceNames = ss.forces.map(function(f) { return f && f.name ? f.name : f; }).filter(Boolean);
          if (forceNames.length) newSettings.push({key: '主要势力', val: forceNames.join('、'), group: '世界观'});
        }
        if (ss.locations && ss.locations.length) {
          var locNames = ss.locations.map(function(l) { return l && l.name ? l.name : l; }).filter(Boolean);
          if (locNames.length) newSettings.push({key: '关键地点', val: locNames.join('、'), group: '世界观'});
        }
        if (ss.items && ss.items.length) {
          var itemNames = ss.items.map(function(i) { return i && i.name ? i.name : i; }).filter(Boolean);
          if (itemNames.length) newSettings.push({key: '重要道具', val: itemNames.join('、'), group: '道具'});
        }
        if (ss.constraints && ss.constraints.length) {
          newSettings.push({key: '硬性约束', val: ss.constraints.join('、'), group: '世界观'});
        }
      }
      // 后端有数据就使用，不再要求最低数量
      if (newSettings.length > 0) {
        worldSettings = newSettings;
      } else {
        // 后端没有数据，保持空状态（新项目）
        worldSettings = [];
      }
      // 加载人物档案
      if (r.characters && Array.isArray(r.characters)) {
        window.characters = r.characters;
        // 也把人物档案加到worldSettings里，让设定编辑器能显示
        r.characters.forEach(function(c) {
          if (c && c.name) {
            var charDesc = c.identity || '';
            if (c.personality) charDesc += '；' + c.personality;
            if (c.background) charDesc += '；' + c.background;
            newSettings.push({key: c.name, val: charDesc, group: '角色'});
          }
        });
        // 重新赋值worldSettings（包含人物）
        if (newSettings.length > 0) {
          worldSettings = newSettings;
        }
      } else {
        window.characters = [];
      }
      // 加载结构化世界观字段
      if (typeof loadWorldMeta === 'function') {
        loadWorldMeta({
          narrative_style: r.narrative_style,
          era: r.era,
          world_rules: r.world_rules
        });
      }
    }
  } catch(e) { console.error('loadProjectSettings error:', e); }
}

// 保存默认设定到后端
async function saveDefaultSettings() {
  try {
    var worldData = {};
    var charData = {};
    worldSettings.forEach(function(s) {
      if (s.group === '世界观' || s.group === '事件' || s.group === '道具') {
        worldData[s.key] = s.val;
      } else if (s.group === '角色') {
        charData[s.key] = s.val;
      }
    });
    await api('/api/project/settings', {
      method: 'POST',
      body: JSON.stringify({world_settings: worldData, character_settings: charData})
    });
  } catch(e) { console.error('saveDefaultSettings error:', e); }
}

// ── Load project outline from backend ──
async function loadProjectOutline() {
  try {
    // 先尝试从结构化大纲API加载（project.json）
    var r = await api('/api/project/novel-outline');
    if (r.ok && r.novel_outline && r.novel_outline.length > 0) {
      // 检测数据格式：结构化格式 {title, chapters, events} vs markdown格式 {content}
      var isStructured = r.novel_outline.some(function(act) {
        return Array.isArray(act.events);
      });

      if (isStructured) {
        // 直接转换为 novelActs 格式
        novelActs = r.novel_outline.map(function(act) {
          return {
            title: act.title || '',
            range: act.chapters || '',
            events: (act.events || []).map(function(ev) {
              return {
                text: ev.text || ev.title || '',
                ch: String(ev.chapter || ''),
                checked: false
              };
            })
          };
        });
        console.log('Loaded structured outline:', novelActs.length, 'acts');
        return;
      }

      // 回退：兼容旧版 markdown 格式 {content}
      var allText = r.novel_outline.map(function(act) {
        return act.content || act.title || '';
      }).join('\n');

      var sections = allText.split(/\n(?=##\s)/);
      var outlineSections = [];

      sections.forEach(function(section) {
        var trimmed = section.trim();
        if (!trimmed) return;
        var titleMatch = trimmed.match(/^##\s+(.+)/);
        var title = titleMatch ? titleMatch[1].trim() : '';
        if (!title || /核心世界观|世界观设定|主要角色|角色设定|人物设定/.test(title)) {
          return;
        }
        var lines = trimmed.split('\n').slice(1).map(function(l) {
          return l.replace(/^#{1,3}\s*/, '').replace(/^[-•]\s*/, '').trim();
        }).filter(function(l) { return l; });
        if (lines.length === 0) return;
        if (/各章节大纲|章节大纲/.test(title)) {
          var chapterText = lines.join('\n');
          var chapterSections = chapterText.split(/\n(?=###\s)/);
          chapterSections.forEach(function(chSec) {
            var chMatch = chSec.match(/^###\s+(.+)/);
            var chTitle = chMatch ? chMatch[1].trim() : '';
            if (!chTitle) return;
            var chLines = chSec.split('\n').slice(1).map(function(l) {
              return l.replace(/^[-•]\s*/, '').trim();
            }).filter(function(l) { return l; });
            if (chLines.length > 0) {
              outlineSections.push({
                title: chTitle,
                range: '',
                events: chLines.map(function(line) { return { text: line, ch: '', checked: false }; })
              });
            }
          });
        } else {
          outlineSections.push({
            title: title,
            range: '',
            events: lines.map(function(line) { return { text: line, ch: '', checked: false }; })
          });
        }
      });

      novelActs = outlineSections;
      console.log('Loaded outline (markdown format):', novelActs.length, 'acts');
      return;
    }
    // 回退到纯文本大纲（outline.txt）
    r = await api('/api/project/outline');
    if (r.ok && r.outline) {
      parseOutline(r.outline);
    }
  } catch(e) {
    console.error('loadProjectOutline error:', e.message, e.stack);
    novelActs = JSON.parse(JSON.stringify(DEFAULT_NOVEL_ACTS));
  }
}

// 保存默认大纲到后端
async function saveDefaultOutline() {
  try {
    var outlineText = novelActs.map(function(act) {
      var lines = ['## ' + act.title + '（' + act.range + '）'];
      act.events.forEach(function(ev) {
        lines.push('- ' + ev.text);
      });
      return lines.join('\n');
    }).join('\n\n');
    await api('/api/project/outline', {
      method: 'POST',
      body: JSON.stringify({outline: outlineText})
    });
  } catch(e) { console.error('saveDefaultOutline error:', e); }
}

// ── Close popovers on outside click ──


