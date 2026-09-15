# -*- coding: utf-8 -*-
"""distill_service 模块级函数与 DistillService 单元测试（8 用例）"""

import os
import json
from unittest.mock import patch


# ═══════════════════════════════════════════
# 导入被测模块
# ═══════════════════════════════════════════

from backend.services.distill_service import (
    split_chapters,
    sample_text,
    parse_yaml_candidates,
    slugify,
    content_object_to_markdown,
    save_state_memory,
)


# ═══════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════

class TestSplitChapters:
    """split_chapters 测试"""

    def test_split_chapters(self):
        """含'第X章'标记的文本正确切分"""
        text = """第1章 初入江湖
主角下山历练。

第2章 偶遇仙缘
在洞穴中发现古剑。

第3章 宗门考核
通过入门测试。"""

        chapters = split_chapters(text)
        assert len(chapters) >= 3, f"应至少切出3章，实际{len(chapters)}"
        # split_chapters 按章节标记分割，标题被丢弃，只保留正文
        assert any("下山历练" in ch for ch in chapters), "应包含第1章正文"
        assert any("洞穴" in ch and "古剑" in ch for ch in chapters), "应包含第2章正文"


class TestSampleText:
    """sample_text 测试"""

    def test_sample_text(self):
        """超长文本采样不超过 max_chars"""
        long_text = "这是一个测试句子。" * 100  # 约 1000 字符
        result = sample_text(long_text, max_chars=500)

        assert len(result) <= 500 + 200, f"采样结果长度应接近上限，实际{len(result)}"
        assert "开头部分" in result
        assert "中间部分" in result
        assert "结尾部分" in result

    def test_sample_text_short(self):
        """短文本不截断"""
        short = "只有一句话。"
        result = sample_text(short, max_chars=500)
        assert short in result


class TestParseYamlCandidates:
    """parse_yaml_candidates 测试"""

    def test_parse_yaml_candidates(self):
        """YAML 块正常解析为候选列表"""
        yaml_text = """```yaml
- id: plot-001
  title: 三幕式高潮迭起
  type: three-act
  source_chapter: 第12章
  source_quote: "他突然意识到…"
  summary: 这是一个结构技巧描述
  tags: [高潮, 反转, 结构]
- id: plot-002
  title: 多线交织
  type: multi-thread
  tags: [支线, 交织]
```"""

        candidates = parse_yaml_candidates(yaml_text)
        assert len(candidates) >= 2
        assert candidates[0]["id"] == "plot-001"
        assert candidates[0]["title"] == "三幕式高潮迭起"


class TestSlugify:
    """slugify 测试"""

    def test_slugify(self):
        """中文书名生成合法 slug"""
        assert slugify("斗破苍穹") == "斗破苍穹"
        assert slugify("The Great Ruler") == "the-great-ruler"
        assert slugify("凡人修仙传") == "凡人修仙传"


class TestContentObjectToMarkdown:
    """content_object_to_markdown 测试"""

    def test_content_object_to_markdown(self):
        """dict 转 Markdown 包含各 RIA 字段"""
        content = {
            "reading": "原文引用内容",
            "interpretation": "方法论解释",
            "example": "案例说明",
            "trigger": "触发场景描述",
            "execution": "执行步骤",
            "boundary": "边界限制条件",
        }

        md = content_object_to_markdown(content, skill_name="测试技能")
        assert "测试技能" in md
        assert "原文引用" in md
        assert "方法论" in md
        assert isinstance(md, str)

    def test_content_object_to_markdown_empty(self):
        """空 dict 返回空字符串"""
        assert content_object_to_markdown({}) == ""
        assert content_object_to_markdown(None) == ""


class TestSaveStateMemory:
    """save_state_memory 测试"""

    def test_save_state_memory_without_transaction(self, temp_project_dir):
        """不传 project，走传统 write 方式"""
        state_data = {
            "chapter_index": 0,
            "characters": [{"name": "主角", "location": "青云山"}],
            "events": ["发现古剑"],
            "foreshadowing": {},
            "new_settings": [],
            "bridge": {"from_prev": "", "to_next": "前往洞穴"},
        }

        save_state_memory(temp_project_dir, 0, state_data)

        # 验证章节 JSON 文件存在
        mem_dir = os.path.join(temp_project_dir, "state_memory")
        ch_file = os.path.join(mem_dir, "000.json")
        idx_file = os.path.join(mem_dir, "_index.json")

        assert os.path.exists(ch_file), f"章节文件 {ch_file} 应存在"
        assert os.path.exists(idx_file), f"索引文件 {idx_file} 应存在"

        with open(ch_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["chapter_index"] == 0
        assert data["characters"][0]["name"] == "主角"

    def test_save_state_memory_with_transaction(self, temp_project_dir):
        """传入 project，走 TransactionContext 原子写入"""
        from unittest.mock import MagicMock
        mock_proj = MagicMock()
        mock_proj._save_meta.return_value = None

        state_data = {
            "chapter_index": 1,
            "characters": [],
            "events": ["修炼突破"],
            "foreshadowing": {},
            "new_settings": ["灵力等级系统"],
            "bridge": {"from_prev": "到达宗门", "to_next": "参加考核"},
        }

        save_state_memory(temp_project_dir, 1, state_data, project=mock_proj)

        mem_dir = os.path.join(temp_project_dir, "state_memory")
        ch_file = os.path.join(mem_dir, "001.json")
        idx_file = os.path.join(mem_dir, "_index.json")

        assert os.path.exists(ch_file)
        assert os.path.exists(idx_file)

        with open(ch_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["chapter_index"] == 1


class TestDistillSingleChapter:
    """distill_single_chapter 测试"""

    def test_distill_single_chapter_with_mock(self):
        """Mock _ai_generate / AIClient，验证返回结构化 state_data"""
        mock_result = json.dumps({
            "characters": [{"name": "萧炎", "location": "魔兽山脉", "mood": "冷静", "realm": "斗师", "items": [], "alive": True}],
            "events": ["击杀三阶魔兽"],
            "foreshadowing": {"planted": [], "resolved": []},
            "new_settings": [],
            "bridge": {"from_prev": "", "to_next": "继续深入山脉"},
        }, ensure_ascii=False)

        with patch('backend.services.distill_service.AIClient') as mock_ai:
            mock_ai.return_value.generate.return_value = mock_result
            from backend.services.distill_service import distill_single_chapter

            result = distill_single_chapter(
                chapter_text="萧炎走进魔兽山脉深处，准备猎杀三阶魔兽。",
                chapter_index=1,
                prev_state=None,
            )

        assert isinstance(result, dict)
        assert result["chapter_index"] == 1
