# -*- coding: utf-8 -*-
"""TruthLedger 单元测试（11 用例）"""

# ═══════════════════════════════════════════
# 导入被测模块和数据类
# ═══════════════════════════════════════════

from backend.ledger import (
    TruthLedger,
    CharacterState,
)


# ═══════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════

class TestTruthLedgerInit:
    """初始化测试"""

    def test_init_creates_empty_ledger(self, temp_project_dir):
        """新 ledger 所有集合为空，project_dir 正确"""
        ledger = TruthLedger(temp_project_dir)

        assert ledger.project_dir == temp_project_dir
        assert ledger.character_states == {}
        assert ledger.foreshadowing == []
        assert ledger.chapter_logs == []
        assert ledger.artifacts == {}
        assert ledger.factions == {}
        assert ledger.locations == {}
        assert ledger.subplots == []


class TestTruthLedgerCharacter:
    """角色管理测试"""

    def test_ensure_character_creates_and_returns(self, temp_project_dir):
        """ensure_character 创建并返回角色"""
        ledger = TruthLedger(temp_project_dir)
        ledger.ensure_character("张三")

        assert "张三" in ledger.character_states
        cs = ledger.character_states["张三"]
        assert isinstance(cs, CharacterState)
        assert cs.name == "张三"

    def test_update_character_modifies_fields(self, temp_project_dir):
        """update_character 修改角色字段"""
        ledger = TruthLedger(temp_project_dir)
        ledger.update_character("张三", health="受伤", location="山洞", realm="筑基期")

        cs = ledger.character_states["张三"]
        assert cs.health == "受伤"
        assert cs.location == "山洞"
        assert cs.realm == "筑基期"


class TestTruthLedgerForeshadowing:
    """伏笔系统测试"""

    def test_add_and_recover_hook_lifecycle(self, temp_project_dir):
        """伏笔完整生命周期：add_hook → pendant → abandon → recover_hook → recovered"""
        ledger = TruthLedger(temp_project_dir)

        hid = ledger.add_hook("神秘黑衣人出现", planted_chapter=3)
        pending = ledger.get_pending_hooks()
        assert any(h.id == hid for h in pending), "新伏笔应在 pending 列表"
        assert all(h.status in ("planted", "active") for h in pending if h.id == hid)

        # abandon → recover
        assert ledger.abandon_hook(hid, reason="暂时搁置")
        assert ledger.recover_hook(hid, chapter=8)
        for h in ledger.foreshadowing:
            if h.id == hid:
                assert h.status == "recovered"
                assert h.recovery_chapter == 8

    def test_activate_nearby_hooks_windows(self, temp_project_dir):
        """activate_nearby_hooks 窗口范围正确"""
        ledger = TruthLedger(temp_project_dir)

        # 种植多个伏笔，不同预期回收章节
        ledger.add_hook("伏笔1", planted_chapter=1, expected_recovery_chapter=5)
        ledger.add_hook("伏笔2", planted_chapter=1, expected_recovery_chapter=10)
        ledger.add_hook("伏笔3", planted_chapter=1, expected_recovery_chapter=3)

        # 当前第5章，window=3 → 激活预期回收章在 [2,8] 范围内的
        activated = ledger.activate_nearby_hooks(5, window=3)

        # 伏笔1（预期5章）和伏笔3（预期3章）应在范围内被激活
        # 伏笔2（预期10章）不应被激活
        for h in ledger.foreshadowing:
            if h.expected_recovery_chapter == 5:
                assert h.status == "active", f"预期5章的伏笔应被激活，实际状态={h.status}"
            elif h.expected_recovery_chapter == 3:
                assert h.status == "active", f"预期3章的伏笔应被激活"
            elif h.expected_recovery_chapter == 10:
                assert h.status == "planted", f"预期10章的伏笔不应被激活"


class TestTruthLedgerH2Analysis:
    """追读力分析测试"""

    def test_get_read_pull_scoring(self, temp_project_dir):
        """验证 get_read_pull 评分计算和等级划分"""
        ledger = TruthLedger(temp_project_dir)

        # 创建混合强度+弧线伏笔
        ledger.add_hook("高强悬念", planted_chapter=1, strength=5,
                        arc_type="long", expected_recovery_chapter=50)
        ledger.add_hook("中等悬念", planted_chapter=2, strength=3,
                        arc_type="medium", expected_recovery_chapter=8)
        ledger.add_hook("短期钩子", planted_chapter=3, strength=2,
                        arc_type="short", expected_recovery_chapter=5)

        result = ledger.get_read_pull(current_chapter=4)

        assert "score" in result
        assert "level" in result
        assert result["active_count"] == 3
        assert isinstance(result["score"], int)
        assert result["level"] in ("strong", "moderate", "weak", "empty")
        # 三种弧线类型都覆盖
        assert result["arc_score"] > 0


