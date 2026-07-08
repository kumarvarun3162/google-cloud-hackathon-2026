"""
test_confidence.py — Unit tests for the deterministic confidence and
guardrail logic. These run without any API keys or network access.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.models.schemas import ConfidenceLevel
from app.utils.confidence import (
    compute_overall_confidence,
    guardrail_check,
    make_annotation,
    score_to_level,
)


class TestScoreToLevel:
    def test_high(self):
        assert score_to_level(0.85) == ConfidenceLevel.HIGH

    def test_high_boundary(self):
        assert score_to_level(0.80) == ConfidenceLevel.HIGH

    def test_medium(self):
        assert score_to_level(0.65) == ConfidenceLevel.MEDIUM

    def test_medium_boundary(self):
        assert score_to_level(0.50) == ConfidenceLevel.MEDIUM

    def test_low(self):
        assert score_to_level(0.30) == ConfidenceLevel.LOW

    def test_low_boundary(self):
        assert score_to_level(0.49) == ConfidenceLevel.LOW

    def test_zero(self):
        assert score_to_level(0.0) == ConfidenceLevel.LOW

    def test_one(self):
        assert score_to_level(1.0) == ConfidenceLevel.HIGH


class TestMakeAnnotation:
    def test_wraps_value(self):
        ann = make_annotation("road", 0.9)
        assert ann.value == "road"
        assert ann.score == 0.9
        assert ann.level == ConfidenceLevel.HIGH
        assert ann.override is None
        assert ann.is_ai_generated is True

    def test_effective_value_no_override(self):
        ann = make_annotation("school", 0.7)
        assert ann.effective_value == "school"

    def test_effective_value_with_override(self):
        ann = make_annotation("school", 0.7)
        ann.override = "road"
        assert ann.effective_value == "road"

    def test_score_rounded(self):
        ann = make_annotation("water", 0.12345678)
        assert ann.score == 0.123


class TestGuardrailCheck:
    def test_clean_text_passes(self):
        triggered, reason = guardrail_check("The road near our village has potholes")
        assert triggered is False
        assert reason is None

    def test_clean_hindi_style_passes(self):
        triggered, _ = guardrail_check("School mein teachers nahi hain")
        assert triggered is False

    def test_blocks_violence_keyword(self):
        triggered, reason = guardrail_check("I want to bomb the road")
        assert triggered is True
        assert reason is not None

    def test_case_insensitive(self):
        triggered, _ = guardrail_check("BOMB the building")
        assert triggered is True

    def test_drug_keyword(self):
        triggered, _ = guardrail_check("drug supply in market")
        assert triggered is True

    def test_legitimate_medical_mention(self):
        # "medicine" is not in _GUARDRAIL_KEYWORDS — only "drug"
        triggered, _ = guardrail_check("No medicine at health centre")
        assert triggered is False


class TestOverallConfidence:
    def test_single_score(self):
        result = compute_overall_confidence([0.8])
        assert result == 0.8

    def test_all_high(self):
        result = compute_overall_confidence([0.9, 0.85, 0.92])
        assert result > 0.8

    def test_mixed_punishes_low(self):
        # Harmonic mean punishes low outliers more than arithmetic mean
        result = compute_overall_confidence([0.9, 0.1])
        arithmetic_mean = (0.9 + 0.1) / 2   # 0.5
        assert result < arithmetic_mean      # harmonic mean is lower

    def test_empty_returns_zero(self):
        assert compute_overall_confidence([]) == 0.0

    def test_all_zero_handled(self):
        # Should not divide by zero
        result = compute_overall_confidence([0.0, 0.0])
        assert result == 0.0 or result >= 0.0   # just must not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
