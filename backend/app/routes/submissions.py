"""
submissions.py — FastAPI routes for Phase 1 citizen submission ingestion.

Endpoints:
  POST /api/v1/submissions/text          — text submission (streaming SSE)
  POST /api/v1/submissions/audio         — audio file submission (streaming SSE)
  POST /api/v1/submissions/image         — image/photo submission (streaming SSE)
  GET  /api/v1/submissions/{id}          — fetch a stored submission
  GET  /api/v1/submissions               — list submissions (MP dashboard)
  PATCH /api/v1/submissions/{id}/override — human label correction

Streaming pattern:
  All ingest endpoints return text/event-stream (SSE).
  Each event is a JSON-encoded StreamChunk with step, status, message,
  progress (0–100), and optional data.

  The final event (step="done", progress=100) carries the full
  SubmissionResponse in `data`.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    OverrideRequest,
    StreamChunk,
    TextSubmissionRequest,
)
from app.services.firebase_service import FirebaseService
from app.services.gemini_service import GeminiService
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

# ── Dependency injection ──────────────────────────────────────────────────────
# These are singletons created once at startup and injected into routes.

_gemini: GeminiService | None = None
_firebase: FirebaseService | None = None


def init_services(gemini: GeminiService, firebase: FirebaseService) -> None:
    """Called from main.py at startup."""
    global _gemini, _firebase
    _gemini = gemini
    _firebase = firebase


def get_ingestion_service() -> IngestionService:
    if _gemini is None or _firebase is None:
        raise RuntimeError("Services not initialised — call init_services() first.")
    return IngestionService(_gemini, _firebase)


def get_firebase() -> FirebaseService:
    if _firebase is None:
        raise RuntimeError("FirebaseService not initialised.")
    return _firebase


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse_format(chunk: StreamChunk) -> str:
    """Format a StreamChunk as an SSE event string."""
    payload = json.dumps(chunk.model_dump(mode="json"))
    return f"data: {payload}\n\n"


async def _stream_generator(
    async_gen: AsyncGenerator[StreamChunk, None],
) -> AsyncGenerator[str, None]:
    """
    Wraps the ingestion generator and formats each chunk as SSE.
    Sends a final [DONE] sentinel so the client knows to close the connection.
    """
    try:
        async for chunk in async_gen:
            yield _sse_format(chunk)
    except Exception as e:
        error_chunk = StreamChunk(
            step="error",
            status="error",
            message=f"Pipeline error: {str(e)}",
            data=None,
            progress=100,
        )
        yield _sse_format(error_chunk)
    finally:
        yield "data: [DONE]\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/text")
async def submit_text(
    request: TextSubmissionRequest,
    svc: IngestionService = Depends(get_ingestion_service),
) -> StreamingResponse:
    """
    Accept a text submission and stream the processing pipeline back to client.

    Request body (JSON):
      { "text": "...", "constituency": "...", "submitter_name": "..." }

    Response: text/event-stream
      Each SSE event is a StreamChunk JSON object.
      Final event: step="done", data=<full SubmissionResponse>
    """
    logger.info(f"Text submission received, constituency={request.constituency}")

    async def generate():
        async for chunk in svc.ingest_text_stream(
            text=request.text,
            constituency=request.constituency,
            submitter_name=request.submitter_name,
        ):
            yield _sse_format(chunk)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables Nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.post("/audio")
async def submit_audio(
    constituency: str           = Form(...),
    submitter_name: str | None  = Form(None),
    file: UploadFile            = File(...),
    svc: IngestionService       = Depends(get_ingestion_service),
) -> StreamingResponse:
    """
    Accept an audio file and stream the transcription + classification pipeline.

    Supported formats: audio/wav, audio/mp3, audio/ogg, audio/flac, audio/aac
    Max size: controlled by MAX_AUDIO_SIZE_MB env var (default 10 MB)

    Form fields:
      constituency (str)
      submitter_name (str, optional)
      file (UploadFile)
    """
    allowed_types = {
        "audio/wav", "audio/mp3", "audio/mpeg",
        "audio/ogg", "audio/flac", "audio/aac", "audio/x-m4a",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format: {file.content_type}. "
                   f"Supported: {', '.join(allowed_types)}",
        )

    audio_bytes = await file.read()
    logger.info(
        f"Audio submission: constituency={constituency}, "
        f"size={len(audio_bytes)//1024}KB, type={file.content_type}"
    )

    return StreamingResponse(
        _stream_generator(
            svc.ingest_audio_stream(
                audio_bytes=audio_bytes,
                mime_type=file.content_type,
                constituency=constituency,
                submitter_name=submitter_name,
            )
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/image")
async def submit_image(
    constituency: str           = Form(...),
    submitter_name: str | None  = Form(None),
    caption: str | None         = Form(None),
    file: UploadFile            = File(...),
    svc: IngestionService       = Depends(get_ingestion_service),
) -> StreamingResponse:
    """
    Accept an image submission (photo of a civic problem) and stream analysis.

    Supported formats: image/jpeg, image/png, image/webp, image/gif
    Max size: controlled by MAX_IMAGE_SIZE_MB env var (default 5 MB)

    Form fields:
      constituency (str)
      submitter_name (str, optional)
      caption (str, optional) — citizen's text caption accompanying the photo
      file (UploadFile)
    """
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image format: {file.content_type}.",
        )

    image_bytes = await file.read()
    logger.info(
        f"Image submission: constituency={constituency}, "
        f"size={len(image_bytes)//1024}KB, type={file.content_type}"
    )

    return StreamingResponse(
        _stream_generator(
            svc.ingest_image_stream(
                image_bytes=image_bytes,
                mime_type=file.content_type,
                constituency=constituency,
                submitter_name=submitter_name,
                caption=caption,
            )
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """Fetch a single processed submission by ID."""
    data = await db.get_submission(submission_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found.")
    return data


@router.get("")
async def list_submissions(
    constituency: str | None = None,
    limit: int = 50,
    db: FirebaseService = Depends(get_firebase),
) -> list[dict]:
    """
    List recent submissions, optionally filtered by constituency.
    Used by the MP dashboard in Phase 4.
    """
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit cannot exceed 200.")
    return await db.list_submissions(constituency=constituency, limit=limit)


@router.patch("/{submission_id}/override")
async def apply_override(
    submission_id: str,
    req: OverrideRequest,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """
    Human label correction endpoint.

    The MP or operator can correct any AI-generated label — category,
    location, severity — without re-running the AI pipeline.

    Body:
      {
        "submission_id": "...",
        "field_path": "issues[0].category",
        "corrected_value": "road",
        "override_by": "mp_user_id",
        "reason": "Misclassified — pothole issue not water"
      }

    The override is stored in the `override` field of the ConfidenceAnnotation
    and written to an audit subcollection.
    """
    if req.submission_id != submission_id:
        raise HTTPException(400, "submission_id in path and body must match.")
    try:
        result = await db.apply_override(req)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
