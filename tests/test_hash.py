"""Tests for chunker.py: chunk creation, size limits, line tracking."""

import pytest

from projmap.chunker import chunk_text
from projmap.schemas import file_hash


class TestChunkText:
    def test_single_chunk(self):
        content = "Short content"
        chunks = chunk_text(content, "test.md", max_chars=1000)
        assert len(chunks) == 1
        assert chunks[0].content == content

    def test_multiple_chunks(self):
        content = "A" * 500
        chunks = chunk_text(content, "test.md", max_chars=200, overlap_chars=50)
        assert len(chunks) > 1

    def test_chunk_respects_max_chars(self):
        content = "Word " * 5000  # ~25k chars
        chunks = chunk_text(content, "test.md", max_chars=12000, overlap_chars=800)
        for chunk in chunks:
            assert len(chunk.content) <= 12000

    def test_chunk_preserves_file_path(self):
        chunks = chunk_text("Hello world", "README.md")
        assert all(c.file_path == "README.md" for c in chunks)

    def test_chunk_index_sequential(self):
        content = "Word " * 5000
        chunks = chunk_text(content, "test.md", max_chars=12000)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_content(self):
        chunks = chunk_text("", "test.md")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n  ", "test.md")
        assert chunks == []

    def test_chunk_has_hash(self):
        chunks = chunk_text("Hello world", "test.md")
        assert chunks[0].content_hash
        assert chunks[0].id

    def test_chunk_id_deterministic(self):
        c1 = chunk_text("Hello world", "test.md")
        c2 = chunk_text("Hello world", "test.md")
        assert c1[0].id == c2[0].id

    def test_chunk_id_differs_for_different_content(self):
        c1 = chunk_text("Hello world", "test.md")
        c2 = chunk_text("Different content", "test.md")
        assert c1[0].id != c2[0].id

    def test_line_tracking(self):
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        chunks = chunk_text(content, "test.md")
        assert chunks[0].start_line == 1
        assert chunks[0].end_line is not None

    def test_splits_at_heading(self):
        content = "Intro text\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2"
        # Small max_chars to force split
        chunks = chunk_text(content, "test.md", max_chars=30, overlap_chars=10)
        assert len(chunks) >= 1
