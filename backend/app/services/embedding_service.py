"""
embedding_service.py — Vector embeddings via Gemini Embedding API (free tier).

Model: text-embedding-004  (768 dimensions)
SDK:   google-genai  (new, replaces deprecated google-generativeai)

Free on Google AI Studio — no payment needed.
Rate limit: 1500 req/day, 100 RPM — fine for hackathon.
"""

from __future__ import annotations

import logging
import math
from collections import Counter

from google import genai
from google.genai import types

from app.models.schemas import ProcessingFlag
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIMS  = 768

_STOPWORDS = {
    "the", "a", "an", "is", "in", "on", "at", "of", "to", "and", "or",
    "hai", "ka", "ki", "ke", "mein", "se", "ko", "ne", "hain", "tha",
    "nahi", "bahut", "yahan", "wahan", "koi", "kuch",
}


def _bow_vector(text: str, dims: int = EMBEDDING_DIMS) -> list[float]:
    """
    Deterministic bag-of-words fallback vector.
    Hash words into fixed-size float array, then L2-normalise.
    """
    words = [w for w in text.lower().split() if w not in _STOPWORDS and len(w) > 2]
    counts = Counter(words)
    vec = [0.0] * dims
    for word, count in counts.items():
        vec[hash(word) % dims] += count
    magnitude = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / magnitude for v in vec]


class EmbeddingService:
    """
    Generates text embeddings using Gemini Embedding API (google-genai SDK).
    Falls back to BoW if API unavailable.
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._client = genai.Client(api_key=cfg.gemini_api_key)
        logger.info(f"EmbeddingService ready — model: {EMBEDDING_MODEL}")

    def embed(self, text: str) -> tuple[list[float], list[ProcessingFlag]]:
        """Embed a single text. Returns (vector, flags). Synchronous."""
        flags: list[ProcessingFlag] = []
        truncated = text[:2000]

        try:
            result = self._client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=truncated,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
            )
            embedding = result.embeddings[0].values
            return list(embedding), flags

        except Exception as e:
            logger.warning(f"Gemini embedding failed: {e}. Using BoW fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return _bow_vector(truncated), flags

    def embed_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[ProcessingFlag]]:
        all_flags: list[ProcessingFlag] = []
        vectors: list[list[float]] = []
        for text in texts:
            vec, flags = self.embed(text)
            vectors.append(vec)
            all_flags.extend(flags)
        return vectors, list(set(all_flags))


# ── Pure math helpers ─────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    mag_b = math.sqrt(sum(x * x for x in b)) or 1e-9
    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


def mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return [0.0] * EMBEDDING_DIMS
    dims = len(vectors[0])
    centroid = [0.0] * dims
    for vec in vectors:
        for i, v in enumerate(vec):
            centroid[i] += v
    n = len(vectors)
    return [v / n for v in centroid]


def find_most_central(vectors: list[list[float]], centroid: list[float]) -> int:
    best_idx, best_score = 0, -1.0
    for i, vec in enumerate(vectors):
        score = cosine_similarity(vec, centroid)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx