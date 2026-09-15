// Extracted from app.js - AI对话中枢 (全局助手)
// ═══════════════════════════════════════════
// AI对话中枢 (全局助手)
// ═══════════════════════════════════════════

function toggleAIAssistant() {
  var panel = document.getElementById('ai-assistant-panel');
  var fab = document.getElementById('ai-assistant-fab');
  if (panel.style.display === 'none') {
    panel.style.display = 'flex';
    fab.style.display = 'none';
    setTimeout(function() { document.getElementById('assistant-input').focus(); }, 100);
  } else {
    panel.style.display = 'none';
    fab.style.display = 'flex';
  }
}

function clearAssistantChat() {
  var msgDiv = document.getElementById('assistant-messages');
  msgDiv.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:12px;padding:8px">💡 直接告诉我你想做什么，比如：<br>"检查第2章连贯性" · "导出epub" · "这周写了多少字" · "列出角色"</div>';
}

function _appendAssistantMsg(text, isUser) {
  var msgDiv = document.getElementById('assistant-messages');
  // 清除提示文字
  var hint = msgDiv.querySelector('div[style*="text-align:center"]');
  if (hint) hint.remove();
  
  var div = document.createElement('div');
  if (isUser) {
    div.style.cssText = 'align-self:flex-end;max-width:85%;padding:8px 12px;background:var(--accent);color:#fff;border-radius:12px 12px 4px 12px;font-size:13px;line-height:1.6;word-break:break-word';
  } else {
    div.style.cssText = 'align-self:flex-start;max-width:90%;padding:10px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:12px 12px 12px 4px;font-size:13px;line-height:1.6;word-break:break-word;color:var(--ink);white-space:pre-wrap';
  }
  div.textContent = text;
  msgDiv.appendChild(div);
  msgDiv.scrollTop = msgDiv.scrollHeight;
}

// 带操作按钮的AI助手消息（检查结果专用）
function _appendAssistantMsgWithActions(text, action) {
  var msgDiv = document.getElementById('assistant-messages');
  if (!msgDiv) return;
  var hint = msgDiv.querySelector('div[style*="text-align:center"]');
  if (hint) hint.remove();
  
  var div = document.createElement('div');
  div.style.cssText = 'align-self:flex-start;max-width:90%;padding:10px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:12px 12px 12px 4px;font-size:13px;line-height:1.6;word-break:break-word;color:var(--ink);white-space:pre-wrap';
  
  var textDiv = document.createElement('div');
  textDiv.textContent = text;
  div.appendChild(textDiv);
  
  if (action && action.has_issue) {
    var btnBar = document.createElement('div');
    btnBar.style.cssText = 'display:flex;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border-soft);flex-wrap:wrap';
    
    var fixBtn = document.createElement('button');
    fixBtn.textContent = '🤖 AI修复';
    fixBtn.style.cssText = 'padding:4px 10px;background:var(--accent);color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer';
    fixBtn.onclick = function() {
      var chIdx = action.chapter_index || 0;
      if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(chIdx);
      if (typeof goToStep === 'function') goToStep(STEPS.分卷);
      setTimeout(function() {
        var checkType = action.check_type;
        var btn = document.querySelector('.check-btn[data-check="' + checkType + '"]');
        if (btn) {
          document.querySelectorAll('.check-btn').forEach(function(b) { b.classList.remove('selected'); });
          btn.classList.add('selected');
        }
        var runBtn = document.getElementById('btn-run-checks');
        if (runBtn) runBtn.click();
        _appendAssistantMsg('📍 已切换到第' + (chIdx + 1) + '章并开始' + (action.check_type) + '检查，请在右侧面板查看结果并修复。', false);
      }, 1500);
    };
    btnBar.appendChild(fixBtn);
    
    var locBtn = document.createElement('button');
    locBtn.textContent = '📍 定位问题';
    locBtn.style.cssText = 'padding:4px 10px;background:var(--info);color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer';
    locBtn.onclick = function() {
      var chIdx = action.chapter_index || 0;
      if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(chIdx);
      if (typeof goToStep === 'function') goToStep(STEPS.分卷);
      _appendAssistantMsg('📍 已切换到第' + (chIdx + 1) + '章，请在编辑器中查看问题段落。', false);
    };
    btnBar.appendChild(locBtn);
    
    var chBtn = document.createElement('button');
    chBtn.textContent = '📖 查看章节';
    chBtn.style.cssText = 'padding:4px 10px;background:var(--bg);color:var(--ink);border:1px solid var(--border);border-radius:4px;font-size:11px;cursor:pointer';
    chBtn.onclick = function() {
      var chIdx = action.chapter_index || 0;
      if (typeof loadChapterContentAPI === 'function') loadChapterContentAPI(chIdx);
      if (typeof goToStep === 'function') goToStep(STEPS.分卷);
      _appendAssistantMsg('📖 已切换到第' + (chIdx + 1) + '章。', false);
    };
    btnBar.appendChild(chBtn);
    
    div.appendChild(btnBar);
  }
  
  msgDiv.appendChild(div);
  msgDiv.scrollTop = msgDiv.scrollHeight;
}

