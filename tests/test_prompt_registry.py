"""Tests for the prompt registry module."""

from __future__ import annotations

import json

import pytest

from projmap.prompts import load


class TestLoad:
    def test_load_v1(self):
        pack = load("v1")
        assert pack.version == "v1"
        assert len(pack.prompt_text) > 100
        assert "nodes" in pack.schema["properties"]
        assert "edges" in pack.schema["properties"]
        assert len(pack.examples) > 0

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load("nonexistent")

    def test_prompt_text_not_empty(self):
        pack = load("v1")
        assert pack.prompt_text.strip()
        assert "extract" in pack.prompt_text.lower()

    def test_schema_valid_json(self):
        pack = load("v1")
        serialized = json.dumps(pack.schema, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed == pack.schema

    def test_examples_have_good_and_bad(self):
        pack = load("v1")
        assert "good_examples" in pack.examples
        assert "bad_examples" in pack.examples
