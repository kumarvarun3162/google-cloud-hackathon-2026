"""
main.py — FastAPI application entrypoint for Phase 1.

Start with:
  uvicorn phase1.app.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
Health:     http://localhost:8000/health
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import submissions
from app.services.firebase_service import FirebaseService
from app.services.gemini_service import GeminiService
from app.utils.config import get_settings

# ── Logging ───────────────────────────────────────────────────────────────────
cfg = get_settings()
logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CitizenPriority — Phase 1 Ingestion API",
    description=(
        "Multilingual citizen grievance ingestion pipeline for MP development planning. "
        "Accepts text, audio, and images. Processes via Gemini AI (Google AI Studio free tier). "
        "Stores to Firebase Firestore (Spark free plan)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the React frontend (running on localhost:5173 in dev) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # CRA dev server (if used)
        "https://*.web.app",       # Firebase Hosting
        "https://*.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    logger.info("Starting CitizenPriority Phase 1 API...")
    logger.info(f"Environment: {cfg.app_env}")
    logger.info(f"Gemini model: {cfg.gemini_model}")

    # Initialise singletons
    gemini = GeminiService()
    firebase = FirebaseService()

    # Wire into route module
    submissions.init_services(gemini, firebase)
    logger.info("Services initialised. Ready.")


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("Shutting down.")


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(submissions.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """
    Simple liveness probe.
    Returns the model and environment so frontend can confirm the right
    backend is connected.
    """
    return {
        "status": "ok",
        "model": cfg.gemini_model,
        "env": cfg.app_env,
        "phase": 1,
        "features": [
            "text_ingestion",
            "audio_transcription",
            "image_analysis",
            "multilingual",
            "streaming_sse",
            "confidence_scores",
            "human_override",
            "guardrails",
            "silent_fallback",
        ],
    }


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {"message": "CitizenPriority Phase 1 API — see /docs"}
