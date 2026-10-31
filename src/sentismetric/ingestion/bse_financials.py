"""
src/sentismetric/ingestion/bse_financials.py

BSE SME financials, sourced ONLY from the exchange's structured XBRL
(inline-XBRL .html "Integrated Finance" files, plus legacy XBRL .xml for
older filings). Never OCR. Values are stored in rupees, same as the NSE
path (inline `scale='7'` display values are multiplied out).

Flow
  Corp_FinanceResult_ng_new (per company, FlagDur=7 = full history)
    -> one best candidate file per period label
    -> fetch via a real Chromium session (Akamai blocks plain HTTP)
    -> parse tags -> Financials row (skip if (company, period) exists)

Shared by backfill_bse_financials.py (one-time) and
poll_bse_recent() (nightly top-up).
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime

from sentismetric.log import log

BSE_PAGE = "https://www.bseindia.com/corporates/Comp_Resultsnew.aspx"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/Corp_FinanceResult_ng_new/w"
XBRL_BASE = "https://www.bseindia.com/XBRLFILES/"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# field -> concept local-names in priority order
FIELD_CONCEPTS: dict[str, list[str]] = {
    "revenue": ["RevenueFromOperations"],
    "pat": ["ProfitLossForThePeriod", "ProfitLossForPeriod"],
    "eps": ["BasicEarningsLossPerShareFromContinuingOperations",
            "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"],
    "debt_current": ["BorrowingsCurrent"],
    "debt_noncurrent": ["BorrowingsNoncurrent"],
    "debt_equity_ratio": ["DebtEquityRatio"],
    "total_expenses": ["Expenses"],
}
_CONCEPT_TO_FIELD = {c: f for f, cs in FIELD_CONCEPTS.items() for c in cs}
_DURATION_FIELDS = ("revenue", "pat", "total_expenses", "eps")

_QUARTER_LETTER = {"J": 1, "S": 2, "D": 3, "M": 4}


# --------------------------------------------------------------------------
# Browser session (Akamai blocks plain HTTP clients; a real page context works)
# --------------------------------------------------------------------------

class BseBrowserSession:
    def __init__(self, headless: bool = True, settle_ms: int = 9000):
        self.headless = headless
        self.settle_ms = settle_ms
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, args=["--disable-http2"])
        ctx = self._browser.new_context(user_agent=UA, locale="en-IN")
        self._page = ctx.new_page()
        try:
            self._page.goto(BSE_PAGE, wait_until="commit", timeout=60000)
        except Exception as e:  # often fine with wait_until="commit"
            log.warning("bse goto raised (usually fine): %s", e)
        self._page.wait_for_timeout(self.settle_ms)

    def close(self):
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._pw = self._browser = self._page = None

    def restart(self):
        self.close()
        time.sleep(3)
        self.start()

    def get_text(self, url: str) -> tuple[int, str]:
        res = self._page.evaluate(
            """async (u) => { const ac = new AbortController();
                 const t = setTimeout(() => ac.abort(), 45000);
                 try { const r = await fetch(u, {signal: ac.signal});
                       const b = await r.text(); clearTimeout(t);
                       return {s: r.status, b: b}; }
                 catch (e) { clearTimeout(t); return {s: -1, b: String(e)}; } }""",
            url,
        )
        return res["s"], res["b"]

    def get_text_checked(self, url: str, retries: int = 2) -> str:
        """Fetch with restart-on-block. Raises on persistent failure."""
        last = None
        for attempt in range(retries + 1):
            status, body = self.get_text(url)
            blocked = status in (403, -1) or "<title>access denied" in body[:600].lower()
            if status == 200 and not blocked:
                return body
            last = f"status={status}"
            log.warning("bse fetch %s attempt %d failed (%s)", url[-80:], attempt + 1, last)
            if attempt < retries:
                self.restart()
        raise RuntimeError(f"bse fetch failed: {last}")


# --------------------------------------------------------------------------
# Row selection
# --------------------------------------------------------------------------

def label_from_quarter_code(qc: str | None) -> tuple[str, str, int] | None:
    """'MQ2025-2026' -> ('Q4-FY2025-26', 'Q', 2025). Cumulative ('C') rows
    are skipped: they duplicate the same file already listed as a quarter
    and would mislabel annual / 9-month figures."""
    if not qc:
        return None
    m = re.match(r"^([JSDM])([QHC])(\d{4})-(\d{4})$", qc.strip())
    if not m:
        return None
    letter, kind, y1, _y2 = m.groups()
    if kind == "C":
        return None
    start = int(y1)
    q = _QUARTER_LETTER[letter]
    return f"Q{q}-FY{start}-{str(start + 1)[-2:]}", kind, start


def pick_candidates(rows: list[dict], since_fy: int | None = None) -> dict[str, list[tuple]]:
    """Group a company's result rows by period label and return, per label,
    candidate files sorted best-first as (name, nature, provisional_label).

    Preference: Standalone inline-XBRL .html > legacy .xml > Consolidated
    .html (same preference the NSE path uses); quarterly over half-year
    rows; most recently filed first (so later revisions win)."""
    by_label: dict[str, list[tuple]] = {}
    for r in rows:
        parsed = label_from_quarter_code(r.get("quarter_code"))
        if parsed is None:
            continue
        label, kind, fy_start = parsed
        if since_fy is not None and fy_start < since_fy:
            continue
        type_rank = 0 if kind == "Q" else 1
        stamp = r.get("Fld_CreateDate") or ""
        nature = (r.get("Fld_NatureOfReport") or "None")
        name = r.get("XMLName")
        cname = r.get("Consol_XMLName")

        if name:
            low = name.lower()
            if low.endswith(".html"):
                nrank = 0 if nature == "Standalone" else (2 if nature == "Consolidated" else 1)
            elif low.endswith(".xml"):
                nrank = 1
            else:
                nrank = 3
            by_label.setdefault(label, []).append(((nrank, type_rank, _neg(stamp)), name, nature))
        if cname and cname != name and cname.lower().endswith(".html"):
            by_label.setdefault(label, []).append(((2, type_rank, _neg(stamp)), cname, "Consolidated"))

    out: dict[str, list[tuple]] = {}
    for label, cands in by_label.items():
        cands.sort(key=lambda c: c[0])
        seen, ordered = set(), []
        for _rank, name, nature in cands:
            if name in seen:
                continue
            seen.add(name)
            ordered.append((name, nature, label))
        out[label] = ordered
    return out


def _neg(stamp: str):
    """Sort key making later ISO timestamps sort first."""
    return tuple(-ord(c) for c in stamp)


# --------------------------------------------------------------------------
# XBRL parsing (inline .html and legacy .xml)
# --------------------------------------------------------------------------

_CTX_RE = re.compile(r"<(?:\w+:)?context\b[^>]*?\bid\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</(?:\w+:)?context>",
                     re.I | re.S)
_DATE_RE = {
    "start": re.compile(r"<(?:\w+:)?startDate>\s*([^<\s]+)", re.I),
    "end": re.compile(r"<(?:\w+:)?endDate>\s*([^<\s]+)", re.I),
    "instant": re.compile(r"<(?:\w+:)?instant>\s*([^<\s]+)", re.I),
}
_IX_RE = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.I | re.S)
_ATTR_RE = re.compile(r"([\w:\-]+)\s*=\s*[\"']([^\"']*)[\"']")


def _parse_date(s: str | None) -> date | None:
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


def parse_contexts(text: str) -> dict[str, dict]:
    ctxs = {}
    for cid, body in _CTX_RE.findall(text):
        has_dim = bool(re.search(r"<(?:\w+:)?(scenario|segment)\b|xbrldi:", body, re.I))
        g = {k: (rx.search(body).group(1) if rx.search(body) else None) for k, rx in _DATE_RE.items()}
        ctxs[cid] = {
            "dim": has_dim,
            "start": _parse_date(g["start"]),
            "end": _parse_date(g["end"]),
            "instant": _parse_date(g["instant"]),
        }
    return ctxs


def parse_facts(text: str) -> list[tuple[str, str, float, int]]:
    """Return [(field, contextRef, value_in_rupees_or_ratio)] for mapped
    concepts. Handles inline XBRL (scale/sign attributes) and legacy
    plain-XML instances."""
    facts: list[tuple[str, str, float, int]] = []

    for attrs_raw, inner in _IX_RE.findall(text):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(attrs_raw)}
        name = attrs.get("name", "")
        local = name.split(":")[-1]
        field = _CONCEPT_TO_FIELD.get(local)
        if not field:
            continue
        raw = re.sub(r"<[^>]+>", "", inner).strip().replace(",", "")
        fmt = attrs.get("format", "").lower()
        if raw in ("", "-", "—") and "zerodash" in fmt:
            val = 0.0
        else:
            try:
                val = float(raw)
            except ValueError:
                continue
        scale = int(attrs.get("scale", "0") or 0)
        val = round(val * 10 ** scale, 4)
        if attrs.get("sign") == "-":
            val = -val
        facts.append((field, attrs.get("contextref", ""), val, FIELD_CONCEPTS[field].index(local)))

    if facts:
        return facts

    # legacy plain-XML instance
    for concept, field in _CONCEPT_TO_FIELD.items():
        rx = re.compile(rf"<[\w\-]+:{concept}\b([^>]*)>\s*([^<]+?)\s*</", re.I)
        for attrs_raw, raw in rx.findall(text):
            attrs = {k.lower(): v for k, v in _ATTR_RE.findall(attrs_raw)}
            try:
                val = float(raw.replace(",", ""))
            except ValueError:
                continue
            facts.append((field, attrs.get("contextref", ""), val, FIELD_CONCEPTS[field].index(concept)))
    return facts


def parse_bse_xbrl(text: str) -> dict | None:
    """Return {'period_end': date, 'duration_days': int, 'values': {field: v},
    'raw': {...}} for the CURRENT reporting period, or None.

    Current period = non-dimensional duration context carrying results
    facts, with the latest end date, then the SHORTEST duration (so a Q4
    filing's quarter column beats its full-year column; a half-yearly
    filer's only column is its half). Annual / 9-month-only files (>200
    days) are rejected rather than mislabelled as a quarter."""
    ctxs = parse_contexts(text)
    facts = parse_facts(text)
    if not ctxs or not facts:
        return None

    dur_ctx_ids = {
        cid for _f, cid, _v, _p in facts
        if _f in _DURATION_FIELDS and cid in ctxs
        and not ctxs[cid]["dim"] and ctxs[cid]["start"] and ctxs[cid]["end"]
    }
    if not dur_ctx_ids:
        return None

    def sort_key(cid):
        c = ctxs[cid]
        return (-c["end"].toordinal(), (c["end"] - c["start"]).days)

    best = sorted(dur_ctx_ids, key=sort_key)[0]
    cur = ctxs[best]
    days = (cur["end"] - cur["start"]).days
    if days > 200:
        return None

    inst_ids = {cid for cid, c in ctxs.items() if not c["dim"] and c["instant"] == cur["end"]}

    values: dict[str, float] = {}
    for field in FIELD_CONCEPTS:
        if field in _DURATION_FIELDS:
            ok = {best}
        else:  # balance-sheet items sit on the instant at period end; ratio may be either
            ok = inst_ids | ({best} if field == "debt_equity_ratio" else set())
        hits = [(p, i, v) for i, (f, cid, v, p) in enumerate(facts) if f == field and cid in ok]
        if hits:
            values[field] = min(hits)[2]

    if not values.get("revenue") and values.get("pat") is None:
        return None

    return {
        "period_end": cur["end"],
        "duration_days": days,
        "values": values,
        "raw": {"period": [str(cur["start"]), str(cur["end"])], "values": values},
    }


# --------------------------------------------------------------------------
# Persist
# --------------------------------------------------------------------------

def period_label_from_end(end: date) -> str | None:
    from sentismetric.analyze.scorecard import quarter_label_from_dates
    return quarter_label_from_dates(end.isoformat())


def process_company_rows(company, rows: list[dict], session, browser: BseBrowserSession,
                         limiter=None, since_fy: int | None = None) -> int:
    """Insert Financials for any periods this company is missing. Returns
    number of NEW rows. Fetches at most one good file per missing period."""
    from sentismetric.models import Financials
    from sqlalchemy.exc import IntegrityError

    cands_by_label = pick_candidates(rows, since_fy=since_fy)
    if not cands_by_label:
        return 0

    have = {p for (p,) in session.query(Financials.period).filter_by(company_id=company.id).all()}
    inserted = 0

    for label, cands in sorted(cands_by_label.items()):
        if label in have:
            continue

        parsed = None
        used = None
        for name, nature, _prov in cands[:3]:
            try:
                if limiter:
                    limiter.wait()
                body = browser.get_text_checked(XBRL_BASE + name)
                parsed = parse_bse_xbrl(body)
            except Exception as e:
                log.warning("bse %s %s: fetch/parse failed for %s: %s", company.symbol, label, name[-50:], e)
                continue
            if parsed:
                used = (name, nature)
                break

        if not parsed:
            log.info("bse %s %s: no usable XBRL (annual-only/empty/unparseable)", company.symbol, label)
            continue

        true_label = period_label_from_end(parsed["period_end"])
        if true_label is None:
            continue
        if true_label != label:
            log.info("bse %s: row label %s != XBRL period %s, using XBRL", company.symbol, label, true_label)
        if true_label in have:
            continue

        v = parsed["values"]
        raw = dict(parsed["raw"])
        raw.update({"_source": "BSE", "_file": used[0], "_nature": used[1],
                    "_duration_days": parsed["duration_days"]})
        fin = Financials(
            company_id=company.id, period=true_label,
            revenue=v.get("revenue"), pat=v.get("pat"), eps=v.get("eps"),
            debt_current=v.get("debt_current"), debt_noncurrent=v.get("debt_noncurrent"),
            debt_equity_ratio=v.get("debt_equity_ratio"), total_expenses=v.get("total_expenses"),
            raw=raw, source="XBRL",
        )
        try:
            session.add(fin)
            session.commit()
            have.add(true_label)
            inserted += 1
        except IntegrityError:
            session.rollback()
    return inserted


def load_active_bse_companies(session) -> dict[int, "Company"]:
    from sentismetric.models import Company
    out = {}
    for c in session.query(Company).filter_by(exchange="BSE", active=True).all():
        code = (c.scrip_code or c.symbol or "").strip()
        if code.isdigit():
            out[int(code)] = c
    return out


def fetch_company_rows(browser: BseBrowserSession, scrip: int, flag_dur: int = 7) -> list[dict]:
    url = f"{BSE_API}?SCRIP_CD={scrip}&FlagDur={flag_dur}&HFQ=&ISUBGROUP_CODE=&segment=C"
    body = browser.get_text_checked(url)
    return (json.loads(body).get("Table")) or []


def poll_bse_recent(session, browser: BseBrowserSession, flag_dur: int = 3, limiter=None) -> int:
    """Nightly top-up. flag_dur 3 = last 15 days, 4 = last month. One bulk
    call, filtered to tracked BSE SME scrip codes."""
    companies = load_active_bse_companies(session)
    url = f"{BSE_API}?SCRIP_CD=&FlagDur={flag_dur}&HFQ=&ISUBGROUP_CODE=&segment=C"
    rows = (json.loads(browser.get_text_checked(url)).get("Table")) or []
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        sc = r.get("Scrip_cd")
        if sc in companies:
            grouped.setdefault(int(sc), []).append(r)
    total = 0
    for sc, crow in grouped.items():
        total += process_company_rows(companies[sc], crow, session, browser, limiter=limiter)
    log.info("bse recent poll: %d tracked companies in window, %d new financials", len(grouped), total)
    return total