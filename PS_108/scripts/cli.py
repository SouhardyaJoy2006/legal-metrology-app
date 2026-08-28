#!/usr/bin/env python3
"""
scripts/cli.py
==============
Interactive CLI to test the BIS RAG database.

Usage:
    python scripts/cli.py

Commands:
    status            — check DB connection and embedding readiness
    search <query>    — semantic search (falls back to keyword if no embeddings)
    get <std_number>  — full details for one standard (partial match OK)
    list              — browse standards with optional filters
    stats             — database statistics
    help / quit
"""

from __future__ import annotations

import cmd
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── ANSI colours ──────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)
GREEN  = lambda t: _c("32", t)
CYAN   = lambda t: _c("36", t)
YELLOW = lambda t: _c("33", t)
RED    = lambda t: _c("31", t)

# ── Helpers ────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 72, indent: str = "   ") -> str:
    if not text:
        return ""
    return textwrap.fill(text, width=width, subsequent_indent=indent)


def _trunc(text: str, max_len: int = 80) -> str:
    if not text:
        return DIM("—")
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def _hr(char: str = "─", width: int = 70) -> str:
    return DIM(char * width)


def _print_standard_row(row: dict, rank: int | None = None, sim: float | None = None) -> None:
    prefix = f"{rank}. " if rank else "   "
    sim_str = f"  {GREEN(f'{sim*100:.0f}%')}" if sim is not None else ""
    print(f"\n{prefix}{BOLD(row['standard_number'])}{sim_str}")
    print(f"   {_trunc(row.get('title') or '', 80)}")
    parts = []
    if row.get("type_of_standard"):
        parts.append(row["type_of_standard"])
    if row.get("current_status"):
        parts.append(row["current_status"])
    if row.get("ics_code"):
        parts.append(f"ICS {row['ics_code']}")
    if parts:
        print(f"   {DIM(' | '.join(parts))}")


# ── DB helpers ─────────────────────────────────────────────────────────────

def _get_conn():
    from bis_rag.db.connection import get_connection
    return get_connection()


def _has_embeddings(conn) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM standard_embeddings WHERE embedding IS NOT NULL"
    ).fetchone()
    return (row["n"] if row else 0) > 0


def _detect_embedding_model(conn) -> str | None:
    row = conn.execute(
        "SELECT model_name FROM standard_embeddings WHERE model_name IS NOT NULL LIMIT 1"
    ).fetchone()
    return row["model_name"] if row else None


# ── REPL ───────────────────────────────────────────────────────────────────

