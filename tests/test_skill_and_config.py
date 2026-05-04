"""Tests for skill installation, extraction config, and import config integration."""

import json
import pytest
from pathlib import Path

from projmap import api
from projmap.config import load_config, init_projmap


# ── Skill Installation Tests ───────────────────────────────────

@pytest.fixture
def project_dir(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Test\n\nWe use Python.")
    return root


class TestInstallSkill:
    def test_creates_file(self, project_dir):
        api.init_project(str(project_dir))
        result = api.install_skill_fn(str(project_dir))
        assert result["ok"] is True
        assert result["created"] is True
        skill_path = project_dir / ".agents" / "skills" / "projmap-memory" / "SKILL.md"
        assert skill_path.exists()

    def test_no_overwrite_without_force(self, project_dir):
        api.init_project(str(project_dir))
        api.install_skill_fn(str(project_dir))
        result = api.install_skill_fn(str(project_dir))
        assert result["ok"] is True
        assert result["created"] is False
        assert any("already exists" in w for w in result.get("warnings", []))

    def test_force_overwrites(self, project_dir):
        api.init_project(str(project_dir))
        api.install_skill_fn(str(project_dir))
        result = api.install_skill_fn(str(project_dir), force=True)
        assert result["ok"] is True
        assert result["created"] is True

    def test_print_only(self, project_dir):
        api.init_project(str(project_dir))
        result = api.install_skill_fn(str(project_dir), print_only=True)
        assert result["ok"] is True
        assert result["print_only"] is True
        assert "content" in result
        skill_path = project_dir / ".agents" / "skills" / "projmap-memory" / "SKILL.md"
        assert not skill_path.exists()

    def test_skill_content_has_triggers(self):
        content = api.SKILL_MD
        assert "更新 projMap 记忆" in content
        assert "refresh projMap memory" in content

    def test_skill_content_has_workflow(self):
        content = api.SKILL_MD
        assert "prepare-extraction" in content
        assert "import-extraction" in content
        assert "projmap status" in content

    def test_custom_path(self, project_dir):
        api.init_project(str(project_dir))
        result = api.install_skill_fn(str(project_dir), path=".claude/skills/projmap.md")
        assert result["ok"] is True
        assert (project_dir / ".claude" / "skills" / "projmap.md").exists()

    def test_result_json_serializable(self, project_dir):
        api.init_project(str(project_dir))
        result = api.install_skill_fn(str(project_dir))
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["ok"] is True


# ── Init Config Tests ──────────────────────────────────────────

class TestInitExtractionConfig:
    def test_init_writes_extraction_config(self, project_dir):
        api.init_project(str(project_dir))
        cfg = load_config(str(project_dir))
        assert cfg.extraction_mode == "external"
        assert cfg.strict_evidence is True

    def test_init_default_strict_evidence_true(self, project_dir):
        api.init_project(str(project_dir))
        result = api.init_project(str(project_dir), force=True)
        assert result["strict_evidence"] is True

    def test_init_no_strict_evidence(self, project_dir):
        result = api.init_project(str(project_dir), strict_evidence=False)
        assert result["strict_evidence"] is False
        cfg = load_config(str(project_dir))
        assert cfg.strict_evidence is False

    def test_init_install_skill_flag(self, project_dir):
        result = api.init_project(str(project_dir), install_skill=True)
        assert result["skill_installed"] is True
        assert result.get("skill_path")
        skill_path = project_dir / result["skill_path"]
        assert skill_path.exists()

    def test_config_toml_has_extraction_section(self, project_dir):
        api.init_project(str(project_dir))
        config_text = (project_dir / ".projmap" / "config.toml").read_text()
        assert "[extraction]" in config_text
        assert "strict_evidence" in config_text


# ── Import Config Integration Tests ────────────────────────────

class TestImportConfigIntegration:
    def test_import_uses_config_strict_evidence(self, project_dir):
        # Init with strict_evidence=True
        api.init_project(str(project_dir), strict_evidence=True)
        api.prepare_extraction(str(project_dir))

        # No explicit override → reads config (strict=True)
        result = api.import_extraction(str(project_dir))
        assert result["strict_evidence"] is True

    def test_import_override_to_false(self, project_dir):
        api.init_project(str(project_dir), strict_evidence=True)
        api.prepare_extraction(str(project_dir))

        # Explicit override to False
        result = api.import_extraction(str(project_dir), strict_evidence=False)
        assert result["strict_evidence"] is False

    def test_import_config_false_no_override(self, project_dir):
        api.init_project(str(project_dir), strict_evidence=False)
        api.prepare_extraction(str(project_dir))

        result = api.import_extraction(str(project_dir))
        assert result["strict_evidence"] is False

    def test_import_config_false_override_to_true(self, project_dir):
        api.init_project(str(project_dir), strict_evidence=False)
        api.prepare_extraction(str(project_dir))

        result = api.import_extraction(str(project_dir), strict_evidence=True)
        assert result["strict_evidence"] is True


# ── CLI Skill Tests ────────────────────────────────────────────

class TestCLISkillJson:
    def test_install_skill_json(self, project_dir):
        import subprocess
        api.init_project(str(project_dir))
        proc = subprocess.run(
            ["projmap", "install-skill", "--format", "json"],
            capture_output=True, text=True, cwd=str(project_dir), timeout=10,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True

    def test_init_with_install_skill_json(self, project_dir):
        import subprocess
        proc = subprocess.run(
            ["projmap", "init", "--install-skill", "--format", "json"],
            capture_output=True, text=True, cwd=str(project_dir), timeout=10,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data.get("skill_installed") is True
