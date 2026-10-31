"""
Sentismetric design system — desert sand.

Import `apply_theme()` at the top of every page before other st.* calls.

Design notes:
- Desert sand (#CD9F66 family) is the ONLY accent colour in the system.
  Used on: notability rings, the hero card, active nav, hover/focus states.
  Nowhere else, so it never becomes wallpaper.
- Green/red are reserved strictly for real financial movement (revenue/PAT
  deltas). They are not decorative and must not be reused for UI state.
- Every numeric value renders in JetBrains Mono so figures read as data.
- Lists render as custom HTML grids rather than st.columns, because stock
  Streamlit widgets can't reach the density this UI needs.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

SAND_100 = "#F8ECE0"
SAND_200 = "#EFDCC0"
SAND_300 = "#E7C7A3"
SAND_500 = "#CD9F66"
SAND_700 = "#A97A43"

# dedicated dropdown palette — dark desert rock, distinct from page
# surfaces so selects read as one deliberate component rather than
# borrowed tokens. Same values in both light/dark mode by design.
# (dropdowns now use the same surface/border/ink tokens as every other
# card on the page — see LIGHT/DARK dicts below — rather than a separate
# palette, so they belong to the same visual family instead of clashing)

LIGHT = {
    "bg": "#F6F4F0",
    "sidebar": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_alt": "#F1EEE8",
    "border": "#E6E1D8",
    "border_soft": "#EFEBE3",
    "ink": "#16171B",
    "muted": "#6A6B73",
    "faint": "#9B9AA0",
    "up": "#0E8A5F",
    "down": "#C24444",
    "accent": SAND_700,
    "accent_bright": SAND_500,
    "accent_soft": "rgba(205,159,102,0.12)",
    "accent_border": "rgba(205,159,102,0.38)",
    "ring_track": "#E6E1D8",
    "hero_ink": "#3B2A15",
    "shadow": "0 1px 2px rgba(22,23,27,.04), 0 8px 24px rgba(22,23,27,.04)",
    "navy_bg": "#E8EDF7",
    "navy_border": "#B8C7E8",
    "navy_text": "#2C4A73",
}

DARK = {
    "bg": "#0A0B0F",
    "sidebar": "#12141B",
    "surface": "#14161D",
    "surface_alt": "#191C24",
    "border": "#232630",
    "border_soft": "#1C1F27",
    "ink": "#F2F3F5",
    "muted": "#8A8C96",
    "faint": "#5B5D67",
    "up": "#34C08C",
    "down": "#E5696B",
    "accent": SAND_300,
    "accent_bright": SAND_500,
    "accent_soft": "rgba(231,199,163,0.10)",
    "accent_border": "rgba(231,199,163,0.28)",
    "ring_track": "#242730",
    "hero_ink": "#2A1D0C",
    "shadow": "0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.28)",
    "navy_bg": "#1B2838",
    "navy_border": "#3A5578",
    "navy_text": "#8FB4E3",
}

FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Sans:ital,wght@0,500;0,600;0,700;1,600&"
    "family=Inter:wght@400;500;600&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)


def _css(t: dict) -> str:
    return f"""
    @import url('{FONTS}');

    :root {{
        --bg:{t['bg']}; --sidebar:{t['sidebar']}; --surface:{t['surface']};
        --surface-alt:{t['surface_alt']}; --border:{t['border']};
        --border-soft:{t['border_soft']}; --ink:{t['ink']}; --muted:{t['muted']};
        --faint:{t['faint']}; --up:{t['up']}; --down:{t['down']};
        --accent:{t['accent']}; --accent-bright:{t['accent_bright']};
        --accent-soft:{t['accent_soft']}; --accent-border:{t['accent_border']};
        --ring-track:{t['ring_track']}; --hero-ink:{t['hero_ink']};
        --shadow:{t['shadow']};
        --sand-500:{SAND_500}; --sand-200:{SAND_200}; --sand-300:{SAND_300};
        --navy-bg:{t['navy_bg']}; --navy-border:{t['navy_border']}; --navy-text:{t['navy_text']};
    }}

    /* pin the background at the root level first — closes the gap that
       was letting Streamlit's own light default bleed through at the
       edges, which is what made the sand-on-cream text go invisible */
    html, body, #root {{
        background: var(--bg) !important;
    }}

    /* --- splash overlay: masks the render flash ---
       Streamlit paints its own default DOM (dark chrome, auto-nav, raw
       widgets) a beat before our injected CSS applies. This themed
       overlay covers the whole viewport in the CORRECT theme colour,
       then fades itself out after ~0.5s once styles have settled — so
       the user never sees the unstyled flash. Pure CSS, no JS. */
    @keyframes senti-splash-out {{
        0%   {{ opacity: 1; visibility: visible; }}
        70%  {{ opacity: 1; visibility: visible; }}
        100% {{ opacity: 0; visibility: hidden; }}
    }}
    /* sidebar starts hidden and fades in only after the splash has
       covered the flash — this is what actually kills the "Home/Filing
       auto-nav visible for 3s" problem, since the sidebar renders in its
       own stacking context and can paint on top of the splash overlay
       otherwise. Delay is tuned to match the splash hold. */
    @keyframes senti-sidebar-in {{
        0%   {{ opacity: 0; }}
        75%  {{ opacity: 0; }}
        100% {{ opacity: 1; }}
    }}
    [data-testid="stSidebar"] {{
        animation: senti-sidebar-in .8s ease forwards;
    }}
    #senti-splash {{
        position: fixed; inset: 0; z-index: 2147483647;  /* above sidebar's own stacking context */
        background: var(--bg);
        display: flex; align-items: center; justify-content: center;
        animation: senti-splash-out .8s ease forwards;
        pointer-events: none;
    }}
    #senti-splash .senti-splash-mark {{
        font-family: 'Instrument Sans', sans-serif; font-weight: 700;
        font-size: 1.5rem; letter-spacing: -.02em; color: var(--ink);
        opacity: .9;
    }}
    #senti-splash .senti-splash-mark .wm-accent {{
        background: linear-gradient(120deg, var(--sand-500), var(--sand-300) 70%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent; color: var(--accent);
    }}

    /* --- force our surfaces everywhere Streamlit paints its own --- */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stMain"],
    [data-testid="stBottomBlockContainer"] {{
        background: var(--bg) !important;
        color: var(--ink);
    }}
    [data-testid="stHeader"] {{
        border-bottom: none !important;
        background: transparent !important;
        height: 3.2rem;
    }}
    /* hide only the Deploy button + hamburger menu specifically —
       hiding the whole stToolbar container was taking the sidebar's
       reopen arrow down with it in some Streamlit versions, since they
       can share the same header toolbar */
    [data-testid*="Deploy" i],
    [data-testid*="MainMenu" i],
    [data-testid="stAppDeployButton"] {{ display: none !important; }}
    [data-testid="stDecoration"] {{ display: none !important; }}

    /* sidebar collapse/expand control — testid naming varies across
       Streamlit versions, so match collapse AND expand by substring +
       aria-label, and force a visible background/border + icon color.
       The reopen control (shown when collapsed) lives in a different
       container than the in-sidebar collapse button, so both 'ollapse'
       and 'xpand' substrings are covered. */
    [data-testid*="ollapse" i],
    [data-testid*="xpand" i],
    [data-testid="stSidebarCollapsedControl"],
    button[aria-label*="sidebar" i],
    button[aria-label*="Open" i][aria-label*="idebar" i],
    button[title*="sidebar" i] {{
        z-index: 9999 !important;
        opacity: 1 !important;
        visibility: visible !important;
        display: flex !important;
    }}
    [data-testid*="ollapse" i] button,
    [data-testid*="xpand" i] button,
    [data-testid*="ollapse" i][role="button"],
    [data-testid="stSidebarCollapsedControl"] button,
    button[aria-label*="sidebar" i] {{
        background: var(--surface) !important;
        border: 1px solid var(--accent-border) !important;
        border-radius: 8px !important;
        box-shadow: var(--shadow) !important;
    }}
    [data-testid*="ollapse" i] svg,
    [data-testid*="xpand" i] svg,
    [data-testid="stSidebarCollapsedControl"] svg,
    button[aria-label*="sidebar" i] svg,
    button[title*="sidebar" i] svg {{
        fill: var(--ink) !important;
        stroke: var(--ink) !important;
        color: var(--ink) !important;
        opacity: 1 !important;
    }}

    /* (ambient glow removed — it was rendering as a near-solid light
       patch instead of a soft blur in some browser/theme combos, not
       worth the instability) */

    [data-testid="stSidebar"],
    [data-testid="stSidebarContent"] {{
        background: var(--sidebar) !important;
        border-right: 1px solid var(--border);
        box-shadow: 2px 0 12px rgba(0,0,0,0.12);
    }}
    /* hide Streamlit's auto-generated page nav (the "Home / Filing" list
       it builds from the pages/ folder) — the custom SentiSMEtric nav
       below replaces it, and having both created a confusing double nav
       whose auto-links navigate with no filing selected */
    [data-testid="stSidebarNav"],
    [data-testid="stSidebarNavItems"],
    [data-testid="stSidebarNavSeparator"],
    nav[aria-label*="page" i],
    ul[data-testid*="NavItems" i] {{ display: none !important; }}
    [data-testid="stSidebarContent"] * {{
        color: var(--ink);
    }}
    [data-testid="stSidebarContent"] .muted,
    [data-testid="stSidebarContent"] .faint {{
        color: var(--muted) !important;
    }}

    html, body, [class*="css"], .stMarkdown, p, span, div, label {{
        font-family: 'Inter', -apple-system, sans-serif;
        color: var(--ink);
    }}

    .block-container {{
        padding-top: 3.6rem; padding-bottom: 4rem; max-width: 1240px;
        background: transparent !important;
    }}

    h1,h2,h3,.display {{
        font-family: 'Instrument Sans','Inter',sans-serif !important;
        font-weight: 600; letter-spacing: -.02em; color: var(--ink);
        line-height: 1.25; padding-top: 0.08em; overflow: visible;
    }}
    .mono {{ font-family:'JetBrains Mono',monospace; font-variant-numeric: tabular-nums; }}
    .muted {{ color: var(--muted) !important; }}
    .faint {{ color: var(--faint) !important; }}

    .eyebrow {{
        font-size:.68rem; text-transform:uppercase; letter-spacing:.1em;
        color: var(--muted); font-weight:500; line-height:1.6;
    }}

    /* ---------- sidebar ---------- */
    .wordmark {{
        font-family:'Instrument Sans',sans-serif; font-weight:700;
        font-size:1.32rem; letter-spacing:-.015em; line-height:1.3;
        padding-top:.1em; color:var(--ink); margin-bottom:2px;
    }}
    .wordmark .wm-accent {{
        background: linear-gradient(120deg, var(--sand-500), var(--sand-300) 70%);
        -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: var(--accent);
    }}
    .brand-sub {{ font-size:.7rem; color:var(--muted); margin:0 0 22px 1px; }}

    .nav-item {{
        display:flex; align-items:center; gap:10px; padding:9px 11px;
        border-radius:9px; font-size:.88rem; color:var(--muted);
        margin-bottom:3px; border:1px solid transparent;
    }}
    .nav-item.active {{
        background:var(--accent-soft); color:var(--accent);
        border-color:var(--accent-border); font-weight:500;
    }}
    .nav-dot {{ width:5px; height:5px; border-radius:50%; background:currentColor; flex:none; }}

    .pipe {{ margin-top:22px; padding-top:16px; border-top:1px solid var(--border-soft); }}
    .pipe-row {{
        display:flex; justify-content:space-between; align-items:center;
        padding:6px 2px; font-size:.8rem; color:var(--muted);
    }}
    .pipe-row b {{
        font-family:'JetBrains Mono',monospace; font-weight:600;
        color:var(--accent); font-size:.82rem;
    }}

    /* ---------- hero ---------- */
    .hero {{
        border-radius:18px; padding:22px 24px; min-height:152px;
        background: linear-gradient(135deg, var(--sand-500) 0%, var(--sand-200) 100%);
        color: var(--hero-ink); position:relative; overflow:hidden;
    }}
    .hero-label {{
        font-size:.68rem; text-transform:uppercase; letter-spacing:.1em;
        font-weight:600; opacity:.62; color:var(--hero-ink);
    }}
    .hero-co {{
        font-family:'Instrument Sans',sans-serif; font-weight:700;
        font-size:1.5rem; letter-spacing:-.02em; margin-top:8px;
        color:var(--hero-ink); line-height:1.15;
    }}
    .hero-meta {{ font-size:.8rem; opacity:.72; margin-top:4px; color:var(--hero-ink); }}
    .hero-sum {{
        font-size:.82rem; opacity:.8; margin-top:10px; line-height:1.45;
        color:var(--hero-ink); max-width:52ch;
    }}
    .hero-score {{ position:absolute; right:24px; top:20px; text-align:right; color:var(--hero-ink); }}
    .hero-score .n {{
        font-family:'JetBrains Mono',monospace; font-size:2.5rem;
        font-weight:600; line-height:1;
    }}
    .hero-score .l {{ font-size:.64rem; text-transform:uppercase; letter-spacing:.1em; opacity:.6; }}
    .hero-empty {{
        display:flex; align-items:center; justify-content:center; min-height:152px;
        border-radius:18px; border:1px solid var(--border);
        background: linear-gradient(135deg, var(--accent-soft) 0%, transparent 60%),
                    var(--surface);
        color:var(--muted); font-size:.88rem;
    }}

    /* ---------- stat tiles ---------- */
    .tile {{
        background:var(--surface); border:1px solid var(--border);
        border-radius:14px; padding:15px 17px; box-shadow:var(--shadow);
        margin-bottom:9px;
    }}
    .tile .lab {{
        font-size:.66rem; text-transform:uppercase; letter-spacing:.08em;
        color:var(--muted); font-weight:500;
    }}
    .tile .val {{
        font-family:'JetBrains Mono',monospace; font-size:1.6rem;
        font-weight:600; line-height:1.1; margin-top:5px;
        background: linear-gradient(120deg, var(--ink) 30%, var(--accent) 150%);
        -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: var(--accent);
    }}
    .tile .sub {{ font-size:.72rem; color:var(--faint); margin-top:2px; }}

    /* ---------- filing rows ---------- */
    .rows {{ display:flex; flex-direction:column; gap:8px; }}
    .row {{
        display:grid; grid-template-columns:52px 1fr auto; gap:16px;
        align-items:center; text-decoration:none !important;
        background:var(--surface); border:1px solid var(--border);
        border-radius:13px; padding:14px 18px; transition:all .16s ease;
    }}
    .row:hover {{
        border-color:var(--accent-border); background:var(--surface-alt);
        transform:translateY(-1px);
    }}
    .row-hot {{ border-left:2px solid var(--accent-bright); }}

    .co {{
        font-family:'Instrument Sans',sans-serif; font-weight:600;
        font-size:.97rem; color:var(--ink); letter-spacing:-.01em;
    }}
    .sym {{
        font-family:'JetBrains Mono',monospace; font-size:.73rem;
        color:var(--faint); margin-left:7px;
    }}
    .sum {{
        font-size:.83rem; color:var(--muted); line-height:1.45;
        margin-top:5px; max-width:74ch;
    }}
    .meta {{ display:flex; align-items:center; gap:8px; margin-top:6px; flex-wrap:wrap; }}
    .ts {{
        font-family:'JetBrains Mono',monospace; font-size:.72rem;
        color:var(--faint); white-space:nowrap;
    }}
    .chev {{ color:var(--faint); font-size:1.05rem; }}
    .row:hover .chev {{ color:var(--accent); }}

    .badge {{
        display:inline-block; vertical-align:middle; box-sizing:border-box;
        line-height:1; font-size:.66rem; font-weight:500;
        text-transform:uppercase; letter-spacing:.05em; padding:3px 8px;
        border-radius:6px; border:1px solid var(--border);
        background:var(--surface-alt); color:var(--muted); white-space:nowrap;
    }}
    .badge-results {{
        color:var(--accent); border-color:var(--accent-border);
        background:var(--accent-soft);
    }}
    .badge-exch {{
        font-family:'JetBrains Mono',monospace; letter-spacing:.02em;
        color: var(--accent);
    }}
    /* flag badges (leadership_change, order_win, etc.) — same size/
       formula as the main filing-type badge for visual uniformity,
       but sand-accent ("golden") coloring to distinguish the category */
    .badge-flag {{
        display:inline-block; vertical-align:middle; box-sizing:border-box;
        line-height:1; font-size:.66rem; font-weight:600;
        text-transform:uppercase; letter-spacing:.05em; padding:3px 8px;
        border-radius:6px; margin-right:6px; margin-bottom:6px;
        border:1px solid var(--sand-500); background:var(--sand-500);
        color:#FFFFFF; white-space:nowrap;
    }}

    /* ---------- scorecard metric grid: 3 compact cards per row ---------- */
    .metric-grid {{
        display:grid; grid-template-columns:repeat(3, 1fr); gap:8px;
    }}
    .metric-card {{
        background:var(--surface); border:1px solid var(--border);
        border-radius:10px; padding:10px 12px;
    }}

    /* ---------- notability ring ---------- */
    .ring {{
        position:relative; width:46px; height:46px; border-radius:50%;
        display:flex; align-items:center; justify-content:center; flex:none;
    }}
    .ring::before {{
        content:""; position:absolute; inset:0; border-radius:50%;
        background: conic-gradient(from -90deg,
            var(--sand-500) 0, var(--sand-200) var(--pct), var(--ring-track) var(--pct));
        -webkit-mask: radial-gradient(farthest-side,transparent calc(100% - 3.5px),#000 calc(100% - 3.5px));
        mask: radial-gradient(farthest-side,transparent calc(100% - 3.5px),#000 calc(100% - 3.5px));
    }}
    .ring span {{
        position:relative; font-family:'JetBrains Mono',monospace;
        font-size:.76rem; font-weight:600;
        background: linear-gradient(120deg, var(--ink), var(--accent) 140%);
        -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: var(--accent);
    }}
    .ring-idle::before {{
        background: none;
        border: 1.5px solid var(--accent-border);
        -webkit-mask: none; mask: none;
        animation: ring-pulse 2.6s ease-in-out infinite;
    }}
    .ring-idle span {{ color:var(--faint); }}
    @keyframes ring-pulse {{
        0%, 100% {{ opacity: .55; }}
        50% {{ opacity: 1; }}
    }}

    /* sentiment-coloured variants — extends the same up/down convention
       already used for real revenue/PAT movement to notability: net
       positive coverage (more positives than negatives, positive flags)
       rings in --up, net negative rings in --down. Neutral/mixed stays
       the default sand gradient above. This is a deliberate, requested
       extension of that colour convention, not a new decorative use. */
    .ring-positive::before {{
        background: conic-gradient(from -90deg,
            var(--up) 0, var(--up) var(--pct), var(--ring-track) var(--pct));
    }}
    .ring-positive span {{
        background: linear-gradient(120deg, var(--ink), var(--up) 140%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent; color: var(--up);
    }}
    .ring-negative::before {{
        background: conic-gradient(from -90deg,
            var(--down) 0, var(--down) var(--pct), var(--ring-track) var(--pct));
    }}
    .ring-negative span {{
        background: linear-gradient(120deg, var(--ink), var(--down) 140%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent; color: var(--down);
    }}

    .empty {{
        border:1px solid var(--border); border-radius:14px; padding:44px;
        text-align:center; color:var(--muted); font-size:.9rem;
        background: linear-gradient(135deg, var(--accent-soft) 0%, transparent 55%),
                    var(--surface);
    }}

    /* ---------- streamlit widget overrides ---------- */
    [data-testid="stTextInput"] input {{
        background:var(--surface) !important; border:1.5px solid var(--border) !important;
        border-radius:10px !important; color:var(--ink) !important;
        font-family:'Inter',sans-serif !important; height:44px;
        font-size:.9rem !important; padding-left:14px !important;
        letter-spacing:.01em;
    }}
    [data-testid="stTextInput"] input::placeholder {{
        color:var(--muted) !important; font-weight:400;
    }}
    [data-testid="stTextInput"] input:focus {{
        border-color:var(--accent) !important;
        box-shadow:0 0 0 3px var(--accent-soft) !important;
    }}
    /* hide "Press Enter to apply" globally — inputs here filter live or
       submit via their own controls, so the hint is misleading */
    [data-testid="InputInstructions"] {{ display: none !important; }}

    /* search — single pill, icon as a CSS mask directly on the input's
       own container (not a separate stacked element — that was the bug:
       a second Streamlit element doesn't share the input's exact box,
       so top:50% centered against the WRONG height and the icon floated
       above the pill instead of inside it). mask lets the icon pick up
       var(--muted)/var(--accent) as real colour, same trick used
       elsewhere for theme-aware icons without shipping multiple SVGs.

       Styled to match the chat-input reference: a rounded RECTANGLE
       (12px, not a 999px pill — the pill radius fought the rectangular
       focus ring and produced the choppy corners), with the search icon
       sitting in a sand-accent rounded button on the RIGHT edge, mirroring
       the chat input's send button. */
    .st-key-search_wrap [data-testid="stTextInput"] {{
        position: relative;
    }}
    /* kill the "Press Enter to apply" helper text Streamlit shows on
       text inputs — filtering is live on keystroke, so it's misleading */
    .st-key-search_wrap [data-testid="InputInstructions"] {{
        display: none !important;
    }}
    .st-key-search_wrap [data-testid="stTextInput"] input {{
        border-radius: 12px !important;
        padding-left: 16px !important;
        padding-right: 52px !important;   /* room for the button on the right */
        outline: none !important;
    }}
    /* the red border/underline was the browser's spellcheck + focus
       outline, not Streamlit's ring — kill both explicitly */
    .st-key-search_wrap [data-testid="stTextInput"] input:focus,
    .st-key-search_wrap [data-testid="stTextInput"] input:focus-visible {{
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-soft) !important;
        outline: none !important;
    }}
    /* accent button block on the right */
    .st-key-search_wrap [data-testid="stTextInput"]::after {{
        content: "";
        position: absolute;
        right: 5px; top: 50%; transform: translateY(-50%);
        width: 34px; height: 34px;
        border-radius: 9px;
        background: var(--accent-bright);
        z-index: 1;
        transition: filter .15s ease;
    }}
    /* the search icon, masked, centered over that button */
    .st-key-search_wrap [data-testid="stTextInput"]::before {{
        content: "";
        position: absolute;
        right: 13px; top: 50%; transform: translateY(-50%);
        width: 18px; height: 18px;
        background: #FFFFFF;
        -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") no-repeat center / contain;
                mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") no-repeat center / contain;
        pointer-events: none;
        z-index: 2;
    }}
    /* dropdown / select — same surface/border/ink tokens as every other
       card on the page, so it belongs to the site rather than clashing.
       Single border lives on the OUTER wrapper only, and radius matches
       between trigger + popover so the two don't look "choppy" against
       each other. */
    [data-testid="stSelectbox"],
    [data-testid="stSelectbox"] > div,
    [data-testid="stSelectbox"] div {{
        background: var(--surface) !important;
    }}
    [data-testid="stSelectbox"] {{
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
    }}
    [data-testid="stSelectbox"]:focus-within {{
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-soft) !important;
    }}
    [data-baseweb="select"] > div {{
        background: var(--surface) !important;
        border: none !important;
        border-radius: 10px !important;
        color: var(--ink) !important;
        min-height: 42px;
    }}
    /* every Streamlit widget internal gets explicit ink — since
       config.toml no longer pins a base theme, nothing else is setting
       these, so they must be covered here or they inherit browser
       defaults and go invisible against our surfaces */
    [data-testid="stSelectbox"] *,
    [data-testid="stTextInput"] *,
    [data-baseweb="select"] *,
    [data-baseweb="input"] *,
    [data-baseweb="popover"] *,
    [role="listbox"] *,
    [role="option"] {{
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        opacity: 1 !important;
    }}
    [data-baseweb="select"] * {{
        background: transparent !important;
    }}
    [data-baseweb="select"] [data-baseweb="tag"],
    [data-baseweb="select"] div[class*="value" i],
    [data-baseweb="select"] div[class*="Value" i] {{
        color: var(--ink) !important;
        opacity: 1 !important;
    }}
    [data-baseweb="select"] svg {{ fill: var(--muted) !important; }}

    [data-baseweb="popover"],
    [data-baseweb="popover"] > div,
    [data-baseweb="menu"],
    [data-baseweb="menu"] > div,
    [data-baseweb="popover"] ul,
    [role="listbox"],
    [role="listbox"] ul,
    [role="listbox"] > div {{
        background: var(--surface) !important;
    }}
    [data-baseweb="popover"],
    [role="listbox"] {{
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: var(--shadow) !important;
        overflow: hidden;
    }}
    [data-baseweb="popover"] li,
    [role="option"] {{
        background: var(--surface) !important;
        color: var(--ink) !important;
    }}
    [data-baseweb="popover"] li:hover,
    [data-baseweb="popover"] li[aria-selected="true"],
    [role="option"]:hover,
    [role="option"][aria-selected="true"] {{
        background: var(--accent-soft) !important;
        color: var(--ink) !important;
    }}

    .stButton button {{
        border-radius:9px !important; border:1px solid var(--border) !important;
        background:var(--surface) !important; color:var(--ink) !important;
        font-family:'Inter',sans-serif !important;
    }}
    .stButton button:hover {{ border-color:var(--accent) !important; color:var(--accent) !important; }}
    [data-testid="stAlert"] {{ border-radius:11px; }}

    /* st.chat_input — never styled before, was using Streamlit's own
       default dark chrome regardless of theme toggle */
    [data-testid="stChatInput"] {{
        background: var(--surface-alt) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
    }}
    [data-testid="stChatInput"] textarea {{
        background: transparent !important;
        color: var(--ink) !important;
    }}
    [data-testid="stChatInput"] textarea::placeholder {{
        color: var(--muted) !important;
    }}
    [data-testid="stChatInput"] button {{
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
    }}
    [data-testid="stChatInput"] svg {{ fill: var(--ink) !important; }}
    [data-testid="stChatMessage"] {{
        background: var(--surface-alt) !important;
        border-radius: 12px !important;
    }}

    /* two-button light/dark control — the active mode's button gets the
       sand accent, the other stays neutral surface. Which is active is
       set inline in apply_theme() by appending a marker class. */
    .st-key-theme_light button, .st-key-theme_dark button {{
        border-radius: 9px !important;
        font-size: .8rem !important;
        padding: 6px 0 !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--muted) !important;
    }}
    .st-key-theme_light button:hover, .st-key-theme_dark button:hover {{
        border-color: var(--accent) !important;
        color: var(--accent) !important;
    }}
    """


def apply_theme(active: str = "Filings") -> str:
    """Injects tokens + renders sidebar chrome. Returns 'light' or 'dark'.

    Theme source of truth, in priority order: URL `?theme=` param, then
    session_state, then default dark. The URL param matters because row
    navigation uses a real <a href> (a genuine browser reload, not
    Streamlit's internal SPA routing) — a hard reload can start a fresh
    session before session_state's toggle choice carries over, so the
    preference needs to also travel through the URL itself to survive
    that. Callers building links to other pages should append
    `&theme={mode}` (see Home.py's row hrefs / Filing.py's back link).

    IMPORTANT: call this FIRST, before any slow work (DB queries, etc).
    It used to accept a `pipeline` dict and render it inline, which meant
    callers had to load that data before calling apply_theme() at all —
    so the splash/CSS/hidden-auto-nav didn't apply until AFTER those
    queries finished, leaving raw unstyled Streamlit visible the whole
    time. Pipeline stats now render separately via render_sidebar_pipeline()
    after apply_theme() has already run.
    """
    # Seed from the URL only when session_state has no value yet (a
    # genuinely fresh session/hard reload). Once theme_mode exists, trust
    # it exclusively — otherwise a lingering ?theme= param in the address
    # bar (which doesn't clear itself between reruns) would keep
    # stomping on an active toggle click every single rerun. This was
    # exactly why the toggle worked on the Filing page (reached via
    # switch_page, no leftover param) but not on Home (reached via a
    # hard <a href>, param persists in the URL indefinitely).
    if "theme_mode" not in st.session_state:
        url_theme = st.query_params.get("theme")
        st.session_state["theme_mode"] = url_theme if url_theme in ("light", "dark") else "dark"

    mode = st.session_state["theme_mode"]
    st.markdown(f"<style>{_css(DARK if mode == 'dark' else LIGHT)}</style>",
                unsafe_allow_html=True)

    # NOTE: the load-time splash that masks the pre-boot flash is NOT here
    # anymore — it lives in Streamlit's index.html via patch_splash.py.
    # It has to, because a Python/component-injected splash only loads
    # AFTER Streamlit's React app has already painted its default chrome,
    # which is the half-second flash you were seeing. The HTML-shell
    # splash paints on frame one instead. Run `python patch_splash.py`
    # once (and after any streamlit upgrade) to install it.
    # The stSidebarNav display:none rule in _css() above still hides the
    # auto page-nav as a CSS backstop.

    # Sidebar starts COLLAPSED (see initial_sidebar_state="collapsed" in
    # each page's set_page_config) so there's nothing to flash in the
    # first place. This script re-opens it automatically, shortly after
    # real content has rendered — clicking the same expand control a
    # person would click by hand, found via the broad selector set we
    # already use elsewhere for that control (testid naming varies by
    # Streamlit version). Runs once per page load (session_state guard),
    # not on every rerun, so it doesn't fight a person who deliberately
    # collapses it again mid-session.
    if not st.session_state.get("_sidebar_auto_opened"):
        st.session_state["_sidebar_auto_opened"] = True
        import streamlit.components.v1 as _components
        _components.html(
            """
            <script>
            (function () {
                const doc = window.parent.document;
                function findExpandBtn() {
                    const selectors = [
                        '[data-testid*="ollapse" i] button',
                        '[data-testid*="xpand" i] button',
                        '[data-testid="stSidebarCollapsedControl"] button',
                        'button[aria-label*="sidebar" i]',
                    ];
                    for (const sel of selectors) {
                        const el = doc.querySelector(sel);
                        if (el) return el;
                    }
                    return null;
                }
                function tryOpen() {
                    const btn = findExpandBtn();
                    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                    const isCollapsed = sidebar && sidebar.getAttribute('aria-expanded') === 'false';
                    if (btn && isCollapsed) { btn.click(); return true; }
                    return !sidebar || !isCollapsed; // nothing to do / already open
                }
                let ticks = 0;
                const iv = setInterval(function () {
                    if (tryOpen() || ++ticks > 40) clearInterval(iv);
                }, 150);
            })();
            </script>
            """,
            height=0,
        )

    with st.sidebar:
        st.markdown(
            '<div class="wordmark">Senti<span class="wm-accent">SME</span>tric</div>'
            '<div class="brand-sub">SME filing intelligence</div>',
            unsafe_allow_html=True,
        )

        html = ""
        nav_targets = {"Filings": "/", "Watchlist": "/Watchlist"}
        for item in ("Filings", "Watchlist", "Macro brief"):
            cls = "nav-item active" if item == active else "nav-item"
            if item in nav_targets:
                href = f'{nav_targets[item]}?theme={st.session_state["theme_mode"]}'
                html += (f'<a class="{cls}" href="{href}" target="_self" '
                         f'style="text-decoration:none;">'
                         f'<span class="nav-dot"></span>{item}</a>')
            else:
                html += (f'<div class="{cls}"><span class="nav-dot"></span>{item}'
                         f'<span class="faint" style="margin-left:auto;font-size:.66rem;">soon</span></div>')
        st.markdown(html, unsafe_allow_html=True)

        # pipeline stats (if any) render separately via
        # render_sidebar_pipeline() — see note in the docstring above

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        # Two-button light/dark control instead of st.toggle — BaseWeb's
        # toggle markup varies by version and kept evading our CSS
        # (invisible track in light mode). These are plain buttons we
        # fully style via .st-key-theme_* hooks below.
        st.markdown('<div class="eyebrow" style="margin-bottom:6px;">Appearance</div>',
                    unsafe_allow_html=True)
        # highlight whichever button matches the current mode
        _active = "theme_light" if mode == "light" else "theme_dark"
        st.markdown(
            f'<style>.st-key-{_active} button {{'
            f'background: var(--accent-soft) !important;'
            f'border-color: var(--accent-border) !important;'
            f'color: var(--accent) !important; font-weight: 600 !important;}}</style>',
            unsafe_allow_html=True,
        )
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            with st.container(key="theme_light"):
                if st.button("☀ Light", use_container_width=True):
                    st.session_state["theme_mode"] = "light"
                    st.rerun()
        with tcol2:
            with st.container(key="theme_dark"):
                if st.button("☾ Dark", use_container_width=True):
                    st.session_state["theme_mode"] = "dark"
                    st.rerun()

    return mode


def render_sidebar_pipeline(pipeline: dict | None) -> None:
    """Renders the pipeline status rows in the sidebar. Call this AFTER
    apply_theme() and AFTER your data has loaded — it's deliberately
    separate from apply_theme() so theming never has to wait on a DB
    query first. Appears below the light/dark control since it's added
    later in page flow; that's a fine tradeoff for not blocking the
    splash/CSS/hidden-nav on data loading.
    """
    if not pipeline:
        return
    with st.sidebar:
        rows = "".join(
            f'<div class="pipe-row"><span>{k.title()}</span><b>{v}</b></div>'
            for k, v in pipeline.items()
        )
        st.markdown(
            '<div class="pipe"><div class="eyebrow" style="margin-bottom:8px;">'
            f'Pipeline</div>{rows}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# HTML component helpers
# ---------------------------------------------------------------------------

def ring(score, sentiment: str | None = None) -> str:
    """Notability ring. sentiment: 'positive' | 'negative' | None (neutral,
    default sand gradient). Shows the actual score; the ring FILL is
    capped at 10 visually (a score of 15 fills the ring fully) but the
    printed number is the real value, since notability() is intentionally
    uncapped and the exact figure is meaningful for ranking."""
    if score is None:
        return '<div class="ring ring-idle" style="--pct:0%"><span>&mdash;</span></div>'
    pct = max(0.0, min(float(score), 10.0)) / 10.0 * 100
    cls = "ring"
    if sentiment == "positive":
        cls += " ring-positive"
    elif sentiment == "negative":
        cls += " ring-negative"
    return f'<div class="{cls}" style="--pct:{pct:.0f}%"><span>{score:.1f}</span></div>'


def row_sentiment(positives, negatives, flags) -> str | None:
    """Same logic as notability_sentiment(), but takes raw values
    directly — for list/table views querying individual columns rather
    than a full Insight ORM object (e.g. Home.py's row query)."""
    if positives is None and negatives is None:
        return None
    pos = len(positives or [])
    neg = len(negatives or [])
    flags = flags or {}

    NEGATIVE_FLAGS = {"auditor_qualification", "pledge", "guidance_negative",
                       "regulatory_action", "litigation"}
    POSITIVE_FLAGS = {"order_win", "capacity_expansion", "guidance_positive"}

    flag_score = sum(1 for f in NEGATIVE_FLAGS if f in flags) * -1
    flag_score += sum(1 for f in POSITIVE_FLAGS if f in flags)

    net = (pos - neg) + flag_score
    if net > 0:
        return "positive"
    if net < 0:
        return "negative"
    return None


def notability_sentiment(insight) -> str | None:
    """Same as row_sentiment(), for callers that already have a full
    Insight ORM object (e.g. Filing.py's detail page)."""
    if insight is None:
        return None
    return row_sentiment(insight.positives, insight.negatives, insight.flags)


def badge(filing_type: str) -> str:
    key = (filing_type or "").lower()
    cls = "badge-results" if "result" in key else ""
    label = (filing_type or "unknown").replace("_", " ").title()
    return f'<span class="badge {cls}">{label}</span>'


def flag_badges(flags: dict | None, max_shown: int | None = None) -> str:
    """Small pill badges for each detected flag (leadership_change,
    order_win, etc.) — shared between Home's row preview (capped via
    max_shown, since row space is tight) and the Filing detail header
    (uncapped, shown in full). Flag NAMES only, not their matched quote
    text — this is a compact preview, not the full evidence (that's
    what the Insight section's grounded quotes are for)."""
    if not flags:
        return ""
    names = list(flags.keys())
    shown = names if max_shown is None else names[:max_shown]
    extra = len(names) - len(shown)
    html = "".join(
        f'<span class="badge-flag">★ {n.replace("_", " ").title()}</span>'
        for n in shown
    )
    if extra > 0:
        html += f'<span class="badge-flag">+{extra} more</span>'
    return html


def tile(label: str, value, sub: str = "") -> str:
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="tile"><div class="lab">{label}</div>'
            f'<div class="val">{value}</div>{sub_html}</div>')