from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from sentismetric.log import setup_logging, log
from sentismetric.db import init_db, get_next_filing, SessionLocal
from sentismetric.config import settings
from sentismetric.models import Filing, FilingStatus, FilingType, Company, Financials, Insight, Chunk, Watchlist
from sentismetric.ingestion.bse import poll_bse_once, sync_bse_sme_universe
from sentismetric.ingestion.nse import poll_nse_once, sync_nse_sme_universe

from sentismetric.extract.pdf import triage, extract_digital_page, page_to_png, chunk_pages, PageText
from sentismetric.extract.vision_backend import VisionBackend
from sentismetric.analyze.scorecard import extract_flags, get_metrics_for_period, notability, quarter_label_from_dates
from sentismetric.analyze.insights import analyze_filing
from sentismetric.rag.embed_backend import get_backend as get_embed_backend
from sentismetric.delivery.whatsapp import alert_all


NOTABILITY_THRESHOLD = getattr(settings, "notability_threshold", 4.0)
# Non-watchlist companies need a much higher score to alert — watchlist
# companies keep the normal threshold above. Raises the bar for the
# general feed while never missing anything about tracked companies.
NON_WATCHLIST_THRESHOLD = getattr(settings, "non_watchlist_threshold", 10.0)


def estimate_period_from_exchange_ts(exchange_ts: datetime) -> str | None:
    """FALLBACK ONLY — used when the LLM's grounded period_end_date
    (from analyze_filing(), validated against the filing's own text)
    comes back null. Maps a filing's publish date to the quarter it
    most likely REPORTS ON, based on standard SEBI reporting-deadline
    windows (India fiscal year: Apr-Mar):
        published Jul/Aug/Sep  -> reporting Q1 (Apr-Jun)
        published Oct/Nov/Dec  -> reporting Q2 (Jul-Sep)
        published Jan/Feb/Mar  -> reporting Q3 (Oct-Dec, previous cal. year)
        published Apr/May/Jun  -> reporting Q4/Annual (Jan-Mar)
    Less reliable than the grounded extraction — a late or revised
    filing could break this — only reached for when the LLM genuinely
    found no explicit period in the document.
    """
    month = exchange_ts.month
    year = exchange_ts.year

    if month in (7, 8, 9):
        end_date = f"{year}-06-30"
    elif month in (10, 11, 12):
        end_date = f"{year}-09-30"
    elif month in (1, 2, 3):
        end_date = f"{year - 1}-12-31"
    elif month in (4, 5, 6):
        end_date = f"{year}-03-31"
    else:
        return None

    return quarter_label_from_dates(end_date)


def poll_all() -> None:
    try:
        count = poll_bse_once()
        log.info("BSE poll: %d new filings", count)
    except Exception:
        log.exception("BSE poll failed")

    try:
        count = poll_nse_once()
        log.info("NSE poll: %d new filings", count)
    except Exception:
        log.exception("NSE poll failed")


# ---------------------------------------------------------------------------
# Extraction helper — digital + vision, assembled with [Page N] tags that
# extract_flags() and analyze_filing() both expect
# ---------------------------------------------------------------------------

def _extract_markdown_with_pages(pdf_path: str) -> tuple[str, list[dict]]:
    vision = VisionBackend.get_backend()
    pages_info = triage(pdf_path)  # [(page_no, is_digital)]

    page_records = []
    for page_no, is_digital in pages_info:
        if is_digital:
            text = extract_digital_page(pdf_path, page_no)
            method = "digital"
        else:
            png_bytes = page_to_png(pdf_path, page_no)
            text = vision.page_to_markdown(png_bytes)
            method = "vision"
        page_records.append({"page": page_no, "text": text, "method": method})

    markdown_with_pages = "\n\n".join(
        f"[Page {p['page']}]\n{p['text']}" for p in page_records
    )
    return markdown_with_pages, page_records


def _find_prior_insight_json(session, company_id: int, current_period: str | None) -> str | None:
    """Best-effort vs_previous wiring — a documented, previously-unwired
    gap. Looks up the most recent Insight for this company whose filing
    period sorts before the current one."""
    if not current_period:
        return None
    import json

    prior = (
        session.query(Insight)
        .join(Filing, Filing.id == Insight.filing_id)
        .filter(Filing.company_id == company_id)
        .filter(Filing.period < current_period)
        .filter(Filing.period.like("Q%-FY%"))
        .order_by(Filing.period.desc())
        .first()
    )
    if prior is None:
        return None
    return json.dumps({
        "summary": prior.summary,
        "positives": prior.positives,
        "negatives": prior.negatives,
    })


def _store_chunks(session, filing_id: int, page_records: list[dict]) -> None:
    page_texts = [
        PageText(page=p["page"], text=p["text"], method=p["method"])
        for p in page_records
    ]
    chunks = chunk_pages(page_texts)  # returns list of dicts: text/page_start/page_end

    if not chunks:
        return

    backend = get_embed_backend()

    def _get(c, key):
        return getattr(c, key, None) if hasattr(c, key) else c.get(key)

    texts = [_get(c, "text") for c in chunks]
    embeddings = backend.embed(texts, input_type="document")

    for chunk, embedding in zip(chunks, embeddings):
        session.add(Chunk(
            filing_id=filing_id,
            page_start=_get(chunk, "page_start"),
            page_end=_get(chunk, "page_end"),
            text=_get(chunk, "text"),
            embedding=embedding,
        ))


# ---------------------------------------------------------------------------
# The real process_one_filing() — replaces the old EXTRACTED-only stub
# ---------------------------------------------------------------------------

