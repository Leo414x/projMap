"""Tests for resolvers.py: time labels, visibility, module normalization, badges, formatters."""

import pytest

from projmap.resolvers import (
    CANONICAL_MODULES,
    MODULE_ALIASES,
    normalize_module,
    infer_module_from_path,
    infer_module_from_heading,
    resolve_project,
    resolve_version,
    resolve_time_label,
    resolve_time_value,
    resolve_sort_time,
    resolve_visibility,
    compute_display_priority,
    resolve_badges,
    format_type_label,
    format_module_label,
    format_project_version,
    format_status_label,
    resolve_status_severity,
    format_source_label,
    format_confidence_label,
    format_time_display,
    truncate_text,
    format_source_confidence,
    resolve_classification,
)


# ── Module Normalization ──────────────────────────────────────────

class TestNormalizeModule:
    def test_alias_decision_flow(self):
        assert normalize_module("Decision Flow") == ("decision_flow", 0.9)

    def test_alias_decision_flow_hyphen(self):
        assert normalize_module("decision-flow") == ("decision_flow", 0.9)

    def test_alias_side_monitoring(self):
        assert normalize_module("side monitoring") == ("decision_flow", 0.9)

    def test_alias_consensus(self):
        assert normalize_module("consensus") == ("decision_flow", 0.9)

    def test_alias_paper_shadow_slash(self):
        assert normalize_module("paper/shadow") == ("paper_shadow", 0.9)

    def test_alias_paper_shadow_hyphen(self):
        assert normalize_module("paper-shadow") == ("paper_shadow", 0.9)

    def test_alias_eval(self):
        assert normalize_module("eval") == ("evaluation", 0.9)

    def test_alias_oos(self):
        assert normalize_module("oos") == ("evaluation", 0.9)

    def test_alias_holdout(self):
        assert normalize_module("holdout") == ("evaluation", 0.9)

    def test_alias_train(self):
        assert normalize_module("train") == ("training", 0.9)

    def test_alias_walk_forward(self):
        assert normalize_module("walk forward") == ("training", 0.9)

    def test_alias_prompt(self):
        assert normalize_module("prompt") == ("prompt_engineering", 0.9)

    def test_canonical_direct(self):
        assert normalize_module("risk") == ("risk", 0.85)

    def test_canonical_storage(self):
        assert normalize_module("storage") == ("storage", 0.85)

    def test_unknown_gibberish(self):
        assert normalize_module("xyzzy123") == ("unknown", 0.3)

    def test_none_returns_unknown(self):
        assert normalize_module(None) == ("unknown", 0.0)

    def test_empty_returns_unknown(self):
        assert normalize_module("") == ("unknown", 0.0)

    def test_whitespace_returns_unknown(self):
        assert normalize_module("   ") == ("unknown", 0.0)

    def test_case_insensitive_alias(self):
        assert normalize_module("DECISION FLOW") == ("decision_flow", 0.9)

    def test_canonical_with_spaces(self):
        assert normalize_module("decision flow") == ("decision_flow", 0.9)

    def test_all_aliases_resolve_to_canonical(self):
        for alias, canonical in MODULE_ALIASES.items():
            result, conf = normalize_module(alias)
            assert result == canonical, f"Alias '{alias}' resolved to '{result}', expected '{canonical}'"
            assert conf == 0.9

    def test_all_canonical_modules_self_resolve(self):
        for mod in CANONICAL_MODULES:
            result, conf = normalize_module(mod)
            assert result == mod, f"Canonical '{mod}' resolved to '{result}'"
            assert conf >= 0.85  # alias hit gives 0.9, canonical gives 0.85


class TestInferModuleFromPath:
    def test_path_with_evaluation(self):
        mod, conf = infer_module_from_path("src/evaluation/metrics.py")
        assert mod == "evaluation"
        assert conf == 0.75

    def test_path_with_risk(self):
        mod, conf = infer_module_from_path("modules/risk/scoring.py")
        assert mod == "risk"

    def test_empty_path(self):
        assert infer_module_from_path("") == ("unknown", 0.0)

    def test_no_matching_segment(self):
        assert infer_module_from_path("src/utils/helpers.py") == ("unknown", 0.1)

    def test_windows_path(self):
        mod, conf = infer_module_from_path("src\\decision_flow\\core.py")
        assert mod == "decision_flow"


