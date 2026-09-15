# 书斋 V66 前端重构 — AI 执行规划

> 工作目录：`<项目根>/`（原始项目 `<源项目>/` 的完整副本）
> 目标：UI 视觉精致度 + 流畅度/稳定性，不换框架，保留 vanilla JS

---

## 一、AI 修改的可行性与风险评估

### AI 能做什么（高可行性 ✅）

| 任务 | AI可行性 | 原因 |
|------|----------|------|
| 清理 inline style → CSS class | ✅✅✅ 极高 | 机械替换，pattern 可自动提取 |
| 建立 components.css 组件库 | ✅✅✅ 极高 | 纯 CSS 编写，无逻辑风险 |
| CSS 变量体系补充（间距/阴影/字号） | ✅✅✅ 极高 | 只加变量，不改现有 |
| 视觉微调（间距统一/圆角/动效） | ✅✅ 中高 | 需逐文件调整，量大但机械 |
| 加 Vite 打包 | ✅✅ 中高 | 配置文件 + main.js 入口，但调试全局变量依赖需谨慎 |
| 拆分大 JS 文件 | ✅ 中等 | 需分析全局变量依赖关系，拆分后要保证所有 `window.xxx` 挂载正确 |
| HTML 拆分成 fragments | ✅ 中等 | fetch 加载片段，但要保证 JS 事件绑定不受影响 |
| innerHTML → textContent 替换 | ✅✅ 中高 | 机械替换，但需判断哪些是真的纯文本场景 |

### AI 不太擅长的（需人审 ⚠️）

| 任务 | 风险 | 原因 |
|------|------|------|
| 视觉"质感"打磨 | ⚠️ 中 | AI 不擅长判断"好不好看"，间距/阴影数值需要人眼验证 |
| 空状态设计 | ⚠️ 中 | 需要设计感觉，AI 可以写代码但布局/文案需要人审 |
| Vite 全局变量依赖解决 | ⚠️ 中高 | 42 个 JS 文件全是全局变量互相引用，Vite 的 ES module 模式可能打断依赖链 |
| 虚拟滚动实现 | ⚠️ 中 | 逻辑不复杂但需处理各种边界（异步加载、选中状态、滚动位置保持） |

### 核心难点：全局变量依赖网

当前 42 个 JS 文件通过全局变量互相通信：

```
state.js → 定义 window.state / currentChapterIndex 等
api.js → 使用 window.state / 定义 window.api
editor.js → 使用 window.api / window.currentChapterIndex
validate-ui.js → 使用 window.api / window.state / window.DraftManager
...
```

**Vite 的 ES module 模式会打断这个依赖链**——每个文件变成独立 module，`window.xxx` 不再自动共享。

**解决方案（两种路线）**：

#### 路线 A：Vite + 保留全局挂载（推荐 ✅）

每个 JS 文件末尾保持 `window.XxxModule = XxxModule`，Vite 只是做打包压缩，不做模块化改造：

```javascript
// validate-ui.js 保持现状，末尾照常挂全局
// Vite 只负责：打包 → 压缩 → 代码分割 → tree-shaking
// 不改文件内部结构，只改加载方式
```

好处：零风险，Vite 只是"打包工具"，代码逻辑完全不变。

#### 路线 B：渐进式 ES module 化（高风险 ⚠️）

逐个文件改成 `import/export`，重构全局变量为模块依赖。这等于重写前端，不推荐现阶段做。

**结论：走路线 A。Vite 只做打包，不改代码逻辑。**

---

## 二、执行计划（11 天，分 4 个阶段）

### 阶段 1：CSS 清理 + 组件系统（D1-D3）

#### D1 · 清理 inline style

**步骤**：
1. 提取高频 inline style pattern
2. 为每个 pattern 创建 CSS class
3. 批量替换 index.html 中的 `style="..."` → `class="xxx"`
4. 验证渲染效果（浏览器截图对比）

**AI 执行方式**：
- 用 `grep -oP 'style="[^"]*"' index.html | sort | uniq -c | sort -rn` 提取高频 pattern
- 每个出现 5+ 次的 pattern 提取成 class
- 逐 pattern 替换（不是一次全替换，避免出错）
- 替换后运行浏览器截图对比

**预期结果**：inline style 从 661 → <50 个

#### D2 · 建立 components.css

**步骤**：
1. 创建 `frontend/css/components.css`
2. 定义 6 大组件系统：按钮、卡片、表单、标签/徽章、面板、overlay
3. 补充 :root 变量（间距体系、阴影体系、字号体系）
4. 在 index.html 引入 components.css
5. 把现有 HTML 元素的 class 替换成标准组件 class

**AI 执行方式**：
- 直接写 components.css（纯 CSS，无逻辑风险）
- 逐区域替换 HTML class（按工作流步骤分区处理）
- 每个区域替换后验证渲染

#### D3 · 视觉微调

**步骤**：
1. 统一间距节奏（4/8/12/16/24/32 体系）
2. 加 box-shadow 层次（sm/md/lg）
3. 加过渡动效（所有交互元素统一 transition）
4. 空状态设计（"暂无数据" → 插图提示）
5. 全局走查：字号、留白、对齐一致性

**AI 执行方式**：
- 修改 style.css 和 components.css
- 需要人在浏览器里验证视觉效果

---

### 阶段 2：HTML 拆分（D4-D5）

#### D4 · 创建 fragments 目录 + 拆分主要面板

**步骤**：
1. 创建 `frontend/fragments/` 目录
2. 从 index.html 提取 7 个步骤面板 → 7 个 HTML 文件
3. 从 index.html 提取 overlay 弹窗 → 各自的 HTML 文件
4. 写 `loadFragment()` 函数
5. index.html 只保留骨架

