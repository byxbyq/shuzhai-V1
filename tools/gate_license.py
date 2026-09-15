#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书斋 V66 开源合规门禁（防回归 · 纳入 ESM 全量门禁）

硬阻断规则（任一命中即 FAIL，exit 1）：
  1. 禁止 AGPL / GPL / copyleft / PolyForm / Noncommercial 进入分发代码。
     ⚠️ 例外（2026-09-15 · 作者拍板）：若某技能块的 `license` 含「发布前复核」标记
     （⇒ 该技能已被发布闸门 tools/pre-publish-check.py 阻断、**不会进入对外分发基线**），
     则该块内允许**如实标注** copyleft 上游来源名（如 `Webnovel Writer(GPL-3.0)`）。
     fail-safe：例外范围**仅限已阻断的技能块**，且**只管规则1**，规则2（已清零痕迹）不豁免。
  2. 禁止任何已清零的上游痕迹残留：InkOS / ProseForge / lengdu / EbookLib / ebooklib。
  3. 运行时依赖必须登记于 DEPENDENCY_WHITELIST.md（未登记即 FAIL）。
  4. 内容指纹：禁与禁用源（lengdu 等）连续≥30字重合，或归一化行精确命中 >5 行（防「换皮保内容」）。
  5. 指纹扫描面：skill-data.js 各技能 content + backend 赋值型三引号硬编码 prompt。
  6. 上游许可元数据一致性（T3 根治 · 2026-09-15）：author 的 `(XXX许可)` 标注 ⟷ license 字段
     ⟷ THIRD_PARTY_LICENSES.md 台账登记，三方必须一致；无审计记录的外部技能禁止入库。

设计原则（与既有门禁一致）：
  - 只读、fail-loud、不写不删任何文件、不触发 git 操作。
  - 仅扫描源码目录（backend / novel_world / frontend/js / tools），排除本脚本自身、
    LICENSE / THIRD_PARTY_LICENSES.md / DEPENDENCY_WHITELIST.md / 文档 / 依赖 / 归档。
  - 合法 Attribution（FictionForge / 白城主V2 / Humanizer-zh 等）已在台账登记，属允许。
