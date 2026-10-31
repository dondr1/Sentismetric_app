"""
Sentismetric — Watchlist.

Same feed layout as Home.py, filtered to companies you've explicitly
added. Any company (even one with no filings yet) can be added via the
search-and-add box at the top. Companies here also alert at the NORMAL
notability threshold (not the raised bar applied to everything else) —
see main.py's alert gate.

Run: streamlit run src/sentismetric/app/Home.py (this is a page under it)
"""

import html as _html
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from theme import apply_theme, render_sidebar_pipeline, ring, badge, flag_badges, tile, row_sentiment

st.set_page_config(
    page_title="Watchlist — Sentismetric",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Same redirect-first pattern as Home.py, for consistency if a row link
# from here is ever clicked before Home.py's own redirect has a chance
# to run first in the same session.
_selected = st.query_params.get("filing")
if _selected:
    _url_theme = st.query_params.get("theme")
    if _url_theme in ("light", "dark"):
        st.session_state["theme_mode"] = _url_theme
    st.session_state["selected_filing_id"] = int(_selected)
    st.switch_page("pages/1_Filing.py")


def resolve_db_url() -> str:
    from sentismetric.config import settings
    return str(settings.database_url)


@st.cache_resource
def get_engine():
    return create_engine(resolve_db_url(), pool_pre_ping=True)


from sentismetric.models import Filing, Company, Insight, Watchlist  # noqa: E402


@st.cache_data(ttl=15)
def load_watchlist_companies():
    """All companies currently on the watchlist, for the feed filter
    AND for rendering the 'remove' list."""
    with Session(get_engine()) as s:
        return s.execute(
            select(Company.id, Company.name, Company.symbol, Company.exchange)
            .join(Watchlist, Watchlist.company_id == Company.id)
            .order_by(Watchlist.added_at.desc())
        ).all()


@st.cache_data(ttl=15)
def search_companies(query: str, limit: int = 8):
    """For the add-to-watchlist search box — searches the FULL company
    universe (not just ones with existing filings), since any company
    can be added even before it's ever filed anything."""
    if not query or len(query.strip()) < 2:
        return []
    with Session(get_engine()) as s:
        like = f"%{query.strip()}%"
        return s.execute(
            select(Company.id, Company.name, Company.symbol, Company.exchange)
            .where(Company.name.ilike(like) | Company.symbol.ilike(like))
            .limit(limit)
        ).all()


@st.cache_data(ttl=15)
def load_watchlist_filings(company_ids: tuple[int, ...], limit: int = 60):
    if not company_ids:
        return []
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
            .where(Filing.company_id.in_(company_ids))
            .order_by(Insight.notability.desc().nulls_last(), Filing.exchange_ts.desc())
            .limit(limit)
        )
        return s.execute(stmt).all()


def add_to_watchlist(company_id: int):
    with Session(get_engine()) as s:
        exists = s.execute(
            select(Watchlist).where(Watchlist.company_id == company_id)
        ).first()
        if not exists:
            s.add(Watchlist(company_id=company_id))
            s.commit()
    load_watchlist_companies.clear()
    load_watchlist_filings.clear()


def remove_from_watchlist(company_id: int):
    with Session(get_engine()) as s:
        row = s.execute(
            select(Watchlist).where(Watchlist.company_id == company_id)
        ).scalar_one_or_none()
        if row:
            s.delete(row)
            s.commit()
    load_watchlist_companies.clear()
    load_watchlist_filings.clear()


mode = apply_theme(active="Watchlist")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="eyebrow">Tracked companies</div>'
    '<div class="display" style="font-size:1.85rem;margin-top:4px;">Watchlist</div>',
    unsafe_allow_html=True,
)
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Add company
# ---------------------------------------------------------------------------

add_col, _ = st.columns([2.2, 1.9])
with add_col:
    with st.container(key="search_wrap"):
        query = st.text_input("Add company", key="wl_search",
                              placeholder="Search company or symbol to add…",
                              label_visibility="collapsed")

if query and len(query.strip()) >= 2:
    results = search_companies(query)
    watchlisted_ids = {c.id for c in load_watchlist_companies()}
    if not results:
        st.caption("No matching companies.")
    else:
        for c in results:
            rcol1, rcol2 = st.columns([5, 1])
            with rcol1:
                st.markdown(
                    f'<div style="padding:8px 0;">'
                    f'<span class="co" style="font-size:.92rem;">{_html.escape(c.name or "")}</span> '
                    f'<span class="sym">{_html.escape(c.symbol or "")}</span> '
                    f'<span class="badge badge-exch">{c.exchange}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with rcol2:
                already = c.id in watchlisted_ids
                if st.button("Added ✓" if already else "+ Add",
                            key=f"add_{c.id}", disabled=already,
                            use_container_width=True):
                    add_to_watchlist(c.id)
                    st.rerun()

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Currently tracked — with remove controls
# ---------------------------------------------------------------------------

watchlist_companies = load_watchlist_companies()

if not watchlist_companies:
    st.markdown(
        '<div class="empty">No companies tracked yet — search above to add one. '
        'Watchlist companies alert at the normal notability threshold; '
        'everything else needs a much higher score to interrupt you.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

with st.expander(f"Tracking {len(watchlist_companies)} companies", expanded=False):
    for c in watchlist_companies:
        wcol1, wcol2 = st.columns([5, 1])
        with wcol1:
            st.markdown(
                f'<div style="padding:6px 0;">'
                f'<span class="co" style="font-size:.88rem;">{_html.escape(c.name or "")}</span> '
                f'<span class="sym">{_html.escape(c.symbol or "")}</span></div>',
                unsafe_allow_html=True,
            )
        with wcol2:
            if st.button("Remove", key=f"rm_{c.id}", use_container_width=True):
                remove_from_watchlist(c.id)
                st.rerun()

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Feed — same row rendering as Home.py, filtered to watchlist companies
# ---------------------------------------------------------------------------

company_ids = tuple(c.id for c in watchlist_companies)
rows = load_watchlist_filings(company_ids)

if not rows:
    st.markdown(
        '<div class="empty">No filings yet for your tracked companies.</div>',
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