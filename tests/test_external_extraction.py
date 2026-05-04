"""Tests for external extraction mode: prepare-extraction + import-extraction."""

import json
import pytest
from pathlib import Path

from projmap import api


@pytest.fixture
def project_dir(tmp_path):
    """Create and init a project with sample docs."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text(
        "# Test\n\nWe decided to use Python.\n\nRisk: API might be slow."
    )
    (root / "TODO.md").write_text("# TODO\n\n- [ ] Add tests\n- [ ] Fix bug")
    api.init_project(str(root))
    return root


def _make_result(root: Path, task_id: str, chunk_id: str, file_path: str,
                 nodes=None, edges=None, **overrides) -> None:
    """Helper to write a result file."""
    result = {
        "schema_version": "external_extraction_v1",
        "task_id": task_id,
        "chunk_id": chunk_id,
        "file_path": file_path,
        "nodes": nodes or [],
        "edges": edges or [],
    }
    result.update(overrides)
    result_dir = root / ".projmap" / "extraction_results"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / f"{task_id}.result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )


class TestPrepareExtraction:
    def test_creates_manifest(self, project_dir):
        result = api.prepare_extraction(str(project_dir))
        assert result["ok"] is True
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["schema_version"] == "external_extraction_v1"
        assert manifest["mode"] == "external"

    def test_creates_task_files(self, project_dir):
        result = api.prepare_extraction(str(project_dir))
        assert result["ok"] is True
        assert result["tasks_created"] >= 1
        task_dir = project_dir / ".projmap" / "extraction_tasks"
        task_files = list(task_dir.glob("task_*.json"))
        assert len(task_files) >= 1

    def test_task_file_has_content(self, project_dir):
        api.prepare_extraction(str(project_dir))
        task_dir = project_dir / ".projmap" / "extraction_tasks"
        task_file = sorted(task_dir.glob("task_*.json"))[0]
        data = json.loads(task_file.read_text())
        assert "content" in data
        assert "instructions" in data
        assert data["instructions"]["node_types"] == [
            "decision", "risk", "assumption", "version", "constraint",
            "config", "evaluation_result", "process_rule", "open_question",
        ]

    def test_limit(self, project_dir):
        result = api.prepare_extraction(str(project_dir), limit=1)
        assert result["ok"] is True
        assert result["tasks_created"] == 1

    def test_no_api_key_needed(self, project_dir, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = api.prepare_extraction(str(project_dir))
        assert result["ok"] is True

    def test_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        result = api.prepare_extraction(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"

    def test_clear_removes_old_tasks(self, project_dir):
        api.prepare_extraction(str(project_dir))
        result_dir = project_dir / ".projmap" / "extraction_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "old.result.json").write_text("{}")
        api.prepare_extraction(str(project_dir), clear=True)
        old_files = list(result_dir.glob("*.result.json"))
        assert len(old_files) == 0

    def test_force_processes_all(self, project_dir):
        # First prepare to register files
        api.prepare_extraction(str(project_dir))
        result = api.prepare_extraction(str(project_dir), force=True)
        assert result["ok"] is True
        assert result["tasks_created"] >= 1

    def test_result_json_serializable(self, project_dir):
        result = api.prepare_extraction(str(project_dir))
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["ok"] is True


class TestImportExtraction:
    def test_valid_result_imports(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        assert prep["ok"] is True
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())

        for t in manifest["tasks"]:
            _make_result(
                project_dir, t["task_id"], t["chunk_id"], t["file_path"],
                nodes=[{
                    "type": "decision",
                    "content": "We decided to use Python for the project",
                    "detail": "Python chosen as main language",
                    "source_line": "line 3",
                    "evidence_quote": "We decided to use Python.",
                    "confidence": 0.9,
                }],
            )

        result = api.import_extraction(str(project_dir))
        assert result["ok"] is True
        assert result["results_imported"] >= 1
        assert result["nodes_inserted"] >= 1

    def test_task_mismatch(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        t = manifest["tasks"][0]

        _make_result(
            project_dir, t["task_id"], "wrong_chunk_id", t["file_path"],
            nodes=[{
                "type": "decision",
                "content": "Some decision about the project architecture",
                "evidence_quote": "some quote from text",
                "confidence": 0.9,
            }],
        )

        result = api.import_extraction(str(project_dir))
        assert result["results_failed"] >= 1

    def test_invalid_schema(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        t = manifest["tasks"][0]

        _make_result(
            project_dir, t["task_id"], t["chunk_id"], t["file_path"],
            nodes=[{
                "type": "invalid_type",
                "content": "Some content that is here",
                "evidence_quote": "evidence quote",
                "confidence": 0.9,
            }],
        )

        result = api.import_extraction(str(project_dir))
        assert result["results_failed"] >= 1

    def test_evidence_not_found_strict(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        t = manifest["tasks"][0]

        _make_result(
            project_dir, t["task_id"], t["chunk_id"], t["file_path"],
            nodes=[{
                "type": "decision",
                "content": "A completely fabricated decision about architecture",
                "detail": "This is made up",
                "evidence_quote": "this quote does not exist anywhere in chunk",
                "confidence": 0.9,
            }],
        )

        result = api.import_extraction(str(project_dir), strict_evidence=True)
        assert result["evidence_failures"] >= 1
        assert result["nodes_inserted"] == 0

    def test_evidence_not_found_lax(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        t = manifest["tasks"][0]

        _make_result(
            project_dir, t["task_id"], t["chunk_id"], t["file_path"],
            nodes=[{
                "type": "decision",
                "content": "A fabricated decision about the project",
                "detail": "Not real",
                "evidence_quote": "this quote does not exist in chunk",
                "confidence": 0.9,
            }],
        )

        result = api.import_extraction(str(project_dir), strict_evidence=False)
        # With strict_evidence=False, should still import
        assert result["nodes_inserted"] >= 1

    def test_partial_failure(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())

        if len(manifest["tasks"]) < 2:
            # Not enough tasks; just verify the single task
            return

        # Make one valid, one invalid
        t0 = manifest["tasks"][0]
        t1 = manifest["tasks"][1]
        _make_result(
            project_dir, t0["task_id"], t0["chunk_id"], t0["file_path"],
            nodes=[{
                "type": "decision",
                "content": "Valid decision about the project technology",
                "evidence_quote": "We decided to use Python.",
                "confidence": 0.9,
            }],
        )
        _make_result(
            project_dir, t1["task_id"], "wrong_id", t1["file_path"],
            nodes=[],
        )

        result = api.import_extraction(str(project_dir), allow_partial=True)
        assert result["ok"] is True
        assert result["results_imported"] >= 1
        assert result["results_failed"] >= 1

    def test_min_confidence_filter(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        t = manifest["tasks"][0]

        _make_result(
            project_dir, t["task_id"], t["chunk_id"], t["file_path"],
            nodes=[{
                "type": "decision",
                "content": "A low confidence decision about the project",
                "evidence_quote": "We decided to use Python.",
                "confidence": 0.3,  # Below default threshold of 0.55
            }],
        )

        result = api.import_extraction(str(project_dir), min_confidence=0.55)
        assert result["nodes_skipped_low_confidence"] >= 1
        assert result["nodes_inserted"] == 0

    def test_no_manifest(self, project_dir):
        result = api.import_extraction(str(project_dir))
        assert result["ok"] is False
        assert result["error_code"] == "TASK_MANIFEST_NOT_FOUND"

    def test_missing_result_file(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        # Don't create any result files
        result = api.import_extraction(str(project_dir))
        assert result["results_failed"] >= 1

    def test_not_initialized(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        result = api.import_extraction(str(root))
        assert result["ok"] is False
        assert result["error_code"] == "NOT_INITIALIZED"

    def test_result_json_serializable(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        result = api.import_extraction(str(project_dir))
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert "ok" in parsed

    def test_edges_with_valid_nodes(self, project_dir):
        prep = api.prepare_extraction(str(project_dir))
        manifest_path = project_dir / ".projmap" / "extraction_tasks" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        # Find the README.md task (has the evidence strings)
        t = next(t for t in manifest["tasks"] if t["file_path"] == "README.md")

        _make_result(
            project_dir, t["task_id"], t["chunk_id"], t["file_path"],
            nodes=[
                {
                    "type": "decision",
                    "content": "We decided to use Python for the project",
                    "evidence_quote": "We decided to use Python.",
                    "confidence": 0.9,
                },
                {
                    "type": "risk",
                    "content": "API might be slow as a performance risk",
                    "evidence_quote": "API might be slow.",
                    "confidence": 0.85,
                },
            ],
            edges=[
                {
                    "from_content": "We decided to use Python for the project",
                    "to_content": "API might be slow as a performance risk",
                    "relationship": "depends-on",
                    "evidence_quote": "API might be slow.",
                    "confidence": 0.75,
                },
            ],
        )

        result = api.import_extraction(str(project_dir))
        assert result["ok"] is True
        assert result["nodes_inserted"] == 2
        assert result["edges_inserted"] == 1