"""
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_DIRS = ["backend", "novel_world", "frontend/js", "tools"]
SCAN_EXT = (".py", ".js")

# 本门禁脚本自身不扫描
SELF_PATH = os.path.abspath(__file__)

# 规则1：明确禁止的许可关键词（不区分大小写）
FORBIDDEN_LICENSE = [
    "agpl", "gpl", "copyleft", "polyform", "noncommercial", "non-commercial",
]

# 规则1 例外标记：技能块 license 含此标记 ⇒ 已被发布闸门阻断，允许如实标注 copyleft 来源
PUBLISH_BLOCK_MARK = "发布前复核"

# 规则2：已清零、不得残留的上游痕迹（不区分大小写）
REMOVED_TRACES = [
    "inkos", "proseforge", "lengdu", "ebooklib",
]

# 合法 Attribution（在 THIRD_PARTY_LICENSES.md 登记，允许出现）
ALLOWED_ATTR = [
    "fictionforge", "白城主v2", "baichengzhu_v2", "humanizer-zh",
    "chinese-novelist-skill", "oh-story-claudecode", "webnovel writer",
]

# 扫描时跳过的目录 / 文件
SKIP_DIRS = {"__pycache__", "node_modules", "_archive", ".git", "data", "venv"}
SKIP_FILES = {"LICENSE", "THIRD_PARTY_LICENSES.md", "DEPENDENCY_WHITELIST.md"}


def iter_source_files():
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(SCAN_EXT):
                    continue
                full = os.path.join(root, fn)
                if os.path.abspath(full) == SELF_PATH:
                    continue
                if fn in SKIP_FILES:
                    continue
                yield full


def _exempt_block_lines(path):
    """返回 skill-data.js 中「已阻断技能块」覆盖的行号集合（1-based，闭区间）。

    判据：技能块的 `license` 值含 PUBLISH_BLOCK_MARK（「发布前复核」）
    ⇒ 该技能**已被发布闸门阻断、不会进入对外分发基线**，故允许其如实标注
    copyleft 上游来源名（仅规则1豁免；规则2「已清零痕迹」不豁免）。

    其它文件一律返回空集 ⇒ 不产生任何豁免。
    """
    if os.path.basename(path) != "skill-data.js":
        return set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return set()
    starts = [i for i, l in enumerate(lines) if re.search(r"^\s*id: '\S", l)]
    exempt = set()
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = "".join(lines[s:e])
        ml = re.search(r"license: '([^']*)'", body)
        if ml and PUBLISH_BLOCK_MARK in ml.group(1):
            exempt.update(range(s + 1, e + 1))
    return exempt


def check_forbidden_tokens():
    hits = []
    for path in iter_source_files():
        try:
            exempt = _exempt_block_lines(path)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    low = line.lower()
                    # 规则1：禁止许可关键词（已阻断技能块内豁免）
                    if i not in exempt:
                        for kw in FORBIDDEN_LICENSE:
                            if kw in low:
                                hits.append((path, i, f"禁止许可关键词: {kw!r}"))
                                break
                    # 规则2：已清零上游痕迹（不豁免）
                    for kw in REMOVED_TRACES:
                        if kw in low:
                            hits.append((path, i, f"已清零痕迹残留: {kw!r}"))
                            break
        except Exception as e:
            hits.append((path, 0, f"读取失败: {e}"))
    return hits


def load_whitelist_packages():
    """从 DEPENDENCY_WHITELIST.md 解析已核准依赖包名（表格首列）。"""
    pkgs = set()
    path = os.path.join(ROOT, "DEPENDENCY_WHITELIST.md")
    if not os.path.exists(path):
        return pkgs
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # 首列包名：允许其后有 ⚠️ 等标注（如弱 Copyleft 例外项），再遇 | 结束
            m = re.match(r"\|\s*([A-Za-z][A-Za-z0-9_.\-]*)\s*[^|]*\|", line)
            if m:
                pkgs.add(m.group(1).lower())
    return pkgs


def check_dependencies():
    """requirements*.txt 中的每个包必须在白名单中。"""
    violations = []
    whitelist = load_whitelist_packages()
    for fn in os.listdir(ROOT):
        if not fn.startswith("requirements") or not fn.endswith(".txt"):
            continue
        full = os.path.join(ROOT, fn)
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                # 支持 name==ver / name>=ver / name 形式
                m = re.match(r"^([A-Za-z0-9_.\-]+)", s)
                if not m:
                    continue
                name = m.group(1).lower()
                if name not in whitelist:
                    violations.append((full, i, f"依赖未入白名单: {name}"))
    return violations


# ── 规则4/5：内容指纹校验（防“换皮保内容”绕过关键词门禁）──
# 内置离线指纹库：由禁用上游（lengdu 为主，可扩展 inkos/proseforge）参考文件预提取，
# 见 _gen_fingerprints.py。门禁加载 tools/license_fingerprints.json 做静态比对。
# 规则：任意文本块与禁用源指纹 (a) 连续≥30字（去标点空白后）重合，或 (b) 归一化行精确命中>5 行 → FAIL。
# 仅扫描：skill-data.js 各技能 content；backend 内赋值型三引号硬编码字符串（prompt）。
# 跳过空行/纯分隔符/平凡短行（<12字）/代码样板行。不联网、不引模型、不扫运行时动态文本。
FINGERPRINT_PATH = os.path.join(ROOT, "tools", "license_fingerprints.json")
OVERLAP_MIN = 30          # 连续重合字宽（去标点空白后）
EXACT_HIT_MAX = 5         # 归一化行精确命中上限，超过即 FAIL


def _fp_norm(s):
    s = s.strip().strip('#-*>`').strip()
    s = s.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    return s


def _fp_loose(s):
    return re.sub(r"[\s\"',\.。，、：:；;！!？?（）\(\)\[\]【】\-—~～]", "", s)


def _fp_trivial(s):
    return s == "" or s in ("---", "***", "===")


def load_fingerprints():
    """返回 {source: {"tg": set(30字窗口), "exact": set(归一化长行)}}；缺失返回 {}。"""
    if not os.path.exists(FINGERPRINT_PATH):
        return {}
    try:
        with open(FINGERPRINT_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[规则4/5] 指纹库读取失败: {e}")
        return {}
    out = {}
    for src, fp in raw.items():
        out[src] = {
            "tg": set(fp.get("thirty_grams", [])),
            "exact": set(fp.get("exact_lines", [])),
        }
    return out


def _check_lines_against(lines, tg, exact):
    """返回 (overlap_lines, exact_count)。"""
    overlap = []
    exact_count = 0
    for ln in lines:
        n = _fp_norm(ln)
        if _fp_trivial(n):
            continue
        core = _fp_loose(n)
        if len(core) >= OVERLAP_MIN:
            hit = False
            for i in range(len(core) - OVERLAP_MIN + 1):
                if core[i:i + OVERLAP_MIN] in tg:
                    hit = True
                    break
            if hit:
                overlap.append(ln[:60])
        if len(n) >= 12 and n in exact:
            exact_count += 1
    return overlap, exact_count


def _parse_skill_content(js_text, skill_id):
    idx = js_text.find("id: '%s'" % skill_id)
    if idx < 0:
        return None
    cstart = js_text.find("content: [", idx)
    if cstart < 0:
        return None
    cend = js_text.find("].join('\\n')", cstart)
    if cend < 0:
        return None
    block = js_text[cstart + len("content: [") : cend]
    strings = re.findall(r"'(?:\\.|[^'\\])*'", block)
    out = []
    for s in strings:
        inner = s[1:-1].replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        out.append(inner)
    return out


def _iter_skill_ids(js_text):
    for m in re.finditer(r"id: '([^']+)'", js_text):
        yield m.group(1)


def _extract_assigned_triple(text):
    """提取 `VAR = \"\"\"...\"\"\"` 形式的硬编码字符串（prompt），排除文档字符串。"""
    out = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"\"\"(.*?)\"\"\"", text, re.DOTALL):
        out.append((m.group(1), m.group(2)))
    return out


def fingerprint_check():
    fps = load_fingerprints()
    if not fps:
        return [("tools/license_fingerprints.json", 0,
                 "指纹库缺失：内容指纹校验跳过（请运行 _gen_fingerprints.py 重新生成）")]
    src_sets = {src: (fp["tg"], fp["exact"]) for src, fp in fps.items()}
    hits = []

    # 目标1：skill-data.js 各技能 content
    sd = os.path.join(ROOT, "frontend", "js", "skill-data.js")
    if os.path.exists(sd):
        txt = open(sd, "r", encoding="utf-8", errors="ignore").read()
        for sid in _iter_skill_ids(txt):
            content = _parse_skill_content(txt, sid)
            if not content:
                continue
            for src, (tg, exact) in src_sets.items():
                ov, ec = _check_lines_against(content, tg, exact)
                if ov:
                    hits.append((sd, 0,
                        "[%s] 技能 %s 检出连续≥%d字重合 %d 处（内容指纹命中，疑似非商业源移植）"
                        % (src, sid, OVERLAP_MIN, len(ov))))
                elif ec > EXACT_HIT_MAX:
                    hits.append((sd, 0,
                        "[%s] 技能 %s 归一化行精确命中 %d 行>%d（疑似非商业源移植）"
                        % (src, sid, ec, EXACT_HIT_MAX)))

    # 目标2：backend 内赋值型三引号硬编码字符串
    backend = os.path.join(ROOT, "backend")
    if os.path.isdir(backend):
        for root, dirs, files in os.walk(backend):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(root, fn)
                if os.path.abspath(full) == SELF_PATH:
                    continue
                txt = open(full, "r", encoding="utf-8", errors="ignore").read()
                for var, body in _extract_assigned_triple(txt):
                    lines = body.split("\n")
                    for src, (tg, exact) in src_sets.items():
                        ov, ec = _check_lines_against(lines, tg, exact)
                        if ov:
                            hits.append((full, 0,
                                "[%s] 变量 %s 检出连续≥%d字重合 %d 处（内容指纹命中）"
                                % (src, var, OVERLAP_MIN, len(ov))))
                        elif ec > EXACT_HIT_MAX:
                            hits.append((full, 0,
                                "[%s] 变量 %s 归一化行精确命中 %d 行>%d"
                                % (src, var, ec, EXACT_HIT_MAX)))
    return hits


# ── 规则6（T3 根治）：上游许可元数据一致性（author 标注 ⟷ license ⟷ 台账）──
# 背景：曾实测 `author:'Webnovel Writer(MIT)'` 是**事实性误标**（该上游实为 GPL-3.0）；
#   且「结构/参数级派生」不产生任何内容指纹命中 ⇒ 关键词门禁与指纹门禁**两道都拦不住元数据说谎**。
# 规则（只约束**带许可标注**的技能块；fail-safe：无标注 ⇒ 无约束，不产生误伤）：
#   6a 一致性：author 的 `(XXX许可)` 标注必须与 license 字段一致 ——
#      copyleft 家族（AGPL/LGPL/GPL/PolyForm/CC-BY）⇒ license 必须含「发布前复核」阻断标记 + 同名；
#      宽松家族（MIT/BSD/Apache/MPL）⇒ license 必须含同名，且不得写成 copyleft 阻断态。
#   6b 台账登记：带许可标注（或 license 为具名宽松许可）的技能 id 必须在
#      THIRD_PARTY_LICENSES.md 出现 ⇒ 无审计记录者禁止入库。
LICENSE_TOKEN_RE = re.compile(
    r"\(\s*(AGPL|LGPL|GPL|MIT|BSD|Apache|MPL|PolyForm|CC[- ]BY)[- ]?([0-9.]*)\s*\)", re.I)
COPYLEFT_FAMILIES = ("AGPL", "LGPL", "GPL", "POLYFORM", "CC-BY")
PERMISSIVE_FAMILIES = ("MIT", "BSD", "APACHE", "MPL")
LEDGER_PATH = os.path.join(ROOT, "THIRD_PARTY_LICENSES.md")


def _squash(s):
    """归一化许可名：去空白 / 连字符 / 点 / 下划线并大写（'GPL-3.0' → 'GPL30'）。"""
    return re.sub(r"[\s\-_.]", "", s or "").upper()


def _norm_family(tok):
    t = _squash(tok)
    return "CC-BY" if t.startswith("CC") else t


def _parse_skill_meta(js_text):
    """按 id 块切分 skill-data.js，返回 [(id, author, license), ...]。"""
    out = []
    for b in re.split(r"(?=\n\s*\{\s*\n\s*id: ')", js_text):
        mid = re.search(r"id: '([^']+)'", b)
        if not mid:
            continue
        ma = re.search(r"author: '([^']*)'", b)
        ml = re.search(r"license: '([^']*)'", b)
        out.append((mid.group(1), ma.group(1) if ma else "", ml.group(1) if ml else ""))
    return out


def check_license_meta_consistency():
    """规则6：author 许可标注 ⟷ license 字段 ⟷ 台账登记 三方校验。"""
    sd = os.path.join(ROOT, "frontend", "js", "skill-data.js")
    if not os.path.exists(sd):
        return []
    with open(sd, "r", encoding="utf-8", errors="ignore") as f:
        js_text = f.read()
    ledger = ""
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "r", encoding="utf-8", errors="ignore") as f:
            ledger = f.read()
    ledger_sq = _squash(ledger)
    hits = []
    for sid, author, lic in _parse_skill_meta(js_text):
        fams = sorted({_norm_family(t[0]) for t in LICENSE_TOKEN_RE.findall(author or "")})
        lic_sq = _squash(lic)
        need_ledger = bool(fams)
        for fam in fams:
            if fam in COPYLEFT_FAMILIES:
                if PUBLISH_BLOCK_MARK not in (lic or ""):
                    hits.append((sd, 0, "[规则6a] 技能 %s: author 标注 copyleft %s，但 license 无「%s」"
                                      "阻断标记 ⇒ 须划入自用阻断组" % (sid, fam, PUBLISH_BLOCK_MARK)))
                elif _squash(fam) not in lic_sq:
                    hits.append((sd, 0, "[规则6a] 技能 %s: author 标注 %s 与 license=%r 许可名不一致"
                                      % (sid, fam, lic)))
            elif fam in PERMISSIVE_FAMILIES:
                if _squash(fam) not in lic_sq:
                    hits.append((sd, 0, "[规则6a] 技能 %s: author 标注宽松许可 %s，但 license=%r "
                                      "不含该许可名" % (sid, fam, lic)))
                for cf in COPYLEFT_FAMILIES:
                    if _squash(cf) in lic_sq:
                        hits.append((sd, 0, "[规则6a] 技能 %s: author 标注 %s 却写成 copyleft(%s) 态，"
                                          "语义冲突" % (sid, fam, cf)))
        if not need_ledger:
            need_ledger = any(_squash(p) in lic_sq for p in PERMISSIVE_FAMILIES)
        if need_ledger and sid and _squash("`%s`" % sid) not in ledger_sq:
            hits.append((sd, 0, "[规则6b] 技能 %s: 带上游许可标注 / 具名许可，但未在 "
                              "THIRD_PARTY_LICENSES.md 登记（无审计记录禁止入库）" % sid))
    return hits


def main():
    print("===== 开源合规门禁 (gate_license) =====")
    errors = []

    hits = check_forbidden_tokens()
    if hits:
        print(f"[规则1/2] 命中 {len(hits)} 处禁止项：")
        for path, ln, msg in hits:
            rel = os.path.relpath(path, ROOT)
            print(f"  FAIL {rel}:{ln}  {msg}")
        errors.extend(hits)
    else:
        print("[规则1/2] PASS：无 AGPL/GPL/非商业许可关键词，无 InkOS/ProseForge/lengdu/EbookLib 残留。")

    dep_v = check_dependencies()
    if dep_v:
        print(f"[规则3] 命中 {len(dep_v)} 处依赖未登记：")
        for path, ln, msg in dep_v:
            rel = os.path.relpath(path, ROOT)
            print(f"  FAIL {rel}:{ln}  {msg}")
        errors.extend(dep_v)
    else:
        print("[规则3] PASS：所有 requirements 依赖均已在 DEPENDENCY_WHITELIST.md 登记。")

    fp_h = fingerprint_check()
    if fp_h:
        print(f"[规则4/5] 命中 {len(fp_h)} 处内容指纹风险：")
        for path, ln, msg in fp_h:
            rel = os.path.relpath(path, ROOT)
            print(f"  FAIL {rel}:{ln}  {msg}")
        errors.extend(fp_h)
    else:
        print("[规则4/5] PASS：skill-data.js 与 backend 硬编码 prompt 均无禁用源内容指纹重合。")

    meta_h = check_license_meta_consistency()
    if meta_h:
        print(f"[规则6] 命中 {len(meta_h)} 处许可元数据不一致：")
        for path, ln, msg in meta_h:
            rel = os.path.relpath(path, ROOT)
            print(f"  FAIL {rel}:{ln}  {msg}")
        errors.extend(meta_h)
    else:
        print("[规则6] PASS：author 许可标注 / license 字段 / 台账登记 三方一致。")

    print("=====================================")
    if errors:
        print(f"结果: {len(errors)} 项失败 —— 开源合规门禁未通过，禁止提交。")
        sys.exit(1)
    print("结果: 全部 PASS。开源合规无阻断项。")


if __name__ == "__main__":
    main()
