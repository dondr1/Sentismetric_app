"""
list_bse_rows.py -- show every result row BSE returns for one company, to
see which quarter codes and file types exist. Read-only.

    python list_bse_rows.py 534109 --headed
"""

import argparse
from collections import Counter

from sentismetric.ingestion.bse_financials import (
    BseBrowserSession, fetch_company_rows, label_from_quarter_code,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scrip", type=int)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    with BseBrowserSession(headless=not args.headed) as b:
        rows = fetch_company_rows(b, args.scrip)

    print(f"{len(rows)} rows for {args.scrip}\n")
    print("quarter_code counts:", dict(Counter(r.get("quarter_code") for r in rows)))
    print()
    print(f"{'quarter_code':<14}{'label':<16}{'created':<22}{'nature':<14}file")
    for r in sorted(rows, key=lambda r: r.get("Fld_CreateDate") or "", reverse=True):
        lab = label_from_quarter_code(r.get("quarter_code"))
        print(f"{str(r.get('quarter_code')):<14}{(lab[0] if lab else '(skipped)'):<16}"
              f"{str(r.get('Fld_CreateDate'))[:19]:<22}{str(r.get('Fld_NatureOfReport')):<14}"
              f"{str(r.get('XMLName'))[-60:]}")


if __name__ == "__main__":
    main()