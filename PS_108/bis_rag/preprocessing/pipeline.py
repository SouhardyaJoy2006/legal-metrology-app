"""
bis_rag.preprocessing.pipeline
================================
Orchestrates the raw → processed JSON preprocessing pipeline.

Usage:
    python -m bis_rag.preprocessing.pipeline \\
        --input  data/raw/bis_standards.jsonl \\
        --output data/processed/

Reads raw JSON/JSONL, canonicalizes + validates each record, writes:
  <stem>_processed.json       — canonical records
  <stem>_quality_report.txt   — data quality summary

Does NOT connect to the database or generate embeddings.

Deduplication: keeps the record with the later scraped_at when
the same standard_number appears more than once.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterator

from bis_rag.preprocessing.normalizer import canonicalize_record
from bis_rag.preprocessing.validator import (
    generate_quality_report,
    format_quality_report,
)

logger = logging.getLogger(__name__)


def _iter_records(path: Path) -> Iterator[dict]:
    """Yield raw record dicts from a JSON array file or JSON Lines file."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.warning("File is empty: %s", path)
        return

    if text.startswith("["):
        try:
            records = json.loads(text)
            if isinstance(records, list):
                yield from records
                return
        except json.JSONDecodeError:
            pass

    errors = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj
        except json.JSONDecodeError as exc:
            logger.warning("Line %d: JSON parse error — %s", lineno, exc)
            errors += 1

    if errors:
        logger.warning("%d JSON parse errors in %s", errors, path)


def _deduplicate(canonical_records: list[dict]) -> tuple[list[dict], list[str]]:
    """Keep one record per standard_number (latest scraped_at wins)."""
    seen: dict[str, dict] = {}
    dropped: list[str] = []

    for rec in canonical_records:
        sn = rec.get("standard_number")
        if not sn:
            seen[f"__no_sn_{id(rec)}"] = rec
            continue
        if sn not in seen:
            seen[sn] = rec
        else:
            existing_at = seen[sn].get("scraped_at") or ""
            new_at = rec.get("scraped_at") or ""
            if new_at > existing_at:
                dropped.append(sn)
                seen[sn] = rec
            else:
                dropped.append(sn)

    return list(seen.values()), dropped


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    fail_on_invalid: bool = False,
) -> tuple[list[dict], object]:
    """
    Run the full preprocessing pipeline for one raw JSON/JSONL file.

    Returns (canonical_records, quality_report).
    Writes processed JSON and quality report to output_dir.
    Does NOT modify input_path.
    """
    logger.info("Pipeline: reading %s", input_path)

    raw_records = list(_iter_records(input_path))
    logger.info("Parsed %d raw records", len(raw_records))

    canonical: list[dict] = []
    for raw in raw_records:
        try:
            canonical.append(canonicalize_record(raw))
        except Exception as exc:
            logger.error("canonicalize_record failed on %r: %s", raw.get("standard_number"), exc)

    canonical, dropped_sns = _deduplicate(canonical)
    if dropped_sns:
        logger.warning("Dropped %d duplicate(s)", len(dropped_sns))

    report = generate_quality_report(canonical)
    logger.info("Validation: %d valid, %d invalid", report.valid_records, report.invalid_records)

    if fail_on_invalid and report.invalid_records > 0:
        raise RuntimeError(f"{report.invalid_records} invalid records. Review quality report.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    def _json_default(obj):
        from datetime import date
        if isinstance(obj, date):
            return obj.isoformat()
        raise TypeError(f"Not serializable: {type(obj)}")

    processed_path = output_dir / f"{stem}_processed.json"
    with processed_path.open("w", encoding="utf-8") as f:
        json.dump(canonical, f, indent=2, default=_json_default, ensure_ascii=False)
    logger.info("Wrote processed records to %s", processed_path)

    report_path = output_dir / f"{stem}_quality_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(format_quality_report(report))
    logger.info("Wrote quality report to %s", report_path)

    return canonical, report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BIS RAG preprocessing pipeline — raw JSON → canonical JSON",
    )
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--fail-on-invalid", action="store_true", default=False)
    return p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    args = _build_parser().parse_args()

    input_path: Path = args.input
    output_dir: Path = args.output

    if input_path.is_dir():
        json_files = sorted(input_path.glob("*.json")) + sorted(input_path.glob("*.jsonl"))
        if not json_files:
            print(f"No JSON files found in {input_path}")
            sys.exit(1)
    elif input_path.is_file():
        json_files = [input_path]
    else:
        print(f"Input path does not exist: {input_path}")
        sys.exit(1)

    total_invalid = 0
    for json_file in json_files:
        _, rpt = run_pipeline(json_file, output_dir, fail_on_invalid=False)
        total_invalid += rpt.invalid_records
        print(format_quality_report(rpt))

    if args.fail_on_invalid and total_invalid > 0:
        print(f"\nFailed: {total_invalid} invalid records.")
        sys.exit(1)
