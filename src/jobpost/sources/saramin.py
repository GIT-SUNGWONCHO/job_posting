"""사람인(saramin.co.kr) 수집기. 직무 분류 목록 페이지(HTML)를 읽는다.

확인된 페이지 구조(주소, 필터, 경력 표기)는 docs/collection.md "수집처에서 확인된 사실"에 있다.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from ..http import Client, TimeBudgetExceeded
from ..models import DeadlineType, Detail, Posting, Source
from ..normalize import company_key
from . import CollectResult

log = logging.getLogger(__name__)

LIST_URL = "https://www.saramin.co.kr/zf_user/jobs/list/job-category"
VIEW_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx={}"
# 공고 페이지 안에 iframe으로 들어가는 본문. 글로 된 공고가 많고, 이미지 한 장인 공고도 있다(2026.10.13 확인)
DETAIL_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={}&rec_seq=0"
PAGE_COUNT = 100
EMPLOYMENT = ("정규직", "계약직", "인턴직", "파견직", "프리랜서", "아르바이트", "위촉직", "병역특례")


def parse_career(text: str) -> tuple[int | None, int | None, bool, list[str]]:
    """경력 글 → (최소, 최대, 신입 가능, 고용 형태)."""
    tokens = [t.strip() for t in (text or "").split("·") if t.strip()]
    cmin = cmax = None
    newcomer = False
    experienced = False
    employment: list[str] = []
    for t in tokens:
        base = t.replace(" 외", "").strip()
        if base in EMPLOYMENT:
            employment.append(base)
            continue
        if t == "신입":
            newcomer = True
        elif t in ("경력무관",):
            newcomer = True
        elif t.startswith("경력(년수무관)") or t == "경력":
            experienced = True
        elif m := re.fullmatch(r"경력\s*(\d+)\s*년\s*↑", t):
            cmin = int(m.group(1))
        elif m := re.fullmatch(r"(\d+)\s*~\s*(\d+)\s*년", t):
            cmin, cmax = int(m.group(1)), int(m.group(2))
        elif m := re.fullmatch(r"경력\s*(\d+)\s*~\s*(\d+)\s*년", t):
            cmin, cmax = int(m.group(1)), int(m.group(2))
    if newcomer and not experienced and cmin is None and cmax is None and "신입" in tokens \
            and not any("경력" in t for t in tokens):
        cmax = 0  # 신입만
    return cmin or None, cmax, newcomer, employment


def parse_deadline(text: str, today: date) -> tuple[DeadlineType, date | None]:
    t = (text or "").strip()
    if not t or "채용시" in t:
        return DeadlineType.UNTIL_FILLED, None
    if "상시" in t:
        return DeadlineType.ALWAYS, None
    if "오늘마감" in t:
        return DeadlineType.DATE, today
    if "내일마감" in t:
        return DeadlineType.DATE, today + timedelta(days=1)
    if m := re.search(r"D-(\d+)", t):
        return DeadlineType.DATE, today + timedelta(days=int(m.group(1)))
    if m := re.search(r"(\d{1,2})[./](\d{1,2})", t):
        month, day = int(m.group(1)), int(m.group(2))
        try:
            d = date(today.year, month, day)
        except ValueError:
            return DeadlineType.UNTIL_FILLED, None
        if d < today - timedelta(days=60):  # 연말에 내년 날짜가 보이는 경우
            d = date(today.year + 1, month, day)
        return DeadlineType.DATE, d
    return DeadlineType.UNTIL_FILLED, None


def parse_posted(text: str, now: datetime) -> datetime | None:
    m = re.search(r"(\d+)\s*(분|시간|일)\s*전\s*등록", text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"분": timedelta(minutes=n), "시간": timedelta(hours=n), "일": timedelta(days=n)}[unit]
    return now - delta


def _region(place: str) -> str | None:
    first = (place or "").split(" ")[0]
    first = re.sub(r"전체$", "", first)
    return first or None


def parse_list(html: str, today: date, now: datetime) -> tuple[list[Posting], int]:
    """목록 페이지 → (공고 목록, 페이지 표시에 보이는 가장 큰 페이지 번호)."""
    soup = BeautifulSoup(html, "lxml")
    postings: list[Posting] = []
    for it in soup.select(".list_item"):
        rid = (it.get("id") or "").removeprefix("rec-")
        if not rid.isdigit():
            continue
        company_el = it.select_one(".company_nm .str_tit")
        title_el = it.select_one(".job_tit a.str_tit")
        career_el = it.select_one(".career")
        date_el = it.select_one(".support_detail .date")
        posted_el = it.select_one(".support_detail .deadlines")
        place_el = it.select_one(".work_place")
        sectors = [s.get_text(strip=True) for s in it.select(".job_sector span")]
        career_txt = career_el.get_text(" ", strip=True) if career_el else ""
        date_txt = date_el.get_text(strip=True) if date_el else ""
        place_txt = place_el.get_text(" ", strip=True) if place_el else ""
        posted_txt = posted_el.get_text(strip=True) if posted_el else ""
        cmin, cmax, newcomer, employment = parse_career(career_txt)
        dtype, deadline = parse_deadline(date_txt, today)
        region = _region(place_txt)
        title = (title_el.get("title") or title_el.get_text(strip=True)) if title_el else ""
        postings.append(Posting(
            source=Source.SARAMIN,
            source_id=rid,
            url=VIEW_URL.format(rid),
            company=company_el.get_text(strip=True) if company_el else "",
            title=title,
            career_min=cmin,
            career_max=cmax,
            newcomer=newcomer,
            deadline_type=dtype,
            deadline=deadline,
            regions=[region] if region else [],
            employment_types=employment,
            categories=["saramin"] + [f"saramin/{s}" for s in sectors if s != "외"],
            posted_at=parse_posted(posted_txt, now),
            raw={"career": career_txt, "date": date_txt, "place": place_txt,
                 "sectors": sectors, "posted": posted_txt},
        ))
    pages = [int(a.get("page")) for a in soup.select("[page]") if (a.get("page") or "").isdigit()]
    return postings, max(pages, default=1)


def parse_detail(html: str, rid: str, now: datetime) -> Detail:
    """본문 iframe HTML → 글. 이미지뿐인 공고는 글이 거의 없다."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [" ".join(ln.split()) for ln in soup.get_text("\n").splitlines()]
    lines = [ln for ln in lines if ln]
    if lines and lines[0] == "채용공고 상세":
        lines = lines[1:]
    text = "\n".join(lines)
    return Detail(uid=f"{Source.SARAMIN.value}:{rid}", fetched_at=now, description=text or None,
                  raw={"images": len(soup.find_all("img"))})


