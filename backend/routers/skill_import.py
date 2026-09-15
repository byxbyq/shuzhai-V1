# -*- coding: utf-8 -*-
"""技能包导入路由 - /api/skills/*
支持从「小说蒸馏器」（项目A）蒸馏出的 .json 技能包导入到当前项目。
导入的技能包保存到当前项目的 skills/ 目录下，与内置技能包兼容。
"""
from fastapi import APIRouter, UploadFile, File
from typing import Optional
from pydantic import BaseModel
import os, json, re, logging

from backend.services.project_service import state
from backend.api_models import err, ErrorCode
from backend.prompt_sanitizer import sanitize_light

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills")

# 技能包必需字段
REQUIRED_FIELDS = ['id', 'name', 'type', 'description', 'content']


def _get_skills_dir() -> Optional[str]:
    """获取当前项目的 skills 目录路径，不存在则创建"""
    if not state.project:
        return None
    skills_dir = os.path.join(state.project.project_dir, 'skills')
    os.makedirs(skills_dir, exist_ok=True)
    return skills_dir


def _sanitize_filename(name: str) -> str:
    """清理文件名/ID，只保留安全字符，防止路径穿越"""
    # 去掉路径分隔符等危险字符
    safe = re.sub(r'[^\w\-.]', '_', name)
    # 防止以 . 开头或包含 ..
    safe = safe.lstrip('.')
    if not safe:
        safe = 'skill'
    return safe


@router.post("/import")
async def import_skill(file: UploadFile = File(...)):
    """导入技能包 .json 文件（multipart/form-data）

    接收上传的 .json 文件，解析并验证必需字段后保存到当前项目的 skills/ 目录。
    文件名格式：{id}.json；若 id 已存在则返回冲突提示。
    """
    # 1. 读取文件内容
    raw = await file.read()
    if not raw:
        return err(ErrorCode.VALIDATION_ERROR, "上传的文件为空")

    # 2. 解码（优先 UTF-8，回退 GBK）
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = raw.decode('gbk')
        except Exception:
            return err(ErrorCode.INTERNAL_ERROR, "文件编码无法识别，请使用 UTF-8 编码")

    # 3. 解析 JSON
    try:
        skill = json.loads(text)
    except json.JSONDecodeError as e:
        return err(ErrorCode.PARSE_FAILED, f"JSON 解析失败: {str(e)}")

    if not isinstance(skill, dict):
        return err(ErrorCode.INTERNAL_ERROR, "技能包格式错误：根元素必须是 JSON 对象")

    # 4. 验证必需字段
    missing = [f for f in REQUIRED_FIELDS if not skill.get(f)]
    if missing:
        return err(ErrorCode.VALIDATION_ERROR, f"缺少必需字段: {', '.join(missing)}")

    # 5. 校验 id
    skill_id = str(skill['id']).strip()
    if not skill_id:
        return err(ErrorCode.VALIDATION_ERROR, "技能包 id 不能为空")

    safe_id = _sanitize_filename(skill_id)

    # 6. 获取 skills 目录
    skills_dir = _get_skills_dir()
    if not skills_dir:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目，请先打开或创建一个项目")

    # 7. 检查 id 冲突
    target_path = os.path.join(skills_dir, safe_id + '.json')
    if os.path.exists(target_path):
        return {
            "ok": False,
            "error": "技能包 id 已存在（" + skill_id + "），请先删除已有技能包或修改 id 后重试",
            "conflict": True,
            "skill_id": skill_id
        }

    # 8. 补全元数据，标记为导入的技能包
    skill['imported'] = True
    skill['builtin'] = False
    if 'version' not in skill or not skill['version']:
        skill['version'] = '1.0.0'
    if 'author' not in skill or not skill['author']:
        skill['author'] = '导入'
    if 'scope' not in skill or not skill['scope']:
        skill['scope'] = 'generate'

    # 9. 保存到文件
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"保存文件失败: {str(e)}")

    return {
        "ok": True,
        "skill": {
            "id": skill_id,
            "name": skill.get('name', ''),
            "type": skill.get('type', '')
        }
    }


