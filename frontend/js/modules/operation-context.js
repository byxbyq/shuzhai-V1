/**
 * OperationContext - 操作上下文管理器
 * 借鉴 inkos (开源AI小说引擎) 的设计模式：
 *   1. 操作开始时锁定目标章节索引，贯穿整个异步操作链
 *   2. 所有保存操作必须使用锁定的索引，禁止读取全局 currentChapterIndex
 *   3. 操作进行中禁止切章（或提供冲突检测）
 *
 * 核心思想：消灭全局可变状态带来的竞态风险
 */

;(function(global) {
  'use strict';

  // 当前活跃的操作上下文栈（支持嵌套，但同一时间只有一个活跃写操作）
  var _activeContext = null;

  /**
   * 创建操作上下文 — 在异步操作开始时调用
   * @param {Object} opts
   * @param {number} opts.chapterIndex - 锁定的目标章节索引（不可变）
   * @param {string} opts.operation - 操作描述（如 "AI修复"、"生成正文"）
   * @param {Function} opts.onConflict - 可选：切章冲突回调
   * @returns {Object} 上下文对象 { chapterIndex, operation, isAlive, release }
   */
  function createOperationContext(opts) {
    var ctx = {
      chapterIndex: opts.chapterIndex,     // 锁定的章节索引 — 不可变
      operation: opts.operation || '未知操作',
      isAlive: true,                       // 操作是否仍在进行
      createdAt: Date.now(),
      onConflict: opts.onConflict || null
    };

    // 如果已有活跃上下文，记录警告
    if (_activeContext && _activeContext.isAlive) {
      console.warn('[OperationContext] 覆盖活跃上下文:', _activeContext.operation, '→', ctx.operation);
    }

    _activeContext = ctx;
    console.log('[OperationContext] 创建:', ctx.operation, '目标章节:', ctx.chapterIndex + 1);

    return ctx;
  }

  /**
   * 释放操作上下文 — 在异步操作完成时调用（无论成功或失败）
   */
  function releaseOperationContext(ctx) {
    if (!ctx) return;
    ctx.isAlive = false;
    if (_activeContext === ctx) {
      _activeContext = null;
      console.log('[OperationContext] 释放:', ctx.operation);
    }
  }

  /**
   * 获取当前活跃的操作上下文
   */
  function getActiveContext() {
    return _activeContext;
  }

  /**
   * 获取安全的章节索引 — 优先使用操作上下文的锁定值
   * 这是对所有异步操作的统一出口：
   *   - 如果有活跃上下文，返回锁定的索引
   *   - 否则返回 currentChapterIndex（同步操作场景）
   */
  function safeChapterIndex(fallbackIndex) {
    if (_activeContext && _activeContext.isAlive) {
      return _activeContext.chapterIndex;
    }
    return fallbackIndex !== undefined ? fallbackIndex : (typeof currentChapterIndex !== 'undefined' ? currentChapterIndex : 0);
  }

  /**
   * 切章冲突检测 — 在切章操作前调用
   * 如果有活跃的异步写操作，返回 true（表示应该阻止切章或提醒用户）
   */
  function hasActiveWriteOperation() {
    return _activeContext && _activeContext.isAlive;
  }

  /**
   * 带上下文的异步操作包装器 — 简化用法
   * 自动创建/释放上下文，确保操作链中使用锁定的章节索引
   *
   * 用法：
   *   await withChapterContext(chapterIndex, 'AI修复', async function(ctx) {
   *     // 在这里进行耗时操作...
   *     // 保存时使用 ctx.chapterIndex 而非 currentChapterIndex
   *     await saveChapter(ctx.chapterIndex, content);
   *   });
   */
  async function withChapterContext(chapterIndex, operation, asyncFn) {
    var ctx = createOperationContext({ chapterIndex: chapterIndex, operation: operation });
    try {
      return await asyncFn(ctx);
    } catch (e) {
      console.error('[OperationContext] 操作异常:', operation, e);
      throw e;
    } finally {
      releaseOperationContext(ctx);
    }
  }

  // 导出
  global.OperationContext = {
    create: createOperationContext,
    release: releaseOperationContext,
    getActive: getActiveContext,
    safeIndex: safeChapterIndex,
    hasActiveWrite: hasActiveWriteOperation,
    withChapter: withChapterContext
  };

})(window);
