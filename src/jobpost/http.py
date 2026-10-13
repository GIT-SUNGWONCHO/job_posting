"""수집처 요청용 HTTP 클라이언트. 재시도, 호스트별 최소 간격, 수집처별 시간 한도를 지킨다."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class TimeBudgetExceeded(RuntimeError):
    """수집처에 쓸 시간을 다 썼다. 받은 데까지만 저장하고 '일부만 받음'으로 처리한다."""


class Client:
    def __init__(self, min_interval: float = 0.5, timeout: tuple[float, float] = (10.0, 30.0),
                 max_minutes: float | None = None, backoff: float = 1.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self.deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
        self._last: dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
        # 응답이 멈추는 경우(2026.10 리멤버)가 있어 재시도는 짧게 한다
        retry = Retry(
            total=3,
            backoff_factor=backoff,
            backoff_max=60,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
            respect_retry_after_header=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.requests = 0

    def _wait(self, url: str) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise TimeBudgetExceeded("시간 한도 초과")
        host = urlparse(url).netloc
        last = self._last.get(host)
        if last is not None:
            gap = time.monotonic() - last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
        self._last[host] = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response:
        self._wait(url)
        self.requests += 1
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, url: str, **kwargs) -> requests.Response:
        self._wait(url)
        self.requests += 1
        resp = self.session.post(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp
