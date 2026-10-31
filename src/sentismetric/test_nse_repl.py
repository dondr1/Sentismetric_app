import httpx

url = "https://www.nseindia.com/api/corporate-announcements"
params = {"index": "equities"}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"}

for i in range(3):
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=10)
        print(f"Attempt {i+1}: Status {r.status_code}")
    except httpx.ReadTimeout:
        print(f"Attempt {i+1}: ReadTimeout")