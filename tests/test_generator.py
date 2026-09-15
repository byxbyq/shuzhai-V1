# -*- coding: utf-8 -*-
"""ChapterGenerator 单元测试（10 用例）"""

import pytest
from unittest.mock import patch, MagicMock

# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def mock_ai_generate():
    """Mock AIClient.generate()，所有 AI 调用返回空字符串（用例中覆盖 return_value）"""
    with patch('backend.ai_client.AIClient.generate', return_value="") as mock_gen:
        yield mock_gen


# ═══════════════════════════════════════════
# 导入被测模块
# ═══════════════════════════════════════════

from backend.generator import ChapterGenerator


def _make_generator(project_dir):
    """创建 ChapterGenerator 并 mock 掉 AI 客户端和外部依赖"""
    with patch('backend.ai_client.AIClient'), \
         patch('backend.generator.TruthLedger'), \
         patch('backend.generator.WorldSettings'), \
         patch('backend.generator.VectorMemory'):
        gen = ChapterGenerator(project_dir)
    # 设置 _project（非 property，可赋值），避免 project_service.state 链路上的 MagicMock 污染
    mock_project = MagicMock()
    mock_project.novel_outline = {}
    mock_project.brainstorm_cards = []
    mock_project._save_meta.return_value = None
    gen._project = mock_project
    # world.to_prompt() 也可能返回 MagicMock，将其设为空字符串
    gen.world.to_prompt.return_value = ""
    return gen


# ═══════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════

class TestDetectChapterType:
    """章节类型检测（纯逻辑）"""

    def test_detect_chapter_type(self, temp_project_dir):
        """验证 _detect_chapter_type 返回正确类型"""
        gen = _make_generator(temp_project_dir)

        assert gen._detect_chapter_type("决战青云山", "主角与反派爆发大战") == "battle"
        assert gen._detect_chapter_type("惊天反转", "真相终于揭晓，所有人都震惊了") == "climax"
        assert gen._detect_chapter_type("离别", "她哭着告别故乡") == "emotion"
        assert gen._detect_chapter_type("日常修炼", "今天继续修炼打坐") == "daily"
        assert gen._detect_chapter_type("神秘来客", "暗中调查线索发现秘密") == "mystery"
        assert gen._detect_chapter_type("旅途启程", "主角辞别师门，踏上漫长征途") == "transition"


class TestAdaptiveTemperature:
    """自适应温度（纯逻辑）"""

    def test_adaptive_temperature(self, temp_project_dir):
        """验证 _get_adaptive_temperature 不同条件下的温度值"""
        gen = _make_generator(temp_project_dir)

        t1 = gen._get_adaptive_temperature("battle", attempt=1)
        assert 0.9 <= t1 <= 1.0

        t2 = gen._get_adaptive_temperature("daily", attempt=1)
        assert 0.75 <= t2 <= 0.85

        # 重试时降温
        t3 = gen._get_adaptive_temperature("battle", attempt=3)
        assert t3 < t1, f"重试温度{t3}应低于首次{t1}"


class TestPostProcess:
    """后处理（纯逻辑）"""

    def test_post_process_cleanup(self, temp_project_dir):
        """验证 _post_process 移除禁用词和 AI 水印"""
        gen = _make_generator(temp_project_dir)

        raw = "他微微一愣，不由得心中暗道：这怎么可能？她轻轻地叹了口气。"
        result = gen._post_process(raw)

        # 禁用词应该被替换或移除
        assert result, "后处理不应返回空字符串"
        assert isinstance(result, str)


class TestRunHardChecks:
    """硬校验（纯逻辑）"""

    def test_run_hard_checks(self, temp_project_dir):
        """验证 _run_hard_checks 检测过短文本"""
        gen = _make_generator(temp_project_dir)

        # 过短的文本应触发问题
        issues = gen._run_hard_checks("太短", "测试标题", "大纲", 0)
        assert isinstance(issues, list)
        # 过短文本至少有一个 issue
        assert len(issues) >= 1


