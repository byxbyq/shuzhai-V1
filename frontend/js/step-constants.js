// step-constants.js — 工作流步骤常量（唯一真相源）
// 所有模块通过 STEPS.xxx 引用步号，硬编码 goToStep(N) 已消除
// 调整步骤顺序时只需修改此文件中的数值
(function(global) {
  'use strict';

  var S = {
    世界观:     1,
    人物:       2,
    全书大纲:   3,
    分卷:       4,
    章节大纲:   5,
    连线框:     6,
    写作:       7,
    时间线:     8,
    草稿定稿:   9
  };

  // 反向映射（步号→名称），方便日志和 toast 用
  S._nameOf = {};
  Object.keys(S).forEach(function(k) {
    if (k.charAt(0) !== '_') S._nameOf[S[k]] = k;
  });

  global.STEPS = S;

})(window);