// 任务3: AI助手请求重试机制
// 指数退避重试：失败后等待 1s/2s/4s 重试，最多 3 次
// 仅对网络错误和 5xx 错误重试，4xx 不重试
async function _sendAssistantRequestWithRetry(reqBody) {
  var maxRetries = 3;
  var retryDelayBase = 1000; // 1秒基数
  var attempt = 0;
  var lastError = null;

  function updateWaitingText(text) {
    var w = document.getElementById('assistant-waiting');
    if (w) w.textContent = text;
  }

  function isRetryableError(result) {
    // 网络错误或5xx才重试
    if (!result) return true;
    // 4xx 客户端错误不重试
    if (result.status && result.status >= 400 && result.status < 500) return false;
    // 5xx 服务端错误重试
    if (result.status && result.status >= 500 && result.status < 600) return true;
    // 没有 status（纯网络错误）重试
    if (!result.status && result.error) return true;
    // 业务错误（ok:false但有status 200）不重试
    return false;
  }

  function wait(ms) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
  }

  while (attempt < maxRetries) {
    attempt++;
    try {
      var r = await api('/api/agent/chat', {
        method: 'POST',
        body: JSON.stringify(reqBody)
      });

      if (r && r.ok) {
        return r; // 成功
      }

      // 判断是否可重试
      if (isRetryableError(r) && attempt < maxRetries) {
        lastError = r ? (r.error || '请求失败') : '未知错误';
        var delay = retryDelayBase * Math.pow(2, attempt - 1);
        updateWaitingText('⏳ 重试中（第' + (attempt + 1) + '/' + maxRetries + '次）...');
        await wait(delay);
        continue;
      }

      // 不可重试或已达最大次数
      return r;
    } catch (e) {
      lastError = e.message || '网络错误';
      if (attempt < maxRetries) {
        var delay2 = retryDelayBase * Math.pow(2, attempt - 1);
        updateWaitingText('⏳ 重试中（第' + (attempt + 1) + '/' + maxRetries + '次）...');
        await wait(delay2);
        continue;
      }
      throw e;
    }
  }

  // 理论上不会走到这里
  throw new Error(lastError || '请求失败');
}

