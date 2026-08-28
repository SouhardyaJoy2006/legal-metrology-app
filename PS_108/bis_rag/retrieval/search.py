"""
bis_rag.retrieval.search
========================
High-level entry point for BIS standard retrieval.

Exposes:
    search_standards(query, top_k=8, retrieval_k=30, include_superseded=True) -> list[dict]
"""

from __future__ import annotations

import logging
from typing import Any

from bis_rag.db.connection import get_connection
from bis_rag.embeddings import get_embedder
from bis_rag.retrieval.semantic import semantic_search
from bis_rag.retrieval.lexical import lexical_search
from bis_rag.retrieval.merge import merge_candidates
from bis_rag.retrieval.lifecycle import resolve_lifecycle_and_families
from bis_rag.retrieval.ranking import rank_candidates

logger = logging.getLogger(__name__)


def search_standards(
    query: str,
    top_k: int = 8,
    retrieval_k: int = 30,
    include_superseded: bool = True,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Search BIS standards by natural language, standard number, or keyword.

    Parameters
    ----------
    query : str
        User search text (English or Hindi), e.g. "lifting chains", "IS 16810 Part 1".
    top_k : int
        Number of final recommendations to return (default: 8).
    retrieval_k : int
        Internal candidate pool size for hybrid retrieval (default: 30).
    include_superseded : bool
        If True, historical/superseded standards can be included in results (marked with is_current=False and latest_version pointer).
        If False, only current active standards are returned.
    weights : dict, optional
        Custom weights for vector, lexical, lifecycle, type, and exact match ranking signals.

    Returns
    -------
    list[dict]
        List of formatted result dictionaries ready for CLI or API consumption.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # Step 1: Query Embedding
    embedder = get_embedder()
    query_vec = embedder.embed_query(cleaned_query)

    with get_connection() as conn:
        # Step 2: Semantic Vector Search (30 candidates)
        sem_cands = semantic_search(query_vec, conn, retrieval_k=retrieval_k)

        # Step 3: Lexical / Exact Search (30 candidates)
        lex_cands = lexical_search(cleaned_query, conn, retrieval_k=retrieval_k)

        # Step 4: Candidate Merging
        merged_cands = merge_candidates(sem_cands, lex_cands)

        # Step 5: Standard Lifecycle Resolution & Family Grouping
        lifecycle_cands = resolve_lifecycle_and_families(merged_cands, conn)

        # Step 6: Metadata-Aware Ranking & Scoring
        ranked_cands = rank_candidates(lifecycle_cands, cleaned_query, weights=weights)

    # Step 7: Filter superseded if requested
    if not include_superseded:
        filtered = [c for c in ranked_cands if c.get("is_current")]
        # Fallback to ranked if all candidates were filtered
        results = filtered if filtered else ranked_cands
    else:
        results = ranked_cands

    # Step 8: Return top_k structured dictionaries
    top_results = results[:top_k]

    # Format result structure cleanly for consumers
    formatted = []
    for r in top_results:
        amendments_count = int(r.get("no_of_amendments") or 0)
        formatted.append({
            "id": r["id"],
            "standard_number": r["standard_number"],
            "standard_number_base": r.get("standard_number_base"),
            "title": r.get("title") or "",
            "relevance_score": round(float(r.get("relevance_score", 0.0)), 4),
            "relevance_percentage": round(float(r.get("relevance_score", 0.0)) * 100, 1),
            "type_of_standard": r.get("type_of_standard") or "N/A",
            "department": r.get("department") or "N/A",
            "committee": r.get("committee") or "N/A",
            "current_status": r.get("current_status") or "N/A",
            "is_current": bool(r.get("is_current")),
            "status_label": r.get("status_label") or "UNKNOWN",
            "date_of_publish": str(r.get("date_of_publish") or "N/A"),
            "supersedes": r.get("superseding_is_raw") or "None",
            "latest_version": r.get("latest_version"),
            "no_of_revisions": int(r.get("no_of_revisions") or 0),
            "no_of_amendments": amendments_count,
            "certification": r.get("certification") or "N/A",
            "ics_code": r.get("ics_code") or "N/A",
            "equivalent_standards": r.get("equivalent_standards") or "N/A",
            "detail_url": r.get("detail_url") or "",
        })

    return formatted
