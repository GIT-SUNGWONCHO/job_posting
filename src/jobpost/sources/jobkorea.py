"""잡코리아 헤드헌팅 공고 수집기. 데이터·AI 직무의 헤드헌팅 목록을 받고, 본문은 상세 iframe에서 받는다.

헤드헌팅 공고는 회사 이름 대신 서치펌 이름과 "대기업 - 국내 대기업 시중은행" 같은 의뢰 회사 설명이 온다.
회사는 서치펌으로 두고(리멤버 헤드헌터 공고와 같게), 의뢰 회사 구분(client_type)을 공고마다 따로 둔다.
헤드헌터 이름·연락처는 저장하지 않는다(목록에서 읽지 않고, 본문에서는 지운다).

확인된 동작(엔드포인트, 직무 번호, 행 모양)은 docs/collection.md "수집처에서 확인된 사실"에 있다.
"""

from __future__ import annotations

import html
import logging
import re
import time
from datetime import date, datetime
from typing import Any

from ..http import Client, TimeBudgetExceeded
from ..models import CompanyType, DeadlineType, Detail, Posting, Source
from . import CollectResult
from .saramin import parse_career

log = logging.getLogger(__name__)

LIST_URL = "https://www.jobkorea.co.kr/Recruit/Home/_HH_GI_List/"
DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno={}&PageGbn=HH"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.jobkorea.co.kr/recruit/joblist?menucode=duty"}
PAGE_SIZE = 10  # 헤드헌팅 목록은 한 페이지 10건(pagesize를 줘도 같다)

# 의뢰 회사 설명 앞부분 → 기업 구분. 중견·중소·벤처는 "그 외"
CLIENT_LABELS = ("대기업", "중견기업", "중소기업", "외국계", "공기업", "공공기관", "벤처기업", "스타트업")
CLIENT_TYPES = {"대기업": CompanyType.LARGE, "외국계": CompanyType.FOREIGN,
                "공기업": CompanyType.PUBLIC, "공공기관": CompanyType.PUBLIC}
DOMESTIC = {"서울", "경기", "인천", "대전", "세종", "충남", "충북", "광주", "전남", "전북", "대구", "경북",
            "부산", "울산", "경남", "강원", "제주", "전국"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+?82[-\s]?)?0\d{1,2}[-.\s)]*\d{3,4}[-.\s]*\d{4}")
# "채용담당 : 홍길동 전무", "이메일: …" 같은 연락처 줄(콜론이 붙은 것만. 업무 설명의 "고객 문의 분류"는 남긴다)
_CONTACT_LINE = re.compile(r"(채용\s*담당|담당\s*자|문의\s*처?|연락\s*처|이메일|e-?mail|tel|전화)\s*[:：][^\n]*", re.IGNORECASE)


def _clean(x: str | None) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x or ""))).strip()


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def client_label(intro: str) -> str | None:
    """"대기업 - 국내 대기업 시중은행" → "대기업". 정해진 말로 시작하지 않으면 None."""
    head = (intro or "").strip()
    return next((label for label in CLIENT_LABELS if head.startswith(label)), None)


def parse_rows(text: str) -> list[dict[str, Any]]:
    """헤드헌팅 목록 HTML의 행들. 헤드헌터 이름(행 맨 앞)은 읽지 않는다."""
    out = []
    for block in text.split('<tr class="devloopArea"')[1:]:
        gno = re.search(r'data-info="\s*(\d+)\|', block)
        firm = re.search(r'<p class="tplCoName">(.*?)</p>', block, re.S)
        title = re.search(r'<td class="tplTit">.*?<strong><a [^>]*>(.*?)</a></strong>', block, re.S)
        intro = re.search(r'<p class="tplIntroTxt">(.*?)</p>', block, re.S)
        dsc = re.search(r'<p class="dsc">(.*?)</p>', block, re.S)
        braze = re.search(r'data-brazeinfo="([^"]*)"', block)
        info = html.unescape(braze.group(1)).split("|") if braze else []
        if not gno or not title:
            continue
        out.append({
            "id": gno.group(1),
            "firm": _clean(firm.group(1)) if firm else "",
            "title": _clean(title.group(1)),
            "intro": _clean(intro.group(1)) if intro else "",
            "cells": [_clean(c) for c in re.findall(r'<span class="cell">(.*?)</span>', block, re.S)],
            "keywords": [k.strip() for k in _clean(dsc.group(1)).split(",") if k.strip()] if dsc else [],
            "posted": info[3] if len(info) > 4 else None,
            "deadline": info[4] if len(info) > 4 else None,
        })
    return out


