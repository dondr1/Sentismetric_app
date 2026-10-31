"""
Sentismetric — Filings dashboard.

Run: streamlit run src/sentismetric/app/Home.py
"""

import html as _html
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from theme import apply_theme, render_sidebar_pipeline, ring, badge, flag_badges, tile, row_sentiment

st.set_page_config(
    page_title="Sentismetric",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Redirect FIRST, before any data loading or rendering — this must be the
# very first thing that runs. It used to sit at the bottom of the file,
# which meant clicking a row re-rendered the ENTIRE home page (stats,
# filters, all rows) once before redirecting — that full render is what
# looked like "glitching back to home" before the filing page opened.
# ---------------------------------------------------------------------------

_selected = st.query_params.get("filing")
if _selected:
    # seed theme from the URL before navigating away
    _url_theme = st.query_params.get("theme")
    if _url_theme in ("light", "dark"):
        st.session_state["theme_mode"] = _url_theme
    st.session_state["selected_filing_id"] = int(_selected)
    # NOTE: deliberately do NOT clear the query param here. Clearing it
    # before switch_page raced the navigation and could leave the Filing
    # page with no filing to show, bouncing the user back to Home. The
    # Filing page reads selected_filing_id from session_state (set above)
    # and doesn't depend on the param surviving, so leaving it is safe.
    st.switch_page("pages/1_Filing.py")

# ---------------------------------------------------------------------------
# Config / DB
# ---------------------------------------------------------------------------

def resolve_db_url() -> str:
    from sentismetric.config import settings
    return str(settings.database_url)


@st.cache_resource
def get_engine():
    return create_engine(resolve_db_url(), pool_pre_ping=True)


from sentismetric.models import Filing, Company, Insight  # noqa: E402


@st.cache_data(ttl=30)
def load_filings(search: str, exchange: str, filing_type: str, limit: int = 60):
    with Session(get_engine()) as s:
        stmt = (
            select(
                Filing.id, Filing.exchange, Filing.filing_type, Filing.period,
                Filing.exchange_ts, Company.name, Company.symbol,
                Insight.summary, Insight.notability,
                Insight.positives, Insight.negatives, Insight.flags,
            )
            .join(Company, Company.id == Filing.company_id)
            .outerjoin(Insight, Insight.filing_id == Filing.id)
        )
        if exchange != "All":
            stmt = stmt.where(Filing.exchange == exchange)
        if filing_type != "All":
            stmt = stmt.where(Filing.filing_type == filing_type)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(Company.name.ilike(like) | Company.symbol.ilike(like))
        stmt = stmt.order_by(
            Insight.notability.desc().nulls_last(), Filing.exchange_ts.desc()
        ).limit(limit)
        return s.execute(stmt).all()


@st.cache_data(ttl=30)
def load_stats():
    today = datetime.now(timezone.utc).date()
    with Session(get_engine()) as s:
        today_count = s.scalar(
            select(func.count(Filing.id)).where(func.date(Filing.ingest_ts) == today)
        ) or 0
        total = s.scalar(select(func.count(Filing.id))) or 0
        companies = s.scalar(select(func.count(Company.id))) or 0
        by_status = dict(
            s.execute(
                select(Filing.status, func.count(Filing.id)).group_by(Filing.status)
            ).all()
        )
    return today_count, total, companies, by_status


# Theme FIRST — before any DB work. This used to run after load_stats()/
# load_filings(), which meant the splash/CSS/hidden-auto-nav didn't apply
# until those queries finished — raw unstyled Streamlit was visible the
# whole time they ran. Now it's immediate regardless of query speed.
mode = apply_theme(active="Filings")

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

db_error = None
try:
    today_count, total, companies, by_status = load_stats()
    rows = load_filings(
        st.session_state.get("q", ""),
        st.session_state.get("exch", "All"),
        st.session_state.get("ftype", "All"),
    )
except Exception as e:
    db_error = e
    today_count = total = companies = 0
    by_status, rows = {}, []

pipeline = {k.lower(): v for k, v in by_status.items()} or None
render_sidebar_pipeline(pipeline)

if db_error:
    st.error(f"Database unavailable — {db_error}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="eyebrow">BSE &middot; NSE Emerge</div>'
    '<div class="display" style="font-size:1.85rem;margin-top:4px;">Filings</div>',
    unsafe_allow_html=True,
)
st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Hero + tiles (asymmetric)
# ---------------------------------------------------------------------------

hero_col, tiles_col = st.columns([2.15, 1], gap="medium")

with hero_col:
    top = next((r for r in rows if r.notability is not None), None)
    if top:
        summary = (top.summary or "").strip()
        if len(summary) > 165:
            summary = summary[:165].rsplit(" ", 1)[0] + "…"
        st.markdown(
            f'<div class="hero">'
            f'<div class="hero-label">Highest notability</div>'
            f'<div class="hero-co">{_html.escape(top.name or "")}</div>'
            f'<div class="hero-meta">{top.exchange} · {_html.escape(top.symbol or "")}'
            f' · {_html.escape(top.period or "—")}</div>'
            f'<div class="hero-sum">{_html.escape(summary)}</div>'
            f'<div class="hero-score"><div class="n">{top.notability:.1f}</div>'
            f'<div class="l">score</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="hero-empty">No analyzed filings yet — '
            'run the poller to populate the feed.</div>',
            unsafe_allow_html=True,
        )

with tiles_col:
    st.markdown(tile("Filings today", today_count), unsafe_allow_html=True)
    st.markdown(
        tile("Total filings", f"{total:,}", f"{companies:,} companies tracked"),
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

# Search icon is a CSS mask applied directly to the input's own
# container (see .st-key-search_wrap rules in theme.py) — not a
# separate element, which is what caused it to float above the pill
# instead of sitting inside it. Filtering is already live on keystroke
# via session_state["q"], so no submit affordance is needed.

f1, f2, f3 = st.columns([3.1, 1, 1.2])
with f1:
    with st.container(key="search_wrap"):
        st.text_input("Search", key="q", placeholder="Search company or symbol…",
                      label_visibility="collapsed")
with f2:
    st.selectbox("Exchange", ["All", "BSE", "NSE"], key="exch",
                 label_visibility="collapsed")
with f3:
    st.selectbox("Type", ["All", "results", "board_meeting_outcome",
                          "intimation", "routine"],
                 key="ftype", label_visibility="collapsed")

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filing rows — rendered as one HTML block, navigation via query param
# ---------------------------------------------------------------------------

if not rows:
    st.markdown(
        '<div class="empty">No filings match these filters.</div>',
        unsafe_allow_html=True,
    )
else:
    cards = []
    for r in rows:
        summary = (r.summary or "Not yet analyzed.").strip()
        if len(summary) > 150:
            summary = summary[:150].rsplit(" ", 1)[0] + "…"
        ts = r.exchange_ts.strftime("%d %b · %H:%M") if r.exchange_ts else "—"
        hot = " row-hot" if (r.notability or 0) >= 5 else ""

        cards.append(
            f'<a class="row{hot}" href="?filing={r.id}&theme={mode}" target="_self">'
            f'{ring(r.notability, row_sentiment(r.positives, r.negatives, r.flags))}'
            f'<div>'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">'
            f'<div><span class="co">{_html.escape(r.name or "")}</span>'
            f'<span class="sym">{_html.escape(r.symbol or "")}</span></div>'
            f'<div style="flex-shrink:0;">{flag_badges(r.flags, max_shown=2)}</div>'
            f'</div>'
            f'<div class="sum">{_html.escape(summary)}</div>'
            f'<div class="meta">'
            f'<span class="badge badge-exch">{r.exchange}</span>'
            f'{badge(r.filing_type)}'
            f'<span class="ts">{ts}</span>'
            f'</div></div>'
            f'<div class="chev">&rsaquo;</div>'
            f'</a>'
        )

    st.markdown(f'<div class="rows">{"".join(cards)}</div>', unsafe_allow_html=True)