async function sendAssistantMessage() {
  var input = document.getElementById('assistant-input');
  var msg = input.value.trim();
  if (!msg) return;
  
  _appendAssistantMsg(msg, true);
  input.value = '';
  
  // 选段修复：检查编辑器中是否有选中文字
  var selectedText = '';
  try {
    // 优先用保存的选区（点击输入框后选区会丢失）
    if (window._lastEditorSelection && window._lastEditorSelection.text) {
      selectedText = window._lastEditorSelection.text;
    } else {
      var editorEl = document.getElementById('editor-content');
      if (editorEl) {
        var sel = window.getSelection();
        selectedText = sel.toString();
        if (selectedText && !editorEl.contains(sel.anchorNode)) {
          selectedText = '';
        }
      }
    }
    
    if (selectedText && selectedText.length >= 10) {
      var preview = selectedText.length > 80 ? selectedText.substring(0, 80) + '...' : selectedText;
      _appendAssistantMsg('📝 已选中文字：「' + preview + '」\n指令：' + msg, false);
    } else {
      selectedText = '';
    }
  } catch(e) { selectedText = ''; }
  
  // 本地拦截：修复检查问题相关指令
  var fixKeywords = ['修复', '修改问题', '修复问题', '全部修复', '一键修复', '修一下', '改正', '纠正'];
  var isFixIntent = fixKeywords.some(function(k) { return msg.includes(k); });
  if (isFixIntent && !selectedText && window._allValProblems && window._allValProblems.length > 0) {
    _appendAssistantMsg('🔍 检测到检查结果中有' + window._allValProblems.length + '项问题，正在调用AI综合修复...', false);
    // 直接调用valAIFixAll
    if (typeof valAIFixAll === 'function') {
      valAIFixAll();
    }
    return;
  }
  if (isFixIntent && !selectedText && (!window._allValProblems || window._allValProblems.length === 0)) {
    _appendAssistantMsg('⚠️ 当前没有检查出的问题可修复。请先在右侧检查面板运行检查，发现问题后再来修复。\n💡 或者你可以在编辑器中选中一段文字，然后告诉我怎么修改。', false);
    return;
  }
  
  // 显示等待
  var msgDiv = document.getElementById('assistant-messages');
  var waitDiv = document.createElement('div');
  waitDiv.id = 'assistant-waiting';
  waitDiv.style.cssText = 'align-self:flex-start;padding:10px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:12px 12px 12px 4px;font-size:13px;color:var(--muted)';
  waitDiv.textContent = '⏳ 正在处理...';
  msgDiv.appendChild(waitDiv);
  msgDiv.scrollTop = msgDiv.scrollHeight;
  
  try {
    // 构建上下文
    var ctx = {};
    if (typeof currentChapterIndex !== 'undefined') {
      ctx.current_chapter_index = currentChapterIndex;
    }
    // C2: 包含上传文件内容
    if (_assistantFileContent) {
      ctx.file_content = _assistantFileContent;
      ctx.file_name = _assistantFileName;
    }
    // 创作向导上下文
    if (window._wizardState && window._wizardState.stage && window._wizardState.stage !== 'done') {
      ctx.wizard_stage = window._wizardState.stage;
      if (window._wizardState.genre) ctx.wizard_genre = window._wizardState.genre;
      if (window._wizardState.world_text) ctx.wizard_world_text = window._wizardState.world_text;
      if (window._wizardState.protagonist_info) ctx.wizard_protagonist_info = window._wizardState.protagonist_info;
      if (window._wizardState.char_text) ctx.wizard_char_text = window._wizardState.char_text;
      if (window._wizardState.oneliner) ctx.wizard_oneliner = window._wizardState.oneliner;
      if (window._wizardState.outline_text) ctx.wizard_outline_text = window._wizardState.outline_text;
      if (window._wizardState.volumes_text) ctx.wizard_volumes_text = window._wizardState.volumes_text;
      if (window._wizardState.chapter_outline_text) ctx.wizard_chapter_outline_text = window._wizardState.chapter_outline_text;
      if (window._wizardState.append_stage) ctx.wizard_append_stage = window._wizardState.append_stage;
      if (window._wizardState.append_volume_index !== undefined) ctx.wizard_append_volume_index = window._wizardState.append_volume_index;
    }
    
    var reqBody = { message: msg, context: ctx };
    if (selectedText) {
      reqBody.selected_text = selectedText;
    }
    
    // C2: 判断是否为自由对话（非命令型），使用流式渲染
    var commandKeywords = ['检查', '导出', '修复', '删除', '创建', '添加', '生成', '列出', '显示', '统计', '跳转', '打开', '关闭', '切换', '保存', '清空', '去AI味', '扫榜', '诊断', '伏笔', '时间线', '去', '书架', '面板', '改名', '改成', '修改', '新增', '废弃', '重命名', '删掉'];
    var isCommand = commandKeywords.some(function(k) { return msg.includes(k); });
    
    if (!isCommand && !selectedText && !_assistantFileContent) {
      // 纯自由对话：使用流式渲染
      var w0 = document.getElementById('assistant-waiting');
      if (w0) w0.remove();
      
      // 创建流式消息气泡
      var streamDiv = document.createElement('div');
      streamDiv.style.cssText = 'align-self:flex-start;max-width:90%;padding:10px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:12px 12px 12px 4px;font-size:13px;line-height:1.6;word-break:break-word;color:var(--ink);white-space:pre-wrap';
      streamDiv.textContent = '…';
      msgDiv.appendChild(streamDiv);
      msgDiv.scrollTop = msgDiv.scrollHeight;
      
      // 构建消息上下文
      var chatMessages = [{role: 'user', content: msg}];
      // 注入当前章节上下文
      if (typeof currentChapterIndex !== 'undefined' && typeof chapters !== 'undefined' && chapters[currentChapterIndex]) {
        var ch = chapters[currentChapterIndex];
        var content = (ch.content || '').substring(0, 2000);
        if (content) {
          chatMessages.unshift({role: 'system', content: '当前是第' + (currentChapterIndex+1) + '章《' + (ch.title||'') + '》，正文前2000字：\n' + content});
        }
      }
      
      var streamText = '';
      await _sendAssistantStream(chatMessages,
        function(chunk) {
          streamText += chunk;
          streamDiv.textContent = streamText;
          msgDiv.scrollTop = msgDiv.scrollHeight;
        },
        function() {
          if (!streamText) streamDiv.textContent = '(空回复)';
        },
        function(err) {
          streamDiv.textContent = '❌ 流式请求失败: ' + err + '\n\n正在尝试普通请求...';
          // 降级到普通请求
          _sendAssistantFallback(reqBody);
        }
      );
      return;
    }
    
    // 使用带重试的请求
    var r = await _sendAssistantRequestWithRetry(reqBody);
    
    // 移除等待
    var w = document.getElementById('assistant-waiting');
    if (w) w.remove();
    
    if (r.ok) {
      // 如果有检查结果action，显示带按钮的富文本消息
      if (r.action && r.action.type === 'check_result') {
        _appendAssistantMsgWithActions(r.reply || '(空回复)', r.action);
      } else {
        _appendAssistantMsg(r.reply || '(空回复)', false);
      }
      
      // 执行action
      if (r.action) {
        if (r.action.type === 'replace_selection') {
          // 选段修复：替换编辑器中的选中文字
          _replaceSelectionInEditor(r.action.new_text, r.action.original_text);
        } else if (r.action.type && r.action.type.indexOf('wizard_') === 0) {
          // 创作向导相关动作
          _handleWizardAction(r.action, r.reply, r.data);
        } else if (r.action.type !== 'check_result') {
          _executeAssistantAction(r.action);
        }
      }
    } else {
      var errMsg = r.error || '处理失败';
      _appendAssistantMsg('❌ 请求失败：' + errMsg + '\n\n💡 请检查网络连接或稍后重试。', false);
    }
  } catch (e) {
    // 最终失败，移除等待提示
    var w2 = document.getElementById('assistant-waiting');
    if (w2) w2.remove();
    _appendAssistantMsg('❌ 网络错误：' + (e.message || '未知错误') + '\n\n💡 请检查网络连接后重试。', false);
  }
}

