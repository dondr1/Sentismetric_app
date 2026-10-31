import re

# reuse fetched text
import httpx
url = "https://www.bseindia.com/XBRLFILES/IFOtherthanDuplicateUploadDocument/IFOtherthan_544458_2952026185119_IFOtherthan.html"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
r = httpx.get(url, headers=headers, timeout=15)
text = r.text

match = re.search(r"<ix:nonFraction[^>]*name=['\"][^'\"]*Revenue[^'\"]*['\"][^>]*>.*?</ix:nonFraction>", text)
print(match.group(0) if match else "no Revenue tag found")