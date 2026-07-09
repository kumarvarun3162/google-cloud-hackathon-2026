"""
clusters.py — FastAPI routes for Phase 2: duplicate clustering.

Endpoints:
  GET  /api/v1/clusters                        — list clusters (MP dashboard)
  GET  /api/v1/clusters/{id}                   — single cluster detail
  POST /api/v1/clusters/assign                 — manually trigger cluster assignment
  PATCH /api/v1/clusters/{id}/status           — MP marks cluster resolved/merged
  GET  /api/v1/clusters/{id}/submissions       — all submissions in a cluster

How clustering is triggered:
  Normally the ingestion pipeline (ingestion_service.py) calls ClusteringService
  automatically after saving a submission. The POST /assign endpoint exists for
  re-processing existing submissions or testing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.clustering_service import ClusteringService
from app.services.firebase_service import FirebaseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])

# ── Singletons injected from main.py ──────────────────────────────────────────

_clustering: ClusteringService | None = None
_firebase:   FirebaseService   | None = None


def init_services(clustering: ClusteringService, firebase: FirebaseService) -> None:
    global _clustering, _firebase
    _clustering = clustering
    _firebase   = firebase


def get_clustering() -> ClusteringService:
    if _clustering is None:
        raise RuntimeError("ClusteringService not initialised.")
    return _clustering


def get_firebase() -> FirebaseService:
    if _firebase is None:
        raise RuntimeError("FirebaseService not initialised.")
    return _firebase


# ── Request / response bodies ─────────────────────────────────────────────────

class AssignRequest(BaseModel):
    """Manually trigger cluster assignment for an already-saved submission."""
    submission_id: str
    english_text:  str
    constituency:  str


class StatusUpdateRequest(BaseModel):
    """MP marks a cluster as resolved or merged."""
    status: str    # "resolved" | "merged"
    reason: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_clusters(
    constituency: str | None = None,
    category:     str | None = None,
    status:       str        = "active",
    limit:        int        = 50,
    db: FirebaseService = Depends(get_firebase),
) -> list[dict]:
    """
    List clusters for the MP dashboard, sorted by submission_count descending.
    Centroid embeddings are stripped — frontend doesn't need them.

    Query params:
      constituency  filter by constituency name
      category      filter by issue category (road, water, school, ...)
      status        active | resolved | merged  (default: active)
      limit         max results (default 50, max 200)
    """
    if limit > 200:
        raise HTTPException(400, "limit cannot exceed 200.")
    return await db.list_clusters(
        constituency=constituency,
        category=category,
        status=status,
        limit=limit,
    )


@router.get("/{cluster_id}")
async def get_cluster(
    cluster_id: str,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """
    Full cluster detail — includes submission_ids list and severity distribution.
    Centroid embedding is still stripped (too large, not useful to frontend).
    """
    cluster = await db.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(404, f"Cluster {cluster_id} not found.")

    data = cluster.model_dump(mode="json")
    data.pop("centroid_embedding", None)   # strip before sending
    return data


@router.get("/{cluster_id}/submissions")
async def get_cluster_submissions(
    cluster_id: str,
    limit: int = 20,
    db: FirebaseService = Depends(get_firebase),
) -> list[dict]:
    """
    Fetch all individual submissions that belong to a cluster.
    Used by the MP to drill into "what are people actually saying?"
    Returns submissions ordered by created_at desc.
    """
    cluster = await db.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(404, f"Cluster {cluster_id} not found.")

    sub_ids = cluster.submission_ids[:limit]
    submissions: list[dict] = []
    for sid in sub_ids:
        sub = await db.get_submission(sid)
        if sub:
            # Trim heavy fields before returning
            sub.pop("translation", None)   # keep response small
            submissions.append(sub)

    # Sort newest first
    submissions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return submissions


@router.post("/assign")
async def assign_submission(
    req: AssignRequest,
    svc: ClusteringService = Depends(get_clustering),
    db:  FirebaseService   = Depends(get_firebase),
) -> dict:
    """
    Manually trigger cluster assignment for a submission.
    Useful for re-processing or testing without re-submitting.

    In normal flow, ingestion_service.py calls this automatically.
    """
    # Load existing submission to get issues
    sub_data = await db.get_submission(req.submission_id)
    if sub_data is None:
        raise HTTPException(404, f"Submission {req.submission_id} not found.")

    # Reconstruct issues from stored data
    from app.models.schemas import ExtractedIssue
    raw_issues = sub_data.get("issues", [])
    try:
        issues = [ExtractedIssue(**i) for i in raw_issues]
    except Exception:
        issues = []

    assignment, flags = await svc.assign_submission(
        submission_id=req.submission_id,
        english_text=req.english_text,
        issues=issues,
        constituency=req.constituency,
    )

    return {
        **assignment.model_dump(mode="json"),
        "flags": [f.value for f in flags],
    }


@router.patch("/{cluster_id}/status")
async def update_cluster_status(
    cluster_id: str,
    req: StatusUpdateRequest,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """
    MP marks a cluster as resolved or merged.

    - resolved: problem has been addressed (e.g. road repaired)
    - merged: this cluster was merged into another one manually

    Resolved/merged clusters are filtered out of the default dashboard view.
    """
    valid_statuses = {"active", "resolved", "merged"}
    if req.status not in valid_statuses:
        raise HTTPException(
            400,
            f"Invalid status '{req.status}'. Must be one of: {valid_statuses}",
        )

    cluster = await db.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(404, f"Cluster {cluster_id} not found.")

    result = await db.update_cluster_status(cluster_id, req.status)
    logger.info(f"Cluster {cluster_id} marked {req.status}")
    return result


@router.get("/{cluster_id}/stats")
async def get_cluster_stats(
    cluster_id: str,
    db: FirebaseService = Depends(get_firebase),
) -> dict:
    """
    Summary statistics for a single cluster — used by Phase 4 comparison screen.

    Returns:
      submission_count, severity_distribution, category, constituency,
      confidence, top_location_hints (extracted from member submissions)
    """
    cluster = await db.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(404, f"Cluster {cluster_id} not found.")

    # Collect location hints from member submissions (up to 10)
    location_hints: list[str] = []
    for sid in cluster.submission_ids[:10]:
        sub = await db.get_submission(sid)
        if sub:
            for issue in sub.get("issues", []):
                loc = issue.get("location_hint")
                if loc and loc not in location_hints:
                    location_hints.append(loc)

    return {
        "cluster_id":           cluster.cluster_id,
        "category":             cluster.category,
        "constituency":         cluster.constituency,
        "title":                cluster.title,
        "summary":              cluster.summary,
        "submission_count":     cluster.submission_count,
        "severity_distribution": cluster.severity_distribution,
        "confidence":           cluster.confidence,
        "confidence_level":     cluster.confidence_level,
        "status":               cluster.status,
        "top_location_hints":   location_hints[:5],
        "created_at":           cluster.created_at,
        "updated_at":           cluster.updated_at,
    }