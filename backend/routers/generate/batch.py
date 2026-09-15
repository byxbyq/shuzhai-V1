# -*- coding: utf-8 -*-
import re
import time
import uuid
import logging
import threading
from typing import Dict, Optional
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import CancelGenerateRequest

router = APIRouter()

class GenerationTask:
    """单个生成任务的状态"""
    def __init__(self, task_id: str, total: int):
        self.task_id = task_id
        self.status = "pending"  # pending / running / completed / failed / cancelled
        self.total = total
        self.current = 0
        self.results = []
        self.error = ""
        self.started_at = time.time()
        self.finished_at = None
        self._cancel_flag = False

    def cancel(self):
        self._cancel_flag = True
        self.status = "cancelled"

    @property
    def is_cancelled(self):
        return self._cancel_flag

    def to_dict(self) -> dict:
        elapsed = (self.finished_at or time.time()) - self.started_at
        eta_seconds = 0
        if self.current > 0 and self.status == "running":
            avg = elapsed / self.current
            eta_seconds = int(avg * (self.total - self.current))
        return {
            "task_id": self.task_id,
            "status": self.status,
            "total": self.total,
            "current": self.current,
            "progress": round(self.current / max(self.total, 1) * 100, 1),
            "elapsed_seconds": int(elapsed),
            "eta_seconds": eta_seconds,
            "results": self.results[-5:] if self.status == "running" else self.results,
            "error": self.error,
        }

