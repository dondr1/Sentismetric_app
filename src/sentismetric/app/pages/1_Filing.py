"""
Sentismetric — Filing detail page.

Three panes, left to right: scorecard metrics | original PDF | insight
card (quoted positives/negatives) + per-filing chat. The PDF sits in the
middle deliberately — the manual is explicit that verbatim quotes must
be visually adjacent to the source document ("trust is a UI feature"),
so the insight pane sits right next to it rather than on the far side.

NOTE on assumptions — adjust these if your actual code differs:
- get_metrics_for_period(session, company_id, period) is assumed to
  return the already-computed metrics dict (revenue_hoh_pct,
  revenue_yoy_pct, pat_margin_pct, expenses_hoh_pct, total_debt,
  debt_equity_ratio) rather than raw (cur, prev, yoy) rows — that's
  what the memory notes describe it doing. If it actually returns raw
  rows, call compute_metrics() on the result before using it here.
- rag.answer(question, filing_id=..., company_id=...) is assumed to
  return a plain string (per the manual's signature).
- Insight.positives / Insight.negatives are assumed to be JSON lists
  of {"quote": ..., "page": ..., "why_notable": ...} per the manual's
  prompt schema.
- A `feedback` table (filing_id, verdict, comment, ts) is created
  lazily on first use below rather than assumed to already exist in
  models.py — move it there properly once you're happy with the shape.
"""

import html as _html
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import create_engine, select, text as sql
from sqlalchemy.orm import Session

from theme import apply_theme, ring, badge, flag_badges, notability_sentiment