@router.get("/list")
def list_skills():
    """列出当前项目 skills/ 目录下所有导入的技能包"""
    skills_dir = _get_skills_dir()
    if not skills_dir:
        return {"ok": True, "skills": [], "error": "没有打开的项目"}

    skills = []
    if os.path.isdir(skills_dir):
        for fname in sorted(os.listdir(skills_dir)):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(skills_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                skills.append({
                    "id": data.get('id', fname[:-5]),
                    "name": data.get('name', ''),
                    "type": data.get('type', 'rules'),
                    "description": data.get('description', ''),
                    "content": data.get('content', ''),
                    "version": data.get('version', '1.0.0'),
                    "author": data.get('author', '导入'),
                    "scope": data.get('scope', 'generate'),
                    "trigger": data.get('trigger', ''),
                    "imported": True,
                    "builtin": False
                })
            except Exception:
                # 跳过无法解析的文件
                continue

    return {"ok": True, "skills": skills}


@router.delete("/{skill_id}")
def delete_skill(skill_id: str):
    """删除指定的导入技能包"""
    skills_dir = _get_skills_dir()
    if not skills_dir:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    safe_id = _sanitize_filename(skill_id)
    target_path = os.path.join(skills_dir, safe_id + '.json')

    if not os.path.exists(target_path):
        return err(ErrorCode.NOT_FOUND, f"技能包不存在: {skill_id}")

    try:
        os.remove(target_path)
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"删除失败: {str(e)}")

    return {"ok": True, "skill_id": skill_id}


# ═══════════════════════════════════════════
# 小说蒸馏：从小说文本自动生成写作技能包
# ═══════════════════════════════════════════

class DistillRequest(BaseModel):
    novel_text: str
    novel_name: str = "未命名小说"
    import_to_project: bool = True
    decon_data: dict = None        # 拆书五维结构化数据（source_type=decon时使用）
    source_type: str = "raw"       # 蒸馏策略：raw(原始文本) | decon(基于拆书数据)


@router.post("/distill")
def distill_novel(data: DistillRequest):
    """从小说文本中蒸馏写作技能包。

    运行 RIA-TV++ 流水线（理解→提取→验证→构造），生成可执行的写作技能包。
    可选：自动导入到当前项目的 skills/ 目录。
    source_type: raw=原始文本蒸馏, decon=基于拆书数据蒸馏（质量更高，省token）
    """
    from backend.services.distill_service import (
        DistillService,
        content_object_to_markdown,
    )

    if not data.novel_text or len(data.novel_text) < 1000:
        return err(ErrorCode.VALIDATION_ERROR, "小说文本过短，请提供至少1000字")

    try:
        service = DistillService(
            novel_text=sanitize_light(data.novel_text),
            novel_name=data.novel_name or "未命名小说",
            decon_data=data.decon_data,
            source_type=data.source_type,
        )
        result = service.run(end_stage=2)

        skills = result.get("skills", [])

        imported_count = 0
        import_errors = []

        if data.import_to_project and skills and state.project:
            skills_dir = _get_skills_dir()
            if skills_dir:
                for skill in skills:
                    try:
                        skill_id = str(skill.get("id", "")).strip()
                        if not skill_id:
                            continue
                        safe_id = _sanitize_filename(skill_id)

                        # 格式适配：content 对象 → markdown 字符串
                        content_obj = skill.get("content", {})
                        if isinstance(content_obj, dict):
                            skill["content"] = content_object_to_markdown(
                                content_obj,
                                skill.get("name", "")
                            )

                        # 补全元数据
                        skill["imported"] = True
                        skill["builtin"] = False
                        if "version" not in skill or not skill["version"]:
                            skill["version"] = "1.0.0"
                        if "author" not in skill or not skill["author"]:
                            skill["author"] = "蒸馏生成"
                        if "scope" not in skill or not skill["scope"]:
                            skill["scope"] = "generate"

                        target_path = os.path.join(skills_dir, safe_id + '.json')
                        if os.path.exists(target_path):
                            import_errors.append(f"ID已存在: {skill_id}")
                            continue

                        with open(target_path, 'w', encoding='utf-8') as f:
                            json.dump(skill, f, ensure_ascii=False, indent=2)

                        imported_count += 1
                    except Exception as e:
                        import_errors.append(f"{skill.get('name', '?')}: {str(e)}")

        return {
            "ok": True,
            "novel_name": result.get("novel_name", ""),
            "novel_chars": result.get("novel_chars", 0),
            "chapter_count": result.get("chapter_count", 0),
            "api_calls": result.get("api_calls", 0),
            "candidate_count": result.get("candidates", {}).get("total", 0),
            "verified_count": result.get("verified", {}).get("total", 0),
            "skill_count": result.get("skill_count", 0),
            "imported_count": imported_count,
            "import_errors": import_errors,
            "skills": skills,
        }

    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"蒸馏失败: {str(e)}")


