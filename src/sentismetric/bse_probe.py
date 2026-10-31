"""
bse_probe_results.py -- probe BSE Corp_FinanceResult_ng_new (the API the
Financial Results page really uses) and the Integrated Filing HTML files it
points to. Read-only. Run: python bse_probe_results.py  (window opens, ~90s)
"""

import json
import re

from playwright.sync_api import sync_playwright

PAGE = "https://www.bseindia.com/corporates/Comp_Resultsnew.aspx"
API = "https://api.bseindia.com/BseIndiaAPI/api/Corp_FinanceResult_ng_new/w"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

FETCH_JS = """async (u) => { try { const r = await fetch(u);
    return {s: r.status, ct: r.headers.get('content-type')||'', b: await r.text()}; }
    catch (e) { return {s: -1, ct: '', b: String(e)}; } }"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-http2"])
        ctx = browser.new_context(user_agent=UA, locale="en-IN")
        page = ctx.new_page()
        try:
            page.goto(PAGE, wait_until="commit", timeout=60000)
        except Exception as e:
            print("goto raised (often fine):", repr(e))
        page.wait_for_timeout(10000)

        def get(url):
            return page.evaluate(FETCH_JS, url)

        # 1) how much history per FlagDur, quarterly only
        print("=== row counts per FlagDur (HFQ=3 quarterly, segment=C) ===")
        first_rows = {}
        for fd in range(1, 8):
            r = get(f"{API}?SCRIP_CD=&FlagDur={fd}&HFQ=3&ISUBGROUP_CODE=&segment=C")
            try:
                d = json.loads(r["b"])
                tables = {k: len(v) for k, v in d.items() if isinstance(v, list)}
                print(f"FlagDur={fd}: status={r['s']} tables={tables} chars={len(r['b'])}")
                t = d.get("Table") or []
                if t:
                    first_rows[fd] = t
            except Exception:
                print(f"FlagDur={fd}: status={r['s']} NOT JSON: {r['b'][:120]!r}")

        rows = first_rows.get(2) or first_rows.get(1) or next(iter(first_rows.values()), [])
        print("\n=== FULL first row ===")
        if rows:
            print(json.dumps(rows[0], ensure_ascii=False, indent=1))
            print("\nrow keys:", list(rows[0].keys()))
            codes = sorted({int(r["Scrip_cd"]) for r in rows if r.get("Scrip_cd") is not None})
            print("scrip code range in this batch:", codes[:3], "...", codes[-3:], f"({len(codes)} unique)")
            print("quarter_code values:", sorted({r.get("quarter_code") for r in rows})[:10])
            print("Fld_NatureOfReport values:", sorted({str(r.get('Fld_NatureOfReport')) for r in rows}))

        # 2) the HTML files
        print("\n=== downloading XMLName HTML files ===")
        bases = [
            "https://www.bseindia.com/XBRLFILES/",
            "https://www.bseindia.com/xbrlfiles/",
            "https://www.bseindia.com/",
            "https://api.bseindia.com/BseIndiaAPI/api/",
        ]
        tried = 0
        for row in rows[:3]:
            for field in ("XMLName", "Consol_XMLName"):
                name = row.get(field)
                if not name:
                    continue
                print(f"\n-- {row.get('company_name')} [{row.get('Scrip_cd')}] {field}: {name}")
                for b in bases:
                    r = get(b + name)
                    print(f"   {b}  -> status={r['s']} ct={r['ct']} chars={len(r['b'])}")
                    if r["s"] == 200 and len(r["b"]) > 500 and "<html" in r["b"][:2000].lower():
                        body = r["b"]
                        print("   HTML head:", re.sub(r"\s+", " ", body[:600]))
                        # look for the numbers we need
                        for label in ["Revenue From Operations", "Total Income", "Profit",
                                      "Earnings per share", "Total expenses", "Borrowings"]:
                            m = [x.start() for x in re.finditer(label, body, flags=re.I)][:2]
                            for pos in m:
                                snippet = re.sub(r"<[^>]+>", " ", body[pos:pos + 400])
                                snippet = re.sub(r"\s+", " ", snippet)[:160]
                                print(f"   [{label}] ...{snippet}")
                        print("   has XBRL-ish ix: tags:", "ix:nonfraction" in body.lower(),
                              "| in-capmkt tags:", "in-capmkt" in body.lower())
                        break
                tried += 1
            if tried >= 4:
                break

        # 3) one SME-style scrip code lookup (pagination / per-company use)
        print("\n=== per-company call (using first row's scrip code) ===")
        if rows:
            sc = rows[0]["Scrip_cd"]
            r = get(f"{API}?SCRIP_CD={sc}&FlagDur=7&HFQ=3&ISUBGROUP_CODE=&segment=C")
            try:
                d = json.loads(r["b"])
                print("per-company FlagDur=7:", {k: len(v) for k, v in d.items() if isinstance(v, list)})
                t = d.get("Table") or []
                for x in t[:6]:
                    print("  ", x.get("quarter_code"), x.get("DT_TM"), x.get("Fld_NatureOfReport"), x.get("XMLName"))
            except Exception:
                print("not json:", r["b"][:150])

        browser.close()
    print("\nDONE.")


if __name__ == "__main__":
    main()