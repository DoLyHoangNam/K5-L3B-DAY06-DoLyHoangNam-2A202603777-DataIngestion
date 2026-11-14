"""Evaluate retrieved evidence and preserve per-query traces."""
import re
import unicodedata
from typing import Any


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


def _is_gold_hit(hit: dict[str, Any], question: dict[str, Any]) -> bool:
    gold_doc = question["gold_source_id"]
    raw_pages = question["gold_page"]
    gold_pages = set(raw_pages if isinstance(raw_pages, list) else [raw_pages])
    if hit.get("document_id") != gold_doc:
        return False
    if hit.get("page") not in gold_pages:
        return False
    return _norm(question["evidence_quote"]) in _norm(hit.get("text", ""))


def evaluate_query(
    strategy: str,
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    applied_filter: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check source/page and gold evidence substring; keep full top-k trace."""
    formatted_hits = []
    for rank, h in enumerate(hits, 1):
        matched = _is_gold_hit(h, question)
        formatted_hits.append(
            {
                "rank": rank,
                "chunk_id": h["chunk_id"],
                "document_id": h["document_id"],
                "source": h["source"],
                "page": h["page"],
                "year": h.get("year"),
                "section": h.get("section"),
                "similarity": round(float(h["similarity"]), 6),
                "matched_gold": matched,
                "text": h["text"],
            }
        )

    hit_at_1 = bool(formatted_hits and formatted_hits[0]["matched_gold"])
    hit_at_3 = any(h["matched_gold"] for h in formatted_hits[:3])

    return {
        "strategy": strategy,
        "question_id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
        "question_filter": question.get("filter"),
        "applied_filter": applied_filter,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "top_k": formatted_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for t in traces:
        groups.setdefault((t["strategy"], t["split"]), []).append(t)

    summary: dict[str, Any] = {}
    for (strategy, split), items in sorted(groups.items()):
        n = len(items)
        h1 = sum(1 for x in items if x["hit_at_1"])
        h3 = sum(1 for x in items if x["hit_at_3"])
        summary[f"{strategy}_{split}"] = {
            "strategy": strategy,
            "split": split,
            "total": n,
            "hit1_count": h1,
            "hit1_ratio": f"{h1}/{n}",
            "hit1_pct": round(100.0 * h1 / n, 1) if n else 0.0,
            "hit3_count": h3,
            "hit3_ratio": f"{h3}/{n}",
            "hit3_pct": round(100.0 * h3 / n, 1) if n else 0.0,
        }
    return summary
