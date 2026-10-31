from pathlib import Path
from datetime import datetime
from sentismetric.db import SessionLocal
from sentismetric.models import Financials, Company
from sentismetric.extract.xbrl import parse_xbrl
from sentismetric.log import setup_logging, log

setup_logging(level="INFO")


def period_label_from_dates(end: str | None) -> str | None:
    """Turn an XBRL end/instant date into a human period label matching
    what poll_nse_financial_results() already stores, e.g. 'Third Quarter'.
    Debt/balance-sheet facts are instant (no start date), so we determine
    the Indian FY quarter using the end date's month alone."""
    if not end:
        return None
    try:
        e = datetime.fromisoformat(end)
    except ValueError:
        return None

    # Indian FY quarters, keyed by the END month of each quarter
    quarter_end_map = {6: "First Quarter", 9: "Second Quarter", 12: "Third Quarter", 3: "Fourth Quarter"}
    return quarter_end_map.get(e.month)


xbrl_dir = Path("data/xbrl/NSE")
files = list(xbrl_dir.glob("*.xml"))
log.info("found %d XBRL files to backfill", len(files))

updated = 0
skipped = 0
ambiguous = 0

with SessionLocal() as session:
    for f in files:
        symbol = f.stem.split("_")[0]

        company = (
            session.query(Company)
            .filter_by(exchange="NSE", symbol=symbol)
            .one_or_none()
        )
        if company is None:
            skipped += 1
            continue

        try:
            facts = parse_xbrl(str(f))
        except Exception as e:
            log.warning("failed to parse %s: %s", f.name, e)
            skipped += 1
            continue

        def first_entry(concept):
            entries = facts.get(concept)
            return entries[0] if entries else None

        debt_current_entry = first_entry("debt_current")
        debt_noncurrent_entry = first_entry("debt_noncurrent")
        debt_equity_entry = first_entry("debt_equity_ratio")

        if not any([debt_current_entry, debt_noncurrent_entry, debt_equity_entry]):
            skipped += 1
            continue

        source_entry = debt_current_entry or debt_noncurrent_entry or debt_equity_entry
        period_tuple = source_entry["period"] if source_entry else None
        if period_tuple is None:
            skipped += 1
            continue

        _, end = period_tuple
        period_label = period_label_from_dates(end)

        if period_label is None:
            log.warning("could not determine period for %s (end=%s) -- skipping", symbol, end)
            ambiguous += 1
            continue

        row = (
            session.query(Financials)
            .filter_by(company_id=company.id, period=period_label)
            .one_or_none()
        )
        if row is None:
            log.warning("no matching financials row for %s / %s -- skipping", symbol, period_label)
            skipped += 1
            continue

        row.debt_current = debt_current_entry["value"] if debt_current_entry else None
        row.debt_noncurrent = debt_noncurrent_entry["value"] if debt_noncurrent_entry else None
        row.debt_equity_ratio = debt_equity_entry["value"] if debt_equity_entry else None
        session.commit()
        updated += 1
        log.info("backfilled debt for %s / %s", symbol, period_label)

log.info("backfill complete: %d updated, %d skipped, %d ambiguous period", updated, skipped, ambiguous)