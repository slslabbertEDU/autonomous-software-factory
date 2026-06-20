"""Tests for configuration management."""

from pipeline.shared.config import (
    CostLimits,
    PipelineConfig,
    QAConfig,
    RevertThresholds,
    get_config,
)


def test_default_config_loads() -> None:
    config = PipelineConfig()
    assert config.llm.coder_model == "Qwen/Qwen3-Coder-30B-A3B-AWQ"
    assert config.llm.reasoning_model == "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"


def test_cost_limits_defaults() -> None:
    limits = CostLimits()
    assert limits.max_inference_calls_per_feature == 50
    assert limits.max_gpu_minutes_per_feature == 120.0
    assert limits.max_retries_global == 3


def test_revert_thresholds() -> None:
    thresholds = RevertThresholds()
    assert thresholds.error_rate == 0.01
    assert thresholds.p99_latency_increase == 2.0
    assert thresholds.cpu_sustained == 0.90
    assert thresholds.memory_leak_rate == 0.05


def test_qa_config() -> None:
    qa = QAConfig()
    assert qa.min_coverage_percent == 80.0
    assert qa.semantic_diff_threshold == 0.75
    assert qa.mypy_strict is True


def test_get_config_singleton() -> None:
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2
