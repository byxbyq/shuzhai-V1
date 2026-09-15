# -*- coding: utf-8 -*-
"""向量记忆路由 - /api/memory/*"""
import os
import logging
from fastapi import APIRouter
from typing import Optional, Dict, Any
from pydantic import BaseModel

from backend.services.project_service import state, get_vector_memory, get_shared_vector_memory
from backend.services.vector_memory import MemoryType, EMBEDDING_MODELS
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory")


class MemoryAdd(BaseModel):
    content: str
    memory_type: str = "event"
    importance: float = 0.5
    metadata: Dict[str, Any] = {}


class MemorySearch(BaseModel):
    query: str
    k: int = 5
    memory_type: Optional[str] = None
    min_importance: float = 0.0
    chapter: int = 0


@router.get("/stats")
def memory_stats():
    """获取记忆统计"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, **vm.get_stats()}


@router.post("/add")
def add_memory(data: MemoryAdd):
    """添加记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        mem_type = MemoryType(data.memory_type) if data.memory_type else MemoryType.EVENT
    except ValueError:
        mem_type = MemoryType.EVENT

    entry = vm.add_memory(
        content=data.content,
        memory_type=mem_type,
        importance=data.importance,
        metadata=data.metadata
    )
    if entry:
        return {"ok": True, "id": entry.id}
    return err(ErrorCode.INTERNAL_ERROR, "添加失败")


@router.post("/search")
def search_memory(data: MemorySearch):
    """搜索记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    try:
        mem_type = MemoryType(data.memory_type) if data.memory_type else None
    except ValueError:
        mem_type = None

    results = vm.search(
        query=data.query,
        k=data.k,
        memory_type=mem_type,
        min_importance=data.min_importance
    )

    return {
        "ok": True,
        "results": [
            {
                "id": entry.id,
                "content": entry.content,
                "memory_type": entry.memory_type.value,
                "importance": entry.importance,
                "score": round(score, 4),
                "metadata": entry.metadata
            }
            for entry, score in results
        ],
        "count": len(results)
    }


@router.post("/search-for-generation")
def search_for_generation(data: MemorySearch):
    """为章节生成搜索召回上下文（返回格式化文本）"""
    vm = get_vector_memory()
    if not vm:
        return {**err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目"), "context": ""}

    context = vm.search_for_generation(
        outline=data.query,
        chapter_index=data.chapter,
        k=data.k
    )

    return {"ok": True, "context": context, "length": len(context)}


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    """删除记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = vm.delete_memory(memory_id)
    return {"ok": ok}


@router.post("/import-chapter")
def import_chapter(data: dict):
    """将章节内容导入向量记忆（章节保存时自动调用）"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    content = data.get("content", "")
    chapter_index = data.get("chapter_index", -1)
    chapter_title = data.get("chapter_title", "")
    memory_type = data.get("memory_type", "event")

    if not content or len(content) < 100:
        return err(ErrorCode.INTERNAL_ERROR, "内容太短")

    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        mem_type = MemoryType.EVENT

    # 将章节按段落分割，每段作为一条记忆
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and len(p.strip()) > 50]

    added = 0
    for i, para in enumerate(paragraphs):
        meta = {
            "chapter": chapter_index + 1,
            "chapter_title": chapter_title,
            "paragraph": i,
        }
        entry = vm.add_memory(
            content=para,
            memory_type=mem_type,
            importance=0.6,  # 章节内容默认中等重要性
            metadata=meta
        )
        if entry:
            added += 1

    return {"ok": True, "added": added, "total_paragraphs": len(paragraphs)}


# ═══════════════════════════════════════════
# 跨项目共享记忆 API
# ═══════════════════════════════════════════

@router.post("/search-combined")
def search_memory_combined(data: MemorySearch):
    """合并搜索：项目记忆 + 跨项目共享记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    try:
        mem_type = MemoryType(data.memory_type) if data.memory_type else None
    except ValueError:
        mem_type = None

    shared_vm = get_shared_vector_memory()
    results = vm.search_combined(
        query=data.query,
        shared_memory=shared_vm,
        k=data.k,
        memory_type=mem_type,
        min_importance=data.min_importance
    )

    return {
        "ok": True,
        "results": [
            {
                "id": entry.id,
                "content": entry.content,
                "memory_type": entry.memory_type.value,
                "importance": entry.importance,
                "score": round(score, 4),
                "metadata": entry.metadata,
                "is_shared": entry.metadata.get("source") == "shared"
            }
            for entry, score in results
        ],
        "count": len(results),
        "shared_total": len(shared_vm.memories) if shared_vm else 0
    }


