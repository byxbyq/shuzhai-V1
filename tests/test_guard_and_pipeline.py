# -*- coding: utf-8 -*-
"""书斋 V66 — 门禁/防幻觉/分镜补齐项 回归测试

覆盖：
- GuardPipeline 五门禁触发/放行
- P3-2 防幻觉检查幂等（OPEN 不重复报，mark_fixed 后可再报）
- SB-7 carried_state 跨镜头状态继承
- SB-9 双平台词替换
- SB-10 GENRE_PRESETS 完整性
- P2-1 max_rounds=2 生效
- P2-2 ctx_layer 三层排除
- P3-1 六席位 DAG 构建与预置模板
- P3-4 用量统计 by_model + 时间窗
"""
import time


# ═══════════════════════════════════════════
# GuardPipeline 五门禁
# ═══════════════════════════════════════════

class TestGuardPipeline:

    def _pipeline(self):
        from backend.services.guard_pipeline import create_default_pipeline
        return create_default_pipeline()

    def test_clean_content_passes(self):
        p = self._pipeline()
        paras = [
            "山雨欲来，客栈里的灯火被风吹得忽明忽暗。",
            "掌柜拨弄着算盘，心里盘算今日的进项。",
            "一位戴斗笠的剑客推门而入，肩头还挂着雨水。",
            "角落里的说书人清了清嗓子，拍下醒木。",
            "楼上雅间传来瓷碗碰的轻响，有人低声叹息。",
            "门外马蹄声远去，夜色重新归于寂静。",
        ]
        report = p.run("\n\n".join(paras))
        assert report.passed is True
        assert report.blocked is False

    def test_cjk_ngram_repeat_blocks(self):
        p = self._pipeline()
        content = ("他握紧了手中的长剑，" * 20)
        report = p.run(content)
        assert report.blocked is True
        assert any(i.guard_name == "cjk_ngram_repeat" for i in report.issues)

    def test_paragraph_start_repeat_warns(self):
        p = self._pipeline()
        # 段首两字仅四种且各重复两次，其余内容各不相同避免触发 n-gram 门禁
        bodies = [
            "向山门拾级而上，露水打湿了石阶。",
            "见远处灯火渐近，马蹄声碎。",
            "洒在瓦片上泛起一层银霜。",
            "卷起檐下铜铃轻响不止。",
            "入古寺时香灰尚未冷透。",
            "着江面渔火三两点摇曳。",
            "照得庭院老槐影子斜长。",
            "落在渡口孤舟的蓬顶上。",
        ]
        starts = ["他走", "她看", "月光", "风起"]
        paras = [f"{starts[i % 4]}{bodies[i]}" for i in range(8)]
        report = p.run("\n\n".join(paras))
        assert any(i.guard_name == "paragraph_start_repeat" for i in report.issues)
        # WARN 不阻断
        assert report.passed is True

    def test_required_clues_all_missed_blocks(self):
        p = self._pipeline()
        report = p.run("普通正文内容", context={
            "required_clues": ["青冥剑诀", "玄天令牌"],
            "clue_match_mode": "exact",
        })
        assert report.blocked is True
        assert any(i.guard_name == "required_clues" for i in report.issues)

    def test_required_clues_hit_passes(self):
        p = self._pipeline()
        report = p.run("他祭出青冥剑诀，又取出玄天令牌。", context={
            "required_clues": ["青冥剑诀", "玄天令牌"],
        })
        assert report.passed is True
        assert not any(i.guard_name == "required_clues" for i in report.issues)

    def test_min_word_count_blocks(self):
        p = self._pipeline()
        report = p.run("短文本", context={"min_words": 100})
        assert report.blocked is True
        assert any(i.guard_name == "min_word_count" for i in report.issues)

    def test_consecutive_summary_endings_warns(self):
        p = self._pipeline()
        # 段落末尾不加句号，保证切分后最后一句非空
        paras = [
            f"战斗的过程曲折离奇，细节{i}不可尽述，总而言之，他赢了" for i in range(4)
        ]
        report = p.run("\n\n".join(paras))
        assert any(i.guard_name == "consecutive_summary_endings" for i in report.issues)


