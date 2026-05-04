"""Tests for brief section generation."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from projmap import api


@pytest.fixture
def project_dir(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text(
        "# Test\n\nDecision: Use Python for backend.\nRisk: API latency may be high."
    )
    api.init_project(str(root))
    return root


class TestPrepareBriefSectionTasks:
    def test_creates_manifest_and_prompts(self, project_dir):
        from projmap.report.llm_enricher import prepare_brief_section_tasks
        result = prepare_brief_section_tasks(str(project_dir))
        assert result["ok"] is True
        assert result["sections_prepared"] == 3

        task_dir = project_dir / ".projmap" / "brief_section_tasks"
        assert (task_dir / "manifest.json").exists()
        assert (task_dir / "prompt.md").exists()
        assert (task_dir / "status_prompt.md").exists()
        assert (task_dir / "constraints.json").exists()
        assert (task_dir / "decisions.json").exists()
        assert (task_dir / "risks.json").exists()

    def test_not_initialized(self, tmp_path):
        from projmap.report.llm_enricher import prepare_brief_section_tasks
        root = tmp_path / "empty"
        root.mkdir()
        result = prepare_brief_section_tasks(str(root))
        assert result["ok"] is False


class TestImportBriefSectionResults:
    def test_no_manifest(self, project_dir):
        from projmap.report.llm_enricher import import_brief_section_results
        result = import_brief_section_results(str(project_dir))
        assert result["ok"] is False

    def test_import_with_results(self, project_dir):
        from projmap.report.llm_enricher import (
            prepare_brief_section_tasks,
            import_brief_section_results,
        )
        prepare_brief_section_tasks(str(project_dir))

        result_dir = project_dir / ".projmap" / "brief_section_results"
        result_dir.mkdir(parents=True, exist_ok=True)

        for section in ["constraints", "decisions", "risks"]:
            data = {
                "section_summary": f"Test {section} summary",
                "items": [{"node_id": "test", "headline": "Test", "detail": "Detail",
                           "status": "active", "related_nodes": []}],
            }
            (result_dir / f"{section}.result.json").write_text(
                json.dumps(data, ensure_ascii=False)
            )

        result = import_brief_section_results(str(project_dir))
        assert result["ok"] is True
        assert result["sections_imported"] == 3

        cache_path = project_dir / ".projmap" / "brief_sections_cache.json"
        assert cache_path.exists()
        cache = json.loads(cache_path.read_text())
        assert "sections" in cache
        assert "current_status" in cache


class TestLoadCachedBriefSections:
    def test_no_cache(self, project_dir):
        from projmap.report.llm_enricher import load_cached_brief_sections
        result = load_cached_brief_sections(str(project_dir))
        assert result is None

    def test_with_cache(self, project_dir):
        from projmap.report.llm_enricher import load_cached_brief_sections
        cache_path = project_dir / ".projmap" / "brief_sections_cache.json"
        cache_data = {"sections": {"decisions": {"items": []}}, "current_status": {"current_status": "ok"}}
        cache_path.write_text(json.dumps(cache_data))
        result = load_cached_brief_sections(str(project_dir))
        assert result is not None
        assert "sections" in result
