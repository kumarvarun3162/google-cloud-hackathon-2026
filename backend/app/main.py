"""
main.py — FastAPI application entrypoint (Phase 1 + Phase 2).

Run from backend/ directory:
  uvicorn app.main:app --port 8080 --reload

Swagger UI:  http://localhost:8080/docs
Health:      http://localhost:8080/health
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import submissions, clusters
from app.services.embedding_service import EmbeddingService
from app.services.clustering_service import ClusteringService
from app.services.firebase_service import FirebaseService
from app.services.gemini_service import GeminiService
from app.utils.config import get_settings

cfg = get_settings()

logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CitizenPriority API",
    description=(
        "Multilingual citizen grievance ingestion + duplicate clustering "
        "for MP development planning. "
        "Phase 1: text / audio / image ingestion with Gemini AI. "
        "Phase 2: automatic duplicate clustering with Gemini Embeddings."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",       # Vite
        "http://localhost:3000",       # CRA
        "https://*.web.app",           # Firebase Hosting
        "https://*.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    logger.info("Starting CitizenPriority API (Phase 1 + 2)...")
    logger.info(f"Env: {cfg.app_env} | Gemini model: {cfg.gemini_model}")
    logger.info(f"Cluster threshold: {cfg.cluster_similarity_threshold}")

    # Initialise singletons — order matters: firebase first (no deps),
    # then embedding (no deps), then clustering (needs both), then gemini.
    firebase   = FirebaseService()
    embedding  = EmbeddingService()
    clustering = ClusteringService(embedding, firebase)
    gemini     = GeminiService()

    # Wire into routes
    submissions.init_services(gemini, firebase, clustering)
    clusters.init_services(clustering, firebase)

    logger.info("All services initialised. Ready.")


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("Shutting down.")


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(submissions.router)
app.include_router(clusters.router)


# ── Health + meta ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "version": "2.0.0",
        "phase": 2,
        "model": cfg.gemini_model,
        "env": cfg.app_env,
        "cluster_threshold": cfg.cluster_similarity_threshold,
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
            "duplicate_clustering",      # Phase 2
            "cluster_summary_gemini",    # Phase 2
            "cluster_status_management", # Phase 2
        ],
    }


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "message": "CitizenPriority API v2 — see /docs",
        "endpoints": {
            "submit_text":      "POST /api/v1/submissions/text",
            "submit_audio":     "POST /api/v1/submissions/audio",
            "submit_image":     "POST /api/v1/submissions/image",
            "list_submissions": "GET  /api/v1/submissions",
            "list_clusters":    "GET  /api/v1/clusters",
            "cluster_detail":   "GET  /api/v1/clusters/{id}",
            "cluster_stats":    "GET  /api/v1/clusters/{id}/stats",
            "resolve_cluster":  "PATCH /api/v1/clusters/{id}/status",
        },
    }