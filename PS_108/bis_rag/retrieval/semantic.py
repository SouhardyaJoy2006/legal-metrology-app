"""
bis_rag.retrieval.semantic
===========================
Semantic vector retrieval using BGE-M3 embeddings and pgvector cosine distance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg


_SEMANTIC_SEARCH_SQL = """
SELECT
    s.id,
    s.standard_number,
    s.standard_number_base,
    s.title,
    s.date_of_publish,
    s.type_of_standard,
    s.degree_of_equivalence,
    s.current_status,
    s.lifecycle_path,
    s.detail_url,
    s.department,
    s.committee,
    s.language,
    s.reaffirmation_year,
    s.member_secretary,
    s.no_of_revisions,
    s.no_of_amendments,
    s.superseding_is_raw,
    s.superseding_standard_id,
    s.std_group,
    s.sub_group,
    s.sub_sub_group,
    s.certification,
    s.relevant_ministries,
    s.sdg,
    s.short_common_man_title,
    s.ics_code,
    s.equivalent_standards,
    1 - (se.embedding <=> %(query_vec)s::vector) AS vector_similarity
FROM standard_embeddings se
JOIN standards s ON s.id = se.standard_id
WHERE se.embedding IS NOT NULL
ORDER BY se.embedding <=> %(query_vec)s::vector
LIMIT %(retrieval_k)s;
"""


def semantic_search(
    query_vec: list[float],
    conn: "psycopg.Connection",
    retrieval_k: int = 30,
) -> list[dict]:
    """
    Retrieve top-k candidates by pgvector cosine similarity.

    Returns a list of dicts, each containing standard fields and vector_similarity (0.0 to 1.0).
    """
    rows = conn.execute(
        _SEMANTIC_SEARCH_SQL,
        {"query_vec": query_vec, "retrieval_k": retrieval_k},
    ).fetchall()

    candidates = []
    for r in rows:
        d = dict(r)
        d["vector_similarity"] = float(d.get("vector_similarity") or 0.0)
        candidates.append(d)
    return candidates
