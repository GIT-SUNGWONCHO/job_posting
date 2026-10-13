"""리멤버(career.rememberapp.co.kr) 수집기. 전체 공고를 받아 범위 규칙으로 고른다.

확인된 사실(2026.10):
- 목록: POST https://career-api.rememberapp.co.kr/job_postings/search
- body {"search": {...}, "page": 1부터, "per": 최대 50}. 51 이상이면 "최대 요청 수 초과"
- 공고 본문(주요업무, 자격요건, 우대사항)이 목록에 같이 온다
- 헤드헌터 공고는 job_posting_type이 internal_headhunter, organization.headhunter가 true
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..http import Client
from ..models import DeadlineType, Posting, Source
from . import CollectResult

API = "https://career-api.rememberapp.co.kr/job_postings/search"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://career.rememberapp.co.kr",
    "Referer": "https://career.rememberapp.co.kr/",
}


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _description(item: dict[str, Any]) -> str | None:
    sections = [
        ("주요업무", item.get("job_description")),
        ("자격요건", item.get("qualifications")),
        ("우대사항", item.get("preferred_qualifications")),
        ("채용절차", item.get("recruiting_process")),
    ]
    text = "\n\n".join(f"[{name}]\n{body.strip()}" for name, body in sections if body and body.strip())
    return text or None


def parse_item(item: dict[str, Any]) -> Posting:
    org = item.get("organization") or {}
    ends = _datetime(item.get("ends_at"))
    cmin, cmax = item.get("min_experience"), item.get("max_experience")
    region = (item.get("normalized_address") or {}).get("level1")
    cats = []
    for c in item.get("job_categories") or []:
        cats.append(c.get("level1"))
        cats.append(f"{c.get('level1')}/{c.get('level2')}")
    headhunter = item.get("job_posting_type") != "general" or bool(org.get("headhunter"))
    link = item.get("link") or None
    return Posting(
        source=Source.REMEMBER,
        source_id=str(item["id"]),
        url=f"https://career.rememberapp.co.kr/job/posting/{item['id']}",
        apply_url=link if item.get("application_type") == "redirection" else None,
        company=org.get("name") or "",
        title=item.get("title") or "",
        career_min=cmin if cmin else None,
        career_max=cmax,
        newcomer=not cmin,
        deadline_type=DeadlineType.DATE if ends else DeadlineType.UNTIL_FILLED,
        deadline=ends.date() if ends else None,
        regions=[region] if region else [],
        categories=list(dict.fromkeys(c for c in cats if c)),
        headhunter=headhunter,
        posted_at=_datetime(item.get("starts_at")),
        description=_description(item),
        raw=item,
    )


class RememberCollector:
    def __init__(self, client: Client, cfg: dict[str, Any]):
        self.client = client
        self.cfg = cfg

    def _page(self, page: int) -> dict[str, Any]:
        body = {"search": {}, "page": page, "per": self.cfg.get("per", 50)}
        return self.client.post(API, json=body, headers=HEADERS).json()

    def collect(self, max_pages: int | None = None) -> CollectResult:
        result = CollectResult(source=Source.REMEMBER.value)
        start = self.client.requests
        found: dict[str, dict[str, Any]] = {}
        page, total_pages = 1, None
        while True:
            try:
                data = self._page(page)
            except Exception as e:
                result.complete = False
                result.errors.append(f"페이지 {page}: {e}")
                break
            items = data.get("data") or []
            if not isinstance(items, list):
                result.complete = False
                result.errors.append(f"페이지 {page}: {data.get('meta')}")
                break
            for x in items:
                found[str(x["id"])] = x
            total_pages = (data.get("meta") or {}).get("total_pages") or total_pages
            page += 1
            if not items or (total_pages and page > total_pages):
                break
            if max_pages is not None and page > max_pages:
                result.complete = False  # 일부만 받았으니 마감 판단에 쓰지 않는다
                break
        for item in found.values():
            try:
                result.postings.append(parse_item(item))
            except Exception as e:
                result.errors.append(f"파싱 {item.get('id')}: {e}")
        result.requests = self.client.requests - start
        return result
