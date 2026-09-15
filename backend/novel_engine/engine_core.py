# -*- coding: utf-8 -*-
"""
小说引擎核心 - 桥接六轴碰撞图与书斋现有模块

职责：
  - 从 TruthLedger 读取角色状态，构建六轴关系图
  - 运行碰撞检测，生成碰撞事件
  - 将碰撞事件转化为自然语言灵感（brainstorm_cards 格式）
  - 持久化引擎状态

V2 扩展（四期融合）：
  - WorldTimeline: 世界时间轴管理
  - SwimlaneManager: 角色泳道生命周期管理
  - GoalScheduler: 多层级目标调度
  - CausalCollisionScheduler: 六轴增强版碰撞调度
  - ConsistencyChecker: 全局一致性校验
  - WorldRuleGuard: 世界观规则守卫
  - TimelineBranch: 时序回溯分支存档
"""
import json
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NovelEngineCore:
    """小说引擎核心类

    集成书斋的 AppState / TruthLedger / VectorMemory，
    提供六轴碰撞检测、角色泳道、目标调度、一致性校验等完整能力。
    """

    def __init__(self):
        # ─── 一期：基础模块 ───
        # 六轴关系图实例
        self.six_axis_graph = None
        # 碰撞历史记录
        self.collision_history: List[dict] = []

        # ─── 二期：调度层模块 ───
        self._world_timeline = None       # WorldTimeline（延迟初始化）
        self._swimlane_manager = None      # SwimlaneManager（延迟初始化）
        self._goal_scheduler = None        # GoalScheduler（延迟初始化）

        # ─── 三期：校验层模块 ───
        self._collision_scheduler = None   # CausalCollisionScheduler
        self._consistency_checker = None   # ConsistencyChecker
        self._rule_guard = None            # WorldRuleGuard

        # ─── 四期：回溯与输出 ───
        self._timeline_branch = None       # TimelineBranch

        # 尝试从磁盘加载已保存的状态
        self._load_state()

    # ─── 状态目录管理 ───

    def get_or_create_state_dir(self) -> Optional[str]:
        """获取或创建引擎状态目录 {project_dir}/novel_engine/

        Returns:
            状态目录绝对路径，若项目未打开则返回 None
        """
        # 延迟导入，避免项目未打开时的导入错误
        from backend.services.project_service import state
        if state.project is None:
            return None
        project_dir = state.project.project_dir
        state_dir = os.path.join(project_dir, "novel_engine")
        os.makedirs(state_dir, exist_ok=True)
        return state_dir

    # ─── V2 模块懒加载访问器 ───

    @property
    def world_timeline(self):
        """世界时间轴（懒加载）"""
        if self._world_timeline is None:
            from .scheduler import WorldTimeline
            self._world_timeline = WorldTimeline()
        return self._world_timeline

    @property
    def swimlane_manager(self):
        """角色泳道管理器（懒加载）"""
        if self._swimlane_manager is None:
            from .scheduler import SwimlaneManager
            self._swimlane_manager = SwimlaneManager()
            self._swimlane_manager.set_timeline(self.world_timeline)
        return self._swimlane_manager

    @property
    def goal_scheduler(self):
        """目标调度器（懒加载）"""
        if self._goal_scheduler is None:
            from .scheduler import GoalScheduler
            self._goal_scheduler = GoalScheduler()
            self._goal_scheduler.set_swimlane_manager(self.swimlane_manager)
        return self._goal_scheduler

    @property
    def collision_scheduler(self):
        """因果碰撞调度器（懒加载）"""
        if self._collision_scheduler is None:
            from .scheduler import CausalCollisionScheduler
            self._collision_scheduler = CausalCollisionScheduler()
            self._collision_scheduler.set_graph(self.six_axis_graph)
            self._collision_scheduler.set_swimlane_manager(self.swimlane_manager)
            self._collision_scheduler.set_timeline(self.world_timeline)
            # 绑定 TruthLedger 和 VectorMemory
            try:
                from backend.services.project_service import state
                if state.ledger is not None:
                    self._collision_scheduler.set_truth_ledger(state.ledger)
                if state.vector_memory is not None:
                    self._collision_scheduler.set_vector_memory(state.vector_memory)
            except Exception:
                pass
        return self._collision_scheduler

    @property
    def consistency_checker(self):
        """全局一致性校验器（懒加载）"""
        if self._consistency_checker is None:
            from .scheduler import ConsistencyChecker
            self._consistency_checker = ConsistencyChecker()
            self._consistency_checker.set_swimlane_manager(self.swimlane_manager)
            self._consistency_checker.set_timeline(self.world_timeline)
            self._consistency_checker.set_goal_scheduler(self.goal_scheduler)
            self._consistency_checker.set_collision_scheduler(self.collision_scheduler)
            try:
                from backend.services.project_service import state
                if state.ledger is not None:
                    self._consistency_checker.set_truth_ledger(state.ledger)
            except Exception:
                pass
        return self._consistency_checker

    @property
    def rule_guard(self):
        """世界观规则守卫（懒加载）"""
        if self._rule_guard is None:
            from .scheduler import WorldRuleGuard
            self._rule_guard = WorldRuleGuard()
            try:
                from backend.services.project_service import state
                if state.ledger is not None:
                    self._rule_guard.set_truth_ledger(state.ledger)
            except Exception:
                pass
        return self._rule_guard

    @property
    def timeline_branch(self):
        """时序回溯分支管理器（懒加载）"""
        if self._timeline_branch is None:
            from .scheduler import TimelineBranch
            self._timeline_branch = TimelineBranch()
            self._timeline_branch.set_timeline(self.world_timeline)
            self._timeline_branch.set_swimlane_manager(self.swimlane_manager)
            self._timeline_branch.set_goal_scheduler(self.goal_scheduler)
            self._timeline_branch.set_collision_scheduler(self.collision_scheduler)
            try:
                from backend.services.project_service import state
                if state.ledger is not None:
                    self._timeline_branch.set_truth_ledger(state.ledger)
            except Exception:
                pass
        return self._timeline_branch

    # ─── 角色数据读取 ───

    def get_characters_from_ledger(self) -> List[dict]:
        """从当前项目读取角色列表

        优先从 project.characters（人物卡）读取基础信息，
        再从 TruthLedger 补充状态数据（位置、心境、健康、境界、持有物等）。
        如果人物卡没有，则回退到 TruthLedger 的角色状态。

        Returns:
            角色字典列表，每项包含：
            name, description, location, emotion, health, realm,
            relationships, possessions, personality, background
            若项目未打开或无角色数据则返回空列表
        """
        try:
            from backend.services.project_service import get_ledger, state

            # 1. 从人物卡读取（主要来源）
            card_chars = {}
            if state.project and hasattr(state.project, 'characters') and state.project.characters:
                for c in state.project.characters:
                    name = c.get('name') or c.get('character_name') or ''
                    if not name:
                        continue
                    card_chars[name] = {
                        "name": name,
                        "description": c.get('description') or c.get('bio') or c.get('简介') or '',
                        "realm": c.get('realm') or c.get('境界') or c.get('realm_level') or '',
                        "location": c.get('location') or c.get('所在地') or '',
                        "emotion": c.get('emotion') or c.get('心境') or '',
                        "health": c.get('health') or c.get('健康') or 100,
                        "personality": c.get('personality') or c.get('性格') or '',
                        "background": c.get('background') or c.get('背景') or '',
                        "relationships": {},
                        "possessions": [],
                    }
                    # 解析关系字段（可能是字符串或 dict）
                    rel_raw = c.get('relationships') or c.get('人物关系') or c.get('relation') or ''
                    if isinstance(rel_raw, dict):
                        card_chars[name]["relationships"] = dict(rel_raw)
                    elif isinstance(rel_raw, str) and rel_raw.strip():
                        card_chars[name]["relationships"] = self._parse_relation_text(rel_raw, name)
                    # 解析持有物
                    pos = c.get('possessions') or c.get('持有物') or c.get('items') or []
                    if isinstance(pos, list):
                        card_chars[name]["possessions"] = list(pos)
                    elif isinstance(pos, str) and pos.strip():
                        card_chars[name]["possessions"] = [x.strip() for x in pos.split('，') if x.strip()]

            # 2. 从 TruthLedger 补充状态数据
            ledger = get_ledger()
            if ledger is not None:
                for name, cs in ledger.character_states.items():
                    if name in card_chars:
                        # 人物卡已有，补充状态
                        entry = card_chars[name]
                        if cs.location and not entry["location"]:
                            entry["location"] = cs.location
                        if cs.emotion and not entry["emotion"]:
                            entry["emotion"] = cs.emotion
                        if cs.realm and not entry["realm"]:
                            entry["realm"] = cs.realm
                        if cs.health:
                            entry["health"] = cs.health
                        if cs.relationships:
                            for rname, rdesc in cs.relationships.items():
                                if rname not in entry["relationships"]:
                                    entry["relationships"][rname] = rdesc
                        if cs.possessions:
                            for p in cs.possessions:
                                if p not in entry["possessions"]:
                                    entry["possessions"].append(p)
                    else:
                        # TruthLedger 有但人物卡没有，也加进去
                        card_chars[name] = {
                            "name": cs.name,
                            "description": '',
                            "location": cs.location,
                            "emotion": cs.emotion,
                            "health": cs.health,
                            "realm": cs.realm,
                            "personality": '',
                            "background": '',
                            "relationships": dict(cs.relationships) if cs.relationships else {},
                            "possessions": list(cs.possessions) if cs.possessions else [],
                        }

            return list(card_chars.values())

        except Exception as e:
            logger.warning("读取角色数据失败: %s", e)
            import traceback
            traceback.print_exc()
            return []

    def _parse_relation_text(self, text: str, self_name: str) -> Dict[str, str]:
        """从关系描述文本中解析出 对方角色名 -> 关系描述 的映射

        Args:
            text: 关系描述文本（如"林惊羽：师兄弟，好友，竞争对手\n碧瑶：敌对"）
            self_name: 当前角色名（用于跳过自身）

        Returns:
            关系字典
        """
        relations = {}
        if not text:
            return relations
        # 按行分割，每行尝试解析 "角色名：关系描述"
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for sep in ['：', ':', ' - ', '—', ' ']:
                if sep in line:
                    parts = line.split(sep, 1)
                    name = parts[0].strip()
                    desc = parts[1].strip() if len(parts) > 1 else ''
                    if name and name != self_name:
                        relations[name] = desc
                    break
        return relations

    # ─── 六轴图构建 ───

    def build_six_axis_graph_from_characters(self, characters: List[dict]):
        """根据角色列表构建六轴关系图

        遍历所有角色对，分析关系文本中的关键词，
        自动推断六轴各维度的权重值，生成有向边。

        Args:
            characters: get_characters_from_ledger() 返回的角色列表

        Returns:
            SixAxisGraph 实例
        """
        from .six_axis_graph import SixAxisGraph

        graph = SixAxisGraph()
        if not characters:
            return graph

        # 关键词 → 轴映射规则
        # 格式：(关键词列表, {轴: 值})
        rules = [
            (["敌", "对", "仇", "恨"], {"lr": -0.8, "sd": -0.6}),
            (["友", "盟", "信", "亲"], {"lr": 0.7, "sd": 0.5}),
            (["师", "尊", "长"], {"ud": 0.8}),
            (["徒", "弟", "卑"], {"ud": -0.8}),
            (["欠", "恩", "债"], {"fb": 0.6}),
            (["利用", "棋", "工具"], {"io": -0.7}),
        ]

        # 收集所有角色的 last_seen_chapter 用于时序轴
        chapter_map = {c["name"]: c.get("last_seen_chapter", 0)
                       for c in characters}

        # 遍历所有角色对，双向分析关系
        n = len(characters)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                src_char = characters[i]
                dst_char = characters[j]
                src_name = src_char["name"]
                dst_name = dst_char["name"]

                # 获取 src 对 dst 的关系描述
                rel_text = src_char.get("relationships", {}).get(dst_name, "")
                if not rel_text:
                    continue

                # 初始化六轴值
                axis_vals = {"fb": 0.0, "ud": 0.0, "lr": 0.0,
                             "sd": 0.0, "io": 0.0, "tm": 0.0}

                # 逐条规则匹配关键词
                for keywords, axis_map in rules:
                    for kw in keywords:
                        if kw in rel_text:
                            for axis, val in axis_map.items():
                                # 取绝对值最大的匹配（避免覆盖更强的信号）
                                if abs(val) > abs(axis_vals[axis]):
                                    axis_vals[axis] = val

                # 时序轴：基于两人最后出场章节的差值
                ch_src = chapter_map.get(src_name, 0)
                ch_dst = chapter_map.get(dst_name, 0)
                if ch_src > 0 and ch_dst > 0:
                    diff = ch_src - ch_dst
                    axis_vals["tm"] = round(min(max(diff / 50.0, -1.0), 1.0), 2)

                # 仅当至少有一个非零轴时才添加边
                has_signal = any(v != 0.0 for v in axis_vals.values())
                if has_signal:
                    graph.add_edge(
                        src=src_name, dst=dst_name,
                        fb=axis_vals["fb"], ud=axis_vals["ud"],
                        lr=axis_vals["lr"], sd=axis_vals["sd"],
                        io=axis_vals["io"], tm=axis_vals["tm"],
                        metadata={"relationship_text": rel_text},
                    )

        return graph

    # ─── 碰撞检测 ───

    def run_collision_detection(self) -> List[dict]:
        """执行完整的碰撞检测流程

        步骤：
          1. 从 TruthLedger 读取角色
          2. 构建六轴关系图
          3. 以 activation=1.0 激活所有角色节点
          4. 调用 detect_convergence 检测碰撞
          5. 格式化碰撞事件为字典列表

        Returns:
            碰撞事件字典列表，每项包含：
            collision_type, node_id, sources, total_activation,
            axis_breakdown, description
        """
        from .six_axis_graph import ConvergenceEvent

        # 第一步：获取角色
        characters = self.get_characters_from_ledger()
        if not characters:
            logger.info("无角色数据，跳过碰撞检测")
            return []

        # 第二步：构建六轴图
        self.six_axis_graph = self.build_six_axis_graph_from_characters(characters)
        stats = self.six_axis_graph.get_stats()
        logger.info("关系图构建完成: %d 节点, %d 边", stats['node_count'], stats['edge_count'])

        if stats["edge_count"] == 0:
            logger.info("无关系边，跳过碰撞检测")
            return []

        # 第三步：激活所有角色节点
        activated = {c["name"]: 1.0 for c in characters
                     if c["name"] in self.six_axis_graph.adj}

        # 第四步：碰撞检测
        events: List[ConvergenceEvent] = self.six_axis_graph.detect_convergence(activated)

        # 第五步：格式化结果
        collision_type_zh = {
            "causal_conflict": "因果冲突",
            "causal_cooperation": "因果合作",
            "interest_competition": "利益竞争",
            "interest_cooperation": "利益共赢",
            "ideology_conflict": "理念冲突",
            "ideology_resonance": "理念共鸣",
            "hierarchy_suppress": "层级压制",
            "hierarchy_rebellion": "层级反抗",
            "interaction_conflict": "交互冲突",
            "interaction_harmony": "交互和谐",
            "temporal_encounter": "时序遭遇",
            "multi_dimensional": "多维碰撞",
            "weak_encounter": "弱遭遇",
        }

        results = []
        for ev in events:
            desc = (f"角色 {', '.join(ev.sources)} 的力量汇聚到 {ev.node_id}，"
                    f"形成【{collision_type_zh.get(ev.collision_type, ev.collision_type)}】"
                    f"碰撞，总激活值 {ev.total_activation:.3f}")
            results.append({
                "collision_type": ev.collision_type,
                "collision_type_zh": collision_type_zh.get(ev.collision_type, ev.collision_type),
                "node_id": ev.node_id,
                "sources": ev.sources,
                "total_activation": ev.total_activation,
                "axis_breakdown": ev.axis_breakdown,
                "description": desc,
            })

        # 记录碰撞历史
        self.collision_history.extend(results)
        logger.info("检测到 %d 个碰撞事件", len(results))
        return results

    # ─── 灵感生成 ───

    def collisions_to_inspirations(self, collisions: List[dict]) -> List[dict]:
        """将碰撞事件转化为自然语言灵感

        每条灵感为 50-150 字的碰撞场景描述，
        适合作为书斋 brainstorm_cards 的内容。

        Args:
            collisions: run_collision_detection() 返回的碰撞列表

        Returns:
            灵感字典列表，每项包含 title, desc, impact, tags
        """
        inspirations = []
        for c in collisions:
            sources = c["sources"]
            node = c["node_id"]
            ctype = c.get("collision_type_zh", c["collision_type"])
            act = c["total_activation"]

            # 根据碰撞类型生成不同风格的描述
            if "冲突" in ctype or "竞争" in ctype:
                title = f"{node}的{ctype}危机"
                desc = (f"当{'、'.join(sources)}的影响力同时作用于{node}时，"
                        f"一股强烈的{ctype}正在酝酿。多方势力的交汇使得{node}"
                        f"陷入前所未有的困境，激活强度达{act:.2f}。"
                        f"这一碰撞点可能成为情节转折的关键节点，"
                        f"建议在此处设计戏剧性场景。")
            elif "共鸣" in ctype or "合作" in ctype or "和谐" in ctype:
                title = f"{node}的{ctype}契机"
                desc = (f"{'、'.join(sources)}与{node}之间产生了微妙的{ctype}信号。"
                        f"这种多方力量的正向汇聚，激活值{act:.2f}，"
                        f"暗示着合作或联盟的可能性。可以围绕这一契机"
                        f"构建信任建立或能力互补的情节线。")
            elif "压制" in ctype or "反抗" in ctype:
                title = f"{node}的{ctype}风暴"
                desc = (f"来自{'、'.join(sources)}的压力汇聚在{node}身上，"
                        f"形成{ctype}态势，激活值{act:.2f}。"
                        f"这种层级力量的碰撞往往预示着权力格局的变动，"
                        f"是塑造角色成长弧线的绝佳时机。")
            elif "多维" in ctype:
                title = f"{node}的多维碰撞漩涡"
                desc = (f"{'、'.join(sources)}从多个维度同时冲击{node}，"
                        f"因果、利益、理念等多条轴线交织，形成复杂的碰撞漩涡，"
                        f"激活值高达{act:.2f}。这种多维碰撞极为罕见，"
                        f"适合作为卷末高潮或重大转折点。")
            else:
                title = f"{node}的{ctype}事件"
                desc = (f"{'、'.join(sources)}与{node}之间存在{ctype}信号，"
                        f"激活值{act:.2f}。虽然强度不算很高，但可作为"
                        f"伏笔或过渡情节的素材，为后续更大的碰撞埋下种子。")

            # 根据激活值判断影响等级
            if act >= 0.8:
                impact = "high"
            elif act >= 0.4:
                impact = "medium"
            else:
                impact = "low"

            inspirations.append({
                "title": title,
                "desc": desc,
                "impact": impact,
                "tags": [ctype] + sources,
            })

        return inspirations

    # ─── 状态持久化 ───

    def save_state(self):
        """将引擎状态持久化到 engine_state.json

        保存内容包括：六轴图数据、碰撞历史记录，以及 V2 模块状态。
        """
        state_dir = self.get_or_create_state_dir()
        if state_dir is None:
            logger.warning("无项目目录，无法保存状态")
            return

        data = {
            "collision_history": self.collision_history[-50:],  # 保留最近50条
            "graph_data": self.six_axis_graph.to_dict() if self.six_axis_graph else None,
        }

        # V2 模块状态（仅保存已初始化的）
        if self._world_timeline is not None:
            data["world_timeline"] = self._world_timeline.to_dict()
        if self._swimlane_manager is not None:
            data["swimlane_manager"] = self._swimlane_manager.to_dict()
        if self._goal_scheduler is not None:
            data["goal_scheduler"] = self._goal_scheduler.to_dict()
        if self._timeline_branch is not None:
            data["timeline_branch"] = self._timeline_branch.to_dict()
        if self._rule_guard is not None:
            data["rule_guard"] = self._rule_guard.to_dict()

        path = os.path.join(state_dir, "engine_state.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("状态已保存: %s", path)
        except Exception as e:
            logger.warning("保存状态失败: %s", e)

    def _load_state(self):
        """从磁盘加载引擎状态（内部方法，__init__ 时调用）"""
        try:
            from backend.services.project_service import state
            if state.project is None:
                return
            state_dir = os.path.join(state.project.project_dir, "novel_engine")
            path = os.path.join(state_dir, "engine_state.json")
            if not os.path.exists(path):
                return

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 恢复碰撞历史
            self.collision_history = data.get("collision_history", [])

            # 恢复六轴图
            from .six_axis_graph import SixAxisGraph
            graph_data = data.get("graph_data")
            if graph_data:
                self.six_axis_graph = SixAxisGraph.from_dict(graph_data)

            # V2 模块恢复（延迟加载时使用）
            self._v2_saved_data = {
                "world_timeline": data.get("world_timeline"),
                "swimlane_manager": data.get("swimlane_manager"),
                "goal_scheduler": data.get("goal_scheduler"),
                "timeline_branch": data.get("timeline_branch"),
                "rule_guard": data.get("rule_guard"),
            }

            logger.info("状态已加载: %s", path)
        except Exception:
            # 初始化时加载失败是正常的（项目未打开等），静默处理
            self._v2_saved_data = {}
            pass
