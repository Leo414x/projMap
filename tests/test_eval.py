"""Tests for the eval framework."""

from __future__ import annotations

import json
import pytest
from pathlib import Path


class TestEvalRelations:
    def test_perfect_match(self, tmp_path):
        from projmap.eval.relation_eval import eval_relations
        from projmap import api

        root = tmp_path / "project"
        root.mkdir()
        (root / "README.md").write_text("# Test\nDecision: Use Python.")
        api.init_project(str(root))

        # Insert nodes and edges manually
        from projmap.storage.duckdb_store import DuckDBStore
        from projmap.config import load_config
        cfg = load_config(str(root))

        store = DuckDBStore(cfg.db_path)
        store.insert_node("n1", "decision", "Use Python", source_file="README.md")
        store.insert_node("n2", "decision", "Use Go", source_file="README.md")
        store.insert_edge("e1", "n1", "n2", "supersedes", "test", 0.9,
                          "README.md", "", source="relation_discovery")
        store.close()

        gt = {"edges": [{"from_id": "n1", "to_id": "n2", "relation": "supersedes"}]}
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt))

        result = eval_relations(str(root), str(gt_path))
        assert result["ok"] is True
        assert result["true_positives"] == 1
        assert result["false_positives"] == 0
        assert result["false_negatives"] == 0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_partial_match(self, tmp_path):
        from projmap.eval.relation_eval import eval_relations
        from projmap import api
        from projmap.storage.duckdb_store import DuckDBStore
        from projmap.config import load_config

        root = tmp_path / "project"
        root.mkdir()
        (root / "README.md").write_text("# Test")
        api.init_project(str(root))
        cfg = load_config(str(root))

        store = DuckDBStore(cfg.db_path)
        store.insert_node("n1", "decision", "A", source_file="README.md")
        store.insert_node("n2", "decision", "B", source_file="README.md")
        store.insert_node("n3", "decision", "C", source_file="README.md")
        store.insert_edge("e1", "n1", "n2", "supersedes", "", 0.9,
                          "README.md", "", source="relation_discovery")
        store.close()

        # GT has n1->n2 (TP) and n2->n3 (FN)
        gt = {"edges": [
            {"from_id": "n1", "to_id": "n2", "relation": "supersedes"},
            {"from_id": "n2", "to_id": "n3", "relation": "depends-on"},
        ]}
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt))

        result = eval_relations(str(root), str(gt_path))
        assert result["true_positives"] == 1
        assert result["false_negatives"] == 1
        assert result["recall"] < 1.0

    def test_no_match(self, tmp_path):
        from projmap.eval.relation_eval import eval_relations
        from projmap import api
        from projmap.storage.duckdb_store import DuckDBStore
        from projmap.config import load_config

        root = tmp_path / "project"
        root.mkdir()
        (root / "README.md").write_text("# Test")
        api.init_project(str(root))
        cfg = load_config(str(root))

        store = DuckDBStore(cfg.db_path)
        store.insert_node("n1", "decision", "A", source_file="README.md")
        store.insert_node("n2", "decision", "B", source_file="README.md")
        store.insert_edge("e1", "n1", "n2", "supersedes", "", 0.9,
                          "README.md", "", source="relation_discovery")
        store.close()

        gt = {"edges": [{"from_id": "x", "to_id": "y", "relation": "depends-on"}]}
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt))

        result = eval_relations(str(root), str(gt_path))
        assert result["true_positives"] == 0
        assert result["false_positives"] == 1
        assert result["false_negatives"] == 1


class TestEvalBrief:
    def test_returns_structure(self, tmp_path):
        from projmap.eval.brief_eval import eval_brief_vs_claude

        root = tmp_path / "project"
        root.mkdir()
        (root / "README.md").write_text("# Test")
        from projmap import api
        api.init_project(str(root))

        result = eval_brief_vs_claude(str(root), "docs", "What decisions were made?")
        assert result["ok"] is True
        assert "projmap_brief" in result
        assert "claude_direct" in result
        assert "question" in result
