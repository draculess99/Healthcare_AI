"""Tests for the FAISS-backed RAG manager.

These tests verify document loading, chunking, keyword fallback, the
legacy ``query_rag`` API, and the ``/api/rag`` Flask endpoint.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---------------------------------------------------------------------------
# Unit tests for the RAGManager class
# ---------------------------------------------------------------------------

class TestRAGManager:
    """Core RAG manager functionality."""

    def _fresh_manager(self):
        """Return a brand-new RAGManager (bypass singleton for isolation)."""
        from backend.rag_manager import RAGManager
        # Reset singleton so each test gets a fresh instance
        RAGManager._instance = None
        mgr = RAGManager()
        return mgr

    def test_retrieve_returns_results(self):
        mgr = self._fresh_manager()
        results = mgr.retrieve("IV Kit shortage in the Emergency Department")
        assert isinstance(results, list)
        assert len(results) > 0, "Expected at least one result for a known query"

    def test_retrieve_each_result_has_required_keys(self):
        mgr = self._fresh_manager()
        results = mgr.retrieve("catheter recall FDA", top_k=2)
        for r in results:
            assert "text" in r, "Each result must contain 'text'"
            assert "source" in r, "Each result must contain 'source'"
            assert "score" in r, "Each result must contain 'score'"

    def test_retrieve_respects_top_k(self):
        mgr = self._fresh_manager()
        results = mgr.retrieve("surgical mask operating room", top_k=2)
        assert len(results) <= 2

    def test_query_rag_returns_formatted_string(self):
        mgr = self._fresh_manager()
        text = mgr.query_rag("saline flush shortage", n_results=2)
        assert isinstance(text, str)
        assert "RAG Document" in text

    def test_list_sources_returns_filenames(self):
        mgr = self._fresh_manager()
        sources = mgr.list_sources()
        assert isinstance(sources, list)
        # We expect at least the policy docs we created
        assert any("privacy_policy" in s for s in sources), \
            f"Expected privacy_policy in sources, got {sources}"

    def test_get_stats_returns_dict(self):
        mgr = self._fresh_manager()
        stats = mgr.get_stats()
        assert isinstance(stats, dict)
        assert "backend" in stats
        assert stats["backend"] in ("faiss", "keyword")
        assert "total_chunks" in stats
        assert stats["total_chunks"] > 0

    def test_empty_query_returns_empty(self):
        mgr = self._fresh_manager()
        results = mgr.retrieve("")
        # Empty query should still not crash
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestRAGEndpoint:
    """Test the /api/rag Flask endpoint."""

    @pytest.fixture
    def client(self):
        from backend.server import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_rag_query_returns_results(self, client):
        resp = client.post(
            "/api/rag",
            data=json.dumps({"query": "IV Kit shortage Emergency Department"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "results" in body
        assert len(body["results"]) > 0

    def test_rag_query_missing_query(self, client):
        resp = client.post(
            "/api/rag",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rag_stats_endpoint(self, client):
        resp = client.get("/api/rag/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "backend" in body
        assert "total_chunks" in body
        assert "sources" in body
