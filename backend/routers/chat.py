# -*- coding: utf-8 -*-
"""角色对话模拟路由 - /api/chat/*
从项目角色设定中提取角色列表，支持以角色身份与读者/作者对话。
- GET  /api/chat/characters  获取当前项目可用角色列表
- POST /api/chat/talk         以指定角色身份回复消息

角色设定来源（优先级从高到低）：
  - state.project.characters（SQLite characters 表，含 name/identity/backstory 等）
  - state.project.character_settings（旧字典格式，形如 {char_1_name: ..., char_1_role: ...}）
  - state.project.meta 中的 characters 列表（如有）
AI 调用：复用项目生成器 state.generator.ai（get_generator().ai.generate）
"""
import re
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.services.project_service import state, get_generator, get_ledger
from backend.prompt_sanitizer import sanitize_light
from backend.api_models import paginated, PaginationParams, err, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat")


# ── 角色解析 ──
_CHAR_KEY_RE = re.compile(r"char_(\d+)_(\w+)")


def _parse_characters_from_settings(cs: dict) -> List[dict]:
    """从 character_settings 字典解析角色列表。

    支持三种存储格式：
    1. 扁平编号格式：
        {"char_1_name": "陈墨", "char_1_role": "...", "char_2_name": "苏清玄", ...}
    2. 角色名为键的嵌套格式（dispatcher add_character 写入的格式）：
        {"林墨": {"name": "林墨", "description": "...", "personality": "..."}}
    3. 角色名为键的纯字符串格式（创建项目时写入的格式）：
        {"林枫": "男主；16岁；天剑宗外门杂役..."}
    每个角色返回 {name, role, description}。
    """
    if not cs or not isinstance(cs, dict):
        return []
    # 格式1: char_N_field 扁平编号
    char_map: dict = {}
    named_dict_chars: dict = {}
    named_str_chars: dict = {}
    for key, val in cs.items():
        m = _CHAR_KEY_RE.match(str(key))
        if m:
            num, field = m.group(1), m.group(2).lower()
            char_map.setdefault(num, {})[field] = val
        elif isinstance(val, dict) and val.get("name"):
            # 格式2: 角色名作为键，值是角色详情字典
            named_dict_chars[key] = val
        elif isinstance(val, str) and val.strip():
            # 格式3: 角色名作为键，值是纯字符串描述
            named_str_chars[key] = val
    result = []
    for num in sorted(char_map.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        info = char_map[num]
        name = info.get("name", "")
        if not name:
            continue
        role = info.get("role", "")
        desc = info.get("description", "") or role
        result.append({
            "name": str(name),
            "role": str(role),
            "description": str(desc),
        })
    # 格式2的角色
    for key, val in named_dict_chars.items():
        name = val.get("name", key)
        role = val.get("role", "") or val.get("identity", "")
        desc = val.get("description", "") or val.get("background", "") or val.get("personality", "") or role
        result.append({
            "name": str(name),
            "role": str(role),
            "description": str(desc),
        })
    # 格式3的角色
    for key, val in named_str_chars.items():
        result.append({
            "name": str(key),
            "role": "",
            "description": str(val),
        })
    return result


def _parse_characters_from_meta(meta: dict) -> List[dict]:
    """从 meta['characters'] 提取角色信息（如果存在）"""
    if not meta:
        return []
    meta_chars = meta.get("characters")
    if not isinstance(meta_chars, list):
        return []
    result = []
    for c in meta_chars:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "")
        if not name:
            continue
        role = c.get("role", "")
        desc = c.get("description", "") or role
        result.append({"name": str(name), "role": str(role), "description": str(desc)})
    return result


def _parse_characters_from_list(chars_list: list) -> List[dict]:
    """从 state.project.characters 列表解析角色（SQLite characters 表来源）。
    每个元素含 name/identity/goal/appearance/personality/backstory 等字段。
    """
    if not chars_list or not isinstance(chars_list, list):
        return []
    result = []
    for c in chars_list:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "")
        if not name:
            continue
        role = c.get("identity", "") or c.get("role", "")
        desc = c.get("backstory", "") or c.get("description", "") or c.get("personality", "") or role
        result.append({"name": str(name), "role": str(role), "description": str(desc)})
    return result