class SaraminCollector:
    def __init__(self, client: Client, cfg: dict[str, Any]):
        self.client = client
        self.cfg = cfg

    def _pages(self, max_pages: int, **params: Any) -> tuple[list[Posting], bool]:
        """페이지를 끝까지 넘긴다. 페이지 번호 표시는 앞쪽 몇 개만 보여서 믿지 않고,
        한 페이지가 꽉 차지 않으면 마지막으로 본다."""
        codes = ",".join(str(c) for c in self.cfg.get("categories", {}))
        out: list[Posting] = []
        for page in range(1, max_pages + 1):
            resp = self.client.get(LIST_URL, params={
                "cat_kewd": codes, "page": page, "page_count": PAGE_COUNT, "sort": "RD", **params,
            })
            postings, _ = parse_list(resp.text, date.today(), datetime.now())
            out += postings
            if len(postings) < PAGE_COUNT:
                return out, True
        return out, False

    def collect(self, max_pages: int | None = None) -> CollectResult:
        result = CollectResult(source=Source.SARAMIN.value)
        start = self.client.requests
        limit = min(max_pages or 10**6, self.cfg.get("max_pages", 80))
        found: dict[str, Posting] = {}
        try:
            postings, done = self._pages(limit)
            if not done:
                result.complete = False
                result.errors.append(f"최대 {limit}페이지에서 멈춤")
            for p in postings:
                found[p.source_id] = p
            log.info("사람인 분류 목록: %d건", len(postings))
        except Exception as e:
            result.complete = False
            result.errors.append(f"목록: {e}")
            log.warning("사람인 목록 실패: %s", e)
        for code, label in (self.cfg.get("company_types") or {}).items():
            try:
                typed, _ = self._pages(limit, company_type=code)
            except Exception as e:
                result.errors.append(f"{label}: {e}")
                continue
            log.info("사람인 %s: %d건", label, len(typed))
            for p in typed:
                found.setdefault(p.source_id, p)
                result.company_types.setdefault(company_key(p.company), set()).add(label)
        for p in found.values():
            types = result.company_types.get(company_key(p.company))
            if types:
                p.source_company_types = sorted(types)
            result.postings.append(p)
        result.requests = self.client.requests - start
        return result

    def fetch_details(self, source_ids: list[str]) -> tuple[list[Detail], list[str]]:
        details: list[Detail] = []
        errors: list[str] = []
        for n, rid in enumerate(source_ids, 1):
            try:
                resp = self.client.get(DETAIL_URL.format(rid))
                details.append(parse_detail(resp.text, rid, datetime.now()))
            except TimeBudgetExceeded:
                errors.append(f"시간 한도 초과: {n - 1}/{len(source_ids)}건에서 멈춤")
                break
            except Exception as e:
                errors.append(f"상세 {rid}: {e}")
            if n % 100 == 0:
                log.info("사람인 상세 %d/%d건", n, len(source_ids))
        return details, errors
