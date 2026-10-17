"""Supabase DB(REST) 읽기·쓰기. 매일 작업이 서버 키로 쓴다(행 단위 권한을 건너뛴다).

키는 환경 변수 SUPABASE_URL, SUPABASE_SECRET_KEY로만 받는다. 저장소(Storage)는 publish.py.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests


def configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


class DB:
    def __init__(self, session: requests.Session | None = None):
        self.url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
        key = os.environ["SUPABASE_SECRET_KEY"]
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.count(".") == 2:  # 예전 service_role 키(JWT)
            self.headers["Authorization"] = f"Bearer {key}"
        self.http = session or requests.Session()
        self._used = time.monotonic()

    def _check(self, resp: requests.Response) -> requests.Response:
        if resp.status_code >= 300:
            raise RuntimeError(f"Supabase {resp.request.method} {resp.status_code} {resp.text[:200]}")
        return resp

    def check_server_key(self) -> None:
        """서버 키로 들어왔는지 확인한다. 행 단위 권한에 막히면 오류 없이 빈 목록이 와서 겉으로는 구분이 안 된다.
        없는 사람 id로 매칭 행을 넣어 본다: 서버 키면 사람 참조 오류(23503)로 막히고, 아니면 권한 오류가 난다.
        """
        resp = self.http.post(f"{self.url}/matches", json={
            "user_id": "00000000-0000-0000-0000-000000000000", "posting_id": "-", "score": 0, "parts": {},
            "score_v": 0, "profile_v": 0, "computed_on": "2000-01-01"}, headers={**self.headers, "Prefer": "return=minimal"}, timeout=60)
        code = resp.json().get("code") if resp.headers.get("content-type", "").startswith("application/json") else None
        if code != "23503":
            raise RuntimeError(f"Supabase 키가 서버 권한으로 들어가지 않음({resp.status_code} {code}). SUPABASE_SECRET_KEY를 확인")

    def _send(self, method: str, url: str, **kw: Any) -> requests.Response:
        """AI를 부르는 동안 몇 분 쉰 연결은 응답 없이 끊겨 있다(2026-10-14 Actions에서 매칭 끝 DELETE가 두 번 60초 시간 초과).
        1분 넘게 쉬었으면 새 연결로 보내고, 그래도 연결 오류·시간 초과면 두 번까지 다시 보낸다.
        다시 보내도 같은 결과가 되는 요청만 이걸 쓴다."""
        if time.monotonic() - self._used > 60:
            self.http = requests.Session()
        for attempt in range(3):
            self._used = time.monotonic()
            try:
                return self._check(self.http.request(method, url, timeout=60, **kw))
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                self.http = requests.Session()
                time.sleep(2 * (attempt + 1))
        raise AssertionError("unreachable")

    def select(self, table: str, query: str = "select=*") -> list[dict[str, Any]]:
        return self._send("GET", f"{self.url}/{table}?{query}", headers=self.headers).json()

    def delete(self, table: str, query: str) -> None:
        self._send("DELETE", f"{self.url}/{table}?{query}", headers=self.headers)

    def update(self, table: str, query: str, values: dict[str, Any]) -> None:
        """query에 맞는 줄의 값을 바꾼다(없으면 아무 일도 없다)."""
        self._send("PATCH", f"{self.url}/{table}?{query}", json=values, headers={**self.headers, "Prefer": "return=minimal"})

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        """기본 키가 같은 줄은 덮어쓴다(다시 보내도 안전하고, 중간 저장한 줄을 마지막에 다시 써도 된다)."""
        for i in range(0, len(rows), 500):
            self._send("POST", f"{self.url}/{table}", json=rows[i:i + 500],
                       headers={**self.headers, "Prefer": "return=minimal,resolution=merge-duplicates"})
