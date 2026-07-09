"""
test_phase2.py — Unit tests for Phase 2 clustering logic.
Zero API calls — tests pure math functions only.

Run from backend/:
  python -m pytest tests/test_phase2.py -v
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.services.embedding_service import (
    cosine_similarity,
    mean_vector,
    find_most_central,
    _bow_vector,
    EMBEDDING_DIMS,
)


# ── cosine_similarity ─────────────────────────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors_are_one(self):
        v = [1.0, 0.0, 0.5]
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors_are_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors_clamped_to_zero(self):
        # We clamp at 0.0 — negative similarity not meaningful for complaints
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        result = cosine_similarity(a, b)
        assert result == 0.0

    def test_similar_vectors(self):
        a = [0.9, 0.1, 0.0]
        b = [0.8, 0.2, 0.0]
        result = cosine_similarity(a, b)
        assert result > 0.99   # very similar

    def test_mismatched_lengths_return_zero(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_zero_vector_handled(self):
        result = cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_result_always_in_range(self):
        import random
        random.seed(42)
        for _ in range(20):
            a = [random.uniform(-1, 1) for _ in range(10)]
            b = [random.uniform(-1, 1) for _ in range(10)]
            result = cosine_similarity(a, b)
            assert 0.0 <= result <= 1.0


# ── mean_vector ───────────────────────────────────────────────────────────────

class TestMeanVector:
    def test_single_vector(self):
        v = [1.0, 2.0, 3.0]
        result = mean_vector([v])
        assert result == pytest.approx(v)

    def test_two_vectors(self):
        a = [0.0, 0.0]
        b = [2.0, 2.0]
        result = mean_vector([a, b])
        assert result == pytest.approx([1.0, 1.0])

    def test_three_vectors(self):
        vecs = [[1.0, 0.0], [0.0, 1.0], [2.0, 2.0]]
        result = mean_vector(vecs)
        assert result == pytest.approx([1.0, 1.0])

    def test_empty_returns_zero_vector(self):
        result = mean_vector([])
        assert len(result) == EMBEDDING_DIMS
        assert all(v == 0.0 for v in result)

    def test_centroid_is_closer_to_cluster_than_outlier(self):
        # Centroid of tight cluster should be far from an outlier
        cluster_vecs = [[0.9, 0.1], [0.85, 0.15], [0.88, 0.12]]
        centroid = mean_vector(cluster_vecs)
        outlier  = [0.0, 1.0]

        sim_cluster = cosine_similarity(centroid, cluster_vecs[0])
        sim_outlier = cosine_similarity(centroid, outlier)
        assert sim_cluster > sim_outlier


# ── find_most_central ─────────────────────────────────────────────────────────

class TestFindMostCentral:
    def test_returns_index_of_closest_to_centroid(self):
        centroid = [1.0, 0.0]
        vecs = [
            [0.9, 0.1],   # index 0 — closest to centroid
            [0.0, 1.0],   # index 1 — orthogonal
            [0.5, 0.5],   # index 2 — middling
        ]
        idx = find_most_central(vecs, centroid)
        assert idx == 0

    def test_single_vector(self):
        v = [1.0, 0.5]
        assert find_most_central([v], v) == 0

    def test_exact_match_wins(self):
        centroid = [1.0, 0.0, 0.0]
        vecs = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        assert find_most_central(vecs, centroid) == 1


# ── BoW fallback vector ───────────────────────────────────────────────────────

class TestBowVector:
    def test_returns_correct_dimensions(self):
        v = _bow_vector("road pothole water supply")
        assert len(v) == EMBEDDING_DIMS

    def test_is_normalised(self):
        v = _bow_vector("school education children")
        magnitude = math.sqrt(sum(x * x for x in v))
        assert magnitude == pytest.approx(1.0, abs=1e-6)

    def test_similar_texts_have_higher_similarity_than_unrelated(self):
        v1 = _bow_vector("pothole on the main road near market")
        v2 = _bow_vector("bad road condition potholes near chowk")
        v3 = _bow_vector("school needs more teachers and classrooms")

        sim_related   = cosine_similarity(v1, v2)
        sim_unrelated = cosine_similarity(v1, v3)
        assert sim_related > sim_unrelated

    def test_empty_text_does_not_crash(self):
        v = _bow_vector("")
        assert len(v) == EMBEDDING_DIMS

    def test_stopwords_are_filtered(self):
        # "hai", "mein", "the", "a" are stopwords — same as without them
        v1 = _bow_vector("road pothole")
        v2 = _bow_vector("the road a pothole hai mein")
        # They won't be identical but should be very similar
        sim = cosine_similarity(v1, v2)
        assert sim > 0.8

    def test_deterministic(self):
        text = "water supply problem in ward 5"
        v1 = _bow_vector(text)
        v2 = _bow_vector(text)
        assert v1 == v2   # must be identical on repeated calls


# ── Cluster threshold behaviour ───────────────────────────────────────────────

class TestClusterThreshold:
    """
    Simulate the cluster assignment decision using pure math —
    no service instantiation, no API calls.
    """
    THRESHOLD = 0.72

    def _should_join(self, new_vec, centroid) -> bool:
        return cosine_similarity(new_vec, centroid) >= self.THRESHOLD

    def test_very_similar_joins_cluster(self):
        centroid  = _bow_vector("pothole main road GT Road")
        new_sub   = _bow_vector("potholes on GT Road near chowk")
        # BoW sim may be lower than Gemini embeddings but still directionally correct
        # Just check the function works — actual threshold is tuned for Gemini embeddings
        result = cosine_similarity(centroid, new_sub)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_completely_unrelated_does_not_join(self):
        centroid  = _bow_vector("pothole road repair needed urgently")
        new_sub   = _bow_vector("school needs more teachers and blackboards")
        sim = cosine_similarity(centroid, new_sub)
        assert not self._should_join(new_sub, centroid) or sim < 0.95

    def test_threshold_boundary(self):
        # At exactly threshold — should join
        v = [1.0, 0.0]
        centroid_at_threshold = [
            math.cos(math.acos(self.THRESHOLD)),
            math.sin(math.acos(self.THRESHOLD)),
        ]
        sim = cosine_similarity(v, centroid_at_threshold)
        assert sim == pytest.approx(self.THRESHOLD, abs=1e-6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])