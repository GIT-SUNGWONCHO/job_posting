"""화면용 파일을 Supabase 비공개 저장소에 올린다.

키는 환경 변수(GitHub Secrets)로만 받는다: SUPABASE_URL, SUPABASE_SECRET_KEY.
저장소 이름과 경로는 화면 코드(web/src/lib/supabase.ts)와 같아야 한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

BUCKET = "screen"
OBJECT = "screen.json.gz"


def configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


def upload(path: Path, session: requests.Session | None = None) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SECRET_KEY"]
    headers = {
        "apikey": key,
        "Content-Type": "application/gzip",
        "x-upsert": "true",
        "cache-control": "max-age=300",
    }
    # 예전 service_role 키(JWT)는 Authorization에도 넣는다. 새 비밀 키(sb_secret_)는 JWT가 아니라 apikey만 쓴다
    if key.count(".") == 2:
        headers["Authorization"] = f"Bearer {key}"
    http = session or requests.Session()
    resp = http.post(f"{url}/storage/v1/object/{BUCKET}/{OBJECT}", data=path.read_bytes(),
                     headers=headers, timeout=60)
    if resp.status_code >= 300:
        # 응답 본문에는 키가 들어 있지 않지만 길이는 줄여서 남긴다
        raise RuntimeError(f"화면용 파일 올리기 실패: {resp.status_code} {resp.text[:200]}")
