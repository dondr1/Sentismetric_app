import hashlib
from datetime import datetime
from pathlib import Path
from nse import NSE

from sentismetric.config import settings
from sentismetric.db import SessionLocal
from sentismetric.models import Company, Filing, FilingType
from sentismetric.log import log
from sentismetric.extract.xbrl import parse_xbrl, NotXBRLError
from sentismetric.extract.nse_browser_fetch import NseBrowserSession, fetch_xbrl_via_browser
from sentismetric.models import Financials
RESULT_WORDS = ("financial result", "un-audited", "unaudited", "half year", "H1")
OUTCOME_WORDS = ("outcome of board", "outcome of the board")
INTIMATION_WORDS = ("board meeting", "intimation")


def classify(category: str, subject: str) -> str:
    text = f"{category} {subject}".lower()
    if any(w in text for w in RESULT_WORDS):
        return FilingType.RESULTS_HALF_YEARLY.value
    if any(w in text for w in OUTCOME_WORDS):
        return FilingType.BOARD_MEETING_OUTCOME.value
    if any(w in text for w in INTIMATION_WORDS):
        return FilingType.BOARD_MEETING_INTIMATION.value
    return FilingType.ROUTINE.value


def upsert_company(session, *, symbol: str, name: str | None = None, isin: str | None = None) -> Company:
    row = (
        session.query(Company)
        .filter_by(exchange="NSE", symbol=symbol)
        .one_or_none()
    )
    if row is None:
        row = Company(
            exchange="NSE",
            symbol=symbol,
            name=name or symbol,  # real name filled in later, from announcements
            isin=isin,
            series_or_group="SME",
        )
        session.add(row)
        log.info("new NSE SME company: %s", symbol)
    else:
        if name:
            row.name = name
        if isin:
            row.isin = isin
        row.active = True
    return row


def sync_nse_sme_universe() -> int:
    with NSE(download_folder="./") as nse:
        result = nse.listSme()
    companies_data = result.get("data", [])

    with SessionLocal() as session:
        for c in companies_data:
            upsert_company(session, symbol=c["symbol"])
        session.commit()

    log.info("NSE SME universe sync complete: %d companies", len(companies_data))
    return len(companies_data)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def poll_nse_once() -> int:
    new_count = 0

    with SessionLocal() as session:
        nse_companies = {
            c.symbol: c
            for c in session.query(Company).filter_by(exchange="NSE", active=True)
        }

        with NSE(download_folder="./") as nse:
            announcements = nse.announcements(index="sme")
            log.info("fetched %d NSE SME announcements today", len(announcements))

            for ann in announcements:
                symbol = ann.get("symbol")
                company = nse_companies.get(symbol)
                if company is None:
                    continue

                # Enrich company name/isin the first time we see real data for it
                real_name = ann.get("sm_name")
                real_isin = ann.get("sm_isin")
                changed = False
                if real_name and company.name == company.symbol:
                    company.name = real_name
                    changed = True
                if real_isin and not company.isin:
                    company.isin = real_isin
                    changed = True
                if changed:
                    session.commit()

                ann_id = str(ann.get("seq_id"))
                exists = (
                    session.query(Filing)
                    .filter_by(exchange="NSE", ann_id=ann_id)
                    .one_or_none()
                )
                if exists:
                    continue

                pdf_path = None
                content_hash = None
                attach_url = ann.get("attchmntFile")
                if attach_url:
                    try:
                        downloaded_path = nse.download_document(
                            attach_url, folder=str(Path(settings.data_dir) / "pdfs" / "NSE")
                        )
                        pdf_bytes = Path(downloaded_path).read_bytes()
                        content_hash = sha256_bytes(pdf_bytes)
                        pdf_path = str(downloaded_path)
                    except Exception as e:
                        log.warning("failed to download NSE attachment: %s", e)

                if content_hash:
                    dup = (
                        session.query(Filing)
                        .filter_by(content_hash=content_hash)
                        .one_or_none()
                    )
                    if dup:
                        continue

                exchange_ts_raw = ann.get("an_dt")
                exchange_ts = datetime.strptime(exchange_ts_raw, "%d-%b-%Y %H:%M:%S")

                filing = Filing(
                    company_id=company.id,
                    exchange="NSE",
                    ann_id=ann_id,
                    category_raw=ann.get("desc", ""),
                    filing_type=classify(ann.get("desc", ""), ann.get("attchmntText", "")),
                    exchange_ts=exchange_ts,
                    pdf_path=pdf_path,
                    content_hash=content_hash,
                )
                session.add(filing)
                session.commit()
                new_count += 1
                log.info("filing stored: NSE %s %s", company.symbol, filing.filing_type)

    return new_count