// 选段修复：替换编辑器中的选中文字
function _replaceSelectionInEditor(newText, originalText) {
  try {
    var editorEl = document.getElementById('editor-content');
    if (!editorEl) { _appendAssistantMsg('⚠️ 找不到编辑器', false); return; }
    
    // 方式1：用保存的选区替换
    if (window._lastEditorSelection && window._lastEditorSelection.range) {
      var savedRange = window._lastEditorSelection.range;
      try {
        savedRange.deleteContents();
        savedRange.insertNode(document.createTextNode(newText));
        // 清除保存的选区
        window._lastEditorSelection = null;
        // 触发保存
        if (typeof autoSave === 'function') autoSave();
        _appendAssistantMsg('✏️ 已替换选中文字，记得点保存按钮保存修改。', false);
        return;
      } catch(e2) { /* 失败则用方式2 */ }
    }
    
    // 方式2：用Selection API替换（如果选中还存在）
    var sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && !sel.isCollapsed && editorEl.contains(sel.anchorNode)) {
      var range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(document.createTextNode(newText));
      sel.removeAllRanges();
      if (typeof autoSave === 'function') autoSave();
      _appendAssistantMsg('✏️ 已替换选中文字，记得点保存按钮保存修改。', false);
      return;
    }
    
    // 方式3：用文本查找替换
    var currentText = editorEl.innerText;
    if (currentText.indexOf(originalText) >= 0) {
      var newText2 = currentText.replace(originalText, newText);
      editorEl.innerText = newText2;
      if (typeof autoSave === 'function') autoSave();
      _appendAssistantMsg('✏️ 已替换选中文字，记得点保存按钮保存修改。', false);
      return;
    }
    
    _appendAssistantMsg('⚠️ 无法定位选中的文字（可能已取消选中），请重新选中后重试。', false);
  } catch(e) {
    _appendAssistantMsg('⚠️ 替换失败：' + e.message, false);
  }
}

// 监听编辑器选区变化，保存选区（用于点击输入框后恢复）
document.addEventListener('selectionchange', function() {
  try {
    var editorEl = document.getElementById('editor-content');
    if (!editorEl) return;
    var sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.rangeCount > 0 && editorEl.contains(sel.anchorNode)) {
      var text = sel.toString();
      if (text && text.length >= 5) {
        window._lastEditorSelection = {
          text: text,
          range: sel.getRangeAt(0).cloneRange()
        };
      }
    }
  } catch(e) {}
});

// ═══ AI助手 -> 界面按钮桥接函数 ═══
// 这4个函数让AI助手对话能触发与按钮相同的操作
// 复用已有按钮逻辑，避免重复实现

function aiContinue() {
  var btn = document.getElementById('wt-btn-cont');
  if (btn) { btn.click(); return true; }
  _appendAssistantMsg('⚠️ 找不到续写按钮', false);
  return false;
}

function aiGenerate() {
  var btn = document.getElementById('btn-ai-gen');
  if (btn) { btn.click(); return true; }
  _appendAssistantMsg('⚠️ 找不到生成按钮', false);
  return false;
}

function aiOptimize() {
  var btn = document.getElementById('wt-btn-opt');
  if (btn) { btn.click(); return true; }
  _appendAssistantMsg('⚠️ 找不到优化按钮', false);
  return false;
}

function aiGetOutline() {
  if (typeof generateNextChapterOutline === 'function') {
    generateNextChapterOutline();
    return true;
  }
  _appendAssistantMsg('⚠️ 大纲生成功能未就绪', false);
  return false;
}