def _get_character_full_profile(name: str) -> dict:
    """根据角色名查找完整角色档案（含所有分层字段）。

    返回 dict 含：name, identity, faction, goal, appearance, personality,
    backstory, abilities, relationships, arc, description。
    未找到返回空 dict。
    """
    if not state.project:
        return {}

    # 1. SQLite characters 表（优先，字段最全）
    for ch in state.project.characters or []:
        if not isinstance(ch, dict):
            continue
        if ch.get("name") == name:
            rels = ch.get("relationships", {})
            if isinstance(rels, str):
                try:
                    import json
                    rels = json.loads(rels)
                except Exception:
                    rels = {}
            return {
                "name": ch.get("name", name),
                "identity": ch.get("identity", ""),
                "faction": ch.get("faction", ""),
                "goal": ch.get("goal", ""),
                "goals": ch.get("goals", []),
                "appearance": ch.get("appearance", ""),
                "personality": ch.get("personality", ""),
                "backstory": ch.get("backstory", ""),
                "abilities": ch.get("abilities", ""),
                "relationships": rels,
                "arc": ch.get("arc", ""),
                "cognitive_boundary": ch.get("cognitive_boundary", ""),
                "description": ch.get("backstory", "") or ch.get("personality", "") or ch.get("identity", ""),
            }

    # 2. character_settings 回退
    cs = state.project.character_settings or {}
    for ch in _parse_characters_from_settings(cs):
        if ch["name"] == name:
            return {
                "name": ch["name"],
                "identity": ch.get("role", ""),
                "faction": "",
                "goal": "",
                "goals": [],
                "appearance": "",
                "personality": "",
                "backstory": "",
                "abilities": "",
                "relationships": {},
                "arc": "",
                "cognitive_boundary": "",
                "description": ch.get("description", ""),
            }

    # 3. meta.characters 回退
    for ch in _parse_characters_from_meta(state.project.meta):
        if ch["name"] == name:
            return {
                "name": ch["name"],
                "identity": ch.get("role", ""),
                "faction": "",
                "goal": "",
                "goals": [],
                "appearance": "",
                "personality": "",
                "backstory": "",
                "abilities": "",
                "relationships": {},
                "arc": "",
                "cognitive_boundary": "",
                "description": ch.get("description", ""),
            }
    return {}


def _get_character_dynamic_state(character_name: str) -> dict:
    """从 TruthLedger 获取角色当前动态状态（运行时追踪数据）。

    返回字段：location, emotion, health, realm, relationships,
    secrets_known, last_seen_chapter, is_alive, arc_stage, possessions。
    未找到或获取失败返回空 dict。
    """
    try:
        ledger = get_ledger()
        if not ledger or character_name not in ledger.character_states:
            return {}
        cs = ledger.character_states[character_name]
        rels = cs.relationships or {}
        if isinstance(rels, str):
            try:
                import json
                rels = json.loads(rels)
            except Exception:
                rels = {}
        return {
            "location": cs.location or "",
            "emotion": cs.emotion or "",
            "health": cs.health or "",
            "realm": cs.realm or "",
            "relationships": rels,
            "secrets_known": list(cs.secrets_known or []),
            "last_seen_chapter": cs.last_seen_chapter,
            "is_alive": cs.is_alive,
            "arc_stage": cs.arc_stage or "",
            "possessions": list(cs.possessions or []),
        }
    except Exception as e:
        logger.warning(f"[Chat] 获取角色动态状态失败: {e}")
        return {}


