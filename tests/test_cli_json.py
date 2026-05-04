"""Tests for CLI JSON output via subprocess."""

import json
import subprocess
import pytest
from pathlib import Path


def _run_projmap(*args, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["projmap", *args],
        capture_output=True, text=True, cwd=cwd, timeout=10,
    )


@pytest.fixture
def project_dir(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Test\n\nWe decided to use Python.")
    _run_projmap("init", cwd=str(root))
    return root


class TestCLIJsonInit:
    def test_init_json(self, tmp_path):
        root = tmp_path / "new_proj"
        root.mkdir()
        proc = _run_projmap("init", "--format", "json", cwd=str(root))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["created"] is True


class TestCLIJsonScan:
    def test_scan_json(self, project_dir):
        proc = _run_projmap("scan", "--format", "json", cwd=str(project_dir))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["scanned_files"] >= 1

    def test_scan_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        proc = _run_projmap("scan", "--format", "json", cwd=str(root))
        assert proc.returncode == 1
        data = json.loads(proc.stdout)
        assert data["ok"] is False


class TestCLIJsonStatus:
    def test_status_json(self, project_dir):
        proc = _run_projmap("status", "--format", "json", cwd=str(project_dir))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert "files_tracked" in data

    def test_status_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        proc = _run_projmap("status", "--format", "json", cwd=str(root))
        assert proc.returncode == 1
        data = json.loads(proc.stdout)
        assert data["ok"] is False
        assert data["error_code"] == "NOT_INITIALIZED"


class TestCLIJsonRebuild:
    def test_rebuild_dry_run_json(self, project_dir):
        proc = _run_projmap("rebuild", "--dry-run", "--format", "json",
                           cwd=str(project_dir))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["dry_run"] is True
