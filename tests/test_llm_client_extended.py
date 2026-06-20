"""Extended tests for pipeline/shared/llm_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from pipeline.shared.llm_client import (
    LLMClient,
    LLMResponse,
    ModelRole,
    build_prompt_with_context,
    estimate_token_count,
)


class TestModelRole:
    def test_coder_value(self) -> None:
        assert ModelRole.CODER == "coder"

    def test_reasoning_value(self) -> None:
        assert ModelRole.REASONING == "reasoning"


class TestLLMResponse:
    def test_creation(self) -> None:
        resp = LLMResponse(
            content="Hello world",
            model="qwen3-coder",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_seconds=0.5,
            cost_usd=0.001,
        )
        assert resp.content == "Hello world"
        assert resp.total_tokens == 150
        assert resp.cost_usd == 0.001


class TestLLMClientInit:
    @patch("pipeline.shared.llm_client.get_config")
    def test_default_config(self, mock_config: MagicMock) -> None:
        mock_llm_config = MagicMock()
        mock_config.return_value.llm = mock_llm_config
        client = LLMClient()
        assert client._config is mock_llm_config

    def test_custom_config(self) -> None:
        config = MagicMock()
        client = LLMClient(config=config)
        assert client._config is config

    def test_with_cost_tracker(self) -> None:
        config = MagicMock()
        tracker = MagicMock()
        client = LLMClient(config=config, cost_tracker=tracker)
        assert client._cost_tracker is tracker


class TestLLMClientGetClient:
    def test_coder_client_created(self) -> None:
        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "test-key"
        client = LLMClient(config=config)
        openai_client = client._get_client(ModelRole.CODER)
        assert openai_client is not None
        # Second call should return cached
        assert client._get_client(ModelRole.CODER) is openai_client

    def test_reasoning_client_created(self) -> None:
        config = MagicMock()
        config.reasoning_endpoint = "http://localhost:8001/v1"
        config.reasoning_api_key = "test-key-2"
        client = LLMClient(config=config)
        openai_client = client._get_client(ModelRole.REASONING)
        assert openai_client is not None

    def test_get_model_name_coder(self) -> None:
        config = MagicMock()
        config.coder_model = "qwen3-coder-30b"
        client = LLMClient(config=config)
        assert client._get_model_name(ModelRole.CODER) == "qwen3-coder-30b"

    def test_get_model_name_reasoning(self) -> None:
        config = MagicMock()
        config.reasoning_model = "deepseek-r1"
        client = LLMClient(config=config)
        assert client._get_model_name(ModelRole.REASONING) == "deepseek-r1"


class TestLLMClientComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_response(self) -> None:
        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "key"
        config.coder_model = "test-model"
        config.default_max_tokens = 1024
        config.coder_cost_per_1k_tokens = 0.001

        client = LLMClient(config=config)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        mock_choice = MagicMock()
        mock_choice.message.content = "Generated code here"

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_openai):
            result = await client.complete(
                messages=[{"role": "user", "content": "Write hello world"}],
                role=ModelRole.CODER,
            )

        assert isinstance(result, LLMResponse)
        assert result.content == "Generated code here"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50
        assert result.total_tokens == 150

    @pytest.mark.asyncio
    async def test_complete_with_cost_tracker(self) -> None:
        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "key"
        config.coder_model = "test-model"
        config.default_max_tokens = 1024
        config.coder_cost_per_1k_tokens = 0.001

        cost_tracker = MagicMock()
        client = LLMClient(config=config, cost_tracker=cost_tracker)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 100

        mock_choice = MagicMock()
        mock_choice.message.content = "result"

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_openai):
            await client.complete(
                messages=[{"role": "user", "content": "test"}],
            )

        cost_tracker.record_llm_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_no_usage(self) -> None:
        """Handle response with no usage info."""
        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "key"
        config.coder_model = "test-model"
        config.default_max_tokens = 1024
        config.coder_cost_per_1k_tokens = 0.001

        client = LLMClient(config=config)

        mock_choice = MagicMock()
        mock_choice.message.content = "response"

        mock_response = MagicMock()
        mock_response.usage = None
        mock_response.choices = [mock_choice]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_openai):
            result = await client.complete(
                messages=[{"role": "user", "content": "test"}],
            )

        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0


class TestLLMClientCompleteJson:
    @pytest.mark.asyncio
    async def test_complete_json_parses_model(self) -> None:
        class TestModel(BaseModel):
            name: str
            value: int

        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "key"
        config.coder_model = "test-model"
        config.default_max_tokens = 1024
        config.coder_cost_per_1k_tokens = 0.001

        client = LLMClient(config=config)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 20

        mock_choice = MagicMock()
        mock_choice.message.content = '{"name": "test", "value": 42}'

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_openai):
            parsed, response = await client.complete_json(
                messages=[{"role": "user", "content": "give json"}],
                response_model=TestModel,
            )

        assert isinstance(parsed, TestModel)
        assert parsed.name == "test"
        assert parsed.value == 42

    @pytest.mark.asyncio
    async def test_complete_json_strips_markdown_fences(self) -> None:
        class SimpleModel(BaseModel):
            ok: bool

        config = MagicMock()
        config.coder_endpoint = "http://localhost:8000/v1"
        config.coder_api_key = "key"
        config.coder_model = "test-model"
        config.default_max_tokens = 1024
        config.coder_cost_per_1k_tokens = 0.001

        client = LLMClient(config=config)

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 20

        mock_choice = MagicMock()
        mock_choice.message.content = '```json\n{"ok": true}\n```'

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_openai):
            parsed, _ = await client.complete_json(
                messages=[{"role": "user", "content": "give json"}],
                response_model=SimpleModel,
            )

        assert parsed.ok is True


class TestExtractJson:
    def test_plain_json(self) -> None:
        assert LLMClient._extract_json('{"key": "value"}') == '{"key": "value"}'

    def test_json_fence(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        assert LLMClient._extract_json(text) == '{"key": "value"}'

    def test_generic_fence(self) -> None:
        text = '```\n{"key": "value"}\n```'
        assert LLMClient._extract_json(text) == '{"key": "value"}'

    def test_whitespace_handling(self) -> None:
        text = '  \n  {"key": "value"}  \n  '
        assert LLMClient._extract_json(text) == '{"key": "value"}'


class TestEstimateCost:
    def test_coder_cost(self) -> None:
        config = MagicMock()
        config.coder_cost_per_1k_tokens = 0.002
        client = LLMClient(config=config)
        cost = client._estimate_cost(ModelRole.CODER, 1000, 500)
        assert cost == pytest.approx(0.003)

    def test_reasoning_cost(self) -> None:
        config = MagicMock()
        config.reasoning_cost_per_1k_tokens = 0.01
        client = LLMClient(config=config)
        cost = client._estimate_cost(ModelRole.REASONING, 2000, 1000)
        assert cost == pytest.approx(0.03)


class TestBuildPromptWithContext:
    def test_basic_prompt(self) -> None:
        messages = build_prompt_with_context(
            system_prompt="You are a helpful assistant",
            user_content="Write a function",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Write a function"

    def test_with_context_files(self) -> None:
        files = [
            {"path": "main.py", "content": "print('hello')"},
            {"path": "utils.py", "content": "def helper(): pass"},
        ]
        messages = build_prompt_with_context(
            system_prompt="System",
            user_content="Implement feature",
            context_files=files,
        )
        assert len(messages) == 3
        assert "CONTEXT" in messages[1]["content"]
        assert "main.py" in messages[1]["content"]
        assert "utils.py" in messages[1]["content"]

    def test_with_dependency_constraint(self) -> None:
        messages = build_prompt_with_context(
            system_prompt="System",
            user_content="Implement",
            dependency_constraint="fastapi==0.115.6",
        )
        assert len(messages) == 3
        assert "DEPENDENCY CONSTRAINTS" in messages[1]["content"]
        assert "fastapi==0.115.6" in messages[1]["content"]

    def test_with_both_context_and_deps(self) -> None:
        files = [{"path": "app.py", "content": "code"}]
        messages = build_prompt_with_context(
            system_prompt="System",
            user_content="Task",
            context_files=files,
            dependency_constraint="pydantic==2.10.3",
        )
        assert len(messages) == 3
        context_msg = messages[1]["content"]
        assert "app.py" in context_msg
        assert "DEPENDENCY CONSTRAINTS" in context_msg


class TestEstimateTokenCount:
    def test_empty_string(self) -> None:
        assert estimate_token_count("") == 0

    def test_short_text(self) -> None:
        assert estimate_token_count("hello") == 1

    def test_longer_text(self) -> None:
        text = "a" * 100
        assert estimate_token_count(text) == 25

    def test_realistic_code(self) -> None:
        code = "def hello_world():\n    print('Hello, World!')\n"
        tokens = estimate_token_count(code)
        assert tokens > 0
        assert tokens == len(code) // 4