def _extract_character_scenes(character_name: str, max_chapters: int = 2) -> str:
    """从最近章节正文中提取角色相关场景片段。

    从当前写作进度往前取最多 max_chapters 章，在正文中查找包含
    角色名的段落（前后各取一段上下文），最多返回 3 个片段。
    """
    if not state or not state.project:
        return ""
    chapters = state.project.chapters or []
    if not chapters:
        return ""

    current_idx = state.project.meta.get("current_chapter", 0)
    if isinstance(current_idx, int) and current_idx >= 0:
        start = max(0, current_idx - max_chapters + 1)
    else:
        start = max(0, len(chapters) - max_chapters)

    scenes = []
    for ch in chapters[start:]:
        idx = ch.get("index", 0)
        if not idx:
            continue
        try:
            content = state.project.get_content(idx)
        except Exception:
            continue
        if not content or character_name not in content:
            continue

        lines = content.split("\n")
        for i, line in enumerate(lines):
            if character_name in line:
                ctx_start = max(0, i - 1)
                ctx_end = min(len(lines), i + 2)
                snippet = "\n".join(lines[ctx_start:ctx_end]).strip()
                if snippet and len(snippet) > 10:
                    scenes.append(f"[第{idx}章] {snippet[:200]}")
                if len(scenes) >= 3:
                    break
        if len(scenes) >= 3:
            break

    return "\n".join(scenes) if scenes else ""


def _build_layered_character_prompt(character: str, profile: dict, world: str,
                                     history_text: str, message: str,
                                     dynamic_state: dict = None,
                                     recent_scenes: str = "") -> str:
    """分层构建角色扮演 prompt（含动态剧情上下文）。

    三层结构：
    - B层（背景锚点）：静态档案 + TruthLedger 动态状态（关系/秘密/位置）
    - C层（动机驱动）：静态目标/弧线 + arc_stage + 当前场景动机
    - A层（行动风格）：静态性格 + 当前情绪 + 场景中的行为模式
    """

    def _s(s):
        return str(s).strip() if s else ""
    ds = dynamic_state or {}

    # B 层：背景锚点（静态档案 + 动态状态）
    b_parts = []
    if _s(profile.get("identity")):
        b_parts.append(f"身份：{_s(profile['identity'])}")
    if _s(profile.get("faction")):
        b_parts.append(f"所属势力：{_s(profile['faction'])}")
    if _s(profile.get("backstory")):
        b_parts.append(f"背景故事：{_s(profile['backstory'])}")
    if _s(profile.get("cognitive_boundary")):
        b_parts.append(f"认知边界：{_s(profile['cognitive_boundary'])}")
    # 静态关系
    rels = profile.get("relationships", {})
    if isinstance(rels, dict) and rels:
        rel_text = "；".join(f"{k}: {v}" for k, v in rels.items() if v)
        if rel_text:
            b_parts.append(f"人际关系（初始）：{rel_text}")
    # 动态注入：当前位置 + 关系变化 + 已知秘密
    if _s(ds.get("location")):
        b_parts.append(f"【当前】位置：{_s(ds['location'])}")
    d_rels = ds.get("relationships", {})
    if isinstance(d_rels, dict) and d_rels:
        d_rel_text = "；".join(f"{k}: {v}" for k, v in d_rels.items() if v)
        if d_rel_text:
            b_parts.append(f"【当前】关系变化：{d_rel_text}")
    secrets = ds.get("secrets_known", [])
    if secrets:
        b_parts.append(f"【当前】已知秘密：{'、'.join(str(s) for s in secrets)}")

    # C 层：动机驱动（多目标 + 动态弧光阶段）
    c_parts = []
    goals = profile.get("goals", [])
    if not isinstance(goals, list):
        goals = []
    if goals:
        goal_lines = []
        for g in goals:
            if isinstance(g, dict) and g.get("text"):
                w = g.get("weight", 1.0)
                goal_lines.append(f"{g['text']}（权重 {w:.1f}）")
            elif isinstance(g, str) and g:
                goal_lines.append(g)
        if goal_lines:
            c_parts.append(f"当前目标：\n  " + "\n  ".join(goal_lines))
    elif _s(profile.get("goal")):
        # 旧单目标回退
        c_parts.append(f"核心目标：{_s(profile['goal'])}")
    if _s(profile.get("arc")):
        c_parts.append(f"角色弧线（全篇）：{_s(profile['arc'])}")
    if _s(ds.get("arc_stage")):
        c_parts.append(f"【当前】弧光阶段：{_s(ds['arc_stage'])}")

    # A 层：行动风格（静态性格 + 动态情绪）
    a_parts = []
    if _s(profile.get("personality")):
        a_parts.append(f"性格：{_s(profile['personality'])}")
    if _s(profile.get("abilities")):
        a_parts.append(f"能力：{_s(profile['abilities'])}")
    if _s(profile.get("appearance")):
        a_parts.append(f"外貌：{_s(profile['appearance'])}")
    if _s(ds.get("emotion")):
        a_parts.append(f"【当前】情绪：{_s(ds['emotion'])}")
    if _s(ds.get("health")) and ds.get("health") != "正常":
        a_parts.append(f"【当前】身体状态：{_s(ds['health'])}")
    if _s(ds.get("realm")):
        a_parts.append(f"【当前】修炼境界：{_s(ds['realm'])}")

    # 拼接
    sections = []
    if b_parts:
        sections.append("## 背景锚点（你不能违背的事实）\n" + "\n".join(f"- {p}" for p in b_parts))
    if c_parts:
        sections.append("## 动机驱动（你当前最关心的事）\n" + "\n".join(f"- {p}" for p in c_parts))
    if a_parts:
        sections.append("## 行动风格（你说话的方式）\n" + "\n".join(f"- {p}" for p in a_parts))

    profile_text = "\n\n".join(sections) if sections else (_s(profile.get("description", "")) or "无详细设定")

    # 注入最近出场场景
    scenes_section = ""
    if recent_scenes:
        scenes_section = f"\n\n## 最近出场场景（你刚刚经历了这些）\n{recent_scenes}"

    prompt = (
        f"你是小说中的角色【{character}】。\n\n"
        f"{profile_text}{scenes_section}\n\n"
        f"世界观背景：{world}\n\n"
        f"以下是之前的对话：\n{history_text}\n\n"
        f"用户说：{message}\n\n"
        f"对话规则：\n"
        f"1. 你的认知以【当前】标记的状态为准，它们可能已与初始设定不同\n"
        f"2. 你的认知以认知边界为准，不得超出边界之外的知识。你不知道背景锚点 + 已知秘密之外的事，不要编造\n"
        f"3. 你的言行由当前动机驱动，说话风格匹配当前情绪和性格\n"
        f"4. 保持第一人称，直接回复对话内容，不要解释"
    )
    return prompt


