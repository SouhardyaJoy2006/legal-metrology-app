"""
bis_rag.retrieval.ranking
==========================
Metadata-aware candidate scoring and ranking layer.

Combines:
- Semantic vector similarity (BGE-M3)
- Lexical match score
- Lifecycle preference bonus (current vs superseded)
- Standard type intent bonus (Safety Standard, Code of Practice, Product Specification)
- Exact standard number match boost
"""

from __future__ import annotations

import re


DEFAULT_WEIGHTS = {
    "vector": 0.50,
    "lexical": 0.30,
    "current_bonus": 0.12,
    "type_bonus": 0.08,
    "exact_boost": 0.25,
}


def rank_candidates(
    candidates: list[dict],
    query: str,
    weights: dict | None = None,
) -> list[dict]:
    """
    Score and rank candidate standards using hybrid semantic+lexical similarity,
    lifecycle status, standard type alignment, and exact number matching.

    Returns a list of dicts sorted by relevance_score DESC.
    """
    if not candidates:
        return []

    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    cleaned_query = query.strip().lower()

    # Detect type intent from query
    safety_intent = bool(re.search(r"\b(safety|safe|hazard|protection|prevention)\b", cleaned_query))
    spec_intent   = bool(re.search(r"\b(specification|requirements|dimensions|size)\b", cleaned_query))
    code_intent   = bool(re.search(r"\b(code|practice|guideline|use|maintenance)\b", cleaned_query))

    ranked = []
    for cand in candidates:
        d = dict(cand)

        vec_sim  = float(d.get("vector_similarity") or 0.0)
        lex_score= float(d.get("lexical_score") or 0.0)
        is_curr  = bool(d.get("is_current"))
        std_type = (d.get("type_of_standard") or "").lower()
        std_num  = (d.get("standard_number") or "").lower()
        std_base = (d.get("standard_number_base") or "").lower()

        # 1. Base hybrid score
        score = (vec_sim * w["vector"]) + (lex_score * w["lexical"])

        # 2. Lifecycle current version bonus
        if is_curr:
            score += w["current_bonus"]

        # 3. Standard type intent alignment bonus
        if safety_intent and ("safety" in std_type or "code of practice" in std_type):
            score += w["type_bonus"]
        elif spec_intent and "specification" in std_type:
            score += w["type_bonus"]
        elif code_intent and "code of practice" in std_type:
            score += w["type_bonus"]

        # 4. Exact standard number query boost
        # e.g., query "IS 16810 Part 1" matches "is 16810 (part 1):2026"
        clean_num_digits = "".join(re.findall(r"\d+", std_num))
        clean_query_digits = "".join(re.findall(r"\d+", cleaned_query))

        if std_num in cleaned_query or (clean_query_digits and clean_query_digits in clean_num_digits):
            score += w["exact_boost"]

        final_score = min(1.0, max(0.0, score))
        d["relevance_score"] = final_score
        ranked.append(d)

    # Sort candidates by relevance_score DESC, then date_of_publish DESC
    ranked.sort(
        key=lambda x: (x["relevance_score"], str(x.get("date_of_publish") or "")),
        reverse=True,
    )

    return ranked
