"""직행(zighang.com) 수집기. 사이트가 쓰는 내부 API를 호출한다.

확인된 사실(2026.10):
- 목록: GET /api/recruitments/v4 (page는 0부터, size는 최대 100)
- keyword 검색은 본문까지 찾지만 결과가 제목 일치 순이다
- careerMax 100은 상한 없음, endDate 9999-12-31은 사실상 상시
- sort, startDate, endDate를 넣으면 data가 null로 온다
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Any

from ..http import Client, TimeBudgetExceeded
from ..models import DeadlineType, Detail, Posting, Source
from ..normalize import company_key
from . import CollectResult

log = logging.getLogger(__name__)

API = "https://api.zighang.com/api"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://zighang.com",
    "Referer": "https://zighang.com/recruitment",
}
PAGE_SIZE = 100
NO_UPPER = 50  # 이 값 이상이면 상한 없음으로 본다(직행은 100을 쓴다)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value[:19]).date()
    except ValueError:
        return None
    return None if d.year >= 9000 else d


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:26])
    except ValueError:
        return None


def parse_item(item: dict[str, Any]) -> Posting:
    cmin, cmax = item.get("careerMin"), item.get("careerMax")
    end = _date(item.get("endDate"))
    dtype = item.get("deadlineType")
    if dtype == "마감일" and end:
        deadline_type = DeadlineType.DATE
    elif dtype == "상시채용" or (dtype == "마감일" and not end):
        deadline_type = DeadlineType.ALWAYS
    else:
        deadline_type = DeadlineType.UNTIL_FILLED
    depth_ones = item.get("depthOnes") or []
    depth_twos = item.get("depthTwos") or []
    categories = list(dict.fromkeys(list(depth_ones) + list(depth_twos)))  # 소분류가 어느 대분류 것인지는 알 수 없다
    affiliate = item.get("affiliate")
    return Posting(
        source=Source.ZIGHANG,
        source_id=item["id"],
        url=f"https://zighang.com/recruitment/{item['id']}",
        via=None if affiliate in (None, "직행") else affiliate,
        company=(item.get("company") or {}).get("name") or "",
        title=item.get("title") or "",
        career_min=cmin if cmin else None,
        career_max=None if cmax is None or cmax >= NO_UPPER else cmax,
        newcomer=cmin == 0,
        deadline_type=deadline_type,
        deadline=end if deadline_type is DeadlineType.DATE else None,
        regions=item.get("regions") or [],
        employment_types=item.get("employeeTypes") or [],
        categories=categories,
        keywords=item.get("keywords") or [],
        posted_at=_datetime(item.get("createdAt")),
        raw=item,
    )


def doc_text(node: Any) -> str:
    """직행 본문(ProseMirror JSON)을 줄 단위 글로 바꾼다."""
    lines: list[str] = []

    def walk(n: Any, buf: list[str]) -> None:
        if isinstance(n, dict):
            if n.get("type") == "text":
                buf.append(n.get("text", ""))
                return
            children = n.get("content") or []
            if n.get("type") in ("paragraph", "heading", "listItem", "codeBlock"):
                inner: list[str] = []
                for c in children:
                    walk(c, inner)
                text = "".join(inner).strip()
                if text:
                    prefix = "- " if n.get("type") == "listItem" else ""
                    lines.append(prefix + text)
                return
            for c in children:
                walk(c, buf)
        elif isinstance(n, list):
            for c in n:
                walk(c, buf)

    walk(node, [])
    # 목록 안 문단이 두 번 들어가지 않게 연속 중복을 지운다
    out: list[str] = []
    for line in lines:
        if not out or out[-1].lstrip("- ") != line.lstrip("- "):
            out.append(line)
    return "\n".join(out)


def parse_detail(data: dict[str, Any], fetched_at: datetime) -> Detail:
    parts = [doc_text(data.get("summary")), doc_text(data.get("content"))]
    text = "\n\n".join(p for p in parts if p)
    related = [
        o["recruitmentId"]
        for o in (data.get("dedup") or {}).get("applyOptions") or []
        if o.get("recruitmentId") and o.get("recruitmentId") != data.get("id")
    ]
    return Detail(
        uid=f"{Source.ZIGHANG.value}:{data['id']}",
        fetched_at=fetched_at,
        description=text or None,
        apply_url=data.get("redirectUrl"),
        related_ids=[f"{Source.ZIGHANG.value}:{r}" for r in related],
        raw={k: data.get(k) for k in ("summary", "content", "redirectUrl", "dedup", "status")},
    )


def _title_matcher(keyword: str) -> re.Pattern:
    if re.fullmatch(r"[A-Za-z]{1,4}", keyword):
        return re.compile(rf"(?<![A-Za-z]){re.escape(keyword)}(?![A-Za-z])")
    return re.compile(re.escape(keyword.replace(" ", "")), re.IGNORECASE)


class ZighangCollector:
    def __init__(self, client: Client, cfg: dict[str, Any]):
        self.client = client
        self.cfg = cfg

    def _page(self, page: int, **params: Any) -> dict[str, Any]:
        resp = self.client.get(
            f"{API}/recruitments/v4",
            params={"page": page, "size": PAGE_SIZE, **params},
            headers=HEADERS,
        )
        data = resp.json().get("data")
        if data is None:
            raise RuntimeError(f"직행 응답에 data가 없음: {params}")
        return data

    def _all_pages(self, max_pages: int | None, **params: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 0
        while True:
            data = self._page(page, **params)
            items += data.get("content") or []
            page += 1
            if data.get("last") or page >= data.get("totalPages", 0):
                break
            if max_pages is not None and page >= max_pages:
                break
        return items

    def _title_pages(self, keyword: str, max_pages: int, **params: Any) -> list[dict[str, Any]]:
        """제목에 키워드가 있는 공고만. 제목 일치가 없는 페이지가 나오면 멈춘다."""
        matcher = _title_matcher(keyword)
        hits: list[dict[str, Any]] = []
        for page in range(max_pages):
            data = self._page(page, keyword=keyword, **params)
            content = data.get("content") or []
            matched = [x for x in content if matcher.search((x.get("title") or "").replace(" ", ""))
                       or matcher.search(x.get("title") or "")]
            hits += matched
            if not matched or data.get("last"):
                break
        return hits

    def collect(self, max_pages: int | None = None) -> CollectResult:
        result = CollectResult(source=Source.ZIGHANG.value)
        start = self.client.requests
        found: dict[str, dict[str, Any]] = {}
        kw_pages = self.cfg.get("max_keyword_pages", 30)
        if max_pages is not None:
            kw_pages = min(kw_pages, max_pages)

        typed_kw_pages = self.cfg.get("max_typed_keyword_pages", 3)
        if max_pages is not None:
            typed_kw_pages = min(typed_kw_pages, max_pages)

        def run(label: str, fn, *args, **kwargs) -> list[dict[str, Any]]:
            t0 = time.monotonic()
            try:
                items = fn(*args, **kwargs)
            except TimeBudgetExceeded as e:
                result.complete = False
                if not any("시간 한도" in x for x in result.errors):
                    result.errors.append(f"{label}: {e}")
                    log.warning("직행 시간 한도 초과: %s부터 건너뜀", label)
                return []
            except Exception as e:  # 한 조회가 실패해도 나머지는 계속 받는다
                result.complete = False
                result.errors.append(f"{label}: {e}")
                log.warning("직행 %s 실패: %s", label, e)
                return []
            log.info("직행 %s: %d건 (%.0f초)", label, len(items), time.monotonic() - t0)
            return items

        for cat in self.cfg.get("categories", []):
            for x in run(f"분류 {cat}", self._all_pages, max_pages, depthOnes=cat):
                found[x["id"]] = x
        for kw in self.cfg.get("title_keywords", []):
            for x in run(f"키워드 {kw}", self._title_pages, kw, kw_pages):
                found.setdefault(x["id"], x)

        # 기업 구분 표시: 구분 필터를 건 조회에 나온 회사에 그 구분을 붙인다
        for ctype in self.cfg.get("company_types", []):
            typed: list[dict[str, Any]] = []
            for cat in self.cfg.get("categories", []):
                typed += run(f"{ctype} {cat}", self._all_pages, max_pages,
                             depthOnes=cat, companyTypes=ctype)
            for kw in self.cfg.get("title_keywords", []):
                typed += run(f"{ctype} {kw}", self._title_pages, kw, typed_kw_pages,
                             companyTypes=ctype)
            for x in typed:
                found.setdefault(x["id"], x)
                name = (x.get("company") or {}).get("name") or ""
                result.company_types.setdefault(company_key(name), set()).add(ctype)

        for item in found.values():
            try:
                p = parse_item(item)
            except Exception as e:
                result.errors.append(f"파싱 {item.get('id')}: {e}")
                continue
            types = result.company_types.get(company_key(p.company))
            if types:
                p.source_company_types = sorted(types)
            result.postings.append(p)
        result.requests = self.client.requests - start
        return result

    def fetch_details(self, source_ids: list[str]) -> tuple[list[Detail], list[str]]:
        details: list[Detail] = []
        errors: list[str] = []
        for n, sid in enumerate(source_ids, 1):
            try:
                resp = self.client.get(f"{API}/recruitments/{sid}", headers=HEADERS)
                data = resp.json().get("data")
                if not data:
                    errors.append(f"상세 {sid}: 빈 응답")
                    continue
                details.append(parse_detail(data, datetime.now()))
            except TimeBudgetExceeded:
                errors.append(f"시간 한도 초과: {n - 1}/{len(source_ids)}건에서 멈춤")
                break
            except Exception as e:
                errors.append(f"상세 {sid}: {e}")
            if n % 200 == 0:
                log.info("직행 상세 %d/%d건", n, len(source_ids))
        return details, errors
