"""Deterministic resolvers for classification, time, visibility, and priority.

Formatting functions moved to display/formatters.py.
"""

from __future__ import annotations

import re

from projmap.schemas import TimeBasis

# ── Module Normalization ─────────────────────────────────────────

CANONICAL_MODULES = {
    "graph_foundation", "memory_extraction", "decision_context",
    "source_tracking", "time_inference", "external_extraction",
    "skill_workflow", "prompt_engineering", "import_validation",
    "storage", "query_context", "report_ui", "visualization", "cli",
    "training", "evaluation", "labeling", "decision_flow",
    "risk", "execution", "paper_shadow", "live_monitoring",
    "strategy_comparison", "feature_engineering", "modeling",
    "data_pipeline", "backtest",
    "product_strategy", "market_data", "social_signal",
    "analyst_rating", "trust_leaderboard", "llm_analysis",
    "dashboard", "commercialization", "user_workflow",
    "brand_positioning",
}

MODULE_ALIASES: dict[str, str] = {
    "decision flow": "decision_flow",
    "decision-flow": "decision_flow",
    "decision_flow": "decision_flow",
    "side monitoring": "decision_flow",
    "side-monitoring": "decision_flow",
    "side_monitoring": "decision_flow",
    "side monitoring tier": "decision_flow",
    "consensus": "decision_flow",
    "paper shadow": "paper_shadow",
    "paper/shadow": "paper_shadow",
    "paper-shadow": "paper_shadow",
    "shadow monitoring": "paper_shadow",
    "eval": "evaluation",
    "model eval": "evaluation",
    "model evaluation": "evaluation",
    "strategy eval": "evaluation",
    "strategy evaluation": "evaluation",
    "oos": "evaluation",
    "holdout": "evaluation",
    "train": "training",
    "model training": "training",
    "walk forward": "training",
    "walk-forward": "training",
    "source": "source_tracking",
    "source traceability": "source_tracking",
    "source tracking": "source_tracking",
    "decision time": "time_inference",
    "time inference": "time_inference",
    "timestamp": "time_inference",
    "prompt": "prompt_engineering",
    "prompts": "prompt_engineering",
    "extraction prompt": "prompt_engineering",
    "external mode": "external_extraction",
    "external extraction mode": "external_extraction",
    "codex extraction": "external_extraction",
}


def normalize_module(raw: str | None) -> tuple[str, float]:
    if not raw or not raw.strip():
        return "unknown", 0.0
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    if key in MODULE_ALIASES:
        return MODULE_ALIASES[key], 0.9
    canonical = key.replace(" ", "_")
    if canonical in CANONICAL_MODULES:
        return canonical, 0.85
    return "unknown", 0.3


def infer_module_from_path(path: str) -> tuple[str, float]:
    if not path:
        return "unknown", 0.0
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        canonical = part.lower().replace("-", "_").replace(" ", "_")
        if canonical in CANONICAL_MODULES:
            return canonical, 0.75
        key = part.lower().replace("-", " ").replace("_", " ")
        if key in MODULE_ALIASES:
            return MODULE_ALIASES[key], 0.7
    return "unknown", 0.1


def infer_module_from_heading(heading: str | None) -> tuple[str, float]:
    if not heading:
        return "unknown", 0.0
    key = heading.lower().strip()
    if key in MODULE_ALIASES:
        return MODULE_ALIASES[key], 0.65
    return "unknown", 0.05


def resolve_project(hint: str | None, path: str = "") -> tuple[str, float]:
    if hint:
        return hint.strip(), 0.85
    return "Unassigned Project", 0.1


