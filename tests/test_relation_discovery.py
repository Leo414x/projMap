"""Tests for relation discovery module."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from projmap.report.relation_discovery import (
    cluster_candidates,
    _parse_edges_response,
)
from projmap import api


@pytest.fixture
def project_dir(tmp_path):
    """Create and init a project with sample docs."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text(
        "# Test\n\nDecision: Use Python for backend.\nDecision: Use React for frontend.\n"
        "Risk: API latency may be high.\nConstraint: Must deploy on AWS."
    )
    api.init_project(str(root))
    return root


class TestClusterCandidates:
    def test_groups_by_type_project_module(self):
        nodes = [
            {"id": "1", "type": "decision", "project": "p", "module": "m", "version": "v1"},
            {"id": "2", "type": "decision", "project": "p", "module": "m", "version": "v2"},
            {"id": "3", "type": "risk", "project": "p", "module": "m", "version": "v1"},
        ]
        clusters = cluster_candidates(nodes)
        assert len(clusters) == 2
        types = {c[0]["type"] for c in clusters}
        assert types == {"decision", "risk"}

    def test_caps_at_max_size(self):
        nodes = [
            {"id": str(i), "type": "decision", "project": "p", "module": "m", "version": ""}
            for i in range(25)
        ]
        clusters = cluster_candidates(nodes, max_cluster_size=20)
        assert len(clusters) == 2
        assert len(clusters[0]) == 20
        assert len(clusters[1]) == 5

    def test_incremental_skip_fully_covered_cluster(self):
        nodes = [
            {"id": "1", "type": "decision", "project": "p", "module": "m", "version": ""},
            {"id": "2", "type": "decision", "project": "p", "module": "m", "version": ""},
        ]
        existing = {"1", "2"}
        clusters = cluster_candidates(nodes, existing_edge_node_ids=existing)
        assert len(clusters) == 0

    def test_incremental_keeps_partial_cluster(self):
        nodes = [
            {"id": "1", "type": "decision", "project": "p", "module": "m", "version": ""},
            {"id": "2", "type": "decision", "project": "p", "module": "m", "version": ""},
            {"id": "3", "type": "decision", "project": "p", "module": "m", "version": ""},
        ]
        existing = {"1", "2"}
        clusters = cluster_candidates(nodes, existing_edge_node_ids=existing)
        assert len(clusters) == 1

    def test_sorts_by_version_descending(self):
        nodes = [
            {"id": "1", "type": "decision", "project": "p", "module": "m", "version": "v1"},
            {"id": "2", "type": "decision", "project": "p", "module": "m", "version": "v3"},
            {"id": "3", "type": "decision", "project": "p", "module": "m", "version": "v2"},
        ]
        clusters = cluster_candidates(nodes)
        versions = [n["version"] for n in clusters[0]]
        assert versions == ["v3", "v2", "v1"]


class TestParseEdgesResponse:
    def test_valid_edges(self):
        raw = json.dumps({
            "edges": [
                {"source_id": "a", "target_id": "b", "relation": "supersedes",
                 "evidence": "A replaces B", "confidence": 0.9},
            ]
        })
        valid = {"a", "b"}
        edges = _parse_edges_response(raw, valid, 0.6)
        assert len(edges) == 1
        assert edges[0]["source_id"] == "a"

    def test_drops_self_reference(self):
        raw = json.dumps({
            "edges": [
                {"source_id": "a", "target_id": "a", "relation": "supersedes",
                 "evidence": "self", "confidence": 0.9},
            ]
        })
        edges = _parse_edges_response(raw, {"a"}, 0.6)
        assert len(edges) == 0

    def test_drops_invalid_ids(self):
        raw = json.dumps({
            "edges": [
                {"source_id": "a", "target_id": "z", "relation": "supersedes",
                 "evidence": "test", "confidence": 0.9},
            ]
        })
        edges = _parse_edges_response(raw, {"a", "b"}, 0.6)
        assert len(edges) == 0

    def test_drops_low_confidence(self):
        raw = json.dumps({
            "edges": [
                {"source_id": "a", "target_id": "b", "relation": "depends-on",
                 "evidence": "maybe", "confidence": 0.3},
            ]
        })
        edges = _parse_edges_response(raw, {"a", "b"}, 0.6)
        assert len(edges) == 0

    def test_empty_edges(self):
        raw = json.dumps({"edges": []})
        edges = _parse_edges_response(raw, {"a", "b"}, 0.6)
        assert edges == []


class TestPrepareRelationTasks:
    def test_creates_manifest(self, project_dir):
        from projmap.report.relation_discovery import prepare_relation_tasks
        result = prepare_relation_tasks(str(project_dir))
        assert result["ok"] is True
        manifest_path = project_dir / ".projmap" / "relation_tasks" / "manifest.json"
        assert manifest_path.exists()

    def test_creates_prompt_md(self, project_dir):
        from projmap.report.relation_discovery import prepare_relation_tasks
        prepare_relation_tasks(str(project_dir))
        prompt_path = project_dir / ".projmap" / "relation_tasks" / "prompt.md"
        assert prompt_path.exists()
        assert len(prompt_path.read_text()) > 100

    def test_not_initialized(self, tmp_path):
        from projmap.report.relation_discovery import prepare_relation_tasks
        root = tmp_path / "empty"
        root.mkdir()
        result = prepare_relation_tasks(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"


class TestImportRelationResults:
    def test_no_manifest(self, project_dir):
        from projmap.report.relation_discovery import import_relation_results
        result = import_relation_results(str(project_dir))
        assert result["ok"] is False
        assert result["error_code"] == "MANIFEST_NOT_FOUND"

    def test_not_initialized(self, tmp_path):
        from projmap.report.relation_discovery import import_relation_results
        root = tmp_path / "empty"
        root.mkdir()
        result = import_relation_results(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"
