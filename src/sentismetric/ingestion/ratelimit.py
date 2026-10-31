import time


class RateLimiter:
    def __init__(self, max_rps: float):
        self.min_interval = 1.0 / max_rps
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        sleep_for = self._last + self.min_interval - now
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last = time.monotonic()