st.set_page_config(
    page_title="Filing — Sentismetric",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def resolve_db_url() -> str:
    from sentismetric.config import settings
    return str(settings.database_url)


@st.cache_resource
def get_engine():
    return create_engine(resolve_db_url(), pool_pre_ping=True)


from sentismetric.models import Filing, Company, Insight, Financials  # noqa: E402

try:
    from sentismetric.analyze.scorecard import get_metrics_for_period, get_latest_company_snapshot
except Exception as e:
    get_metrics_for_period = None
    get_latest_company_snapshot = None
    _scorecard_import_error = str(e)
else:
    _scorecard_import_error = None

try:
    from sentismetric.rag.retrieve import answer as rag_answer
except Exception:
    rag_answer = None


# =============================================================================
# Chat widget — pill (closed) / panel (open, sits inline below the insight
# card) / fullscreen (still an overlay, since "maximize" needs to escape
# the column width). Uses st.container(key=...) so each state gets a
# stable CSS hook (Streamlit renders it as `.st-key-<key>`).
# =============================================================================

CHAT_CSS = """
<style>
@property --chat-angle {
    syntax: '<angle>'; initial-value: 0deg; inherits: false;
}
@keyframes chat-glow-spin {
    to { --chat-angle: 360deg; }
}
@keyframes chat-scale-in {
    from { opacity: 0; transform: scale(.4); }
    to   { opacity: 1; transform: scale(1); }
}

/* closed pill — sits inline in normal flow, not floating */
.st-key-chat_pill button {
    background: var(--surface) !important;
    border: 1px solid var(--accent-border) !important;
    border-radius: 14px !important;
    padding: 12px 20px !important;
    box-shadow: var(--shadow) !important;
    font-family: -apple-system, 'SF Pro Display', 'Instrument Sans', sans-serif !important;
    font-weight: 600 !important; font-size: .95rem !important;
    transition: transform .18s ease, border-color .18s ease !important;
    width: 100% !important;
}
.st-key-chat_pill button:hover {
    transform: translateY(-2px) !important;
    border-color: var(--accent) !important;
}

/* open panel — inline block, sits below the insight card in normal
   document flow, full column width. Only fullscreen escapes to a fixed
   overlay, since maximizing genuinely needs to exceed the column.
   transform-origin: bottom left makes it grow up from its own
   bottom-left corner in place, rather than fading in from below. */
.st-key-chat_panel, .st-key-chat_full {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 18px !important;
    box-shadow: var(--shadow) !important;
    transform-origin: bottom left;
    animation: chat-scale-in .3s cubic-bezier(.2,.8,.2,1);
    transition: all .3s cubic-bezier(.2,.8,.2,1);
}
.st-key-chat_panel {
    width: 100% !important; max-height: 480px; overflow-y: auto;
    padding: 16px 18px !important;
}
.st-key-chat_full {
    position: fixed !important; z-index: 9999;
    top: 6vh; right: 3vw; width: 58vw; max-width: 860px;
    height: 86vh; overflow-y: auto; padding: 20px 24px !important;
}

/* moving glow — thin ring only, via mask-composite so the gradient
   only shows on a ~1.5px band, never the card face */
.st-key-chat_panel::before, .st-key-chat_full::before {
    content: ""; position: absolute; inset: 0; border-radius: 18px;
    padding: 1.5px;
    background: conic-gradient(from var(--chat-angle),
        transparent 0deg,
        transparent 300deg,
        var(--sand-500) 340deg,
        var(--sand-200) 356deg,
        transparent 360deg);
    -webkit-mask:
        linear-gradient(#000 0 0) content-box,
        linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
            mask-composite: exclude;
    animation: chat-glow-spin 4s linear infinite;
    pointer-events: none;
}
.st-key-chat_panel, .st-key-chat_full {
    position: relative;
}

.chat-widget-title {
    font-family: -apple-system, 'SF Pro Display', 'Instrument Sans', sans-serif;
    font-weight: 600; font-size: 1rem; color: var(--ink);
    letter-spacing: -.01em;
}
.st-key-chat_panel button, .st-key-chat_full button {
    transition: color .15s ease, border-color .15s ease !important;
}

/* chat input — scoped inside the widget so it beats Streamlit's own
   default dark chrome. The dark fill lives on a NESTED wrapper inside
   stChatInput, not the outer testid, so every descendant div/container
   is forced to the theme surface here; only the textarea stays
   transparent so text sits on that surface. */
.st-key-chat_panel [data-testid="stChatInput"],
.st-key-chat_full [data-testid="stChatInput"],
.st-key-chat_panel [data-testid="stChatInput"] > div,
.st-key-chat_full [data-testid="stChatInput"] > div,
.st-key-chat_panel [data-testid="stChatInputContainer"],
.st-key-chat_full [data-testid="stChatInputContainer"],
.st-key-chat_panel [data-testid="stChatInput"] [data-baseweb="base-input"],
.st-key-chat_full [data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: var(--surface-alt) !important;
    border-color: var(--border) !important;
    border-radius: 12px !important;
}
.st-key-chat_panel [data-testid="stChatInput"] textarea,
.st-key-chat_full [data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
.st-key-chat_panel [data-testid="stChatInput"] textarea::placeholder,
.st-key-chat_full [data-testid="stChatInput"] textarea::placeholder {
    color: var(--muted) !important;
    -webkit-text-fill-color: var(--muted) !important;
}
.st-key-chat_panel [data-testid="stChatInput"] button,
.st-key-chat_full [data-testid="stChatInput"] button {
    background: var(--accent) !important;
    border: none !important;
}
.st-key-chat_panel [data-testid="stChatInput"] button svg,
.st-key-chat_full [data-testid="stChatInput"] button svg {
    fill: var(--bg) !important;
}
</style>
"""


def render_chat_widget(filing_id: int, company_id: int):
    st.markdown(CHAT_CSS, unsafe_allow_html=True)

    state_key = f"chat_state_{filing_id}"
    hist_key = f"chat_history_{filing_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = "open"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = []

    state = st.session_state[state_key]

    if state == "closed":
        with st.container(key="chat_pill"):
            if st.button("👋  Ask about this filing", key="chat_open"):
                st.session_state[state_key] = "open"
                st.rerun()
        return

    container_key = "chat_panel" if state == "open" else "chat_full"
    with st.container(key=container_key):
        top_l, top_clear, top_expand, top_close = st.columns([5, 1, 1, 1])
        with top_l:
            st.markdown('<div class="chat-widget-title">👋 Hey, any questions about this filing?</div>',
                        unsafe_allow_html=True)
        with top_clear:
            if st.button("🗑", key="chat_clear", help="Clear chat"):
                st.session_state[hist_key] = []
                st.rerun()
        with top_expand:
            expand_icon = "⤢" if state == "open" else "⤡"
            if st.button(expand_icon, key="chat_toggle_expand"):
                st.session_state[state_key] = "full" if state == "open" else "open"
                st.rerun()
        with top_close:
            if st.button("✕", key="chat_close"):
                st.session_state[state_key] = "closed"
                st.rerun()

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        thinking_key = f"chat_thinking_{filing_id}"
        pending_key = f"chat_pending_{filing_id}"
        if thinking_key not in st.session_state:
            st.session_state[thinking_key] = False
        if pending_key not in st.session_state:
            st.session_state[pending_key] = None

        for role, text in st.session_state[hist_key]:
            with st.chat_message(role):
                st.markdown(text)

        # If a question is pending from the PREVIOUS rerun, answer it now.
        # This two-rerun split is required: Streamlit can't visually
        # disable chat_input during the same blocking call that's using
        # it — the disabled state has to already be rendered and sent to
        # the browser on a prior pass, before the slow LLM call starts.
        if st.session_state[thinking_key] and st.session_state[pending_key]:
            question = st.session_state[pending_key]
            with st.chat_message("assistant"):
                if rag_answer is None:
                    reply = "RAG module not available — check the import path in this page."
                else:
                    with st.spinner("Reading the filing…"):
                        try:
                            reply = rag_answer(question, filing_id=filing_id, company_id=company_id)
                        except Exception as e:
                            reply = f"Couldn't answer that ({e})."
                st.markdown(reply)
            st.session_state[hist_key].append(("assistant", reply))
            st.session_state[thinking_key] = False
            st.session_state[pending_key] = None
            st.rerun()  # redraw with input re-enabled

        question = st.chat_input(
            "Ask a question about this filing…",
            key="chat_input_widget",
            disabled=st.session_state[thinking_key],
        )
        if question and not st.session_state[thinking_key]:
            st.session_state[hist_key].append(("user", question))
            st.session_state[pending_key] = question
            st.session_state[thinking_key] = True
            st.rerun()  # redraw immediately with input disabled, THEN process


# ---------------------------------------------------------------------------
# Resolve which filing we're looking at
# ---------------------------------------------------------------------------

filing_id = st.session_state.get("selected_filing_id")
if filing_id is None:
    _qp = st.query_params.get("filing")
    if _qp:
        filing_id = int(_qp)

if filing_id is None:
    _mode = apply_theme(active="Filings")
    st.markdown(
        f'<div class="empty">No filing selected. '
        f'<a href="/?theme={_mode}" target="_self">← Back to Filings</a></div>',
        unsafe_allow_html=True,
    )
    st.stop()

# Persist the resolved id into BOTH session_state and the URL. This is
# what makes a hard browser refresh work: on refresh, session_state is
# wiped, so without the id in the URL there'd be nothing to recover from
# and the page would bounce to the empty state. Writing it to
# query_params keeps ?filing=<id> in the address bar so refresh finds it.
st.session_state["selected_filing_id"] = filing_id
if st.query_params.get("filing") != str(filing_id):
    st.query_params["filing"] = str(filing_id)


@st.cache_data(ttl=30)
def load_filing(fid: int):
    with Session(get_engine()) as s:
        row = s.execute(
            select(Filing, Company, Insight)
            .join(Company, Company.id == Filing.company_id)
            .outerjoin(Insight, Insight.filing_id == Filing.id)
            .where(Filing.id == fid)
        ).first()
        return row


@st.cache_data(ttl=30)
def load_financials_period(company_id: int, period: str | None):
    if not period:
        return None
    with Session(get_engine()) as s:
        return s.execute(
            select(Financials)
            .where(Financials.company_id == company_id, Financials.period == period)
        ).scalar_one_or_none()


row = load_filing(filing_id)
if row is None:
    apply_theme(active="Filings")
    st.error(f"Filing #{filing_id} not found.")
    st.stop()

filing, company, insight = row
mode = apply_theme(active="Filings")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    f'<a href="/?theme={mode}" target="_self" class="muted" style="text-decoration:none;font-size:.85rem;">'
    f'← Back to Filings</a>',
    unsafe_allow_html=True,
)

