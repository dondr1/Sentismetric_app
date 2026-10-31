from pathlib import Path
import re

xbrl_dir = Path("data/xbrl/NSE")
files = list(xbrl_dir.glob("*.xml"))

text = files[0].read_text(encoding="utf-8", errors="ignore")

# find all element tag names (opening tags), NSE-style plain XBRL
tag_names = set(re.findall(r"<([A-Za-z][\w\-]*:[A-Za-z][\w\-]*)[ >]", text))
print(f"File: {files[0].name}")
print(f"Found {len(tag_names)} distinct tags")
for name in sorted(tag_names):
    print(" ", name)