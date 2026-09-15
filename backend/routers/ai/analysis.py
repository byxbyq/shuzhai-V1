# -*- coding: utf-8 -*-
import json, logging, re
from fastapi import APIRouter

from backend.services.project_service import state, get_generator, get_world
from backend.api_models import err, ErrorCode
from backend.prompt_sanitizer import sanitize_light

logger = logging.getLogger(__name__)

from ._models import AnalyzeContentRequest

router = APIRouter()

@router.post("/analyze-content")
def ai_analyze_content(data: AnalyzeContentRequest):
    """接收任意文本内容，AI分析提取世界观、风格、角色等设定"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    content = sanitize_light(data.content[:8000])
    if not content.strip(): return err(ErrorCode.VALIDATION_ERROR, "内容为空")

    prompt = f"""你是一位专业的小说世界观分析师。请从以下用户提供的任意内容（可能是分镜脚本、小说梗概、世界观文档等）中提取结构化设定信息。

用户内容：
{content}

请分析并返回以下JSON格式（不要任何解释，只返回JSON）：

{{
  "整体风格": "一句话概括整体风格",
  "视角规则": "视角和叙事方式",
  "感官限制": "如果有特殊的感官限制",
  "氛围基调": "整体氛围描述",
  "核心设定": "核心世界观设定",
  "时代背景": "时代和地点背景",
  "主要角色": "主要角色设定",
  "视觉风格": "如果有视觉/画面风格描述",
  "其他设定": "其他值得记录的设定"
}}

