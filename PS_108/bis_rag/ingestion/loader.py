"""
bis_rag.ingestion.loader
=========================
Loads canonical records (from the preprocessing pipeline) into PostgreSQL.

Entry point:
    from bis_rag.ingestion.loader import load_all

    with get_connection() as conn:
        summary = load_all("data/processed/bis_standards_processed.json", conn)
        print(summary)

Insertion order:
1. Upsert standards rows (ON CONFLICT standard_number → UPDATE metadata).
2. Insert standard_amendments rows for each standard that has them.
3. Insert placeholder rows in standard_embeddings (embedding=NULL, filled later).
4. Second pass: resolve superseding_standard_id FK for all rows.

All work is done inside a single transaction. If anything fails, the whole
batch is rolled back — no partial state is written.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_UPSERT_STANDARD = """
INSERT INTO standards (
    standard_number, standard_number_base, title, date_of_publish,
    type_of_standard, degree_of_equivalence, current_status, lifecycle_path,
    detail_url, department, committee, language, reaffirmation_year,
    member_secretary, no_of_revisions, no_of_amendments, superseding_is_raw,
    std_group, sub_group, sub_sub_group, certification, relevant_ministries,
    sdg, short_common_man_title, ics_code, equivalent_standards,
    scraped_at, raw_data, updated_at
)
VALUES (
    %(standard_number)s, %(standard_number_base)s, %(title)s, %(date_of_publish)s,
    %(type_of_standard)s, %(degree_of_equivalence)s, %(current_status)s, %(lifecycle_path)s,
    %(detail_url)s, %(department)s, %(committee)s, %(language)s, %(reaffirmation_year)s,
    %(member_secretary)s, %(no_of_revisions)s, %(no_of_amendments)s, %(superseding_is_raw)s,
    %(std_group)s, %(sub_group)s, %(sub_sub_group)s, %(certification)s, %(relevant_ministries)s,
    %(sdg)s, %(short_common_man_title)s, %(ics_code)s, %(equivalent_standards)s,
    %(scraped_at)s, %(raw_data)s, NOW()
)
ON CONFLICT (standard_number) DO UPDATE SET
    standard_number_base  = EXCLUDED.standard_number_base,
    title                 = EXCLUDED.title,
    date_of_publish       = EXCLUDED.date_of_publish,
    type_of_standard      = EXCLUDED.type_of_standard,
    degree_of_equivalence = EXCLUDED.degree_of_equivalence,
    current_status        = EXCLUDED.current_status,
    lifecycle_path        = EXCLUDED.lifecycle_path,
    detail_url            = EXCLUDED.detail_url,
    department            = EXCLUDED.department,
    committee             = EXCLUDED.committee,
    language              = EXCLUDED.language,
    reaffirmation_year    = EXCLUDED.reaffirmation_year,
    member_secretary      = EXCLUDED.member_secretary,
    no_of_revisions       = EXCLUDED.no_of_revisions,
    no_of_amendments      = EXCLUDED.no_of_amendments,
    superseding_is_raw    = EXCLUDED.superseding_is_raw,
    std_group             = EXCLUDED.std_group,
    sub_group             = EXCLUDED.sub_group,
    sub_sub_group         = EXCLUDED.sub_sub_group,
    certification         = EXCLUDED.certification,
    relevant_ministries   = EXCLUDED.relevant_ministries,
    sdg                   = EXCLUDED.sdg,
    short_common_man_title= EXCLUDED.short_common_man_title,
    ics_code              = EXCLUDED.ics_code,
    equivalent_standards  = EXCLUDED.equivalent_standards,
    scraped_at            = EXCLUDED.scraped_at,
    raw_data              = EXCLUDED.raw_data,
    updated_at            = NOW()
