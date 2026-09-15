# -*- coding: utf-8 -*-
import threading
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.services.project_service import state
from backend.api_models import err, ErrorCode
import logging

logger = logging.getLogger(__name__)

from ._utils import ChapterOutlineSave

router = APIRouter()

@router.post("/outline")
def save_chapter_outline_endpoint(data: ChapterOutlineSave):
    from backend.services.chapter_service import save_chapter_outline
    return save_chapter_outline(data.dict())


# ═══════════════════════════════════════════════════════════════════
# 规划可视化路由 - /api/chapter/reorder, /api/chapter/{idx}/status, /api/chapter/{idx}/pov
# + /api/planning/matrix, /api/planning/timeline
# ═══════════════════════════════════════════════════════════════════

class ChapterReorder(BaseModel):
    from_index: int
    to_index: int
    from_vol: Optional[int] = None
    to_vol: Optional[int] = None

class ChapterStatusUpdate(BaseModel):
    status: str

class ChapterPovUpdate(BaseModel):
    pov: str

class ChapterSceneLabelsUpdate(BaseModel):
    scene_labels: list = []

@router.post("/reorder")
def reorder_chapter(data: ChapterReorder):
    """重排章节顺序（持久化到 chapters 数组 + volumes + 文件名）"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = state.project.reorder_chapter(
        data.from_index, data.to_index, data.from_vol, data.to_vol
    )
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, "重排失败：索引越界或无章节")
    return {
        "ok": True,
        "chapters": state.project.chapters,
        "volumes": state.project.get_volumes() if hasattr(state.project, "get_volumes") else state.project.volumes,
    }

@router.post("/{index}/status")
def update_chapter_status(index: int, data: ChapterStatusUpdate):
    """更新章节状态：draft / revised / final"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = state.project.update_chapter_status(index, data.status)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, "更新失败：索引越界或状态值非法")

    # 定稿后处理：时间线锁定 + AI对照检查 + 单章蒸馏 + state_memory 写入
    # 改为异步执行，避免前端等待AI调用超时
    if data.status == "final":
        chapter_title = state.project.chapters[index].get("title", "") if 0 <= index < len(state.project.chapters) else ""
        logger.info(f"章节[{index+1}]状态变为final，开始异步定稿后处理...")
        threading.Thread(
            target=_finalize_chapter,
            args=(index,),
            daemon=True,
            name=f"finalize-chapter-{index}"
        ).start()

    return {"ok": True, "status": data.status}

