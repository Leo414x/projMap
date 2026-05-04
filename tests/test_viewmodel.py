"""Tests for viewmodel.py: row builder, table viewmodel, no-null renderer, legacy migration."""

import json
import pytest
from pathlib import Path

from projmap.viewmodel import build_row, build_table_viewmodel, RowViewModel


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "v5"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def load_fixture_list(name: str) -> list:
    return json.loads((FIXTURES_DIR / name).read_text())


# ── Row Builder ──────────────────────────────────────────────────

class TestBuildRow:
    def test_full_decision_node(self):
        node = load_fixture("node_decision_full.json")
        source = load_fixture("source_verified.json")
        edges = load_fixture_list("edges_related.json")
        edge_counts = {"limits": 1, "depends-on": 1}

        row = build_row(node, source, edge_counts, edges)

        assert row.node_id == "dec_full_001"
        assert row.type == "decision"
        assert row.type_label == "Decision"
        assert row.project == "Trading System"
        assert row.version == "V13"
        assert row.project_version_label == "Trading System / V13"
        assert row.module == "decision_flow"
        assert row.module_label == "Decision Flow"
        assert row.title == "V13 Section 8.3 approved for Paper/Shadow monitoring only"
        assert row.status == "paper_only"
        assert row.status_label == "Paper/Shadow Only"
        assert row.status_severity == "warning"
        assert row.time_label == "Decided"
        assert row.time_value == "2026-05-03"
        assert row.time_display == "Decided · 2026-05-03"
        assert row.time_confidence == 0.9
        assert row.time_confidence_label == "High"
        assert row.source_label == "docs/v13_review.md:120-145"
        assert row.source_confidence_label == "Verified"
        assert row.confidence == 0.87
        assert row.confidence_label == "High"
        assert row.is_default_visible is True
        assert row.hidden_reason is None
        assert "paper_only" in row.badges
        assert row.related_counts == edge_counts
        assert row.detail_rationale == node["rationale"]
        assert row.detail_evidence_quote == source["evidence_quote"]

    def test_node_without_source(self):
        node = load_fixture("node_decision_full.json")
        row = build_row(node, None)

        assert row.node_id == "dec_full_001"
        assert row.source_label == "docs/v13_review.md:120-145"
        assert row.source_confidence_label == "Unverified"

    def test_legacy_summary_only_node(self):
        node = load_fixture("node_legacy_summary_only.json")
        row = build_row(node, None)

        # Title falls back to content
        assert "Tier 3 thresholds" in row.title
        assert row.module == "unknown"
        assert row.module_label == "Unknown Module"
        assert row.time_label == "Observed"
        assert row.is_default_visible is False  # missing evidence

    def test_missing_source_node(self):
        node = load_fixture("node_missing_source.json")
        row = build_row(node, None)

        assert row.source_label == "Source missing"
        assert row.is_default_visible is False  # missing evidence

    def test_low_time_confidence_node(self):
        node = load_fixture("node_low_time_confidence.json")
        row = build_row(node, None)

        assert row.time_label == "Observed"
        assert row.time_confidence < 0.5
        assert row.time_confidence_label == "Low"
        assert "low_time_confidence" in row.badges

    def test_superseded_node_hidden(self):
        node = load_fixture("node_superseded.json")
        row = build_row(node, None)

        assert row.is_default_visible is False
        assert row.hidden_reason is not None
        assert "superseded" in row.hidden_reason

    def test_implementation_fact_hidden(self):
        node = load_fixture("node_implementation_fact.json")
        row = build_row(node, None)

        assert row.is_default_visible is False
        assert "implementation_fact" in row.hidden_reason

    def test_rationale_short_truncated(self):
        node = load_fixture("node_decision_full.json")
        node["rationale"] = "A" * 200
        row = build_row(node)
        assert len(row.rationale_short) == 160
        assert row.rationale_short.endswith("...")

    def test_missing_rationale_fallback(self):
        node = load_fixture("node_decision_full.json")
        node["rationale"] = None
        row = build_row(node)
        assert row.rationale_short == "Missing rationale"

    def test_missing_context_fallback(self):
        node = load_fixture("node_decision_full.json")
        node["context"] = None
        row = build_row(node)
        assert row.context_short == "Missing context"

    def test_missing_scope_fallback(self):
        node = load_fixture("node_decision_full.json")
        node["scope"] = None
        row = build_row(node)
        assert row.scope_short == "Scope not specified"

    def test_timeline_bucket(self):
        node = load_fixture("node_decision_full.json")
        row = build_row(node)
        assert row.timeline_bucket == "2026-05"

    def test_schema_version(self):
        node = load_fixture("node_decision_full.json")
        row = build_row(node)
        assert row.schema_version == "v5"


