import httpx

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
}

r = httpx.get("https://m.bseindia.com/smemarket.aspx", headers=headers, timeout=15)
html = r.text

# Find where "INA" appears in the raw HTML and print surrounding context
idx = html.find(">INA<")
if idx == -1:
    idx = html.find("INA")
print(f"Found 'INA' at index {idx}")
print("--- Context around it ---")
print(html[max(0, idx - 300):idx + 100])
print("--- End context ---")

# Also check where "SME" (the nav junk) appears, for comparison
idx2 = html.find(">SME<")
if idx2 == -1:
    idx2 = html.find("SME")
print(f"\nFound 'SME' at index {idx2}")
print("--- Context around it ---")
print(html[max(0, idx2 - 300):idx2 + 100])
print("--- End context ---")