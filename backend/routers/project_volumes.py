# -*- coding: utf-8 -*-
import time
import logging
from fastapi import APIRouter, Request

from backend.services.project_service import state

logger = logging.getLogger(__name__)

"""卷管理 + AI分卷"""

from backend.routers.project_models import (
    VolumeAdd, VolumeOp, VolumeRename, VolumeOutlineUpdate,
    AIVolumeSplitRequest, VolumeChapterRequest, VolumeChaptersRequest,
)

router = APIRouter()

# ── Volumes ──

@router.get("/volumes")
def get_volumes():
    """获取卷列表"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    volumes = state.project.get_volumes()
    return {"ok": True, "volumes": volumes}

@router.post("/volumes")
async def save_volumes(request: Request):
    """保存卷列表（覆盖），接受 dict 或 list"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    data = await request.json()
    if isinstance(data, list):
        volumes_data = data
    else:
        volumes_data = (data or {}).get("volumes", [])
    state.project.set_volumes(volumes_data)
    return {"ok": True, "volumes": state.project.get_volumes()}

@router.post("/volume/add")
def add_volume(data: VolumeAdd):
    """添加一卷"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    idx = state.project.add_volume(data.title, data.outline, data.start_chapter, data.end_chapter)
    return {"ok": True, "index": idx, "volumes": state.project.get_volumes()}

@router.post("/volume/delete")
def delete_volume(data: VolumeOp):
    """删除一卷（章节移到前一卷）"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.delete_volume(data.vol_index)
    return {"ok": ok, "volumes": state.project.get_volumes() if state.project else []}

@router.post("/volume/rename")
def rename_volume(data: VolumeRename):
    """重命名一卷"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.rename_volume(data.vol_index, data.title)
    return {"ok": ok, "volumes": state.project.get_volumes() if state.project else []}


@router.put("/volume/{vol_index}/outline")
def update_volume_outline(vol_index: int, data: VolumeOutlineUpdate):
    """更新卷纲要"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.set_volume_outline(vol_index, {
        "summary": data.summary,
        "theme": data.theme,
        "key_events": data.key_events,
        "character_arcs": data.character_arcs,
    })
    return {"ok": ok}

@router.post("/volume/{vol_index}/outline")
async def update_volume_outline_post(vol_index: int, request: Request):
    """更新卷纲要（POST版本，兼容前端）"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    body = await request.json()
    # 如果前端传了title且与当前不同，先重命名
    title = body.get("title", "").strip()
    if title:
        vols = state.project.get_volumes()
        current_title = ""
        for v in vols:
            if v.get("index") == vol_index:
                current_title = v.get("title", "")
                break
        if title and title != current_title:
            state.project.rename_volume(vol_index, title)
    ok = state.project.set_volume_outline(vol_index, {
        "summary": body.get("summary", ""),
        "theme": body.get("theme", ""),
        "key_events": body.get("key_events", []),
        "character_arcs": body.get("character_arcs", []),
    })
    return {"ok": ok}


@router.get("/volume/{vol_index}/outline")
def get_volume_outline(vol_index: int):
    """获取卷纲要"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    data = state.project.get_volume_outline(vol_index)
    return {"ok": True, "data": data}