def resolve_version(hint: str | None, text: str = "") -> tuple[str, float]:
    if hint:
        return hint.strip(), 0.85
    m = re.search(r"\b(V\d+(?:\.\d+)*)\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper(), 0.5
    return "-", 0.0


# ── Time Label Resolver ──────────────────────────────────────────

def resolve_time_label(basis: str | None, confidence: float = 0.0,
                       has_content_changed: bool = False) -> str:
    if basis == "explicit_doc_date" and confidence >= 0.75:
        return "Decided"
    if basis in {"git_first_seen", "git_blame_line", "git_commit_date"} and confidence >= 0.65:
        return "First seen"
    if has_content_changed:
        return "Updated"
    return "Observed"


def resolve_time_value(
    decision_time: str | None,
    first_seen_at: str | None,
    extracted_at: str | None,
    source_modified_at: str | None,
) -> str:
    for t in (decision_time, first_seen_at, source_modified_at, extracted_at):
        if t:
            s = str(t)
            return s[:10]
    return "unknown"


def resolve_sort_time(
    decision_time: str | None,
    first_seen_at: str | None,
    extracted_at: str | None,
) -> str:
    for t in (decision_time, first_seen_at, extracted_at):
        if t:
            return t
    return ""


# ── Visibility Resolver ──────────────────────────────────────────

HIDDEN_TYPES = {"implementation_fact", "raw_extraction_fragment"}
HIDDEN_STATUSES = {"superseded", "deprecated"}


def resolve_visibility(
    node_type: str,
    status: str | None,
    confidence: float | None,
    evidence_quote: str | None,
    display_priority: float = 1.0,
) -> tuple[bool, str | None]:
    if status and status in HIDDEN_STATUSES:
        return False, f"hidden_status:{status}"
    if node_type in HIDDEN_TYPES:
        return False, f"{node_type}_hidden_by_default"
    if confidence is not None and confidence < 0.45:
        return False, "low_confidence"
    if not evidence_quote:
        return False, "missing_evidence"
    if node_type == "config" and display_priority < 0.5:
        return False, "low_impact_config"
    if node_type == "evaluation_result" and display_priority < 0.55:
        return False, "low_impact_result"
    return True, None


# ── Display Priority ─────────────────────────────────────────────

TYPE_PRIORITY: dict[str, float] = {
    "decision": 1.0,
    "constraint": 0.95,
    "risk": 0.9,
    "version": 0.8,
    "evaluation_result": 0.7,
    "assumption": 0.65,
    "config": 0.5,
    "process_rule": 0.45,
    "implementation_fact": 0.3,
    "open_question": 0.25,
    "raw_extraction_fragment": 0.1,
}


def compute_display_priority(
    node_type: str,
    confidence: float = 0.5,
    edge_count: int = 0,
) -> float:
    base = TYPE_PRIORITY.get(node_type, 0.3)
    conf_factor = min(confidence, 1.0)
    edge_factor = min(edge_count / 10.0, 0.2)
    return round(base * 0.6 + conf_factor * 0.3 + edge_factor * 0.1, 3)


# ── Badge Resolver ───────────────────────────────────────────────

def resolve_badges(
    status: str | None,
    time_confidence: float = 0.0,
    classification_confidence: float = 0.0,
    module: str = "unknown",
    has_rationale: bool = False,
    source_confidence: str | None = None,
) -> list[str]:
    badges: list[str] = []
    if status == "paper_only":
        badges.append("paper_only")
    if status == "diagnostic_only":
        badges.append("diagnostic_only")
    if (time_confidence or 0.0) < 0.5:
        badges.append("low_time_confidence")
    if classification_confidence < 0.6:
        badges.append("low_classification")
    if module == "unknown":
        badges.append("unknown_module")
    if not has_rationale:
        badges.append("missing_rationale")
    if source_confidence == "verified":
        badges.append("source_verified")
    return badges


# ── Classification Resolver ──────────────────────────────────────

def resolve_classification(
    project_hint: str | None = None,
    version_hint: str | None = None,
    module_hint: str | None = None,
    text: str = "",
    source_path: str = "",
    source_heading: str | None = None,
) -> dict:
    project, project_conf = resolve_project(project_hint, source_path)
    version, version_conf = resolve_version(version_hint, text)

    module_from_hint, hint_conf = normalize_module(module_hint)
    module_from_path, path_conf = infer_module_from_path(source_path)
    module_from_heading, heading_conf = infer_module_from_heading(source_heading)

    candidates = [
        (module_from_hint, hint_conf, "llm_hint"),
        (module_from_path, path_conf, "path"),
        (module_from_heading, heading_conf, "heading"),
    ]

    module, module_conf, basis = max(candidates, key=lambda x: x[1])

    if module_conf < 0.5:
        module = "unknown"

    return {
        "project": project,
        "version": version,
        "module": module,
        "classification_confidence": round(min(project_conf, version_conf, module_conf), 3),
        "classification_basis": basis,
    }
