# -*- coding: utf-8 -*-
import os
import json
import logging
from fastapi import APIRouter
from typing import Dict, Any

from backend.services.project_service import state, get_world

logger = logging.getLogger(__name__)

"""工作流状态 + Planning Check"""

from backend.routers.project_models import PlanningCheckRequest

router = APIRouter()

@router.get("/workflow-step-status")
def workflow_step_status():
    """统一的9步工作流数据真实状态检查（用于UI步骤对勾 + 步骤准入校验）
    返回：{steps: {1:bool,2:bool,...}, blockers_for_step_N: {...}, planning_cards_ready: bool}
    """
    result: Dict[str, Any] = {
        "steps": {1:False, 2:False, 3:False, 4:False, 5:False, 6:False, 7:False, 8:False, 9:False},
        "detail": {},
    }
    if not state.project:
        return {"ok": True, "data": result, "project_open": False}
    p = state.project

    def _nonempty(x):
        if x is None: return False
        if isinstance(x, (list, dict, str)):
            if isinstance(x, str): return bool(x.strip())
            return len(x) > 0
        return True

    # ── 步骤1：世界观（自由设定项数 >= 2 或 world_core9 有字段非空） ──
    try:
        w = get_world()
        freeform = w.freeform if w and hasattr(w,'freeform') and w.freeform else {}
        world_settings = w.world_settings if w and hasattr(w,'world_settings') and w.world_settings else (getattr(p,'world_settings',None) or {})
        narrative_style = w.narrative_style if w and hasattr(w,'narrative_style') else {}
        era = w.era if w and hasattr(w,'era') else {}
        world_rules = w.world_rules if w and hasattr(w,'world_rules') else []
        # 合并freeform和world_settings做自由设定检查
        frees_merged = {}
        if isinstance(freeform, dict): frees_merged.update(freeform)
        if isinstance(world_settings, dict): frees_merged.update(world_settings)
        s1_frees = len(frees_merged) >= 2
        # 检查9字段
        core9_fields = ['core_setting','era_background','overall_style','atmosphere','main_roles_overview','other_settings','perspective_rules','sensory_limits','visual_style']
        s1_core9 = any(_nonempty(frees_merged.get(k)) for k in core9_fields)
        # 结构化字段
        ns_fields = ['pov','tense','tone','pacing','description_style','verbosity','time_handling']
        era_fields = ['tech_level','society','geography','culture','social_attitude','social_system','era_name','historical_period','daily_life']
        s1_structured = any(_nonempty(narrative_style.get(k)) for k in ns_fields) or \
                        any(_nonempty(era.get(k)) for k in era_fields) or \
                        (isinstance(world_rules, list) and len(world_rules) > 0)
        result["steps"][1] = bool(s1_frees or s1_core9 or s1_structured)
        result["detail"][1] = {"free_settings": len(frees_merged), "core9": s1_core9, "structured": s1_structured,
                                "narrative_style": {k:v for k,v in narrative_style.items() if _nonempty(v)},
                                "era": {k:v for k,v in era.items() if _nonempty(v)}}
    except Exception as e:
        import traceback
        result["detail"][1] = {"error": str(e), "tb": traceback.format_exc()[:300]}

    # ── 步骤3：全书大纲（novel_outline 主题/核心冲突/故事线有任意2个非空） ──
    try:
        no = p.get_novel_outline() if hasattr(p,'get_novel_outline') else (getattr(p,'novel_outline',None) or {})
        has_theme = _nonempty(no.get('theme')) or _nonempty(no.get('title'))
        has_core = _nonempty(no.get('core_conflict')) or _nonempty(no.get('hook'))
        has_arc = _nonempty(no.get('story_arc')) or _nonempty(no.get('structure')) or _nonempty(no.get('overall_description'))
        result["steps"][3] = bool((int(has_theme)+int(has_core)+int(has_arc)) >= 2 or _nonempty(no.get('overall_description')))
        result["detail"][3] = {"theme": bool(has_theme), "core": bool(has_core), "arc": bool(has_arc)}
    except Exception as e:
        result["detail"][3] = {"error": str(e)}

    # ── 步骤2：人物（characters 表至少 2 人 + 任意一人有 personality/backstory/identity 非空） ──
    try:
        cs = getattr(p, 'characters', None) or []
        if not isinstance(cs, list): cs = []
        s3_count = len(cs) >= 2
        s3_rich = False
        for c in cs:
            if isinstance(c, dict):
                if _nonempty(c.get('personality')) or _nonempty(c.get('backstory')) or _nonempty(c.get('identity')) or _nonempty(c.get('camp')):
                    s3_rich = True; break
            elif hasattr(c, 'personality'):
                if _nonempty(getattr(c,'personality',None)) or _nonempty(getattr(c,'backstory',None)):
                    s3_rich = True; break
        result["steps"][2] = bool(s3_count and s3_rich)
        result["detail"][2] = {"count": len(cs), "rich": s3_rich}
    except Exception as e:
        result["detail"][2] = {"error": str(e)}

    # ── 步骤4：分卷纲要（volumes >=1 卷，且至少一卷 outline 有实质内容） ──
    def _outline_rich(ol):
        """检查outline是否包含实质内容（非空JSON对象/非空字符串）"""
        if not ol: return False
        if isinstance(ol, str):
            ol = ol.strip()
            if not ol: return False
            try:
                import json as _json
                ol = _json.loads(ol)
            except:
                return len(ol) > 5  # 非JSON字符串，长度>5才算有内容
        if isinstance(ol, dict):
            # 检查是否有任意字段非空
            for k, v in ol.items():
                if isinstance(v, str) and v.strip(): return True
                if isinstance(v, (list, dict)) and len(v) > 0: return True
            return False
        return bool(ol)
    try:
        vs = p.get_volumes() if hasattr(p,'get_volumes') else (getattr(p,'volumes',None) or [])
        if not isinstance(vs, list): vs = []
        s4_rich = False
        for v in vs:
            if isinstance(v, dict):
                if _outline_rich(v.get('outline')) or _nonempty(v.get('summary')) or _nonempty(v.get('theme')):
                    s4_rich = True; break
            elif hasattr(v, 'outline'):
                if _outline_rich(getattr(v,'outline',None)) or _nonempty(getattr(v,'summary',None)):
                    s4_rich = True; break
        result["steps"][4] = bool(len(vs) >= 1 and s4_rich)
        result["detail"][4] = {"count": len(vs), "rich": s4_rich}
    except Exception as e:
        result["detail"][4] = {"error": str(e)}

    # ── 步骤5：章节大纲（chapters 至少 1 章 outline 非空） ──
    try:
        chs = getattr(p, 'chapters', None) or []
        if not isinstance(chs, list): chs = []
        s5_rich = False
        for c in chs:
            if isinstance(c, dict):
                if _nonempty(c.get('outline')): s5_rich = True; break
            elif hasattr(c, 'outline'):
                if _nonempty(getattr(c,'outline',None)): s5_rich = True; break
        result["steps"][5] = bool(len(chs) >= 1 and s5_rich)
        result["detail"][5] = {"count": len(chs), "rich": s5_rich}
    except Exception as e:
        result["detail"][5] = {"error": str(e)}

    # ── 步骤6：连线框（planning_cards 节点数 >= 1） ──
    pc_ready = False
    try:
        pc = p.get_planning_cards() if hasattr(p,'get_planning_cards') else {}
        nodes = pc.get('nodes') if isinstance(pc, dict) else []
        edges = pc.get('edges') if isinstance(pc, dict) else []
        nodes_arr = nodes if isinstance(nodes, list) else []
        edges_arr = edges if isinstance(edges, list) else []
        pc_ready = len(nodes_arr) >= 1
        result["steps"][6] = pc_ready
        result["detail"][6] = {"nodes": len(nodes_arr), "edges": len(edges_arr)}
    except Exception as e:
        result["detail"][6] = {"error": str(e)}
    result["planning_cards_ready"] = pc_ready

    # ── 步骤7：写作（chapters.content 或 txt 至少 1 章 >= 500字） ──
    try:
        chs = getattr(p, 'chapters', None) or []
        if not isinstance(chs, list): chs = []
        s6_count = 0
        for c in chs:
            if isinstance(c, dict):
                cont = c.get('content') or ''
                txt = c.get('content_text') or ''
                wc = c.get('word_count') or 0
            else:
                cont = getattr(c,'content',None) or ''
                txt = getattr(c,'content_text',None) or ''
                wc = getattr(c,'word_count',0) or 0
            merged_len = max(len((str(cont or '') + str(txt or '')).strip()), int(wc or 0))
            if merged_len >= 500: s6_count += 1
        result["steps"][7] = bool(s6_count >= 1)
        result["detail"][7] = {"chapters_over_500": s6_count, "total_chapters": len(chs)}
    except Exception as e:
        result["detail"][7] = {"error": str(e)}

    # ── 步骤8：时间线（timeline 表 >= 3 个事件） ──
    try:
        tl = []
        if hasattr(p, 'list_timeline'):
            tl = p.list_timeline() or []
        elif hasattr(p, 'db') and p.db:
            try:
                rows = p.db.execute("SELECT id FROM timeline LIMIT 100").fetchall()
                tl = list(rows)
            except: tl = []
        t7_count = len(tl) >= 3
        result["steps"][8] = bool(t7_count)
        result["detail"][8] = {"count": len(tl)}
    except Exception as e:
        result["detail"][8] = {"error": str(e)}

    # ── 步骤9：草稿定稿（chapters 中 >= 一半章节 status=final/...，或有 export_epub 产物） ──
    try:
        chs = getattr(p, 'chapters', None) or []
        if not isinstance(chs, list): chs = []
        final_n = 0
        for c in chs:
            st = c.get('status') if isinstance(c, dict) else getattr(c,'status',None)
            if st in ('final','finalized','published','approved'): final_n += 1
        exported = False
        try:
            pp = getattr(p, 'project_dir', None) or getattr(p,'project_path', None)
            if pp:
                ex = os.path.join(str(pp), 'export')
                exported = os.path.isdir(ex) and any(f.endswith('.epub') or f.endswith('.docx') for f in os.listdir(ex))
        except: pass
        s9 = bool(exported or (len(chs) >= 2 and final_n * 2 >= len(chs)))
        result["steps"][9] = s9
        result["detail"][9] = {"finalized": final_n, "total": len(chs), "exported": exported}
    except Exception as e:
        result["detail"][9] = {"error": str(e)}

    return {"ok": True, "data": result, "project_open": True}