class TaskManager:
    """全局限程 + 任务注册表（简化版，单任务串行）"""
    def __init__(self):
        self._tasks: Dict[str, GenerationTask] = {}
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

    def create_task(self, total: int) -> GenerationTask:
        task_id = uuid.uuid4().hex[:12]
        task = GenerationTask(task_id, total)
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[GenerationTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def run_async(self, task: GenerationTask, target_fn, *args, **kwargs):
        """在后台线程中运行任务"""
        def _runner():
            try:
                target_fn(task, *args, **kwargs)
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.exception(f"任务 {task.task_id} 失败")
            finally:
                task.finished_at = time.time()
                if task.status == "running":
                    task.status = "completed"

        task.status = "running"
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        self._worker_thread = t
        return task

_task_manager = TaskManager()

def _generate_all_chapters_worker(task: GenerationTask):
    """后台执行全章生成的工作函数"""
    if not state.project:
        task.status = "failed"
        task.error = "没有打开的项目"
        return

    gen = get_generator()
    gen.reload_world()
    chapters = state.project.chapters or []

    for i in range(len(chapters)):
        if task.is_cancelled:
            logger.info(f"任务 {task.task_id} 被取消，已完成 {task.current}/{task.total} 章")
            return

        ch = chapters[i]
        title = ch.get("title", "第%d章" % (i + 1))
        outline = ch.get("outline", "")
        blueprint = ch.get("blueprint", {})

        # 构建上下文
        context = ""
        if i > 0:
            try:
                context = state.project.get_previous_context(chapter_index=i)
                if context:
                    context = "前一章全文：\n" + context
            except Exception:
                pass

        # 蓝图转大纲
        if not outline and blueprint:
            parts = []
            intro = blueprint.get("intro", {})
            if intro:
                parts.append("【起】%s — %s" % (intro.get("scene", ""), intro.get("trigger", "")))
            for dev in blueprint.get("development", []):
                parts.append("【承】%s：%s" % (dev.get("scene", ""), dev.get("event", "")))
            climax = blueprint.get("climax", {})
            if climax:
                parts.append("【转】%s — %s" % (climax.get("conflict", ""), climax.get("twist", "")))
            ending = blueprint.get("ending", {})
            if ending:
                parts.append("【合】%s → %s" % (ending.get("new_state", ""), ending.get("next_hook", "")))
            outline = "\n".join(parts)

        # 生成 + 校验
        try:
            result = gen.generate_and_validate(
                title, outline, context,
                chapter_index=i, max_retries=2,
                use_distilled_memory=True
            )
        except Exception as e:
            result = {"ok": False, "content": "", "warning": f"生成异常: {e}"}

        content = result.get("content", "")

        # 保存
        if content:
            try:
                state.project.set_content(content, i)
            except Exception as e:
                logger.warning("save chapter %d failed: %s", i + 1, e)

            # 状态提取
            try:
                gen.apply_state_extraction(content, i + 1, title)
            except Exception as e:
                logger.warning("state extraction chapter %d failed: %s", i + 1, e)

            # 向量记忆注入
            try:
                from backend.services.project_service import get_vector_memory
                from backend.services.vector_memory import MemoryType
                vm = get_vector_memory()
                if vm:
                    paragraphs = [p.strip() for p in content.split('\n\n')
                                  if p.strip() and len(p.strip()) > 50]
                    for pi, para in enumerate(paragraphs):
                        vm.add_memory(
                            content=para,
                            memory_type=MemoryType.EVENT,
                            importance=0.6,
                            metadata={"chapter": i + 1, "chapter_title": title, "paragraph": pi}
                        )
            except Exception as e:
                logger.warning("vector memory chapter %d failed: %s", i + 1, e)

        ch_result = {
            "chapter": i + 1,
            "title": title,
            "ok": result.get("ok", False),
            "word_count": len(content),
            "warning": result.get("warning", "")
        }
        task.results.append(ch_result)
        task.current = i + 1

    # 最终保存
    try:
        state.project.save_all()
    except Exception as e:
        logger.warning("save_all failed: %s", e)

@router.post("/all-chapter-outlines")
def generate_all_chapter_outlines():
    """一键生成全部章节大纲"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        gen = get_generator()
        gen.reload_world()
        results = []
        chapters = state.project.chapters or []
        novel_outline = state.project.novel_outline or {}  # 现在是dict格式
        world_text = gen.world.to_prompt()
        chars = state.project.characters or []

        # 从新的 novel_outline（dict）构建概括性上下文
        novel_summary_text = ""
        if isinstance(novel_outline, dict) and novel_outline:
            parts = []
            if novel_outline.get('theme'):
                parts.append("【主题】" + novel_outline['theme'])
            if novel_outline.get('core_conflict'):
                parts.append("【核心冲突】" + novel_outline['core_conflict'])
            if novel_outline.get('story_arc'):
                parts.append("【故事走向】" + novel_outline['story_arc'])
            if novel_outline.get('world_anchor'):
                parts.append("【世界观锚点】" + str(novel_outline['world_anchor'])[:500])
            if novel_outline.get('character_arcs'):
                arc_lines = []
                for arc in novel_outline['character_arcs']:
                    if isinstance(arc, dict):
                        arc_lines.append(f"  - {arc.get('character','')}: {arc.get('arc','')}")
                    elif isinstance(arc, str):
                        arc_lines.append(f"  - {arc}")
                if arc_lines:
                    parts.append("【角色弧光】\n" + "\n".join(arc_lines))
            if novel_outline.get('key_hooks'):
                hook_lines = []
                for h in novel_outline['key_hooks']:
                    hook_lines.append(f"  - {h}" if isinstance(h, str) else f"  - {str(h)}")
                if hook_lines:
                    parts.append("【关键伏笔】\n" + "\n".join(hook_lines))
            if novel_outline.get('ending'):
                parts.append("【结局指引】" + novel_outline['ending'])
            if novel_outline.get('tone'):
                parts.append("【基调】" + novel_outline['tone'])
            novel_summary_text = "\n".join(parts)

        for i in range(len(chapters)):
            ch = chapters[i]
            title = ch.get("title", "第%d章" % (i+1))

            # 构建上下文
            ctx = "\n当前是第%d章（共%d章）。" % (i+1, len(chapters))

            # 故事弧位置提示：基于当前卷定位 + 全书进度
            total = len(chapters)
            progress = (i + 1) / total if total > 0 else 0

            # 检测当前章节所在卷的位置
            ch_num = i + 1
            current_vol_is_last = False
            current_vol_is_first = False
            try:
                volumes = state.project.volumes or [] if state.project else []
                if volumes:
                    for vi, vol in enumerate(volumes):
                        vol_chs = vol.get('chapters', [])
                        if ch_num in vol_chs:
                            current_vol_is_first = (vi == 0)
                            current_vol_is_last = (vi == len(volumes) - 1)
                            break
            except Exception:
                pass

            # 判断是否是"开放结局"模式（章节数被扩展过）
            # 如果最后一章的blueprint里有"extended"标记，说明故事被延长了
            is_extended = False
            if i > 0 and chapters[i-1].get('blueprint', {}).get('extended'):
                is_extended = True

            if is_extended:
                # 开放结局模式：不强制结局，保持故事张力
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
            ctx += "\n" + arc_stage + "\n"

            if novel_summary_text:
                ctx += "\n【全书大纲】\n" + novel_summary_text + "\n"
            # 世界观设定
            if world_text:
                ctx += "\n【世界观设定】\n" + world_text[:800] + "\n"
            if chars:
                ctx += "\n主要人物：" + "; ".join([c.get("name","")+"("+c.get("identity","")+")" for c in chars[:8]]) + "\n"
                # 带上人物详细档案摘要
                char_details = []
                for c in chars[:6]:
                    detail = c.get("name","")
                    if c.get("personality"): detail += "（性格：" + c["personality"][:50] + "）"
                    if c.get("background"): detail += "（背景：" + c["background"][:80] + "）"
                    if c.get("goal"): detail += "（目标：" + c["goal"][:50] + "）"
                    char_details.append(detail)
                if char_details:
                    ctx += "人物档案：\n" + "\n".join(char_details) + "\n"
            # 前一章大纲（完整传入，不截断）
            if i > 0:
                prev_ol = chapters[i-1].get("outline", "")
                if prev_ol:
                    ctx += "\n【前一章大纲（第%d章）】\n" % i + (prev_ol if isinstance(prev_ol, str) else str(prev_ol)) + "\n"
                # 前一章blueprint关键信息
                prev_bp = chapters[i-1].get("blueprint", "")
                if prev_bp:
                    bp_text = prev_bp if isinstance(prev_bp, str) else str(prev_bp)
                    # 提取blueprint中的ending和next_hook
                    import re as _re
                    ending_m = _re.search(r'"ending"[\s\S]*?"text"\s*:\s*"([^"]+)"', bp_text)
                    hook_m = _re.search(r'"next_hook"\s*:\s*"([^"]+)"', bp_text)
                    if ending_m:
                        ctx += "前一章结尾状态：%s\n" % ending_m.group(1)[:200]
                    if hook_m:
                        ctx += "前一章钩子/悬念：%s\n" % hook_m.group(1)[:200]
            ctx += "\n请为第%d章生成大纲。%s每章内容必须不同。" % (i+1, "必须与前一章自然衔接。" if i > 0 else "这是第一章，需要有开场感。")
            if i == 0:
                ctx += "\n\n【重要】请在返回内容的最前面，先输出一个【故事总览】段落（200-300字），概述全书的主要角色、核心冲突和故事走向。然后再输出本章的JSON大纲。\n"

            # 最后一章强制完结指令（以实际生成的章节数为准）
            if i == len(chapters) - 1 and len(chapters) > 0:
                ctx += ("\n\n⚠️ 【重要：本章是最后一章（第%d章），必须完结】\n"
                        "1. 本章必须是整个故事的结局，所有主要伏笔必须收束\n"
                        "2. 主角与反派的对抗必须有明确结果（胜负已分）\n"
                        "3. ending的new_state必须是最终结局状态，next_hook不能留悬念\n"
                        "4. 不能有'未完''继续''下一''才刚开始'等开放结局词\n"
                        "5. 故事必须在本章画上句号\n") % (i+1)

            result = gen.generate_chapter_outline(title, ctx, chapter_index=i)
            bp = result.get("blueprint")
            ol_text = result.get("outline_text") or result.get("raw", "")

            # 过滤空内容或错误消息，避免覆盖已有大纲
            has_valid_outline = ol_text and len(ol_text.strip()) > 20 and "[错误]" not in ol_text and "未配置 API Key" not in ol_text
            is_ok = bool(bp or has_valid_outline)
            if is_ok:
                # 保存到后端
                save_data = {"index": i, "outline": ol_text}
                if bp:
                    save_data["blueprint"] = bp
                try:
                    from backend.services.chapter_service import save_chapter_outline as _save
                    _save(save_data)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("save_chapter_outline failed for ch%d: %s", i+1, e)
            else:
                import logging
                logging.getLogger(__name__).warning("第%d章生成内容为空（blueprint=%s, ol_len=%d），跳过保存", i+1, bool(bp), len(ol_text or ""))


            results.append({
                "chapter": i+1,
                "title": title,
                "ok": is_ok,
                "has_blueprint": bool(bp),
                "outline_preview": ol_text[:80] if ol_text else "",
                "raw": result.get("raw", "") if i == 0 else ""
            })

        # 从第一章大纲中提取故事总览，自动保存为全书大纲（dict格式）
        if len(results) > 0 and results[0].get("raw"):
            first_raw = results[0].get("raw", "")
            overview_match = re.search(r'【故事总览】\s*\n([\s\S]+?)(?=\n```json|\n#|```)', first_raw)
            if overview_match:
                overview_text = overview_match.group(1).strip()
                if overview_text:
                    # 存储为新的 dict 格式（仅 theme/story_arc，其他字段需要后续补充）
                    state.project.novel_outline = {
                        "theme": "",
                        "core_conflict": "",
                        "story_arc": overview_text[:1500],
                        "world_anchor": "",
                        "character_arcs": [],
                        "key_hooks": [],
                        "ending": "",
                        "tone": ""
                    }
                    state.project._save_meta()

        return {"ok": True, "count": len(results), "results": results}
    except Exception as e:
        import traceback; traceback.print_exc()
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.post("/all-chapters")
def generate_all_chapters():
    """一键生成全部章节正文"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    gen.reload_world()
    results = []
    chapters = state.project.chapters or []

    for i in range(len(chapters)):
        ch = chapters[i]
        title = ch.get("title", "第%d章" % (i+1))
        outline = ch.get("outline", "")
        blueprint = ch.get("blueprint", {})

        # 构建上下文 — 传入正确的章节索引
        context = ""
        if i > 0:
            try:
                context = state.project.get_previous_context(chapter_index=i)
                if context:
                    context = "前一章全文：\n" + context
            except Exception:
                pass

        # 如果有蓝图，将其转为大纲文本
        if not outline and blueprint:
            parts = []
            intro = blueprint.get("intro", {})
            if intro:
                parts.append("【起】%s — %s" % (intro.get("scene",""), intro.get("trigger","")))
            for dev in blueprint.get("development", []):
                parts.append("【承】%s：%s" % (dev.get("scene",""), dev.get("event","")))
            climax = blueprint.get("climax", {})
            if climax:
                parts.append("【转】%s — %s" % (climax.get("conflict",""), climax.get("twist","")))
            ending = blueprint.get("ending", {})
            if ending:
                parts.append("【合】%s → %s" % (ending.get("new_state",""), ending.get("next_hook","")))
            outline = "\n".join(parts)

        result = gen.generate_and_validate(title, outline, context, chapter_index=i, max_retries=2, use_distilled_memory=True)
        content = result.get("content", "")

        # 保存到后端（使用 set_content 写入章节文件，而非仅修改内存数组）
        if content:
            try:
                state.project.set_content(content, i)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("save chapter %d failed: %s", i+1, e)

            # 状态提取：更新角色状态、时间线、伏笔到Truth Ledger
            try:
                gen.apply_state_extraction(content, i + 1, title)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("state extraction chapter %d failed: %s", i+1, e)

            # 向量记忆注入：把正文段落存入向量记忆
            try:
                from backend.services.project_service import get_vector_memory
                from backend.services.vector_memory import MemoryType
                vm = get_vector_memory()
                if vm:
                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and len(p.strip()) > 50]
                    for pi, para in enumerate(paragraphs):
                        vm.add_memory(
                            content=para,
                            memory_type=MemoryType.EVENT,
                            importance=0.6,
                            metadata={"chapter": i + 1, "chapter_title": title, "paragraph": pi}
                        )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("vector memory chapter %d failed: %s", i+1, e)

        results.append({
            "chapter": i+1,
            "title": title,
            "ok": result.get("ok", False),
            "word_count": len(content),
            "warning": result.get("warning", "")
        })

    # 一次性保存
    try:
        state.project.save_all()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("save_all failed: %s", e)

    return {"ok": True, "count": len(results), "results": results}


