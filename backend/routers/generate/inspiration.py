# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import InspirationToBlueprintRequest, InspirationToNovelOutlineRequest
from .outline import _get_current_vol_position

router = APIRouter()

@router.post("/inspiration-to-blueprint")
def inspiration_to_blueprint(data: InspirationToBlueprintRequest):
    """灵感碎片 → 结构化章节大纲（blueprint）

    用户输入零散的灵感/想法，AI结合全书大纲、前后章节上下文，
    将灵感扩展为完整的起承转合结构化章节大纲。
    """
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    inspiration = data.inspiration.strip()
    if not inspiration:
        return err(ErrorCode.INTERNAL_ERROR, "请先输入灵感碎片内容")
    chapter_index = data.chapter_index
    try:
        gen = get_generator()

        # 故事弧位置提示（与批量生成保持一致）
        total = len(state.project.chapters or [])
        progress = (chapter_index + 1) / total if total > 0 else 0
        ch_num = chapter_index + 1

        # 检测当前章节所在卷的位置
        current_vol_is_last = _get_current_vol_position(chapter_index)

        # 判断是否是开放结局模式
        is_extended = False
        if chapter_index > 0 and state.project.chapters and chapter_index < len(state.project.chapters):
            prev_ch = state.project.chapters[chapter_index - 1]
            if prev_ch.get('blueprint', {}).get('extended'):
                is_extended = True

        if is_extended:
            if current_vol_is_last and progress > 0.85:
                arc_stage = "【当前卷收尾】这是当前卷的后期，可以收束本卷的主要冲突，但全书故事仍在继续。可以留新的悬念引出下一卷。"
            else:
                arc_stage = "【故事延续中】故事正在连载中，保持张力和悬念。本卷要有阶段性成果，但为后续发展留空间。"
        elif current_vol_is_last and progress > 0.85:
            arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔，交代角色结局。"
        elif progress <= 0.15:
            arc_stage = "【开局阶段】这是故事开头，需要建立世界观、引入主角、设定初始冲突。节奏可以稍慢，重在铺垫。"
        elif progress <= 0.4:
            arc_stage = "【发展阶段】故事正在展开，冲突逐步升级，角色关系深化。保持节奏推进，不要过早进入高潮。"
        elif progress <= 0.7:
            arc_stage = "【上升阶段】冲突加剧，stakes提高，角色面临更大挑战。为高潮做铺垫，伏笔开始回收。"
        elif progress <= 0.9:
            arc_stage = "【高潮阶段】故事进入最紧张的部分，主要冲突爆发，角色做出关键抉择。节奏紧凑，张力拉满。"
        else:
            arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔，交代角色结局。"

        # 构建上下文：在原有上下文基础上，把灵感碎片作为核心主线
        base_context = data.context
        # 注入故事弧阶段
        arc_context = "\n\n## 【故事弧定位】\n" + arc_stage + "\n"
        # 灵感专用的增强上下文
        inspiration_context = base_context + arc_context + "\n## 【核心灵感碎片 — 本章必须围绕此主线展开】\n" + inspiration + "\n\n## 要求\n1. 以上述灵感碎片为核心主线，扩展为完整的章节大纲\n2. 灵感碎片中的场景、事件、人物关系必须成为本章的关键情节\n3. 在灵感基础上补充起承转合的完整结构（开场、发展、高潮、收尾）\n4. 保持与全书大纲和前后章节的衔接\n5. 不要遗漏灵感碎片中的任何关键元素\n6. 灵感内容需要符合当前故事弧阶段的特点（见上方【故事弧定位】）"

        result = gen.generate_chapter_outline(
            data.title,
            inspiration_context,
            chapter_index=chapter_index
        )
        ol_text = result.get("outline_text") or result.get("raw", "")
        bp = result.get("blueprint")
        # 保存到后端
        if chapter_index >= 0:
            save_data = {"index": chapter_index, "outline": ol_text}
            if bp:
                save_data["blueprint"] = bp
            # 在blueprint中标记灵感来源
            if bp and isinstance(bp, dict):
                bp["inspiration_source"] = inspiration[:200]
            try:
                from backend.services.chapter_service import save_chapter_outline as _save
                _save(save_data)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("save_chapter_outline failed: %s", e)
        return {
            "ok": True,
            "outline": ol_text,
            "blueprint": bp,
            "raw": result.get("raw", "")
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.post("/inspiration-to-novel-outline")
def inspiration_to_novel_outline(data: InspirationToNovelOutlineRequest):
    """灵感碎片 → 全书大纲

    用户输入零散的灵感/想法/构思，AI结合世界观和角色设定，
    将灵感扩展为完整的全书大纲。
    """
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    inspiration = data.inspiration.strip()
    if not inspiration:
        return err(ErrorCode.INTERNAL_ERROR, "请先输入灵感碎片内容")
    title = data.title
    genre = data.genre
    length = data.length
    try:
        gen = get_generator()
        result = gen.generate_outline(title, genre, length, inspiration=inspiration)
        return {"ok": True, "outline": result}
    except Exception as e:
        import traceback; traceback.print_exc()
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")
