"""
bis_rag.preprocessing.normalizer
=================================
Pure, side-effect-free field normalization functions.

Each function takes a raw scraper value and returns a typed Python value.
None is returned wherever the raw value is a null sentinel.

Null sentinels recognised: "--", "- -", "N/A", "n/a", "NA", "None",
"null", "Nil", "Not Applicable", "" (empty string), and Python None.

Special numeric field mappings found in the real dataset:
  no_of_revisions:  "New Standard" → 0, "01" → 1, etc.
  no_of_amendments: "No amendment issued" → 0, "01" → 1, etc.

type_of_standard casing: scraper emits both "Methods of tests" and
"Methods of Tests" — normalised to title-case.

current_status: scraped as full phrase "IS 456:2000 (Revised)" — we
extract just the status word in parentheses: "Revised".

reaffirmation_year: stored as TEXT because values like "Jan, 2022"
cannot be represented as a bare integer without data loss.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

_NULL_SENTINELS: frozenset[str] = frozenset({
    "--", "- -", "---",
    "N/A", "n/a", "NA", "na",
    "None", "none", "null", "Null", "NULL",
    "Nil", "NIL", "nil",
    "Not Applicable", "not applicable", "NOT APPLICABLE",
})

_DATE_FORMATS = (
    "%d %b %Y",   # "04 Aug 2026"  ← primary BIS format
    "%d %B %Y",   # "04 August 2026"
    "%B %d, %Y",  # "August 4, 2026"
    "%Y-%m-%d",   # ISO
    "%d/%m/%Y",
    "%d-%m-%Y",
)

_STD_NUM_YEAR_RE = re.compile(r":(\d{4})$")
_MULTI_SPACE = re.compile(r"[ \t]+")
_STATUS_IN_PARENS = re.compile(r"\(([^)]+)\)$")


def normalize_null_sentinel(value: Any) -> str | None:
    """Return None for null sentinels/empty values, else the stripped string."""
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value).strip() or None
    stripped = value.strip()
    if not stripped or stripped in _NULL_SENTINELS:
        return None
    return stripped


def normalize_whitespace(value: Any) -> str | None:
    """Collapse internal whitespace; normalise Unicode spaces; apply null check."""
    cleaned = normalize_null_sentinel(value)
    if cleaned is None:
        return None
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "")
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    return cleaned or None


def normalize_standard_number(value: Any) -> str | None:
    """
    Normalise a BIS standard number.
    Collapses whitespace, normalises spacing around the colon-year separator,
    and upper-cases the IS prefix.
    e.g. "is 16810 (Part 1) : 2026" → "IS 16810 (Part 1):2026"
    """
    cleaned = normalize_whitespace(value)
    if cleaned is None:
        return None
    cleaned = re.sub(r"\s*:\s*(\d{4})$", r":\1", cleaned)
    if cleaned.upper().startswith("IS "):
        cleaned = "IS " + cleaned[3:]
    return cleaned


def extract_standard_number_base(standard_number: str | None) -> str | None:
    """Strip year suffix: "IS 456:2000" → "IS 456"."""
    if standard_number is None:
        return None
    return _STD_NUM_YEAR_RE.sub("", standard_number).strip() or None


def normalize_date(value: Any) -> date | None:
    """Parse BIS date strings. Returns None if unparseable."""
    from datetime import datetime
    cleaned = normalize_null_sentinel(value)
    if cleaned is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def normalize_int_field(value: Any) -> int | None:
    """
    Parse an integer field.
    Special mappings for real dataset values:
      "New Standard"        → 0   (no prior revisions)
      "No amendment issued" → 0   (no amendments)
    """
    if isinstance(value, int):
        return value
    cleaned = normalize_null_sentinel(value)
    if cleaned is None:
        return None
    lower = cleaned.lower()
    if lower in ("new standard", "no amendment issued"):
        return 0
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def normalize_name(value: Any) -> str | None:
    """Collapse whitespace; preserve original case (BIS uses uppercase acronyms)."""
    return normalize_whitespace(value)


def normalize_type_of_standard(value: Any) -> str | None:
    """
    Normalise type_of_standard.
    Handles casing inconsistency in real data:
      "Methods of tests" and "Methods of Tests" → "Methods of Tests"
    Also maps "-" and "--" sentinels to None.
    """
    cleaned = normalize_whitespace(value)
    if cleaned is None or cleaned in ("-", "--"):
        return None
    return cleaned.title() if cleaned.lower().startswith("method") else cleaned


def normalize_current_status(value: Any) -> str | None:
    """
    Extract the status keyword from the full phrase stored by the scraper.
    "IS 16810 (Part 1):2026 (Revised)" → "Revised"
    "IS 456:2000 (Published)"          → "Published"
    If the pattern doesn't match, the full cleaned string is returned.
    """
    cleaned = normalize_whitespace(value)
    if cleaned is None:
        return None
    m = _STATUS_IN_PARENS.search(cleaned)
    return m.group(1) if m else cleaned


def canonicalize_record(raw: dict) -> dict:
    """
    Transform one raw scraper record into its canonical form.

    Field mapping (raw path → canonical key):
      standard_number (top)             → standard_number
      basic_details.std_number          →   (same; top-level wins)
      title (top)                       → title
      basic_details.title_full          →   (longer form; kept in _raw)
      date_of_publish                   → date_of_publish (date)
      type_of_standard (top)            → type_of_standard
      degree_of_equivalence (top)       → degree_of_equivalence
      detail_url / lifecycle_path       → direct
      current_status                    → current_status (status word only)
      basic_details.department          → department
      basic_details.committee           → committee
      basic_details.superseding_is      → superseding_is_raw
      basic_details.no_of_revisions     → no_of_revisions (int)
      basic_details.no_of_amendments    → no_of_amendments (int)
      basic_details.language            → language
      basic_details.reaffirmation_year  → reaffirmation_year (TEXT)
      basic_details.member_secretary    → member_secretary
      classification_details.group      → std_group
      classification_details.sub_group  → sub_group
      classification_details.sub_sub_group → sub_sub_group
      classification_details.certification → certification
      classification_details.relevant_ministries → relevant_ministries
      classification_details.sdg        → sdg
      classification_details.short_common_man_title → short_common_man_title
      classification_details.ics_code   → ics_code
      classification_details.equivalent_standards → equivalent_standards
      scraped_at                        → scraped_at
      (full record)                     → _raw
      amendment.amendments              → _amendments (for standard_amendments table)

    Missing keys are tolerated at all levels.
    """
    def _get(obj, *keys, default=None):
        current = obj
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
            if current is None:
                return default
        return current

    bd = raw.get("basic_details") or {}
    cd = raw.get("classification_details") or {}
    amend = raw.get("amendment") or {}

    std_number = normalize_standard_number(
        raw.get("standard_number") or bd.get("std_number")
    )

    return {
        "standard_number":        std_number,
        "standard_number_base":   extract_standard_number_base(std_number),
        "title":                  normalize_whitespace(raw.get("title") or bd.get("title_full")),
        "date_of_publish":        normalize_date(raw.get("date_of_publish")),
        "type_of_standard":       normalize_type_of_standard(raw.get("type_of_standard") or bd.get("type_of_standard")),
        "degree_of_equivalence":  normalize_whitespace(raw.get("degree_of_equivalence") or bd.get("degree_of_equivalence")),
        "current_status":         normalize_current_status(raw.get("current_status")),
        "lifecycle_path":         normalize_whitespace(raw.get("lifecycle_path")),
        "detail_url":             normalize_null_sentinel(raw.get("detail_url")),
        "department":             normalize_name(bd.get("department")),
        "committee":              normalize_name(bd.get("committee")),
        "language":               normalize_whitespace(bd.get("language")),
        "reaffirmation_year":     normalize_null_sentinel(bd.get("reaffirmation_year")),
        "member_secretary":       normalize_whitespace(bd.get("member_secretary")),
        "no_of_revisions":        normalize_int_field(bd.get("no_of_revisions")),
        "no_of_amendments":       normalize_int_field(bd.get("no_of_amendments")),
        "superseding_is_raw":     normalize_whitespace(bd.get("superseding_is")),
        "std_group":              normalize_whitespace(cd.get("group")),
        "sub_group":              normalize_whitespace(cd.get("sub_group")),
        "sub_sub_group":          normalize_whitespace(cd.get("sub_sub_group")),
        "certification":          normalize_whitespace(cd.get("certification")),
        "relevant_ministries":    normalize_whitespace(cd.get("relevant_ministries")),
        "sdg":                    normalize_whitespace(cd.get("sdg")),
        "short_common_man_title": normalize_whitespace(cd.get("short_common_man_title")),
        "ics_code":               normalize_whitespace(cd.get("ics_code")),
        "equivalent_standards":   normalize_whitespace(cd.get("equivalent_standards")),
        "scraped_at":             normalize_null_sentinel(raw.get("scraped_at")),
        "_raw":                   raw,
        "_amendments":            amend.get("amendments") or [],
    }
