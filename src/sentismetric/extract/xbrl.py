from lxml import etree

CONCEPT_MAP = {
    "RevenueFromOperations": "revenue",
    "ProfitLossForThePeriod": "pat",
    "BasicEarningsLossPerShareFromContinuingOperations": "eps",
    "BorrowingsCurrent": "debt_current",
    "BorrowingsNoncurrent": "debt_noncurrent",
    "DebtEquityRatio": "debt_equity_ratio",
    "Expenses": "total_expenses",
}


class NotXBRLError(ValueError):
    """Raised when a file that should be XBRL is actually HTML (NSE block
    page) or otherwise not valid XML. Lets callers distinguish 'NSE
    blocked us' from a genuine parse bug."""


def parse_xbrl(path: str) -> dict:
    # cheap guard: sniff the first bytes for an HTML signature before
    # handing the file to lxml. Catches NSE block/error pages with a
    # clear error instead of a confusing tag-mismatch deep in the parser.
    with open(path, "rb") as f:
        head = f.read(512).lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        raise NotXBRLError(
            f"{path} is HTML, not XBRL — NSE likely returned a block/error "
            f"page (probably rate-limited from an unthrottled fetch loop)."
        )

    tree = etree.parse(path)
    root = tree.getroot()

    contexts = {}  # id -> (start, end) period
    for ctx in root.iter("{*}context"):
        cid = ctx.get("id")
        period = ctx.find("{*}period")
        if period is not None:
            start = period.findtext("{*}startDate")
            end = period.findtext("{*}endDate") or period.findtext("{*}instant")
            contexts[cid] = (start, end)

    facts = {}
    for el in root.iter():
        local = etree.QName(el).localname if el.tag is not etree.Comment else None
        if local in CONCEPT_MAP and el.text:
            facts.setdefault(CONCEPT_MAP[local], []).append({
                "value": float(el.text),
                "period": contexts.get(el.get("contextRef")),
            })
    return facts


def fetch_xbrl(nse_session, url: str, dest_path: str) -> str:
    """Fetch one XBRL doc using a WARMED, RATE-LIMITED NseSession —
    not a bare httpx.get(). This is the actual fix for the block-page
    failures: a single isolated request is invisible to NSE's anti-bot
    system, but a fast unthrottled loop over many symbols gets flagged
    and blocked, after which every request returns the same HTML page
    regardless of which symbol it's for.

    nse_session must be a real sentismetric.ingestion.nse_session.NseSession
    instance, reused across the whole calling loop (create it once
    outside the loop, not per-symbol).
    """
    import os

    if nse_session._client is None:
        nse_session._warm()
    nse_session._limiter.wait()  # <-- the actual throttling that was missing

    resp = nse_session._client.get(url, timeout=20)
    resp.raise_for_status()
    body = resp.content

    # validate BEFORE saving — reject HTML block pages so a corrupt file
    # can never land in data/xbrl/NSE/ again
    sniff = body.lstrip()[:512].lower()
    ctype = resp.headers.get("content-type", "").lower()
    looks_html = sniff.startswith(b"<!doctype html") or sniff.startswith(b"<html") or "text/html" in ctype
    looks_xml = sniff.startswith(b"<?xml") or b"<xbrl" in sniff or "xml" in ctype

    if looks_html or not looks_xml:
        raise NotXBRLError(
            f"NSE returned non-XBRL for {url} "
            f"(content-type={ctype!r}, starts with {sniff[:40]!r}). "
            f"Likely still rate-limited/blocked — wait before retrying."
        )

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(body)
    return dest_path    