def _finalize_chapter(index: int):
    """定稿后处理：时间线锁定 + AI对照检查 + 单章蒸馏 + state_memory 写入。

    失败静默处理，不阻塞定稿主流程。
    """
    project = state.project
    project_dir = project.project_dir

    # 1. 获取章节正文和标题
    content = project.get_content(index)
    title = project.chapters[index].get("title", "") if 0 <= index < len(project.chapters) else ""
    chapter_index_1b = index + 1  # 转为 1-based

    if not content or len(content) < 100:
        logger.warning(f"第{chapter_index_1b}章内容过短，跳过定稿后处理")
        return

    logger.info(f"[定稿后处理] 第{chapter_index_1b}章 '{title}' 开始...")

    # 2. 时间线锁定：确保 timeline 结构存在，记录计划
    from backend.timeline_service import TimelineService
    tsvc = TimelineService(project_dir)
    # 获取章节大纲作为 planned
    outline = project.chapters[index].get("outline", "") if 0 <= index < len(project.chapters) else ""
    # 计算卷索引：优先用 volume_index 字段，否则按每20章一卷
    vol_idx = project.chapters[index].get("volume_index")
    if vol_idx is None:
        vol_idx = index // 20
    # 收集所有章节（避免删除其他章节的定稿状态）
    all_chapters = []
    for ci, ch in enumerate(project.chapters):
        ch_idx = ch.get("index", ci)
        ch_vol = ch.get("volume_index")
        if ch_vol is None:
            ch_vol = ci // 20
        all_chapters.append({
            "index": ch_idx,
            "volume_index": ch_vol,
            "title": ch.get("title", "")
        })

    tsvc.ensure_structure(
        [{"index": vol_idx, "title": ""}],
        all_chapters
    )
    tsvc.update_planned(vol_idx, chapter_index_1b, outline)

    # 3. AI对照检查：自动生成实际摘要和偏离项
    try:
        from backend.ai_client import AIClient
        import re as _re
        import json as _json

        prompt = (
            "你是一位专业的小说编辑和质量审核员。请对照以下「章节计划」和「实际写出的正文」，"
            "从以下维度进行全面检查和分析：\n\n"
            "## 检查维度\n"
            "1. **计划vs实际偏离**：检查实际内容是否符合章节计划\n"
            "2. **设定冲突**：检查是否存在设定矛盾、逻辑冲突、前后不一致\n"
            "3. **内容重复**：检查是否存在与前文重复的情节或描写\n"
            "4. **战力崩坏**：检查是否存在境界跳跃、战力不合理等问题\n"
            "5. **AI味问题**：检查是否存在套话、公式化描写、叙述者越权、塑料感\n"
            "6. **逻辑漏洞**：检查情节发展是否合理，角色行为是否有逻辑\n"
            "7. **人设不符**：检查角色行为是否符合设定的性格和身份\n"
            "8. **章节衔接**：检查与前后章节的衔接是否连贯\n\n"
            "## 章节计划\n%s\n\n"
            "## 实际正文\n%s\n\n"
            "请输出 JSON，格式如下：\n"
            "{\n"
            '  "actual_summary": "用一句话概括实际写出的内容",\n'
            '  "divergences": [\n'
            '    {"type": "推迟/提前/新增/删除/修改/冲突/重复/战力/AI味/逻辑/人设/连贯", "item": "具体内容", "note": "说明"}\n'
            "  ]\n"
            "}\n"
            "如果没有问题，divergences 为空数组 []。只返回 JSON，不要任何解释文字。"
            % (outline or "（无计划）", content[:8000])
        )

        ai = AIClient()
        raw = ai.generate_for_task(prompt, task_type="summary",
                                   temperature=0.3, max_tokens=2048)

        if raw and not raw.startswith("[生成失败") and not raw.startswith("[错误"):
            data = None
            for pattern in [r"```json\s*\n(.*?)\n```", r"```json\s*\n([\s\S]+)", r"\{[\s\S]*\}"]:
                m = _re.search(pattern, raw, _re.DOTALL)
                if m:
                    try:
                        data = _json.loads(m.group(1) if pattern != r"\{[\s\S]*\}" else m.group(0))
                        break
                    except Exception:
                        continue
            if data is None:
                try:
                    data = _json.loads(raw)
                except Exception:
                    data = None

            if data:
                divergences = data.get("divergences", [])
                for d in divergences:
                    d.setdefault("status", "待处理")
                tsvc.update_actual(
                    vol_idx, chapter_index_1b,
                    data.get("actual_summary", content[:200]),
                    divergences
                )
                logger.info(f"第{chapter_index_1b}章AI对照完成，发现{len(divergences)}处问题")
            else:
                # AI返回无法解析，用正文摘要作为actual
                actual_summary = content[:200].replace("\n", " ") + ("..." if len(content) > 200 else "")
                tsvc.update_actual(vol_idx, chapter_index_1b, actual_summary)
                logger.warning(f"第{chapter_index_1b}章AI返回无法解析，仅保存摘要")
        else:
            # AI调用失败，用正文摘要作为actual
            actual_summary = content[:200].replace("\n", " ") + ("..." if len(content) > 200 else "")
            tsvc.update_actual(vol_idx, chapter_index_1b, actual_summary)
            logger.warning(f"第{chapter_index_1b}章AI对照调用失败，仅保存摘要")
    except Exception as e:
        logger.warning(f"第{chapter_index_1b}章AI对照异常: {e}")
        # 异常时用正文摘要作为actual
        try:
            actual_summary = content[:200].replace("\n", " ") + ("..." if len(content) > 200 else "")
            tsvc.update_actual(vol_idx, chapter_index_1b, actual_summary)
        except Exception:
            pass

    # 4. 单章蒸馏
    from backend.services.distill_service import distill_single_chapter, save_state_memory
    state_data = distill_single_chapter(content, chapter_index_1b)

    # 5. 写入 state_memory
    save_state_memory(project_dir, chapter_index_1b, state_data, project=project)

    # 6. 将蒸馏数据整合到时间线
    try:
        tsvc.update_distill(
            vol_idx, chapter_index_1b,
            characters=state_data.get("characters", []),
            events=state_data.get("events", []),
            foreshadowing=state_data.get("foreshadowing", {}),
            new_settings=state_data.get("new_settings", []),
            bridge=state_data.get("bridge", {}),
        )
        # 优先用蒸馏events作为actual（蒸馏后的内容对照）
        if state_data.get("events"):
            events_text = "；".join(state_data["events"])
            tsvc.update_actual(vol_idx, chapter_index_1b, events_text)
        logger.info(f"第{chapter_index_1b}章蒸馏数据已整合到时间线")
    except Exception as e:
        logger.warning(f"第{chapter_index_1b}章蒸馏数据整合到时间线失败: {e}")

    # 6.5 伏笔自动激活：临近回收章节的 planted 伏笔自动变 active
    try:
        from backend.services.project_service import state as _state
        if _state.ledger is not None:
            activated = _state.ledger.activate_nearby_hooks(chapter_index_1b, window=3)
            if activated > 0:
                logger.info(f"第{chapter_index_1b}章自动激活{activated}条临近回收的伏笔")
    except Exception as e:
        logger.warning(f"第{chapter_index_1b}章伏笔自动激活失败: {e}")

    # 7. Novel Engine 自动一致性校验（纯规则，不耗 token，失败不阻塞）
    try:
        from backend.novel_engine import NovelEngineCore
        from backend.novel_engine.scheduler.consistency_checker import CheckLevel
        engine = NovelEngineCore()

        # 7.1 世界观规则守卫：校验正文是否违反世界观规则
        rule_violations = []
        try:
            guard = engine.rule_guard
            # 从 TruthLedger 读取角色名用于角色边界检查
            from backend.services.project_service import state as _state
            char_names = list(_state.ledger.character_states.keys()) if _state.ledger else []
            violations = guard.check_narrative(content, characters=char_names)
            rule_violations = [
                {
                    "rule_id": v.rule_id,
                    "rule_name": v.rule_name,
                    "level": v.level.value if hasattr(v.level, 'value') else str(v.level),
                    "message": v.message,
                    "context": v.context,
                    "fix_suggestion": v.fix_suggestion,
                }
                for v in violations
            ]
            if rule_violations:
                logger.info(f"第{chapter_index_1b}章世界观规则守卫发现{len(rule_violations)}条违规")
        except Exception as e:
            logger.warning(f"第{chapter_index_1b}章世界观规则守卫失败: {e}")

        # 7.2 全局一致性校验
        consistency_issues = []
        try:
            checker = engine.consistency_checker
            issues = checker.check_all(level=CheckLevel.WARNING)
            consistency_issues = [
                {
                    "check": issue.check_type,
                    "level": issue.level.value if hasattr(issue.level, 'value') else str(issue.level),
                    "message": issue.message,
                    "details": issue.details,
                    "affected": issue.affected_entities,
                }
                for issue in issues
            ]
            if consistency_issues:
                logger.info(f"第{chapter_index_1b}章一致性校验发现{len(consistency_issues)}条问题")
        except Exception as e:
            logger.warning(f"第{chapter_index_1b}章一致性校验失败: {e}")

        # 7.3 保存到章节元数据
        if rule_violations or consistency_issues:
            try:
                chapter_data = project.chapters[index] if 0 <= index < len(project.chapters) else {}
                chapter_data["novel_engine_check"] = {
                    "chapter": chapter_index_1b,
                    "rule_violations": rule_violations,
                    "consistency_issues": consistency_issues,
                    "total_issues": len(rule_violations) + len(consistency_issues),
                }
                project.save_all()
            except Exception as e:
                logger.warning(f"第{chapter_index_1b}章保存NovelEngine检查结果失败: {e}")

        logger.info(f"[定稿后处理] 第{chapter_index_1b}章 NovelEngine 校验完成，"
                    f"规则违规:{len(rule_violations)}条，一致性问题:{len(consistency_issues)}条")
    except Exception as e:
        logger.warning(f"第{chapter_index_1b}章NovelEngine校验异常: {e}")


@router.post("/{index}/pov")
def update_chapter_pov(index: int, data: ChapterPovUpdate):
    """设置章节 POV 角色"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = state.project.update_chapter_pov(index, data.pov)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, "更新失败：索引越界")
    return {"ok": True, "pov": data.pov}

@router.post("/{index}/scene-labels")
def update_chapter_scene_labels(index: int, data: ChapterSceneLabelsUpdate):
    """更新章节场景标签"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = state.project.update_chapter_scene_labels(index, data.scene_labels)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, "更新失败：索引越界")
    return {"ok": True, "scene_labels": data.scene_labels}


# 规划视图专用路由（独立前缀 /api/planning）
