"""Display formatters: convert internal values to human-readable labels."""

from __future__ import annotations

# ── Label Constants (used by formatters) ───────────────────────────

TYPE_LABELS: dict[str, str] = {
    "decision": "Decision",
    "constraint": "Constraint",
    "assumption": "Assumption",
    "risk": "Risk",
    "version": "Version",
    "config": "Config",
    "implementation_fact": "Implementation Fact",
    "evaluation_result": "Evaluation Result",
    "process_rule": "Process Rule",
    "open_question": "Open Question",
    "raw_extraction_fragment": "Raw Fragment",
}

STATUS_LABELS: dict[str, str] = {
    "active": "Active",
    "paper_only": "Paper/Shadow Only",
    "diagnostic_only": "Diagnostic Only",
    "frozen": "Frozen",
    "superseded": "Superseded",
    "deprecated": "Deprecated",
    "unknown": "Unknown",
}

STATUS_SEVERITY: dict[str, str] = {
    "active": "info",
    "paper_only": "warning",
    "diagnostic_only": "warning",
    "frozen": "info",
    "superseded": "dim",
    "deprecated": "dim",
    "unknown": "warning",
}


# ── Formatters ────────────────────────────────────────────────────

def format_type_label(node_type: str) -> str:
    return TYPE_LABELS.get(node_type, node_type.replace("_", " ").title())


def format_module_label(module: str | None) -> str:
    if not module or module == "unknown":
        return "Unknown Module"
    return module.replace("_", " ").title()


def format_project_version(project: str | None, version: str | None) -> str:
    p = project or "Unassigned Project"
    v = version or "-"
    if v == "-":
        return p
    return f"{p} / {v}"


def format_status_label(status: str | None) -> str:
    if not status:
        return "Unknown"
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def resolve_status_severity(status: str | None) -> str:
    if not status:
        return "warning"
    return STATUS_SEVERITY.get(status, "warning")


def format_source_label(
    source_file: str | None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    if not source_file:
        return "Source missing"
    if line_start and line_end and line_start != line_end:
        return f"{source_file}:{line_start}-{line_end}"
    if line_start:
        return f"{source_file}:{line_start}"
    return source_file


def format_confidence_label(confidence: float | None) -> str:
    if confidence is None:
        return "Unknown"
    if confidence >= 0.8:
        return "High"
    if confidence >= 0.55:
        return "Medium"
    return "Low"


def format_time_display(time_label: str, time_value: str) -> str:
    if time_value == "unknown":
        return time_label
    return f"{time_label} · {time_value}"


def truncate_text(text: str | None, max_len: int = 160) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def format_source_confidence(confidence: str | None) -> str:
    if confidence == "verified":
        return "Verified"
    if confidence == "missing":
        return "Missing"
    return "Unverified"
