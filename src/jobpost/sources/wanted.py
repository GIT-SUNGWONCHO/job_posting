"""원티드(wanted.co.kr) 수집기. 데이터·AI 직무 태그 목록을 받고, 본문은 상세로 따로 받는다.

확인된 API 동작(엔드포인트, 태그 id, 경력·마감 표기)은 docs/collection.md "수집처에서 확인된 사실"에 있다.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Any

from ..http import Client, TimeBudgetExceeded
from ..models import DeadlineType, Detail, Posting, Source
from ..normalize import clean_company, common_name, company_key
from . import CollectResult

log = logging.getLogger(__name__)

LIST_URL = "https://www.wanted.co.kr/api/v4/jobs"
DETAIL_URL = "https://www.wanted.co.kr/api/v4/jobs/{}"
HEADERS = {"Accept": "application/json", "Referer": "https://www.wanted.co.kr/"}
NO_MAX = 100  # annual_to 100은 상한 없음
# 본문은 리멤버와 같은 칸만 쓴다. 회사 소개·복지는 스킬 수를 흐려서 뺀다(원문 링크에서 볼 수 있다)
SECTIONS = [("주요업무", "main_tasks"), ("자격요건", "requirements"), ("우대사항", "preferred_points")]


# 원티드 회사 이름은 "한글 이름(영문 또는 다른 이름)" 꼴이 많다: 컷백(Cutback), 씨제이올리브영(CJ올리브영)
_ALT = re.compile(r"^(.+?)\s*\(([^()]+)\)$")


def company_names(name: str) -> list[str]:
    """맞춰 볼 이름들, 앞에서부터 먼저: 괄호 앞 이름, 괄호 안 이름, 전체."""
    cleaned = clean_company(name)
    m = _ALT.match(cleaned)
    return [m.group(1).strip(), m.group(2).strip(), cleaned] if m else [cleaned]


def pick_company(name: str, known: set[str]) -> str:
    """이미 아는 회사(다른 수집처에서 본 회사 키)와 맞는 이름을 고른다. 처음 보는 회사면 괄호 앞 이름,
    괄호 안 이름이 그 이름의 보통 부르는 이름이면(씨제이올리브영 → CJ올리브영) 그쪽."""
    names = company_names(name)
    for n in names:
        if company_key(n) in known:
            return n
    if len(names) > 1 and common_name(names[0]) == names[1]:
        return names[1]
    return names[0]


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_item(item: dict[str, Any], tag_names: dict[int, str]) -> Posting:
    company = item.get("company") or {}
    lo, hi = item.get("annual_from"), item.get("annual_to")
    due = _date(item.get("due_time"))
    region = (item.get("address") or {}).get("location")
    tags = [t.get("id") for t in item.get("category_tags") or []]
    return Posting(
        source=Source.WANTED,
        source_id=str(item["id"]),
        url=f"https://www.wanted.co.kr/wd/{item['id']}",
        company=company.get("name") or "",
        title=item.get("position") or "",
        career_min=lo or None,
        career_max=None if hi is None or hi >= NO_MAX else hi,
        newcomer=not lo,
        # 마감일이 없으면 원티드는 "상시채용"으로 보여준다
        deadline_type=DeadlineType.DATE if due else DeadlineType.ALWAYS,
        deadline=due,
        regions=[region] if region else [],
        categories=list(dict.fromkeys(tag_names.get(t, str(t)) for t in tags if t is not None)),
        raw=item,
    )


def parse_detail(job: dict[str, Any], source_id: str, fetched_at: datetime) -> Detail:
    detail = job.get("detail") or {}
    text = "\n\n".join(f"[{name}]\n{detail[key].strip()}" for name, key in SECTIONS
                       if isinstance(detail.get(key), str) and detail[key].strip())
    return Detail(
        uid=f"{Source.WANTED.value}:{source_id}",
        fetched_at=fetched_at,
        description=text or None,
        # 회사 태그(인원 규모, 설립 연수, 업종)와 스킬 태그는 회사 구분·분석에 쓸 수 있어 남긴다
        raw={"company_tags": job.get("company_tags"), "skill_tags": job.get("skill_tags"),
             "company_id": (job.get("company") or {}).get("id")},
    )


class WantedCollector:
    def __init__(self, client: Client, cfg: dict[str, Any]):
        self.client = client
        self.cfg = cfg
        self.tags: dict[int, str] = {int(k): v for k, v in (cfg.get("tags") or {}).items()}

    def _tag(self, tag: int, max_pages: int) -> list[dict[str, Any]]:
        per = self.cfg.get("per", 100)
        items: list[dict[str, Any]] = []
        for page in range(max_pages):
            params = {"country": "kr", "tag_type_ids": tag, "job_sort": "job.latest_order",
                      "locations": "all", "years": -1, "limit": per, "offset": page * per}
            data = self.client.get(LIST_URL, params=params, headers=HEADERS).json()
            batch = data.get("data")
            if not isinstance(batch, list):
                raise RuntimeError("응답에 data가 없음")
            items += batch
            if not batch or not (data.get("links") or {}).get("next"):
                return items
        raise RuntimeError(f"최대 {max_pages}페이지에서 멈춤")

    def collect(self, max_pages: int | None = None) -> CollectResult:
        result = CollectResult(source=Source.WANTED.value)
        start = self.client.requests
        found: dict[str, dict[str, Any]] = {}
        limit = self.cfg.get("max_pages_per_tag", 30)
        if max_pages is not None:
            limit = min(limit, max_pages)
        for tag, name in self.tags.items():
            t0 = time.monotonic()
            try:
                items = self._tag(tag, limit)
            except Exception as e:
                result.complete = False
                result.errors.append(f"{name}: {e}")
                log.warning("원티드 %s 실패: %s", name, e)
                continue
            for x in items:
                found[str(x["id"])] = x
            log.info("원티드 %s: %d건 (%.0f초)", name, len(items), time.monotonic() - t0)
        for item in found.values():
            try:
                result.postings.append(parse_item(item, self.tags))
            except Exception as e:
                result.errors.append(f"파싱 {item.get('id')}: {e}")
        result.requests = self.client.requests - start
        return result

    def resolve_companies(self, postings: list[Posting], known: set[str]) -> None:
        """회사 이름을 다른 수집처와 같은 이름으로 맞춘다(원래 이름은 raw에 남아 있다)."""
        for p in postings:
            p.company = pick_company(p.company, known)

    def fetch_details(self, source_ids: list[str]) -> tuple[list[Detail], list[str]]:
        details: list[Detail] = []
        errors: list[str] = []
        for n, sid in enumerate(source_ids, 1):
            try:
                data = self.client.get(DETAIL_URL.format(sid), headers=HEADERS).json()
                details.append(parse_detail(data.get("job") or {}, sid, datetime.now()))
            except TimeBudgetExceeded:
                errors.append(f"시간 한도 초과: {n - 1}/{len(source_ids)}건에서 멈춤")
                break
            except Exception as e:
                errors.append(f"상세 {sid}: {e}")
            if n % 100 == 0:
                log.info("원티드 상세 %d/%d건", n, len(source_ids))
        return details, errors
