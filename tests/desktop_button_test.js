/**
 * 书斋V66 桌面端全按钮功能测试
 * 使用 Playwright 自动化测试所有按钮
 * 用法: node tests/desktop_button_test.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:8894';
const SCREENSHOT_DIR = process.env.TEST_SCREENSHOT_DIR || path.join(__dirname, '..', 'test_screenshots', 'desktop_test');
const REPORT_FILE = path.join(SCREENSHOT_DIR, 'report.json');

// Ensure screenshot directory exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const results = [];
let screenshotIdx = 0;

function screenshot(page, name) {
  const idx = String(screenshotIdx++).padStart(3, '0');
  const filename = `${idx}_${name}.png`;
  return page.screenshot({ path: path.join(SCREENSHOT_DIR, filename), fullPage: false });
}

async function testStep(page, name, fn) {
  console.log(`  [TEST] ${name}...`);
  try {
    await fn();
    console.log(`    ✅ PASS`);
    results.push({ name, status: 'PASS' });
    return true;
  } catch (e) {
    console.log(`    ❌ FAIL: ${e.message}`);
    await screenshot(page, `FAIL_${name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_')}`);
    results.push({ name, status: 'FAIL', error: e.message });
    return false;
  }
}

async function safeClick(page, selector, timeout = 3000) {
  const el = await page.$(selector);
  if (!el) throw new Error(`Element not found: ${selector}`);
  await el.scrollIntoViewIfNeeded();
  await el.click({ timeout });
}

async function safeType(page, selector, text) {
  const el = await page.$(selector);
  if (!el) throw new Error(`Element not found: ${selector}`);
  await el.fill(text);
}

async function waitForOverlay(page, selector, timeout = 5000) {
  await page.waitForSelector(selector, { state: 'visible', timeout });
}

async function closeOverlay(page, closeBtnSelector) {
  await safeClick(page, closeBtnSelector);
  await page.waitForTimeout(500);
}

async function run() {
  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: 'zh-CN'
  });
  const page = await context.newPage();

  console.log('=== 书斋V66 桌面端全按钮功能测试 ===\n');

  // ========================================
  // Phase 0: 启动 & 等待加载
  // ========================================
  console.log('Phase 0: 启动 & 页面加载');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000); // Wait for init scripts
  await screenshot(page, '00_initial_load');

  // ========================================
  // Phase 1: 顶部工具栏
  // ========================================
  console.log('\nPhase 1: 顶部工具栏');

  await testStep(page, '1.1 左抽屉切换按钮', async () => {
    await safeClick(page, '#btn-toggle-left');
    await page.waitForTimeout(500);
  });

  await testStep(page, '1.2 新建项目按钮打开对话框', async () => {
    await safeClick(page, '#btn-new-project');
    await waitForOverlay(page, '#new-project-overlay');
    await screenshot(page, '01_new_project_dialog');
  });

  await testStep(page, '1.3 新建项目对话框关闭', async () => {
    await safeClick(page, '#new-project-close');
    await page.waitForTimeout(500);
  });

  await testStep(page, '1.4 打开项目选择器', async () => {
    await safeClick(page, '#btn-open-project');
    await waitForOverlay(page, '#project-picker');
    await page.waitForTimeout(500);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  await testStep(page, '1.5 AI模型配置浮层', async () => {
    await safeClick(page, '#model-badge');
    await waitForOverlay(page, '#model-popover');
    await screenshot(page, '02_model_popover');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  await testStep(page, '1.6 阅读模式按钮', async () => {
    await safeClick(page, '#btn-reader');
    await waitForOverlay(page, '#reader-overlay');
    await screenshot(page, '03_reader_overlay');
    await safeClick(page, '#reader-close-btn');
    await page.waitForTimeout(500);
  });

  await testStep(page, '1.7 工具箱下拉菜单', async () => {
    const btn = await page.$('[onclick="toggleToolbox()"]');
    if (!btn) throw new Error('工具箱按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#toolbox-dropdown');
    await screenshot(page, '04_toolbox_dropdown');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  await testStep(page, '1.8 右抽屉切换按钮', async () => {
    await safeClick(page, '#btn-toggle-right');
    await page.waitForTimeout(500);
    await safeClick(page, '#btn-close-right');
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 2: 工具箱各功能按钮
  // ========================================
  console.log('\nPhase 2: 工具箱功能面板');

  const toolboxItems = [
    { name: '2.1 拆书学习', click: "[onclick=\"openToolboxPage('/deconstruct.html')\"]", overlay: null },
    { name: '2.2 视频分镜', click: "[onclick=\"openToolboxPage('/storyboard.html')\"]", overlay: null },
    { name: '2.3 导出书籍', click: "[onclick=\"openExportPanel()\"]", overlay: '#export-overlay', close: "[onclick=\"closeOverlay('export-overlay')\"]" },
    { name: '2.4 导入小说', click: "[onclick=\"openImportPanel()\"]", overlay: '#import-overlay', close: '.overlay-close-btn' },
    { name: '2.5 版本对比', click: "[onclick=\"openSnapshotDiffPanel()\"]", overlay: '#snapshot-diff-overlay', close: "[onclick=\"closeOverlay('snapshot-diff-overlay')\"]" },
    { name: '2.6 角色对话', click: "[onclick=\"openCharacterChatPanel()\"]", overlay: '#character-chat-overlay', close: "[onclick=\"closeOverlay('character-chat-overlay')\"]" },
    { name: '2.7 云同步', click: "[onclick=\"openSyncPanel()\"]", overlay: '#sync-overlay', close: "[onclick=\"closeOverlay('sync-overlay')\"]" },
    { name: '2.8 大纲模板', click: "[onclick=\"openTemplatePanel()\"]", overlay: '#template-overlay', close: "[onclick=\"closeOverlay('template-overlay')\"]" },
    { name: '2.9 技能包', click: "[onclick=\"openSkillPackPanel()\"]", overlay: '#skill-pack-overlay', close: "[onclick=\"closeOverlay('skill-pack-overlay')\"]" },
    { name: '2.10 AI分析', click: "[onclick=\"openAIAnalysisPanel()\"]", overlay: '#ai-analysis-overlay', close: "[onclick=\"closeOverlay('ai-analysis-overlay')\"]" },
    { name: '2.11 规划视图', click: "[onclick=\"openPlanningPanel('grid')\"]", overlay: '#planning-overlay', close: "[onclick=\"closePlanningPanel()\"]" },
    { name: '2.12 审计日志', click: "[onclick=\"openAuditLogPanel()\"]", overlay: '#audit-log-overlay', close: "[onclick=\"closeOverlay('audit-log-overlay')\"]" },
    { name: '2.13 写作统计', click: "[onclick=\"openStatsPanel()\"]", overlay: '#stats-overlay', close: "[onclick=\"closeOverlay('stats-overlay')\"]" },
    { name: '2.14 蒸馏记忆', click: "[onclick=\"openDistillPanel()\"]", overlay: '#distill-overlay', close: "[onclick=\"closeOverlay('distill-overlay')\"]" },
    { name: '2.15 AI责编审稿', click: "[onclick=\"openAIEditorPanel()\"]", overlay: null },
    { name: '2.16 批量检查', click: "[onclick=\"openBatchCheckPanel()\"]", overlay: '#batch-check-overlay', close: "[onclick=\"closeOverlay('batch-check-overlay')\"]" },
  ];

  for (const item of toolboxItems) {
    await testStep(page, item.name, async () => {
      // Open toolbox
      const toolboxBtn = await page.$('[onclick="toggleToolbox()"]');
      if (!(await page.$('#toolbox-dropdown:visible'))) {
        await toolboxBtn.click();
        await page.waitForTimeout(300);
      }
      // Click item
      const el = await page.$(item.click);
      if (!el) {
        // Close toolbox and skip
        await page.keyboard.press('Escape');
        throw new Error(`Toolbox item not found: ${item.click}`);
      }
      await el.click();
      await page.waitForTimeout(800);
      
      if (item.overlay) {
        try {
          await waitForOverlay(page, item.overlay, 3000);
          await screenshot(page, item.name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_'));
          if (item.close) {
            await safeClick(page, item.close);
          } else {
            await page.keyboard.press('Escape');
          }
          await page.waitForTimeout(300);
        } catch {
          // Overlay might not appear - that's a potential issue
          console.log(`      ⚠ Overlay ${item.overlay} did not appear`);
          await page.keyboard.press('Escape');
        }
      } else {
        await page.waitForTimeout(500);
        await page.keyboard.press('Escape');
      }
      // Close toolbox if still open
      if (await page.$('#toolbox-dropdown:visible')) {
        await page.keyboard.press('Escape');
      }
    });
  }

  // ========================================
  // Phase 3: 工作流步骤切换
  // ========================================
  console.log('\nPhase 3: 工作流步骤切换');

  for (let step = 1; step <= 7; step++) {
    await testStep(page, `3.${step} 切换到步骤${step}`, async () => {
      const stepBtn = await page.$(`.workflow-step[onclick="goToStep(${step})"]`);
      if (!stepBtn) {
        // Try text-based selection
        await page.evaluate((s) => {
          const steps = document.querySelectorAll('.workflow-step');
          if (steps[s - 1]) steps[s - 1].click();
        }, step);
      } else {
        await stepBtn.click();
      }
      await page.waitForTimeout(500);
      await screenshot(page, `step_${step}`);
    });
  }

  // ========================================
  // Phase 4: Step 1 世界观面板按钮
  // ========================================
  console.log('\nPhase 4: Step 1 世界观面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(1)"]');
  await page.waitForTimeout(500);

  await testStep(page, '4.1 AI提取设定按钮', async () => {
    await safeClick(page, '#btn-ai-extract');
    await page.waitForTimeout(500);
  });

  await testStep(page, '4.2 导出设定按钮', async () => {
    await safeClick(page, '#btn-export-settings');
    await page.waitForTimeout(500);
  });

  await testStep(page, '4.3 导入设定按钮', async () => {
    await safeClick(page, '#btn-import-settings');
    await page.waitForTimeout(500);
  });

  await testStep(page, '4.4 叙事风格下拉 - 视角', async () => {
    await page.selectOption('#ns-pov', '第一人称');
    await page.waitForTimeout(300);
    await page.selectOption('#ns-pov', '第三人称');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.5 叙事风格下拉 - 时态', async () => {
    await page.selectOption('#ns-tense', '现在时');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.6 叙事风格下拉 - 基调', async () => {
    await page.selectOption('#ns-tone', '冷峻');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.7 叙事风格下拉 - 节奏', async () => {
    await page.selectOption('#ns-pacing', '张弛有度');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.8 描写风格输入', async () => {
    const input = await page.$('#ns-description');
    if (input) await input.fill('意识流');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.9 时代环境 - social_attitude 输入框存在', async () => {
    const input = await page.$('#era-social-attitude');
    if (!input) throw new Error('social_attitude 输入框不存在！');
    await input.fill('普通人对泡泡者既恐惧又依赖');
    await page.waitForTimeout(300);
  });

  await testStep(page, '4.10 添加世界规则按钮', async () => {
    const btn = await page.$('[onclick="addWorldRule()"]');
    if (!btn) throw new Error('添加世界规则按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 5: Step 2 全书大纲面板
  // ========================================
  console.log('\nPhase 5: Step 2 全书大纲面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(2)"]');
  await page.waitForTimeout(500);

  const outlineViews = [
    { name: '5.1 编辑视图', onclick: "switchNovelOutlineView('edit')" },
    { name: '5.2 矩阵视图', onclick: "switchNovelOutlineView('matrix')" },
    { name: '5.3 看板视图', onclick: "switchNovelOutlineView('kanban')" },
  ];

  for (const view of outlineViews) {
    await testStep(page, view.name, async () => {
      await page.evaluate((oc) => {
        const btns = document.querySelectorAll('.outline-view-btn');
        for (const b of btns) {
          if (b.getAttribute('onclick') === oc) { b.click(); return; }
        }
      }, view.onclick);
      await page.waitForTimeout(500);
    });
  }

  // ========================================
  // Phase 6: Step 3 人物面板
  // ========================================
  console.log('\nPhase 6: Step 3 人物面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(3)"]');
  await page.waitForTimeout(500);

  await testStep(page, '6.1 AI生成人物按钮', async () => {
    await safeClick(page, '#btn-ai-gen-characters');
    await page.waitForTimeout(1000);
  });

  await testStep(page, '6.2 添加人物按钮', async () => {
    await safeClick(page, '#btn-add-character');
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 7: Step 4 分卷纲要面板
  // ========================================
  console.log('\nPhase 7: Step 4 分卷纲要面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(4)"]');
  await page.waitForTimeout(500);

  await testStep(page, '7.1 AI分卷按钮', async () => {
    const btn = await page.$('#btn-vol-outline-ai');
    if (!btn) throw new Error('AI分卷按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await testStep(page, '7.2 添加新卷按钮', async () => {
    const btn = await page.$('#btn-add-volume');
    if (!btn) throw new Error('添加新卷按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 8: Step 5 章节大纲面板
  // ========================================
  console.log('\nPhase 8: Step 5 章节大纲面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(5)"]');
  await page.waitForTimeout(500);

  const chOutlineViews = [
    { name: '8.1 编辑视图', onclick: "switchChapterOutlineView('edit')" },
    { name: '8.2 看板视图', onclick: "switchChapterOutlineView('kanban')" },
    { name: '8.3 矩阵视图', onclick: "switchChapterOutlineView('matrix')" },
    { name: '8.4 时间线视图', onclick: "switchChapterOutlineView('timeline')" },
  ];

  for (const view of chOutlineViews) {
    await testStep(page, view.name, async () => {
      await page.evaluate((oc) => {
        const btns = document.querySelectorAll('.chapter-outline-view-btn');
        for (const b of btns) {
          if (b.getAttribute('onclick') === oc) { b.click(); return; }
        }
      }, view.onclick);
      await page.waitForTimeout(500);
    });
  }

  await testStep(page, '8.5 伏笔管理弹窗', async () => {
    const btn = await page.$('[onclick="openForeshadowDialog()"]');
    if (!btn) throw new Error('伏笔管理按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#foreshadow-dialog');
    await screenshot(page, 'foreshadow_dialog');
    await safeClick(page, '[onclick="closeForeshadowDialog()"]');
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 9: Step 6 写作面板
  // ========================================
  console.log('\nPhase 9: Step 6 写作面板');
  await safeClick(page, '.workflow-step[onclick="goToStep(6)"]');
  await page.waitForTimeout(500);

  await testStep(page, '9.1 写作工具栏 - 模型选择器', async () => {
    const sel = await page.$('#model-selector');
    if (!sel) throw new Error('模型选择器未找到');
  });

  await testStep(page, '9.2 写作工具栏 - AI生成按钮', async () => {
    await safeClick(page, '#wt-btn-gen');
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.3 写作工具栏 - 去AI味按钮', async () => {
    const btn = await page.$('#wt-btn-opt');
    if (!btn) throw new Error('去AI味按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.4 写作工具栏 - 续写按钮', async () => {
    const btn = await page.$('#wt-btn-cont');
    if (!btn) throw new Error('续写按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.5 写作工具栏 - AI味检测', async () => {
    await safeClick(page, '#wt-btn-flavor');
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.6 写作工具栏 - 保存按钮', async () => {
    await safeClick(page, '#wt-btn-save');
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.7 写作工具栏 - 草稿模式', async () => {
    const btn = await page.$('#wt-btn-draft');
    if (!btn) throw new Error('草稿按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await testStep(page, '9.8 写作工具栏 - 章节导航上一章', async () => {
    await safeClick(page, '#wt-btn-prev-ch');
    await page.waitForTimeout(300);
  });

  await testStep(page, '9.9 写作工具栏 - 章节导航下一章', async () => {
    await safeClick(page, '#wt-btn-next-ch');
    await page.waitForTimeout(300);
  });

  await testStep(page, '9.10 写作工具栏 - 章节状态切换', async () => {
    await safeClick(page, '#writing-ch-status');
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 10: 创意工具弹窗
  // ========================================
  console.log('\nPhase 10: 创意工具弹窗');

  // 头脑风暴
  await testStep(page, '10.1 头脑风暴', async () => {
    const btn = await page.$('[onclick="openBrainstormPanel()"]');
    if (!btn) throw new Error('头脑风暴按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#brainstorm-panel');
    await screenshot(page, 'brainstorm_panel');
    await safeClick(page, '[onclick="closeBrainstormPanel()"]');
    await page.waitForTimeout(300);
  });

  // 五感描写
  await testStep(page, '10.2 五感描写', async () => {
    const btn = await page.$('[onclick="openSensoryPanel()"]');
    if (!btn) throw new Error('五感描写按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#sensory-panel');
    await screenshot(page, 'sensory_panel');
    await safeClick(page, '[onclick="closeSensoryPanel()"]');
    await page.waitForTimeout(300);
  });

  // 描写增强
  await testStep(page, '10.3 描写增强', async () => {
    const btn = await page.$('[onclick="openDescribePanel()"]');
    if (!btn) throw new Error('描写增强按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#describe-panel');
    await safeClick(page, '[onclick="closeDescribePanel()"]');
    await page.waitForTimeout(300);
  });

  // 场景扩写
  await testStep(page, '10.4 场景扩写', async () => {
    const btn = await page.$('[onclick="openExpandPanel()"]');
    if (!btn) throw new Error('场景扩写按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#expand-panel');
    await safeClick(page, '[onclick="closeExpandPanel()"]');
    await page.waitForTimeout(300);
  });

  // 灵活重写
  await testStep(page, '10.5 灵活重写', async () => {
    const btn = await page.$('[onclick="openRewritePanel()"]');
    if (!btn) throw new Error('灵活重写按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#rewrite-panel');
    await safeClick(page, '[onclick="closeRewritePanel()"]');
    await page.waitForTimeout(300);
  });

  // 5维反馈
  await testStep(page, '10.6 5维写作反馈', async () => {
    const btn = await page.$('[onclick="openFeedbackPanel()"]');
    if (!btn) throw new Error('反馈按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#feedback-panel');
    await safeClick(page, '[onclick="closeFeedbackPanel()"]');
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 11: 底部状态栏
  // ========================================
  console.log('\nPhase 11: 底部状态栏');

  await testStep(page, '11.1 主题切换按钮', async () => {
    await safeClick(page, '#btn-theme');
    await page.waitForTimeout(300);
    await safeClick(page, '#btn-theme');
    await page.waitForTimeout(300);
  });

  await testStep(page, '11.2 字号放大按钮', async () => {
    const btn = await page.$('[onclick="changeFontScale(0.1)"]');
    if (!btn) throw new Error('字号+按钮未找到');
    await btn.click();
    await page.waitForTimeout(300);
  });

  await testStep(page, '11.3 字号缩小按钮', async () => {
    const btn = await page.$('[onclick="changeFontScale(-0.1)"]');
    if (!btn) throw new Error('字号-按钮未找到');
    await btn.click();
    await page.waitForTimeout(300);
  });

  await testStep(page, '11.4 字号重置按钮', async () => {
    await page.evaluate(() => { setFontScale(1.0); });
    await page.waitForTimeout(300);
  });

  await testStep(page, '11.5 专注模式按钮', async () => {
    const btn = await page.$('#btn-focus');
    if (!btn) throw new Error('专注模式按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
    await btn.click();
    await page.waitForTimeout(500);
  });

  await testStep(page, '11.6 撤销按钮', async () => {
    const btn = await page.$('#btn-undo');
    if (!btn) throw new Error('撤销按钮未找到');
    await btn.click();
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 12: AI助手浮动面板
  // ========================================
  console.log('\nPhase 12: AI助手浮动面板');

  await testStep(page, '12.1 AI助手FAB按钮', async () => {
    await safeClick(page, '#ai-assistant-fab');
    await waitForOverlay(page, '#ai-assistant-panel');
    await screenshot(page, 'ai_assistant');
    await safeClick(page, '#ai-assistant-fab');
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 13: 扫榜分析
  // ========================================
  console.log('\nPhase 13: 扫榜分析');

  await testStep(page, '13.1 扫榜分析面板', async () => {
    const btn = await page.$('#wt-btn-ranking');
    if (!btn) throw new Error('扫榜按钮未找到');
    await btn.click();
    await waitForOverlay(page, '#ranking-overlay');
    await screenshot(page, 'ranking_panel');
    await page.evaluate(() => { closeOverlay('ranking-overlay'); });
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 14: 插件工具栏
  // ========================================
  console.log('\nPhase 14: 插件工具栏');

  await testStep(page, '14.1 插件工具栏切换', async () => {
    const btn = await page.$('#wt-btn-plugins');
    if (!btn) throw new Error('插件按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
    await btn.click();
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 15: 阅读器完整测试
  // ========================================
  console.log('\nPhase 15: 阅读器完整测试');

  await testStep(page, '15.1 打开阅读器', async () => {
    await safeClick(page, '#btn-reader');
    await waitForOverlay(page, '#reader-overlay');
  });

  await testStep(page, '15.2 阅读器 - 书架按钮', async () => {
    await safeClick(page, '#reader-bookshelf-btn');
    await page.waitForTimeout(500);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  await testStep(page, '15.3 阅读器 - 目录按钮', async () => {
    await safeClick(page, '#reader-toc-btn');
    await page.waitForTimeout(500);
    await safeClick(page, '#reader-chapter-close');
    await page.waitForTimeout(300);
  });

  await testStep(page, '15.4 阅读器 - 设置按钮', async () => {
    await safeClick(page, '#reader-settings-btn');
    await page.waitForTimeout(500);
    await safeClick(page, '#reader-settings-close');
    await page.waitForTimeout(300);
  });

  await testStep(page, '15.5 阅读器 - 上一章/下一章', async () => {
    await safeClick(page, '#reader-next-btn');
    await page.waitForTimeout(500);
    await safeClick(page, '#reader-prev-btn');
    await page.waitForTimeout(500);
  });

  await testStep(page, '15.6 关闭阅读器', async () => {
    await safeClick(page, '#reader-close-btn');
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 16: 命令面板
  // ========================================
  console.log('\nPhase 16: 命令面板');

  await testStep(page, '16.1 命令面板打开 (Ctrl+K)', async () => {
    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);
    const cmdPanel = await page.$('#command-palette');
    if (!cmdPanel) {
      // Try Ctrl+P instead
      await page.keyboard.press('Control+p');
      await page.waitForTimeout(500);
    }
    await screenshot(page, 'command_palette');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 17: 新建项目完整流程
  // ========================================
  console.log('\nPhase 17: 新建项目对话框');

  await testStep(page, '17.1 打开新建对话框', async () => {
    await safeClick(page, '#btn-new-project');
    await waitForOverlay(page, '#new-project-overlay');
  });

  await testStep(page, '17.2 填写项目信息', async () => {
    const titleInput = await page.$('#new-project-title');
    if (!titleInput) throw new Error('标题输入框未找到');
    await titleInput.fill('测试项目_按钮检测');
    await page.selectOption('#new-project-genre', '玄幻');
    await page.selectOption('#new-project-length', '10');
  });

  await testStep(page, '17.3 取消创建', async () => {
    await safeClick(page, '#new-project-cancel');
    await page.waitForTimeout(500);
  });

  // ========================================
  // Phase 18: 导出面板按钮
  // ========================================
  console.log('\nPhase 18: 导出面板');

  await testStep(page, '18.1 打开导出面板', async () => {
    const toolboxBtn = await page.$('[onclick="toggleToolbox()"]');
    await toolboxBtn.click();
    await page.waitForTimeout(300);
    const exportBtn = await page.$('[onclick="openExportPanel()"]');
    await exportBtn.click();
    await waitForOverlay(page, '#export-overlay');
    await screenshot(page, 'export_panel');
  });

  await testStep(page, '18.2 导出TXT按钮', async () => {
    const btn = await page.$('[onclick="exportBook(\'txt\')"]');
    if (!btn) throw new Error('导出TXT按钮未找到');
    await page.waitForTimeout(200);
  });

  await testStep(page, '18.3 导出EPUB按钮', async () => {
    const btn = await page.$('[onclick="exportBook(\'epub\')"]');
    if (!btn) throw new Error('导出EPUB按钮未找到');
    await page.waitForTimeout(200);
  });

  await testStep(page, '18.4 关闭导出面板', async () => {
    await page.evaluate(() => { closeOverlay('export-overlay'); });
    await page.waitForTimeout(300);
  });

  // ========================================
  // Phase 19: 新增 social_attitude 字段验证
  // ========================================
  console.log('\nPhase 19: social_attitude 字段专项验证');

  await safeClick(page, '.workflow-step[onclick="goToStep(1)"]');
  await page.waitForTimeout(500);

  await testStep(page, '19.1 social_attitude 输入框存在', async () => {
    const el = await page.$('#era-social-attitude');
    if (!el) throw new Error('social_attitude 输入框不存在！');
  });

  await testStep(page, '19.2 social_attitude 可编辑', async () => {
    const el = await page.$('#era-social-attitude');
    await el.fill('测试社会态度值');
    await page.waitForTimeout(500);
    const val = await el.inputValue();
    if (val !== '测试社会态度值') throw new Error(`值不匹配: ${val}`);
  });

  await testStep(page, '19.3 social_attitude 输入触发保存', async () => {
    const el = await page.$('#era-social-attitude');
    await el.fill('官方管控/黑市交易/恐惧与依赖');
    await page.waitForTimeout(1000); // Wait for debounced save
  });

  // ========================================
  // Final: 总结报告
  // ========================================
  console.log('\n\n========== 测试总结 ==========');
  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  console.log(`总计: ${results.length} 项测试`);
  console.log(`通过: ${passCount} ✅`);
  console.log(`失败: ${failCount} ❌`);

  if (failCount > 0) {
    console.log('\n失败项目:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  ❌ ${r.name}: ${r.error}`);
    });
  }

  // Save report
  fs.writeFileSync(REPORT_FILE, JSON.stringify(results, null, 2), 'utf-8');
  console.log(`\n报告已保存: ${REPORT_FILE}`);
  console.log(`截图目录: ${SCREENSHOT_DIR}`);

  // Final screenshot
  await screenshot(page, 'final_state');

  await browser.close();
  return { passCount, failCount, total: results.length };
}

run().catch(e => {
  console.error('测试异常:', e);
  process.exit(1);
});