RETURNING id;
"""

_INSERT_AMENDMENT = """
INSERT INTO standard_amendments (standard_id, amendment_number, amendment_date, amendment_title, raw_data)
VALUES (%(standard_id)s, %(amendment_number)s, %(amendment_date)s, %(amendment_title)s, %(raw_data)s)
ON CONFLICT DO NOTHING;
"""

_UPSERT_EMBEDDING_PLACEHOLDER = """
INSERT INTO standard_embeddings (standard_id)
VALUES (%(standard_id)s)
ON CONFLICT (standard_id) DO NOTHING;
"""

_RESOLVE_SUPERSEDING = """
UPDATE standards AS child
SET    superseding_standard_id = parent.id
FROM   standards AS parent
WHERE  child.superseding_is_raw = parent.standard_number
  AND  child.superseding_standard_id IS NULL;
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all(
    processed_json_path: str | Path,
    conn: "psycopg.Connection",
) -> dict:
    """
    Load all canonical records from a processed JSON file into PostgreSQL.

    Parameters
    ----------
    processed_json_path : str | Path
        Path to the processed JSON file produced by the pipeline
        (e.g. "data/processed/bis_standards_processed.json").
    conn : psycopg.Connection
        An open database connection. NOT in autocommit mode.

    Returns
    -------
    dict
        {
            "inserted": int,      # new rows inserted into standards
            "updated": int,       # existing rows updated
            "amendments": int,    # amendment rows inserted
            "fk_resolved": int,   # superseding_standard_id FKs resolved
        }

    Raises
    ------
    FileNotFoundError
        If processed_json_path does not exist.
    psycopg.Error
        On database errors (entire transaction is rolled back).
    """
    path = Path(processed_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Processed JSON not found: {path}")

    records = json.loads(path.read_text(encoding="utf-8"))
    logger.info("Loading %d records from %s", len(records), path)

    inserted = 0
    updated = 0
    amendments_inserted = 0

    with conn.transaction():
        for rec in records:
            db_id = _upsert_standard(rec, conn)
            if db_id:
                # We can't easily distinguish insert vs update with RETURNING in psycopg
                # without checking created_at == updated_at, so we count all as inserted
                inserted += 1

            _insert_amendments(db_id, rec.get("_amendments") or [], conn)
            amendments_inserted += len(rec.get("_amendments") or [])

            _upsert_embedding_placeholder(db_id, conn)

        fk_resolved = _resolve_superseding_fks(conn)

    logger.info(
        "Loaded: %d standards, %d amendments, %d superseding FKs resolved",
        inserted, amendments_inserted, fk_resolved,
    )
    return {
        "inserted": inserted,
        "updated": 0,  # upsert — rows may have been updated; count is combined above
        "amendments": amendments_inserted,
        "fk_resolved": fk_resolved,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert_standard(rec: dict, conn: "psycopg.Connection") -> int:
    """Upsert one standard row. Returns the database id."""
    import json as _json

    params = {k: rec.get(k) for k in (
        "standard_number", "standard_number_base", "title", "date_of_publish",
        "type_of_standard", "degree_of_equivalence", "current_status", "lifecycle_path",
        "detail_url", "department", "committee", "language", "reaffirmation_year",
        "member_secretary", "no_of_revisions", "no_of_amendments", "superseding_is_raw",
        "std_group", "sub_group", "sub_sub_group", "certification", "relevant_ministries",
        "sdg", "short_common_man_title", "ics_code", "equivalent_standards", "scraped_at",
    )}

    # raw_data: store the original scraped record as JSONB (exclude pipeline-internal keys)
    raw = rec.get("_raw") or {}
    params["raw_data"] = _json.dumps(raw, ensure_ascii=False, default=str)

    row = conn.execute(_UPSERT_STANDARD, params).fetchone()
    return row["id"]


def _insert_amendments(standard_id: int, amendments: list, conn: "psycopg.Connection") -> None:
    """Insert amendment rows for a standard."""
    import json as _json
    for amend in amendments:
        if not isinstance(amend, dict):
            continue
        conn.execute(_INSERT_AMENDMENT, {
            "standard_id":      standard_id,
            "amendment_number": amend.get("amendment_number"),
            "amendment_date":   amend.get("amendment_date"),
            "amendment_title":  amend.get("description") or amend.get("title"),
            "raw_data":         _json.dumps(amend, ensure_ascii=False),
        })


def _upsert_embedding_placeholder(standard_id: int, conn: "psycopg.Connection") -> None:
    """Create a placeholder row in standard_embeddings (embedding stays NULL until generated)."""
    conn.execute(_UPSERT_EMBEDDING_PLACEHOLDER, {"standard_id": standard_id})


def _resolve_superseding_fks(conn: "psycopg.Connection") -> int:
    """
    Second-pass FK resolution: for every row where superseding_is_raw is set
    but superseding_standard_id is NULL, try to find the parent standard by
    matching superseding_is_raw to another row's standard_number.
    Returns the number of FKs successfully resolved.
    """
    result = conn.execute(_RESOLVE_SUPERSEDING)
    count = result.rowcount
    logger.info("Resolved %d superseding_standard_id FK(s)", count)
    return count


# ---------------------------------------------------------------------------
# Individual public functions (used by scripts/load_data.py)
# ---------------------------------------------------------------------------

def load_standards(canonical_records: list[dict], conn: "psycopg.Connection") -> dict[str, int]:
    """
    Insert/upsert a list of canonical records. Returns {standard_number: db_id}.
    Does NOT commit — caller manages the transaction.
    """
    result = {}
    for rec in canonical_records:
        db_id = _upsert_standard(rec, conn)
        result[rec.get("standard_number", "")] = db_id
        _insert_amendments(db_id, rec.get("_amendments") or [], conn)
        _upsert_embedding_placeholder(db_id, conn)
    _resolve_superseding_fks(conn)
    return result


def load_amendments(standard_db_id: int, amendments: list[dict], conn: "psycopg.Connection") -> None:
    """Insert amendment rows for a specific standard."""
    _insert_amendments(standard_db_id, amendments, conn)


def resolve_superseding_references(conn: "psycopg.Connection") -> int:
    """Resolve superseding_standard_id FKs. Returns count resolved."""
    return _resolve_superseding_fks(conn)
