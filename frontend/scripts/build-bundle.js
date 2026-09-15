#!/usr/bin/env node
// -*- coding: utf-8 -*-
/**
 * 书斋V66 前端构建脚本
 * 将所有 JS 源文件按依赖顺序拼接成 bundle.js
 *
 * 用法:
 *   node scripts/build-bundle.js          # 构建 bundle.js
 *   node scripts/build-bundle.js --watch  # 监听变化自动重建
 *   node scripts/build-bundle.js --minify # 构建 + 简单压缩（去除注释/空行）
 */

const fs = require('fs');
const path = require('path');
const { syncAPK } = require('./sync-apk.js');

const ROOT = path.resolve(__dirname, '..');
const JS_DIR = path.join(ROOT, 'js');
const BUNDLE_OUT = path.join(JS_DIR, 'bundle.js');

// JS 文件拼接顺序（按依赖关系排列）
const FILE_ORDER = [
  // ── 步骤常量（必须最先加载） ──
  'js/step-constants.js',

  // ── 基础层 ──
  'js/localdb.js',
  'js/audit-js.js',
  'js/audit-dimensions.js',

  // ── 共享层 ──
  'js/shared/ai-common.js',

  // ── 组件层（可复用 UI 组件）──
  'js/components/comp-toast.js',
  'js/components/comp-modal.js',
  'js/components/comp-card.js',
  'js/components/comp-form.js',

  // ── 核心服务 ──
  'js/ai-engine.js',
  'js/state.js',
  'js/offline-db.js',
  'js/offline-ai.js',
  'js/offline-api.js',
  'js/skill-data.js',
  'js/skill-core.js',

  // ── API 桥接 ──
  'js/api.js',
  'js/utils/json-parser.js',
  'js/utils/virtual-list.js',

  // ── 功能模块 ──
  'js/modules/init.js',
  'js/modules/wizard.js',
  'js/modules/editor.js',
  'js/modules/settings.js',
  'js/modules/timeline.js',
  'js/modules/validate-ui.js',
  'js/modules/val-actions.js',
  'js/modules/val-render.js',
  'js/modules/check-panel.js',
  'js/modules/toolbox.js',
  'js/modules/creative-tools.js',
  'js/modules/ai-analysis.js',
  'js/modules/ai-assistant.js',
  'js/modules/memory-panel.js',
  'js/modules/planning-view.js',
  'js/modules/wireframe-canvas.js',
  'js/modules/white-city-editor.js',
  'js/modules/ranking-panel.js',
  'js/modules/draft-ui.js',
  'js/modules/distill.js',
  'js/modules/commands.js',
  'js/modules/operation-context.js',
  'js/modules/mobile.js',

  // ── 应用入口 ──
  'js/app.js',

  // ── 阅读器 ──
  'js/reader.js',

  // ── 主题 ──
  'js/theme-init.js',

  // ── 页面胶水层（从 index.html 提取的 inline 函数） ──
  // ── 页面胶水层（从 inline-glue.js 拆分） ──
  'js/glue-core.js',
  'js/glue-dom.js',
  'js/glue-modal.js',
  'js/glue-sidebar.js',
  'js/glue-editor.js',
  'js/glue-outline.js',
  'js/glue-chapter.js',
  'js/glue-research.js',
  'js/glue-ai.js',
  'js/glue-stats.js',
  'js/glue-export.js',
  'js/glue-diff.js',
  'js/glue-settings.js',
  'js/glue-init.js',
  'js/glue-xtra.js',
];

