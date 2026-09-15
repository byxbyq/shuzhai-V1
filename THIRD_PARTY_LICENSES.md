# 第三方许可台账（唯一可信源 / Single Source of Truth）

> 本文件是书斋 V66（开源副本）全部第三方代码、资产与依赖义务的**唯一权威台账**。
> 任何外部代码、技能、常量、文本的引入，都必须在此登记；未登记即视为违规。
> 配套文件：`DEPENDENCY_WHITELIST.md`（运行时依赖白名单）、`LICENSE`（双重授权）。
> 门禁：`tools/gate_license.py`（纳入 ESM 全量门禁，fail-loud）。

---

## 一、第三方代码 / 资产登记

| # | 来源项目 | 许可 | 原始作者 | 落点（文件 / 技能） | 义务 / 处理 |
|---|----------|------|----------|---------------------|-------------|
| 1 | 白城主V2（baichengzhu_v2） | 自有资产 | 白城主 | `backend/services/vector_memory.py`（文件头标注「移植自白城主V2」） | 版权归属作者自有；已在 LICENSE 商业授权范围内。 |
| 2 | Humanizer-zh | MIT | op7418 | `frontend/js/skill-data.js`（skill `anti-ai-base`） | 保留 MIT 署名（author 字段已含）；可商用。 |
| 3 | chinese-novelist-skill | MIT | penglonghuang | `frontend/js/skill-data.js`（skills `hook-opener-library`、`genre-templates-37`、`writing-guides`） | 保留 MIT 署名；可商用。 |
| 4 | oh-story-claudecode | MIT | worldwonderer | `frontend/js/skill-data.js`（skills `chapter-positioning`、`deslop-7gate`、`genre-templates-37`、`cover-design-guide`、`writing-guides`） | 保留 MIT 署名；可商用。 |
| 5 | Webnovel Writer | GPL-3.0 | lingfengQAQ | `frontend/js/skill-data.js`（skills `strand-weave-rhythm`、`writing-guides`） | ⚠️ **发布前复核阻断**：上游为 GPL-3.0，仅作内部写作参考；license 字段带「发布前复核」标记，被 `tools/pre-publish-check.py` 阻断，**不进入对外分发基线**。 |

> 说明：其余内置技能均为书斋自研（license=书斋自研）或官方原创/AI辅助生成
> （license=书斋自用·发布前复核），不构成第三方许可义务。运行时 Python 依赖见
> `DEPENDENCY_WHITELIST.md`。

---

## 二、已清零 / 重写记录（合规整改 2026-09-15 · 开源副本）

以下项目曾以代码、注释、常量或技能文本形式进入仓库，已**全部清零或自研重写**，
不再携带任何外部许可义务：

| 来源 | 原许可 | 落点 | 处理结果 |
|------|--------|------|----------|
| EbookLib | AGPL-3.0 | `requirements-mobile.txt` 依赖行；`epub_writer.py` 注释 | **已移除**：EPUB 导出为自研 `backend/services/epub_writer.py`（纯 stdlib，零依赖）；依赖行已删，注释改为中立表述。 |
| InkOS | 代码标 MIT（报告疑 AGPL） | `backend/services/style_fingerprint.py` 注释；`skill-data.js` 4 技能 | **已自研重写**：4 技能改为「书斋(自研)」并加 `license: '书斋自研'`；InkOS 注释已清除。零 AGPL 容忍。 |
| ProseForge | 报告称 AGPL | `guard_pipeline.py`、`context_inspector.py`、`model_registry.py`、`rewrite_loop.py`、`scene_d_discipline.py` 注释与常量来源 | **已自研重写**：来源注释清除，阈值与规则保留为书斋自研质控参数。 |
| oh-story 衍生第三方技能 | 无 MIT 来源核验 | `skill-data.js` / `bundle.js` 的 `ai-flavor-remover`、`shuorenhua`、`de-ai-writer-booster`、`humanizer-v3-integrated` | **已整块删除**（含 `bundle.js` enableIds 与 `toolbox.js` 引用清理）。 |
| lengdu 系列 | PolyForm Noncommercial 1.0.0 | 本副本基线即不含 `cold_read.py`、`shuzhai-calibrator`、`shuzhai-first-read` | 基线干净，无需整改。 |

---

## 三、门禁与内容指纹

- 关键词门禁：`tools/gate_license.py` 规则1/2 禁止 AGPL/GPL/copyleft/非商业许可与
  InkOS/ProseForge/lengdu/EbookLib 痕迹（任一命中即 FAIL）。
- 内容指纹：`tools/license_fingerprints.json` 对 `skill-data.js` 技能 content 与 backend
  赋值型三引号 prompt 做连续≥30字重合 / 精确行命中扫描，防「换皮保内容」。
- 元数据一致性：规则6 校验 author 许可标注 ⟷ license 字段 ⟷ 本台账登记三方一致，
  无审计记录的外部技能禁止入库。

---
*台账生成：2026-09-15（开源副本第二阶段合规整改）*
