"""
clustering_service.py — Duplicate complaint clustering for Phase 2.

Algorithm: incremental centroid-based (online, no retraining needed).

For each incoming submission:
  1. Embed English text → 768-dim vector (Gemini text-embedding-004).
  2. Load existing cluster centroids for same constituency + category.
  3. Cosine similarity with each centroid.
  4. If best_sim >= threshold (default 0.72) → join that cluster, update centroid.
  5. Else → create new cluster.
  6. Generate/refresh plain-English cluster title + summary via Gemini.
  7. Persist to Firestore. Tag submission with cluster_id.

Determinism guarantee:
  Same submission always lands in same cluster (given same cluster state)
  because cosine_similarity is deterministic and we use argmax.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from google import genai
from google.genai import types

from app.models.schemas import (
    ClusterAssignment,
    ClusterRecord,
    ClusterStatus,
    ConfidenceLevel,
    ExtractedIssue,
    ProcessingFlag,
)
from app.services.embedding_service import (
    EmbeddingService,
    cosine_similarity,
    find_most_central,
    mean_vector,
)
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

CLUSTER_THRESHOLD_DEFAULT = 0.72

_SUMMARY_PROMPT = """
Summarise this cluster of similar citizen complaints for an Indian MP's dashboard.

Category: {category}
Constituency: {constituency}
Number of complaints: {count}

Sample complaints (up to 5):
{samples}