hcol1, hcol2 = st.columns([5, 1])
with hcol1:
    ts_label = filing.exchange_ts.strftime("%d %b %Y · %H:%M") if filing.exchange_ts else "—"
    st.markdown(
        f'<div class="display" style="font-size:1.6rem;margin-top:6px;">'
        f'{_html.escape(company.name or "")}</div>'
        f'<div class="muted" style="margin-top:2px;">'
        f'{_html.escape(company.symbol or "")} · {filing.exchange} · '
        f'{_html.escape(filing.period or "—")} · {ts_label}</div>'
        f'<div style="margin-top:8px;">{badge(filing.filing_type)}</div>',
        unsafe_allow_html=True,
    )
with hcol2:
    score = insight.notability if insight else None
    st.markdown(
        f'<div style="display:flex;justify-content:flex-end;">{ring(score, notability_sentiment(insight))}</div>',
        unsafe_allow_html=True,
    )

# Flags get their own full-width row, clearly separated from both the
# header columns above (generous margin-top) — previous attempts kept
# them squeezed near the ring or the filing-type badge, which is what
# kept causing spacing/alignment fights. A dedicated row sidesteps that
# entirely rather than continuing to chase pixel proximity to something else.
flags_html = flag_badges(insight.flags if insight else None)
if flags_html:
    st.markdown(
        f'<div style="margin-top:18px;">{flags_html}</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Three panes
# ---------------------------------------------------------------------------

# Two columns now: LEFT stacks scorecard + insight (all the text/analysis
# in one place), RIGHT is the PDF given more room. This replaces the old
# scorecard | PDF | insight arrangement, which put the document awkwardly
# between two text panes.

col_left, col_pdf = st.columns([1.15, 1.5], gap="medium")

# --- LEFT (top): scorecard ---------------------------------------------

with col_left:
    st.markdown('<div class="eyebrow">Scorecard</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Company-level snapshot — shown on EVERY filing page (routine,
    # intimation, results, anything), independent of whether THIS
    # filing's own period matches a Financials row. Always shows the
    # company's most recent known financials + HoH/YoY trend, since
    # that's more useful than going blank just because this specific
    # filing isn't itself a results filing.
    snapshot = None
    if get_latest_company_snapshot is not None:
        try:
            with Session(get_engine()) as s:
                snapshot = get_latest_company_snapshot(s, company.id)
        except Exception as e:
            st.caption(f"Financials unavailable ({e})")

    def metric_card_html(label: str, value, suffix: str = "", signed: bool = True) -> str:
        if value is None:
            val_html = '<span class="mono faint">—</span>'
        else:
            color = "var(--muted)"
            arrow = ""
            if signed:
                if value > 0:
                    color, arrow = "var(--up)", "▲ "
                elif value < 0:
                    color, arrow = "var(--down)", "▼ "
            val_html = f'<span class="mono" style="color:{color};">{arrow}{value:+.1f}{suffix}</span>' \
                if signed else f'<span class="mono">{value:,.1f}{suffix}</span>'
        return (
            f'<div class="metric-card">'
            f'<div class="eyebrow" style="font-size:.68rem;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:.92rem;">{val_html}</div>'
            f'</div>'
        )

    if snapshot:
        # period context — this is the COMPANY's latest period, which
        # may differ from the filing you're currently viewing (e.g. a
        # routine intimation shows the last known results regardless)
        same_period = snapshot.get("period") == filing.period
        context_label = (
            f"As of {snapshot['period']}" if same_period
            else f"Latest available: {snapshot['period']} (this filing: {filing.period or 'n/a'})"
        )
        st.markdown(
            f'<div class="mono muted" style="font-size:.8rem;margin-bottom:10px;">{context_label}</div>',
            unsafe_allow_html=True,
        )

        # absolute figures first, then trend — all rendered as one grid,
        # 3 cards per row, instead of a long vertical stack
        cards = "".join([
            metric_card_html("Revenue", snapshot.get("revenue"), "", signed=False),
            metric_card_html("PAT", snapshot.get("pat"), "", signed=False),
            metric_card_html("EPS", snapshot.get("eps"), "", signed=False),
            metric_card_html("Revenue (HoH)", snapshot.get("revenue_hoh_pct"), "%"),
            metric_card_html("Revenue (YoY)", snapshot.get("revenue_yoy_pct"), "%"),
            metric_card_html("PAT margin", snapshot.get("pat_margin_pct"), "%", signed=False),
            metric_card_html("Expenses (HoH)", snapshot.get("expenses_hoh_pct"), "%"),
            metric_card_html("Total debt", snapshot.get("total_debt"), "", signed=False),
            metric_card_html("Debt/Equity", snapshot.get("debt_equity_ratio"), "x", signed=False),
        ])
        st.markdown(
            f'<div class="metric-grid">{cards}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="empty" style="padding:24px;">No financials available for this company yet.</div>',
            unsafe_allow_html=True,
        )

# --- Pane B: PDF viewer -------------------------------------------------
# Rendered as page images via PyMuPDF rather than an embedded iframe —
# base64 data-URI iframes are unreliable across browsers (size limits,
# sandboxing, silent blank renders) and your Ch9 pipeline already solved
# this exact problem with page_to_png(). Reusing that approach directly
# rather than fighting the iframe is the more robust choice.

with col_pdf:
    st.markdown('<div class="eyebrow">Original filing</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if not filing.pdf_path:
        st.markdown('<div class="empty">No PDF stored for this filing.</div>',
                     unsafe_allow_html=True)
    else:
        try:
            import fitz  # PyMuPDF

            page_key = f"pdf_page_{filing.id}"
            if page_key not in st.session_state:
                st.session_state[page_key] = 1

            with fitz.open(filing.pdf_path) as doc:
                total_pages = len(doc)
                page_no = min(max(st.session_state[page_key], 1), total_pages)
                pix = doc[page_no - 1].get_pixmap(dpi=140)
                png_bytes = pix.tobytes("png")

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("← Prev", disabled=(page_no <= 1), use_container_width=True):
                    st.session_state[page_key] = page_no - 1
                    st.rerun()
            with nav2:
                st.markdown(
                    f'<div style="text-align:center;" class="mono muted">'
                    f'Page {page_no} of {total_pages}</div>',
                    unsafe_allow_html=True,
                )
            with nav3:
                if st.button("Next →", disabled=(page_no >= total_pages), use_container_width=True):
                    st.session_state[page_key] = page_no + 1
                    st.rerun()

            st.image(png_bytes, use_container_width=True)

            with open(filing.pdf_path, "rb") as f:
                st.download_button(
                    "Download full PDF", data=f.read(),
                    file_name=f"{company.symbol}_{filing.period or filing.id}.pdf",
                    mime="application/pdf",
                )
        except FileNotFoundError:
            st.markdown(
                f'<div class="empty">PDF not found on disk at '
                f'<span class="mono">{_html.escape(filing.pdf_path)}</span></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(f'<div class="empty">Couldn\'t render PDF ({e})</div>',
                         unsafe_allow_html=True)

# --- LEFT (bottom): insight, stacked under the scorecard ---------------

with col_left:
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">Insight</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if insight is None:
        st.markdown(
            '<div class="empty" style="padding:24px;">Not yet analyzed.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="card" style="margin-bottom:14px;">'
            f'<div style="font-size:.9rem;line-height:1.5;">{_html.escape(insight.summary or "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        def quote_block(label: str, items):
            if not items:
                return
            st.markdown(f'<div class="eyebrow" style="margin:12px 0 6px;">{label}</div>',
                        unsafe_allow_html=True)
            for item in items:
                quote = _html.escape(item.get("quote", ""))
                page = item.get("page")
                why = _html.escape(item.get("why_notable", ""))
                page_label = f"p. {page}" if page else ""
                st.markdown(
                    f'<div class="card" style="padding:12px 14px;margin-bottom:8px;'
                    f'border-left:2px solid var(--accent-border);">'
                    + (f'<div style="font-size:.9rem;font-weight:600;color:var(--ink);'
                       f'line-height:1.45;margin-bottom:6px;">{why}</div>' if why else "")
                    + f'<div style="font-size:.78rem;font-style:italic;line-height:1.4;color:var(--muted);">'
                    f'"{quote}"</div>'
                    f'<div class="faint mono" style="font-size:.72rem;margin-top:6px;">{page_label}</div>'
                    + '</div>',
                    unsafe_allow_html=True,
                )

        quote_block("Positives", insight.positives or [])
        quote_block("Negatives", insight.negatives or [])
        # flags now shown in the header, next to the filing-type badge —
        # removed the duplicate here

        # feedback — thumbs + optional comment, feeds future notability tuning
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        fb_col1, fb_col2 = st.columns([1, 1])
        with fb_col1:
            up_clicked = st.button("👍 Notable", key=f"fb_up_{filing.id}", use_container_width=True)
        with fb_col2:
            down_clicked = st.button("👎 Not notable", key=f"fb_down_{filing.id}", use_container_width=True)

        def save_feedback(verdict: str):
            try:
                with Session(get_engine()) as s:
                    s.execute(sql(
                        "CREATE TABLE IF NOT EXISTS feedback ("
                        "id SERIAL PRIMARY KEY, filing_id INTEGER NOT NULL, "
                        "verdict TEXT NOT NULL, comment TEXT, "
                        "ts TIMESTAMPTZ NOT NULL DEFAULT now())"
                    ))
                    s.execute(
                        sql("INSERT INTO feedback (filing_id, verdict) VALUES (:fid, :v)"),
                        {"fid": filing.id, "v": verdict},
                    )
                    s.commit()
                st.toast(f"Feedback recorded: {verdict}")
            except Exception as e:
                st.caption(f"Couldn't save feedback ({e})")

        if up_clicked:
            save_feedback("notable")
        if down_clicked:
            save_feedback("not_notable")

    # --- chat, now inline below the insight card in the same column ---
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    render_chat_widget(filing.id, company.id)

    # --- per-filing chat now lives as a floating widget, rendered below
    # the three-pane layout so it overlays on top rather than taking
    # column space — see render_chat_widget() at the bottom of this file.