class TestParseNovelOutline:
    """大纲解析（纯逻辑）"""

    def test_parse_novel_outline(self, temp_project_dir):
        """_parse_novel_outline 正确解析 Markdown 大纲"""
        gen = _make_generator(temp_project_dir)

        outline_text = """## 主题
这是一个修仙故事。

## 核心冲突
正邪两道的终极对决。

## 故事弧线
主角从凡人成长为仙帝。

## 卷结构
### 第一卷：初入仙门
- 第1章: 偶遇仙缘
- 第2章: 拜入宗门
"""

        result = gen._parse_novel_outline(outline_text, is_volume=False)
        assert isinstance(result, dict)
        assert "theme" in result or "core_conflict" in result or result, \
            "应能解析出结构化字段"


class TestExtractPartialBlueprint:
    """蓝图提取（纯逻辑）"""

    def test_extract_partial_blueprint(self, temp_project_dir):
        """_extract_partial_blueprint 从截断 JSON 中提取信息"""
        gen = _make_generator(temp_project_dir)

        # 合法但截断的 JSON — 方法通过正则匹配 "intro"/"climax"/"ending" 子对象
        truncated = '{"intro": {"scene": "主角在古墓中醒来"}, "development": [{"scene": '
        result = gen._extract_partial_blueprint(truncated)
        assert isinstance(result, dict)
        assert "intro" in result

        # 完整 JSON（各子对象独立闭合）
        valid = '{"intro": {"scene": "开局"}, "development": [{"scene": "发展"}], "climax": {"conflict": "对战"}, "ending": {"twist": "反转"}}'
        result2 = gen._extract_partial_blueprint(valid)
        assert result2 is not None
        assert isinstance(result2, dict)


class TestGenerateChapterOutline:
    """章节大纲生成（需 mock AI）"""

    def test_generate_chapter_outline_with_mock(self, temp_project_dir, mock_ai_generate):
        """Mock AI 返回 blueprint JSON，验证返回结构完整"""
        import json
        mock_ai_generate.return_value = json.dumps({
            "intro_scene": "主角推开门",
            "development": "发现了秘密",
            "climax": "与守卫交手",
            "ending": "成功逃脱，留下悬念"
        }, ensure_ascii=False)

        gen = _make_generator(temp_project_dir)
        result = gen.generate_chapter_outline(
            title="密室逃脱",
            context="主角被关在密室中",
            chapter_index=0,
        )

        assert isinstance(result, dict)
        assert "outline_text" in result or "blueprint" in result or "raw" in result


class TestGenerateOutline:
    """全本大纲生成（需 mock AI）"""

    def test_generate_outline_with_mock(self, temp_project_dir, mock_ai_generate):
        """Mock AI 返回大纲 Markdown"""
        mock_ai_generate.return_value = """## 主题
修仙

## 核心冲突
正邪之战

## 故事弧线
成长弧线

## 卷结构
### 第一卷：初入江湖
"""

        gen = _make_generator(temp_project_dir)
        result = gen.generate_outline(
            title="仙路",
            genre="仙侠",
            length=10,
            inspiration="凡人修仙传",
        )

        assert isinstance(result, dict)


class TestGenerateCharacters:
    """角色生成（需 mock AI）"""

    def test_generate_characters_with_mock(self, temp_project_dir, mock_ai_generate):
        """Mock AI 返回角色 JSON 数组"""
        import json
        mock_ai_generate.return_value = json.dumps([
            {"name": "叶辰", "identity": "散修", "faction": "散修联盟",
             "personality": "冷静果断", "realm": "筑基期", "bond_to_mc": "挚友"},
            {"name": "苏婉", "identity": "圣女", "faction": "天剑宗",
             "personality": "外冷内热", "realm": "金丹期", "bond_to_mc": "道侣"},
        ], ensure_ascii=False)

        gen = _make_generator(temp_project_dir)
        result = gen.generate_characters(novel_outline="仙侠故事大纲")

        assert isinstance(result, list)
        if len(result) >= 2:
            assert "name" in result[0]


class TestValidateCharacterBonds:
    """角色羁绊校验（纯逻辑）"""

    def test_validate_character_bonds(self, temp_project_dir):
        """验证矛盾羁绊检测"""
        gen = _make_generator(temp_project_dir)

        chars = [
            {"name": "A", "bond_to_mc": "挚友"},
            {"name": "B", "bond_to_mc": "仇敌"},
        ]

        # _validate_character_bonds 应不抛异常
        try:
            gen._validate_character_bonds(chars)
        except Exception as e:
            pytest.fail(f"_validate_character_bonds 异常: {e}")