# ═══════════════════════════════════════════
# P3-2 防幻觉检查
# ═══════════════════════════════════════════

class _FakeCharState:
    def __init__(self, name, realm=""):
        self.name = name
        self.realm = realm
        self.is_alive = True


class _FakeLedger:
    def __init__(self):
        self.character_states = {
            "林惊羽": _FakeCharState("林惊羽", realm="金丹期"),
        }


class TestHallucinationGuard:

    def test_near_miss_detected(self):
        from backend.services.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        # 正文不含规范名，仅含近似名「林惊鸿」
        report = guard.check("林惊鸿提剑而来，站在远处。", ledger=_FakeLedger())
        assert report["new_issues"], "近似名应被检出"
        assert report["new_issues"][0]["issue_type"] == "near_miss_name"

    def test_open_idempotent(self):
        from backend.services.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        content = "林惊鸿与人对峙。"
        first = guard.check(content, ledger=_FakeLedger())
        assert len(first["new_issues"]) == 1
        # OPEN 状态重复检查不重复上报
        second = guard.check(content, ledger=_FakeLedger())
        assert second["new_issues"] == []
        assert second["open_total"] == 1

    def test_mark_fixed_allows_rereport(self):
        from backend.services.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        content = "林惊鸿与人对峙。"
        first = guard.check(content, ledger=_FakeLedger())
        sig = first["new_issues"][0]["signature"]
        assert guard.mark_fixed(sig) is True
        again = guard.check(content, ledger=_FakeLedger())
        assert len(again["new_issues"]) == 1

    def test_realm_mismatch_detected(self):
        from backend.services.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        report = guard.check("林惊羽的境界是元婴期，众人哗然。", ledger=_FakeLedger())
        assert any(i["issue_type"] == "realm_mismatch" for i in report["new_issues"])


# ═══════════════════════════════════════════
# SB-7 跨镜头状态继承
# ═══════════════════════════════════════════

class TestStateInheritance:

    def _service(self):
        from backend.services.storyboard_service import StoryboardService
        return StoryboardService.__new__(StoryboardService)

    def _shot(self, scene_description="", prompt_full=""):
        from backend.services.storyboard_ir import StoryboardShot
        return StoryboardShot(index=0, scene_description=scene_description, prompt_full=prompt_full)

    def test_carried_state_inherited(self):
        svc = self._service()
        s1 = self._shot(scene_description="他手臂流血，衣袍破碎，手中握着断剑。")
        s2 = self._shot(prompt_full="第二镜基础描述")
        svc._inherit_state([s1, s2])
        assert s2.carried_state, "第二镜应继承状态"
        assert any("剑" in v or "伤" in k or "血" in v for k, v in s2.carried_state.items())
        assert "[状态继承:" in s2.prompt_full

    def test_first_shot_no_carried(self):
        svc = self._service()
        s1 = self._shot(scene_description="他手臂流血。")
        svc._inherit_state([s1])
        assert s1.carried_state == {}


# ═══════════════════════════════════════════
# SB-9 双平台词替换 / SB-10 赛道预设
# ═══════════════════════════════════════════

class TestPlatformAndGenre:

    def test_douyin_filter_replaces(self):
        from backend.services.storyboard_prompts import apply_platform_filter
        out = apply_platform_filter("画面中鲜血飞溅，尸体倒地。", "douyin")
        assert "鲜血" not in out
        assert "尸体" not in out
        assert "暗红痕迹" in out

    def test_empty_platform_noop(self):
        from backend.services.storyboard_prompts import apply_platform_filter
        text = "画面中鲜血飞溅。"
        assert apply_platform_filter(text, "") == text

    def test_genre_presets_complete(self):
        from backend.services.storyboard_prompts import GENRE_PRESETS, get_genre_preset
        expected = {"古风甜宠", "高燃打斗", "现代逆袭", "悬疑重生"}
        assert expected.issubset(set(GENRE_PRESETS.keys()))
        for name in expected:
            preset = get_genre_preset(name)
            for key in ("style_note", "camera_words", "light_words", "palette_hint", "negative_words"):
                assert preset.get(key), f"{name} 缺少 {key}"