INTEGRATED_LISTING_API = "https://www.nseindia.com/api/integrated-filing-results"

# Design decision, not a fact: when both Standalone and Consolidated
# entries exist for the same company+period (real, confirmed pattern in
# NSE's data), the Financials table only allows ONE row per
# (company_id, period) — no standalone/consolidated column in the
# schema. Defaulting to Standalone as the more common base case for SME
# analysis. Flip this if you want Consolidated preferred instead.
PREFERRED_CONSOLIDATION = "Standalone"

# safety cap for the NIGHTLY poller specifically — at size=20 and
# totalCount in the thousands, don't crawl the whole history every
# night. The backfill script (backfill_nse_financials.py) has NO such
# cap; it's meant to walk the entire history once.
MAX_PAGES_PER_RUN = 25

LISTING_PAGE_SIZE = 20


def listing_url(page: int, size: int = LISTING_PAGE_SIZE) -> str:
    """Shared by both the nightly poller and the backfill script."""
    return (
        f"{INTEGRATED_LISTING_API}?index=sme"
        f"&type=Integrated%20Filing-%20Financials"
        f"&page={page}&size={size}"
    )


def process_integrated_filing_page(
    rows: list[dict],
    session,
    nse_companies: dict,
    browser: "NseBrowserSession",
) -> int:
    """Processes one page's worth of Integrated Filing rows: dedupes
    Standalone/Consolidated pairs (preferring PREFERRED_CONSOLIDATION),
    downloads + parses XBRL for anything new, inserts Financials rows.

    Shared by poll_nse_financial_results() (nightly, early-stops) and
    backfill_nse_financials.py (one-time, walks every page) — this is
    the correctness-critical logic; the two callers only differ in
    HOW MANY pages they walk and when they stop.

    Returns the count of NEW Financials rows inserted from this page.
    """
    # within-page dedup: prefer PREFERRED_CONSOLIDATION when both
    # Standalone/Consolidated exist for the same (symbol, period) — they
    # commonly land on the same page since they're usually filed
    # minutes apart. Cross-page duplicates (rarer) fall back to
    # first-seen-wins via the DB exists-check below — a known, accepted
    # edge case.
    by_key = {}
    for r in rows:
        symbol = r.get("symbol")
        if symbol not in nse_companies:
            continue
        qe_date_raw = r.get("qe_Date")
        if not qe_date_raw:
            continue
        key = (symbol, qe_date_raw)
        consolidation = r.get("consolidated")
        existing_pick = by_key.get(key)
        if existing_pick is None:
            by_key[key] = r
        elif consolidation == PREFERRED_CONSOLIDATION and existing_pick.get("consolidated") != PREFERRED_CONSOLIDATION:
            by_key[key] = r  # swap in the preferred variant

    page_new = 0
    for (symbol, qe_date_raw), r in by_key.items():
        company = nse_companies[symbol]

        xbrl_url = r.get("xbrl")
        if not xbrl_url or xbrl_url.strip() == "-":
            continue

        period_label = period_label_from_qe_date(qe_date_raw)
        if period_label is None:
            log.warning("couldn't parse qe_Date %r for %s, skipping", qe_date_raw, symbol)
            continue

        exists = (
            session.query(Financials)
            .filter_by(company_id=company.id, period=period_label)
            .one_or_none()
        )
        if exists:
            continue

        seq_id = r.get("seq_Id", "unknown")
        xbrl_dir = Path(settings.data_dir) / "xbrl" / "NSE"
        xbrl_path = xbrl_dir / f"{symbol}_{seq_id}.xml"

        try:
            fetch_xbrl_via_browser(browser, xbrl_url, str(xbrl_path))
            facts = parse_xbrl(str(xbrl_path))
        except NotXBRLError as e:
            log.warning("skipping XBRL for %s: %s", symbol, e)
            continue
        except Exception as e:
            log.warning("failed to fetch/parse XBRL for %s: %s", symbol, e)
            continue

        def first_value(concept):
            entries = facts.get(concept)
            return entries[0]["value"] if entries else None

        fin = Financials(
            company_id=company.id,
            period=period_label,
            revenue=first_value("revenue"),
            pat=first_value("pat"),
            eps=first_value("eps"),
            debt_current=first_value("debt_current"),
            debt_noncurrent=first_value("debt_noncurrent"),
            debt_equity_ratio=first_value("debt_equity_ratio"),
            total_expenses=first_value("total_expenses"),
            raw=facts,
            source="XBRL",
        )
        session.add(fin)
        session.commit()
        page_new += 1
        log.info("financials stored: NSE %s %s (%s)", symbol, period_label,
                 r.get("consolidated"))

    return page_new