class BISCli(cmd.Cmd):
    intro = (
        f"\n{_hr('═')}\n"
        f"  {BOLD('BIS Indian Standards — RAG Database CLI')}\n"
        f"  Type {CYAN('help')} for commands, {CYAN('status')} to check readiness.\n"
        f"{_hr('═')}\n"
    )
    prompt = f"{CYAN('bis>')} "

    # ── status ──────────────────────────────────────────────────────────────

    def do_status(self, _arg: str) -> None:
        """Check database connection and embedding readiness."""
        print()
        try:
            with _get_conn() as conn:
                pg_ver      = conn.execute("SELECT version()").fetchone()["version"].split()[1]
                std_count   = conn.execute("SELECT COUNT(*) AS n FROM standards").fetchone()["n"]
                emb_total   = conn.execute("SELECT COUNT(*) AS n FROM standard_embeddings").fetchone()["n"]
                emb_done    = conn.execute("SELECT COUNT(*) AS n FROM standard_embeddings WHERE embedding IS NOT NULL").fetchone()["n"]
                amend_count = conn.execute("SELECT COUNT(*) AS n FROM standard_amendments").fetchone()["n"]
                model_name  = _detect_embedding_model(conn)

            print(f"  {GREEN('✓')} PostgreSQL {pg_ver}  connected")
            print(f"  {GREEN('✓')} Standards loaded   : {BOLD(str(std_count))}")
            print(f"  {GREEN('✓')} Amendments loaded  : {BOLD(str(amend_count))}")

            if emb_done == 0:
                print(f"  {YELLOW('!')} Embeddings        : {BOLD('none yet')}")
                print(f"      Run: python scripts/create_embeddings.py")
            elif emb_done < emb_total:
                print(f"  {YELLOW('!')} Embeddings        : {emb_done}/{emb_total}  model={model_name or 'unknown'}")
            else:
                print(f"  {GREEN('✓')} Embeddings ready  : {BOLD(str(emb_done))}  model={model_name or 'unknown'}")

            if emb_done > 0:
                print(f"\n  {GREEN('✓')} Semantic search available  (use: search <query>)")
            else:
                print(f"\n  {YELLOW('!')} Keyword search only until embeddings are generated")
        except Exception as exc:
            print(f"  {RED('✗')} Cannot connect: {exc}")
            print(f"      Check .env and that PostgreSQL is running.")
        print()

    # ── search ──────────────────────────────────────────────────────────────

    def do_search(self, arg: str) -> None:
        """
        search <query> [--n <k>] [--all-versions]
        Hybrid semantic + lexical retrieval with lifecycle resolution.
        Examples:
          search safety of machinery
          search IS 16810 Part 1
          search lifting chains and slings
        """
        raw_args = arg.strip().split()
        if not raw_args:
            print(f"  {YELLOW('Usage:')} search <your query> [--n <count>] [--all-versions]")
            return

        top_k = 8
        include_superseded = True
        query_parts = []

        i = 0
        while i < len(raw_args):
            tok = raw_args[i]
            if tok == "--n" and i + 1 < len(raw_args):
                try:
                    top_k = int(raw_args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok in ("--only-current", "--no-superseded"):
                include_superseded = False
                i += 1
            else:
                query_parts.append(tok)
                i += 1

        query = " ".join(query_parts).strip()
        if not query:
            print(f"  {YELLOW('Usage:')} search <your query>")
            return

        print(f"\n  Searching: {CYAN(query)}")

        try:
            from bis_rag.retrieval import search_standards
            results = search_standards(
                query=query,
                top_k=top_k,
                retrieval_k=30,
                include_superseded=include_superseded,
            )

            if not results:
                print(f"  No results found for query: {query}")
                return

            print(f"  {DIM(f'Top {len(results)} recommendations (Hybrid · BGE-M3 + pgvector + Lexical):')}\n")
            for rank, r in enumerate(results, 1):
                self._print_rich_result(r, rank=rank)

        except Exception as exc:
            print(f"  {RED('Error during retrieval:')} {exc}")
            import traceback
            traceback.print_exc()
        print()

    def _print_rich_result(self, r: dict, rank: int) -> None:
        score_pct = r.get("relevance_percentage", 0.0)
        is_curr = r.get("is_current", False)
        status_badge = GREEN("CURRENT") if is_curr else YELLOW("SUPERSEDED")
        std_num = r.get("standard_number") or ""

        print(f"  {BOLD(f'{rank}. {std_num}')}  ({score_pct:.1f}% Match)")
        print(f"     {_wrap(r.get('title') or '', width=70, indent='     ')}")
        print(f"     {CYAN('Relevance:')}   {score_pct:.1f}%")
        print(f"     {CYAN('Type:')}        {r.get('type_of_standard', 'N/A')}")
        print(f"     {CYAN('Department:')}  {_trunc(r.get('department', 'N/A'), 55)}")
        print(f"     {CYAN('Committee:')}   {_trunc(r.get('committee', 'N/A'), 55)}")
        print(f"     {CYAN('Status:')}      {status_badge} ({r.get('current_status', 'N/A')})")

        latest_info = r.get("latest_version")
        if latest_info:
            print(f"     {CYAN('Latest Ver:')}  {GREEN(latest_info['standard_number'])} — {latest_info['title'][:50]}...")
        else:
            print(f"     {CYAN('Latest Ver:')}  YES (This is the active standard)")

        if r.get("supersedes") and r["supersedes"] != "None":
            print(f"     {CYAN('Supersedes:')}  {r['supersedes']}")

        amendments = r.get("no_of_amendments", 0)
        amend_str = f"{amendments} issued" if amendments > 0 else "None"
        print(f"     {CYAN('Amendments:')}  {amend_str}")

        if r.get("certification") and r["certification"] != "N/A":
            print(f"     {CYAN('Certify:')}     {r['certification']}")

        print(f"     {_hr('─', width=65)}")

    def _keyword_search(self, conn, query: str, top_k: int = 8) -> None:
        terms = " & ".join(w for w in query.split() if len(w) > 2)
        if not terms:
            terms = query

        rows = conn.execute(
            """
            SELECT standard_number, title, type_of_standard, current_status, ics_code,
                   ts_rank(to_tsvector('english', coalesce(title,'')),
                           to_tsquery('english', %(terms)s)) AS rank
            FROM   standards
            WHERE  to_tsvector('english', coalesce(title,'')) @@ to_tsquery('english', %(terms)s)
            ORDER  BY rank DESC
            LIMIT  %(k)s
            """,
            {"terms": terms, "k": top_k},
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """
                SELECT standard_number, title, type_of_standard, current_status, ics_code
                FROM   standards
                WHERE  title ILIKE %(p)s OR standard_number ILIKE %(p)s
                LIMIT  %(k)s
                """,
                {"p": f"%{query}%", "k": top_k},
            ).fetchall()

        if not rows:
            print(f"  No results for: {query}")
            return

        print(f"  {DIM(f'Top {len(rows)} results (keyword):')}")
        for i, row in enumerate(rows, 1):
            _print_standard_row(row, rank=i)

    # ── get ─────────────────────────────────────────────────────────────────

    def do_get(self, arg: str) -> None:
        """
        get <standard_number>
        Full details for one standard. Partial matches work.
        Examples:
          get IS 456:2000
          get IS 16810
        """
        query = arg.strip()
        if not query:
            print(f"  {YELLOW('Usage:')} get <standard_number>")
            return

        try:
            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM standards WHERE standard_number = %(q)s", {"q": query}
                ).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT * FROM standards WHERE standard_number ILIKE %(q)s ORDER BY date_of_publish DESC LIMIT 1",
                        {"q": f"%{query}%"},
                    ).fetchone()
                if not row:
                    print(f"\n  {YELLOW('Not found:')} {query}")
                    print(f"  Try: list  or  search {query}\n")
                    return
                self._print_detail(row, conn)
        except Exception as exc:
            print(f"  {RED('Error:')} {exc}")

    def _print_detail(self, row: dict, conn) -> None:
        print(f"\n{_hr()}")
        print(f"  {BOLD(row['standard_number'])}")
        print(f"  {_wrap(row.get('title') or '', indent='  ')}")
        print(f"{_hr()}")

        def _field(label: str, key: str, width: int = 20) -> None:
            val = row.get(key)
            if val is not None and str(val).strip():
                print(f"  {CYAN(label.ljust(width))} {val}")

        _field("Type",             "type_of_standard")
        _field("Status",           "current_status")
        _field("Date Published",   "date_of_publish")
        _field("Department",       "department")
        _field("Committee",        "committee")
        _field("Language",         "language")
        _field("ICS Code",         "ics_code")
        _field("Certification",    "certification")
        _field("Revisions",        "no_of_revisions")
        _field("Amendments",       "no_of_amendments")
        _field("Reaffirmed",       "reaffirmation_year")
        _field("Supersedes",       "superseding_is_raw")
        _field("Equivalent to",    "equivalent_standards")
        _field("Degree of Equiv.", "degree_of_equivalence")
        _field("Group",            "std_group")
        _field("Sub-group",        "sub_group")
        _field("Sub-sub-group",    "sub_sub_group")
        _field("Ministries",       "relevant_ministries")
        _field("Member Secretary", "member_secretary")
        if row.get("short_common_man_title"):
            _field("Common Name",  "short_common_man_title")
        if row.get("sdg"):
            print(f"  {CYAN('SDG'.ljust(20))} {_trunc(row['sdg'], 70)}")

        if row.get("lifecycle_path"):
            print(f"\n  {DIM('Lifecycle:')}")
            for step in row["lifecycle_path"].split(" -> "):
                print(f"    → {step}")

        amendments = conn.execute(
            "SELECT amendment_number, amendment_date, amendment_title FROM standard_amendments WHERE standard_id = %(id)s ORDER BY id",
            {"id": row["id"]},
        ).fetchall()
        if amendments:
            print(f"\n  {DIM('Amendments:')}")
            for a in amendments:
                print(f"    • {a.get('amendment_number') or ''} {a.get('amendment_date') or ''} {a.get('amendment_title') or ''}".rstrip())

        emb = conn.execute(
            "SELECT model_name, embedded_at FROM standard_embeddings WHERE standard_id = %(id)s",
            {"id": row["id"]},
        ).fetchone()
        if emb:
            if emb.get("embedded_at"):
                m_name = emb.get('model_name') or 'unknown'
                e_at = emb.get('embedded_at')
                print(f"\n  {DIM(f'Embedded: {m_name} at {e_at}')}")
            else:
                print(f"\n  {DIM('Embedding: not yet generated')}")

        if row.get("detail_url"):
            print(f"\n  {DIM('URL: ' + row['detail_url'])}")

        print(f"{_hr()}\n")

    # ── list ────────────────────────────────────────────────────────────────

    def do_list(self, arg: str) -> None:
        """
        list [--type <type>] [--status <status>] [--ics <code>] [--n <count>]
        Browse standards. Filters are optional.
        Examples:
          list
          list --type Safety Standard
          list --status Revised --n 20
          list --ics 13.110
        """
        args = arg.strip().split()
        filters = {"type": None, "status": None, "ics": None, "n": 15}

        i = 0
        while i < len(args):
            token = args[i]
            if token in ("--type", "--status", "--ics", "--n") and i + 1 < len(args):
                key = token.lstrip("-")
                val_parts = []
                i += 1
                while i < len(args) and not args[i].startswith("--"):
                    val_parts.append(args[i])
                    i += 1
                val = " ".join(val_parts)
                if key == "n":
                    try:
                        filters["n"] = int(val)
                    except ValueError:
                        pass
                else:
                    filters[key] = val
            else:
                i += 1

        where_clauses = []
        params: dict = {}
        if filters["type"]:
            where_clauses.append("type_of_standard ILIKE %(type)s")
            params["type"] = f"%{filters['type']}%"
        if filters["status"]:
            where_clauses.append("current_status ILIKE %(status)s")
            params["status"] = f"%{filters['status']}%"
        if filters["ics"]:
            where_clauses.append("ics_code ILIKE %(ics)s")
            params["ics"] = f"%{filters['ics']}%"

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        params["n"] = filters["n"]

        try:
            with _get_conn() as conn:
                total = conn.execute(
                    f"SELECT COUNT(*) AS c FROM standards {where_sql}", params
                ).fetchone()["c"]
                rows = conn.execute(
                    f"""
                    SELECT standard_number, title, type_of_standard, current_status, ics_code
                    FROM   standards
                    {where_sql}
                    ORDER  BY date_of_publish DESC NULLS LAST, standard_number
                    LIMIT  %(n)s
                    """,
                    params,
                ).fetchall()
        except Exception as exc:
            print(f"  {RED('Error:')} {exc}")
            return

        filter_desc = []
        if filters["type"]:   filter_desc.append(f"type={filters['type']}")
        if filters["status"]: filter_desc.append(f"status={filters['status']}")
        if filters["ics"]:    filter_desc.append(f"ics={filters['ics']}")
        filter_str = f"  [{', '.join(filter_desc)}]" if filter_desc else ""
        print(f"\n  {DIM(f'Showing {len(rows)} of {total} standards{filter_str}')}")

        for row in rows:
            _print_standard_row(row)

        if total > filters["n"]:
            rem = total - filters["n"]
            print(f"\n  {DIM(f'... {rem} more. Use --n {total} to see all.')}")
        print()

    # ── stats ───────────────────────────────────────────────────────────────

    def do_stats(self, _arg: str) -> None:
        """Show aggregate statistics about the loaded standards."""
        try:
            with _get_conn() as conn:
                total     = conn.execute("SELECT COUNT(*) AS n FROM standards").fetchone()["n"]
                emb_done  = conn.execute("SELECT COUNT(*) AS n FROM standard_embeddings WHERE embedding IS NOT NULL").fetchone()["n"]
                amendments= conn.execute("SELECT COUNT(*) AS n FROM standard_amendments").fetchone()["n"]
                by_type   = conn.execute("SELECT type_of_standard AS label, COUNT(*) AS n FROM standards WHERE type_of_standard IS NOT NULL GROUP BY type_of_standard ORDER BY n DESC").fetchall()
                by_status = conn.execute("SELECT current_status AS label, COUNT(*) AS n FROM standards WHERE current_status IS NOT NULL GROUP BY current_status ORDER BY n DESC").fetchall()
                by_ics    = conn.execute("SELECT ics_code AS label, COUNT(*) AS n FROM standards WHERE ics_code IS NOT NULL GROUP BY ics_code ORDER BY n DESC LIMIT 10").fetchall()
        except Exception as exc:
            print(f"  {RED('Error:')} {exc}")
            return

        print(f"\n{_hr()}")
        print(f"  {BOLD('BIS Standards — Database Statistics')}")
        print(f"{_hr()}")
        print(f"  {'Total standards':30} {BOLD(str(total))}")
        print(f"  {'Total amendments':30} {BOLD(str(amendments))}")
        print(f"  {'Embeddings generated':30} {BOLD(str(emb_done))} / {total}")
        print()

        if by_type:
            print(f"  {CYAN('By type:')}")
            for row in by_type:
                bar = "█" * min(int(row["n"] / total * 30), 30)
                print(f"    {str(row['label']):<35} {str(row['n']):>5}  {DIM(bar)}")
        print()

        if by_status:
            print(f"  {CYAN('By status:')}")
            for row in by_status:
                print(f"    {str(row['label']):<20} {row['n']}")
        print()

        if by_ics:
            print(f"  {CYAN('Top ICS codes:')}")
            for row in by_ics:
                print(f"    {str(row['label']):<15} {row['n']}")
        print(f"{_hr()}\n")

    # ── housekeeping ────────────────────────────────────────────────────────

    def do_quit(self, _arg: str) -> bool:
        """Exit the CLI."""
        print(f"\n  {DIM('Goodbye.')}\n")
        return True

    def do_exit(self, arg: str) -> bool:
        """Exit."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str) -> bool:
        print()
        return self.do_quit(arg)

    def default(self, line: str) -> None:
        print(f"  {YELLOW('Unknown command:')} {line}")
        print(f"  Type {CYAN('help')} to see available commands.")

    def emptyline(self) -> None:
        pass

    def do_help(self, arg: str) -> None:
        if arg:
            super().do_help(arg)
            return
        hr = _hr()
        print(hr)
        print(f"  {BOLD('Commands')}")
        print(hr)
        print(f"  {CYAN('status')}                    DB connection + embedding readiness")
        print(f"  {CYAN('search')} <query>            Hybrid semantic+lexical search (with lifecycle & ranking)")
        print(f"  {CYAN('get')} <standard_number>     Full detail view (partial match OK)")
        print(f"  {CYAN('list')}                      Browse standards (recent first)")
        print(f"  {CYAN('list --type')} <type>        Filter by type, e.g. \"Safety Standard\"")
        print(f"  {CYAN('list --status')} <status>    Filter by status, e.g. \"Revised\"")
        print(f"  {CYAN('list --ics')} <code>         Filter by ICS code, e.g. \"13.110\"")
        print(f"  {CYAN('list --n')} <number>         How many results (default 15)")
        print(f"  {CYAN('stats')}                     Counts + breakdown by type, status, ICS")
        print(f"  {CYAN('quit')}                      Exit")
        print(hr)
        print(f"  {DIM('Examples:')}")
        print("    search safety of machinery control systems")
        print("    search IS 16810 Part 1")
        print("    get IS 16810 (Part 1):2026")
        print("    list --type Safety Standard --n 20")
        print("    list --ics 13.110")
        print(hr)
        print()


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    try:
        from bis_rag.db.connection import get_connection as _gc
        with _gc() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        print(f"\n{RED('Cannot connect to database:')} {exc}")
        print("Check your .env file and that PostgreSQL is running.")
        print("Then: python -m bis_rag.db.manage ping\n")
        sys.exit(1)

    BISCli().cmdloop()


if __name__ == "__main__":
    main()