function buildBundle(minify = false) {
  console.log('书斋V66 前端构建开始...');
  const parts = [];

  for (const relPath of FILE_ORDER) {
    const absPath = path.join(ROOT, relPath);
    if (!fs.existsSync(absPath)) {
      console.warn(`  ⚠ 文件不存在: ${relPath}，跳过`);
      continue;
    }
    let content = fs.readFileSync(absPath, 'utf-8');
    // 去除 BOM
    if (content.charCodeAt(0) === 0xFEFF) {
      content = content.slice(1);
    }
    parts.push(`// ── ${relPath} ──\n${content}`);
  }

  let output = `// 书斋V66 前端 Bundle (自动生成)\n// 构建时间: ${new Date().toISOString()}\n// 文件数: ${FILE_ORDER.length}\n\n` + parts.join('\n\n');
  if (minify) {
    // 简单压缩：移除多行注释和连续空行（保留单行注释以确保逻辑正确）
    output = output
      .replace(/\/\*[\s\S]*?\*\//g, '')         // 多行注释
      .replace(/\n{3,}/g, '\n\n');              // 连续3+空行变2行
    console.log('  已简单压缩（移除多行注释/空行）');
  }

  fs.writeFileSync(BUNDLE_OUT, output, 'utf-8');
  const sizeKB = (Buffer.byteLength(output, 'utf-8') / 1024).toFixed(1);
  console.log(`✅ bundle.js 构建完成: ${sizeKB} KB, ${FILE_ORDER.length} 个文件`);

  // 自动同步到 APK assets
  syncAPK();
}

// ── 拼接完整产物（时间戳用占位符，供 --check 归一化比较） ──
function renderBody() {
  const parts = [];
  for (const relPath of FILE_ORDER) {
    const absPath = path.join(ROOT, relPath);
    if (!fs.existsSync(absPath)) continue;
    let content = fs.readFileSync(absPath, 'utf-8');
    if (content.charCodeAt(0) === 0xFEFF) content = content.slice(1);
    parts.push(`// ── ${relPath} ──\n${content}`);
  }
  return `// 书斋V66 前端 Bundle (自动生成)\n// 构建时间: <占位>\n// 文件数: ${FILE_ORDER.length}\n\n` + parts.join('\n\n');
}

// 归一化：统一行尾并去掉时间戳行，只比正文
const normalize = s => s.replace(/\r\n/g, '\n').split('\n')
  .filter(l => !l.startsWith('// 构建时间')).join('\n');

// ── --check 模式：检测 bundle.js 与源文件是否漂移（漂移时退出码 1） ──
function checkDrift() {
  if (!fs.existsSync(BUNDLE_OUT)) {
    console.error('❌ bundle.js 不存在，请先运行 npm run build');
    process.exit(1);
  }
  const expected = normalize(renderBody());
  const actual = normalize(fs.readFileSync(BUNDLE_OUT, 'utf-8'));
  if (expected === actual) {
    console.log('✅ bundle.js 与源文件一致');
    return;
  }
  console.error('❌ bundle.js 与源文件漂移：改源文件后请运行 npm run build 重建；');
  console.error('   若漂移来自手改 bundle.js，请把改动回移到对应 js/ 源文件后重建。');
  process.exit(1);
}

// ── Watch 模式 ──
if (process.argv.includes('--check')) {
  checkDrift();
} else if (process.argv.includes('--watch')) {
  console.log('监听模式启动，修改 JS 文件后自动重建...');
  buildBundle();

  const watchers = [];
  for (const relPath of FILE_ORDER) {
    const absPath = path.join(ROOT, relPath);
    if (fs.existsSync(absPath)) {
      fs.watch(absPath, { persistent: true }, (eventType) => {
        if (eventType === 'change') {
          console.log(`文件变化: ${relPath}`);
          buildBundle();
        }
      });
      watchers.push(absPath);
    }
  }
  console.log(`  监听 ${watchers.length} 个文件`);

  // 监听新增文件
  const moduleDir = path.join(ROOT, 'js', 'modules');
  const utilsDir = path.join(ROOT, 'js', 'utils');
  [moduleDir, utilsDir].forEach(dir => {
    if (fs.existsSync(dir)) {
      fs.watch(dir, { persistent: true }, (eventType, filename) => {
        if (eventType === 'rename' && filename && filename.endsWith('.js')) {
          console.log(`新文件: ${filename}，重建 bundle...`);
          buildBundle();
        }
      });
    }
  });

  process.on('SIGINT', () => {
    console.log('\n监听模式停止');
    process.exit(0);
  });
} else {
  const minify = process.argv.includes('--minify');
  buildBundle(minify);
}
