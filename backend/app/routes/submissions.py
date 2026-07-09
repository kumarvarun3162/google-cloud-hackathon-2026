"""
submissions.py — FastAPI routes for citizen submission ingestion (Phase 1 + 2).

Phase 2 addition:
  After every successful ingestion, the submission is automatically passed to
  ClusteringService.assign_submission(). This happens inside the streaming
  pipeline so the frontend gets a cluster_id in the final SSE chunk.

Endpoints:
  POST /api/v1/submissions/text          — text submission (streaming SSE)
  POST /api/v1/submissions/audio         — audio file (streaming SSE)
  POST /api/v1/submissions/image         — image/photo (streaming SSE)
  GET  /api/v1/submissions/{id}          — fetch one submission
  GET  /api/v1/submissions               — list submissions
  PATCH /api/v1/submissions/{id}/override — human label correction
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    OverrideRequest,
    StreamChunk,
    TextSubmissionRequest,
)
from app.services.clustering_service import ClusteringService
from app.services.firebase_service import FirebaseService
from app.services.gemini_service import GeminiService
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

# ── Singletons ────────────────────────────────────────────────────────────────

_gemini:     GeminiService     | None = None
_firebase:   FirebaseService   | None = None
_clustering: ClusteringService | None = None


def init_services(
    gemini:     GeminiService,
    firebase:   FirebaseService,
    clustering: ClusteringService,
) -> None:
    global _gemini, _firebase, _clustering
    _gemini     = gemini
    _firebase   = firebase
    _clustering = clustering


def get_ingestion_service() -> IngestionService:
    if _gemini is None or _firebase is None or _clustering is None:
        raise RuntimeError("Services not initialised.")
    return IngestionService(_gemini, _firebase, _clustering)


def get_firebase() -> FirebaseService:
    if _firebase is None:
        raise RuntimeError("FirebaseService not initialised.")
    return _firebase


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(chunk: StreamChunk) -> str:
    return f"data: {json.dumps(chunk.model_dump(mode='json'))}\n\n"


async def _stream(gen):
    try:
        async for chunk in gen:
            yield _sse(chunk)
    except Exception as e:
        err = StreamChunk(
            step="error", status="error",
            message=f"Pipeline error: {e}",
            data=None, progress=100,
        )
        yield _sse(err)
    finally:
        yield "data: [DONE]\n\n"


_SSE_HEADERS = {
    "Cache-Control":    "no-cache",
    "X-Accel-Buffering": "no",
    "Connection":       "keep-alive",
}

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/text")
async def submit_text(
    request: TextSubmissionRequest,
    svc: IngestionService = Depends(get_ingestion_service),
) -> StreamingResponse:
    """
    Text submission → translate → extract issues → cluster → save.
    Returns SSE stream. Final chunk (step=done) includes cluster_id.
    """
    logger.info(f"Text submission: constituency={request.constituency}")
    return StreamingResponse(
        _stream(svc.ingest_text_stream(
            text=request.text,
            constituency=request.constituency,
            submitter_name=request.submitter_name,
        )),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/audio")
async def submit_audio(
    constituency:   str            = Form(...),
    submitter_name: str | None     = Form(None),
    file:           UploadFile     = File(...),
    svc:            IngestionService = Depends(get_ingestion_service),
) -> StreamingResponse:
    """Audio file → transcribe → translate → extract → cluster → save."""
    allowed = {
        "audio/wav", "audio/mp3", "audio/mpeg",
        "audio/ogg", "audio/flac", "audio/aac", "audio/x-m4a",
    }
    if file.content_type not in allowed:
        raise HTTPException(415, f"Unsupported audio type: {file.content_type}")

    audio_bytes = await file.read()
    return StreamingResponse(
        _stream(svc.ingest_audio_stream(
            audio_bytes=audio_bytes,
            mime_type=file.content_type,
            constituency=constituency,
            submitter_name=submitter_name,
        )),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/image")
async def submit_image(
    constituency:   str            = Form(...),
    submitter_name: str | None     = Form(None),
    caption:        str | None     = Form(None),
    file:           UploadFile     = File(...),
    svc:            IngestionService = Depends(get_ingestion_service),
) -> StreamingResponse:
    """Image → analyse → translate → extract → cluster → save."""
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(415, f"Unsupported image type: {file.content_type}")

    image_bytes = await file.read()
    return StreamingResponse(
        _stream(svc.ingest_image_stream(
            image_bytes=image_bytes,
            mime_type=file.content_type,
            constituency=constituency,
            submitter_name=submitter_name,
            caption=caption,
        )),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    data = await db.get_submission(submission_id)
    if data is None:
        raise HTTPException(404, f"Submission {submission_id} not found.")
    return data


@router.get("")
async def list_submissions(
    constituency: str | None = None,
    limit:        int        = 50,
    db: FirebaseService = Depends(get_firebase),
) -> list[dict]:
    if limit > 200:
        raise HTTPException(400, "limit cannot exceed 200.")
    return await db.list_submissions(constituency=constituency, limit=limit)


@router.patch("/{submission_id}/override")
async def apply_override(
    submission_id: str,
    req: OverrideRequest,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """Human label correction — stored with audit trail."""
    if req.submission_id != submission_id:
        raise HTTPException(400, "submission_id in path and body must match.")
    try:
        return await db.apply_override(req)
    except ValueError as e:
        raise HTTPException(404, str(e))