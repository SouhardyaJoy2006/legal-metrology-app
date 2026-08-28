"""
bis_rag.retrieval.lexical
==========================
Lexical and exact-match retrieval using PostgreSQL full-text search and ILIKE.

Used in hybrid search for exact matches on:
- Standard numbers ("IS 16810", "IS 16810 (Part 1):2026")
- Base standard numbers ("IS 16810 (Part 1)")
- ISO/IEC equivalent numbers ("ISO 13849", "ISO 8745")
- ICS codes ("13.110", "21.060.50")
- Title keywords
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

_SELECT_FIELDS = """
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
    s.equivalent_standards
"""


def lexical_search(
    query: str,
    conn: "psycopg.Connection",
    retrieval_k: int = 30,
) -> list[dict]:
    """
    Retrieve candidates matching exact standard numbers, ISO/IEC codes, ICS codes, or title keywords.

    Returns a list of dicts with lexical_score (0.0 to 1.0) indicating match strength.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # Extract potential standard numbers (e.g., "IS 16810", "ISO 13849", "IS 8324")
    std_match = re.search(r"\b(IS|ISO|IEC|SP)\s*[/:\-]?\s*\d+[\d\s\-()/]*", cleaned_query, re.IGNORECASE)
    std_pattern = std_match.group(0).strip() if std_match else cleaned_query

    # Query 1: Exact / Prefix match on standard_number, standard_number_base, equivalent_standards, ics_code
    sql_exact = f"""
    SELECT {_SELECT_FIELDS},
           CASE
               WHEN LOWER(s.standard_number) = LOWER(%(raw_q)s) THEN 1.0
               WHEN LOWER(s.standard_number_base) = LOWER(%(raw_q)s) THEN 0.9
               WHEN s.standard_number ILIKE %(std_pat)s THEN 0.85
               WHEN s.standard_number_base ILIKE %(std_pat)s THEN 0.80
               WHEN s.equivalent_standards ILIKE %(std_pat)s THEN 0.75
               WHEN s.ics_code ILIKE %(raw_q)s THEN 0.70
               ELSE 0.50
           END AS lexical_score
    FROM standards s
    WHERE s.standard_number ILIKE %(std_pat)s
       OR s.standard_number_base ILIKE %(std_pat)s
       OR s.equivalent_standards ILIKE %(std_pat)s
       OR s.ics_code ILIKE %(raw_q)s
    LIMIT %(retrieval_k)s;
    """

    results_dict: dict[int, dict] = {}

    exact_rows = conn.execute(
        sql_exact,
        {
            "raw_q": cleaned_query,
            "std_pat": f"%{std_pattern}%",
            "retrieval_k": retrieval_k,
        },
    ).fetchall()

    for r in exact_rows:
        d = dict(r)
        results_dict[d["id"]] = d

    # Query 2: Full-text title search / keyword ILIKE
    words = [w for w in re.findall(r"\w+", cleaned_query) if len(w) > 2]
    if words:
        ts_query_str = " & ".join(words)
        sql_fts = f"""
        SELECT {_SELECT_FIELDS},
               ts_rank(to_tsvector('english', coalesce(s.title, '')), to_tsquery('english', %(fts_q)s)) AS rank
        FROM standards s
        WHERE to_tsvector('english', coalesce(s.title, '')) @@ to_tsquery('english', %(fts_q)s)
        LIMIT %(retrieval_k)s;
        """
        try:
            fts_rows = conn.execute(sql_fts, {"fts_q": ts_query_str, "retrieval_k": retrieval_k}).fetchall()
            for r in fts_rows:
                d = dict(r)
                sid = d["id"]
                score = min(0.60, float(d.get("rank") or 0.1) * 2.0 + 0.30)
                if sid in results_dict:
                    results_dict[sid]["lexical_score"] = max(results_dict[sid].get("lexical_score", 0.0), score)
                else:
                    d["lexical_score"] = score
                    results_dict[sid] = d
        except Exception:
            pass  # Full text parse fail fallback

    return list(results_dict.values())