class TestBuildRowFallbacks:
    """Test that build_row handles every missing field gracefully."""

    def test_minimal_node(self):
        node = {"id": "min_001", "content": "A valid minimal node content here."}
        row = build_row(node)

        assert row.node_id == "min_001"
        assert row.type == "raw_extraction_fragment"
        assert row.type_label == "Raw Fragment"
        assert row.project == "Unassigned Project"
        assert row.version == "-"
        assert row.module == "unknown"
        assert row.module_label == "Unknown Module"
        assert row.status == "unknown"
        assert row.status_label == "Unknown"
        assert row.time_label == "Observed"
        assert row.source_label == "Source missing"

    def test_node_with_only_content(self):
        node = {"id": "c_001", "content": "This is the only field."}
        row = build_row(node)
        assert row.title == "This is the only field."
        assert row.summary == "This is the only field."


# ── No-null Renderer ─────────────────────────────────────────────

class TestNoNullRenderer:
    """Renderer must never output null / None / undefined / nan / NaT."""

    FORBIDDEN = ["null", "None", "undefined", "nan", "NaT"]

    def test_full_node_no_null(self):
        node = load_fixture("node_decision_full.json")
        source = load_fixture("source_verified.json")
        row = build_row(node, source)
        output = _render_row(row)
        for token in self.FORBIDDEN:
            assert token not in output, f"Found forbidden token '{token}' in output"

    def test_legacy_node_no_null(self):
        node = load_fixture("node_legacy_summary_only.json")
        row = build_row(node, None)
        output = _render_row(row)
        for token in self.FORBIDDEN:
            assert token not in output, f"Found forbidden token '{token}' in output"

    def test_missing_source_no_null(self):
        node = load_fixture("node_missing_source.json")
        row = build_row(node, None)
        output = _render_row(row)
        for token in self.FORBIDDEN:
            assert token not in output, f"Found forbidden token '{token}' in output"

    def test_minimal_node_no_null(self):
        node = {"id": "x", "content": "Minimal content for testing."}
        row = build_row(node)
        output = _render_row(row)
        for token in self.FORBIDDEN:
            assert token not in output, f"Found forbidden token '{token}' in output"

    def test_table_viewmodel_no_null(self):
        node = load_fixture("node_decision_full.json")
        row = build_row(node)
        vm = build_table_viewmodel([row])
        json_str = json.dumps(vm, default=str)
        for token in self.FORBIDDEN:
            assert token not in json_str, f"Found forbidden token '{token}' in table ViewModel JSON"


def _render_row(row: RowViewModel) -> str:
    """Simulate rendering a row to string (like a CLI table)."""
    parts = [
        row.node_id,
        row.type_label,
        row.project_version_label,
        row.module_label,
        row.title,
        row.status_label,
        row.time_display,
        row.source_label,
        row.confidence_label,
        row.rationale_short,
        row.context_short,
        row.scope_short,
        row.time_confidence_label,
        row.source_confidence_label,
        row.classification_confidence_label,
        str(row.hidden_reason or ""),
    ]
    return " | ".join(parts)


# ── Table ViewModel ──────────────────────────────────────────────

