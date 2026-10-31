"""
backfill_bse_financials.py -- one-time (resumable) BSE SME financials
backfill from the exchange's own XBRL. Run from repo root, in your venv.

    python backfill_bse_financials.py --limit 5            # smoke test, headed
    python backfill_bse_financials.py --headed --limit 5
    python backfill_bse_financials.py                      # everything, headless
    python backfill_bse_financials.py --scrip 543320 --since-fy 2022

Safe to stop and re-run: periods already in the DB are skipped, and each
company commits as it goes. Default history is FY2023 onward (enough for
HoH and YoY on recent filings).
"""

import argparse
import sys
import time

from sentismetric.db import SessionLocal
from sentismetric.log import setup_logging, log
from sentismetric.ingestion.bse_financials import (
    BseBrowserSession,
    fetch_company_rows,
    load_active_bse_companies,
    process_company_rows,
)
from sentismetric.ingestion.ratelimit import RateLimiter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only first N companies")
    ap.add_argument("--scrip", type=int, nargs="*", help="only these BSE scrip codes")
    ap.add_argument("--since-fy", type=int, default=2023, help="earliest FY start year (default 2023)")
    ap.add_argument("--headed", action="store_true", help="show the browser (use if headless gets 403)")
    ap.add_argument("--rps", type=float, default=0.8, help="max file fetches per second")
    args = ap.parse_args()

    setup_logging(level="INFO")
    log.info("bse backfill starting - connecting to database (if this hangs, start Docker: docker compose up -d)")
    limiter = RateLimiter(args.rps)
    total_new = 0
    no_data = 0
    failed = []

    with SessionLocal() as session:
        companies = load_active_bse_companies(session)
        log.info("database OK - %d BSE companies with numeric scrip codes", len(companies))
        scrips = sorted(companies)
        if args.scrip:
            scrips = [s for s in scrips if s in set(args.scrip)]
        if args.limit:
            scrips = scrips[: args.limit]
        log.info("bse backfill: %d companies (since FY%d)", len(scrips), args.since_fy)
        if not scrips:
            log.error("no active BSE companies with numeric scrip codes found in DB")
            return 1

        log.info("launching browser (settles ~10s on the BSE page)...")
        with BseBrowserSession(headless=not args.headed) as browser:
            t0 = time.time()
            for i, sc in enumerate(scrips, 1):
                company = companies[sc]
                log.info("[%d/%d] %s %s: fetching result list...", i, len(scrips), sc, company.name[:30])
                try:
                    rows = fetch_company_rows(browser, sc)
                    new = process_company_rows(company, rows, session, browser,
                                               limiter=limiter, since_fy=args.since_fy)
                except Exception as e:
                    session.rollback()
                    log.error("bse %s (%s) failed: %s", company.symbol, sc, e)
                    failed.append(sc)
                    continue
                total_new += new
                if new == 0:
                    no_data += 1
                log.info("[%d/%d] %s: +%d new (running total %d, %.0fs elapsed)",
                         i, len(scrips), sc, new, total_new, time.time() - t0)

    log.info("bse backfill done: %d new rows; %d companies added nothing; %d failed %s",
             total_new, no_data, len(failed), failed[:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())