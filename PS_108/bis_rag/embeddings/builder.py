"""
bis_rag.embeddings.builder
===========================
Builds the text string passed to the embedding model for each standard.

Why text construction matters:
  The embedding model only sees the text you give it. Richer, more
  structured text → better retrieval. Missing a key field → that
  field becomes unsearchable by meaning.

BGE-M3 and E5 models accept a document prefix ("passage: ...").
This is applied automatically by the embedder — builder just returns
the raw content text.

Changing the template: edit build_standard_text() and re-run
create_embeddings.py --force to regenerate all embeddings.
"""

from __future__ import annotations


def build_standard_text(row: dict) -> str:
    """
    Build the embedding text for one standard row (from DB or processed JSON).

    Included fields and why:
      standard_number + title  — primary identity; most query-relevant
      type_of_standard         — Safety Standard vs Product Spec changes retrieval
      current_status           — Published/Revised/Amended is relevant context
      department + committee   — domain and technical committee
      ics_code                 — international classification; cross-standard linking
      equivalent_standards     — links this IS to ISO/IEC equivalents semantically
      superseding_is_raw       — historical context (this replaced IS XXXX)
      certification            — Mandatory/Voluntary changes regulatory meaning
      short_common_man_title   — plain-language name if present
      std_group hierarchy      — product/domain category

    Excluded:
      sdg             — verbose, low retrieval value
      lifecycle_path  — redundant with current_status
      detail_url      — not semantic
      member_secretary— not relevant to search queries
      scraped_at      — metadata noise
    """
    parts: list[str] = []

    std_num = (row.get("standard_number") or "").strip()
    title   = (row.get("title") or "").strip()
    if std_num and title:
        parts.append(f"{std_num} — {title}")
    elif std_num or title:
        parts.append(std_num or title)

    meta: list[str] = []
    for label, key in [
        ("Type",       "type_of_standard"),
        ("Status",     "current_status"),
        ("Department", "department"),
        ("Committee",  "committee"),
        ("ICS",        "ics_code"),
        ("Language",   "language"),
    ]:
        val = row.get(key)
        if val:
            meta.append(f"{label}: {val}")
    if meta:
        parts.append(" | ".join(meta))

    if row.get("equivalent_standards"):
        parts.append(f"Equivalent to: {row['equivalent_standards']}")
    if row.get("superseding_is_raw"):
        parts.append(f"Supersedes: {row['superseding_is_raw']}")
    if row.get("certification"):
        parts.append(f"Certification: {row['certification']}")
    if row.get("short_common_man_title"):
        parts.append(f"Common name: {row['short_common_man_title']}")
    if row.get("relevant_ministries"):
        parts.append(f"Ministry: {row['relevant_ministries']}")

    group_parts: list[str] = []
    for key in ("std_group", "sub_group", "sub_sub_group"):
        val = row.get(key)
        if val:
            group_parts.append(val)
    if group_parts:
        parts.append("Group: " + " > ".join(group_parts))

    return "\n".join(parts)


def build_chunk_text(chunk_text: str, standard_number: str, title: str) -> str:
    """
    Build embedding text for a PDF chunk. Prepends the standard's identity
    so the model knows what document the chunk comes from.
    Used when PDF ingestion is implemented.
    """
    header = f"{standard_number} — {title}" if title else standard_number
    return f"{header}\n\n{chunk_text}"
