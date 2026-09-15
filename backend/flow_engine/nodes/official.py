# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 书斋官方节点注册

将所有 15 个书斋 Agent 注册为 Flow Engine 可编排节点。
每注册一个节点，前端即可拖拽连线，构造自定义写作流水线。
"""

import logging

from backend.flow_engine.registry import registry

logger = logging.getLogger(__name__)

# 延迟导入——避免循环依赖
_agents_cache = None


def _get_agent_instances():
    """获取所有 Agent 实例（延迟初始化）"""
    global _agents_cache
    if _agents_cache is not None:
        return _agents_cache

    from backend.agents.example_agents import register_all_agents
    _agents_cache = register_all_agents()
    return _agents_cache


def register_shuzhai_nodes():
    """
    将所有书斋 Agent 注册到全局 registry。
    调用一次即可，重复调用幂等。
    返回注册的节点数量。
    """
    from backend.flow_engine.nodes.adapter import wrap_agent

    agents = _get_agent_instances()
    registered = 0

    for agent in agents:
        node = wrap_agent(agent)
        node_cls = type(node)
        try:
            registry.register(node_cls)
            registered += 1
        except Exception as e:
            # 已注册过则跳过
            if "已存在" in str(e):
                pass
            else:
                logger.warning("[shuzhai_nodes] 注册 %s 失败: %s", node.node_id, e)

    # P3-1: 注册六席位自定义节点（reviser/factcheck/librarian）
    from backend.services.six_seat_pipeline import ReviserNode, FactcheckNode, LibrarianNode
    for node_cls in (ReviserNode, FactcheckNode, LibrarianNode):
        try:
            registry.register(node_cls)
            registered += 1
        except Exception:
            pass  # 已注册过则跳过

    logger.info(
        "[shuzhai_nodes] 已注册 %d/%d 个书斋节点到 Flow Engine",
        registered, len(agents),
    )
    return registered


def get_preset_pipelines() -> list:
    """
    预置常见写作流水线模板。

    返回格式（供前端加载）：
    [
        {
            "name": "章节生成流水线",
            "description": "大纲 -> 章节生成 -> 校验 -> 导出",
            "nodes": [...],
            "edges": [...]
        },
    ]
    """
    agent = _get_agent_instances()
    # 按 agent_id 建立索引
    by_id = {a.agent_id: a for a in agent}

    pipelines = [
        {
            "id": "pipeline_outline_to_export",
            "name": "大纲→章节→校验→导出",
            "description": "标准写作全流程：生成大纲 → 批量生成正文 → 连贯性检查 → 导出TXT",
            "nodes": [
                {"node_id": "shuzhai.outline", "params": {"message": "生成全部章节大纲"}},
                {"node_id": "shuzhai.chapter", "params": {"message": "生成全部章节正文"}},
                {"node_id": "shuzhai.validate", "params": {"message": "连贯性检查"}},
                {"node_id": "shuzhai.export", "params": {"message": "导出TXT"}},
            ],
            "edges": [
                {"from": 0, "from_port": "reply", "to": 1, "to_port": "message"},
                {"from": 1, "from_port": "reply", "to": 2, "to_port": "message"},
                {"from": 2, "from_port": "reply", "to": 3, "to_port": "message"},
            ],
        },
        {
            "id": "pipeline_world_upgrade",
            "name": "世界观→角色→大纲联动",
            "description": "建立世界观后生成角色，再生成与之匹配的大纲",
            "nodes": [
                {"node_id": "shuzhai.world", "params": {"message": "查看世界观"}},
                {"node_id": "shuzhai.character", "params": {"message": "生成所有人物档案"}},
                {"node_id": "shuzhai.outline", "params": {"message": "基于角色设定生成大纲"}},
            ],
            "edges": [
                {"from": 0, "from_port": "data", "to": 1, "to_port": "params"},
                {"from": 1, "from_port": "data", "to": 2, "to_port": "params"},
            ],
        },
        {
            "id": "pipeline_sync_and_search",
            "name": "记忆检索→AI对话",
            "description": "从项目记忆中检索相关信息，再与AI对话深度分析",
            "nodes": [
                {"node_id": "shuzhai.memory", "params": {"message": "检索关键事件"}},
                {"node_id": "shuzhai.ai", "params": {"message": "基于检索结果分析剧情走向"}},
            ],
            "edges": [
                {"from": 0, "from_port": "reply", "to": 1, "to_port": "message"},
            ],
        },
        {
            "id": "pipeline_six_seats",
            "name": "六席位写作流水线",
            "description": "P3-1 固定六席：大纲→正文→校验→修订→防幻觉→承诺台账",
            "nodes": [
                {"node_id": "shuzhai.outline", "params": {"message": "生成本章大纲"}},
                {"node_id": "shuzhai.chapter", "params": {"message": "按大纲生成章节正文"}},
                {"node_id": "shuzhai.validate", "params": {"message": "连贯性检查"}},
                {"node_id": "sixseat.reviser", "params": {}},
                {"node_id": "sixseat.factcheck", "params": {}},
                {"node_id": "sixseat.librarian", "params": {}},
            ],
            "edges": [
                {"from": 0, "from_port": "reply", "to": 1, "to_port": "message"},
                {"from": 1, "from_port": "reply", "to": 2, "to_port": "message"},
                {"from": 2, "from_port": "reply", "to": 3, "to_port": "message"},
                {"from": 3, "from_port": "reply", "to": 4, "to_port": "message"},
                {"from": 4, "from_port": "reply", "to": 5, "to_port": "message"},
            ],
        },
        {
            "id": "pipeline_chapter_to_storyboard",
            "name": "章节→分镜",
            "description": "SB-11：生成章节正文后转为视频分镜脚本",
            "nodes": [
                {"node_id": "shuzhai.chapter", "params": {"message": "生成章节正文"}},
                {"node_id": "shuzhai.storyboard", "params": {"message": "将章节正文转分镜"}},
            ],
            "edges": [
                {"from": 0, "from_port": "reply", "to": 1, "to_port": "message"},
            ],
        },
    ]
    return pipelines
