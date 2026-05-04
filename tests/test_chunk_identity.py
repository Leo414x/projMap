"""Tests for chunk identity stabilization: heading paths, semantic anchors, slugify."""

import pytest

from projmap.schemas import slugify_heading_path
from projmap.chunker import chunk_text, extract_heading_events, heading_path_for_offset


class TestSlugifyHeadingPath:
    def test_simple(self):
        assert slugify_heading_path("V13") == "v13"

    def test_nested(self):
        result = slugify_heading_path("V13 > V8.4 > Final Decision")
        assert result == "v13/v8-4/final-decision"

    def test_special_chars(self):
        result = slugify_heading_path("Setup & Config!")
        assert result == "setup-config"

    def test_none(self):
        assert slugify_heading_path(None) is None

    def test_empty(self):
        assert slugify_heading_path("") is None

    def test_spaces_only(self):
        assert slugify_heading_path("  ") is None

    def test_idempotent(self):
        inp = "V13 > V8.4 > Final Decision"
        assert slugify_heading_path(inp) == slugify_heading_path(inp)

    def test_multiple_arrows(self):
        result = slugify_heading_path("A > B > C > D")
        assert result == "a/b/c/d"

    def test_collapses_dashes(self):
        result = slugify_heading_path("Hello---World")
        assert result == "hello-world"


class TestExtractHeadingEvents:
    def test_basic_headings(self):
        content = "# V13\n\nIntro\n\n## V8.4\n\nContent"
        events = extract_heading_events(content)
        assert len(events) == 2
        assert events[0]["title"] == "V13"
        assert events[0]["heading_path"] == "V13"
        assert events[1]["heading_path"] == "V13 > V8.4"

    def test_three_levels(self):
        content = "# V13\n\n## V8.4\n\n### Final Decision\n\nText"
        events = extract_heading_events(content)
        assert len(events) == 3
        assert events[2]["heading_path"] == "V13 > V8.4 > Final Decision"

    def test_no_headings(self):
        content = "Just some text\nNo headings"
        events = extract_heading_events(content)
        assert len(events) == 0

    def test_level_reset(self):
        content = "# A\n\n## B\n\n# C\n\nText"
        events = extract_heading_events(content)
        assert len(events) == 3
        assert events[1]["heading_path"] == "A > B"
        assert events[2]["heading_path"] == "C"  # A > B reset when # C appears


class TestHeadingPathForOffset:
    def test_before_first_heading(self):
        events = [{"offset": 10, "heading_path": "V13"}]
        assert heading_path_for_offset(events, 5) is None

    def test_after_heading(self):
        events = [{"offset": 0, "heading_path": "V13"}]
        assert heading_path_for_offset(events, 50) == "V13"

    def test_between_headings(self):
        events = [
            {"offset": 0, "heading_path": "V13"},
            {"offset": 100, "heading_path": "V13 > V8.4"},
        ]
        assert heading_path_for_offset(events, 50) == "V13"


class TestChunkHasHeadingFields:
    def test_chunk_has_heading_path(self):
        content = "# V13\n\nSome content about V13."
        chunks = chunk_text(content, "test.md", max_chars=1000)
        assert len(chunks) >= 1
        assert chunks[0].heading_path == "V13"

    def test_chunk_has_semantic_anchor(self):
        content = "# V13\n\nSome content."
        chunks = chunk_text(content, "test.md", max_chars=1000)
        assert chunks[0].semantic_anchor == "v13"

    def test_chunk_no_heading_uses_index_anchor(self):
        content = "Just plain text without any headings at all."
        chunks = chunk_text(content, "test.md", max_chars=1000)
        assert chunks[0].heading_path is None
        assert chunks[0].semantic_anchor == "chunk-0000"

    def test_nested_heading(self):
        # Verify that heading events correctly track nested headings
        from projmap.chunker import extract_heading_events, heading_path_for_offset

        content = "# V13\n\nIntro text.\n\n## V8.4\n\nDecision content here."
        events = extract_heading_events(content)

        # Second heading should have nested path
        v84_event = [e for e in events if "V8.4" in e.get("title", "")]
        assert len(v84_event) == 1
        assert v84_event[0]["heading_path"] == "V13 > V8.4"

        # Content after V8.4 heading should resolve to V13 > V8.4
        v84_offset = v84_event[0]["offset"]
        hp = heading_path_for_offset(events, v84_offset + 10)
        assert hp == "V13 > V8.4"


class TestChunkIdStability:
    def test_same_content_same_anchor_same_id(self):
        content = "# Intro\n\nHello world"
        c1 = chunk_text(content, "test.md", max_chars=1000)
        c2 = chunk_text(content, "test.md", max_chars=1000)
        assert c1[0].id == c2[0].id

    def test_different_content_different_id(self):
        c1 = chunk_text("# A\n\nHello world", "test.md", max_chars=1000)
        c2 = chunk_text("# A\n\nDifferent content here", "test.md", max_chars=1000)
        assert c1[0].id != c2[0].id

    def test_different_heading_different_id(self):
        c1 = chunk_text("# A\n\nSame content", "test.md", max_chars=1000)
        c2 = chunk_text("# B\n\nSame content", "test.md", max_chars=1000)
        assert c1[0].id != c2[0].id


class TestPrepareExtractionAnchors:
    def test_task_contains_anchor(self, tmp_path):
        from projmap import api

        root = tmp_path / "project"
        root.mkdir()
        (root / "doc.md").write_text("# Architecture\n\nWe chose Python.")
        api.init_project(str(root))
        result = api.prepare_extraction(str(root))
        assert result["ok"] is True

        import json
        manifest = json.loads(
            (root / ".projmap" / "extraction_tasks" / "task_manifest.json").read_text()
        )
        t = manifest["tasks"][0]
        assert t["heading_path"] == "Architecture"
        assert t["semantic_anchor"] == "architecture"

        task_data = json.loads(
            (root / ".projmap" / "extraction_tasks" / f"{t['task_id']}.json").read_text()
        )
        assert task_data["heading_path"] == "Architecture"
        assert task_data["semantic_anchor"] == "architecture"


class TestChunksTableHasAnchorColumns:
    def test_table_has_columns(self, tmp_path):
        from projmap.storage.duckdb_store import DuckDBStore

        store = DuckDBStore(tmp_path / "test.duckdb")
        store.insert_chunk("c1", "f.md", 0, "Intro", "intro", "content", "h", 1, 5)
        # Verify columns exist by querying
        row = store.conn.execute(
            "SELECT heading_path, semantic_anchor FROM chunks WHERE id = 'c1'"
        ).fetchone()
        assert row[0] == "Intro"
        assert row[1] == "intro"
        store.close()
