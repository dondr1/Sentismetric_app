def compute_metrics(cur: dict, prev: dict | None, yoy: dict | None) -> dict:
    """Pure function: computes deterministic scorecard metrics from
    financials dicts. No LLM involved -> just arithmetic on real numbers.

    cur: current period's financials (revenue, pat, debt_current, etc.)
    prev: immediately preceding period's financials, or None if unavailable
    yoy: same-quarter-last-year financials, or None if unavailable
    """
    m: dict = {}

    if cur.get("revenue") and prev and prev.get("revenue"):
        m["revenue_hoh_pct"] = round(
            100 * (cur["revenue"] - prev["revenue"]) / abs(prev["revenue"]), 1
        )

    if cur.get("revenue") and yoy and yoy.get("revenue"):
        m["revenue_yoy_pct"] = round(
            100 * (cur["revenue"] - yoy["revenue"]) / abs(yoy["revenue"]), 1
        )

    if cur.get("pat") is not None and cur.get("revenue"):
        m["pat_margin_pct"] = round(100 * cur["pat"] / cur["revenue"], 1)

    # debt-related metrics, added tonight
    if cur.get("debt_current") is not None and cur.get("debt_noncurrent") is not None:
        m["total_debt"] = cur["debt_current"] + cur["debt_noncurrent"]

    if cur.get("debt_equity_ratio") is not None:
        m["debt_equity_ratio"] = cur["debt_equity_ratio"]

    if cur.get("total_expenses") and prev and prev.get("total_expenses"):
        m["expenses_hoh_pct"] = round(
            100 * (cur["total_expenses"] - prev["total_expenses"]) / abs(prev["total_expenses"]), 1
        )
    return m

def _parse_period_label(period: str) -> tuple[int, str] | None:
    """Parses a period label like 'Q4-FY2025-26' into (start_year, quarter)
    -- e.g. (2025, 'Q4'). This is the inverse of quarter_label_from_dates(),
    which produces that exact format. Returns None for anything that
    doesn't match (defensive -- malformed/legacy period strings, like the
    'Fourth Quarter' rows already cleaned out of the DB, should be
    skipped rather than crash).
    """
    import re
    m = re.match(r'^(Q[1-4])-FY(\d{4})-\d{2}$', period)
    if not m:
        return None
    quarter, year_str = m.group(1), m.group(2)
    return int(year_str), quarter

#flagging notability words:

FLAG_WORDS = {
    "order_win": (
        "order win", "bagged an order", "secured an order", "new order",
        "won a contract", "order book", "letter of award", "purchase order received",
        "work order", "loi received", "letter of intent",
    ),
    "capacity_expansion": (
        "capacity expansion", "expand capacity", "new facility", "commissioned",
        "additional capacity", "greenfield", "brownfield", "new plant",
        "expansion project", "enhance production", "installed capacity",
    ),
    "auditor_qualification": (
        "qualified opinion", "auditor qualification", "adverse opinion",
        "disclaimer of opinion", "emphasis of matter", "material uncertainty",
        "going concern", "qualified report",
    ),
    "pledge": (
        "pledge of shares", "shares pledged", "encumbrance", "pledged shares",
        "invocation of pledge", "release of pledge",
    ),
    "guidance_positive": (
        "strong outlook", "positive outlook", "growth guidance", "expects growth",
        "confident of growth", "robust demand", "healthy pipeline",
    ),
    "guidance_negative": (
        "weak outlook", "challenging environment", "headwinds", "subdued demand",
        "cautious outlook", "uncertain environment",
    ),
    "leadership_change": (
        "resignation of", "appointment of", "ceasing to be", "resigned as",
        "cessation of directorship", "change in key managerial personnel",
    ),
    "regulatory_action": (
        "show cause notice", "penalty imposed", "regulatory action",
        "sebi order", "adjudication order", "compounding application",
    ),
    "litigation": (
        "legal proceedings", "civil suit", "arbitration", "litigation",
        "court order against",
    ),
    "credit_rating_change": (
        "rating upgraded", "rating downgraded", "rating reaffirmed",
        "credit rating action", "outlook revised",
    ),
}

import re