class TestInferModuleFromHeading:
    def test_heading_eval(self):
        assert infer_module_from_heading("eval") == ("evaluation", 0.65)

    def test_none_heading(self):
        assert infer_module_from_heading(None) == ("unknown", 0.0)

    def test_empty_heading(self):
        assert infer_module_from_heading("") == ("unknown", 0.0)

    def test_non_matching_heading(self):
        assert infer_module_from_heading("Introduction") == ("unknown", 0.05)


class TestResolveProject:
    def test_with_hint(self):
        assert resolve_project("Trading System") == ("Trading System", 0.85)

    def test_none_hint(self):
        assert resolve_project(None) == ("Unassigned Project", 0.1)

    def test_whitespace_hint(self):
        assert resolve_project("  Trading System  ") == ("Trading System", 0.85)


class TestResolveVersion:
    def test_with_hint(self):
        assert resolve_version("V13") == ("V13", 0.85)

    def test_extract_from_text(self):
        assert resolve_version(None, "The V13 evaluation framework") == ("V13", 0.5)

    def test_extract_from_text_lowercase(self):
        assert resolve_version(None, "using v8 features") == ("V8", 0.5)

    def test_no_version(self):
        assert resolve_version(None, "no version here") == ("-", 0.0)


# ── Time Label Resolver ──────────────────────────────────────────

class TestResolveTimeLabel:
    def test_explicit_doc_date_decided(self):
        assert resolve_time_label("explicit_doc_date", 0.9) == "Decided"

    def test_explicit_doc_date_low_confidence(self):
        assert resolve_time_label("explicit_doc_date", 0.5) == "Observed"

    def test_git_first_seen(self):
        assert resolve_time_label("git_first_seen", 0.7) == "First seen"

    def test_git_blame_line(self):
        assert resolve_time_label("git_blame_line", 0.75) == "First seen"

    def test_git_commit_date(self):
        assert resolve_time_label("git_commit_date", 0.8) == "First seen"

    def test_git_low_confidence(self):
        assert resolve_time_label("git_first_seen", 0.5) == "Observed"

    def test_file_modified_at(self):
        assert resolve_time_label("file_modified_at", 0.35) == "Observed"

    def test_file_created_at(self):
        assert resolve_time_label("file_created_at", 0.5) == "Observed"

    def test_extraction_time(self):
        assert resolve_time_label("extraction_time", 0.1) == "Observed"

    def test_content_changed(self):
        assert resolve_time_label("file_modified_at", 0.3, has_content_changed=True) == "Updated"

    def test_unknown_basis(self):
        assert resolve_time_label("unknown", 0.0) == "Observed"

    def test_none_basis(self):
        assert resolve_time_label(None, 0.0) == "Observed"


class TestResolveTimeValue:
    def test_decision_time(self):
        assert resolve_time_value("2026-05-03T00:00:00Z", None, None, None) == "2026-05-03"

    def test_first_seen_fallback(self):
        assert resolve_time_value(None, "2026-05-02T00:00:00Z", None, None) == "2026-05-02"

    def test_source_modified_fallback(self):
        assert resolve_time_value(None, None, None, "2026-05-01T00:00:00Z") == "2026-05-01"

    def test_extracted_at_fallback(self):
        assert resolve_time_value(None, None, "2026-04-30T00:00:00Z", None) == "2026-04-30"

    def test_all_none(self):
        assert resolve_time_value(None, None, None, None) == "unknown"


class TestResolveSortTime:
    def test_decision_time_first(self):
        assert resolve_sort_time("2026-05-03T00:00:00Z", "2026-05-02T00:00:00Z", None) == "2026-05-03T00:00:00Z"

    def test_first_seen_fallback(self):
        assert resolve_sort_time(None, "2026-05-02T00:00:00Z", None) == "2026-05-02T00:00:00Z"

    def test_all_empty(self):
        assert resolve_sort_time(None, None, None) == ""


# ── Visibility Resolver ──────────────────────────────────────────