class TestBuildTableViewModel:
    def test_default_columns(self):
        node = load_fixture("node_decision_full.json")
        source = load_fixture("source_verified.json")
        row = build_row(node, source)
        vm = build_table_viewmodel([row])

        assert vm["default_columns"] == [
            "time_display",
            "project_version_label",
            "module_label",
            "type_label",
            "title",
            "status_label",
            "source_label",
        ]

    def test_filters_hidden_by_default(self):
        nodes = [
            load_fixture("node_decision_full.json"),
            load_fixture("node_superseded.json"),
        ]
        rows = [build_row(n) for n in nodes]
        vm = build_table_viewmodel(rows, include_hidden=False)

        # Only the non-superseded node should appear
        assert vm["summary"]["visible_rows"] == 1
        assert vm["rows"][0]["node_id"] == "dec_full_001"

    def test_include_hidden_shows_all(self):
        nodes = [
            load_fixture("node_decision_full.json"),
            load_fixture("node_superseded.json"),
        ]
        rows = [build_row(n) for n in nodes]
        vm = build_table_viewmodel(rows, include_hidden=True)

        assert vm["summary"]["visible_rows"] == 2

    def test_empty_rows(self):
        vm = build_table_viewmodel([])
        assert vm["summary"]["visible_rows"] == 0
        assert vm["rows"] == []

    def test_sorted_by_sort_time_desc(self):
        n1 = load_fixture("node_decision_full.json")
        n2 = load_fixture("node_superseded.json")
        rows = [build_row(n1), build_row(n2)]
        vm = build_table_viewmodel(rows, include_hidden=True)

        # n1 has sort_time 2026-05-03, n2 has 2026-03-01
        assert vm["rows"][0]["node_id"] == "dec_full_001"

    def test_view_type(self):
        vm = build_table_viewmodel([])
        assert vm["view_type"] == "decision_table"

    def test_group_by_default(self):
        vm = build_table_viewmodel([])
        assert vm["group_by"] == ["project", "version", "module"]


# ── Default Visibility Integration ───────────────────────────────

class TestDefaultVisibilityIntegration:
    def test_constraint_visible(self):
        node = {"id": "c1", "type": "constraint", "content": "Must not exceed risk limit for position sizing.",
                "status": "active", "confidence": 0.9, "evidence_quote": "risk limit constraint"}
        row = build_row(node)
        assert row.is_default_visible is True

    def test_risk_visible(self):
        node = {"id": "r1", "type": "risk", "content": "API dependency is a risk factor for production.",
                "status": "active", "confidence": 0.8, "evidence_quote": "API risk"}
        row = build_row(node)
        assert row.is_default_visible is True

    def test_assumption_active_visible(self):
        node = {"id": "a1", "type": "assumption", "content": "We assume the data pipeline is reliable.",
                "status": "active", "confidence": 0.7, "evidence_quote": "data pipeline assumption"}
        row = build_row(node)
        assert row.is_default_visible is True

    def test_config_low_impact_hidden(self):
        node = {"id": "cfg1", "type": "config", "content": "Log level is set to DEBUG in development.",
                "status": "active", "confidence": 0.6, "evidence_quote": "log level config"}
        row = build_row(node)
        # display_priority for config is 0.5 * 0.6 + ... = low
        assert row.is_default_visible is False

    def test_low_confidence_hidden(self):
        node = {"id": "low1", "type": "decision", "content": "Possibly relevant decision with low confidence.",
                "status": "active", "confidence": 0.3, "evidence_quote": "some evidence"}
        row = build_row(node)
        assert row.is_default_visible is False
        assert row.hidden_reason == "low_confidence"


# ── Include Hidden Filter ────────────────────────────────────────

class TestIncludeHiddenFilter:
    def test_query_without_include_hidden(self):
        nodes = [
            load_fixture("node_decision_full.json"),
            load_fixture("node_superseded.json"),
            load_fixture("node_implementation_fact.json"),
        ]
        rows = [build_row(n) for n in nodes]
        vm = build_table_viewmodel(rows, include_hidden=False)

        visible_ids = {r["node_id"] for r in vm["rows"]}
        assert "dec_full_001" in visible_ids
        assert "super_001" not in visible_ids
        assert "impl_001" not in visible_ids

    def test_query_with_include_hidden(self):
        nodes = [
            load_fixture("node_decision_full.json"),
            load_fixture("node_superseded.json"),
            load_fixture("node_implementation_fact.json"),
        ]
        rows = [build_row(n) for n in nodes]
        vm = build_table_viewmodel(rows, include_hidden=True)

        visible_ids = {r["node_id"] for r in vm["rows"]}
        assert "dec_full_001" in visible_ids
        assert "super_001" in visible_ids
        assert "impl_001" in visible_ids
