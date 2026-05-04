"""Tests for the prompt registry module."""

from __future__ import annotations

import json

import pytest

from projmap.prompts import load, split_prompt_sections


class TestLegacyLoad:
    def test_load_v1_positional(self):
        pack = load("v1")
        assert pack.version == "v1"
        assert pack.purpose == "extraction"
        assert len(pack.prompt_text) > 100
        assert pack.schema is not None
        assert "nodes" in pack.schema["properties"]

    def test_load_v1_keyword(self):
        pack = load(version="v1")
        assert pack.purpose == "extraction"
        assert pack.version == "v1"


class TestMultiPurposeLoad:
    def test_load_enrichment(self):
        pack = load(purpose="enrichment")
        assert pack.purpose == "enrichment"
        assert "## System" in pack.prompt_text
        assert "## User template" in pack.prompt_text
        assert pack.schema is None
        assert pack.examples is None

    def test_load_enrichment_query(self):
        pack = load(purpose="enrichment_query")
        assert pack.purpose == "enrichment_query"
        assert "{query}" in pack.prompt_text

    def test_load_relation_discovery(self):
        pack = load(purpose="relation_discovery")
        assert pack.purpose == "relation_discovery"
        assert len(pack.prompt_text) > 100
        assert "supersedes" in pack.prompt_text

    def test_load_brief_section(self):
        pack = load(purpose="brief_section")
        assert pack.purpose == "brief_section"
        assert "{section_name}" in pack.prompt_text

    def test_load_brief_status(self):
        pack = load(purpose="brief_status")
        assert pack.purpose == "brief_status"
        assert "{sections_json}" in pack.prompt_text

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load(purpose="nonexistent")

    def test_examples_have_good_and_bad(self):
        pack = load("v1")
        assert pack.examples is not None
        assert "good_examples" in pack.examples
        assert "bad_examples" in pack.examples


class TestSplitPromptSections:
    def test_splits_system_and_user(self):
        pack = load(purpose="enrichment")
        system, user = split_prompt_sections(pack.prompt_text)
        assert len(system) > 50
        assert "analyst" in system.lower()
        assert "{count}" in user
        assert "{nodes_json}" in user

    def test_no_headers_returns_empty_system(self):
        text = "Just some plain text without headers."
        system, user = split_prompt_sections(text)
        assert system == ""
        assert user == text

    def test_brief_status_sections(self):
        pack = load(purpose="brief_status")
        system, user = split_prompt_sections(pack.prompt_text)
        assert len(system) > 20
        assert "{sections_json}" in user

    def test_relation_discovery_sections(self):
        pack = load(purpose="relation_discovery")
        system, user = split_prompt_sections(pack.prompt_text)
        assert "relation" in system.lower() or "relationship" in system.lower()
        assert "{nodes_json}" in user
