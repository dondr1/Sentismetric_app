"""
backfill_pat.py — re-parses every XBRL file already saved on disk
(data/xbrl/NSE/*.xml) with the FIXED CONCEPT_MAP (ProfitLossForThePeriod,
not ProfitLossForPeriod), and updates the matching Financials row.

WHY THIS APPROACH: Financials rows don't store which specific file/seq_id
produced them — only (company_id, period). To match a re-parsed file back
to its row without extra bookkeeping, this uses the file's OWN embedded
XBRL period end-date (from the revenue fact, which we know parsed
correctly) to derive the same period label quarter_label_from_dates()
would have produced at original ingestion time. Self-contained — no
network calls needed, since every file is already on disk.

KNOWN LIMITATION (accepted tradeoff, not silently hidden): when both
Standalone and Consolidated XBRL files exist for the same company+period,
this can't tell them apart from the filename alone (that distinction only
existed in the original listing API response, never stored on disk).
Whichever file the filesystem processes LAST for a given period wins —
which may not match your original Standalone preference for that
specific row. Given this only affects companies with both variants, and
fixing the PAT gap (was ~85% of rows) matters more, this is accepted
rather than solved here. If it matters to you, re-running the real
backfill_nse_financials.py (which DOES see the Standalone/Consolidated
field) would restore the original preference — this script is a faster,
network-free patch, not a full re-ingestion.

USAGE (from repo root, in your venv):
    python backfill_pat.py
"""

import glob
from pathlib import Path

from sentismetric.log import setup_logging, log
from sentismetric.db import SessionLocal
from sentismetric.models import Company, Financials
from sentismetric.extract.xbrl import parse_xbrl, NotXBRLError
from sentismetric.analyze.scorecard import quarter_label_from_dates


def backfill_pat() -> dict:
    stats = {"updated": 0, "no_company_match": 0, "no_period_match": 0,
              "parse_errors": 0, "no_revenue_period": 0}

    xbrl_files = glob.glob("data/xbrl/NSE/*.xml")
    log.info("backfill_pat: found %d saved XBRL files to re-parse", len(xbrl_files))

    with SessionLocal() as session:
        companies = {c.symbol: c.id for c in session.query(Company).filter_by(exchange="NSE")}

        for filepath in xbrl_files:
            filename = Path(filepath).stem  # e.g. "MVKAGRO_128468"
            symbol = filename.rsplit("_", 1)[0]
            company_id = companies.get(symbol)
            if company_id is None:
                stats["no_company_match"] += 1
                continue

            try:
                facts = parse_xbrl(filepath)
            except NotXBRLError:
                stats["parse_errors"] += 1
                continue
            except Exception as e:
                log.warning("re-parse failed for %s: %s", filepath, e)
                stats["parse_errors"] += 1
                continue

            revenue_entries = facts.get("revenue")
            if not revenue_entries or not revenue_entries[0].get("period"):
                stats["no_revenue_period"] += 1
                continue

            period_tuple = revenue_entries[0]["period"]
            end_date = period_tuple[1] if period_tuple else None
            if not end_date:
                stats["no_revenue_period"] += 1
                continue

            period_label = quarter_label_from_dates(end_date)

            fin = (
                session.query(Financials)
                .filter_by(company_id=company_id, period=period_label)
                .one_or_none()
            )
            if fin is None:
                stats["no_period_match"] += 1
                continue

            def first_value(concept):
                entries = facts.get(concept)
                return entries[0]["value"] if entries else None

            fin.revenue = first_value("revenue")
            fin.pat = first_value("pat")
            fin.eps = first_value("eps")
            fin.debt_current = first_value("debt_current")
            fin.debt_noncurrent = first_value("debt_noncurrent")
            fin.debt_equity_ratio = first_value("debt_equity_ratio")
            fin.total_expenses = first_value("total_expenses")
            fin.raw = facts
            session.commit()
            stats["updated"] += 1

    return stats


if __name__ == "__main__":
    setup_logging(level="INFO")
    log.info("Starting PAT backfill (re-parsing saved XBRL files, no network calls)...")
    result = backfill_pat()
    log.info("Backfill complete: %s", result)