// ═══════════════════════════════════════════
// 创作向导状态机处理
// ═══════════════════════════════════════════
function _handleWizardAction(action, reply, data) {
  _clearWizardGenreBtns();
  
  var actionType = action.type;
  
  if (actionType === 'wizard_ask_genre') {
    // 重新询问题材
    window._wizardState.stage = 'ask_genre';
    var msgDiv = document.getElementById('assistant-messages');
    var btnDiv = document.createElement('div');
    btnDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin:4px 0;padding:0 14px;align-self:flex-start;max-width:90%';
    btnDiv.id = 'wizard-genre-btns';
    var genres = ['仙侠', '都市', '玄幻', '科幻', '历史', '悬疑', '言情', '军事', '游戏', '末世', '重生', '穿越', '武侠', '灵异', '同人', '轻小说', '古言', '职场', '电竞', '无限流', '系统流', '快穿', '甜宠', '星际'];
    genres.forEach(function(g) {
      var b = document.createElement('button');
      b.textContent = g;
      b.style.cssText = 'padding:4px 12px;background:var(--bg);border:1px solid var(--border);border-radius:14px;font-size:12px;cursor:pointer;color:var(--ink)';
      b.onmouseover = function() { b.style.background = 'var(--accent)'; b.style.color = '#fff'; b.style.borderColor = 'var(--accent)'; };
      b.onmouseout = function() { b.style.background = 'var(--bg)'; b.style.color = 'var(--ink)'; b.style.borderColor = 'var(--border)'; };
      b.onclick = function() {
        document.getElementById('assistant-input').value = g;
        sendAssistantMessage();
      };
      btnDiv.appendChild(b);
    });
    msgDiv.appendChild(btnDiv);
    msgDiv.scrollTop = msgDiv.scrollHeight;
    return;
  }
  
  if (actionType === 'wizard_stage') {
    // 阶段推进
    var nextStage = action.next;
    window._wizardState.stage = nextStage;
    
    if (data) {
      if (data.genre) window._wizardState.genre = data.genre;
      if (data.world_settings && data.world_settings.raw_text) window._wizardState.world_text = data.world_settings.raw_text;
      if (data.world_name) window._wizardState.world_name = data.world_name;
      if (data.protagonist_info) window._wizardState.protagonist_info = data.protagonist_info;
      if (data.character_info && data.character_info.raw_text) window._wizardState.char_text = data.character_info.raw_text;
      if (data.oneliner) window._wizardState.oneliner = data.oneliner;
      if (data.outline_text) window._wizardState.outline_text = data.outline_text;
      if (data.volumes_text) window._wizardState.volumes_text = data.volumes_text;
      if (data.chapter_outline_text) window._wizardState.chapter_outline_text = data.chapter_outline_text;
      // 追加模式：新阶段名和卷索引
      if (data.new_stage) window._wizardState.append_stage = data.new_stage;
      if (data.volume_index !== undefined) window._wizardState.append_volume_index = data.volume_index;
    }
    
    // 题材选择后、人物确定后、大纲确定后，提供快捷输入
    if (nextStage === 'ask_protagonist') {
      setTimeout(function() {
        var input = document.getElementById('assistant-input');
        if (input) input.placeholder = '描述你的主角，比如：李明，22岁，普通大学生，性格内敛但倔强...';
      }, 300);
    } else if (nextStage === 'ask_oneliner') {
      setTimeout(function() {
        var input = document.getElementById('assistant-input');
        if (input) input.placeholder = '一句话主线，比如：废材少年捡到上古神器，一路逆袭踏上修仙巅峰';
      }, 300);
    } else if (nextStage === 'generate_world') {
      // 自动触发世界观生成
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_world') {
          document.getElementById('assistant-input').value = window._wizardState.genre;
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'generate_characters') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_characters') {
          document.getElementById('assistant-input').value = window._wizardState.protagonist_info || '';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'generate_outline') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_outline') {
          document.getElementById('assistant-input').value = window._wizardState.oneliner || '';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'generate_blueprint') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_blueprint') {
          document.getElementById('assistant-input').value = '开始';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'generate_volumes') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_volumes') {
          document.getElementById('assistant-input').value = '开始';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'generate_chapter_outlines') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'generate_chapter_outlines') {
          document.getElementById('assistant-input').value = '开始';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'append_volumes') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'append_volumes') {
          document.getElementById('assistant-input').value = '开始';
          sendAssistantMessage();
        }
      }, 500);
    } else if (nextStage === 'append_chapter_outlines') {
      setTimeout(function() {
        if (window._wizardState && window._wizardState.stage === 'append_chapter_outlines') {
          document.getElementById('assistant-input').value = '开始';
          sendAssistantMessage();
        }
      }, 500);
    }
    return;
  }
  
  if (actionType === 'wizard_complete') {
    window._wizardState.stage = 'done';
    _appendAssistantMsg('🎉 向导完成！你可以开始写作了。', false);
    // 刷新项目数据（如果 initApp 还没执行完）
    setTimeout(function() {
      if (typeof reloadAllProjectData === 'function') reloadAllProjectData();
    }, 1000);
    return;
  }
}

