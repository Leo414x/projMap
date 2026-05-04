"""Tests for cache.py: file hash cache read/write."""

import pytest
from pathlib import Path

from projmap.storage.cache import FileHashCache


@pytest.fixture
def cache(tmp_path):
    return FileHashCache(tmp_path / "cache")


class TestFileHashCache:
    def test_get_missing(self, cache):
        assert cache.get("missing.md") is None

    def test_set_and_get(self, cache):
        cache.set("README.md", "hash123")
        assert cache.get("README.md") == "hash123"

    def test_save_and_reload(self, tmp_path):
        c1 = FileHashCache(tmp_path / "cache")
        c1.set("a.md", "h1")
        c1.set("b.md", "h2")
        c1.save()

        c2 = FileHashCache(tmp_path / "cache")
        assert c2.get("a.md") == "h1"
        assert c2.get("b.md") == "h2"

    def test_as_dict(self, cache):
        cache.set("a.md", "h1")
        cache.set("b.md", "h2")
        d = cache.as_dict()
        assert d == {"a.md": "h1", "b.md": "h2"}