def _consistency_check(character: str, profile: dict, reply: str,
                       message: str, gen) -> bool:
    """角色一致性门禁：检查回复是否违反 B 层背景锚点。

    返回 True 表示通过，False 表示失败（回复含矛盾或越界信息）。
    仅当角色有足够 B 层信息时才执行检查，否则直接通过。
    """
    b_parts = []
    for field, label in [
        ("identity", "身份"), ("faction", "势力"), ("backstory", "背景故事"),
    ]:
        val = str(profile.get(field, "")).strip()
        if val:
            b_parts.append(f"{label}：{val}")

    if not b_parts:
        return True  # 无 B 层信息，跳过检查

    b_text = "\n".join(b_parts)

    check_prompt = (
        f"你是角色一致性检查器。判断角色回复是否违反设定。\n\n"
        f"角色【{character}】的已知事实：\n{b_text}\n\n"
        f"用户说：{message}\n"
        f"角色回复：{reply}\n\n"
        f"检查：角色是否说了他不知道的事？是否与设定矛盾？\n"
        f"只回答 PASS 或 FAIL:一句话说明问题。"
    )

    try:
        result = gen.ai.generate(check_prompt)
        if not result:
            return True  # 检查失败时宽容通过
        return not result.strip().upper().startswith("FAIL")
    except Exception as e:
        logger.warning(f"[Chat] 一致性检查异常，跳过: {e}")
        return True


# ── 请求模型 ──
class ChatTalkRequest(BaseModel):
    character: str
    message: str
    history: Optional[List[dict]] = None