@router.post("/planning-check")
def planning_check(req: PlanningCheckRequest):
    """连线框对照校验：AI判断节点设定与正文的一致性，返回三状态"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    if not req.nodes:
        return {"ok": True, "results": {}, "detail": ""}
    if not req.chapter_text or len(req.chapter_text.strip()) < 50:
        return {"ok": True, "results": {}, "detail": "正文过短，无法校验"}

    try:
        from backend.ai_client import AIClient
        from backend.prompt_sanitizer import sanitize_light
        ai = AIClient()

        # 构建节点设定摘要
        node_descs = []
        for i, n in enumerate(req.nodes):
            node_descs.append(
                f"[{i+1}] 类型:{n.get('type','自由')} | 标题:{n.get('title','')} | "
                f"摘要:{n.get('summary','')} | 引用:{n.get('quotes','')} | "
                f"章节:{n.get('chapter_ref','')}"
            )
        nodes_text = "\n".join(node_descs)

        # 构建连线描述（如有）
        edges_text = ""
        if req.edges:
            edge_descs = []
            for e in req.edges:
                fn = next((x.get('title', '?') for x in req.nodes if x.get('id') == e.get('from')), '?')
                tn = next((x.get('title', '?') for x in req.nodes if x.get('id') == e.get('to')), '?')
                edge_descs.append(f"{fn} → {tn}（{e.get('label','关联')}）")
            edges_text = "\n连线关系：\n" + "\n".join(edge_descs)

        # 正文截断（避免超长）
        chapter_excerpt = sanitize_light(req.chapter_text[:3000])

        prompt = f"""你是小说设定一致性校验助手。请判断以下「规划设定」在「正文」中的落地情况。