def extract_flags(markdown_with_pages: str) -> dict:
    page_splits = re.split(r"\[Page (\d+)\]", markdown_with_pages)
    pages = []
    for i in range(1, len(page_splits), 2):
        page_num = int(page_splits[i])
        page_text = page_splits[i + 1] if i + 1 < len(page_splits) else ""
        pages.append((page_num, page_text))

    flags: dict = {}
    for flag_name, trigger_phrases in FLAG_WORDS.items():
        matches = []
        for page_num, page_text in pages:
            lower_text = page_text.lower()
            for phrase in trigger_phrases:
                idx = lower_text.find(phrase)
                if idx != -1:
                    # grab the surrounding sentence, not just the bare phrase
                    start = max(0, idx - 150)
                    end = min(len(page_text), idx + len(phrase) + 150)
                    context = page_text[start:end].strip()
                    matches.append((page_num, context))
        if matches:
            flags[flag_name] = matches

    return flags

def get_metrics_for_period(session, company_id: int, period: str) -> dict:
    from sentismetric.models import Financials

    cur_row = (
        session.query(Financials)
        .filter_by(company_id=company_id, period=period)
        .one_or_none()
    )
    if cur_row is None:
        return {}

    cur = {
        "revenue": float(cur_row.revenue) if cur_row.revenue is not None else None,
        "pat": float(cur_row.pat) if cur_row.pat is not None else None,
        "debt_current": float(cur_row.debt_current) if cur_row.debt_current is not None else None,
        "debt_noncurrent": float(cur_row.debt_noncurrent) if cur_row.debt_noncurrent is not None else None,
        "debt_equity_ratio": float(cur_row.debt_equity_ratio) if cur_row.debt_equity_ratio is not None else None,
        "total_expenses": float(cur_row.total_expenses) if cur_row.total_expenses is not None else None,
    }

    parsed = _parse_period_label(period)
    prev = None
    yoy = None

    if parsed:
        year, quarter = parsed
        quarter_seq = ["Q1", "Q2", "Q3", "Q4"]
        idx = quarter_seq.index(quarter) if quarter in quarter_seq else None

        if idx is not None:
            #immediately preceding quarter (handles year rollover: Q1 -> prior year's Q4)
            if idx > 0:
                prev_period = f"{quarter_seq[idx - 1]}-FY{year}-{str(year + 1)[-2:]}"
            else:
                prev_period = f"Q4-FY{year - 1}-{str(year)[-2:]}"

            prev_row = (
                session.query(Financials)
                .filter_by(company_id=company_id, period=prev_period)
                .one_or_none()
            )
            if prev_row:
                prev = {
                    "revenue": float(prev_row.revenue) if prev_row.revenue is not None else None,
                    "total_expenses": float(prev_row.total_expenses) if prev_row.total_expenses is not None else None,
                }

            #same quarter, prior fiscal year --> now genuinely unambiguous
            yoy_period = f"{quarter}-FY{year - 1}-{str(year)[-2:]}"
            yoy_row = (
                session.query(Financials)
                .filter_by(company_id=company_id, period=yoy_period)
                .one_or_none()
            )
            if yoy_row:
                yoy = {"revenue": float(yoy_row.revenue) if yoy_row.revenue is not None else None}

    return compute_metrics(cur, prev, yoy)

def notability(metrics: dict, flags: dict, insight: dict, financials: dict | None = None) -> float:
    """Score how notable a filing is, for alerting purposes. Higher = more
    worth interrupting the user for, regardless of whether the news is
    good or bad -- this scores magnitude of change, not sentiment.

    financials: optional dict with 'revenue' and 'prev_revenue' in
    absolute terms, used to dampen noisy percentage swings on tiny
    revenue bases (a company going ₹5L -> ₹15L is a 200% jump that
    means far less than a large company's steady -25% decline).
    """
    score = 0.0

    revenue_pct = metrics.get("revenue_hoh_pct")
    if revenue_pct is not None:
        pct_score = min(abs(revenue_pct) / 10, 3)

        if financials and financials.get("prev_revenue"):
            prev_revenue = abs(financials["prev_revenue"])
            SMALL_BASE_THRESHOLD = 10_000_000
            if prev_revenue < SMALL_BASE_THRESHOLD:
                confidence = prev_revenue / SMALL_BASE_THRESHOLD
                pct_score *= max(confidence, 0.2)

        score += pct_score

        #separate, undampened flag: extreme swings always surface,
        #even on a small base, because "unusual" itself is worth a user's attention regardless of absolute rupee size
        if abs(revenue_pct) >= 100:
            score += 1.5  #flat bump, independent of size dampening

    expenses_pct = metrics.get("expenses_hoh_pct")
    if expenses_pct is not None:
        score += min(abs(expenses_pct) / 15, 2)  #slightly lower weight than revenue

    score += 2.0 * len(insight.get("positives", []))
    score += 2.5 * len(insight.get("negatives", []))

    score += 3.0 if "auditor_qualification" in flags else 0
    score += 1.5 if "order_win" in flags else 0
    score += 2.0 if "capacity_expansion" in flags else 0

    # debt-assoc notability -> a meaningful jump in debt is worth flagging
    debt_current = metrics.get("total_debt")
    if debt_current is not None and debt_current > 0:
        score += 0.5  #small baseline bump for any reported debt change activity

    return round(score, 2)

