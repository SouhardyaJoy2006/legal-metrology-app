"""
bis_rag.preprocessing.validator
================================
Record-level validation and aggregate data-quality reporting.

validate_record(canonical)         → ValidationResult
generate_quality_report(records)   → QualityReport
format_quality_report(report)      → str
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# Matches all real BIS standard number patterns observed in the dataset:
#   IS NNNNN[:YYYY]                        plain standard
#   IS NNNNN (Part N)[:YYYY]               part notation
#   IS NNNNN (Part N/Sec M)[:YYYY]         section notation
#   IS NNNNN (Part N to M)[:YYYY]          range notation e.g. "Part 1 to 8"
#   IS/ISO NNNNN[:YYYY]                    dual-numbered with ISO
#   IS/ISO/TR, IS/ISO/TS, IS/ISO/PAS       ISO sub-types
#   IS/IEC, IS/ISO/IEC                     IEC standards
#   SP NNNNN[:YYYY]                        Special Publications
_VALID_STD_NUMBER_RE = re.compile(
    r"^(IS(/ISO)?(/IEC|/TR|/TS|/PAS|/GUIDE)?|IS/ISO/IEC(\s+GUIDE)?|SP)"
    r"\s+\d[\d\s\-]*"
    r"(\s*\(Part\s+\d+(\s+(to|and)\s+\d+|/Sec\s*\d+)?\))?"
    r"(\s*/\s*Sec\s*\d+)?"
    r"(\s*\(Amendment\s+\d+\))?"
    r"(:\d{4})?$",
    re.IGNORECASE,
)

REQUIRED_FIELDS = ("standard_number", "title")
RECOMMENDED_FIELDS = ("department", "committee", "current_status", "type_of_standard")


@dataclass
class ValidationResult:
    standard_number: str | None
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_standard_numbers: list[str] = field(default_factory=list)
    missing_required_fields: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    invalid_standard_numbers: list[str] = field(default_factory=list)
    missing_titles: list[str] = field(default_factory=list)
    missing_departments: list[str] = field(default_factory=list)
    missing_statuses: list[str] = field(default_factory=list)
    malformed_dates: list[str] = field(default_factory=list)
    by_department: dict[str, int] = field(default_factory=lambda: Counter())
    by_status: dict[str, int] = field(default_factory=lambda: Counter())
    by_type: dict[str, int] = field(default_factory=lambda: Counter())
    warnings_by_record: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def validate_record(canonical: dict) -> ValidationResult:
    """Validate a single canonical record. Returns errors (fatal) and warnings (non-fatal)."""
    std_num = canonical.get("standard_number")
    result = ValidationResult(standard_number=std_num, is_valid=True)

    for fld in REQUIRED_FIELDS:
        if not canonical.get(fld):
            result.errors.append(f"Missing required field: '{fld}'")
            result.is_valid = False

    if std_num and not _VALID_STD_NUMBER_RE.match(std_num):
        result.errors.append(f"standard_number does not match expected pattern: '{std_num}'")
        result.is_valid = False

    if canonical.get("date_of_publish") is None and canonical.get("scraped_at"):
        result.warnings.append("date_of_publish is missing or could not be parsed")

    for fld in RECOMMENDED_FIELDS:
        if not canonical.get(fld):
            result.warnings.append(f"Recommended field missing: '{fld}'")

    return result


def generate_quality_report(records: list[dict]) -> QualityReport:
    """Generate an aggregate quality report for a list of canonical records."""
    report = QualityReport(total_records=len(records))

    number_counter: Counter[str] = Counter(
        r.get("standard_number") or "" for r in records if r.get("standard_number")
    )
    report.duplicate_standard_numbers = [
        sn for sn, count in number_counter.items() if count > 1
    ]

    for rec in records:
        sn = rec.get("standard_number") or "<no standard_number>"
        vr = validate_record(rec)

        if vr.is_valid:
            report.valid_records += 1
        else:
            report.invalid_records += 1

        if not rec.get("standard_number"):
            report.missing_required_fields["standard_number"].append(sn)
        if not rec.get("title"):
            report.missing_titles.append(sn)
            report.missing_required_fields["title"].append(sn)
        if not rec.get("department"):
            report.missing_departments.append(sn)
        if not rec.get("current_status"):
            report.missing_statuses.append(sn)
        if rec.get("date_of_publish") is None:
            report.malformed_dates.append(sn)
        if rec.get("standard_number") and not _VALID_STD_NUMBER_RE.match(rec["standard_number"]):
            report.invalid_standard_numbers.append(sn)

        report.by_department[rec.get("department") or "Unknown"] += 1
        report.by_status[rec.get("current_status") or "Unknown"] += 1
        report.by_type[rec.get("type_of_standard") or "Unknown"] += 1

        if vr.warnings:
            report.warnings_by_record[sn].extend(vr.warnings)

    return report


def format_quality_report(report: QualityReport) -> str:
    """Render a QualityReport as a human-readable text block."""
    lines: list[str] = [
        "=" * 60,
        "BIS RAG — Data Quality Report",
        "=" * 60,
        f"Total records          : {report.total_records}",
        f"Valid records          : {report.valid_records}",
        f"Invalid records        : {report.invalid_records}",
        f"Duplicate std numbers  : {len(report.duplicate_standard_numbers)}",
        "",
    ]

    if report.duplicate_standard_numbers:
        lines.append("Duplicate standard numbers:")
        for sn in sorted(report.duplicate_standard_numbers):
            lines.append(f"  {sn}")
        lines.append("")

    lines += [
        f"Missing standard_number: {len(report.missing_required_fields.get('standard_number', []))}",
        f"Missing title          : {len(report.missing_titles)}",
        f"Missing department     : {len(report.missing_departments)}",
        f"Missing current_status : {len(report.missing_statuses)}",
        f"Malformed/missing dates: {len(report.malformed_dates)}",
        f"Invalid std numbers    : {len(report.invalid_standard_numbers)}",
        "",
    ]

    if report.by_department:
        lines.append("Records by department (top 20):")
        for dept, count in sorted(report.by_department.items(), key=lambda x: -x[1])[:20]:
            lines.append(f"  {count:>6}  {dept}")
        lines.append("")

    if report.by_status:
        lines.append("Records by status:")
        for status, count in sorted(report.by_status.items(), key=lambda x: -x[1]):
            lines.append(f"  {count:>6}  {status}")
        lines.append("")

    if report.by_type:
        lines.append("Records by type_of_standard:")
        for typ, count in sorted(report.by_type.items(), key=lambda x: -x[1]):
            lines.append(f"  {count:>6}  {typ}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