function _executeAssistantAction(action) {
  if (!action) return;
  switch (action.type) {
    case 'export':
      // 触发导出下载
      window.open(API_BASE + '/api/export/' + action.format, '_blank');
      _appendAssistantMsg('📎 已触发' + action.format.toUpperCase() + '下载，请查看浏览器下载。', false);
      break;
    case 'load_chapter':
      // 加载章节
      if (typeof loadChapter === 'function') {
        loadChapter(action.chapter_index);
        _appendAssistantMsg('📖 已切换到第' + (action.chapter_index + 1) + '章。', false);
      }
      break;
    case 'open_stats':
      if (typeof openStatsPanel === 'function') {
        setTimeout(openStatsPanel, 500);
        _appendAssistantMsg('📊 已打开统计面板。', false);
      }
      break;
    case 'open_snapshot_diff':
      if (typeof openSnapshotDiffPanel === 'function') {
        setTimeout(openSnapshotDiffPanel, 500);
        _appendAssistantMsg('📋 已打开版本对比面板。', false);
      }
      break;
    case 'reload_outline':
      if (typeof loadProjectOutline === 'function') {
        setTimeout(loadProjectOutline, 500);
        _appendAssistantMsg('📐 大纲已刷新。', false);
      }
      break;
    case 'reload_settings':
      if (typeof loadProjectSettings === 'function') {
        setTimeout(loadProjectSettings, 500);
        _appendAssistantMsg('⚙️ 世界观设定已刷新。', false);
      }
      break;
    case 'reload_settings':
      if (typeof loadProjectSettings === 'function') {
        setTimeout(loadProjectSettings, 500);
        _appendAssistantMsg('⚙️ 设定已刷新。', false);
      }
      break;
    case 'reload_outline':
      if (typeof loadProjectOutline === 'function') {
        setTimeout(loadProjectOutline, 500);
        _appendAssistantMsg('📐 大纲已刷新。', false);
      }
      break;
    case 'continue':
      if (typeof aiContinue === 'function') {
        if (action.chapter_index !== undefined && action.chapter_index !== currentChapterIndex) {
          loadChapter(action.chapter_index);
        }
        setTimeout(aiContinue, 800);
        _appendAssistantMsg('✍️ 正在续写，请稍候...', false);
      } else {
        _appendAssistantMsg('⚠️ 续写功能未就绪', false);
      }
      break;
    case 'generate':
      if (typeof aiGenerate === 'function') {
        if (action.chapter_index !== undefined && action.chapter_index !== currentChapterIndex) {
          loadChapter(action.chapter_index);
        }
        setTimeout(aiGenerate, 800);
        _appendAssistantMsg('✍️ 正在生成内容，请稍候...', false);
      } else {
        _appendAssistantMsg('⚠️ 生成功能未就绪', false);
      }
      break;
    case 'optimize':
      if (typeof aiOptimize === 'function') {
        if (action.chapter_index !== undefined && action.chapter_index !== currentChapterIndex) {
          loadChapter(action.chapter_index);
        }
        setTimeout(aiOptimize, 800);
        _appendAssistantMsg('✍️ 正在优化内容，请稍候...', false);
      } else {
        _appendAssistantMsg('⚠️ 优化功能未就绪', false);
      }
      break;
    case 'generate_outline':
      if (typeof aiGetOutline === 'function') {
        setTimeout(aiGetOutline, 500);
        _appendAssistantMsg('📐 正在生成大纲...', false);
      } else {
        _appendAssistantMsg('⚠️ 大纲生成功能未就绪', false);
      }
      break;
    case 'save_chapter':
      if (typeof saveChapter === 'function' && typeof currentChapterIndex !== 'undefined') {
        saveChapter(currentChapterIndex);
        _appendAssistantMsg('💾 已保存当前章节。', false);
      } else {
        var saveBtn = document.getElementById('btn-save');
        if (saveBtn) { saveBtn.click(); _appendAssistantMsg('💾 已保存当前章节。', false); }
      }
      break;
    case 'open_deconstruct':
      window.open('deconstruct.html', '_blank');
      _appendAssistantMsg('📖 已打开拆书学习页面。', false);
      break;
    case 'open_storyboard':
      window.open('storyboard.html', '_blank');
      _appendAssistantMsg('🎬 已打开分镜页面。', false);
      break;
    case 'open_sync':
      if (typeof openSyncPanel === 'function') {
        setTimeout(openSyncPanel, 500);
        _appendAssistantMsg('☁️ 已打开云同步面板。', false);
      }
      break;
    case 'reload_chapters':
      // 重新加载章节列表
      if (typeof loadChaptersFromAPI === 'function') {
        setTimeout(function() {
          loadChaptersFromAPI().then(function() {
            if (action.chapter_index !== undefined && typeof loadChapterContentAPI === 'function') {
              loadChapterContentAPI(action.chapter_index);
            }
          });
        }, 300);
      }
      break;
    case 'reload_project':
      // 重新加载整个项目
      if (typeof loadProjectList === 'function') {
        setTimeout(function() {
          loadProjectList().then(function() {
            if (typeof loadChaptersFromAPI === 'function') loadChaptersFromAPI();
            if (typeof loadProjectSettings === 'function') loadProjectSettings();
            if (typeof loadProjectOutline === 'function') loadProjectOutline();
          });
        }, 300);
      }
      break;
    case 'reload_current_chapter':
      // 重新加载当前章节（全文替换后用）
      if (typeof loadChapterContentAPI === 'function' && typeof currentChapterIndex !== 'undefined') {
        setTimeout(function() { loadChapterContentAPI(currentChapterIndex); }, 300);
        _appendAssistantMsg('🔄 编辑器内容已刷新。', false);
      }
      break;
    case 'open_page':
      // 页面导航：后端 NavigateAgent 返回规范页面名，映射表执行跳转
      _navigateToPage(action.page);
      break;
    case 'reload_volumes':
      // 卷增删改后刷新分卷列表（loadVolumesData + renderVolumeOutlineList 都在 inline-glue 定义）
      if (typeof loadVolumesData === 'function') {
        setTimeout(function() {
          loadVolumesData().then(function() {
            if (typeof renderVolumeOutlineList === 'function') renderVolumeOutlineList();
          });
        }, 300);
        _appendAssistantMsg('📚 卷列表已刷新。', false);
      }
      break;
    case 'reload_hooks':
      // 伏笔状态变更后刷新伏笔面板（面板未打开时静默刷新数据）
      setTimeout(function() {
        if (typeof loadHooksPanel === 'function') loadHooksPanel();
        if (typeof loadForeshadows === 'function') loadForeshadows();
      }, 300);
      break;
  }
}

