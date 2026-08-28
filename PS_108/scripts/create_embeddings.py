#!/usr/bin/env python3
"""
scripts/create_embeddings.py
==============================
Generate and store embedding vectors for BIS standards.

Model is configured via .env — no code changes needed to switch models:
    EMBEDDING_MODEL=BAAI/bge-m3
    EMBEDDING_DIM=1024
    EMBEDDING_BATCH_SIZE=32

See bis_rag/embeddings/models.py for the full model registry.

Usage:
    python scripts/create_embeddings.py              # embed all pending
    python scripts/create_embeddings.py --dry-run    # preview text, no writes
    python scripts/create_embeddings.py --force      # re-embed everything
    python scripts/create_embeddings.py --filter "IS 456"  # one standard
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bis_rag.db.connection import get_connection
from bis_rag.embeddings import get_embedder, build_standard_text, get_active_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


_FETCH_PENDING = """
SELECT se.id, se.standard_id,
       s.standard_number, s.title, s.type_of_standard, s.current_status,
       s.department, s.committee, s.ics_code, s.language,
       s.equivalent_standards, s.superseding_is_raw, s.certification,
       s.short_common_man_title, s.std_group, s.sub_group, s.sub_sub_group,
       s.relevant_ministries
FROM   standard_embeddings se
JOIN   standards s ON s.id = se.standard_id
WHERE  se.embedding IS NULL
ORDER  BY s.standard_number;
"""

_FETCH_ALL = _FETCH_PENDING.replace("WHERE  se.embedding IS NULL", "WHERE  1=1")

_FETCH_FILTERED = """
SELECT se.id, se.standard_id,
       s.standard_number, s.title, s.type_of_standard, s.current_status,
       s.department, s.committee, s.ics_code, s.language,
       s.equivalent_standards, s.superseding_is_raw, s.certification,
       s.short_common_man_title, s.std_group, s.sub_group, s.sub_sub_group,
       s.relevant_ministries
FROM   standard_embeddings se
JOIN   standards s ON s.id = se.standard_id
WHERE  s.standard_number ILIKE %(p)s OR s.title ILIKE %(p)s
ORDER  BY s.standard_number;
"""

_UPDATE_EMBEDDING = """
UPDATE standard_embeddings
SET    embedding      = %(embedding)s,
       embedding_text = %(embedding_text)s,
       model_name     = %(model_name)s,
       embedded_at    = NOW(),
       updated_at     = NOW()
WHERE  id = %(se_id)s;
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Generate BIS standard embeddings")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    p.add_argument("--force",   action="store_true", help="Re-embed already-embedded rows")
    p.add_argument("--filter",  metavar="PATTERN",  help="Only embed matching standards")
    args = p.parse_args()

    config = get_active_model()
    print(f"\nModel      : {config.name}")
    print(f"Dimension  : {config.dim}")
    print(f"Multilingual: {config.multilingual}")
    print(f"Backend    : {config.backend}")
    print()

    with get_connection() as conn:
        # Validate DB column dimension matches model
        col_info = conn.execute("""
            SELECT atttypmod FROM pg_attribute
            JOIN pg_class ON pg_class.oid = pg_attribute.attrelid
            WHERE pg_class.relname = 'standard_embeddings'
              AND pg_attribute.attname = 'embedding'
        """).fetchone()
        if col_info and col_info["atttypmod"] != -1:
            db_dim = col_info["atttypmod"]
            if db_dim != config.dim:
                print(f"ERROR: DB column is {db_dim} dims but model produces {config.dim} dims.")
                print(f"Run migration 009 to fix this:")
                print(f"  python -m bis_rag.db.manage migrate")
                sys.exit(1)

        # Fetch rows to embed
        if args.filter:
            rows = conn.execute(_FETCH_FILTERED, {"p": f"%{args.filter}%"}).fetchall()
        elif args.force:
            rows = conn.execute(_FETCH_ALL).fetchall()
        else:
            rows = conn.execute(_FETCH_PENDING).fetchall()

        if not rows:
            print("Nothing to embed — all standards already have embeddings.")
            print("Use --force to re-embed everything.")
            return

        print(f"Standards to embed: {len(rows)}")

        # Build texts
        texts = [build_standard_text(row) for row in rows]

        if args.dry_run:
            print("\nDRY RUN — first 3 embedding texts:\n")
            for row, text in zip(rows[:3], texts[:3]):
                print(f"--- {row['standard_number']} ---")
                print(text)
                print()
            print(f"Would embed {len(rows)} standards. No writes.")
            return

        # Load model and embed
        print(f"Loading model (may take ~30s on first run, downloads ~2.3GB)...")
        embedder = get_embedder()

        print(f"\nGenerating embeddings on GPU...")
        start = time.time()
        vectors = embedder.embed_documents(texts)
        elapsed = time.time() - start
        print(f"Done: {len(vectors)} vectors in {elapsed:.1f}s  "
              f"({len(vectors)/elapsed:.0f} standards/sec)")

        # Write to DB
        print("Writing to database...")
        with conn.transaction():
            for row, text, vec in zip(rows, texts, vectors):
                conn.execute(_UPDATE_EMBEDDING, {
                    "se_id":          row["id"],
                    "embedding":      vec,
                    "embedding_text": text,
                    "model_name":     config.name,
                })

        print(f"Stored {len(vectors)} embeddings  [{config.name}]")
        print("\nTest with:")
        print("  python scripts/cli.py")
        print("  bis> search safety of machinery")


if __name__ == "__main__":
    main()