@router.post("/auto-volumes")
def auto_build_volumes():
    """根据大纲文本自动解析卷结构和章节"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    result = state.project.auto_build_volumes_from_outline()
    return result

@router.post("/ai-split-volumes")
def ai_split_volumes(request: AIVolumeSplitRequest):
    """AI智能分卷：根据全书大纲自动生成卷结构和章节分配"""
    if not state.project:
        logger.warning("AI分卷失败: 没有打开的项目")
        return {"ok": False, "error": "没有打开的项目"}
    logger.info(f"AI分卷请求: volume_count={request.volume_count}, inspiration={request.inspiration[:50] if request.inspiration else '无'}")
    import re
    try:
        from backend.ai_client import AIClient
        ai = AIClient()

        ctx_parts = []

        # 全书大纲
        novel_outline = state.project.get_novel_outline()
        story_arc_text = ""
        if novel_outline:
            if isinstance(novel_outline, dict):
                parts = []
                if novel_outline.get('theme'):
                    parts.append("【主题】" + novel_outline['theme'])
                if novel_outline.get('core_conflict'):
                    parts.append("【核心冲突】" + novel_outline['core_conflict'])
                if novel_outline.get('story_arc'):
                    story_arc_text = novel_outline['story_arc']
                    parts.append("【故事走向】" + novel_outline['story_arc'])
                if novel_outline.get('world_anchor'):
                    parts.append("【世界观锚点】" + str(novel_outline['world_anchor'])[:500])
                if novel_outline.get('character_arcs'):
                    arc_lines = []
                    for arc in novel_outline['character_arcs'][:8]:
                        if isinstance(arc, dict):
                            arc_lines.append(f"  - {arc.get('character','')}: {arc.get('arc','')}")
                        elif isinstance(arc, str):
                            arc_lines.append(f"  - {arc}")
                    if arc_lines:
                        parts.append("【角色弧光】\n" + "\n".join(arc_lines))
                if novel_outline.get('ending'):
                    parts.append("【结局指引】" + novel_outline['ending'])
                if novel_outline.get('tone'):
                    parts.append("【基调】" + novel_outline['tone'])
                nol_text = "\n".join(parts)
                if nol_text:
                    ctx_parts.append("【全书大纲】\n" + nol_text[:3000])
            elif isinstance(novel_outline, str):
                story_arc_text = novel_outline
                ctx_parts.append("【全书大纲】\n" + novel_outline[:3000])

        # 世界观设定
        try:
            from backend.generator import WorldBuilder
            wb = WorldBuilder(state.project.world_settings or {})
            world_text = wb.to_prompt()
            if world_text:
                ctx_parts.append("【世界观设定】\n" + world_text[:1500])
            # 自由格式世界观
            ws = getattr(state.project, 'world_settings', None) or {}
            if ws and isinstance(ws, dict):
                ws_lines = [f"- {k}：{v}" for k, v in ws.items() if v and str(v).strip()]
                if ws_lines:
                    ctx_parts.append("【自由格式世界观设定】\n" + "\n".join(ws_lines[:1000]))
        except Exception:
            pass

        # 人物设定
        try:
            chars = state.project.characters or []
            if chars:
                char_lines = []
                for c in chars[:10]:
                    name = c.get('name', '')
                    identity = c.get('identity', '')
                    faction = c.get('faction', '')
                    goal = c.get('goal', '')
                    desc = f"- {name}"
                    if identity: desc += f"（{identity}）"
                    if faction: desc += f" 阵营：{faction}"
                    if goal: desc += f" 目标：{goal}"
                    char_lines.append(desc)
                if char_lines:
                    ctx_parts.append("【人物设定】\n" + "\n".join(char_lines[:1500]))
        except Exception:
            pass

        if request.inspiration:
            ctx_parts.append("【灵感碎片】\n" + request.inspiration[:1000])

        if not ctx_parts:
            return {"ok": False, "error": "没有足够的全书大纲信息"}

        # 优先级：请求参数 > 用户设定章数 > meta.total_chapters > meta.chapter_count > 实际章节数 > 正则兜底
        # planned_chapters 是用户在建项目时设定的章数，不会被AI分卷覆盖
        total_chapters = request.total_chapters or state.project.meta.get("planned_chapters", 0) or state.project.meta.get("total_chapters", 0) or state.project.meta.get("chapter_count", 0)
        if total_chapters == 0:
            total_chapters = len(state.project.chapters or [])
        if total_chapters == 0 and story_arc_text:
            range_matches = re.findall(r'第\s*(\d+)\s*[\-~到至]\s*(\d+)\s*章', story_arc_text)
            if range_matches:
                for start_str, end_str in range_matches:
                    total_chapters = max(total_chapters, int(end_str))
            single_matches = re.findall(r'第\s*(\d+)\s*章', story_arc_text)
            if single_matches:
                total_chapters = max(total_chapters, max(int(m) for m in single_matches))
        if total_chapters == 0:
            total_chapters = 5

        # 默认每卷 3-6 章，计算合理卷数
        suggested_vol_count = max(2, min(10, round(total_chapters / 4)))
        vol_count = request.volume_count or suggested_vol_count
        if vol_count < 2:
            vol_count = 2
        if vol_count > 10:
            vol_count = 10

        # 每卷平均章节数
        avg_chapters_per_vol = max(2, round(total_chapters / vol_count))

        prompt = f"""请根据以下全书大纲信息，将小说划分为 {vol_count} 个卷，并为每卷分配章节范围和大纲内容。

注意：全书大纲共 {total_chapters} 章，请严格按照这个总章节数分配，不要混淆"幕"和"章"的概念。

{chr(10).join(ctx_parts)}

