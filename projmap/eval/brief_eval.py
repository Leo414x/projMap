"""Brief A/B evaluation: compare projMap section-aware brief vs direct Claude."""

from __future__ import annotations

import json
import os
from pathlib import Path

from projmap.config import load_config


def eval_brief_vs_claude(
    project_root: str,
    docs_dir: str,
    question: str,
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
    max_files: int = 5,
) -> dict:
    """A/B test: projMap section-aware brief vs direct Claude with raw files.

    1. Load projMap brief from cache
    2. Pick top N files, concatenate, ask Claude same question
    3. Return both answers for human comparison
    """
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return {"ok": False, "error": "Not initialized"}

    root = Path(cfg.root).resolve()

    # Load projMap brief from cache
    cache_path = root / ".projmap" / "brief_sections_cache.json"
    projmap_brief = None
    projmap_has_edges = False
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
        projmap_brief = cache
        sections = cache.get("sections", {})
        for section_data in sections.values():
            items = section_data.get("items", [])
            for item in items:
                if item.get("related_nodes"):
                    projmap_has_edges = True
                    break

    # Load raw files for direct Claude comparison
    docs_path = Path(docs_dir)
    if not docs_path.is_absolute():
        docs_path = root / docs_dir

    raw_files = []
    if docs_path.exists():
        for f in sorted(docs_path.rglob("*.md"))[:max_files]:
            raw_files.append({"path": str(f.relative_to(root)), "content": f.read_text(encoding="utf-8")})

    # Ask Claude directly with raw files
    claude_direct = None
    claude_has_edges = False
    api_key = os.environ.get(api_key_env, "").strip()
    if api_key and raw_files:
        try:
            import anthropic

            files_text = "\n\n---\n\n".join(
                f"File: {f['path']}\n{f['content']}" for f in raw_files
            )
            prompt = (
                f"Based on these project documents, answer the following question.\n\n"
                f"Question: {question}\n\n"
                f"Documents:\n{files_text}"
            )

            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            claude_direct = message.content[0].text
        except Exception:
            claude_direct = None

    return {
        "ok": True,
        "question": question,
        "projmap_brief": projmap_brief,
        "claude_direct": claude_direct,
        "projmap_files_used": "all (via graph)",
        "claude_files_used": [f["path"] for f in raw_files],
        "projmap_has_edges": projmap_has_edges,
        "claude_has_edges": claude_has_edges,
    }
