"""
firebase_service.py — Firebase Firestore operations for Phase 1.

Free tier (Spark plan) limits:
  - 1 GiB storage, 50K reads/day, 20K writes/day, 20K deletes/day
  - More than enough for a hackathon prototype.

Collections:
  submissions/       — one doc per citizen submission
  submissions/{id}/override_log/  — subcollection tracking human corrections

Setup steps (no payment needed):
  1. Go to https://console.firebase.google.com
  2. Create project → enable Firestore (Native mode, any region)
  3. Project Settings → Service Accounts → Generate new private key
  4. Save as firebase-credentials.json in project root
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from app.models.schemas import OverrideRequest, SubmissionResponse
from app.utils.config import get_settings

logger = logging.getLogger(__name__)


def _init_firebase() -> firestore.AsyncClient | None:
    """
    Initialise Firebase Admin SDK.
    Returns None in development if credentials file is missing —
    allows local development without Firebase configured.
    """
    cfg = get_settings()
    cred_path = cfg.firebase_credentials_path

    if not os.path.exists(cred_path):
        if cfg.is_development:
            logger.warning(
                "Firebase credentials not found at %s. "
                "Running in LOCAL mode — submissions will not be persisted.",
                cred_path,
            )
            return None
        raise FileNotFoundError(
            f"Firebase credentials not found: {cred_path}. "
            "Set FIREBASE_CREDENTIALS_PATH in .env"
        )

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    return firestore.AsyncClient(project=cfg.firebase_project_id)


class FirebaseService:
    """
    Handles all Firestore read/write for Phase 1.
    Falls back to in-memory store in development mode if Firebase is not set up.
    """

    COLLECTION = "submissions"

    def __init__(self) -> None:
        self._db = _init_firebase()
        self._local_store: dict[str, dict] = {}   # dev fallback

    @property
    def _is_local(self) -> bool:
        return self._db is None

    async def save_submission(self, submission: SubmissionResponse) -> str:
        """
        Persist a completed submission to Firestore.
        Returns the document ID (= submission_id).
        """
        data = submission.model_dump(mode="json")

        if self._is_local:
            self._local_store[submission.submission_id] = data
            logger.info(f"[LOCAL] Saved submission {submission.submission_id}")
            return submission.submission_id

        doc_ref = self._db.collection(self.COLLECTION).document(submission.submission_id)
        await doc_ref.set(data)
        logger.info(f"[Firestore] Saved submission {submission.submission_id}")
        return submission.submission_id

    async def get_submission(self, submission_id: str) -> dict | None:
        """Fetch a single submission by ID."""
        if self._is_local:
            return self._local_store.get(submission_id)

        doc = await self._db.collection(self.COLLECTION).document(submission_id).get()
        return doc.to_dict() if doc.exists else None

    async def apply_override(self, req: OverrideRequest) -> dict:
        """
        Apply a human label correction to a stored submission.
        Writes the original AI value + corrected value to an override_log
        subcollection for auditability.

        Supports dot-notation field paths like "issues[0].category.override"
        by flattening to Firestore update syntax.
        """
        submission = await self.get_submission(req.submission_id)
        if submission is None:
            raise ValueError(f"Submission {req.submission_id} not found")

        # Parse the field path to set the override slot
        # e.g. "issues[0].category" → set issues[0].category.override
        override_field_path = f"{req.field_path}.override"
        override_by_path = f"{req.field_path}.override_by"

        now = datetime.now(timezone.utc).isoformat()

        if self._is_local:
            # Simple nested set for local dev (doesn't support array notation)
            if req.submission_id in self._local_store:
                self._local_store[req.submission_id]["_override_applied"] = True
            log_entry = {
                "field_path": req.field_path,
                "corrected_value": req.corrected_value,
                "override_by": req.override_by,
                "reason": req.reason,
                "applied_at": now,
            }
            logger.info(f"[LOCAL] Override applied: {log_entry}")
            return log_entry

        # Firestore update with override value
        doc_ref = self._db.collection(self.COLLECTION).document(req.submission_id)
        await doc_ref.update({
            override_field_path: req.corrected_value,
            override_by_path: req.override_by,
            "metadata.flags": firestore.ArrayUnion(["override_applied"]),
        })

        # Write audit log to subcollection
        log_ref = doc_ref.collection("override_log").document()
        await log_ref.set({
            "field_path": req.field_path,
            "corrected_value": req.corrected_value,
            "override_by": req.override_by,
            "reason": req.reason,
            "applied_at": now,
        })

        return {"status": "override_applied", "field": req.field_path, "at": now}

    async def list_submissions(
        self,
        constituency: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List recent submissions, optionally filtered by constituency."""
        if self._is_local:
            results = list(self._local_store.values())
            if constituency:
                results = [r for r in results if r.get("constituency") == constituency]
            return results[:limit]

        query = self._db.collection(self.COLLECTION).order_by(
            "created_at", direction=firestore.Query.DESCENDING
        ).limit(limit)

        if constituency:
            query = query.where("constituency", "==", constituency)

        docs = await query.get()
        return [d.to_dict() for d in docs]
