"""Supabase DB(REST) 읽기·쓰기. 매일 작업이 서버 키로 쓴다(행 단위 권한을 건너뛴다).

키는 환경 변수 SUPABASE_URL, SUPABASE_SECRET_KEY로만 받는다. 저장소(Storage)는 publish.py.
"""

from __future__ import annotations

import os
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

    def select(self, table: str, query: str = "select=*") -> list[dict[str, Any]]:
        return self._check(self.http.get(f"{self.url}/{table}?{query}", headers=self.headers, timeout=60)).json()

    def delete(self, table: str, query: str) -> None:
        self._check(self.http.delete(f"{self.url}/{table}?{query}", headers=self.headers, timeout=60))

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), 500):
            self._check(self.http.post(f"{self.url}/{table}", json=rows[i:i + 500],
                                       headers={**self.headers, "Prefer": "return=minimal"}, timeout=60))
