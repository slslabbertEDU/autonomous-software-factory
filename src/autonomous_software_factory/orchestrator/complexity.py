"""Complexity bucket classification for feature requests."""

from __future__ import annotations

from dataclasses import dataclass

from autonomous_software_factory.pipeline.models import ComplexityBucket

BUCKET_TIMEOUTS_HOURS: dict[ComplexityBucket, int] = {
    ComplexityBucket.NANO: 4,
    ComplexityBucket.MICRO: 8,
    ComplexityBucket.STANDARD: 16,
    ComplexityBucket.COMPLEX: 24,
    ComplexityBucket.CRITICAL: 48,
}

COMPLEXITY_KEYWORDS: dict[ComplexityBucket, list[str]] = {
    ComplexityBucket.CRITICAL: [
        "payment", "medical", "compliance", "financial", "hipaa",
        "pci", "gdpr", "encryption", "audit",
    ],
    ComplexityBucket.COMPLEX: [
        "real-time", "websocket", "queue", "streaming", "pubsub",
        "event-driven", "distributed",
    ],
    ComplexityBucket.STANDARD: [
        "auth", "multi-user", "database", "role", "permission",
        "session", "oauth",
    ],
    ComplexityBucket.MICRO: [
        "multi-entity", "relationship", "join", "aggregate",
        "report", "dashboard",
    ],
    ComplexityBucket.NANO: [
        "crud", "single", "simple", "basic", "list", "create",
    ],
}


@dataclass
class ClassificationResult:
    """Result of complexity classification with explanation."""

    bucket: ComplexityBucket
    timeout_hours: int
    matched_keywords: list[str]
    confidence: float

    @property
    def timeout_seconds(self) -> int:
        return self.timeout_hours * 3600


def classify_complexity(
    description: str,
    entities: list[str] | None = None,
    has_auth: bool = False,
    has_realtime: bool = False,
    is_financial: bool = False,
) -> ClassificationResult:
    """Classify a feature request into a complexity bucket.

    Uses keyword matching and explicit flags. Higher complexity wins.
    """
    description_lower = description.lower()
    entities = entities or []

    if is_financial:
        return ClassificationResult(
            bucket=ComplexityBucket.CRITICAL,
            timeout_hours=BUCKET_TIMEOUTS_HOURS[ComplexityBucket.CRITICAL],
            matched_keywords=["financial"],
            confidence=1.0,
        )

    best_bucket = ComplexityBucket.NANO
    best_keywords: list[str] = []
    best_score = 0

    for bucket in [
        ComplexityBucket.CRITICAL,
        ComplexityBucket.COMPLEX,
        ComplexityBucket.STANDARD,
        ComplexityBucket.MICRO,
        ComplexityBucket.NANO,
    ]:
        keywords = COMPLEXITY_KEYWORDS[bucket]
        matched = [kw for kw in keywords if kw in description_lower]
        score = len(matched)

        if score > best_score:
            best_score = score
            best_bucket = bucket
            best_keywords = matched

    if has_realtime and best_bucket.value not in ("complex", "critical"):
        best_bucket = ComplexityBucket.COMPLEX
        best_keywords.append("real-time (flag)")

    if has_auth and best_bucket.value in ("nano", "micro"):
        best_bucket = ComplexityBucket.STANDARD
        best_keywords.append("auth (flag)")

    entity_count = len(entities)
    if entity_count > 5 and best_bucket == ComplexityBucket.NANO:
        best_bucket = ComplexityBucket.MICRO
        best_keywords.append(f"entity_count={entity_count}")

    total_keywords = sum(len(v) for v in COMPLEXITY_KEYWORDS.values())
    confidence = min(1.0, (best_score + 1) / (total_keywords * 0.1)) if best_score > 0 else 0.3

    return ClassificationResult(
        bucket=best_bucket,
        timeout_hours=BUCKET_TIMEOUTS_HOURS[best_bucket],
        matched_keywords=best_keywords,
        confidence=confidence,
    )


def get_timeout_hours(bucket: ComplexityBucket) -> int:
    """Get the activity timeout in hours for a given complexity bucket."""
    return BUCKET_TIMEOUTS_HOURS[bucket]


def get_timeout_seconds(bucket: ComplexityBucket) -> int:
    """Get the activity timeout in seconds for a given complexity bucket."""
    return BUCKET_TIMEOUTS_HOURS[bucket] * 3600