Return ONLY valid JSON, no markdown:
{{
  "title": "<5-10 word title describing the common problem>",
  "summary": "<2-3 sentence summary: what citizens report, location if mentioned, urgency>",
  "dominant_severity": "<urgent|moderate|chronic>",
  "confidence": <float 0.0-1.0>
}}
"""


class ClusteringService:

    def __init__(
        self,
        embedding_svc: EmbeddingService,
        firebase_svc,
    ) -> None:
        self._embed  = embedding_svc
        self._db     = firebase_svc
        cfg = get_settings()
        self._threshold = getattr(cfg, "cluster_similarity_threshold", CLUSTER_THRESHOLD_DEFAULT)
        self._client = genai.Client(api_key=cfg.gemini_api_key)
        self._model  = cfg.gemini_model
        self._gen_cfg = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=512,
        )

    async def assign_submission(
        self,
        submission_id: str,
        english_text:  str,
        issues:        list[ExtractedIssue],
        constituency:  str,
    ) -> tuple[ClusterAssignment, list[ProcessingFlag]]:
        flags: list[ProcessingFlag] = []

        primary_category = "other"
        if issues:
            best = max(issues, key=lambda i: i.category.score)
            primary_category = best.category.effective_value

        embedding, embed_flags = self._embed.embed(english_text)
        flags.extend(embed_flags)

        existing = await self._db.get_clusters(
            constituency=constituency,
            category=primary_category,
        )

        best_cluster: ClusterRecord | None = None
        best_sim: float = 0.0
        for cluster in existing:
            sim = cosine_similarity(embedding, cluster.centroid_embedding)
            if sim > best_sim:
                best_sim, best_cluster = sim, cluster

        is_new = best_sim < self._threshold or best_cluster is None

        if is_new:
            cluster_id = str(uuid.uuid4())
            assignment = await self._create_cluster(
                cluster_id, submission_id, english_text,
                embedding, primary_category, constituency, issues,
            )
        else:
            assignment = await self._update_cluster(
                best_cluster, submission_id, english_text,
                embedding, best_sim, issues,
            )

        await self._db.tag_submission_cluster(
            submission_id=submission_id,
            cluster_id=assignment.cluster_id,
            similarity_score=assignment.similarity_score,
        )

        return assignment, flags

    async def _create_cluster(
        self,
        cluster_id:   str,
        submission_id: str,
        english_text:  str,
        embedding:     list[float],
        category:      str,
        constituency:  str,
        issues:        list[ExtractedIssue],
    ) -> ClusterAssignment:
        now = datetime.now(timezone.utc).isoformat()
        title, summary, severity, conf = self._generate_summary(
            category, constituency, 1, [english_text]
        )
        cluster = ClusterRecord(
            cluster_id=cluster_id,
            constituency=constituency,
            category=category,
            title=title,
            summary=summary,
            submission_ids=[submission_id],
            submission_count=1,
            centroid_embedding=embedding,
            representative_text=english_text[:500],
            severity_distribution={severity: 1} if severity else {"moderate": 1},
            confidence=conf,
            confidence_level=self._conf_level(conf),
            status=ClusterStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        await self._db.save_cluster(cluster)
        logger.info(f"New cluster: {cluster_id} ({category}, {constituency})")
        return ClusterAssignment(
            submission_id=submission_id,
            cluster_id=cluster_id,
            similarity_score=1.0,
            is_new_cluster=True,
            cluster_size=1,
        )

    async def _update_cluster(
        self,
        cluster:       ClusterRecord,
        submission_id: str,
        english_text:  str,
        embedding:     list[float],
        similarity:    float,
        issues:        list[ExtractedIssue],
    ) -> ClusterAssignment:
        now        = datetime.now(timezone.utc).isoformat()
        updated_ids = cluster.submission_ids + [submission_id]
        new_count   = len(updated_ids)
        old_n       = cluster.submission_count

        # Incremental centroid update
        new_centroid = [
            (cluster.centroid_embedding[i] * old_n + embedding[i]) / new_count
            for i in range(len(embedding))
        ]

        sev_dist = dict(cluster.severity_distribution)
        for issue in issues:
            sev = issue.severity_hint or "moderate"
            sev_dist[sev] = sev_dist.get(sev, 0) + 1

        # Refresh summary every 5 members
        if new_count % 5 == 0 or new_count <= 3:
            samples = await self._db.get_cluster_sample_texts(cluster.cluster_id, limit=5)
            samples.append(english_text)
            title, summary, _, conf = self._generate_summary(
                cluster.category, cluster.constituency, new_count, samples
            )
        else:
            title, summary, conf = cluster.title, cluster.summary, cluster.confidence

        updated = ClusterRecord(
            cluster_id=cluster.cluster_id,
            constituency=cluster.constituency,
            category=cluster.category,
            title=title,
            summary=summary,
            submission_ids=updated_ids,
            submission_count=new_count,
            centroid_embedding=new_centroid,
            representative_text=cluster.representative_text,
            severity_distribution=sev_dist,
            confidence=conf,
            confidence_level=self._conf_level(conf),
            status=cluster.status,
            created_at=cluster.created_at,
            updated_at=now,
        )
        await self._db.save_cluster(updated)
        logger.info(f"Cluster {cluster.cluster_id} updated: {new_count} members, sim={similarity:.2f}")
        return ClusterAssignment(
            submission_id=submission_id,
            cluster_id=cluster.cluster_id,
            similarity_score=round(similarity, 3),
            is_new_cluster=False,
            cluster_size=new_count,
        )

    def _generate_summary(
        self,
        category:     str,
        constituency: str,
        count:        int,
        samples:      list[str],
    ) -> tuple[str, str, str, float]:
        fb_title    = f"{category.replace('_', ' ').title()} issue in {constituency}"
        fb_summary  = f"{count} citizen(s) reported {category.replace('_', ' ')} problems in {constituency}."
        fb_severity = "moderate"
        fb_conf     = 0.60

        try:
            samples_text = "\n".join(f"- {s[:200]}" for s in samples[:5] if s.strip())
            prompt = _SUMMARY_PROMPT.format(
                category=category, constituency=constituency,
                count=count, samples=samples_text,
            )
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._gen_cfg,
            )
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response.text).strip()
            data = json.loads(cleaned)
            return (
                data.get("title", fb_title),
                data.get("summary", fb_summary),
                data.get("dominant_severity", fb_severity),
                float(data.get("confidence", fb_conf)),
            )
        except Exception as e:
            logger.warning(f"Cluster summary failed: {e}. Using fallback.")
            return fb_title, fb_summary, fb_severity, fb_conf

    @staticmethod
    def _conf_level(score: float) -> ConfidenceLevel:
        if score >= 0.80:
            return ConfidenceLevel.HIGH
        if score >= 0.50:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW