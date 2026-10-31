"""
backfill_nse_financials.py — one-time historical backfill of NSE SME
Integrated Filing financials.

Separate from poll_nse_financial_results() (the nightly job) on
purpose: the nightly job early-stops once a page yields nothing new,
since it only needs to catch RECENT filings each run. This script walks
the ENTIRE history once — per your manual's own Ch15 philosophy,
historical backfills are expected to run for a while, off-hours.

Reuses the exact same per-page logic (process_integrated_filing_page)
as the nightly poller, imported from nse.py — so there's one
correctness-critical implementation, not two copies that could drift
apart. Only the pagination STRATEGY differs here: walk every page using
the real totalCount from NSE's own response, with no early stop.

USAGE (from repo root, in your venv):
    python backfill_nse_financials.py

Expect this to take a while — real numbers: totalCount was ~4,821 at
20/page when last checked (~241 pages), each with real XBRL downloads
through a real browser session. This is NOT something to run casually
mid-day; treat it like the manual's own backfill guidance — run it
once, off-hours, and let it work.

If NSE's session appears to go stale partway through (repeated
failures), the script restarts the browser session once and retries
the current page before giving up on it and moving on — a bad page
should never kill the whole backfill.
"""

import math
import time

from sentismetric.log import setup_logging, log
from sentismetric.db import SessionLocal
from sentismetric.extract.nse_browser_fetch import NseBrowserSession
from sentismetric.ingestion.nse import (
    listing_url,
    process_integrated_filing_page,
    load_active_nse_companies,
    LISTING_PAGE_SIZE,
)

MAX_RETRIES_PER_PAGE = 2
RETRY_BACKOFF_SECONDS = 5


def backfill_nse_financials() -> int:
    total_new = 0

    with SessionLocal() as session:
        nse_companies = load_active_nse_companies(session)
        log.info("backfill: %d active NSE companies tracked", len(nse_companies))

        with NseBrowserSession() as browser:
            # first page tells us the real totalCount to compute how
            # many pages actually exist — don't guess/hardcode it
            first_payload = browser.get_json(listing_url(1))
            total_count = first_payload.get("totalCount", 0)
            total_pages = math.ceil(total_count / LISTING_PAGE_SIZE) if total_count else 1
            log.info("backfill: totalCount=%d, size=%d -> %d pages to walk",
                      total_count, LISTING_PAGE_SIZE, total_pages)

            rows = first_payload.get("data", [])
            page_new = process_integrated_filing_page(rows, session, nse_companies, browser)
            total_new += page_new
            log.info("backfill page 1/%d: %d new financials (running total: %d)",
                      total_pages, page_new, total_new)

            for page in range(2, total_pages + 1):
                payload = None
                for attempt in range(MAX_RETRIES_PER_PAGE + 1):
                    try:
                        payload = browser.get_json(listing_url(page))
                        break
                    except Exception as e:
                        log.warning("backfill page %d attempt %d failed: %s",
                                     page, attempt + 1, e)
                        if attempt < MAX_RETRIES_PER_PAGE:
                            time.sleep(RETRY_BACKOFF_SECONDS)
                            browser.restart()  # session likely stale — re-solve challenge
                        else:
                            log.error("backfill page %d failed after retries, skipping", page)

                if payload is None:
                    continue  # this page's data is lost for this run — a re-run later will catch it

                rows = payload.get("data", [])
                if not rows:
                    log.info("backfill: page %d returned no rows, stopping early", page)
                    break

                page_new = process_integrated_filing_page(rows, session, nse_companies, browser)
                total_new += page_new

                if page % 10 == 0 or page_new > 0:
                    log.info("backfill page %d/%d: %d new financials (running total: %d)",
                              page, total_pages, page_new, total_new)

    return total_new


if __name__ == "__main__":
    setup_logging(level="INFO")
    log.info("Starting NSE financials backfill — this will take a while.")
    count = backfill_nse_financials()
    log.info("Backfill complete: %d new financials rows inserted.", count)