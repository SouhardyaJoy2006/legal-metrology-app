#!/usr/bin/env python3
"""
scripts/load_data.py
=====================
Load the preprocessed BIS standards into PostgreSQL.

This script reads data/processed/bis_standards_processed.json and inserts
every record into the database using an upsert strategy (safe to run
multiple times — duplicate standard_numbers are updated, not re-inserted).

Prerequisites:
    1. PostgreSQL is running.
    2. .env file has your credentials (copy from .env.example).
    3. Migrations have been run:
           python -m bis_rag.db.manage migrate
    4. The pipeline has been run:
           python -m bis_rag.preprocessing.pipeline \\
               --input data/raw/bis_standards.jsonl \\
               --output data/processed/

Usage:
    python scripts/load_data.py
    python scripts/load_data.py --input data/processed/bis_standards_processed.json
    python scripts/load_data.py --dry-run   # validate only, no DB writes

What it does:
    1. Opens a connection to PostgreSQL.
    2. Upserts each standard into the standards table.
    3. Inserts amendment rows into standard_amendments.
    4. Creates placeholder rows in standard_embeddings (embedding=NULL).
    5. Resolves superseding_standard_id FK references between standards.
    6. Commits everything as one transaction.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Make sure the project root is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from bis_rag.db.connection import get_connection
from bis_rag.ingestion.loader import load_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load BIS standards into PostgreSQL")
    p.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/bis_standards_processed.json"),
        help="Path to the processed JSON file (default: data/processed/bis_standards_processed.json)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the file but do not write to the database",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}")
        print("Run the pipeline first:")
        print("  python -m bis_rag.preprocessing.pipeline \\")
        print("      --input data/raw/bis_standards.jsonl \\")
        print("      --output data/processed/")
        sys.exit(1)

    if args.dry_run:
        import json
        records = json.loads(args.input.read_text())
        print(f"DRY RUN: {len(records)} records found in {args.input}")
        print("No database writes performed.")
        return

    print(f"Loading: {args.input}")
    print("Connecting to database...")

    start = time.time()
    with get_connection() as conn:
        summary = load_all(args.input, conn)
    elapsed = time.time() - start

    print()
    print("=" * 50)
    print("Load complete.")
    print(f"  Standards inserted/updated : {summary['inserted']}")
    print(f"  Amendments inserted        : {summary['amendments']}")
    print(f"  Superseding FKs resolved   : {summary['fk_resolved']}")
    print(f"  Time taken                 : {elapsed:.1f}s")
    print()
    print("Next step: generate embeddings")
    print("  python scripts/create_embeddings.py --model local")


if __name__ == "__main__":
    main()
