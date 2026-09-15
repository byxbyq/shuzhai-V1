#!/usr/bin/env node
// -*- coding: utf-8 -*-
/**
 * 书斋V66 APK 同步脚本
 * 将 frontend/ 的产物（index.html + bundle.js）同步到 APK 内嵌 assets 目录。
 *
 * 用法:
 *   node scripts/sync-apk.js             # 同步
 *   node build-bundle.js                 # 构建后自动同步（已集成）
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const APK_PUBLIC = path.join(ROOT, '..', 'apk', 'android', 'app', 'src', 'main', 'assets', 'public');

// 同步清单：源路径（相对于 ROOT） → 目标路径（相对于 APK_PUBLIC）
const SYNC_MAP = [
  { src: path.join(ROOT, 'index.html'),        dst: path.join(APK_PUBLIC, 'index.html') },
  { src: path.join(ROOT, 'js', 'bundle.js'),    dst: path.join(APK_PUBLIC, 'js', 'bundle.js') },
];

/**
 * 确保目录存在
 */
function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * 同步文件到 APK assets
 */
function syncAPK() {
  console.log('── APK 同步开始 ──');

  // 确保 APK_PUBLIC 目录存在
  ensureDir(APK_PUBLIC);

  const results = [];
  let allOK = true;

  for (const { src, dst } of SYNC_MAP) {
    // 确保目标目录存在
    ensureDir(path.dirname(dst));

    // 检查源文件
    if (!fs.existsSync(src)) {
      console.error(`  ❌ 源文件不存在: ${path.relative(ROOT, src)}`);
      allOK = false;
      continue;
    }

    // 复制
    try {
      const content = fs.readFileSync(src);
      fs.writeFileSync(dst, content);
      const sizeKB = (content.length / 1024).toFixed(1);
      const relSrc = path.relative(ROOT, src);
      const relDst = path.relative(ROOT, dst);
      results.push({ relSrc, relDst, sizeKB });
    } catch (err) {
      console.error(`  ❌ 同步失败: ${path.relative(ROOT, src)} → ${path.relative(ROOT, dst)}`);
      console.error(`     ${err.message}`);
      allOK = false;
    }
  }

  // 打印结果
  if (results.length > 0) {
    console.log(`  已同步 ${results.length} 个文件:`);
    for (const { relSrc, relDst, sizeKB } of results) {
      console.log(`    ${relSrc} (${sizeKB} KB) → ${relDst}`);
    }
    console.log('✅ APK 同步完成');
  }

  return allOK;
}

// 直接执行
if (require.main === module) {
  const ok = syncAPK();
  process.exit(ok ? 0 : 1);
}

module.exports = { syncAPK, APK_PUBLIC, SYNC_MAP };
