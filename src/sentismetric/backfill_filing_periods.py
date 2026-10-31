"""
backfill_filing_periods.py — one-time backfill for existing filings
missing a period (confirmed blank for every filing in your DB today).

Two-tier approach, per your cost/accuracy tradeoff decision:
  - RECENT filings (last RECENT_MONTHS_THRESHOLD months): full
    re-extraction + re-analysis through the updated prompt, so they get
    the ACCURATE, grounded period_end_date (and refreshed insight
    content generally, since prompt_version changed). Costs real
    Anthropic API calls (vision extraction + LLM analysis) — this is
    the expensive, accurate path, deliberately scoped to only recent
    filings to control cost.
  - OLDER filings: cheap estimate_period_from_exchange_ts() only, no
    API calls, no re-analysis. Less accurate, but free and unblocks the
    scorecard at zero cost for the long tail.

Only touches filings whose filing_type actually reports period
financials (RESULTS_HALF_YEARLY, BOARD_MEETING_OUTCOME) — others
correctly have no period at all, nothing to fix.

Reuses your real pipeline functions from main.py
(_extract_markdown_with_pages, _find_prior_insight_json, extract_flags,
analyze_filing, estimate_period_from_exchange_ts) rather than
duplicating that logic — same "one shared implementation" principle
used for the NSE backfill.

USAGE:
    python backfill_filing_periods.py
"""

from datetime import datetime, timedelta, timezone

from sentismetric.log import setup_logging, log
from sentismetric.db import SessionLocal
from sentismetric.models import Filing, FilingType, FilingStatus, Insight
from sentismetric.analyze.scorecard import quarter_label_from_dates

# Adjust to taste — this is the cost/accuracy dial. Filings older than
# this get the free estimate instead of a full re-analysis.
RECENT_MONTHS_THRESHOLD = 3


def backfill_filing_periods() -> dict:
    # local imports from main.py — these must exist there per the
    # period_fix.py / insights_validate_patch.py changes already applied
    from sentismetric.main import (
        _extract_markdown_with_pages,
        _find_prior_insight_json,
        estimate_period_from_exchange_ts,
    )
    from sentismetric.analyze.scorecard import extract_flags
    from sentismetric.analyze.insights import analyze_filing

    stats = {"accurate": 0, "estimated": 0, "skipped_no_period_found": 0, "errors": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_MONTHS_THRESHOLD * 30)

    with SessionLocal() as session:
        candidates = (
            session.query(Filing)
            .filter(Filing.filing_type.in_([
                FilingType.RESULTS_HALF_YEARLY.value,
                FilingType.BOARD_MEETING_OUTCOME.value,
            ]))
            .filter((Filing.period.is_(None)) | (Filing.period == ""))
            .filter(Filing.status.in_([FilingStatus.ANALYZED.value, FilingStatus.ALERTED.value]))
            .all()
        )
        log.info("backfill_filing_periods: %d filings need a period", len(candidates))

        for filing in candidates:
            is_recent = filing.exchange_ts and filing.exchange_ts.replace(tzinfo=timezone.utc) >= cutoff

            try:
                if is_recent:
                    # ---- accurate path: full re-extraction + re-analysis ----
                    if not filing.pdf_path:
                        log.warning("filing %s has no pdf_path, falling back to estimate", filing.id)
                        is_recent = False
                    else:
                        markdown, _ = _extract_markdown_with_pages(filing.pdf_path)
                        flags = extract_flags(markdown)
                        prev_insight_json = _find_prior_insight_json(session, filing.company_id, filing.period)
                        insight_data = analyze_filing(markdown, prev_insight_json=prev_insight_json, flags=flags)

                        period_end = insight_data.get("period_end_date")
                        if period_end:
                            filing.period = quarter_label_from_dates(period_end)
                        else:
                            # LLM found nothing even on a fresh read —
                            # fall back to estimate rather than leaving blank
                            filing.period = estimate_period_from_exchange_ts(filing.exchange_ts)

                        # refresh the Insight row too, since we just did a
                        # full re-analysis anyway — keeps prompt_version
                        # consistent with the content actually stored
                        existing = session.query(Insight).filter_by(filing_id=filing.id).one_or_none()
                        if existing:
                            existing.summary = insight_data.get("summary", existing.summary)
                            existing.positives = insight_data.get("positives", existing.positives)
                            existing.negatives = insight_data.get("negatives", existing.negatives)
                            existing.flags = flags
                            existing.prompt_version = insight_data.get("prompt_version", existing.prompt_version)

                        if filing.period:
                            stats["accurate"] += 1
                        else:
                            stats["skipped_no_period_found"] += 1

                if not is_recent:
                    # ---- cheap path: estimate only, no API calls ----
                    filing.period = estimate_period_from_exchange_ts(filing.exchange_ts)
                    if filing.period:
                        stats["estimated"] += 1
                    else:
                        stats["skipped_no_period_found"] += 1

                session.commit()

            except Exception as e:
                session.rollback()
                log.error("backfill failed for filing %s: %s", filing.id, e)
                stats["errors"] += 1

    return stats


if __name__ == "__main__":
    setup_logging(level="INFO")
    log.info("Starting filing-period backfill (recent=%d months get accurate re-analysis)...",
              RECENT_MONTHS_THRESHOLD)
    result = backfill_filing_periods()
    log.info("Backfill complete: %s", result)