"""
schemas.py — All request/response data contracts for Phase 1.

Design principles baked in here:
  - Every AI-produced field ships with a `confidence` float (0.0–1.0).
  - Every AI label ships with an `override` field so the MP/operator can
    correct it without touching the database directly.
  - `processing_flags` is a list of machine-readable strings the frontend
    can use to decide what UI to show (warn, block, ask_user, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class SubmissionType(str, Enum):
    TEXT  = "text"
    AUDIO = "audio"
    IMAGE = "image"


class IssueCategory(str, Enum):
    ROAD             = "road"
    WATER            = "water"
    SCHOOL           = "school"
    HEALTH           = "health"
    ELECTRICITY      = "electricity"
    SANITATION       = "sanitation"
    VOCATIONAL       = "vocational_training"
    AGRICULTURE      = "agriculture"
    HOUSING          = "housing"
    PUBLIC_TRANSPORT = "public_transport"
    OTHER            = "other"


class ConfidenceLevel(str, Enum):
    """Human-readable band derived from the float confidence score."""
    HIGH   = "high"    # >= 0.80
    MEDIUM = "medium"  # >= 0.50
    LOW    = "low"     # <  0.50


class ProcessingFlag(str, Enum):
    """
    Machine-readable flags the frontend uses to drive UX decisions.
    A response can carry multiple flags.
    """
    OK                    = "ok"
    LOW_CONFIDENCE        = "low_confidence"          # score < LOW threshold
    TRANSLATION_USED      = "translation_used"        # content was translated
    AUDIO_TRANSCRIBED     = "audio_transcribed"       # came in as audio
    IMAGE_ANALYSED        = "image_analysed"          # came in as image
    CONTENT_GUARDRAIL_HIT = "content_guardrail_hit"  # off-topic / harmful
    LOCATION_INFERRED     = "location_inferred"       # location not explicit
    OVERRIDE_APPLIED      = "override_applied"        # human corrected a label
    SILENT_FALLBACK       = "silent_fallback"         # Gemini failed, rule used


# ── Sub-models ────────────────────────────────────────────────────────────────

class ConfidenceAnnotation(BaseModel):
    """Wraps any AI-produced value with its confidence metadata."""
    value:            Any
    score:            float          = Field(..., ge=0.0, le=1.0, description="0.0–1.0 confidence from model")
    level:            ConfidenceLevel
    override:         Any | None     = Field(None, description="Human-corrected value; None = accept AI output")
    override_by:      str | None     = None
    is_ai_generated:  bool           = True

    @property
    def effective_value(self) -> Any:
        """Always use this in downstream logic — respects human override."""
        return self.override if self.override is not None else self.value


class ExtractedIssue(BaseModel):
    """One discrete problem found in the submission."""
    description:    str
    category:       ConfidenceAnnotation   # value = IssueCategory string
    location_hint:  str | None = None      # e.g. "near X road", "ward 7"
    severity_hint:  str | None = None      # e.g. "urgent", "long-standing"


class TranslationResult(BaseModel):
    original_text:    str
    detected_language: str           # BCP-47 code e.g. "hi", "te", "en"
    detected_language_name: str      # human name e.g. "Hindi"
    translated_text:  str | None     # None if source was already English
    translation_confidence: float    = Field(..., ge=0.0, le=1.0)


# ── Request models ─────────────────────────────────────────────────────────────

class TextSubmissionRequest(BaseModel):
    text:           str    = Field(..., min_length=5, max_length=5000)
    constituency:   str    = Field(..., min_length=2, max_length=100)
    submitter_name: str | None = None
    hint_language:  str | None = None   # optional BCP-47 if frontend knows it


class OverrideRequest(BaseModel):
    """
    MP / operator corrects an AI label after the fact.
    Sent to PATCH /submissions/{id}/override
    """
    submission_id:    str
    field_path:       str        # e.g. "issues[0].category"
    corrected_value:  Any
    override_by:      str        # operator ID or name
    reason:           str | None = None


# ── Response models ────────────────────────────────────────────────────────────

class ProcessingMetadata(BaseModel):
    model_used:         str
    processing_ms:      int
    flags:              list[ProcessingFlag]
    guardrail_triggered: bool = False
    guardrail_reason:   str | None = None
    fallback_used:      bool = False
    fallback_reason:    str | None = None


class SubmissionResponse(BaseModel):
    """
    The full deterministic response for one ingested submission.
    This is what gets stored in Firestore and returned to the frontend.
    """
    submission_id:    str
    submission_type:  SubmissionType
    constituency:     str
    submitter_name:   str | None

    # ── Raw + translated content ──
    translation:      TranslationResult

    # ── AI-extracted intelligence ──
    issues:           list[ExtractedIssue]
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    overall_confidence_level: ConfidenceLevel

    # ── Processing trace ──
    metadata:         ProcessingMetadata

    # ── Transcript (populated for audio submissions) ──
    transcript:       str | None = None

    # ── Image description (populated for image submissions) ──
    image_description: str | None = None

    created_at:       str   # ISO-8601


class StreamChunk(BaseModel):
    """
    One chunk sent over SSE during streaming ingestion.
    `step` tells the frontend which processing stage just completed.
    """
    step:      str           # "transcribing" | "translating" | "extracting" | "storing" | "done"
    status:    str           # "in_progress" | "complete" | "error"
    message:   str           # human-readable status for UI
    data:      Any | None    # partial or final payload
    progress:  int           # 0–100 percent


class ErrorResponse(BaseModel):
    error:    str
    detail:   str | None = None
    flags:    list[ProcessingFlag] = []