# ── 异步全章生成（后台任务 + 进度查询） ──

@router.post("/all-chapters/start")
def start_generate_all_chapters():
    """启动全章生成后台任务，立即返回 task_id"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    chapters = state.project.chapters or []
    total = len(chapters)
    if total == 0:
        return err(ErrorCode.INTERNAL_ERROR, "没有章节")

    task = _task_manager.create_task(total)
    _task_manager.run_async(task, _generate_all_chapters_worker)
    return {"ok": True, "task_id": task.task_id, "total": total}

@router.get("/all-chapters/status")
def get_generate_status(task_id: str = ""):
    """查询生成任务进度"""
    if not task_id:
        return err(ErrorCode.VALIDATION_ERROR, "缺少 task_id")
    task = _task_manager.get_task(task_id)
    if not task:
        return err(ErrorCode.NOT_FOUND, "任务不存在")
    return {"ok": True, **task.to_dict()}

@router.post("/all-chapters/cancel")
def cancel_generate(data: CancelGenerateRequest):
    """取消正在运行的生成任务"""
    task_id = data.task_id
    if not task_id:
        return err(ErrorCode.VALIDATION_ERROR, "缺少 task_id")
    task = _task_manager.get_task(task_id)
    if not task:
        return err(ErrorCode.NOT_FOUND, "任务不存在")
    if task.status not in ("running", "pending"):
        return err(ErrorCode.INTERNAL_ERROR, f"任务状态为 {task.status}，无法取消")
    task.cancel()
    return {"ok": True, "message": "已发送取消信号，将在当前章节完成后停止"}