# ═══════════════════════════════════════════
# P2-1 max_rounds / P2-2 ctx_layer
# ═══════════════════════════════════════════

class TestRewriteAndCompressor:

    def test_max_rounds_default_is_two(self):
        from backend.services.rewrite_loop import RewriteConfig, get_rewrite_config
        assert RewriteConfig().max_rounds == 2
        assert get_rewrite_config().max_rounds == 2

    def test_ctx_layer_excluded_dropped(self):
        from backend.services.context_compressor import compress_context
        msgs = [
            {"role": "user", "content": "保留我", "ctx_layer": "draft"},
            {"role": "assistant", "content": "丢弃我", "ctx_layer": "excluded"},
            {"role": "user", "content": "当前问题"},
        ]
        out = compress_context(msgs, strategy="full", task_type="check")
        contents = [m.get("content", "") for m in out]
        assert not any("丢弃我" in c for c in contents)
        # draft 在非生成类任务中被丢弃
        assert not any("保留我" in c for c in contents)

    def test_ctx_layer_draft_kept_for_generation(self):
        from backend.services.context_compressor import compress_context
        msgs = [
            {"role": "user", "content": "草稿内容甲", "ctx_layer": "draft"},
            {"role": "user", "content": "当前问题"},
        ]
        out = compress_context(msgs, strategy="full", task_type="generate")
        assert any("草稿内容甲" in m.get("content", "") for m in out)

    def test_ctx_layer_archived_merged(self):
        from backend.services.context_compressor import compress_context
        msgs = [
            {"role": "assistant", "content": "归档信息一", "ctx_layer": "archived"},
            {"role": "assistant", "content": "归档信息二", "ctx_layer": "archived"},
            {"role": "user", "content": "当前问题"},
        ]
        out = compress_context(msgs, strategy="full", task_type="general")
        merged = [m for m in out if "[归档摘要]" in m.get("content", "")]
        assert len(merged) == 1
        assert "归档信息一" in merged[0]["content"] and "归档信息二" in merged[0]["content"]


# ═══════════════════════════════════════════
# P3-1 六席位流水线 / SB-11 预置模板
# ═══════════════════════════════════════════

class TestSixSeatPipeline:

    def test_graph_structure(self):
        from backend.services.six_seat_pipeline import build_six_seat_graph, SIX_SEAT_ORDER
        built = build_six_seat_graph(chapter_index=0)
        graph = built["graph"]
        assert len(graph.nodes) == 6
        assert len(graph.edges) == 5
        assert len(built["instances"]) == len(SIX_SEAT_ORDER)
        assert graph.validate() == []

    def test_preset_pipelines_contains_six_seats_and_storyboard(self):
        from backend.flow_engine.nodes.official import get_preset_pipelines
        ids = {p["id"] for p in get_preset_pipelines()}
        assert "pipeline_six_seats" in ids
        assert "pipeline_chapter_to_storyboard" in ids


# ═══════════════════════════════════════════
# P3-4 用量统计
# ═══════════════════════════════════════════

class TestUsageStats:

    def _client(self):
        from backend.ai_client import AIClient
        c = AIClient.__new__(AIClient)
        c.usage_log = []
        return c

    def test_by_model_and_windows(self):
        c = self._client()
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 10 * 86400))
        c.usage_log = [
            {"timestamp": now, "provider": "deepseek", "model": "deepseek-chat",
             "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost_cny": 0.01},
            {"timestamp": old, "provider": "kimi", "model": "moonshot-v1-8k",
             "prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300, "cost_cny": 0.02},
        ]
        stats = c.get_usage_stats()
        assert "deepseek/deepseek-chat" in stats["by_model"]
        assert stats["by_model"]["deepseek/deepseek-chat"]["calls"] == 1
        # 24h 窗口只含最新一条；10 天前的一条在 30d 窗口内
        assert stats["windows"]["24h"]["calls"] == 1
        assert stats["windows"]["30d"]["calls"] == 2