def process_one_filing() -> None:
    """Pulls the next NEW filing off the queue and runs it through
    extract -> analyze -> notability -> alert -> status update.

    Errors are isolated: any exception lands the filing in ERROR with
    the message stored, and does NOT propagate — one bad filing must
    never stall the queue.
    """
    filing_row = get_next_filing(FilingStatus.NEW.value)
    if filing_row is None:
        return

    log.info(
        "processing filing id=%s exchange=%s ann_id=%s",
        filing_row["id"], filing_row["exchange"], filing_row["ann_id"],
    )

    with SessionLocal() as session:
        filing = session.query(Filing).filter_by(id=filing_row["id"]).one()
        company = session.get(Company, filing.company_id)

        try:
            # ---- extract ----
            if not filing.pdf_path:
                raise ValueError("no pdf_path on filing — nothing to extract")

            markdown, page_records = _extract_markdown_with_pages(filing.pdf_path)
            filing.status = FilingStatus.EXTRACTED.value
            session.commit()

            # ---- analyze: flags + LLM insight ----
            flags = extract_flags(markdown)

            prev_insight_json = _find_prior_insight_json(session, filing.company_id, filing.period)
            insight_data = analyze_filing(markdown, prev_insight_json=prev_insight_json, flags=flags)
            # analyze_filing() already runs validate_quotes() internally
            # and sets insight_data["prompt_version"]

            # ---- resolve period: grounded LLM extraction first, ----
            # ---- publish-date estimate as fallback ----
            if not filing.period:
                llm_period_end = insight_data.get("period_end_date")
                if llm_period_end:
                    filing.period = quarter_label_from_dates(llm_period_end)
                elif filing.filing_type in (
                    FilingType.RESULTS_HALF_YEARLY.value,
                    FilingType.BOARD_MEETING_OUTCOME.value,
                ):
                    filing.period = estimate_period_from_exchange_ts(filing.exchange_ts)
                if filing.period:
                    session.commit()

            # ---- analyze: financials-derived metrics ----
            # Financials rows are populated by the SEPARATE nightly
            # poll_nse_financial_results() job, not here — this just
            # reads whatever's already landed for this period. Empty
            # metrics degrade gracefully rather than erroring.
            metrics = {}
            if filing.period:
                metrics = get_metrics_for_period(session, filing.company_id, filing.period) or {}

            financials_for_notability = {}  # prev_revenue dampening not wired yet

            score = notability(metrics, flags, insight_data, financials_for_notability)

            # ---- store insight ----
            existing = session.query(Insight).filter_by(filing_id=filing.id).one_or_none()
            if existing is None:
                existing = Insight(filing_id=filing.id)
                session.add(existing)
            existing.summary = insight_data.get("summary", "")
            existing.positives = insight_data.get("positives", [])
            existing.negatives = insight_data.get("negatives", [])
            existing.flags = flags
            existing.notability = score
            existing.prompt_version = insight_data.get("prompt_version", "")

            # ---- chunk + embed for RAG ----
            _store_chunks(session, filing.id, page_records)

            filing.status = FilingStatus.ANALYZED.value
            session.commit()

            # ---- notability gate -> alert ----
            is_watchlisted = (
                session.query(Watchlist)
                .filter_by(company_id=filing.company_id)
                .one_or_none()
                is not None
            )
            effective_threshold = NOTABILITY_THRESHOLD if is_watchlisted else NON_WATCHLIST_THRESHOLD

            if score >= effective_threshold:
                try:
                    alert_all(company.name, existing.summary)
                    filing.status = FilingStatus.ALERTED.value
                    session.commit()
                except Exception as e:
                    log.error("alert send failed for filing %s: %s", filing.id, e)

            log.info(
                "processed filing %s (%s): notability=%.1f status=%s",
                filing.id, company.symbol if company else "?", score, filing.status,
            )

        except Exception as e:
            session.rollback()
            filing.status = FilingStatus.ERROR.value
            filing.error = str(e)[:1024]
            session.commit()
            log.error("filing %s failed processing: %s", filing.id, e)


def process_queue() -> None:
    try:
        process_one_filing()
    except Exception:
        log.exception("process_queue failed")


def nightly() -> None:
    try:
        sync_bse_sme_universe()
    except Exception:
        log.exception("BSE universe sync failed")

    try:
        sync_nse_sme_universe()
    except Exception:
        log.exception("NSE universe sync failed")

    try:
        from sentismetric.ingestion.nse import poll_nse_financial_results
        count = poll_nse_financial_results()
        log.info("NSE financial results: %d new", count)
    except Exception:
        log.exception("NSE financial results poll failed")

    try:
        count = poll_bse_once()
        log.info("BSE reconciliation sweep: %d new filings", count)
    except Exception:
        log.exception("BSE reconciliation sweep failed")

    try:
        count = poll_nse_once()
        log.info("NSE reconciliation sweep: %d new filings", count)
    except Exception:
        log.exception("NSE reconciliation sweep failed")


def main() -> None:
    setup_logging()
    init_db()

    sched = BlockingScheduler(timezone="Asia/Kolkata")
    sched.add_job(
        poll_all, "interval", seconds=180, id="poll",
        max_instances=1, coalesce=True,
        next_run_time=datetime.now(ZoneInfo("Asia/Kolkata")),
    )
    sched.add_job(process_queue, "interval", seconds=30, id="process", max_instances=1, coalesce=True)
    sched.add_job(nightly, CronTrigger(hour=23, minute=30), id="nightly")

    log.info("scheduler starting")
    try:
        sched.start()
    except KeyboardInterrupt:
        log.info("shutting down scheduler")
        sched.shutdown()


if __name__ == "__main__":
    main()