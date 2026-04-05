#!/usr/bin/env python3
"""
CLI entry point for the rental scraper system.

Usage examples:
  # Scrape all sites (only those due for a refresh)
  python run_scraper.py

  # Force-scrape all sites regardless of recency
  python run_scraper.py --force

  # Scrape specific sites
  python run_scraper.py --sites suumo ddproperty hipflat

  # Show stored listings with filters
  python run_scraper.py --report --country Thailand --grade S

  # Show grade distribution summary
  python run_scraper.py --summary

  # Show top-value listings
  python run_scraper.py --top-value --country Japan --limit 10

  # Run continuously (re-scrape every N hours)
  python run_scraper.py --watch --interval 12
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure package is importable when run from project root
sys.path.insert(0, str(Path(__file__).parent))

from rental_scraper.agent import OrchestratorAgent
from rental_scraper.config import SITES
from rental_scraper.grader.grader import ValueGrader
from rental_scraper.storage.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scraper")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Rental listing scraper – Japan / Vietnam / Thailand",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Scrape options
    p.add_argument("--sites", nargs="+", metavar="SITE_ID",
                   help="Limit scraping to these site IDs")
    p.add_argument("--force", action="store_true",
                   help="Ignore recency; always scrape")
    p.add_argument("--max-concurrent", type=int, default=2,
                   help="Max parallel site agents (default: 2)")
    p.add_argument("--max-age", type=float, default=24.0, metavar="HOURS",
                   help="Re-scrape sites older than this many hours (default: 24)")

    # Reporting
    p.add_argument("--report", action="store_true",
                   help="Print stored listings")
    p.add_argument("--summary", action="store_true",
                   help="Print grade distribution summary")
    p.add_argument("--top-value", action="store_true",
                   help="Print top-value (S/A grade) listings")

    # Filters (used with --report / --top-value)
    p.add_argument("--country", metavar="COUNTRY",
                   help="Filter by country (Japan/Vietnam/Thailand)")
    p.add_argument("--city", metavar="CITY",
                   help="Filter by city")
    p.add_argument("--grade", metavar="GRADE",
                   help="Filter by value grade (S/A/B/C/D)")
    p.add_argument("--limit", type=int, default=20,
                   help="Max rows to show (default: 20)")

    # Continuous watch
    p.add_argument("--watch", action="store_true",
                   help="Run continuously, re-scraping on schedule")
    p.add_argument("--interval", type=float, default=24.0, metavar="HOURS",
                   help="Hours between watch cycles (default: 24)")

    # Misc
    p.add_argument("--list-sites", action="store_true",
                   help="List all configured sites and exit")
    p.add_argument("--db", default=None, metavar="PATH",
                   help="Path to SQLite database (default: data/rentals.db)")
    p.add_argument("--json", action="store_true",
                   help="Output results as JSON instead of table")

    return p


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_table(rows, columns):
    if not rows:
        print("  (no results)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, "") or "")) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    print(header)
    print("-" * len(header))
    for r in rows:
        print("  ".join(str(r.get(c, "") or "").ljust(widths[c]) for c in columns))


def _print_listings(rows, as_json=False):
    cols = ["id", "site_id", "country", "city", "title", "price_usd", "size_sqm",
            "price_per_sqm_usd", "value_grade", "value_score", "url"]
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, cols)


def _print_summary(rows, as_json=False):
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, ["country", "city", "site_id", "value_grade", "n",
                             "avg_price_usd", "avg_sqm", "avg_ppsqm"])


# ── Async tasks ───────────────────────────────────────────────────────────────

async def run_scrape(args, db: Database):
    async with OrchestratorAgent(
        db,
        max_concurrent=args.max_concurrent,
        max_age_hours=args.max_age,
    ) as orch:
        summary = await orch.run(site_ids=args.sites, force=args.force)

    print(f"\n── Scrape Complete ──────────────────────────────")
    print(f"  Sites run   : {summary['sites_run']}")
    print(f"  Total found : {summary['total_found']}")
    print(f"  New listings: {summary['total_new']}")
    print(f"  Grades upd  : {summary['grades_updated']}")
    print()
    cols = ["site_id", "status", "found", "new", "duration_s", "error"]
    _print_table(summary["results"], cols)
    return summary


async def run_watch(args, db: Database):
    interval_s = args.interval * 3600
    cycle = 0
    while True:
        cycle += 1
        logger.info("Watch cycle %d starting…", cycle)
        await run_scrape(args, db)
        logger.info("Watch cycle %d done. Sleeping %.1f hours…", cycle, args.interval)
        await asyncio.sleep(interval_s)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.list_sites:
        _print_table(
            [
                {
                    "site_id": s.site_id,
                    "country": s.country,
                    "name": s.name,
                    "scale": s.scale,
                    "english": s.english_friendly,
                    "priority": s.priority,
                }
                for s in SITES
            ],
            ["site_id", "country", "name", "scale", "english", "priority"],
        )
        return

    db_path = Path(args.db) if args.db else None
    db_kwargs = {"db_path": db_path} if db_path else {}
    db = Database(**db_kwargs)
    db.connect()

    try:
        if args.report:
            rows = db.get_listings(
                country=args.country,
                city=args.city,
                grade=args.grade,
                limit=args.limit,
            )
            print(f"\n── Listings ({len(rows)}) ─────────────────────────────")
            _print_listings(rows, as_json=args.json)
            return

        if args.summary:
            grader = ValueGrader(db)
            rows = grader.summary()
            print("\n── Grade Distribution ───────────────────────────────")
            _print_summary(rows, as_json=args.json)
            return

        if args.top_value:
            grader = ValueGrader(db)
            rows = grader.top_value_listings(country=args.country, limit=args.limit)
            print(f"\n── Top-Value Listings ({len(rows)}) ─────────────────")
            _print_listings(rows, as_json=args.json)
            return

        if args.watch:
            await run_watch(args, db)
        else:
            await run_scrape(args, db)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