def fiscal_year_label(date_str: str) -> str:
    """Given an ISO date string, return the Indian fiscal year label
    it falls in, e.g. '2024-10-15' -> 'FY2024-25'."""
    from datetime import datetime
    d = datetime.fromisoformat(date_str)
    if d.month >= 4:
        start_year = d.year
    else:
        start_year = d.year - 1
    end_year_short = str(start_year + 1)[-2:]
    return f"FY{start_year}-{end_year_short}"


def quarter_label_from_dates(end: str | None) -> str | None:
    """Given an XBRL end/instant date, return a full period label like
    'Q3-FY2024-25', combining the quarter and fiscal year."""
    if not end:
        return None
    from datetime import datetime
    try:
        e = datetime.fromisoformat(end)
    except ValueError:
        return None

    quarter_end_map = {6: "Q1", 9: "Q2", 12: "Q3", 3: "Q4"}
    quarter = quarter_end_map.get(e.month)
    if quarter is None:
        return None

    fy = fiscal_year_label(end)
    return f"{quarter}-{fy}"

from sentismetric.models import Financials
 
 
def get_latest_period_for_company(session, company_id: int) -> str | None:
    """Finds the chronologically latest period with a Financials row for
    this company, using _parse_period_label() (already in this file) to
    build a real sortable key rather than comparing period strings
    directly. Skips any row whose period doesn't parse cleanly (defensive
    — protects against any future stale/malformed data, same class of
    issue as the 'Fourth Quarter' rows just cleaned out of the DB)."""
    rows = session.query(Financials.period).filter_by(company_id=company_id).all()
    periods = [r[0] for r in rows if r[0]]
    if not periods:
        return None
 
    def sort_key(period_str):
        parsed = _parse_period_label(period_str)
        if parsed is None:
            return None
        year, quarter = parsed
        quarter_num = int(quarter[1])  # "Q1" -> 1, "Q4" -> 4
        # year*10 + quarter_num orders correctly ACROSS fiscal-year
        # boundaries: FY2025 Q4 -> 20254, FY2026 Q1 -> 20261 (later, correctly)
        return year * 10 + quarter_num
 
    scored = [(sort_key(p), p) for p in periods]
    scored = [(k, p) for k, p in scored if k is not None]
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]
 
 
def get_latest_company_snapshot(session, company_id: int) -> dict | None:
    """Company-level financial snapshot for display on ANY filing page,
    regardless of that specific filing's own period. Combines the raw
    latest Financials row (for absolute numbers: revenue, PAT, EPS) with
    HoH/YoY trend metrics (reusing get_metrics_for_period()'s existing
    prev/YoY logic, not duplicating it). Returns None if the company has
    no financials at all yet — genuinely nothing to show, not an error.
    """
    latest_period = get_latest_period_for_company(session, company_id)
    if latest_period is None:
        return None
 
    latest_row = (
        session.query(Financials)
        .filter_by(company_id=company_id, period=latest_period)
        .one_or_none()
    )
    if latest_row is None:
        return None
 
    metrics = get_metrics_for_period(session, company_id, latest_period)
 
    return {
        "period": latest_period,
        "revenue": float(latest_row.revenue) if latest_row.revenue is not None else None,
        "pat": float(latest_row.pat) if latest_row.pat is not None else None,
        "eps": float(latest_row.eps) if latest_row.eps is not None else None,
        "debt_current": float(latest_row.debt_current) if latest_row.debt_current is not None else None,
        "debt_noncurrent": float(latest_row.debt_noncurrent) if latest_row.debt_noncurrent is not None else None,
        "debt_equity_ratio": float(latest_row.debt_equity_ratio) if latest_row.debt_equity_ratio is not None else None,
        "total_expenses": float(latest_row.total_expenses) if latest_row.total_expenses is not None else None,
        **metrics,  # revenue_hoh_pct, revenue_yoy_pct, pat_margin_pct, total_debt, expenses_hoh_pct
    }
 