class TestResolveVisibility:
    def test_decision_active_visible(self):
        vis, reason = resolve_visibility("decision", "active", 0.8, "evidence here")
        assert vis is True
        assert reason is None

    def test_superseded_hidden(self):
        vis, reason = resolve_visibility("decision", "superseded", 0.9, "evidence")
        assert vis is False
        assert "superseded" in reason

    def test_deprecated_hidden(self):
        vis, reason = resolve_visibility("decision", "deprecated", 0.9, "evidence")
        assert vis is False
        assert "deprecated" in reason

    def test_implementation_fact_hidden(self):
        vis, reason = resolve_visibility("implementation_fact", "active", 0.9, "evidence")
        assert vis is False
        assert "implementation_fact" in reason

    def test_raw_extraction_fragment_hidden(self):
        vis, reason = resolve_visibility("raw_extraction_fragment", "active", 0.9, "evidence")
        assert vis is False

    def test_low_confidence_hidden(self):
        vis, reason = resolve_visibility("decision", "active", 0.3, "evidence")
        assert vis is False
        assert reason == "low_confidence"

    def test_missing_evidence_hidden(self):
        vis, reason = resolve_visibility("decision", "active", 0.8, "")
        assert vis is False
        assert reason == "missing_evidence"

    def test_missing_evidence_none_hidden(self):
        vis, reason = resolve_visibility("decision", "active", 0.8, None)
        assert vis is False

    def test_low_impact_config_hidden(self):
        vis, reason = resolve_visibility("config", "active", 0.7, "evidence", display_priority=0.4)
        assert vis is False
        assert "config" in reason

    def test_high_impact_config_visible(self):
        vis, reason = resolve_visibility("config", "active", 0.9, "evidence", display_priority=0.7)
        assert vis is True

    def test_low_impact_eval_hidden(self):
        vis, reason = resolve_visibility("evaluation_result", "active", 0.7, "evidence", display_priority=0.5)
        assert vis is False
        assert "result" in reason

    def test_constraint_visible(self):
        vis, reason = resolve_visibility("constraint", "active", 0.8, "evidence")
        assert vis is True

    def test_risk_visible(self):
        vis, reason = resolve_visibility("risk", "active", 0.8, "evidence")
        assert vis is True

    def test_paper_only_visible(self):
        vis, reason = resolve_visibility("decision", "paper_only", 0.8, "evidence")
        assert vis is True


# ── Display Priority ─────────────────────────────────────────────

class TestComputeDisplayPriority:
    def test_decision_high_priority(self):
        p = compute_display_priority("decision", 0.9, 5)
        assert 0.5 < p <= 1.0

    def test_raw_fragment_low_priority(self):
        p = compute_display_priority("raw_extraction_fragment", 0.5, 0)
        assert p < 0.3

    def test_more_edges_higher_priority(self):
        p1 = compute_display_priority("decision", 0.8, 0)
        p2 = compute_display_priority("decision", 0.8, 10)
        assert p2 >= p1


# ── Badge Resolver ───────────────────────────────────────────────

class TestResolveBadges:
    def test_paper_only_badge(self):
        badges = resolve_badges("paper_only")
        assert "paper_only" in badges

    def test_diagnostic_only_badge(self):
        badges = resolve_badges("diagnostic_only")
        assert "diagnostic_only" in badges

    def test_low_time_confidence_badge(self):
        badges = resolve_badges("active", time_confidence=0.3)
        assert "low_time_confidence" in badges

    def test_high_time_no_badge(self):
        badges = resolve_badges("active", time_confidence=0.8)
        assert "low_time_confidence" not in badges

    def test_low_classification_badge(self):
        badges = resolve_badges("active", classification_confidence=0.4)
        assert "low_classification" in badges

    def test_unknown_module_badge(self):
        badges = resolve_badges("active", module="unknown")
        assert "unknown_module" in badges

    def test_missing_rationale_badge(self):
        badges = resolve_badges("active", has_rationale=False)
        assert "missing_rationale" in badges

    def test_has_rationale_no_badge(self):
        badges = resolve_badges("active", has_rationale=True)
        assert "missing_rationale" not in badges

    def test_source_verified_badge(self):
        badges = resolve_badges("active", source_confidence="verified")
        assert "source_verified" in badges

    def test_clean_node_no_badges(self):
        badges = resolve_badges(
            "active", time_confidence=0.9, classification_confidence=0.8,
            module="decision_flow", has_rationale=True, source_confidence="verified",
        )
        assert "missing_rationale" not in badges
        assert "low_time_confidence" not in badges
        assert "source_verified" in badges


# ── Formatters ───────────────────────────────────────────────────

class TestFormatTypeLabel:
    def test_decision(self):
        assert format_type_label("decision") == "Decision"

    def test_evaluation_result(self):
        assert format_type_label("evaluation_result") == "Evaluation Result"

    def test_unknown_type(self):
        assert format_type_label("some_new_type") == "Some New Type"


