"""
patch_splash.py — eliminate the pre-boot flash by injecting a splash
overlay directly into Streamlit's served index.html.

WHY THIS EXISTS (and why nothing in theme.py could fix it):
The flash you saw — raw Home/Filing nav + Deploy toolbar for ~half a
second before the app appears — happens BEFORE any Python-injected CSS
or component JS loads. st.markdown styles and st.components scripts only
run once Streamlit's React app has already booted and painted its
default chrome. So the only place a splash can win the race is the HTML
shell itself, served before React starts. This script edits that shell.

WHAT IT DOES:
Adds a fixed full-screen overlay (correct theme background + wordmark)
into <body>, plus a tiny script in <head> that removes the overlay once
Streamlit's #root actually has content. Painted on frame one; gone the
moment the real app is ready.

CAVEAT — re-run after upgrades:
This edits a file inside the installed streamlit package. A
`pip install --upgrade streamlit` replaces index.html and wipes the
patch. Just re-run `python patch_splash.py` after any streamlit upgrade.
The script is idempotent (it won't double-inject) and reversible
(`python patch_splash.py --revert`).

USAGE:
    python patch_splash.py            # apply
    python patch_splash.py --revert   # undo
"""

import sys
from pathlib import Path

import streamlit

# Match the app's dark-mode bg / accent so the splash looks native.
BG = "#0A0B0F"
INK = "#F2F3F5"
ACCENT = "#CD9F66"

MARKER = "senti-splash-shell"  # lets us detect / remove a prior injection

HEAD_SNIPPET = f"""
    <!-- {MARKER}:head -->
    <style id="{MARKER}-style">
      #{MARKER} {{
        position: fixed; inset: 0; z-index: 2147483647;
        background: {BG}; display: flex; align-items: center;
        justify-content: center; transition: opacity .35s ease;
        font-family: 'Instrument Sans', -apple-system, sans-serif;
      }}
      #{MARKER} .m {{
        font-weight: 700; font-size: 1.55rem; letter-spacing: -.02em;
        color: {INK}; opacity: .92;
      }}
      #{MARKER} .m span {{ color: {ACCENT}; }}
    </style>
    <script>
      // Remove the splash once Streamlit's #root actually has content,
      // with a hard fallback so it can never get stuck.
      (function () {{
        function remove() {{
          var s = document.getElementById("{MARKER}");
          if (s) {{ s.style.opacity = "0"; setTimeout(function(){{ s.remove(); }}, 400); }}
        }}
        function ready() {{
          var root = document.getElementById("root");
          return root && root.querySelector('[data-testid="stApp"], [data-testid="stAppViewContainer"]');
        }}
        var iv = setInterval(function () {{
          if (ready()) {{ clearInterval(iv); setTimeout(remove, 200); }}
        }}, 60);
        setTimeout(function () {{ clearInterval(iv); remove(); }}, 6000);
      }})();
    </script>
    <!-- /{MARKER}:head -->
"""

BODY_SNIPPET = f"""
    <!-- {MARKER}:body -->
    <div id="{MARKER}"><div class="m">Senti<span>SME</span>tric</div></div>
    <!-- /{MARKER}:body -->
"""


def index_path() -> Path:
    return Path(streamlit.__file__).parent / "static" / "index.html"


def revert(html: str) -> str:
    import re
    # consume the block plus any newline/indent immediately after it, so
    # nothing (not even a blank line) is left behind
    html = re.sub(rf"\s*<!-- {MARKER}:head -->.*?<!-- /{MARKER}:head -->\s*\n?",
                  "\n", html, flags=re.DOTALL)
    html = re.sub(rf"\s*<!-- {MARKER}:body -->.*?<!-- /{MARKER}:body -->\s*\n?",
                  "\n", html, flags=re.DOTALL)
    return html


def main():
    do_revert = "--revert" in sys.argv
    p = index_path()
    if not p.exists():
        print(f"Could not find Streamlit index.html at {p}")
        sys.exit(1)

    html = p.read_text(encoding="utf-8")

    # always strip any prior injection first (idempotent)
    html = revert(html)

    if do_revert:
        p.write_text(html, encoding="utf-8")
        print(f"Reverted. {p}")
        return

    if "</head>" not in html or "<body>" not in html:
        print("index.html structure unexpected — aborting to avoid corruption.")
        sys.exit(1)

    html = html.replace("</head>", HEAD_SNIPPET + "\n  </head>", 1)
    html = html.replace("<body>", "<body>\n" + BODY_SNIPPET, 1)

    p.write_text(html, encoding="utf-8")
    print(f"Splash injected into {p}")
    print("Restart Streamlit to see it. Re-run this after any streamlit upgrade.")


if __name__ == "__main__":
    main()