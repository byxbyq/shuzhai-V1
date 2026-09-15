# -*- coding: utf-8 -*-
"""世界观知识库路由 - /api/kb/*
将跨项目共享记忆产品化为独立"世界观知识库"功能：
- 导入公开设定集（修仙境界体系/势力地图/物品图鉴等）
- 跨小说复用世界观
- 社区共享设定包导入/导出
"""
import os, json, logging, datetime
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from backend.services.project_service import PROJECTS_DIR
from backend.services.vector_memory import MemoryType
from backend.api_models import paginated, PaginationParams, err, ErrorCode
from backend.routers.sync import _safe_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb")

# 知识库存储目录（与共享记忆同目录）
KB_DIR = os.path.join(PROJECTS_DIR, "_shared", "knowledge_base")
os.makedirs(KB_DIR, exist_ok=True)

# 预设设定集模板
KB_TEMPLATES = {
    "xianxia_realm": {
        "name": "修仙境界体系",
        "desc": "经典修仙/玄幻小说境界等级体系",
        "type": "KNOWLEDGE",
        "entries": [
            {"content": "炼气期：修仙入门阶段，分为一至九层，每层需积累灵气。九层圆满可筑基。", "importance": 0.8},
            {"content": "筑基期：修仙第一道坎，筑基成功则寿元增至两百。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "金丹期：体内凝聚金丹，可御剑飞行。金丹品质决定未来潜力。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "元婴期：金丹化为元婴，可神识出窍。寿元五百。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "化神期：元婴与天地共鸣，可操控天地灵气。寿元千年。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "炼虚期：领悟空间法则，可撕裂空间。寿元两千。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "合体期：肉身与元婴合一，不再依赖肉身。寿元五千。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "大乘期：半步飞升，可感应仙界。寿元万年。分初期/中期/后期/大圆满。", "importance": 0.8},
            {"content": "渡劫期：引动天劫，渡劫成功则飞升仙界，失败则身陨。", "importance": 0.9},
        ]
    },
    "xianxia_factions": {
        "name": "修仙势力架构",
        "desc": "经典修仙世界势力组织模板",
        "type": "KNOWLEDGE",
        "entries": [
            {"content": "宗门：修仙者聚集修炼之地，分内门/外门/核心弟子。掌门通常化神期以上。", "importance": 0.7},
            {"content": "世家：以血脉传承的修仙家族，底蕴深厚，常有祖传功法。", "importance": 0.7},
            {"content": "散修：无门无派的修仙者，资源匮乏但经历丰富。", "importance": 0.6},
            {"content": "魔道：以掠夺他人修为修炼的邪修组织，被正道追杀。", "importance": 0.7},
            {"content": "仙廷：飞升者建立的天界政权，管理下界飞升事务。", "importance": 0.8},
        ]
    },
    "urban_power": {
        "name": "都市异能体系",
        "desc": "都市异能/超能力小说等级体系",
        "type": "SKILL",
        "entries": [
            {"content": "F级：普通人，无超能力。", "importance": 0.5},
            {"content": "E级：觉醒初期，能力微弱，仅能自保。", "importance": 0.6},
            {"content": "D级：能力成型，可对抗小型威胁。", "importance": 0.6},
            {"content": "C级：能力强化，可对抗中型威胁，城市级战力。", "importance": 0.7},
            {"content": "B级：能力质变，可对抗大型威胁，省级战力。", "importance": 0.7},
            {"content": "A级：能力领域化，可影响区域，国家级战力。", "importance": 0.8},
            {"content": "S级：能力概念化，可改变规则，洲级战力。", "importance": 0.9},
            {"content": "SS级：能力因果律级，可改写现实，全球级战力。", "importance": 0.9},
            {"content": "SSS级：能力神话级，超越人类理解范畴。", "importance": 1.0},
        ]
    },
    "fantasy_items": {
        "name": "奇幻物品图鉴",
        "desc": "通用奇幻小说物品设定模板",
        "type": "KNOWLEDGE",
        "entries": [
            {"content": "灵石：修仙界通用货币，分下品/中品/上品/极品。1中品=100下品。", "importance": 0.7},
            {"content": "储物戒：可存储物品的空间法器，按容量分一至九品。", "importance": 0.7},
            {"content": "传音符：一次性通讯法器，可远距离传音。", "importance": 0.5},
            {"content": "丹药：回复类(疗伤/补灵)、增益类(突破/洗髓)、毒药类。", "importance": 0.7},
            {"content": "飞剑：修仙者主战武器，品质分法器/灵器/法宝/仙器。", "importance": 0.8},
        ]
    },
}


class KBImportRequest(BaseModel):
    name: str = Field(..., max_length=100, description="知识库名称")
    description: str = ""
    entries: List[Dict[str, Any]] = []
    memory_type: str = "knowledge"


class KBExportRequest(BaseModel):
    name: str = Field(..., max_length=100)
    include_shared: bool = True


@router.get("/templates")
def get_templates():
    """获取预设设定集模板列表"""
    templates = []
    for tid, tpl in KB_TEMPLATES.items():
        templates.append({
            "id": tid,
            "name": tpl["name"],
            "desc": tpl["desc"],
            "type": tpl["type"],
            "entry_count": len(tpl["entries"])
        })
    return {"ok": True, "templates": templates}


class TemplateImportRequest(BaseModel):
    template_id: str
    target_project: bool = True  # True=导入到当前项目, False=导入到共享知识库