class TestFormatModuleLabel:
    def test_decision_flow(self):
        assert format_module_label("decision_flow") == "Decision Flow"

    def test_unknown(self):
        assert format_module_label("unknown") == "Unknown Module"

    def test_none(self):
        assert format_module_label(None) == "Unknown Module"


class TestFormatProjectVersion:
    def test_both(self):
        assert format_project_version("Trading System", "V13") == "Trading System / V13"

    def test_no_version(self):
        assert format_project_version("Trading System", None) == "Trading System"

    def test_no_project(self):
        assert format_project_version(None, "V13") == "Unassigned Project / V13"

    def test_neither(self):
        assert format_project_version(None, None) == "Unassigned Project"


class TestFormatStatusLabel:
    def test_active(self):
        assert format_status_label("active") == "Active"

    def test_paper_only(self):
        assert format_status_label("paper_only") == "Paper/Shadow Only"

    def test_none(self):
        assert format_status_label(None) == "Unknown"

    def test_unknown_status(self):
        assert format_status_label("custom_status") == "Custom Status"


class TestResolveStatusSeverity:
    def test_active(self):
        assert resolve_status_severity("active") == "info"

    def test_paper_only(self):
        assert resolve_status_severity("paper_only") == "warning"

    def test_superseded(self):
        assert resolve_status_severity("superseded") == "dim"

    def test_none(self):
        assert resolve_status_severity(None) == "warning"


class TestFormatSourceLabel:
    def test_with_line_range(self):
        assert format_source_label("docs/v13.md", 120, 145) == "docs/v13.md:120-145"

    def test_with_line_start_only(self):
        assert format_source_label("docs/v13.md", 88, None) == "docs/v13.md:88"

    def test_no_lines(self):
        assert format_source_label("docs/v13.md") == "docs/v13.md"

    def test_no_file(self):
        assert format_source_label(None) == "Source missing"

    def test_same_line_start_end(self):
        assert format_source_label("docs/v13.md", 88, 88) == "docs/v13.md:88"


class TestFormatConfidenceLabel:
    def test_high(self):
        assert format_confidence_label(0.9) == "High"

    def test_medium(self):
        assert format_confidence_label(0.7) == "Medium"

    def test_low(self):
        assert format_confidence_label(0.3) == "Low"

    def test_none(self):
        assert format_confidence_label(None) == "Unknown"

    def test_boundary_high(self):
        assert format_confidence_label(0.8) == "High"

    def test_boundary_medium(self):
        assert format_confidence_label(0.55) == "Medium"

    def test_just_below_medium(self):
        assert format_confidence_label(0.54) == "Low"


class TestFormatTimeDisplay:
    def test_normal(self):
        assert format_time_display("Decided", "2026-05-03") == "Decided · 2026-05-03"

    def test_unknown_time(self):
        assert format_time_display("Observed", "unknown") == "Observed"


class TestTruncateText:
    def test_short_text(self):
        assert truncate_text("Short text", 160) == "Short text"

    def test_long_text(self):
        long_text = "a" * 200
        result = truncate_text(long_text, 160)
        assert len(result) == 160
        assert result.endswith("...")

    def test_none(self):
        assert truncate_text(None, 160) == ""

    def test_empty(self):
        assert truncate_text("", 160) == ""


class TestFormatSourceConfidence:
    def test_verified(self):
        assert format_source_confidence("verified") == "Verified"

    def test_missing(self):
        assert format_source_confidence("missing") == "Missing"

    def test_none(self):
        assert format_source_confidence(None) == "Unverified"


# ── Classification Resolver ──────────────────────────────────────

class TestResolveClassification:
    def test_full_classification(self):
        result = resolve_classification(
            project_hint="Trading System",
            version_hint="V13",
            module_hint="decision flow",
        )
        assert result["project"] == "Trading System"
        assert result["version"] == "V13"
        assert result["module"] == "decision_flow"
        assert result["classification_confidence"] > 0.5

    def test_no_hints_uses_path(self):
        result = resolve_classification(
            source_path="src/evaluation/metrics.py",
        )
        assert result["module"] == "evaluation"
        assert result["classification_basis"] == "path"

    def test_unknown_module_when_low_conf(self):
        result = resolve_classification(
            module_hint="xyzzy_nonsense",
            source_path="random/file.py",
            source_heading="Introduction",
        )
        assert result["module"] == "unknown"

    def test_hint_takes_priority(self):
        result = resolve_classification(
            module_hint="risk",
            source_path="src/evaluation/metrics.py",
        )
        assert result["module"] == "risk"
        assert result["classification_basis"] == "llm_hint"
