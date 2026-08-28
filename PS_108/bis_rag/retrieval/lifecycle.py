"""
bis_rag.retrieval.lifecycle
============================
Lifecycle resolution and version family grouping.

Determines:
- Standard family key (e.g. "IS 16810 (Part 1)")
- Current vs Superseded status (is_current)
- Latest version pointers for historical/superseded standards
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg


def resolve_lifecycle_and_families(
    candidates: list[dict],
    conn: "psycopg.Connection",
) -> list[dict]:
    """
    Enrich candidates with lifecycle status, family key, and pointers to current/superseding standards.

    Does NOT delete historical standards — simply marks is_current=True/False and attaches latest_version metadata.
    """
    if not candidates:
        return []

    # Collect standard IDs and base numbers
    candidate_ids = {c["id"] for c in candidates}
    base_numbers = {c.get("standard_number_base") for c in candidates if c.get("standard_number_base")}

    # Fetch latest/current standard for each family key from DB
    latest_by_base: dict[str, dict] = {}
    if base_numbers:
        sql = """
        SELECT DISTINCT ON (standard_number_base)
               id, standard_number, standard_number_base, title, date_of_publish, current_status
        FROM standards
        WHERE standard_number_base = ANY(%(bases)s)
        ORDER BY standard_number_base, date_of_publish DESC NULLS LAST, no_of_revisions DESC;
        """
        rows = conn.execute(sql, {"bases": list(base_numbers)}).fetchall()
        for r in rows:
            d = dict(r)
            latest_by_base[d["standard_number_base"]] = d

    # Fetch superseding parent standards for candidate rows where superseding_standard_id is set
    superseding_ids = {c["superseding_standard_id"] for c in candidates if c.get("superseding_standard_id")}
    superseding_map: dict[int, dict] = {}
    if superseding_ids:
        sql_sup = """
        SELECT id, standard_number, title, date_of_publish, current_status
        FROM standards
        WHERE id = ANY(%(sids)s);
        """
        sup_rows = conn.execute(sql_sup, {"sids": list(superseding_ids)}).fetchall()
        for r in sup_rows:
            d = dict(r)
            superseding_map[d["id"]] = d

    # Find which standards in our candidate pool are superseded by a newer edition
    # If standard B has superseding_standard_id = A.id, then A is superseded by B.
    candidate_id_list = list(candidate_ids)
    superseded_ids: set[int] = set()
    superseded_by_map: dict[int, dict] = {}

    if candidate_id_list:
        sql_superseded = """
        SELECT child.id AS superseded_id,
               parent.id AS latest_id,
               parent.standard_number AS latest_number,
               parent.title AS latest_title,
               parent.date_of_publish AS latest_date
        FROM standards child
        JOIN standards parent ON child.id = parent.superseding_standard_id
        WHERE child.id = ANY(%(cids)s);
        """
        sup_rows = conn.execute(sql_superseded, {"cids": candidate_id_list}).fetchall()
        for r in sup_rows:
            d = dict(r)
            superseded_ids.add(d["superseded_id"])
            superseded_by_map[d["superseded_id"]] = d

    enriched = []
    for c in candidates:
        d = dict(c)
        base_key = d.get("standard_number_base") or d.get("standard_number") or ""
        d["family_key"] = base_key
        cid = d["id"]

        family_latest = latest_by_base.get(base_key)
        is_latest_in_family = bool(family_latest and family_latest["id"] == cid)

        # A standard is CURRENT if it is the latest in its family and not superseded
        if cid in superseded_ids or (not is_latest_in_family and family_latest):
            is_current = False
            status_label = "SUPERSEDED"
        else:
            is_current = True
            status_label = "CURRENT"

        d["is_current"] = is_current
        d["status_label"] = status_label

        # Attach latest version info if superseded
        if not is_current:
            if cid in superseded_by_map:
                sup_info = superseded_by_map[cid]
                d["latest_version"] = {
                    "id": sup_info["latest_id"],
                    "standard_number": sup_info["latest_number"],
                    "title": sup_info["latest_title"],
                    "date_of_publish": str(sup_info.get("latest_date") or ""),
                }
            elif family_latest and family_latest["id"] != cid:
                d["latest_version"] = {
                    "id": family_latest["id"],
                    "standard_number": family_latest["standard_number"],
                    "title": family_latest["title"],
                    "date_of_publish": str(family_latest.get("date_of_publish") or ""),
                }
            else:
                d["latest_version"] = None
        else:
            d["latest_version"] = None

        enriched.append(d)

    return enriched
