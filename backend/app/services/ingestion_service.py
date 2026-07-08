"""
ingestion_service.py — Orchestrates the full Phase 1 ingestion pipeline.

Pipeline steps (per submission type):

  TEXT:
    1. Guardrail pre-check
    2. Language detection + translation (Gemini)
    3. Issue extraction + classification (Gemini)
    4. Confidence scoring + flag assembly
    5. Persist to Firestore

  AUDIO:
    1. Validate size + mime type
    2. Transcription (Gemini multimodal)
    3. Language detection + translation (Gemini, on transcript)
    4. Issue extraction (same as TEXT from here)
    5. Persist

  IMAGE:
    1. Validate size + mime type
    2. Image analysis → description + initial category (Gemini multimodal)
    3. Run description through translation + extraction pipeline
    4. Persist

Each step emits an SSE chunk via the async generator so the frontend
can show real-time progress.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from app.models.schemas import (
    ConfidenceLevel,
    ExtractedIssue,
    IssueCategory,
    ProcessingFlag,
    ProcessingMetadata,
    StreamChunk,
    SubmissionResponse,
    SubmissionType,
    TranslationResult,
)
from app.services.firebase_service import FirebaseService
from app.services.gemini_service import GeminiService
from app.utils.confidence import (
    compute_overall_confidence,
    guardrail_check,
    make_annotation,
    score_to_level,
)
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

cfg = get_settings()


def _make_chunk(
    step: str,
    status: str,
    message: str,
    progress: int,
    data: object = None,
) -> StreamChunk:
    return StreamChunk(
        step=step,
        status=status,
        message=message,
        data=data,
        progress=progress,
    )


class IngestionService:
    """
    Top-level orchestrator. Instantiated once per request (not a singleton).
    Holds references to shared GeminiService and FirebaseService.
    """

    def __init__(
        self,
        gemini: GeminiService,
        firebase: FirebaseService,
    ) -> None:
        self._gemini = gemini
        self._firebase = firebase

    # ── Public entry points ───────────────────────────────────────────────────

    async def ingest_text_stream(
        self,
        text: str,
        constituency: str,
        submitter_name: str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Full text ingestion pipeline with SSE streaming.
        Yields StreamChunks at each step.
        """
        start_ms = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        submission_id = str(uuid.uuid4())

        # Step 0 — Guardrail pre-check (instant, no AI needed)
        yield _make_chunk("guardrail", "in_progress", "Checking content safety...", 5)
        triggered, reason = guardrail_check(text)
        if triggered:
            all_flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            yield _make_chunk(
                "guardrail", "error",
                "Submission blocked: content does not meet community guidelines.",
                100,
                data={"guardrail_reason": reason, "flags": [f.value for f in all_flags]},
            )
            return

        yield _make_chunk("guardrail", "complete", "Content check passed.", 10)

        # Step 1 — Language detection + translation
        yield _make_chunk("translating", "in_progress", "Detecting language and translating...", 15)
        translation, t_flags = await self._gemini.translate_and_detect(text)
        all_flags.extend(t_flags)
        english_text = translation.translated_text or text
        yield _make_chunk(
            "translating", "complete",
            f"Language: {translation.detected_language_name} "
            + ("→ translated to English" if translation.translated_text else "(already English)"),
            35,
            data={"language": translation.detected_language_name},
        )

        # Step 2 — Issue extraction
        yield _make_chunk("extracting", "in_progress", "Extracting issues and classifying...", 40)
        issues, overall_conf, e_flags = await self._gemini.extract_issues(
            english_text, translation.detected_language, constituency
        )
        all_flags.extend(e_flags)

        if not issues:
            # No issues found — could be guardrail or empty submission
            if ProcessingFlag.CONTENT_GUARDRAIL_HIT not in all_flags:
                all_flags.append(ProcessingFlag.LOW_CONFIDENCE)

        issue_scores = [
            i.category.score for i in issues
        ]
        final_confidence = (
            compute_overall_confidence(issue_scores)
            if issue_scores else 0.0
        )
        confidence_level = score_to_level(final_confidence)

        yield _make_chunk(
            "extracting", "complete",
            f"Found {len(issues)} issue(s). Confidence: {confidence_level.value} ({final_confidence:.0%})",
            65,
            data={"issue_count": len(issues), "confidence": final_confidence},
        )

        # Step 3 — Assemble deterministic response
        yield _make_chunk("assembling", "in_progress", "Building structured response...", 70)

        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) if all_flags else [ProcessingFlag.OK],
            guardrail_triggered=False,
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
            fallback_reason="Gemini unavailable; rule-based classification used"
            if ProcessingFlag.SILENT_FALLBACK in all_flags
            else None,
        )

        response = SubmissionResponse(
            submission_id=submission_id,
            submission_type=SubmissionType.TEXT,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_confidence,
            overall_confidence_level=confidence_level,
            metadata=metadata,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Step 4 — Persist
        yield _make_chunk("storing", "in_progress", "Saving to database...", 80)
        await self._firebase.save_submission(response)
        yield _make_chunk("storing", "complete", "Saved.", 90)

        # Final chunk — full response payload
        yield _make_chunk(
            "done", "complete",
            "Submission processed successfully.",
            100,
            data=response.model_dump(mode="json"),
        )

    async def ingest_audio_stream(
        self,
        audio_bytes: bytes,
        mime_type: str,
        constituency: str,
        submitter_name: str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Audio ingestion pipeline with SSE streaming."""
        start_ms = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        submission_id = str(uuid.uuid4())

        # Validate size
        max_bytes = cfg.max_audio_size_mb * 1024 * 1024
        if len(audio_bytes) > max_bytes:
            yield _make_chunk(
                "validation", "error",
                f"Audio file too large. Max {cfg.max_audio_size_mb} MB.",
                100,
            )
            return

        # Step 1 — Transcribe
        yield _make_chunk("transcribing", "in_progress", "Transcribing audio...", 10)
        transcript, lang_code, lang_name, transcript_conf, t_flags = (
            await self._gemini.transcribe_audio(audio_bytes, mime_type)
        )
        all_flags.extend(t_flags)

        if not transcript or transcript.startswith("[Transcription unavailable"):
            yield _make_chunk(
                "transcribing", "error",
                "Could not transcribe audio. Please re-submit as text.",
                100,
                data={"flags": [ProcessingFlag.SILENT_FALLBACK.value]},
            )
            return

        yield _make_chunk(
            "transcribing", "complete",
            f"Transcribed ({lang_name}, confidence {transcript_conf:.0%})",
            30,
            data={"transcript_preview": transcript[:100]},
        )

        # Step 2 — Guardrail on transcript
        triggered, reason = guardrail_check(transcript)
        if triggered:
            all_flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            yield _make_chunk("guardrail", "error", "Content blocked.", 100)
            return

        # Step 3 — Build a synthetic TranslationResult from transcription output
        yield _make_chunk("translating", "in_progress", "Translating transcript...", 35)
        translation, tr_flags = await self._gemini.translate_and_detect(transcript)
        all_flags.extend(tr_flags)
        english_text = translation.translated_text or transcript
        yield _make_chunk("translating", "complete", "Translation done.", 50)

        # Step 4 — Extract issues
        yield _make_chunk("extracting", "in_progress", "Extracting issues...", 55)
        issues, overall_conf, e_flags = await self._gemini.extract_issues(
            english_text, lang_code, constituency
        )
        all_flags.extend(e_flags)

        issue_scores = [i.category.score for i in issues]
        final_confidence = compute_overall_confidence(issue_scores) if issue_scores else 0.0
        confidence_level = score_to_level(final_confidence)

        yield _make_chunk(
            "extracting", "complete",
            f"{len(issues)} issue(s), confidence {confidence_level.value}",
            70,
        )

        # Assemble + store
        yield _make_chunk("storing", "in_progress", "Saving...", 80)
        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) if all_flags else [ProcessingFlag.OK],
            guardrail_triggered=False,
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
        )
        response = SubmissionResponse(
            submission_id=submission_id,
            submission_type=SubmissionType.AUDIO,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_confidence,
            overall_confidence_level=confidence_level,
            metadata=metadata,
            transcript=transcript,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._firebase.save_submission(response)
        yield _make_chunk("done", "complete", "Done.", 100, data=response.model_dump(mode="json"))

    async def ingest_image_stream(
        self,
        image_bytes: bytes,
        mime_type: str,
        constituency: str,
        submitter_name: str | None,
        caption: str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Image ingestion pipeline with SSE streaming."""
        start_ms = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        submission_id = str(uuid.uuid4())

        # Validate size
        max_bytes = cfg.max_image_size_mb * 1024 * 1024
        if len(image_bytes) > max_bytes:
            yield _make_chunk(
                "validation", "error",
                f"Image too large. Max {cfg.max_image_size_mb} MB.",
                100,
            )
            return

        # Step 1 — Analyse image
        yield _make_chunk("analysing_image", "in_progress", "Analysing image...", 10)
        description, img_category, img_conf, loc_clues, severity, img_flags = (
            await self._gemini.analyse_image(image_bytes, mime_type)
        )
        all_flags.extend(img_flags)

        full_text = description
        if caption:
            full_text = f"{caption}. {description}"

        yield _make_chunk(
            "analysing_image", "complete",
            f"Image analysed: {img_category.value} (confidence {img_conf:.0%})",
            35,
            data={"description_preview": description[:100]},
        )

        # Step 2 — Guardrail
        triggered, reason = guardrail_check(full_text)
        if triggered:
            yield _make_chunk("guardrail", "error", "Content blocked.", 100)
            return

        # Step 3 — Translation
        yield _make_chunk("translating", "in_progress", "Processing description...", 40)
        translation, tr_flags = await self._gemini.translate_and_detect(full_text)
        all_flags.extend(tr_flags)
        english_text = translation.translated_text or full_text
        yield _make_chunk("translating", "complete", "Done.", 55)

        # Step 4 — Extract issues (seed with image category as hint)
        yield _make_chunk("extracting", "in_progress", "Classifying issues...", 60)
        issues, overall_conf, e_flags = await self._gemini.extract_issues(
            english_text, translation.detected_language, constituency
        )
        all_flags.extend(e_flags)

        # If Gemini extraction failed, fall back to image-level category
        if not issues:
            issues = [
                ExtractedIssue(
                    description=description,
                    category=make_annotation(img_category.value, img_conf),
                    location_hint=loc_clues,
                    severity_hint=severity,
                )
            ]

        issue_scores = [i.category.score for i in issues]
        final_confidence = compute_overall_confidence(issue_scores) if issue_scores else img_conf
        confidence_level = score_to_level(final_confidence)

        yield _make_chunk("extracting", "complete", f"{len(issues)} issue(s).", 75)

        # Assemble + store
        yield _make_chunk("storing", "in_progress", "Saving...", 85)
        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) if all_flags else [ProcessingFlag.OK],
            guardrail_triggered=False,
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
        )
        response = SubmissionResponse(
            submission_id=submission_id,
            submission_type=SubmissionType.IMAGE,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_confidence,
            overall_confidence_level=confidence_level,
            metadata=metadata,
            image_description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._firebase.save_submission(response)
        yield _make_chunk("done", "complete", "Done.", 100, data=response.model_dump(mode="json"))
