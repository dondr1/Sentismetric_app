import httpx
from datetime import date

today = date.today().strftime("%Y%m%d")

url = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
params = {
    "pageno": 1,
    "strCat": -1,
    "strPrevDate": today,
    "strScrip": "",
    "strSearch": "P",
    "strToDate": today,
    "strType": "C",
    "subcategory": -1,
}
headers = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
}

r = httpx.get(url, params=params, headers=headers, timeout=15)
print("Status:", r.status_code)
data = r.json()
print("Type of response:", type(data))
if isinstance(data, dict):
    print("Keys:", data.keys())
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  {k}: list of {len(v)} items")
            if v:
                print(f"  first item: {v[0]}")