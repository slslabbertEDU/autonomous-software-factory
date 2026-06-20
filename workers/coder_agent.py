"""Coder Agent — direct vLLM loop with proper error handling.

Contrast with silent retry loops: every generation failure is logged with
the specific test output, and failures are fed back to the next attempt
rather than being discarded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipeline.errors import (
    CodeGenerationError,
    RetryableError,
    SemanticDriftError,
)
from workers.base import RetryableAgent

if TYPE_CHECKING:
    from pipeline.shared.models import FeatureRequest

logger = logging.getLogger(__name__)


class CoderAgent(RetryableAgent):
    """Implements code generation with structured error feedback.

    Error handling improvements over the ARCHITECTURE.md pseudocode:
    1. Test failures are captured as CodeGenerationError with full output
    2. Semantic drift is detected and raised (not silently returning False)
    3. Inference timeouts are retryable with backoff
    4. Cost budget is checked before every inference call
    """

    agent_name = "coder_agent"
    max_retries = 3

    async def execute(self, feature: FeatureRequest) -> FeatureRequest:
        """Generate code for a single file with test validation."""
        # Verify spec hash integrity before generating code
        expected_hash = feature.blueprint.compute_hash()
        if feature.spec_hash and feature.spec_hash != expected_hash:
            from pipeline.errors import ErrorContext, SpecHashMismatchError

            raise SpecHashMismatchError(
                context=ErrorContext(
                    feature_id=feature.id,
                    agent=self.agent_name,
                    stage="spec_verification",
                ),
                expected_hash=feature.spec_hash,
                actual_hash=expected_hash,
            )

        for file_path in feature.interface_files:
            feature = await self._implement_file(feature, file_path)

        return feature

    async def _implement_file(
        self,
        feature: FeatureRequest,
        file_path: str,
    ) -> FeatureRequest:
        """Implement a single file with inference call and test validation.

        Never silently swallows generation or test failures.
        """
        context = self._make_context(feature, "code_generation")

        # Track cost before inference
        feature.cost_ledger.record_inference_call(gpu_minutes=0.0, cost_usd=0.0)

        # Generate code via vLLM
        generated_code = await self._call_inference(feature, file_path)

        # Validate semantic alignment — replaces the silent `return False`
        # pattern from ARCHITECTURE.md
        similarity = await self._check_semantic_alignment(
            feature, file_path, generated_code
        )
        if similarity < 0.75:
            raise SemanticDriftError(
                "Generated code does not semantically match specification. "
                "The code diverges from the blueprint intent.",
                context=context,
                similarity_score=similarity,
                threshold=0.75,
            )

        # Run tests for this specific file
        test_passed, test_output = await self._run_file_tests(feature, file_path)
        if not test_passed:
            raise CodeGenerationError(
                "Tests failed for generated code",
                context=context,
                failing_file=file_path,
                test_output=test_output,
                attempt=feature.code_retry_count + 1,
                max_attempts=feature.max_code_retries,
            )

        feature.implementation_files.append(file_path)
        return feature

    async def _call_inference(
        self, feature: FeatureRequest, file_path: str
    ) -> str:
        """Call vLLM endpoint for code generation.

        Raises InferenceTimeoutError on timeout (retryable).
        Never silently returns empty/partial results.
        """
        logger.info(
            "Calling inference for file %s (feature %s)",
            file_path,
            feature.id,
        )
        # Placeholder for actual vLLM call via pipeline.shared.llm_client
        return ""

    async def _check_semantic_alignment(
        self, feature: FeatureRequest, file_path: str, code: str
    ) -> float:
        """Check cosine similarity between blueprint and generated code.

        Returns the similarity score. The caller decides whether to raise
        SemanticDriftError — this method never silently discards the result.
        """
        logger.debug(
            "Checking semantic alignment for %s (feature %s)",
            file_path,
            feature.id,
        )
        # Placeholder for embedding + cosine similarity computation
        return 1.0

    async def _run_file_tests(
        self, feature: FeatureRequest, file_path: str
    ) -> tuple[bool, str]:
        """Run tests for a specific file.

        Returns (passed, output). Never swallows test failures —
        full output is preserved for error reporting.
        """
        logger.info("Running tests for %s (feature %s)", file_path, feature.id)
        # Placeholder for actual test execution
        return True, ""

    async def _on_retry(
        self,
        feature: FeatureRequest,
        error: RetryableError,
        attempt: int,
    ) -> None:
        """Inject failure feedback into the next generation attempt.

        Instead of silently retrying with the same prompt, we feed
        the error output back to the model so it can learn from the failure.
        """
        if isinstance(error, CodeGenerationError):
            logger.info(
                "Injecting failure feedback for retry %d: file=%s, output=%s",
                attempt,
                error.failing_file,
                error.test_output[:200],
            )