def parse_item(row: dict[str, Any], duty: str) -> Posting:
    cells = row.get("cells") or []
    cmin, cmax, newcomer, _ = parse_career(cells[0] if cells else "")
    place = (cells[2].split() or [""])[0] if len(cells) > 2 else ""
    due = _date(row.get("deadline"))
    label = client_label(row.get("intro", ""))
    client = CLIENT_TYPES.get(label or "", CompanyType.OTHER) if label else None
    posted = _date(row.get("posted"))
    return Posting(
        source=Source.JOBKOREA,
        source_id=row["id"],
        url=f"https://www.jobkorea.co.kr/Recruit/GI_Read/{row['id']}",
        company=row.get("firm") or "",
        title=row["title"],
        career_min=cmin,
        career_max=cmax,
        newcomer=newcomer,
        deadline_type=DeadlineType.DATE if due else DeadlineType.UNTIL_FILLED,
        deadline=due,
        regions=[] if not place else [place if place in DOMESTIC else "해외"],
        employment_types=[cells[3].replace(" 외", "")] if len(cells) > 3 and cells[3] else [],
        categories=[duty],
        keywords=row.get("keywords") or [],
        headhunter=True,
        client_type=client.value if client else None,
        posted_at=datetime.combine(posted, datetime.min.time()) if posted else None,
        raw={**row, "client_label": label},
    )


def scrub(text: str) -> str:
    """본문에서 헤드헌터 연락처(이메일, 전화번호, 담당자 줄)를 지운다."""
    text = _CONTACT_LINE.sub("", text)
    text = _EMAIL.sub("", text)
    return _PHONE.sub("", text)


def parse_detail(page: str, source_id: str, fetched_at: datetime) -> Detail:
    """상세 iframe에서 "포지션 및 자격요건"부터 "전형절차" 앞까지(서치펌 소개와 안내문은 뺀다)."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    start = text.find("포지션 및 자격요건")
    end = text.find("전형절차", start + 1 if start >= 0 else 0)
    if start >= 0:
        text = text[start + len("포지션 및 자격요건"):end if end > start else None]
    text = re.sub(r"[ \t]+", " ", scrub(text)).strip()
    return Detail(uid=f"{Source.JOBKOREA.value}:{source_id}", fetched_at=fetched_at, description=text or None)


class JobkoreaCollector:
    def __init__(self, client: Client, cfg: dict[str, Any]):
        self.client = client
        self.cfg = cfg
        self.duties: dict[int, str] = {int(k): v for k, v in (cfg.get("duties") or {}).items()}

    def _duty(self, code: int, name: str, max_pages: int, strict: bool = True) -> list[Posting]:
        found: dict[str, Posting] = {}
        for page in range(1, max_pages + 1):
            data = {"condition[duty]": str(code), "condition[menucode]": "duty", "page": str(page), "tabindex": "2"}
            rows = parse_rows(self.client.post(LIST_URL, data=data, headers=HEADERS).text)
            new = [r for r in rows if r["id"] not in found]
            for r in new:
                found[r["id"]] = parse_item(r, name)
            # 마지막 페이지를 넘기면 마지막 페이지를 다시 준다(새 공고가 없으면 끝)
            if len(rows) < PAGE_SIZE or not new:
                return list(found.values())
        if not strict:  # 시험 실행(--max-pages)은 한도에서 멈추는 게 정상
            return list(found.values())
        raise RuntimeError(f"최대 {max_pages}페이지에서 멈춤")

    def collect(self, max_pages: int | None = None) -> CollectResult:
        result = CollectResult(source=Source.JOBKOREA.value)
        start = self.client.requests
        found: dict[str, Posting] = {}
        limit = self.cfg.get("max_pages_per_duty", 40)
        if max_pages is not None:
            limit = min(limit, max_pages)
        for code, name in self.duties.items():
            t0 = time.monotonic()
            try:
                postings = self._duty(code, name, limit, strict=max_pages is None)
            except Exception as e:
                result.complete = False
                result.errors.append(f"{name}: {e}")
                log.warning("잡코리아 %s 실패: %s", name, e)
                continue
            for p in postings:
                if p.source_id in found:
                    found[p.source_id].categories = sorted({*found[p.source_id].categories, name})
                else:
                    found[p.source_id] = p
            log.info("잡코리아 헤드헌팅 %s: %d건 (%.0f초)", name, len(postings), time.monotonic() - t0)
        result.postings = list(found.values())
        result.requests = self.client.requests - start
        return result

    def fetch_details(self, source_ids: list[str]) -> tuple[list[Detail], list[str]]:
        details: list[Detail] = []
        errors: list[str] = []
        for n, sid in enumerate(source_ids, 1):
            try:
                page = self.client.get(DETAIL_URL.format(sid), headers={"Referer": f"https://www.jobkorea.co.kr/Recruit/GI_Read/{sid}"}).text
                details.append(parse_detail(page, sid, datetime.now()))
            except TimeBudgetExceeded:
                errors.append(f"시간 한도 초과: {n - 1}/{len(source_ids)}건에서 멈춤")
                break
            except Exception as e:
                errors.append(f"상세 {sid}: {e}")
            if n % 100 == 0:
                log.info("잡코리아 상세 %d/%d건", n, len(source_ids))
        return details, errors
