"""Centralized configuration for the Autonomous Software Factory.

All agent thresholds, model settings, cost limits, and operational parameters
are defined here. This eliminates magic numbers scattered across agents and
provides a single source of truth.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    """LLM endpoint and model configuration."""

    # Primary coder model (Qwen3-Coder-30B-A3B-AWQ on A10)
    coder_endpoint: str = "http://localhost:8000/v1"
    coder_model: str = "Qwen/Qwen3-Coder-30B-A3B-AWQ"
    coder_api_key: str = Field(default="", description="Set via ASF_LLM__CODER_API_KEY env var")

    # Reasoning model (DeepSeek-R1-Distill-Qwen-32B on A100)
    reasoning_endpoint: str = "http://localhost:8001/v1"
    reasoning_model: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
    reasoning_api_key: str = Field(default="", description="Set via ASF_LLM__REASONING_API_KEY env var")

    # Token budgets
    default_max_tokens: int = 4096
    max_context_tokens: int = 32768
    coder_context_budget: int = 12000  # ~8-12K per Architecture spec

    # Cost estimation (self-hosted GPU cost per 1K tokens)
    coder_cost_per_1k_tokens: float = 0.002
    reasoning_cost_per_1k_tokens: float = 0.008


class CostLimits(BaseModel):
    """Cost circuit breaker thresholds (from Architecture spec)."""

    max_inference_calls_per_feature: int = 50
    max_gpu_minutes_per_feature: float = 120.0
    max_retries_global: int = 3


class RevertThresholds(BaseModel):
    """SRE Agent revert thresholds (from Architecture spec)."""

    error_rate: float = 0.01  # 1% error rate
    p99_latency_increase: float = 2.0  # 2x latency increase
    cpu_sustained: float = 0.90  # 90% CPU for 5 minutes
    memory_leak_rate: float = 0.05  # 5% growth per 5 minutes


class QAConfig(BaseModel):
    """QA pipeline configuration."""

    min_coverage_percent: float = 80.0
    semantic_diff_threshold: float = 0.75
    mypy_strict: bool = True


class TemporalConfig(BaseModel):
    """Temporal orchestrator connection settings."""

    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "factory-pipeline"


class FireDrillConfig(BaseModel):
    """Fire drill timing thresholds."""

    detection_timeout_seconds: int = 300  # 5 minutes
    revert_timeout_seconds: int = 600  # 10 minutes


class PipelineConfig(BaseSettings):
    """Root configuration aggregating all sub-configs.

    Loads from environment variables with ASF_ prefix.
    """

    model_config = {"env_prefix": "ASF_", "env_nested_delimiter": "__"}

    llm: LLMConfig = Field(default_factory=LLMConfig)
    cost_limits: CostLimits = Field(default_factory=CostLimits)
    revert_thresholds: RevertThresholds = Field(default_factory=RevertThresholds)
    qa: QAConfig = Field(default_factory=QAConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    fire_drill: FireDrillConfig = Field(default_factory=FireDrillConfig)

    # Shadow deployment
    shadow_traffic_percent: float = 10.0
    shadow_duration_minutes: int = 15

    # Logging
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_config() -> PipelineConfig:
    """Get the singleton pipeline configuration."""
    return PipelineConfig()
