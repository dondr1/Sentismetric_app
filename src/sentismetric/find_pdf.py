from pathlib import Path
import re

xbrl_dir = Path("data/xbrl/NSE")
dtl_files = list(xbrl_dir.glob("DTL_*.xml"))
print(f"Found {len(dtl_files)} DTL files: {[f.name for f in dtl_files]}")

for f in dtl_files:
    text = f.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<in-bse-fin:RevenueFromOperations[^>]*>.*?</in-bse-fin:RevenueFromOperations>", text)
    print(f"\n{f.name}:")
    print(match.group(0) if match else "  no RevenueFromOperations tag found at all")