"""
confidence.py — Pure functions for confidence scoring and guardrails.

Why a separate module?
  The confidence logic must be deterministic and testable without Gemini.
  Keeping it here means we can unit-test it in isolation and swap thresholds
  via config without touching any AI code.
"""

from __future__ import annotations

from app.models.schemas import ConfidenceAnnotation, ConfidenceLevel, ProcessingFlag
from app.utils.config import get_settings


def score_to_level(score: float) -> ConfidenceLevel:
    """Map a 0.0–1.0 float to a human-readable confidence band."""
    cfg = get_settings()
    if score >= cfg.confidence_threshold_high:
        return ConfidenceLevel.HIGH
    if score >= cfg.confidence_threshold_low:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def make_annotation(value: object, score: float) -> ConfidenceAnnotation:
    """Wrap any AI output value in a ConfidenceAnnotation."""
    return ConfidenceAnnotation(
        value=value,
        score=round(score, 3),
        level=score_to_level(score),
        override=None,
        is_ai_generated=True,
    )


def flags_from_score(score: float) -> list[ProcessingFlag]:
    """Return any processing flags implied by a confidence score alone."""
    if score < get_settings().confidence_threshold_low:
        return [ProcessingFlag.LOW_CONFIDENCE]
    return []


# ── Guardrail checks ──────────────────────────────────────────────────────────

# Categories of content that should be blocked (off-topic for an MP grievance
# platform) or flagged for human review.
_GUARDRAIL_KEYWORDS: list[str] = [
    "bomb", "kill", "weapon", "attack", "drug", "murder",
    "terrorist", "violence", "sexual", "porn",
]

_POLITICAL_ABUSE_KEYWORDS: list[str] = [
    # Highly abusive phrases targeting individuals — flag but don't block
    "rape him", "kill the mp", "death to",
]


def guardrail_check(text: str) -> tuple[bool, str | None]:
    """
    Returns (triggered: bool, reason: str | None).
    Hard-block if any _GUARDRAIL_KEYWORDS present.
    This is intentionally simple for a prototype — in production you'd
    use Gemini's safety settings + a dedicated moderation call.
    """
    lowered = text.lower()
    for kw in _GUARDRAIL_KEYWORDS:
        if kw in lowered:
            return True, f"Content flagged: '{kw}' detected. Submission blocked."
    return False, None


def compute_overall_confidence(issue_scores: list[float]) -> float:
    """
    Aggregate confidence across all extracted issues.
    Uses a weighted harmonic mean — punishes outlier low-confidence issues
    more than a simple average would.
    """
    if not issue_scores:
        return 0.0
    # Harmonic mean
    n = len(issue_scores)
    harmonic = n / sum(1.0 / max(s, 0.01) for s in issue_scores)
    return round(harmonic, 3)
