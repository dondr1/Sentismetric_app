import httpx
from sentismetric.config import settings
from sentismetric.log import log
from sentismetric.ingestion.ratelimit import RateLimiter


NSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US, en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
WARMUP_URL = "https://www.nseindia.com"

class NseSession:
    def __init__(self) -> None:
        self._client: httpx.Client | None = None
        self._limiter = RateLimiter(settings.nse_max_rps)
    
    def _warm(self) -> None:
        log.info("warning NSE session")
        self._client = httpx.Client(headers=NSE_HEADERS,follow_redirects=True, timeout=20)
        self._limiter.wait()
        self._client.get(WARMUP_URL)
    
    def get_json(self, url: str, params: dict | None = None) -> dict:
        if self._client is None:
            self._warm()
        self._limiter.wait()
        r = self._client.get(url, params=params)
        if r.status_code in (401, 403):
            log.warning("NSE sessoin expired: re-warming")
            self._warm()
            self._limiter.wait()
            r = self._client.get(url, params = params)
        r.raise_for_status()
        return r.json()