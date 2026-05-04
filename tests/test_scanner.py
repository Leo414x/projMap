"""Tests for scanner.py: file discovery, ignore rules, hash detection."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from projmap.config import ProjmapConfig
from projmap.scanner import scan_files


FIXTURES = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture
def sample_cfg():
    return ProjmapConfig(
        root=str(FIXTURES),
        include_git_log=False,
    )


class TestScanFiles:
    def test_finds_md_files(self, sample_cfg):
        records = scan_files(sample_cfg)
        paths = {r.path for r in records}
        assert "README.md" in paths
        assert "TODO.md" in paths
        assert "CLAUDE.md" in paths

    def test_finds_nested_docs(self, sample_cfg):
        records = scan_files(sample_cfg)
        paths = {r.path for r in records}
        # Path separator varies by OS, check both
        assert any("handoff.md" in p for p in paths)

    def test_ignores_node_modules(self, sample_cfg):
        records = scan_files(sample_cfg)
        paths = {r.path for r in records}
        assert not any("node_modules" in p for p in paths)

    def test_ignores_git(self, sample_cfg):
        records = scan_files(sample_cfg)
        paths = {r.path for r in records}
        assert not any(".git" in p for p in paths)

    def test_all_new_without_known(self, sample_cfg):
        records = scan_files(sample_cfg)
        assert all(r.status == "new" for r in records)

    def test_detects_unchanged(self, sample_cfg):
        # First scan to get hashes
        records1 = scan_files(sample_cfg)
        known = {r.path: r.content_hash for r in records1}
        # Second scan should show unchanged
        records2 = scan_files(sample_cfg, known)
        assert all(r.status == "unchanged" for r in records2)

    def test_detects_changed(self, sample_cfg, tmp_path):
        # Create a copy of fixture with modification
        import shutil
        root = tmp_path / "project"
        shutil.copytree(FIXTURES, root)

        cfg = ProjmapConfig(root=str(root), include_git_log=False)
        records1 = scan_files(cfg)
        known = {r.path: r.content_hash for r in records1}

        # Modify a file
        (root / "README.md").write_text("# Modified content\n\nNew content here.")
        records2 = scan_files(cfg, known)

        readme = [r for r in records2 if r.path == "README.md"][0]
        assert readme.status == "changed"

    def test_file_record_fields(self, sample_cfg):
        records = scan_files(sample_cfg)
        readme = [r for r in records if r.path == "README.md"][0]
        assert readme.file_type == "md"
        assert readme.size_bytes > 0
        assert readme.content_hash
        assert readme.content

    def test_ignores_binary_extensions(self, tmp_path):
        # Create files with ignored extensions
        (tmp_path / "data.parquet").write_bytes(b"fake")
        (tmp_path / "image.png").write_bytes(b"fake")
        (tmp_path / "doc.md").write_text("hello")

        cfg = ProjmapConfig(root=str(tmp_path), include_git_log=False)
        records = scan_files(cfg)
        paths = {r.path for r in records}
        assert "doc.md" in paths
        assert "data.parquet" not in paths
        assert "image.png" not in paths
