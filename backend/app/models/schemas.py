"""
schemas.py — All request/response data contracts for Phase 1.

Design principles:
  - Every AI-produced field ships with a `confidence` float (0.0–1.0).
  - Every AI label ships with an `override` field so the MP/operator can
    correct it without re-running AI.
  - `processing_flags` gives the frontend machine-readable signals
    (warn, block, ask_user, show_override_ui, etc.).
"""

from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


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
    HIGH   = "high"    # >= 0.80
    MEDIUM = "medium"  # >= 0.50
    LOW    = "low"     # <  0.50


class ProcessingFlag(str, Enum):
    OK                    = "ok"
    LOW_CONFIDENCE        = "low_confidence"
    TRANSLATION_USED      = "translation_used"
    AUDIO_TRANSCRIBED     = "audio_transcribed"
    IMAGE_ANALYSED        = "image_analysed"
    CONTENT_GUARDRAIL_HIT = "content_guardrail_hit"
    LOCATION_INFERRED     = "location_inferred"
    OVERRIDE_APPLIED      = "override_applied"
    SILENT_FALLBACK       = "silent_fallback"


# ── Sub-models ────────────────────────────────────────────────────────────────

class ConfidenceAnnotation(BaseModel):
    """Wraps any AI-produced value with confidence metadata + override slot."""
    value:           Any
    score:           float           = Field(..., ge=0.0, le=1.0)
    level:           ConfidenceLevel
    override:        Any | None      = Field(None)
    override_by:     str | None      = None
    is_ai_generated: bool            = True

    @property
    def effective_value(self) -> Any:
        """Always use this downstream — respects human override."""
        return self.override if self.override is not None else self.value


class ExtractedIssue(BaseModel):
    description:   str
    category:      ConfidenceAnnotation
    location_hint: str | None = None
    severity_hint: str | None = None


class TranslationResult(BaseModel):
    original_text:           str
    detected_language:       str
    detected_language_name:  str
    translated_text:         str | None
    translation_confidence:  float = Field(..., ge=0.0, le=1.0)


# ── Request models ─────────────────────────────────────────────────────────────

class TextSubmissionRequest(BaseModel):
    text:           str    = Field(..., min_length=5, max_length=5000)
    constituency:   str    = Field(..., min_length=2, max_length=100)
    submitter_name: str | None = None


class OverrideRequest(BaseModel):
    submission_id:   str
    field_path:      str
    corrected_value: Any
    override_by:     str
    reason:          str | None = None


# ── Response models ────────────────────────────────────────────────────────────

class ProcessingMetadata(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_used:          str
    processing_ms:       int
    flags:               list[ProcessingFlag]
    guardrail_triggered: bool = False
    guardrail_reason:    str | None = None
    fallback_used:       bool = False
    fallback_reason:     str | None = None


class SubmissionResponse(BaseModel):
    submission_id:            str
    submission_type:          SubmissionType
    constituency:             str
    submitter_name:           str | None
    translation:              TranslationResult
    issues:                   list[ExtractedIssue]
    overall_confidence:       float = Field(..., ge=0.0, le=1.0)
    overall_confidence_level: ConfidenceLevel
    metadata:                 ProcessingMetadata
    transcript:               str | None = None
    image_description:        str | None = None
    created_at:               str


class StreamChunk(BaseModel):
    step:     str
    status:   str
    message:  str
    data:     Any | None
    progress: int


class ErrorResponse(BaseModel):
    error:  str
    detail: str | None = None
    flags:  list[ProcessingFlag] = []


# ── Phase 2: Clustering schemas ───────────────────────────────────────────────

class ClusterStatus(str, Enum):
    ACTIVE   = "active"    # has live submissions
    RESOLVED = "resolved"  # MP marked as handled
    MERGED   = "merged"    # merged into another cluster


class ClusterRecord(BaseModel):
    """
    One cluster = a group of similar citizen complaints about the same issue.
    Stored in Firestore `clusters/` collection.
    """
    cluster_id:          str
    constituency:        str
    category:            str                  # IssueCategory value
    title:               str                  # AI-generated 1-line title
    summary:             str                  # AI-generated summary of all complaints
    submission_ids:      list[str]            # all submissions in this cluster
    submission_count:    int
    centroid_embedding:  list[float]          # mean vector of all members
    representative_text: str                  # most central submission's text
    severity_distribution: dict[str, int]     # {"urgent": 3, "moderate": 5, ...}
    confidence:          float = Field(..., ge=0.0, le=1.0)
    confidence_level:    ConfidenceLevel
    status:              ClusterStatus = ClusterStatus.ACTIVE
    created_at:          str
    updated_at:          str


class ClusterAssignment(BaseModel):
    """Result of assigning one submission to a cluster."""
    submission_id:   str
    cluster_id:      str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    is_new_cluster:  bool
    cluster_size:    int


class ClusterSummaryResponse(BaseModel):
    """Lightweight cluster card for the dashboard list."""
    cluster_id:       str
    constituency:     str
    category:         str
    title:            str
    summary:          str
    submission_count: int
    severity_hint:    str | None
    confidence:       float
    confidence_level: ConfidenceLevel
    status:           ClusterStatus
    created_at:       str
    updated_at:       str


class EmbeddingResult(BaseModel):
    """Raw embedding output from Gemini Embedding API."""
    text:       str
    embedding:  list[float]
    dimensions: int