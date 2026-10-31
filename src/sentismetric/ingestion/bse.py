from bse import BSE
from sentismetric.db import SessionLocal
from sentismetric.models import Company
from sentismetric.log import log

# BSE stock groups that correspond to the SME platform
# (confirmed empirically: SHREEREF is in group 'M'; companies that
# migrate to the main board, like INA/Insolation Energy, move OUT of
# these groups into Group 'B' — so this correctly tracks only current
# SME companies)
BSE_SME_GROUPS = ["M", "MS", "MT"]


def fetch_bse_sme_universe() -> list[dict]:
    """Fetch all BSE SME companies across the M/MS/MT groups,
    including both Active and Suspended companies (but not Delisted —
    those are done and won't file new announcements).
    Returns raw dicts from the bse package, one per company."""
    all_sme = []
    with BSE(download_folder="./") as bse:
        for grp in BSE_SME_GROUPS:
            for status in ["Active", "Suspended"]:
                results = bse.listSecurities(group=grp, status=status)
                log.info(
                    "fetched %d companies in BSE group %s (%s)",
                    len(results), grp, status,
                )
                all_sme.extend(results)
    return all_sme


def upsert_company(session, *, symbol: str, name: str, isin: str | None, group: str, scrip_code: str) -> Company:
    """Insert a new company, or update an existing one if it already exists."""
    row = (
        session.query(Company)
        .filter_by(exchange="BSE", symbol=symbol)
        .one_or_none()
    )
    if row is None:
        row = Company(
            exchange="BSE",
            symbol=symbol,
            name=name,
            isin=isin,
            series_or_group=group,
            scrip_code=scrip_code,
        )
        session.add(row)
        log.info("new BSE SME company: %s (%s)", symbol, name)
    else:
        row.name = name
        row.isin = isin
        row.series_or_group = group
        row.scrip_code = scrip_code
        row.active = True
    return row


def sync_bse_sme_universe() -> int:
    companies_data = fetch_bse_sme_universe()

    with SessionLocal() as session:
        for c in companies_data:
            upsert_company(
                session,
                symbol=c["scrip_id"],
                name=c["Scrip_Name"],
                isin=c.get("ISIN_NUMBER"),
                group=c["GROUP"],
                scrip_code=c["SCRIP_CD"],  # NEW — save it directly, no re-fetch needed
            )
        session.commit()

    log.info("BSE SME universe sync complete: %d companies", len(companies_data))
    return len(companies_data)


# CLASSIFY & POLL CYCYLE

import hashlib
from datetime import date, datetime
from pathlib import Path

import httpx

from sentismetric.config import settings
from sentismetric.models import Filing, FilingType

ANNOUNCEENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"

BSE_ANN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
}

RESULT_WORDS = ("financial result", "un-audited", "unaudited", "half year", "H1")
OUTCOME_WORDS = ("outcome of board", "outcome of the board")
INTIMATION_WORDS = ("board meeting", "intimation")

def classify (category: str, subject: str) -> str:
    """Pure function: maps BSE's category/subject text to our FIling Type.
        Order matters -- MOST specific checks FIRST."""
    text = f"{category} {subject}".lower()
    if any(w in text for w in RESULT_WORDS):
        return FilingType.RESULTS_HALF_YEARLY.value
    if any(w in text for w in OUTCOME_WORDS):
        return FilingType.BOARD_MEETING_OUTCOME.value
    if any(w in text for w in INTIMATION_WORDS):
        return FilingType.BOARD_MEETING_INTIMATION.value
    return FilingType.ROUTINE.value

def make_client() -> httpx.Client:
    return httpx.Client(headers=BSE_ANN_HEADERS, follow_redirects=True, timeout=15)

def fetch_todays_announcements(client: httpx.Client) -> list[dict]:
    """Fetch today's announcements across ALL BSE companies
    (mainboard + SME mixed). We filter down to SME afterward using
    our synced companies table."""
    today = date.today().strftime("%Y%m%d")
    params = {
         "pageno": 1,
        "strCat": -1,
        "strPrevDate": today,
        "strScrip": "",
        "strSearch": "P",
        "strToDate": today,
        "strType": "C",
        "subcategory": -1,
    }
    r = client.get(ANNOUNCEENTS_URL, params=params)
    r.raise_for_status()
    data = r.json()
    return data.get("Table", [])

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def download_attachment(client: httpx.Client, attachment_name: str) -> bytes | None:
    if not attachment_name:
        return None
    url = f"{ATTACHMENT_BASE_URL}/{attachment_name}"
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.content
    except httpx.HTTPError as e:
        log.warning("failed to download attachment %s: %s", attachment_name, e)
        return None
def store_pdf(content: bytes, ann_id: str) -> str:
    d = Path(settings.data_dir) / "pdfs" / "BSE"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{ann_id}.pdf"
    path.write_bytes(content)
    return str(path)

def poll_bse_once() -> int:
    """Fetch today's BSE announcements, keep only SME companies
    (cross-referenced against our synced companies table), dedupe,
    download PDFs, and store as Filing rows. Returns count inserted."""
    new_count = 0

    with SessionLocal() as session:
        # Fast, single DB query -- no external API calls needed,
        # since scrip_code is now stored locally from universe sync.
        sme_scrip_codes: dict[str, Company] = {
            c.scrip_code: c
            for c in session.query(Company).filter_by(exchange="BSE", active=True)
            if c.scrip_code
        }

        client = make_client()
        announcements = fetch_todays_announcements(client)
        log.info("fetched %d total BSE announcements today", len(announcements))

        for ann in announcements:
            scrip_cd = str(ann.get("SCRIP_CD"))
            company = sme_scrip_codes.get(scrip_cd)
            if company is None:
                continue  # not an SME company -> ignore

            ann_id = ann["NEWSID"]
            exists = (
                session.query(Filing)
                .filter_by(exchange="BSE", ann_id=ann_id)
                .one_or_none()
            )
            if exists:
                continue

            attachment_name = ann.get("ATTACHMENTNAME")
            pdf_bytes = download_attachment(client, attachment_name)
            content_hash = sha256_bytes(pdf_bytes) if pdf_bytes else None

            if content_hash:
                dup = (
                    session.query(Filing)
                    .filter_by(content_hash=content_hash)
                    .one_or_none()
                )
                if dup:
                    continue

            pdf_path = store_pdf(pdf_bytes, ann_id) if pdf_bytes else None
            exchange_ts = datetime.fromisoformat(ann["NEWS_DT"])

            filing = Filing(
                company_id=company.id,
                exchange="BSE",
                ann_id=ann_id,
                category_raw=ann.get("CATEGORYNAME", ""),
                filing_type=classify(ann.get("CATEGORYNAME", ""), ann.get("HEADLINE", "")),
                exchange_ts=exchange_ts,
                pdf_path=pdf_path,
                content_hash=content_hash,
            )
            session.add(filing)
            session.commit()
            new_count += 1
            log.info("filing stored: BSE %s %s", company.symbol, filing.filing_type)

        client.close()

    return new_count

if __name__ == "__main__":
    from sentismetric.log import setup_logging
    setup_logging(level="INFO")
    sync_bse_sme_universe()
    inserted = poll_bse_once()
    log.info("poll complete: %d new filings", inserted)