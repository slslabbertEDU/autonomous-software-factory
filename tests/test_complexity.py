"""Unit tests for complexity bucket classification."""


from autonomous_software_factory.orchestrator.complexity import (
    BUCKET_TIMEOUTS_HOURS,
    classify_complexity,
    get_timeout_hours,
    get_timeout_seconds,
)
from autonomous_software_factory.pipeline.models import ComplexityBucket


class TestBucketTimeouts:
    def test_nano_timeout(self) -> None:
        assert get_timeout_hours(ComplexityBucket.NANO) == 4
        assert get_timeout_seconds(ComplexityBucket.NANO) == 14400

    def test_micro_timeout(self) -> None:
        assert get_timeout_hours(ComplexityBucket.MICRO) == 8
        assert get_timeout_seconds(ComplexityBucket.MICRO) == 28800

    def test_standard_timeout(self) -> None:
        assert get_timeout_hours(ComplexityBucket.STANDARD) == 16
        assert get_timeout_seconds(ComplexityBucket.STANDARD) == 57600

    def test_complex_timeout(self) -> None:
        assert get_timeout_hours(ComplexityBucket.COMPLEX) == 24
        assert get_timeout_seconds(ComplexityBucket.COMPLEX) == 86400

    def test_critical_timeout(self) -> None:
        assert get_timeout_hours(ComplexityBucket.CRITICAL) == 48
        assert get_timeout_seconds(ComplexityBucket.CRITICAL) == 172800

    def test_all_buckets_have_timeouts(self) -> None:
        for bucket in ComplexityBucket:
            assert bucket in BUCKET_TIMEOUTS_HOURS


class TestClassifyComplexity:
    def test_simple_crud_classified_as_nano(self) -> None:
        result = classify_complexity("Simple CRUD API for managing users")
        assert result.bucket == ComplexityBucket.NANO

    def test_payment_classified_as_critical(self) -> None:
        result = classify_complexity("Payment processing service")
        assert result.bucket == ComplexityBucket.CRITICAL

    def test_financial_flag_overrides(self) -> None:
        result = classify_complexity("Simple list endpoint", is_financial=True)
        assert result.bucket == ComplexityBucket.CRITICAL
        assert result.confidence == 1.0

    def test_realtime_classified_as_complex(self) -> None:
        result = classify_complexity("Real-time chat with WebSocket support")
        assert result.bucket == ComplexityBucket.COMPLEX

    def test_auth_classified_as_standard(self) -> None:
        result = classify_complexity("Multi-user application with OAuth authentication")
        assert result.bucket == ComplexityBucket.STANDARD

    def test_multi_entity_classified_as_micro(self) -> None:
        result = classify_complexity("Dashboard with multi-entity relationship reports")
        assert result.bucket == ComplexityBucket.MICRO

    def test_has_realtime_flag_upgrades(self) -> None:
        result = classify_complexity("Simple list endpoint", has_realtime=True)
        assert result.bucket == ComplexityBucket.COMPLEX

    def test_has_auth_flag_upgrades_nano_to_standard(self) -> None:
        result = classify_complexity("Simple CRUD endpoint", has_auth=True)
        assert result.bucket == ComplexityBucket.STANDARD

    def test_many_entities_upgrades_nano_to_micro(self) -> None:
        entities = ["User", "Order", "Product", "Category", "Review", "Tag"]
        result = classify_complexity("Basic API", entities=entities)
        assert result.bucket == ComplexityBucket.MICRO

    def test_timeout_hours_in_result(self) -> None:
        result = classify_complexity("Payment gateway", is_financial=True)
        assert result.timeout_hours == 48

    def test_timeout_seconds_in_result(self) -> None:
        result = classify_complexity("Payment gateway", is_financial=True)
        assert result.timeout_seconds == 172800

    def test_matched_keywords_populated(self) -> None:
        result = classify_complexity("WebSocket streaming with queue")
        assert len(result.matched_keywords) > 0

    def test_compliance_classified_as_critical(self) -> None:
        result = classify_complexity("HIPAA compliance audit trail system")
        assert result.bucket == ComplexityBucket.CRITICAL

    def test_distributed_classified_as_complex(self) -> None:
        result = classify_complexity("Distributed event-driven architecture")
        assert result.bucket == ComplexityBucket.COMPLEX

    def test_no_keywords_defaults_to_nano(self) -> None:
        result = classify_complexity("Something completely generic")
        assert result.bucket == ComplexityBucket.NANO
        assert result.confidence == 0.3