**AI 执行方式**：
- 按行号范围提取 HTML 片段
- 写 loadFragment 加载逻辑
- 验证所有面板正确加载

#### D5 · 拆分 overlay 和弹窗

**步骤**：
1. 提取所有 overlay（头脑风暴、导出、快照等）→ 各自 HTML
2. 提取 topbar → topbar.html
3. 提取模型配置弹出层 → model-config.html
4. 验证所有 JS 事件绑定仍然生效（关键：onclick 在片段里仍可用）

**注意**：onclick 事件绑定写在 JS 文件里（不是 HTML 里），所以 HTML 拆分不影响事件。
但 `document.getElementById()` 必须在片段加载后才调用——需要确认所有初始化时机。

---

### 阶段 3：Vite 打包 + 拆分大文件（D6-D8）

#### D6 · 加 Vite（路线 A：只打包，不改逻辑）

**步骤**：
1. `npm init -y` + `npm install -D vite`
2. 创建 vite.config.js
3. 创建 `frontend/js/main.js` 作为入口
4. 修改 index.html：42 个 script 标签 → 1 个 `<script type="module" src="/js/main.js">`
5. 在 main.js 中 import 所有现有 JS 文件
6. **关键**：每个 JS 文件末尾保持全局挂载（不改内部逻辑）
7. 测试 `npx vite` 开发模式 → 确认所有功能正常
8. 测试 `npx vite build` 生产构建 → 确认输出可用

**AI 执行方式**：
- 写配置文件和 main.js
- 逐个验证 JS 文件的全局变量是否正确暴露
- 开发模式下逐功能测试

**最大风险点**：
- 部分 JS 文件用了 `var` 在全局作用域（script 标签天然全局）
- Vite 的 ES module 模式下 `var` 不再是全局
- 解决：main.js 中显式 import 并挂 `window.xxx`

```javascript
// main.js 示例
import './state.js';        // state.js 末尾有 window.state = ...
import './api.js';          // api.js 末尾有 window.api = ...
import './modules/editor.js';
// ...所有模块
```

如果某些文件没有 `window.xxx = ...` 挂载，需要在文件末尾补上。

#### D7 · 拆分 validate-ui.js（1636 行 → 5 个子模块）

**步骤**：
1. 分析 validate-ui.js 的功能区块
2. 拆分成 5 个子文件
3. 写 index.js 组合入口
4. 全局挂载保持不变（`window.ValidateUI = ...`）
5. 验证所有检查功能正常

**AI 执行方式**：
- 先读 validate-ui.js 分析功能边界
- 按功能职责切割代码
- 每个子文件自包含，末尾挂全局
- 测试验证

#### D8 · 拆分 toolbox.js（1601 行 → 8 个子模块）

同 D7 的流程，拆 toolbox.js。

---

### 阶段 4：性能优化（D9-D11）

#### D9 · 虚拟滚动

**步骤**：
1. 写 VirtualList 基类（~60 行）
2. 改左侧章节列表使用虚拟滚动
3. 改 Step2/5 大纲列表使用虚拟滚动
4. 改 Step7 时间线左导航使用虚拟滚动
5. 测试：100+ 章节的场景是否流畅

#### D10 · innerHTML → textContent

**步骤**：
1. 找所有纯文本更新的 innerHTML（标题、字数、状态等）
2. 替换成 textContent
3. 找所有高频更新的 DOM 区域（AI 响应渲染、检查结果渲染）
4. 改成增量更新而非全量 innerHTML

#### D11 · 验收 + 回流

**步骤**：
1. 全面功能测试：7 个步骤 × 所有 AI 功能 × 工具箱 × 检查体系
2. 性能测试：首屏加载时间、100 章流畅度、AI 响应渲染速度
3. 视觉验收：截图对比原始 vs 重构版
4. 确认无回归后，将改动回流到原始项目 <源项目>

---

## 三、AI 执行约束

### 每一步必须做的事

1. **改前必读**：修改任何文件前，先完整读取当前内容
2. **小步替换**：不一次改超过 50 行 inline style，分批处理
3. **即时验证**：每完成一个改动，用浏览器访问验证渲染
4. **截图对比**：关键页面改前/改后截图存档
5. **语法检查**：JS 文件改完用 `node -e "new vm.Script(...)"` 验证

### 不做的事

1. **不换框架**：不引入 React/Vue/Svelte
2. **不改后端**：只改前端，后端不动
3. **不改业务逻辑**：JS 文件内部逻辑保持不变，只做组织方式调整
4. **不做协作功能**：用户已明确暂不做
5. **不破坏全局变量依赖**：所有 `window.xxx` 挂载保持不变

### 回退策略

每个阶段完成后 git commit，如果出现问题可以逐阶段回退：

```bash
cd <项目根>
git init
git add -A
git commit -m "baseline: 原始代码副本"

# D1 完成后
git commit -m "phase1-d1: inline style 清理"

# D2 完成后
git commit -m "phase1-d2: components.css 建立"
...
```

---

## 四、预期成果

| 指标 | 现在 | 目标 |
|------|------|------|
| index.html 行数 | 7061 | ~500（骨架） |
| inline style 数量 | 661 | <50 |
| CSS 变量覆盖率 | 40+ | 60+（加间距/阴影/字号体系） |
| 组件 class 覆盖 | 零 | 6 大系统 ~200 行 |
| 首屏 JS 体积 | ~400KB 裸 | ~80KB gzip |
| JS 文件最大单文件 | 1636 行 | <400 行 |
| 100 章列表渲染 | 全量 DOM | 虚拟滚动 |
| 视觉一致性 | 各处随意 | 统一体系 |
