"""
ingestion_service.py — Orchestrates the full Phase 1 + Phase 2 ingestion pipeline.

Phase 2 addition:
  After every successful submission save, the service calls
  ClusteringService.assign_submission() and appends the cluster_id +
  similarity_score to the final SSE chunk so the frontend knows immediately
  which cluster this submission joined (or created).

Pipeline per submission type:

  TEXT:
    guardrail → translate → extract issues → save → cluster → done

  AUDIO:
    validate → transcribe → guardrail → translate → extract → save → cluster → done

  IMAGE:
    validate → analyse image → guardrail → translate → extract → save → cluster → done
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
from app.services.clustering_service import ClusteringService
from app.utils.confidence import (
    compute_overall_confidence,
    guardrail_check,
    make_annotation,
    score_to_level,
)
from app.utils.config import get_settings

logger = logging.getLogger(__name__)
cfg = get_settings()


def _chunk(
    step: str, status: str, message: str, progress: int, data: object = None
) -> StreamChunk:
    return StreamChunk(
        step=step, status=status,
        message=message, data=data, progress=progress,
    )


class IngestionService:
    def __init__(
        self,
        gemini:     GeminiService,
        firebase:   FirebaseService,
        clustering: ClusteringService,
    ) -> None:
        self._gemini     = gemini
        self._firebase   = firebase
        self._clustering = clustering

    # ── Shared: cluster step ─────────────────────────────────────────────────

    async def _run_clustering(
        self,
        submission_id: str,
        english_text:  str,
        issues:        list[ExtractedIssue],
        constituency:  str,
        all_flags:     list[ProcessingFlag],
    ) -> dict:
        """
        Run clustering and return a dict with cluster_id + similarity_score.
        Failures are swallowed (silent fallback) — clustering should never
        break the main submission response.
        """
        try:
            assignment, c_flags = await self._clustering.assign_submission(
                submission_id=submission_id,
                english_text=english_text,
                issues=issues,
                constituency=constituency,
            )
            all_flags.extend(c_flags)
            return {
                "cluster_id":        assignment.cluster_id,
                "similarity_score":  assignment.similarity_score,
                "is_new_cluster":    assignment.is_new_cluster,
                "cluster_size":      assignment.cluster_size,
            }
        except Exception as e:
            logger.error(f"Clustering failed for {submission_id}: {e}. Skipping.")
            all_flags.append(ProcessingFlag.SILENT_FALLBACK)
            return {"cluster_id": None, "error": "clustering_unavailable"}

    # ── TEXT pipeline ─────────────────────────────────────────────────────────

    async def ingest_text_stream(
        self,
        text:           str,
        constituency:   str,
        submitter_name: str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        start_ms  = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        sid       = str(uuid.uuid4())

        # Step 0 — Guardrail
        yield _chunk("guardrail", "in_progress", "Checking content safety...", 5)
        triggered, reason = guardrail_check(text)
        if triggered:
            all_flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            yield _chunk("guardrail", "error",
                         "Submission blocked: content does not meet guidelines.",
                         100, {"guardrail_reason": reason,
                               "flags": [f.value for f in all_flags]})
            return
        yield _chunk("guardrail", "complete", "Content check passed.", 10)

        # Step 1 — Translate
        yield _chunk("translating", "in_progress", "Detecting language...", 15)
        translation, t_flags = await self._gemini.translate_and_detect(text)
        all_flags.extend(t_flags)
        english_text = translation.translated_text or text
        yield _chunk("translating", "complete",
                     f"Language: {translation.detected_language_name}"
                     + (" → English" if translation.translated_text else ""),
                     35, {"language": translation.detected_language_name})

        # Step 2 — Extract issues
        yield _chunk("extracting", "in_progress", "Extracting and classifying issues...", 40)
        issues, _, e_flags = await self._gemini.extract_issues(
            english_text, translation.detected_language, constituency
        )
        all_flags.extend(e_flags)
        issue_scores   = [i.category.score for i in issues]
        final_conf     = compute_overall_confidence(issue_scores) if issue_scores else 0.0
        conf_level     = score_to_level(final_conf)
        yield _chunk("extracting", "complete",
                     f"{len(issues)} issue(s) — confidence {conf_level.value} ({final_conf:.0%})",
                     60, {"issue_count": len(issues), "confidence": final_conf})

        # Step 3 — Save
        yield _chunk("storing", "in_progress", "Saving submission...", 65)
        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) or [ProcessingFlag.OK],
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
            fallback_reason="Rule-based fallback used" if ProcessingFlag.SILENT_FALLBACK in all_flags else None,
        )
        response = SubmissionResponse(
            submission_id=sid,
            submission_type=SubmissionType.TEXT,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_conf,
            overall_confidence_level=conf_level,
            metadata=metadata,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._firebase.save_submission(response)
        yield _chunk("storing", "complete", "Saved.", 70)

        # Step 4 — Cluster (Phase 2)
        yield _chunk("clustering", "in_progress", "Finding similar complaints...", 75)
        cluster_info = await self._run_clustering(
            sid, english_text, issues, constituency, all_flags
        )
        msg = (
            f"New cluster created"
            if cluster_info.get("is_new_cluster")
            else f"Joined cluster with {cluster_info.get('cluster_size', '?')} reports "
                 f"(similarity {cluster_info.get('similarity_score', 0):.0%})"
        )
        yield _chunk("clustering", "complete", msg, 90, cluster_info)

        # Final — done
        final_data = response.model_dump(mode="json")
        final_data["cluster_info"] = cluster_info
        yield _chunk("done", "complete", "Submission processed.", 100, final_data)

    # ── AUDIO pipeline ────────────────────────────────────────────────────────

    async def ingest_audio_stream(
        self,
        audio_bytes:    bytes,
        mime_type:      str,
        constituency:   str,
        submitter_name: str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        start_ms  = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        sid       = str(uuid.uuid4())

        if len(audio_bytes) > cfg.max_audio_size_mb * 1024 * 1024:
            yield _chunk("validation", "error",
                         f"Audio too large (max {cfg.max_audio_size_mb} MB).", 100)
            return

        yield _chunk("transcribing", "in_progress", "Transcribing audio...", 10)
        transcript, lang_code, lang_name, t_conf, t_flags = (
            await self._gemini.transcribe_audio(audio_bytes, mime_type)
        )
        all_flags.extend(t_flags)
        if not transcript or transcript.startswith("[Transcription unavailable"):
            yield _chunk("transcribing", "error",
                         "Could not transcribe. Please re-submit as text.", 100)
            return
        yield _chunk("transcribing", "complete",
                     f"Transcribed ({lang_name}, {t_conf:.0%} confidence)",
                     30, {"transcript_preview": transcript[:100]})

        triggered, _ = guardrail_check(transcript)
        if triggered:
            all_flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            yield _chunk("guardrail", "error", "Content blocked.", 100)
            return

        yield _chunk("translating", "in_progress", "Translating...", 35)
        translation, tr_flags = await self._gemini.translate_and_detect(transcript)
        all_flags.extend(tr_flags)
        english_text = translation.translated_text or transcript
        yield _chunk("translating", "complete", "Done.", 50)

        yield _chunk("extracting", "in_progress", "Extracting issues...", 55)
        issues, _, e_flags = await self._gemini.extract_issues(
            english_text, lang_code, constituency
        )
        all_flags.extend(e_flags)
        issue_scores = [i.category.score for i in issues]
        final_conf   = compute_overall_confidence(issue_scores) if issue_scores else 0.0
        conf_level   = score_to_level(final_conf)
        yield _chunk("extracting", "complete",
                     f"{len(issues)} issue(s)", 65)

        yield _chunk("storing", "in_progress", "Saving...", 70)
        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) or [ProcessingFlag.OK],
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
        )
        response = SubmissionResponse(
            submission_id=sid,
            submission_type=SubmissionType.AUDIO,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_conf,
            overall_confidence_level=conf_level,
            metadata=metadata,
            transcript=transcript,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._firebase.save_submission(response)
        yield _chunk("storing", "complete", "Saved.", 75)

        yield _chunk("clustering", "in_progress", "Finding similar complaints...", 80)
        cluster_info = await self._run_clustering(
            sid, english_text, issues, constituency, all_flags
        )
        yield _chunk("clustering", "complete",
                     f"{'New cluster' if cluster_info.get('is_new_cluster') else 'Joined cluster'}", 90, cluster_info)

        final_data = response.model_dump(mode="json")
        final_data["cluster_info"] = cluster_info
        yield _chunk("done", "complete", "Done.", 100, final_data)

    # ── IMAGE pipeline ────────────────────────────────────────────────────────

    async def ingest_image_stream(
        self,
        image_bytes:    bytes,
        mime_type:      str,
        constituency:   str,
        submitter_name: str | None,
        caption:        str | None,
    ) -> AsyncGenerator[StreamChunk, None]:
        start_ms  = int(time.time() * 1000)
        all_flags: list[ProcessingFlag] = []
        sid       = str(uuid.uuid4())

        if len(image_bytes) > cfg.max_image_size_mb * 1024 * 1024:
            yield _chunk("validation", "error",
                         f"Image too large (max {cfg.max_image_size_mb} MB).", 100)
            return

        yield _chunk("analysing_image", "in_progress", "Analysing image...", 10)
        desc, img_cat, img_conf, loc_clues, severity, img_flags = (
            await self._gemini.analyse_image(image_bytes, mime_type)
        )
        all_flags.extend(img_flags)
        full_text = f"{caption}. {desc}" if caption else desc
        yield _chunk("analysing_image", "complete",
                     f"Image: {img_cat.value} ({img_conf:.0%})", 30,
                     {"description_preview": desc[:100]})

        triggered, _ = guardrail_check(full_text)
        if triggered:
            yield _chunk("guardrail", "error", "Content blocked.", 100)
            return

        yield _chunk("translating", "in_progress", "Processing...", 35)
        translation, tr_flags = await self._gemini.translate_and_detect(full_text)
        all_flags.extend(tr_flags)
        english_text = translation.translated_text or full_text
        yield _chunk("translating", "complete", "Done.", 50)

        yield _chunk("extracting", "in_progress", "Classifying...", 55)
        issues, _, e_flags = await self._gemini.extract_issues(
            english_text, translation.detected_language, constituency
        )
        all_flags.extend(e_flags)
        if not issues:
            issues = [ExtractedIssue(
                description=desc,
                category=make_annotation(img_cat.value, img_conf),
                location_hint=loc_clues,
                severity_hint=severity,
            )]
        issue_scores = [i.category.score for i in issues]
        final_conf   = compute_overall_confidence(issue_scores) if issue_scores else img_conf
        conf_level   = score_to_level(final_conf)
        yield _chunk("extracting", "complete", f"{len(issues)} issue(s)", 65)

        yield _chunk("storing", "in_progress", "Saving...", 70)
        metadata = ProcessingMetadata(
            model_used=cfg.gemini_model,
            processing_ms=int(time.time() * 1000) - start_ms,
            flags=list(set(all_flags)) or [ProcessingFlag.OK],
            fallback_used=ProcessingFlag.SILENT_FALLBACK in all_flags,
        )
        response = SubmissionResponse(
            submission_id=sid,
            submission_type=SubmissionType.IMAGE,
            constituency=constituency,
            submitter_name=submitter_name,
            translation=translation,
            issues=issues,
            overall_confidence=final_conf,
            overall_confidence_level=conf_level,
            metadata=metadata,
            image_description=desc,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._firebase.save_submission(response)
        yield _chunk("storing", "complete", "Saved.", 75)

        yield _chunk("clustering", "in_progress", "Finding similar complaints...", 80)
        cluster_info = await self._run_clustering(
            sid, english_text, issues, constituency, all_flags
        )
        yield _chunk("clustering", "complete",
                     f"{'New cluster' if cluster_info.get('is_new_cluster') else 'Joined cluster'}", 90, cluster_info)

        final_data = response.model_dump(mode="json")
        final_data["cluster_info"] = cluster_info
        yield _chunk("done", "complete", "Done.", 100, final_data)