class MemoryShare(BaseModel):
    memory_id: str


@router.post("/share")
def share_memory(data: MemoryShare):
    """将项目记忆提升为跨项目共享记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    shared_vm = get_shared_vector_memory()
    ok = vm.promote_to_shared(data.memory_id, shared_vm)
    if ok:
        return {"ok": True, "message": "记忆已提升为跨项目共享"}
    return err(ErrorCode.NOT_FOUND, "记忆不存在或提升失败")


@router.get("/shared/stats")
def shared_memory_stats():
    """获取共享记忆统计"""
    shared_vm = get_shared_vector_memory()
    return {"ok": True, **shared_vm.get_stats()}


@router.post("/shared/add")
def add_shared_memory(data: MemoryAdd):
    """直接添加共享记忆（通用世界观知识）"""
    shared_vm = get_shared_vector_memory()
    try:
        mem_type = MemoryType(data.memory_type) if data.memory_type else MemoryType.KNOWLEDGE
    except ValueError:
        mem_type = MemoryType.KNOWLEDGE

    entry = shared_vm.add_memory(
        content=data.content,
        memory_type=mem_type,
        importance=data.importance,
        metadata=data.metadata
    )
    if entry:
        return {"ok": True, "id": entry.id}
    return err(ErrorCode.INTERNAL_ERROR, "添加失败")


@router.get("/shared/list")
def list_shared_memory():
    """列出所有共享记忆"""
    shared_vm = get_shared_vector_memory()
    memories = []
    for entry in shared_vm.memories.values():
        memories.append({
            "id": entry.id,
            "content": entry.content[:200] + ("..." if len(entry.content) > 200 else ""),
            "memory_type": entry.memory_type.value,
            "importance": entry.importance,
            "metadata": entry.metadata
        })
    return {"ok": True, "memories": memories, "count": len(memories)}


@router.delete("/shared/{memory_id}")
def delete_shared_memory(memory_id: str):
    """删除共享记忆"""
    shared_vm = get_shared_vector_memory()
    ok = shared_vm.delete_memory(memory_id)
    return {"ok": ok}


# ═══════════════════════════════════════════
# 嵌入模型管理 API
# ═══════════════════════════════════════════

@router.get("/embedding-models")
def list_embedding_models():
    """列出所有可用的嵌入模型"""
    vm = get_vector_memory()
    current = vm.model_name if vm else "BAAI/bge-small-zh-v1.5"
    return {
        "ok": True,
        "current": current,
        "current_dim": vm.embedding_dim if vm else 512,
        "models": {name: info for name, info in EMBEDDING_MODELS.items()}
    }


class SwitchModelRequest(BaseModel):
    model_name: str


@router.post("/switch-embedding-model")
def switch_embedding_model(data: SwitchModelRequest):
    """切换嵌入模型并重新编码所有记忆"""
    vm = get_vector_memory()
    if not vm:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    result = vm.migrate_embedding_model(data.model_name)

    # 同时迁移共享记忆
    try:
        shared_vm = get_shared_vector_memory()
        shared_vm.migrate_embedding_model(data.model_name)
    except Exception as e:
        logger.warning("共享记忆迁移失败，不影响主流程: %s", e)

    return result


# ─────────────────────────────────────────────
# 统一记忆系统：AI注入预览
# ─────────────────────────────────────────────

class ContextPreviewRequest(BaseModel):
    chapter_index: int = 0
    chapter_title: str = ""
    outline: str = ""


@router.post("/context-preview")
def context_preview(data: ContextPreviewRequest):
    """预览AI生成章节时将注入的所有记忆源"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    sources = []
    total_items = 0

    # 1. 世界观
    try:
        world = state.world
        if world:
            world_text = world.to_prompt()
            world_count = len(world_text.strip()) // 50 if world_text.strip() else 0
            sources.append({
                "name": "世界观设定",
                "count": world_count,
                "preview": [world_text.strip()[:80] + "..."] if world_text.strip() else []
            })
            total_items += world_count
    except Exception:
        sources.append({"name": "世界观设定", "count": 0, "preview": []})

    # 2. 全书大纲上下文
    try:
        project = state.project
        if project and hasattr(project, 'novel_acts') and project.novel_acts:
            acts = project.novel_acts
            sources.append({
                "name": "全书大纲（当前幕+前后3章）",
                "count": len(acts),
                "preview": [a.get('title', '')[:60] for a in acts[:3]]
            })
            total_items += len(acts)
        else:
            sources.append({"name": "全书大纲", "count": 0, "preview": []})
    except Exception:
        sources.append({"name": "全书大纲", "count": 0, "preview": []})

    # 3. 蒸馏记忆（state_memory + distilled AI 合成文件）
    try:
        project_dir = state.project.project_dir
        # state_memory：每章蒸馏结果
        state_mem_dir = os.path.join(project_dir, "state_memory")
        distilled_count = 0
        distilled_previews = []
        if os.path.isdir(state_mem_dir):
            for f in os.listdir(state_mem_dir):
                if f.endswith('.json') and not f.startswith('_'):
                    distilled_count += 1
        # distilled 的 AI 合成文件
        distilled_dir = os.path.join(project_dir, "distilled")
        if os.path.isdir(distilled_dir):
            for f in os.listdir(distilled_dir):
                if f.endswith('.json') and f != 'meta.json':
                    distilled_count += 1
                    label = f.replace('.json', '').replace('-', ' ')
                    distilled_previews.append(label)
        # state_memory 预览项
        if distilled_count > 0:
            distilled_previews.insert(0, f"state_memory × {distilled_count - len(distilled_previews)} 章")
        sources.append({
            "name": "蒸馏记忆（state_memory + AI 合成）",
            "count": distilled_count,
            "preview": distilled_previews[:5] or ["尚未生成，定稿章节后自动创建"]
        })
        total_items += distilled_count
    except Exception:
        sources.append({"name": "蒸馏记忆", "count": 0, "preview": []})

    # 4. TruthLedger（角色状态+伏笔+时间线）
    try:
        ledger = state.ledger
        if ledger:
            # 角色状态
            char_count = len(ledger.characters) if hasattr(ledger, 'characters') else 0
            # 待回收伏笔
            active_hooks = ledger.get_pending_hooks() if hasattr(ledger, 'get_pending_hooks') else (ledger.get_active_hooks() if hasattr(ledger, 'get_active_hooks') else [])
            hook_count = len(active_hooks)
            # 时间线
            timeline_count = len(ledger.timeline) if hasattr(ledger, 'timeline') else 0

            ledger_total = char_count + hook_count + timeline_count
            previews = []
            if char_count > 0:
                previews.append(f"角色状态 {char_count} 个")
            if hook_count > 0:
                previews.append(f"待回收伏笔 {hook_count} 个")
            if timeline_count > 0:
                previews.append(f"时间线事件 {timeline_count} 条")

            sources.append({
                "name": "TruthLedger（角色/伏笔/时间线）",
                "count": ledger_total,
                "preview": previews
            })
            total_items += ledger_total
        else:
            sources.append({"name": "TruthLedger", "count": 0, "preview": []})
    except Exception:
        sources.append({"name": "TruthLedger", "count": 0, "preview": []})

    # 5. 向量记忆RAG召回
    try:
        vm = get_vector_memory()
        if vm and data.outline:
            result_text = vm.search_for_generation_combined(data.outline, k=5, chapter_index=data.chapter_index)
            count = 0
            previews = []
            if result_text:
                # 返回值是拼接好的字符串，按 [相关 分段统计
                parts = result_text.split("\n\n")
                count = len(parts)
                previews = [p[:60] for p in parts[:3]]
            sources.append({
                "name": "向量记忆RAG召回",
                "count": count,
                "preview": previews
            })
            total_items += count
        else:
            sources.append({"name": "向量记忆RAG召回", "count": 0, "preview": []})
    except Exception:
        sources.append({"name": "向量记忆RAG召回", "count": 0, "preview": []})

    # 6. Lorebook关键词触发
    try:
        project = state.project
        if project and hasattr(project, 'lorebook') and project.lorebook:
            lorebook = project.lorebook
            trigger_text = data.outline + " " + data.chapter_title
            triggered = [e for e in lorebook if any(kw in trigger_text for kw in e.get('keywords', []))]
            sources.append({
                "name": "Lorebook关键词触发",
                "count": len(triggered),
                "preview": [t.get('name', '')[:40] for t in triggered[:3]]
            })
            total_items += len(triggered)
        else:
            sources.append({"name": "Lorebook关键词触发", "count": 0, "preview": []})
    except Exception:
        sources.append({"name": "Lorebook关键词触发", "count": 0, "preview": []})

    return {
        "ok": True,
        "chapter_title": data.chapter_title,
        "chapter_index": data.chapter_index,
        "sources": sources,
        "total_items": total_items
    }
