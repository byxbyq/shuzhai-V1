# -*- coding: utf-8 -*-
"""AIClient 单元测试（13 用例）

测试范围：
  - AIClientException 异常类
  - AIClient 构造 / _ensure_defaults / get_provider / set_provider
  - get_model_for_task 多模型路由
  - generate_safe 安全调用（mock HTTP 层）
  - close / __del__
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def temp_config_file():
    """创建临时 ai_config.json，测试后清理"""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False,
                                      encoding='utf-8')
    json.dump({"provider": "deepseek"}, tmp)
    tmp.close()
    yield tmp.name
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


@pytest.fixture
def ai_client(temp_config_file):
    """创建 AIClient 实例（mock httpx.Client + _save_config）"""
    with patch('backend.ai_client.httpx.Client', autospec=True), \
         patch('backend.ai_client.AIClient._save_config'):
        from backend.ai_client import AIClient
        client = AIClient(config_path=temp_config_file)
    return client


# ═══════════════════════════════════════════
# 导入
# ═══════════════════════════════════════════

from backend.ai_client import AIClient, AIClientException


# ═══════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════

class TestAIClientException:
    """异常类测试"""

    def test_default_error_type(self):
        exc = AIClientException("something went wrong")
        assert exc.error_type == "unknown"
        assert str(exc) == "something went wrong"

    def test_custom_error_type(self):
        exc = AIClientException("network down", error_type="network_error")
        assert exc.error_type == "network_error"

    def test_inherits_from_exception(self):
        exc = AIClientException("test")
        assert isinstance(exc, Exception)


class TestAIClientInit:
    """初始化测试"""

    def test_creates_with_config_path(self, temp_config_file):
        """指定 config_path 可正常创建"""
        with patch('backend.ai_client.httpx.Client', autospec=True), \
             patch('backend.ai_client.AIClient._save_config'):
            client = AIClient(config_path=temp_config_file)
        assert client.config_path == temp_config_file
        assert client.config["provider"] == "deepseek"
        client.close()

    def test_loads_existing_config(self, ai_client):
        """从已有 config 文件加载"""
        assert ai_client.config["provider"] == "deepseek"

    def test_defaults_populated_on_empty_config(self):
        """空配置时 _ensure_defaults 填充所有 provider"""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False,
                                          encoding='utf-8')
        json.dump({}, tmp)
        tmp.close()
        try:
            with patch('backend.ai_client.httpx.Client', autospec=True):
                from backend.ai_client import AIClient
                client = AIClient(config_path=tmp.name)

            # _ensure_defaults 应该填充 provider + 所有默认 provider 配置
            assert client.config["provider"] == "deepseek"
            assert "deepseek" in client.config
            assert "openai" in client.config
            assert "ollama" in client.config
            assert "doubao" in client.config
            assert "kimi" in client.config
            assert client.config["deepseek"]["model"] == "deepseek-v4-flash"
            client.close()
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


class TestAIClientProvider:
    """Provider 管理测试"""

    def test_default_provider_deepseek(self, ai_client):
        assert ai_client.get_provider() == "deepseek"

    def test_config_with_custom_provider(self, temp_config_file):
        """loads existing config"""
        with open(temp_config_file, 'w', encoding='utf-8') as f:
            json.dump({"provider": "openai"}, f)
        with patch('backend.ai_client.httpx.Client', autospec=True), \
             patch('backend.ai_client.AIClient._save_config'):
            client = AIClient(config_path=temp_config_file)
        assert client.get_provider() == "openai"
        client.close()


class TestAIClientModelRouting:
    """多模型路由测试"""

    def test_get_model_for_task_chat(self, ai_client):
        model = ai_client.get_model_for_task("chat")
        assert model == "deepseek-v4-flash"

    def test_get_model_for_task_architecture(self, ai_client):
        model = ai_client.get_model_for_task("architecture")
        assert model == "deepseek-v4"

    def test_get_model_for_task_unknown_falls_back(self, ai_client):
        """未知 task_type 回退到 chat 模型"""
        model = ai_client.get_model_for_task("nonexistent_task")
        assert model == "deepseek-v4-flash"


class TestAIClientGenerateSafe:
    """generate_safe 安全调用测试"""

    def test_generate_safe_returns_tuple_on_success(self, ai_client):
        """generate_safe 成功时返回 (True, result)"""
        with patch.object(ai_client, 'generate', return_value="AI response here"):
            ok, result = ai_client.generate_safe("hello")
        assert ok is True
        assert result == "AI response here"

    def test_generate_safe_returns_false_on_error_string(self, ai_client):
        """generate 返回错误字符串时 generate_safe 返回 (False, str)"""
        with patch.object(ai_client, 'generate', return_value="[错误] API key invalid"):
            ok, result = ai_client.generate_safe("hello")
        assert ok is False
        assert "[错误]" in result


class TestAIClientClose:
    """资源释放测试"""

    def test_close_calls_client_close(self, ai_client):
        """close 调用底层 httpx Client 的 close()"""
        ai_client.close()
        ai_client._client.close.assert_called_once()

    def test_close_idempotent(self, ai_client):
        """重复 close 不抛出异常"""
        ai_client.close()
        ai_client.close()  # 不应报错
        assert ai_client._client.close.call_count == 2