【规划设定】
{nodes_text}
{edges_text}

【正文节选】
{chapter_excerpt}

【校验规则】
对每个设定节点，判断其在正文中的状态：
- consistent（已一致）：正文明确体现了该设定（人物关系/伏笔/章节关联已落地）
- needs_update（需更新）：正文与设定存在冲突，或设定已规划但正文未体现
- uninvolved（未涉及）：该设定与当前正文无关（如其他章节的伏笔）

【输出格式】
仅输出JSON，不要任何解释：
{{
  "results": {{
    "节点id1": "consistent",
    "节点id2": "needs_update",
    "节点id3": "uninvolved"
  }},
  "detail": "简要说明不一致的具体段落和原因（如有）"
}}"""

        raw = ai.generate(prompt, task="check")
        logger.info(f"[planning-check] AI原始返回(前500字): {raw[:500]}")

        # 解析JSON - 多策略尝试
        import re
        data = None

        # 策略1: 尝试直接解析
        try:
            data = json.loads(raw.strip())
        except:
            pass

        # 策略2: 移除markdown代码块后解析
        if not data:
            cleaned = re.sub(r'```(?:json)?\s*', '', raw)
            cleaned = re.sub(r'\s*```', '', cleaned)
            try:
                data = json.loads(cleaned.strip())
            except:
                pass

        # 策略3: 提取花括号内的JSON（最短匹配）
        if not data:
            # 找第一个{开始，尝试逐层匹配
            for start_match in re.finditer(r'\{', raw):
                start = start_match.start()
                # 从后往前找最后一个}
                for end_match in re.finditer(r'\}', raw[start:]):
                    end = start + end_match.end()
                    candidate = raw[start:end]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and ('results' in parsed or 'detail' in parsed):
                            data = parsed
                            break
                    except:
                        continue
                if data:
                    break

        # 策略4: 贪心匹配取最大可能的JSON
        if not data:
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except:
                    # 尝试修复常见问题：尾部多余逗号
                    fixed = re.sub(r',\s*}', '}', json_match.group())
                    fixed = re.sub(r',\s*]', ']', fixed)
                    try:
                        data = json.loads(fixed)
                    except:
                        pass

        if data and isinstance(data, dict):
            results = data.get("results", {})
            # 确保所有节点都有结果
            for n in req.nodes:
                nid = n.get("id")
                if nid and nid not in results:
                    results[nid] = "uninvolved"
            return {"ok": True, "results": results, "detail": data.get("detail", "")}
        else:
            logger.warning(f"[planning-check] JSON解析失败, raw前200字: {raw[:200]}")
            return {"ok": True, "results": {}, "detail": "AI返回格式异常，无法解析"}

    except Exception as e:
        logger.error(f"planning-check 失败: {e}")
        return {"ok": False, "error": str(e)}


