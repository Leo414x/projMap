"""Tests for DuckDB store: table creation, insert, query."""

import pytest
from pathlib import Path

from projmap.storage.duckdb_store import DuckDBStore


@pytest.fixture
def store(tmp_path):
    db = DuckDBStore(tmp_path / "test.duckdb")
    yield db
    db.close()


class TestTableCreation:
    def test_all_tables_exist(self, store):
        counts = store.counts()
        assert "files" in counts
        assert "chunks" in counts
        assert "nodes" in counts
        assert "edges" in counts
        assert "extractions" in counts

    def test_initial_counts_zero(self, store):
        counts = store.counts()
        assert all(v == 0 for v in counts.values())


class TestFileOps:
    def test_upsert_and_get_hash(self, store):
        store.upsert_file("README.md", "md", "hash1", 100, None, "new")
        assert store.get_file_hash("README.md") == "hash1"

    def test_upsert_update(self, store):
        store.upsert_file("README.md", "md", "hash1", 100, None, "new")
        store.upsert_file("README.md", "md", "hash2", 200, None, "changed")
        assert store.get_file_hash("README.md") == "hash2"

    def test_get_all_hashes(self, store):
        store.upsert_file("a.md", "md", "h1", 10, None, "new")
        store.upsert_file("b.md", "md", "h2", 20, None, "new")
        hashes = store.get_all_file_hashes()
        assert hashes == {"a.md": "h1", "b.md": "h2"}

    def test_get_nonexistent_hash(self, store):
        assert store.get_file_hash("nope.md") is None


class TestChunkOps:
    def test_insert_and_query(self, store):
        store.insert_chunk("c1", "README.md", 0, "Intro", "intro", "content", "chash", 1, 10)
        counts = store.counts()
        assert counts["chunks"] == 1

    def test_delete_for_file(self, store):
        store.insert_chunk("c1", "README.md", 0, "S1", "s1", "content1", "h1", 1, 5)
        store.insert_chunk("c2", "README.md", 1, "S2", "s2", "content2", "h2", 6, 10)
        store.insert_chunk("c3", "other.md", 0, None, None, "content3", "h3", 1, 5)

        store.delete_chunks_for_file("README.md")
        counts = store.counts()
        assert counts["chunks"] == 1  # only other.md remains


class TestNodeOps:
    def test_insert_node(self, store):
        inserted = store.insert_node(
            "nid1", "decision", "Chose DuckDB", "detail",
            "README.md", "c1", "line 5", "evidence", 0.9, "chash"
        )
        assert inserted is True

    def test_duplicate_node_skipped(self, store):
        store.insert_node(
            "nid1", "decision", "Chose DuckDB", "detail",
            "README.md", "c1", "line 5", "evidence", 0.9, "chash"
        )
        inserted = store.insert_node(
            "nid1", "decision", "Chose DuckDB", "detail",
            "README.md", "c1", "line 5", "evidence", 0.9, "chash"
        )
        assert inserted is False

    def test_delete_nodes_for_file(self, store):
        store.insert_node("n1", "decision", "A", "", "f1.md", "c1", None, "ev", 0.9, "h1")
        store.insert_node("n2", "risk", "B", "", "f1.md", "c1", None, "ev", 0.8, "h2")
        store.insert_node("n3", "decision", "C", "", "f2.md", "c2", None, "ev", 0.7, "h3")
        store.delete_nodes_for_file("f1.md")
        counts = store.counts()
        assert counts["nodes"] == 1

    def test_node_type_counts(self, store):
        store.insert_node("n1", "decision", "Content A", "", "f.md", "c1", None, "ev", 0.9, "h1")
        store.insert_node("n2", "risk", "Content B", "", "f.md", "c1", None, "ev", 0.8, "h2")
        store.insert_node("n3", "decision", "Content C", "", "f.md", "c1", None, "ev", 0.7, "h3")
        tc = store.node_type_counts()
        assert tc["decision"] == 2
        assert tc["risk"] == 1


class TestEdgeOps:
    def test_insert_edge(self, store):
        store.insert_edge("e1", "n1", "n2", "depends-on", "ev", 0.8, "f.md", "c1")
        counts = store.counts()
        assert counts["edges"] == 1

    def test_delete_edges_for_file(self, store):
        store.insert_edge("e1", "n1", "n2", "depends-on", "ev", 0.8, "f1.md", "c1")
        store.insert_edge("e2", "n3", "n4", "conflicts-with", "ev", 0.7, "f2.md", "c2")
        store.delete_edges_for_file("f1.md")
        counts = store.counts()
        assert counts["edges"] == 1


class TestExtractionOps:
    def test_insert_extraction(self, store):
        store.insert_extraction("ex1", "c1", "f.md", "claude-3", "raw", "{}", "success", None)
        counts = store.counts()
        assert counts["extractions"] == 1

    def test_failed_extraction(self, store):
        store.insert_extraction("ex1", "c1", "f.md", "claude-3", "raw", None, "json_parse_failed", "bad json")
        counts = store.counts()
        assert counts["extractions"] == 1