class DeepAnalysisRequest(BaseModel):
    novel_text: str
    novel_name: str = "未命名小说"
    import_skills: bool = True
    analyze_deconstruct: bool = True
    analyze_distill: bool = True
    source_type: str = "decon"  # deep-analyze默认用decon（有拆书数据支撑）


@router.post("/deep-analyze")
async def deep_analyze_novel(data: DeepAnalysisRequest):
    """一键深度分析：拆书分析 + 技能蒸馏，一次搞定全套

    同时跑两个系统：
    1. 拆书分析：世界观/角色/结构/主题/情节机制
    2. 技能蒸馏：提取可复用的写作技能包（自动导入到项目）
    """
    if not data.novel_text or len(data.novel_text) < 1000:
        return err(ErrorCode.VALIDATION_ERROR, "小说文本过短，请提供至少1000字")

    result = {
        "ok": True,
        "novel_name": data.novel_name,
        "novel_chars": len(data.novel_text),
        "deconstruct": None,
        "distill": None,
    }

    # 1. 拆书分析
    if data.analyze_deconstruct:
        try:
            from backend.services.deconstruct_service import DeconstructService
            service = DeconstructService()
            decon_result = service.deconstruct(data.novel_text)
            result["deconstruct"] = {
                "source_meta": decon_result.get("source_meta", {}),
                "structure": decon_result.get("structure", {}),
                "characters": decon_result.get("characters", {}),
                "worldbuilding": decon_result.get("worldbuilding", {}),
                "theme": decon_result.get("theme", {}),
                "plot_mechanics": decon_result.get("plot_mechanics", {}),
            }
        except Exception as e:
            result["deconstruct"] = {"error": str(e)}
            logger.warning(f"[深度分析] 拆书失败: {e}")

    # 2. 技能蒸馏 + 自动导入（复用拆书结果作为补充上下文）
    if data.analyze_distill:
        try:
            from backend.services.distill_service import (
                DistillService,
                content_object_to_markdown,
            )
            # 断点1修复：如果拆书分析有结果，传给蒸馏服务作为补充上下文
            decon_for_distill = result.get("deconstruct") if "deconstruct" in result else None
            service = DistillService(
                novel_text=data.novel_text,
                novel_name=data.novel_name,
                decon_data=decon_for_distill,
                source_type=data.source_type,
            )
            distill_result = service.run(end_stage=2)

            skills = distill_result.get("skills", [])
            imported_count = 0
            import_errors = []

            if data.import_skills and skills and state.project:
                skills_dir = _get_skills_dir()
                if skills_dir:
                    for skill in skills:
                        try:
                            skill_id = str(skill.get("id", "")).strip()
                            if not skill_id:
                                continue
                            safe_id = _sanitize_filename(skill_id)

                            # 格式适配：content 对象 → markdown 字符串
                            content_obj = skill.get("content", {})
                            if isinstance(content_obj, dict):
                                skill["content"] = content_object_to_markdown(
                                    content_obj,
                                    skill.get("name", "")
                                )

                            # 补全元数据
                            skill["imported"] = True
                            skill["builtin"] = False
                            if "version" not in skill or not skill["version"]:
                                skill["version"] = "1.0.0"
                            if "author" not in skill or not skill["author"]:
                                skill["author"] = "蒸馏生成"
                            if "scope" not in skill or not skill["scope"]:
                                skill["scope"] = "generate"
                            # 标记来源
                            skill["source_novel"] = data.novel_name
                            skill["source_type"] = "deep_analysis"

                            target_path = os.path.join(skills_dir, safe_id + '.json')
                            if os.path.exists(target_path):
                                # 已存在就跳过，不报错
                                import_errors.append(f"已存在: {skill_id}")
                                continue

                            with open(target_path, 'w', encoding='utf-8') as f:
                                json.dump(skill, f, ensure_ascii=False, indent=2)

                            imported_count += 1
                        except Exception as e:
                            import_errors.append(f"{skill.get('name', '?')}: {str(e)}")

            result["distill"] = {
                "skill_count": distill_result.get("skill_count", 0),
                "api_calls": distill_result.get("api_calls", 0),
                "imported_count": imported_count,
                "import_errors": import_errors,
                "skills": skills,
            }
        except Exception as e:
            result["distill"] = {"error": str(e)}
            logger.warning(f"[深度分析] 蒸馏失败: {e}")

    return result