// ═══ AI助手 -> 页面导航（open_page 动作）═══
// 页面名（后端规范名）→ 跳转函数。与 backend/agents/navigate_agent.py 的规范名一一对应。
var _PAGE_NAV_MAP = {
  // 工作流九步
  '世界观':   function() { goToStep(STEPS.世界观); },
  '人物':     function() { goToStep(STEPS.人物); },
  '全书大纲': function() { goToStep(STEPS.全书大纲); },
  '分卷':     function() { goToStep(STEPS.分卷); },
  '章节大纲': function() { goToStep(STEPS.章节大纲); },
  '连线框':   function() { goToStep(STEPS.连线框); },
  '写作':     function() { goToStep(STEPS.写作); },
  '时间线':   function() { goToStep(STEPS.时间线); },
  '草稿定稿': function() { goToStep(STEPS.草稿定稿); },
  // 功能面板
  '伏笔管理': function() { openHooksPanel(); },
  '头脑风暴': function() { openBrainstormPanel(); },
  '五感描写': function() { openSensoryPanel(); },
  '写作统计': function() { openStatsPanel(); },
  '版本对比': function() { openSnapshotDiffPanel(); },
  '云同步':   function() { openSyncPanel(); },
  '导出':     function() { openExportPanel(); },
  '导入':     function() { openImportPanel(); },
  '大纲模板': function() { openTemplatePanel(); },
  '批量检查': function() { openBatchCheckPanel(); },
  '角色对话': function() { openCharacterChatPanel(); },
  '技能包':   function() { openSkillPackPanel(); },
  'AI编辑器': function() { openAIEditorPanel(); },
  '排行榜':   function() { openRankingPanel(); },
  '描写':     function() { openDescribePanel(); },
  '扩写':     function() { openExpandPanel(); },
  '改写':     function() { openRewritePanel(); },
  '反馈':     function() { openFeedbackPanel(); },
  'AI分析':   function() { openAIAnalysisPanel(); },
  '快捷模式': function() { openQuickModePanel(); },
  '提炼':     function() { openDistillPanel(); },
  '审计日志': function() { openAuditLogPanel(); },
  // 独立页面/入口
  '创作向导': function() { startCreativeWizard(true); },
  '拆书':     function() { window.open('deconstruct.html', '_blank'); },
  '分镜':     function() { window.open('storyboard.html', '_blank'); },
  '书架':     function() { openBookshelf(); }
};