@router.post("/import-template")
def import_template(data: TemplateImportRequest):
    """导入预设设定集到当前项目或共享知识库"""
    tpl = KB_TEMPLATES.get(data.template_id)
    if not tpl:
        return err(ErrorCode.INTERNAL_ERROR, f"未知模板: {data.template_id}")

    try:
        mem_type = MemoryType(tpl["type"])
    except ValueError:
        mem_type = MemoryType.KNOWLEDGE

    if data.target_project:
        from backend.services.project_service import get_vector_memory
        vm = get_vector_memory()
        if not vm:
            return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    else:
        from backend.services.project_service import get_shared_vector_memory
        vm = get_shared_vector_memory()

    added = 0
    for entry in tpl["entries"]:
        result = vm.add_memory(
            content=entry["content"],
            memory_type=mem_type,
            importance=entry.get("importance", 0.7),
            metadata={"source": "kb_template", "template": data.template_id, "kb_name": tpl["name"]}
        )
        if result:
            added += 1

    return {"ok": True, "template": tpl["name"], "added": added, "target": "project" if data.target_project else "shared"}


@router.post("/import-custom")
def import_custom(data: KBImportRequest):
    """导入自定义设定集"""
    from backend.services.project_service import get_shared_vector_memory
    vm = get_shared_vector_memory()

    try:
        mem_type = MemoryType(data.memory_type)
    except ValueError:
        mem_type = MemoryType.KNOWLEDGE

    added = 0
    for entry in data.entries:
        content = entry.get("content", "")
        if not content.strip():
            continue
        result = vm.add_memory(
            content=content,
            memory_type=mem_type,
            importance=entry.get("importance", 0.7),
            metadata={"source": "kb_custom", "kb_name": data.name, "kb_desc": data.description}
        )
        if result:
            added += 1

    # 保存设定集元信息
    kb_meta_file = os.path.join(KB_DIR, f"{_safe_filename(data.name)}.json")
    with open(kb_meta_file, "w", encoding="utf-8") as f:
        json.dump({
            "name": data.name,
            "description": data.description,
            "entry_count": added,
            "memory_type": data.memory_type,
            "imported_at": datetime.datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)

    return {"ok": True, "name": data.name, "added": added}


@router.get("/list")
def list_kb(pagination: PaginationParams = Depends()):
    """列出所有已导入的知识库设定集"""
    packs = []
    for fname in os.listdir(KB_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(KB_DIR, fname), "r", encoding="utf-8") as f:
                packs.append(json.load(f))
        except Exception:
            pass
    total = len(packs)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    return paginated(packs[start:end], pagination.page, pagination.page_size, total)


class KBExportPackRequest(BaseModel):
    name: str = Field("", max_length=100)
    memory_types: List[str] = []


@router.post("/export-pack")
async def export_pack(request: Request):
    """导出共享知识库为设定包（JSON格式），可在其他书斋实例导入"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    name = body.get("name", "书斋设定包")
    mem_types = body.get("memory_types", [])

    from backend.services.project_service import get_shared_vector_memory
    vm = get_shared_vector_memory()

    entries = []
    for entry in vm.memories.values():
        if mem_types and entry.memory_type.value not in mem_types:
            continue
        entries.append({
            "content": entry.content,
            "memory_type": entry.memory_type.value,
            "importance": entry.importance,
            "metadata": entry.metadata
        })

    pack = {
        "name": name,
        "version": "1.0",
        "exported_at": datetime.datetime.now().isoformat(),
        "entry_count": len(entries),
        "entries": entries
    }

    export_file = os.path.join(KB_DIR, f"export_{name}.json")
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)

    return {"ok": True, "file": export_file, "name": name, "entry_count": len(entries)}


class KBImportPackRequest(BaseModel):
    pack_data: Dict[str, Any]


@router.post("/import-pack")
def import_pack(data: KBImportPackRequest):
    """导入设定包（从其他书斋实例导出的JSON）"""
    pack = data.pack_data
    if not pack or "entries" not in pack:
        return err(ErrorCode.VALIDATION_ERROR, "无效的设定包格式")

    from backend.services.project_service import get_shared_vector_memory
    vm = get_shared_vector_memory()

    added = 0
    for entry in pack["entries"]:
        try:
            mem_type = MemoryType(entry.get("memory_type", "knowledge"))
        except ValueError:
            mem_type = MemoryType.KNOWLEDGE

        result = vm.add_memory(
            content=entry["content"],
            memory_type=mem_type,
            importance=entry.get("importance", 0.7),
            metadata={**entry.get("metadata", {}), "source": "kb_import_pack", "pack_name": pack.get("name", "")}
        )
        if result:
            added += 1

    return {"ok": True, "pack_name": pack.get("name", ""), "added": added, "total": len(pack["entries"])}


@router.get("/search")
def search_kb(q: str = "", k: int = 10):
    """搜索知识库（共享记忆）"""
    from backend.services.project_service import get_shared_vector_memory
    vm = get_shared_vector_memory()

    if not q.strip():
        return {"ok": True, "results": [], "count": 0}

    try:
        results = vm.search(query=q, k=k)
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

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


@router.delete("/pack/{pack_name}")
def delete_pack(pack_name: str):
    """删除知识库设定集（仅删除元信息，不删除已导入的记忆）"""
    kb_meta_file = os.path.join(KB_DIR, f"{_safe_filename(pack_name)}.json")
    if not os.path.exists(kb_meta_file):
        return err(ErrorCode.NOT_FOUND, "设定集不存在")
    os.remove(kb_meta_file)
    return {"ok": True, "message": f"设定集 {pack_name} 已删除"}