def load_active_nse_companies(session) -> dict:
    """Shared helper — both callers need this same lookup."""
    return {
        c.symbol: c
        for c in session.query(Company).filter_by(exchange="NSE", active=True)
    }


def poll_nse_financial_results() -> int:
    """Fetch recent NSE SME Integrated Filing financials, download +
    parse their XBRL, and store into the financials table.

    FIXED (round 3 — the real fix): NSE migrated to a consolidated
    "Integrated Filing" system; the old nse.financial_results() package
    method was pointing at stale/deprecated data (hence the "-" XBRL
    fields and 404s). This now hits the confirmed-real listing endpoint
    directly: /api/integrated-filing-results?index=sme&type=Integrated
    Filing-Financials — same one NSE's own frontend uses, captured via
    DevTools. That endpoint is ALSO behind Akamai (same as the XBRL
    download), so it goes through the same browser session.

    Paginates newest-first, stopping early once a full page yields zero
    NEW inserts (caught up with previously-processed data) rather than
    crawling all ~240 pages every run — this is a nightly job, so older
    backlog is meant to be caught by backfill_nse_financials.py once,
    not by this function repeatedly.
    """
    new_count = 0

    with SessionLocal() as session:
        nse_companies = load_active_nse_companies(session)

        with NseBrowserSession() as browser:
            page = 1
            while page <= MAX_PAGES_PER_RUN:
                try:
                    payload = browser.get_json(listing_url(page))
                except Exception as e:
                    log.warning("failed to fetch integrated-filing listing page %d: %s", page, e)
                    break

                rows = payload.get("data", [])
                if not rows:
                    log.info("integrated-filing listing: no more rows at page %d, stopping", page)
                    break

                page_new = process_integrated_filing_page(rows, session, nse_companies, browser)
                new_count += page_new

                if page_new == 0:
                    log.info("page %d yielded zero new financials — caught up, stopping", page)
                    break

                page += 1

    return new_count


def period_label_from_qe_date(qe_date_raw: str) -> str | None:
    """qe_Date comes as 'DD-MON-YYYY' (e.g. '30-SEP-2025'), not ISO —
    convert to ISO first, then reuse the existing tested
    quarter_label_from_dates() rather than duplicating its quarter/FY
    logic here."""
    from datetime import datetime
    from sentismetric.analyze.scorecard import quarter_label_from_dates

    try:
        parsed = datetime.strptime(qe_date_raw.strip().title(), "%d-%b-%Y")
    except ValueError:
        return None
    iso = parsed.strftime("%Y-%m-%d")
    return quarter_label_from_dates(iso)


if __name__ == "__main__":
    from sentismetric.log import setup_logging
    setup_logging(level="INFO")
    sync_nse_sme_universe()
    inserted = poll_nse_once()
    log.info("poll complete: %d new filings", inserted)