如果某项内容在用户文本中没有明确体现，请根据上下文合理推断或留空字符串。"""

    try:
        result = gen.ai.generate(prompt)
        clean = result.replace("```json", "").replace("```", "").strip()
        extracted = None
        try:
            extracted = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', clean)
            if match:
                try:
                    extracted = json.loads(match.group())
                except Exception:
                    pass
            if not extracted:
                extracted = {}
                for line in clean.split('\n'):
                    line = line.strip()
                    if not line or line in ['{', '}']:
                        continue
                    m = re.match(r'"([^"]+)"\s*:\s*"(.*?)"(?:,)?$', line)
                    if m:
                        extracted[m.group(1)] = m.group(2)

        if not extracted:
            return err(ErrorCode.AI_FAILED, "AI返回结果无法解析")

        world_settings = {}
        for key in ["整体风格", "视角规则", "感官限制", "氛围基调", "核心设定", "时代背景", "主要角色", "视觉风格", "其他设定"]:
            val = extracted.get(key, "")
            if val and str(val).strip():
                world_settings[key] = str(val).strip()

        if world_settings:
            state.project.world_settings = world_settings
            state.project._save_meta()

        # 同步写入 world_meta.json（让 WorldSettings.to_prompt() 生效）
        try:
            w = get_world()
            # 将扁平的 world_settings 映射到结构化的 WorldSettings
            core_setting = world_settings.get("核心设定", "")
            era = world_settings.get("时代背景", "")
            style = world_settings.get("整体风格", "")
            atmosphere = world_settings.get("氛围基调", "")
            characters_desc = world_settings.get("主要角色", "")
            other = world_settings.get("其他设定", "")

            # 核心设定 + 时代背景 → freeform
            if core_setting and "核心设定" not in w.freeform:
                w.freeform["核心设定"] = core_setting
            if era and "时代背景" not in w.freeform:
                w.freeform["时代背景"] = era
            if style and "整体风格" not in w.freeform:
                w.freeform["整体风格"] = style
            if atmosphere and "氛围基调" not in w.freeform:
                w.freeform["氛围基调"] = atmosphere
            if characters_desc and "主要角色" not in w.freeform:
                w.freeform["主要角色"] = characters_desc
            if other and "其他设定" not in w.freeform:
                w.freeform["其他设定"] = other
            w.save()
            logger.info(f"world_meta.json 已同步: {len(w.freeform)} 项设定")
        except Exception as wm_err:
            logger.warning(f"world_meta.json 同步失败: {wm_err}")

        return {"ok": True, "settings": world_settings, "count": len(world_settings)}
    except Exception as e:
        logger.warning(f"AI analyze content error: {e}")
        return err(ErrorCode.AI_FAILED, f"AI分析失败: {str(e)}")

@router.post("/extract-settings")
def ai_extract_settings():
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    outline = state.project.get_outline_text()
    if not outline: return err(ErrorCode.VALIDATION_ERROR, "outline.txt 为空")
    genre = state.project.meta.get("genre", "小说") or "小说"
    prompt = f"从以下{genre}小说大纲中提取世界观设定，返回JSON：\n\n{outline[:5000]}\n\n只返回JSON，不要解释。"
    result = gen.ai.generate(prompt)
    try:
        clean = result.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        w = get_world()
        w.magic_system = data.get("magic_system", w.magic_system)
        w.forces = data.get("forces", [])
        w.items = data.get("items", [])
        w.hard_constraints = data.get("hard_constraints", [])
        w.freeform = data.get("freeform", {})
        w.save()
        return {"ok": True, "stats": w.get_stats()}
    except Exception as e:
        logger.warning(f"AI extract settings error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, "AI提取结果格式异常")

@router.post("/generate-characters")
def ai_generate_characters(data: dict = None):
    """AI基于世界观+大纲生成人物档案"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    # 重新加载世界观设定（确保拿到最新设定）
    gen.reload_world()
    # 获取全书大纲文本（包含事件细节，让AI能提取角色）
    outline_text = ""
    if state.project.novel_outline:
        no = state.project.novel_outline
        if isinstance(no, dict):
            # 新格式：dict
            parts = []
            if no.get('theme'): parts.append("【主题】" + no['theme'])
            if no.get('core_conflict'): parts.append("【核心冲突】" + no['core_conflict'])
            if no.get('story_arc'): parts.append("【故事走向】" + no['story_arc'])
            if no.get('world_anchor'): parts.append("【世界观锚点】" + str(no['world_anchor'])[:500])
            if no.get('character_arcs'):
                for arc in no['character_arcs']:
                    if isinstance(arc, dict):
                        parts.append(f"  - {arc.get('character','')}: {arc.get('arc','')}")
            if no.get('ending'): parts.append("【结局】" + no['ending'])
            outline_text = "\n".join(parts)
        elif isinstance(no, list):
            # 旧格式：list（兼容）
            parts = []
            for act in no:
                if isinstance(act, dict):
                    title = act.get("title", "")
                    events = act.get("events", [])
                    if isinstance(events, list):
                        ev_list = []
                        for ev in events:
                            if isinstance(ev, dict):
                                ev_list.append(ev.get("text", ""))
                            elif isinstance(ev, str):
                                ev_list.append(ev)
                            else:
                                ev_list.append(str(ev))
                        ev_text = "; ".join(ev_list)
                    else:
                        ev_text = str(events)
                    parts.append(f"{title}：{ev_text}")
                elif isinstance(act, str):
                    parts.append(act)
            outline_text = "\n".join(parts)
        elif isinstance(no, str):
            outline_text = no
    if not outline_text or len(outline_text) < 50:
        if hasattr(state.project, 'get_outline_text'):
            full_outline = state.project.get_outline_text() or ""
            if len(full_outline) > len(outline_text):
                outline_text = full_outline

    try:
        chars = gen.generate_characters(novel_outline=outline_text)
        if not chars:
            return err(ErrorCode.INTERNAL_ERROR, "AI生成人物档案失败，请检查AI配置")

        # 合并模式：默认追加，data.overwrite=True时覆盖
        overwrite = (data or {}).get("overwrite", False)
        existing = getattr(state.project, 'characters', [])
        if overwrite:
            state.project.characters = chars
        else:
            # 追加：跳过同名角色
            existing_names = {c.get("name", "") for c in existing}
            for c in chars:
                if c.get("name", "") not in existing_names:
                    existing.append(c)
            state.project.characters = existing

        state.project._save_meta()
        return {"ok": True, "characters": state.project.characters, "count": len(chars)}
    except Exception as e:
        logger.warning(f"AI generate characters error: {e}")
        return err(ErrorCode.AI_FAILED, f"AI生成失败: {str(e)}")


# ── Canvas 头脑风暴 ──
