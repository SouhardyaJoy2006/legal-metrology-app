"""
bis_rag.retrieval.merge
=======================
Merges semantic and lexical candidate sets into a unified candidate pool.
"""

from __future__ import annotations


def merge_candidates(
    semantic_candidates: list[dict],
    lexical_candidates: list[dict],
) -> list[dict]:
    """
    Combine vector search results and lexical search results by standard ID.

    Maintains vector_similarity and lexical_score fields for each candidate.
    """
    merged: dict[int, dict] = {}

    for cand in semantic_candidates:
        sid = cand["id"]
        d = dict(cand)
        d["vector_similarity"] = float(d.get("vector_similarity") or 0.0)
        d["lexical_score"] = float(d.get("lexical_score") or 0.0)
        merged[sid] = d

    for cand in lexical_candidates:
        sid = cand["id"]
        lex_score = float(cand.get("lexical_score") or 0.0)
        if sid in merged:
            merged[sid]["lexical_score"] = max(merged[sid]["lexical_score"], lex_score)
        else:
            d = dict(cand)
            d["vector_similarity"] = float(d.get("vector_similarity") or 0.0)
            d["lexical_score"] = lex_score
            merged[sid] = d

    return list(merged.values())
