"""회사 리서치 심층분석. 지금은 이미 가진 데이터로 만드는 두 모듈(비용 없음, 모든 회사):

- 경쟁사: DART 업종 코드가 같은 회사 중 최근 매출이 큰 곳. 이 앱이 DART 기본정보를 받은 회사(공고 회사 + 주요 기업) 안에서
- 직무 환경·도구: 그 회사 공고 본문(열린 공고 + 지난 공고, 헤드헌터 공고 제외)에서 찾은 도구. 도구 이름과 찾을 말은
  config/research.yaml(스킬 사전과 따로, 공고에 적힌 제품 이름 그대로)

설정은 config/research.yaml, 기준과 이유는 docs/content-rules.md "회사 리서치 모듈".
AI 웹 조사 모듈(사업 구조, 직무 분야 전략 등)은 아직 없다.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

from . import config
from .normalize import clean_company


def _latest(b: dict[str, Any]) -> dict[str, Any] | None:
    """사업보고서 주요 계정의 가장 최근 해(매출이 있는 경우만). 연결·별도, 계정 이름(매출액·영업수익), 접수번호를 함께."""
    fin = b.get("finance") or {}
    years = fin.get("years") or []
    last = years[-1] if years else None
    if not last or not last.get("revenue"):
        return None
    return {"year": last.get("year"), "revenue": last["revenue"], "operating": last.get("operating"),
            "basis": fin.get("basis"), "revenueName": fin.get("revenue_name") or "매출액", "rceptNo": fin.get("rcept_no")}


class Peers:
    """매출이 있는 회사를 업종 코드와 함께 모아 둔다(회사마다 다시 훑지 않게)."""

    def __init__(self, basics: dict[str, dict[str, Any]]):
        self.basics = basics
        self.rows: list[tuple[str, str, dict[str, Any]]] = []
        for code, b in basics.items():
            ind = (b.get("company") or {}).get("industry_code")
            last = _latest(b)
            if ind and last:
                self.rows.append((code, ind, last))
        self.rows.sort(key=lambda r: (-r[2]["revenue"], r[0]))

    def competitors(self, code: str, names: dict[str, str], keys: dict[str, str], n: int | None = None,
                    self_name: str | None = None) -> dict[str, Any] | None:
        """이 회사와 같은 업종에서 매출이 큰 n곳(자기 회사는 맨 앞 비교 줄). 업종 코드가 없으면 None.
        업종 코드는 한쪽이 다른 쪽으로 시작하면 같은 업종으로 본다(KT 612 = SK텔레콤 61220). 짧은 쪽이 min_code자리 이상일 때만.
        names: DART 고유번호 → 화면 이름, keys: 고유번호 → 화면 회사 키(회사 화면으로 잇는다), self_name: 이 화면의 회사 이름."""
        cfg = config.load("research")
        n = n if n is not None else cfg.get("competitors", 2)
        shortest = cfg.get("min_code", 3)
        b = self.basics.get(code) or {}
        ind = (b.get("company") or {}).get("industry_code")
        if not ind:
            return None

        def same(other: str) -> bool:
            short, long_ = sorted((ind, other), key=len)
            return len(short) >= shortest and long_.startswith(short) or other == ind

        others = [(c, last) for c, other, last in self.rows if c != code and same(other)][:n]

        def row(c: str, last: dict[str, Any] | None, me: bool) -> dict[str, Any]:
            legal = ((self.basics.get(c) or {}).get("company") or {}).get("name") or ""
            rev = last["revenue"] if last else None
            op = last["operating"] if last else None
            name = (self_name if me else None) or names.get(c) or clean_company(legal) or c
            return {"name": name, "key": None if me else keys.get(c), "self": me,
                    "year": last["year"] if last else None, "basis": last["basis"] if last else None,
                    "revenueName": last["revenueName"] if last else None, "rceptNo": last["rceptNo"] if last else None,
                    "revenue": rev, "margin": round(op / rev * 100, 1) if rev and op is not None else None}

        return {"industry": ind, "rows": [row(code, _latest(b), True)] + [row(c, last, False) for c, last in others]}


@cache
def _tool_patterns() -> list[tuple[str, str, list[re.Pattern], list[str]]]:
    """(칸, 도구 이름, 찾을 말 패턴, 있으면 세지 않을 말). 영문은 단어 경계, 세 글자 이하는 대소문자까지 맞춘다."""
    cfg = config.load("research")
    unless: dict[str, list[str]] = cfg.get("unless") or {}
    out = []
    for slot, tools in (cfg.get("tools") or {}).items():
        for name, words in tools.items():
            pats = []
            for w in words:
                if re.search(r"[가-힣]", w):
                    pats.append(re.compile(re.escape(w)))
                else:
                    flags = 0 if len(w) <= 3 else re.IGNORECASE
                    pats.append(re.compile(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])", flags))
            out.append((slot, name, pats, unless.get(name) or []))
    return out


def tools(texts: list[str]) -> dict[str, Any] | None:
    """공고 본문들에서 칸(클라우드, 데이터 플랫폼, BI, AI 도구)마다 도구별 공고 수. 찾은 도구가 하나도 없으면 None."""
    if not texts:
        return None
    patterns = _tool_patterns()
    counts: dict[str, int] = {}
    for text in texts:
        for _, name, pats, unless in patterns:
            if any(p.search(text) for p in pats) and not any(u in text for u in unless):
                counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    top = config.load("research").get("max_per_slot", 6)
    order = {name: i for i, (_, name, _, _) in enumerate(patterns)}
    slots: dict[str, list[str]] = {}
    for slot, name, _, _ in patterns:
        slots.setdefault(slot, []).append(name)
    out = []
    for slot, names in slots.items():
        items = sorted(((s, counts[s]) for s in names if counts.get(s)), key=lambda x: (-x[1], order[x[0]]))
        out.append({"name": slot, "items": [{"skill": s, "count": c} for s, c in items[:top]]})
    return {"postings": len(texts), "slots": out}