class TestTruthLedgerH1Analysis:
    """Strand 节奏系统测试"""

    def test_get_strand_stats_red_lines(self, temp_project_dir):
        """注入 Q/F/C 线型序列，验证红线规则"""
        ledger = TruthLedger(temp_project_dir)

        # 构造章节序列: Q连续6章→红色触发
        for i in range(6):
            ledger.log_chapter(
                chapter=i, title=f"第{i}章",
                strand_type="Q",
                characters=[], word_count=2000
            )
        # 再加一些其他类型
        ledger.log_chapter(chapter=6, title="第6章", strand_type="F",
                          characters=[], word_count=2000)
        ledger.log_chapter(chapter=7, title="第7章", strand_type="C",
                          characters=[], word_count=2000)

        result = ledger.get_strand_stats()

        assert result["total"] == 8
        assert "red_lines" in result
        # Q连续6章应触发红线
        assert any("Q" in rl for rl in result["red_lines"]), \
            f"应触发Q连续超5章红线: {result['red_lines']}"


class TestTruthLedgerSnapshot:
    """快照测试"""

    def test_snapshot_roundtrip(self, temp_project_dir):
        """take_snapshot → restore_snapshot 数据完全恢复"""
        ledger = TruthLedger(temp_project_dir)

        # 添加数据
        ledger.ensure_character("主角")
        ledger.update_character("主角", location="青云山", realm="金丹期")
        ledger.add_hook("藏宝图碎片", planted_chapter=1, strength=3, arc_type="long")
        ledger.log_chapter(chapter=0, title="序章", characters=["主角"], word_count=3000)

        # 备份原始状态
        original_chars = dict(ledger.character_states)
        original_hooks = len(ledger.foreshadowing)
        original_logs = len(ledger.chapter_logs)

        # 创建快照
        snapshot = ledger.take_snapshot(chapter_idx=0)
        snapshot_id = snapshot["snapshot_id"]

        # 修改数据（模拟后续章节的变更）
        ledger.update_character("主角", location="幽冥谷", realm="元婴期")
        ledger.add_hook("新伏笔", planted_chapter=2)
        ledger.log_chapter(chapter=1, title="第一章", characters=["主角"], word_count=2500)

        # 恢复快照
        result = ledger.restore_snapshot(snapshot_id, backup_current=False)
        assert result is True, "restore_snapshot 应返回 True"

        # 验证恢复后的状态与原始一致
        assert len(ledger.foreshadowing) == original_hooks, \
            f"伏笔数量应恢复为{original_hooks}，实际{len(ledger.foreshadowing)}"
        assert len(ledger.chapter_logs) == original_logs, \
            f"章节日志数量应恢复为{original_logs}，实际{len(ledger.chapter_logs)}"

        restored_cs = ledger.character_states.get("主角")
        assert restored_cs is not None
        assert restored_cs.location == "青云山", f"位置应恢复为'青云山'，实际'{restored_cs.location}'"
        assert restored_cs.realm == "金丹期", f"境界应恢复为'金丹期'，实际'{restored_cs.realm}'"


class TestTruthLedgerPersistence:
    """持久化测试"""

    def test_save_and_reload_persistence(self, temp_project_dir):
        """save 后创建新 TruthLedger，数据一致"""
        ledger = TruthLedger(temp_project_dir)

        ledger.ensure_character("李四")
        ledger.update_character("李四", location="长安城", realm="筑基期")
        ledger.add_hook("幕后黑手现身", planted_chapter=1, strength=4)

        # flush 强制落盘
        ledger.flush()

        # 创建新实例加载
        ledger2 = TruthLedger(temp_project_dir)
        assert "李四" in ledger2.character_states
        cs = ledger2.character_states["李四"]
        assert cs.location == "长安城"
        assert cs.realm == "筑基期"
        assert len(ledger2.foreshadowing) == 1


class TestTruthLedgerSubplot:
    """支线测试"""

    def test_subplot_lifecycle(self, temp_project_dir):
        """register → update → resolve 全生命周期"""
        ledger = TruthLedger(temp_project_dir)

        sid = ledger.register_subplot(
            title="寻找失落神器",
            description="主角踏上旅程寻找传说神器",
            start_chapter=3,
            related_characters=["主角", "师傅"],
            priority=1,
            target_chapter=15,
        )

        # 更新进度
        success = ledger.update_subplot(sid, chapter=5,
                                        event="在古墓中发现线索",
                                        status="advancing")
        assert success

        # 确认在活跃列表中
        active = ledger.get_active_subplots()
        assert any(s.id == sid for s in active)

        # 解决支线
        success = ledger.resolve_subplot(sid, chapter=15)
        assert success

        # 不再出现在活跃列表
        active_after = ledger.get_active_subplots()
        assert not any(s.id == sid for s in active_after)


class TestTruthLedgerArtifact:
    """神器/道具测试"""

    def test_artifact_crud(self, temp_project_dir):
        """add → update → destroy 完整 CRUD"""
        ledger = TruthLedger(temp_project_dir)

        ledger.add_artifact(
            artifact_id="qingming_sword",
            name="青冥剑",
            type="weapon",
            grade="灵",
            owner="主角",
            description="上古名剑，剑身湛蓝如青天",
        )

        # 更新
        ledger.update_artifact("qingming_sword", owner="新主人", grade="仙")

        # 确认存在
        all_arts = ledger.get_all_artifacts()
        assert any(a.get("id") == "qingming_sword" for a in all_arts)

        # 销毁
        ledger.destroy_artifact("qingming_sword")

        # 仍在列表中，但 destroyed=True
        all_after = ledger.get_all_artifacts()
        destroyed_arts = [a for a in all_after if a.get("id") == "qingming_sword"]
        assert len(destroyed_arts) == 1
        assert destroyed_arts[0].get("destroyed") is True
