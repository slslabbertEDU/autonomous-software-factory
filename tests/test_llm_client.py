"""Tests for the shared LLM client utilities."""

from pipeline.shared.llm_client import (
    LLMClient,
    build_prompt_with_context,
    estimate_token_count,
)


def test_build_prompt_basic() -> None:
    messages = build_prompt_with_context(
        system_prompt="You are a coder.",
        user_content="Implement the payment module.",
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a coder."
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Implement the payment module."


def test_build_prompt_with_context_files() -> None:
    files = [
        {"path": "models.py", "content": "class Account: pass"},
        {"path": "api.py", "content": "def create(): pass"},
    ]
    messages = build_prompt_with_context(
        system_prompt="System",
        user_content="Task",
        context_files=files,
    )
    assert len(messages) == 3
    assert "CONTEXT:" in messages[1]["content"]
    assert "models.py" in messages[1]["content"]
    assert "api.py" in messages[1]["content"]


def test_build_prompt_with_dependency_constraint() -> None:
    messages = build_prompt_with_context(
        system_prompt="System",
        user_content="Task",
        dependency_constraint="fastapi==0.115.6",
    )
    assert len(messages) == 3
    assert "DEPENDENCY CONSTRAINTS" in messages[1]["content"]
    assert "fastapi==0.115.6" in messages[1]["content"]


def test_estimate_token_count() -> None:
    text = "a" * 400
    assert estimate_token_count(text) == 100


def test_extract_json_strips_fences() -> None:
    raw = '```json\n{"key": "value"}\n```'
    cleaned = LLMClient._extract_json(raw)
    assert cleaned == '{"key": "value"}'


def test_extract_json_plain() -> None:
    raw = '{"key": "value"}'
    cleaned = LLMClient._extract_json(raw)
    assert cleaned == '{"key": "value"}'
