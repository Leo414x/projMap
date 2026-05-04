"""Tests for config.py: default config, write, load."""

import pytest
from pathlib import Path

from projmap.config import (
    ProjmapConfig,
    default_config,
    write_config,
    load_config,
    init_projmap,
)


@pytest.fixture
def tmp_root(tmp_path):
    return str(tmp_path)


class TestDefaultConfig:
    def test_default_values(self):
        cfg = default_config(".")
        assert cfg.project_name
        assert ".md" in cfg.include_extensions
        assert ".txt" in cfg.include_extensions
        assert "CLAUDE.md" in cfg.include_filenames
        assert ".git" in cfg.ignore_paths
        assert "node_modules" in cfg.ignore_paths
        assert cfg.include_git_log is True
        assert cfg.max_chars == 12000
        assert cfg.overlap_chars == 800

    def test_auto_name(self, tmp_root):
        cfg = default_config(tmp_root)
        assert cfg.project_name == Path(tmp_root).resolve().name


class TestWriteLoadConfig:
    def test_roundtrip(self, tmp_root):
        cfg = default_config(tmp_root)
        cfg.project_name = "test-project"
        write_config(cfg)

        loaded = load_config(tmp_root)
        assert loaded.project_name == "test-project"
        assert loaded.include_extensions == cfg.include_extensions
        assert loaded.ignore_paths == cfg.ignore_paths
        assert loaded.max_chars == cfg.max_chars

    def test_creates_directories(self, tmp_root):
        cfg = default_config(tmp_root)
        write_config(cfg)
        assert (Path(tmp_root) / ".projmap").is_dir()
        assert (Path(tmp_root) / ".projmap" / "cache").is_dir()
        assert (Path(tmp_root) / ".projmap" / "logs").is_dir()

    def test_config_file_exists(self, tmp_root):
        cfg = default_config(tmp_root)
        write_config(cfg)
        assert (Path(tmp_root) / ".projmap" / "config.toml").exists()

    def test_load_missing_raises(self, tmp_root):
        with pytest.raises(FileNotFoundError, match="projmap init"):
            load_config(str(Path(tmp_root) / "nonexistent"))


class TestInitProjmap:
    def test_init_creates_structure(self, tmp_root):
        proj_dir = init_projmap(tmp_root)
        assert proj_dir.exists()
        assert (proj_dir / "config.toml").exists()

    def test_init_no_git_disables_git_log(self, tmp_root):
        # tmp_root has no .git
        init_projmap(tmp_root)
        cfg = load_config(tmp_root)
        assert cfg.include_git_log is False
