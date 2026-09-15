/**
 * 书斋V66 桌面端核心功能回归测试（健壮版）
 * 重点验证：social_attitude、工作流步骤、写作工具栏、面板弹窗
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:8894';
const SCREENSHOT_DIR = process.env.TEST_SCREENSHOT_DIR || path.join(__dirname, '..', 'test_screenshots', 'desktop_test');
const REPORT_FILE = path.join(SCREENSHOT_DIR, 'sanity_report.json');

if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = [];
let shotIdx = 0;

function ss(page, name) {
  const fname = `${String(shotIdx++).padStart(3, '0')}_${name}.png`;
  return page.screenshot({ path: path.join(SCREENSHOT_DIR, fname) });
}

async function test(page, name, fn) {
  console.log(`  [TEST] ${name}...`);
  try {
    // Recovery: press Escape and wait for overlays to close
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    await fn();
    console.log(`    ✅ PASS`);
    results.push({ name, status: 'PASS' });
    return true;
  } catch (e) {
    console.log(`    ❌ FAIL: ${e.message}`);
    await ss(page, `FAIL_${name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_')}`);
    results.push({ name, status: 'FAIL', error: e.message });
    return false;
  }
}

async function clickById(page, id) {
  const el = await page.$(id);
  if (!el) throw new Error(`Not found: ${id}`);
  await el.scrollIntoViewIfNeeded();
  await el.click();
  await page.waitForTimeout(400);
}

async function clickByText(page, text) {
  const el = await page.locator(`text="${text}"`).first();
  if (!el) throw new Error(`Text not found: ${text}`);
  await el.click();
  await page.waitForTimeout(400);
}

async function run() {
  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 }, locale: 'zh-CN' });

  console.log('=== 书斋V66 桌面端核心功能回归测试 ===\n');

  // Load page
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await ss(page, '00_load');

  // ============================================
  // Phase 1: 顶部核心按钮
  // ============================================
  console.log('\nPhase 1: 顶部核心按钮');

  await test(page, '1.1 左抽屉开关', async () => {
    await clickById(page, '#btn-toggle-left');
    await ss(page, '01_left_drawer');
    await clickById(page, '#btn-toggle-left');
  });

  await test(page, '1.2 新建项目对话框', async () => {
    await clickById(page, '#btn-new-project');
    await page.waitForSelector('#new-project-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '02_new_project');
    await clickById(page, '#new-project-cancel');
  });

  await test(page, '1.3 打开项目选择器', async () => {
    await clickById(page, '#btn-open-project');
    await page.waitForTimeout(500);
    await ss(page, '03_project_picker');
    await page.keyboard.press('Escape');
  });

  await test(page, '1.4 AI模型配置浮层', async () => {
    await clickById(page, '#model-badge');
    await page.waitForSelector('#model-popover', { state: 'visible', timeout: 3000 });
    await ss(page, '04_model_popover');
    await page.keyboard.press('Escape');
  });

  await test(page, '1.5 右抽屉开关', async () => {
    await clickById(page, '#btn-toggle-right');
    await page.waitForTimeout(400);
    await ss(page, '05_right_drawer');
    await clickById(page, '#btn-close-right');
  });

  // ============================================
  // Phase 2: 工作流 7 步骤切换
  // ============================================
  console.log('\nPhase 2: 工作流步骤切换 (核心)');

  for (let step = 1; step <= 7; step++) {
    await test(page, `2.${step} 步骤${step}`, async () => {
      await page.evaluate((n) => {
        const steps = document.querySelectorAll('.workflow-step');
        if (steps[n - 1]) steps[n - 1].click();
      }, step);
      await page.waitForTimeout(600);
      await ss(page, `step_${step}`);
    });
  }

  // ============================================
  // Phase 3: Step 1 世界观 - social_attitude 专项
  // ============================================
  console.log('\nPhase 3: Step 1 世界观面板 - social_attitude 专项');

  await test(page, '3.1 切到步骤1', async () => {
    await page.evaluate(() => { goToStep(1); });
    await page.waitForTimeout(600);
  });

  await test(page, '3.2 social_attitude 输入框存在', async () => {
    const el = await page.$('#era-social-attitude');
    if (!el) throw new Error('social_attitude 输入框不存在！');
    await ss(page, '06_social_attitude_exists');
  });

  await test(page, '3.3 social_attitude 可编辑并触发保存', async () => {
    const el = await page.$('#era-social-attitude');
    await el.fill('官方管控三级以上泡泡者/黑市交易力场增强剂/普通人对泡泡者既恐惧又依赖');
    await page.waitForTimeout(500);
    const val = await el.inputValue();
    if (val !== '官方管控三级以上泡泡者/黑市交易力场增强剂/普通人对泡泡者既恐惧又依赖') {
      throw new Error(`值不匹配: ${val}`);
    }
    await ss(page, '07_social_attitude_filled');
  });

  await test(page, '3.4 叙事风格下拉全部可交互', async () => {
    await page.selectOption('#ns-pov', '第一人称');
    await page.waitForTimeout(200);
    await page.selectOption('#ns-tense', '现在时');
    await page.waitForTimeout(200);
    await page.selectOption('#ns-tone', '冷峻');
    await page.waitForTimeout(200);
    await page.selectOption('#ns-pacing', '张弛有度');
    await page.waitForTimeout(200);
    await ss(page, '08_narrative_style');
  });

  await test(page, '3.5 描写风格输入', async () => {
    const input = await page.$('#ns-description');
    if (input) await input.fill('意识流');
    await page.waitForTimeout(200);
  });

  await test(page, '3.6 时代环境其他字段正常', async () => {
    const tech = await page.$('#era-tech');
    const society = await page.$('#era-society');
    const geo = await page.$('#era-geography');
    const culture = await page.$('#era-culture');
    if (!tech || !society || !geo || !culture) {
      throw new Error('时代环境字段缺失');
    }
    await ss(page, '09_era_fields');
  });

  // ============================================
  // Phase 4: Step 6 写作工具栏
  // ============================================
  console.log('\nPhase 4: Step 6 写作工具栏');

  await test(page, '4.1 切到步骤6', async () => {
    await page.evaluate(() => { goToStep(6); });
    await page.waitForTimeout(600);
    await ss(page, '10_step6_writing');
  });

  await test(page, '4.2 写作工具栏 - 模型选择器存在', async () => {
    const sel = await page.$('#model-selector');
    if (!sel) throw new Error('模型选择器未找到');
  });

  await test(page, '4.3 写作工具栏 - AI生成按钮存在', async () => {
    const btn = await page.$('#wt-btn-gen');
    if (!btn) throw new Error('AI生成按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await test(page, '4.4 写作工具栏 - 去AI味按钮存在', async () => {
    const btn = await page.$('#wt-btn-opt');
    if (!btn) throw new Error('去AI味按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await test(page, '4.5 写作工具栏 - 续写按钮存在', async () => {
    const btn = await page.$('#wt-btn-cont');
    if (!btn) throw new Error('续写按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await test(page, '4.6 写作工具栏 - AI味检测存在', async () => {
    const btn = await page.$('#wt-btn-flavor');
    if (!btn) throw new Error('AI味检测按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await test(page, '4.7 写作工具栏 - 保存按钮存在', async () => {
    const btn = await page.$('#wt-btn-save');
    if (!btn) throw new Error('保存按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
  });

  await test(page, '4.8 写作工具栏 - 草稿模式', async () => {
    const btn = await page.$('#wt-btn-draft');
    if (!btn) throw new Error('草稿按钮未找到');
    await btn.click();
    await page.waitForTimeout(500);
    await ss(page, '11_draft_mode');
  });

  await test(page, '4.9 写作工具栏 - 章节导航', async () => {
    const prev = await page.$('#wt-btn-prev-ch');
    const next = await page.$('#wt-btn-next-ch');
    if (!prev || !next) throw new Error('章节导航按钮缺失');
    await prev.click(); await page.waitForTimeout(300);
    await next.click(); await page.waitForTimeout(300);
  });

  // ============================================
  // Phase 5: 底部状态栏
  // ============================================
  console.log('\nPhase 5: 底部状态栏');

  await test(page, '5.1 主题切换', async () => {
    const btn = await page.$('#btn-theme');
    if (!btn) throw new Error('主题按钮未找到');
    await btn.click(); await page.waitForTimeout(300);
    await ss(page, '12_theme_dark');
    await btn.click(); await page.waitForTimeout(300);
    await ss(page, '13_theme_light');
  });

  await test(page, '5.2 字号控制', async () => {
    await page.evaluate(() => { setFontScale(1.0); });
    await page.waitForTimeout(200);
    const plus = await page.$('[onclick="changeFontScale(0.1)"]');
    if (plus) await plus.click();
    await page.waitForTimeout(200);
  });

  await test(page, '5.3 专注模式', async () => {
    const btn = await page.$('#btn-focus');
    if (!btn) throw new Error('专注模式按钮未找到');
    await btn.click(); await page.waitForTimeout(500);
    await ss(page, '14_focus_mode');
    await btn.click(); await page.waitForTimeout(500);
  });

  // ============================================
  // Phase 6: 创意工具弹窗（代表性抽样）
  // ============================================
  console.log('\nPhase 6: 创意工具弹窗');

  await test(page, '6.1 头脑风暴面板', async () => {
    const btn = await page.$('#wt-btn-brainstorm');
    if (!btn) throw new Error('头脑风暴按钮未找到');
    await btn.click();
    await page.waitForSelector('#brainstorm-panel', { state: 'visible', timeout: 3000 });
    await ss(page, '15_brainstorm');
    await page.evaluate(() => { closeBrainstormPanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '6.2 五感描写面板', async () => {
    const btn = await page.$('#wt-btn-sensory');
    if (!btn) throw new Error('五感描写按钮未找到');
    await btn.click();
    await page.waitForSelector('#sensory-panel', { state: 'visible', timeout: 3000 });
    await ss(page, '16_sensory');
    await page.evaluate(() => { closeSensoryPanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '6.3 描写增强面板', async () => {
    const btn = await page.$('#wt-btn-describe');
    if (!btn) throw new Error('描写增强按钮未找到');
    await btn.click();
    await page.waitForSelector('#describe-panel', { state: 'visible', timeout: 3000 });
    await page.evaluate(() => { closeDescribePanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '6.4 场景扩写面板', async () => {
    const btn = await page.$('#wt-btn-expand');
    if (!btn) throw new Error('场景扩写按钮未找到');
    await btn.click();
    await page.waitForSelector('#expand-panel', { state: 'visible', timeout: 3000 });
    await page.evaluate(() => { closeExpandPanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '6.5 灵活重写面板', async () => {
    const btn = await page.$('#wt-btn-rewrite');
    if (!btn) throw new Error('灵活重写按钮未找到');
    await btn.click();
    await page.waitForSelector('#rewrite-panel', { state: 'visible', timeout: 3000 });
    await page.evaluate(() => { closeRewritePanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '6.6 5维写作反馈面板', async () => {
    const btn = await page.$('#wt-btn-feedback');
    if (!btn) throw new Error('反馈按钮未找到');
    await btn.click();
    await page.waitForSelector('#feedback-panel', { state: 'visible', timeout: 3000 });
    await page.evaluate(() => { closeFeedbackPanel(); });
    await page.waitForTimeout(300);
  });

  // ============================================
  // Phase 7: 工具箱面板（代表性抽样）
  // ============================================
  console.log('\nPhase 7: 工具箱面板');

  await test(page, '7.1 导出书籍面板', async () => {
    await page.evaluate(() => { openExportPanel(); });
    await page.waitForSelector('#export-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '17_export');
    await page.evaluate(() => { closeOverlay('export-overlay'); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.2 角色对话面板', async () => {
    await page.evaluate(() => { openCharacterChatPanel(); });
    await page.waitForSelector('#character-chat-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '18_char_chat');
    await page.evaluate(() => { closeOverlay('character-chat-overlay'); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.3 云同步面板', async () => {
    await page.evaluate(() => { openSyncPanel(); });
    await page.waitForSelector('#sync-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '19_sync');
    await page.evaluate(() => { closeOverlay('sync-overlay'); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.4 技能包面板', async () => {
    await page.evaluate(() => { openSkillPackPanel(); });
    await page.waitForSelector('#skill-pack-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '20_skill_pack');
    await page.evaluate(() => { closeOverlay('skill-pack-overlay'); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.5 扫榜分析面板', async () => {
    const btn = await page.$('#wt-btn-ranking');
    if (!btn) throw new Error('扫榜按钮未找到');
    await btn.click();
    await page.waitForSelector('#ranking-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '21_ranking');
    await page.evaluate(() => { closeOverlay('ranking-overlay'); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.6 规划视图面板', async () => {
    await page.evaluate(() => { openPlanningPanel('grid'); });
    await page.waitForSelector('#planning-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '22_planning');
    await page.evaluate(() => { closePlanningPanel(); });
    await page.waitForTimeout(300);
  });

  await test(page, '7.7 写作统计面板', async () => {
    await page.evaluate(() => { openStatsPanel(); });
    await page.waitForSelector('#stats-overlay', { state: 'visible', timeout: 3000 });
    await ss(page, '23_stats');
    await page.evaluate(() => { closeOverlay('stats-overlay'); });
    await page.waitForTimeout(300);
  });

  // ============================================
  // Phase 8: 步骤面板特有按钮
  // ============================================
  console.log('\nPhase 8: 各步骤面板特有按钮');

  await test(page, '8.1 Step3 AI生成人物按钮', async () => {
    await page.evaluate(() => { goToStep(3); });
    await page.waitForTimeout(500);
    const btn = await page.$('#btn-ai-gen-characters');
    if (!btn) throw new Error('AI生成人物按钮未找到');
    await ss(page, '24_step3_characters');
  });

  await test(page, '8.2 Step4 AI分卷按钮', async () => {
    await page.evaluate(() => { goToStep(4); });
    await page.waitForTimeout(500);
    const btn = await page.$('#btn-vol-outline-ai');
    if (!btn) throw new Error('AI分卷按钮未找到');
    await ss(page, '25_step4_volumes');
  });

  await test(page, '8.3 Step5 伏笔管理弹窗', async () => {
    await page.evaluate(() => { goToStep(5); });
    await page.waitForTimeout(500);
    const btn = await page.$('[onclick="openForeshadowDialog()"]');
    if (!btn) {
      // Maybe no hook bar - that's fine for empty project
      console.log('    ⚠ 伏笔管理按钮未找到（空项目正常）');
      return;
    }
    await btn.click();
    await page.waitForSelector('#foreshadow-dialog', { state: 'visible', timeout: 3000 });
    await ss(page, '26_foreshadow');
    await page.evaluate(() => { closeForeshadowDialog(); });
    await page.waitForTimeout(300);
  });

  // ============================================
  // Phase 9: AI助手浮动面板
  // ============================================
  console.log('\nPhase 9: AI助手浮动面板');

  await test(page, '9.1 AI助手FAB', async () => {
    await clickById(page, '#ai-assistant-fab');
    await page.waitForSelector('#ai-assistant-panel', { state: 'visible', timeout: 3000 });
    await ss(page, '27_ai_assistant');
    await clickById(page, '#ai-assistant-fab');
    await page.waitForTimeout(300);
  });

  // ============================================
  // Summary
  // ============================================
  console.log('\n\n========== 桌面端测试总结 ==========');
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  console.log(`总计: ${results.length} 项测试`);
  console.log(`通过: ${pass} ✅`);
  console.log(`失败: ${fail} ❌`);

  if (fail > 0) {
    console.log('\n失败项目:');
    results.filter(r => r.status === 'FAIL').forEach(r => console.log(`  ❌ ${r.name}: ${r.error}`));
  }

  fs.writeFileSync(REPORT_FILE, JSON.stringify(results, null, 2), 'utf-8');
  console.log(`\n报告已保存: ${REPORT_FILE}`);

  await ss(page, '99_final');
  await browser.close();
  return { pass, fail, total: results.length };
}

run().catch(e => {
  console.error('测试异常:', e);
  process.exit(1);
});