function _navigateToPage(page) {
  var fn = _PAGE_NAV_MAP[page];
  if (!fn) {
    _appendAssistantMsg('⚠️ 我暂时打不开「' + page + '」页面。', false);
    return;
  }
  try {
    fn();
  } catch (e) {
    _appendAssistantMsg('⚠️ 打开「' + page + '」失败：' + e.message, false);
  }
}

// === AI助手面板拖动 ===
(function() {
  var panel = document.getElementById('ai-assistant-panel');
  var header = document.getElementById('ai-assistant-header');
  if (!panel || !header) return;
  
  var isDragging = false;
  var startX = 0, startY = 0;
  var startLeft = 0, startTop = 0;
  
  header.addEventListener('mousedown', function(e) {
    // 不拦截按钮点击
    if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
    // 手机端不拖动
    if (window.innerWidth <= 640) return;
    
    isDragging = true;
    var rect = panel.getBoundingClientRect();
    // 固定定位改为absolute定位
    panel.style.position = 'fixed';
    panel.style.left = rect.left + 'px';
    panel.style.top = rect.top + 'px';
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    
    startX = e.clientX;
    startY = e.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    
    e.preventDefault();
  });
  
  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    var dx = e.clientX - startX;
    var dy = e.clientY - startY;
    var newLeft = Math.max(0, Math.min(window.innerWidth - panel.offsetWidth, startLeft + dx));
    var newTop = Math.max(0, Math.min(window.innerHeight - panel.offsetHeight, startTop + dy));
    panel.style.left = newLeft + 'px';
    panel.style.top = newTop + 'px';
  });
  
  document.addEventListener('mouseup', function() {
    isDragging = false;
  });
})();

// ═══════════════════════════════════════════
// C2: 文件上传 + 流式渲染
// ═══════════════════════════════════════════
var _assistantFileContent = '';
var _assistantFileName = '';

function handleAssistantFileUpload(input) {
  if (!input.files || !input.files[0]) return;
  var file = input.files[0];
  if (file.size > 50000) {
    showToast && showToast('文件过大（>50KB），仅读取前 50KB');
  }
  var reader = new FileReader();
  reader.onload = function(e) {
    _assistantFileContent = e.target.result.substring(0, 50000);
    _assistantFileName = file.name;
    var badge = document.getElementById('assistant-file-badge');
    if (badge) {
      badge.style.display = 'inline-block';
      badge.textContent = '📎 ' + file.name;
    }
  };
  reader.readAsText(file);
  input.value = ''; // 重置以允许重复上传同一文件
}

function clearAssistantFile() {
  _assistantFileContent = '';
  _assistantFileName = '';
  var badge = document.getElementById('assistant-file-badge');
  if (badge) badge.style.display = 'none';
}

// 降级：流式失败后使用普通 agent 请求
async function _sendAssistantFallback(reqBody) {
  try {
    var r = await _sendAssistantRequestWithRetry(reqBody);
    var w = document.getElementById('assistant-waiting');
    if (w) w.remove();
    if (r && r.ok) {
      if (r.action && r.action.type === 'check_result') {
        _appendAssistantMsgWithActions(r.reply || '(空回复)', r.action);
      } else {
        _appendAssistantMsg(r.reply || '(空回复)', false);
      }
      if (r.action) {
        if (r.action.type === 'replace_selection') {
          _replaceSelectionInEditor(r.action.new_text, r.action.original_text);
        } else if (r.action.type !== 'check_result') {
          _executeAssistantAction(r.action);
        }
      }
    } else {
      _appendAssistantMsg('❌ 请求失败：' + (r && r.error || '处理失败'), false);
    }
  } catch(e) {
    var w2 = document.getElementById('assistant-waiting');
    if (w2) w2.remove();
    _appendAssistantMsg('❌ 请求异常：' + e.message, false);
  }
}

// 流式发送：使用 SSE 实时显示 AI 回复
async function _sendAssistantStream(messages, onChunk, onDone, onError) {
  try {
    var baseURL = (typeof API_BASE !== 'undefined') ? API_BASE : '';
    var headers = (typeof _authHeaders === 'function') ? _authHeaders({'Content-Type': 'application/json'}) : {'Content-Type': 'application/json'};
    var resp = await fetch(baseURL + '/api/ai/chat/stream', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({messages: messages})
    });
    if (!resp.ok) {
      onError && onError('HTTP ' + resp.status);
      return;
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, {stream: true});
      var lines = buffer.split('\n');
      buffer = lines.pop(); // 保留不完整的行
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line.startsWith('data: ')) {
          try {
            var data = JSON.parse(line.substring(6));
            if (data.content) onChunk && onChunk(data.content);
            if (data.done) { onDone && onDone(); return; }
            if (data.error) { onError && onError(data.error); return; }
          } catch(e) {}
        }
      }
    }
    onDone && onDone();
  } catch(e) {
    onError && onError(e.message);
  }
}