# ── 路由 ──
@router.get("/characters")
def list_characters(pagination: PaginationParams = Depends()):
    """获取当前项目可用角色列表。
    合并 character_settings 与 meta 中的角色，按 name 去重。
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")

    characters = []
    # 优先从 SQLite characters 表读取（新版角色数据）
    characters.extend(_parse_characters_from_list(state.project.characters))
    # 兼容旧格式 character_settings（char_N_name 格式）
    characters.extend(_parse_characters_from_settings(state.project.character_settings))
    # 兼容 meta 中的角色（如有）
    characters.extend(_parse_characters_from_meta(state.project.meta))

    seen = set()
    unique = []
    for c in characters:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        unique.append(c)

    total = len(unique)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    return paginated(unique[start:end], pagination.page, pagination.page_size, total)


@router.post("/talk")
def chat_talk(data: ChatTalkRequest):
    """以指定角色身份回复消息。

    请求体：{character, message, history}
    构建角色扮演 prompt，调用 AI 客户端生成回复，返回 {ok, reply}。
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    if not data.character or not data.character.strip():
        return err(ErrorCode.VALIDATION_ERROR, "缺少角色名")
    if not data.message or not data.message.strip():
        return err(ErrorCode.VALIDATION_ERROR, "缺少消息内容")

    character = data.character.strip()
    message = sanitize_light(data.message.strip())

    try:
        # 获取角色完整档案（含所有分层字段）
        profile = _get_character_full_profile(character)
        if not profile:
            return err(ErrorCode.VALIDATION_ERROR, f"未找到角色「{character}」，请先在设定面板中添加角色。")

        # 世界观背景
        world = ""
        if state.project.meta:
            world = state.project.meta.get("world_setting", "") or ""

        # 格式化历史对话
        history_text = ""
        if data.history:
            lines = []
            for h in data.history:
                if not isinstance(h, dict):
                    continue
                role = h.get("role", "")
                content = h.get("content", "")
                if role == "user":
                    lines.append(f"用户：{content}")
                elif role == "assistant":
                    lines.append(f"{character}：{content}")
                elif role:
                    lines.append(f"{role}：{content}")
            history_text = "\n".join(lines)

        # 调用现有 AI 客户端
        gen = get_generator()
        if gen is None or gen.ai is None:
            return err(ErrorCode.INTERNAL_ERROR, "AI 客户端未初始化，请先配置 AI")

        # 获取角色动态状态（TruthLedger 运行时追踪）
        dynamic_state = _get_character_dynamic_state(character)

        # 提取最近章节中的角色出场场景
        recent_scenes = _extract_character_scenes(character)

        # 分层构建角色扮演 prompt（含动态剧情上下文）
        prompt = _build_layered_character_prompt(
            character, profile, world, history_text, message,
            dynamic_state=dynamic_state, recent_scenes=recent_scenes,
        )
        reply = gen.ai.generate(prompt)

        # 校验返回结果
        if not reply or not reply.strip():
            return err(ErrorCode.INTERNAL_ERROR, "AI 未返回内容")
        if reply.startswith("[生成失败") or reply.startswith("[错误]"):
            return {**err(ErrorCode.AI_FAILED, "AI 生成回复失败"), "error": reply}

        # 一致性门禁：检查是否违反 B 层背景锚点
        if not _consistency_check(character, profile, reply, message, gen):
            logger.warning(f"[Chat] 角色【{character}】一致性检查未通过，重新生成")
            # 追加惩罚约束后重试一次
            retry_prompt = prompt + (
                "\n\n【重要提醒】你刚才的回复存在以下问题：说了角色不该知道的事，或与角色设定矛盾。"
                "请严格按照「背景锚点」的已知事实重新作答。"
            )
            reply = gen.ai.generate(retry_prompt)
            if not reply or not reply.strip():
                return err(ErrorCode.INTERNAL_ERROR, "AI 重新生成后未返回内容")

        logger.info(f"[Chat] 角色【{character}】对话成功，回复 {len(reply)} 字")
        return {"ok": True, "reply": reply}
    except Exception as e:
        logger.exception("[Chat] 角色对话失败")
        return err(ErrorCode.INTERNAL_ERROR, f"对话失败: {e}")