要求：
1. 输出格式必须为JSON，不要包含Markdown标记或其他文本
2. JSON结构：{{"volumes": [{{"title": "卷名", "summary": "本卷概要", "theme": "核心主题", "chapters": ["第X章·标题", "第Y章·标题", ...], "chapter_count": N}}]}}
3. 全书总章节数必须为 {total_chapters} 章
4. 共分为 {vol_count} 卷，每卷大约 {avg_chapters_per_vol} 章
5. 章节编号必须从第1章连续到第{total_chapters}章，不能中断或重复
6. 卷名要有文学感，如"第一卷·风起"、"第二卷·云涌"
7. 每卷概要 50-100 字，概括本卷核心冲突和转折点
8. 章节标题要有吸引力，能体现该章核心事件"""

        content = ai.generate(prompt, temperature=0.7)
        if not content:
            return {"ok": False, "error": "AI生成失败"}
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return {"ok": False, "error": "AI输出格式错误"}

        try:
            import json
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return {"ok": False, "error": "AI输出解析失败"}

        volumes = data.get("volumes", [])
        if not volumes or not isinstance(volumes, list):
            return {"ok": False, "error": "AI未返回有效的卷结构"}

        # 收集 AI 返回的所有章节标题文本（去掉原有编号）
        raw_titles = []
        for vol in volumes:
            for ch_title in vol.get("chapters", []):
                if isinstance(ch_title, dict):
                    text = ch_title.get("title", ch_title.get("text", ""))
                else:
                    text = str(ch_title)
                # 去掉 "第X章·" / "第X章 " 等前缀
                text = re.sub(r'^第\s*\d+\s*[章回话节][·\.\s]*', '', text).strip()
                if text:
                    raw_titles.append(text)

        # 如果 AI 返回的标题数量不足，用默认标题补全
        while len(raw_titles) < total_chapters:
            raw_titles.append(f"第{len(raw_titles) + 1}章")

        # 如果过多，截断
        raw_titles = raw_titles[:total_chapters]

        # 检查是否有已有章节内容需要保留
        existing_chapters = state.project.chapters or []
        existing_map = {ch["index"]: ch for ch in existing_chapters} if existing_chapters else {}

        # 重建章节（保留已有内容）
        state.project.chapters = []
        for i in range(total_chapters):
            ch_num = i + 1
            title_text = raw_titles[i] if i < len(raw_titles) else f"第{ch_num}章"
            ch_title_text = f"第{ch_num}章·{title_text}"

            if ch_num in existing_map:
                ch = dict(existing_map[ch_num])
                ch["title"] = ch_title_text
            else:
                ch = {
                    "index": ch_num,
                    "title": ch_title_text,
                    "word_count": 0,
                    "created": time.strftime("%Y-%m-%d %H:%M"),
                    "outline": "",
                    "status": "draft",
                    "pov": "",
                    "scene_labels": [],
                }
            state.project.chapters.append(ch)

        # 重建卷结构
        state.project.volumes = []
        base_per_vol = total_chapters // vol_count
        extra = total_chapters % vol_count
        ch_num = 0

        for vi, vol in enumerate(volumes):
            vol_ch_count = base_per_vol + (1 if vi < extra else 0)
            chapters_in_vol = []

            for ci in range(vol_ch_count):
                if ch_num >= total_chapters:
                    break
                ch_num += 1
                chapters_in_vol.append(ch_num)

            state.project.volumes.append({
                "index": vi,
                "title": vol.get("title", f"第{vi + 1}卷"),
                "outline": {
                    "summary": vol.get("summary", ""),
                    "theme": vol.get("theme", ""),
                    "key_events": vol.get("key_events", []) if isinstance(vol.get("key_events"), list) else [],
                    "character_arcs": vol.get("character_arcs", []) if isinstance(vol.get("character_arcs"), list) else []
                },
                "chapters": chapters_in_vol,
            })

        # 回写 meta
        state.project.meta["total_chapters"] = total_chapters
        state.project._dirty = True
        state.project._save_meta()

        logger.info(f"AI分卷成功: {len(state.project.volumes)}卷, {len(state.project.chapters)}章")
        return {"ok": True, "volumes": state.project.get_volumes(), "chapter_count": len(state.project.chapters)}

    except Exception as e:
        import traceback
        logger.error(f"AI分卷失败: {e}")
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

@router.post("/volume/{vol_index}/add-chapter")
def add_chapter_to_volume(vol_index: int, data: VolumeChapterRequest):
    """添加章节到指定卷"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.add_chapter_to_volume(vol_index, data.chapter_index)
    return {"ok": ok}

@router.post("/volume/{vol_index}/remove-chapter")
def remove_chapter_from_volume(vol_index: int, data: VolumeChapterRequest):
    """从指定卷移除章节"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.remove_chapter_from_volume(vol_index, data.chapter_index)
    return {"ok": ok}

@router.post("/volume/{vol_index}/set-chapters")
def set_volume_chapters(vol_index: int, data: VolumeChaptersRequest):
    """设置卷的章节列表"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    ok = state.project.set_volume_chapters(vol_index, data.chapter_indices)
    return {"ok": ok}
