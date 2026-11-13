"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

from typing import Any


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and evidence match against the gold metadata."""
    gold_source = question.get("gold_source_id")
    gold_page = question.get("gold_page")
    gold_quote = (question.get("evidence_quote") or "").strip().lower()
    hit_1 = False
    evidence_hit_3 = False

    for idx, hit in enumerate(hits[:3], start=1):
        hit_source = hit.get("document_id") or hit.get("metadata", {}).get("document_id")
        hit_page = hit.get("page") or hit.get("metadata", {}).get("page")
        hit_text = (hit.get("text") or "").lower()
        match_source = gold_source is not None and gold_source == hit_source
        match_page = gold_page is not None and gold_page == hit_page
        evidence_match = bool(gold_quote) and gold_quote in hit_text
        if idx == 1 and (match_source and match_page):
            hit_1 = True
        if (match_source and match_page) or evidence_match:
            evidence_hit_3 = True

    return {
        "question_id": question.get("id"),
        "split": question.get("split"),
        "hit_at_1": hit_1,
        "evidence_hit_at_3": evidence_hit_3,
        "top_hits": hits[:3],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    summary: dict[str, Any] = {}
    for trace in traces:
        strategy = trace["strategy"]
        split = trace["split"]
        key = (strategy, split)
        if key not in summary:
            summary[key] = {"count": 0, "hit_at_1": 0, "evidence_hit_at_3": 0}
        summary[key]["count"] += 1
        summary[key]["hit_at_1"] += int(trace["result"]["hit_at_1"])
        summary[key]["evidence_hit_at_3"] += int(trace["result"]["evidence_hit_at_3"])

    aggregated: dict[str, Any] = {}
    for (strategy, split), values in summary.items():
        count = max(values["count"], 1)
        aggregated[f"{strategy}:{split}"] = {
            "count": values["count"],
            "hit_at_1": values["hit_at_1"],
            "hit_at_1_rate": values["hit_at_1"] / count,
            "evidence_hit_at_3": values["evidence_hit_at_3"],
            "evidence_hit_at_3_rate": values["evidence_hit_at_3"] / count,
        }
    return aggregated
