"""Finding factory shared by all analyzers.

A finding is a single, explainable observation. Findings never represent a
final verdict: the risk engine combines them under a documented policy.
"""

from __future__ import annotations

from typing import Any

SEVERITY_WEIGHTS = {
    "info": 0.0,
    "low": 5.0,
    "medium": 12.0,
    "high": 22.0,
    "critical": 35.0,
}

SOURCE_LABELS = {
    "heuristic": "Rule-based heuristic",
    "static": "Static URL inspection",
    "http": "HTTP response observation",
    "html": "HTML inspection",
    "browser": "Isolated browser observation",
    "ml": "Machine-learning prediction",
    "external": "External reputation source",
    "community": "Community report (unverified)",
}


def finding(
    indicator_id: str,
    title: str,
    description: str,
    severity: str = "low",
    category: str = "general",
    source: str = "heuristic",
    weight: float | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if severity not in SEVERITY_WEIGHTS:
        severity = "low"
    return {
        "indicator_id": indicator_id,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "weight": float(SEVERITY_WEIGHTS[severity] if weight is None else weight),
        "evidence": evidence or {},
    }
