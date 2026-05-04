"""Tests for schemas.py: Pydantic validation and ID generation."""

import pytest

from projmap.schemas import (
    ExtractedNode,
    ExtractedEdge,
    ExtractionResult,
    FileRecord,
    ChunkRecord,
    file_hash,
    chunk_id,
    node_id,
    edge_id,
    normalize_content,
)


class TestExtractedNode:
    def test_valid_node(self):
        n = ExtractedNode(
            type="decision",
            content="We chose DuckDB for storage",
            detail="DuckDB provides embedded SQL",
            evidence_quote="decided to use DuckDB",
            confidence=0.9,
        )
        assert n.type == "decision"
        assert n.confidence == 0.9

    def test_invalid_type(self):
        with pytest.raises(Exception):
            ExtractedNode(
                type="invalid_type",
                content="Some content here",
                evidence_quote="quote",
                confidence=0.5,
            )

    def test_content_too_short(self):
        with pytest.raises(Exception):
            ExtractedNode(
                type="decision",
                content="ab",
                evidence_quote="some quote",
                confidence=0.5,
            )

    def test_content_too_long(self):
        with pytest.raises(Exception):
            ExtractedNode(
                type="decision",
                content="x" * 501,
                evidence_quote="some quote",
                confidence=0.5,
            )

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ExtractedNode(
                type="risk",
                content="Valid content here",
                evidence_quote="quote",
                confidence=1.5,
            )

    def test_all_node_types(self):
        for ntype in ("decision", "risk", "assumption", "version", "constraint"):
            n = ExtractedNode(
                type=ntype,
                content=f"This is a {ntype} node content",
                evidence_quote="evidence here",
                confidence=0.5,
            )
            assert n.type == ntype


class TestExtractedEdge:
    def test_valid_edge(self):
        e = ExtractedEdge(
            from_content="We chose DuckDB for storage",
            to_content="DuckDB provides embedded SQL",
            relationship="depends-on",
            evidence_quote="depends on DuckDB",
            confidence=0.8,
        )
        assert e.relationship == "depends-on"

    def test_invalid_relationship(self):
        with pytest.raises(Exception):
            ExtractedEdge(
                from_content="Valid from content",
                to_content="Valid to content",
                relationship="invalid",
                evidence_quote="evidence",
                confidence=0.5,
            )

    def test_all_edge_types(self):
        for etype in ("depends-on", "conflicts-with", "supersedes",
                      "traces-back-to", "mitigates"):
            e = ExtractedEdge(
                from_content="Source node content here",
                to_content="Target node content here",
                relationship=etype,
                evidence_quote="evidence",
                confidence=0.5,
            )
            assert e.relationship == etype


class TestExtractionResult:
    def test_empty(self):
        r = ExtractionResult()
        assert r.nodes == []
        assert r.edges == []

    def test_with_nodes_and_edges(self):
        r = ExtractionResult(
            nodes=[
                ExtractedNode(
                    type="decision",
                    content="We chose DuckDB for local-first storage",
                    evidence_quote="we chose",
                    confidence=0.9,
                )
            ],
            edges=[
                ExtractedEdge(
                    from_content="We chose DuckDB for local-first storage",
                    to_content="The project requires fast local analytics queries",
                    relationship="depends-on",
                    evidence_quote="depends on",
                    confidence=0.8,
                )
            ],
        )
        assert len(r.nodes) == 1
        assert len(r.edges) == 1

    def test_parse_valid_json(self):
        data = {
            "nodes": [
                {
                    "type": "risk",
                    "content": "API dependency is a risk factor",
                    "evidence_quote": "depends on API",
                    "confidence": 0.7,
                }
            ],
            "edges": [],
        }
        r = ExtractionResult.model_validate(data)
        assert len(r.nodes) == 1
        assert r.nodes[0].type == "risk"

    def test_parse_invalid_node_type(self):
        data = {
            "nodes": [
                {
                    "type": "bad_type",
                    "content": "Some content here",
                    "evidence_quote": "quote",
                    "confidence": 0.5,
                }
            ],
            "edges": [],
        }
        with pytest.raises(Exception):
            ExtractionResult.model_validate(data)


class TestIDGeneration:
    def test_file_hash_deterministic(self):
        h1 = file_hash("hello world")
        h2 = file_hash("hello world")
        assert h1 == h2

    def test_file_hash_different_content(self):
        h1 = file_hash("hello")
        h2 = file_hash("world")
        assert h1 != h2

    def test_chunk_id_deterministic(self):
        c1 = chunk_id("README.md", "intro", "abc123")
        c2 = chunk_id("README.md", "intro", "abc123")
        assert c1 == c2

    def test_chunk_id_different_anchor(self):
        c1 = chunk_id("README.md", "intro", "abc123")
        c2 = chunk_id("README.md", "section-2", "abc123")
        assert c1 != c2

    def test_node_id_deterministic(self):
        n1 = node_id("decision", "Chose DuckDB")
        n2 = node_id("decision", "Chose DuckDB")
        assert n1 == n2

    def test_node_id_normalizes(self):
        n1 = node_id("decision", "Chose DuckDB")
        n2 = node_id("decision", "  chose duckdb  ")
        assert n1 == n2

    def test_node_id_different_type(self):
        n1 = node_id("decision", "Chose DuckDB")
        n2 = node_id("risk", "Chose DuckDB")
        assert n1 != n2

    def test_edge_id_deterministic(self):
        e1 = edge_id("from_id", "to_id", "depends-on")
        e2 = edge_id("from_id", "to_id", "depends-on")
        assert e1 == e2


class TestNormalizeContent:
    def test_lower(self):
        assert normalize_content("Hello World") == "hello world"

    def test_strip(self):
        assert normalize_content("  hello  ") == "hello"

    def test_collapse_spaces(self):
        assert normalize_content("hello   world") == "hello world"

    def test_trailing_punct(self):
        assert normalize_content("hello.") == "hello"

    def test_idempotent(self):
        s = "  We chose DuckDB.  "
        assert normalize_content(s) == normalize_content(normalize_content(s))
