"""Tests for api.py: Python API functions and JSON compatibility."""

import json
import pytest
from pathlib import Path

from projmap import api


@pytest.fixture
def project_dir(tmp_path):
    """Create and init a minimal project."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Test\n\nWe decided to use Python.")
    (root / "TODO.md").write_text("# TODO\n\n- [ ] Add tests")
    api.init_project(str(root))
    return root


class TestInitProject:
    def test_init_creates_structure(self, tmp_path):
        root = tmp_path / "new_project"
        root.mkdir()
        result = api.init_project(str(root))
        assert result["ok"] is True
        assert result["created"] is True
        assert (root / ".projmap" / "config.toml").exists()

    def test_init_idempotent(self, tmp_path):
        root = tmp_path / "new_project"
        root.mkdir()
        r1 = api.init_project(str(root))
        r2 = api.init_project(str(root))
        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r2["created"] is False

    def test_init_force(self, tmp_path):
        root = tmp_path / "new_project"
        root.mkdir()
        api.init_project(str(root))
        result = api.init_project(str(root), force=True)
        assert result["ok"] is True
        assert result["created"] is True

    def test_init_result_json_serializable(self, tmp_path):
        root = tmp_path / "new_project"
        root.mkdir()
        result = api.init_project(str(root))
        serialized = json.dumps(result, ensure_ascii=False)
        assert "ok" in serialized


class TestScanProject:
    def test_scan_finds_files(self, project_dir):
        result = api.scan_project(str(project_dir))
        assert result["ok"] is True
        assert result["scanned_files"] >= 2
        assert result["new_files"] >= 2

    def test_scan_returns_files_list(self, project_dir):
        result = api.scan_project(str(project_dir))
        files = result["files"]
        paths = {f["path"] for f in files}
        assert "README.md" in paths

    def test_scan_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        result = api.scan_project(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"

    def test_scan_result_json_serializable(self, project_dir):
        result = api.scan_project(str(project_dir))
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["ok"] is True


class TestRebuildProject:
    def test_rebuild_missing_key(self, project_dir, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = api.rebuild_project(str(project_dir))
        assert result["ok"] is False
        assert result["error_code"] == "MISSING_API_KEY"

    def test_rebuild_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        result = api.rebuild_project(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"

    def test_rebuild_dry_run(self, project_dir):
        result = api.rebuild_project(str(project_dir), dry_run=True)
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert len(result.get("files_to_process", [])) > 0

    def test_rebuild_dry_run_no_llm(self, project_dir, monkeypatch):
        # dry_run should not need API key
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = api.rebuild_project(str(project_dir), dry_run=True)
        assert result["ok"] is True
        assert result["dry_run"] is True

    def test_rebuild_force(self, project_dir, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = api.rebuild_project(str(project_dir), dry_run=True, force=True)
        assert result["ok"] is True
        # force makes all files appear as changed
        assert result["force"] is True

    def test_rebuild_result_json_serializable(self, project_dir):
        result = api.rebuild_project(str(project_dir), dry_run=True)
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["ok"] is True


class TestGetStatus:
    def test_status_initialized(self, project_dir):
        result = api.get_status(str(project_dir))
        assert result["ok"] is True
        assert "files_tracked" in result
        assert "chunks" in result
        assert "nodes" in result
        assert "edges" in result

    def test_status_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        result = api.get_status(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"

    def test_status_json_serializable(self, project_dir):
        result = api.get_status(str(project_dir))
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["ok"] is True


class TestGetContext:
    def test_not_implemented(self, project_dir):
        result = api.get_context("some task", str(project_dir))
        assert result["ok"] is False
        assert result["status"] == "not_implemented"
