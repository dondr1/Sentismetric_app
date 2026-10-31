from pathlib import Path
import re

# use a file we know parses cleanly -- PRITIKA's Q2
text = Path("data/xbrl/NSE/PRITIKA_1184484.xml").read_text(encoding="utf-8", errors="ignore")

tag_names = set(re.findall(r"<(in-bse-fin:[A-Za-z][\w\-]*)[ >]", text))
# filter to expense/cost-related concepts
cost_tags = sorted(t for t in tag_names if re.search(r"expense|cost|expenditure", t, re.IGNORECASE))
print("Cost/expense-related tags found:")
for t in cost_tags:
    print(" ", t)