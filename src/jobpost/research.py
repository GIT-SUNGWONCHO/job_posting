"""회사 리서치 심층분석. 지금은 이미 가진 데이터로 만드는 두 모듈(비용 없음, 모든 회사):

- 경쟁사: DART 업종 코드가 같은 회사 중 최근 매출이 큰 곳. 이 앱이 DART 기본정보를 받은 회사(공고 회사 + 주요 기업) 안에서
- 직무 환경·도구: 그 회사 공고 본문(열린 공고 + 지난 공고)에서 찾은 도구. 도구 이름은 스킬 사전(config/skills.yaml)

설정은 config/research.yaml, 기준과 이유는 docs/content-rules.md "회사 리서치 모듈".
AI 웹 조사 모듈(사업 구조, 직무 분야 전략 등)은 아직 없다.
"""

from __future__ import annotations

from typing import Any

from . import config, matching
from .normalize import clean_company


def _latest(b: dict[str, Any]) -> dict[str, Any] | None:
    """사업보고서 주요 계정의 가장 최근 해(매출이 있는 경우만)."""
    fin = b.get("finance") or {}
    years = fin.get("years") or []
    last = years[-1] if years else None
    if not last or not last.get("revenue"):
        return None
    return {"year": last.get("year"), "revenue": last["revenue"], "operating": last.get("operating"),
            "basis": fin.get("basis")}


class Peers:
    """업종 코드별로 매출이 있는 회사를 모아 둔다(회사마다 다시 훑지 않게)."""

    def __init__(self, basics: dict[str, dict[str, Any]]):
        self.basics = basics
        self.by_industry: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for code, b in basics.items():
            ind = (b.get("company") or {}).get("industry_code")
            last = _latest(b)
            if ind and last:
                self.by_industry.setdefault(ind, []).append((code, last))
        for rows in self.by_industry.values():
            rows.sort(key=lambda r: -r[1]["revenue"])

    def competitors(self, code: str, names: dict[str, str], keys: dict[str, str], n: int | None = None) -> dict[str, Any] | None:
        """이 회사와 같은 업종에서 매출이 큰 n곳(자기 회사는 맨 앞 비교 줄). 업종 코드가 없으면 None.
        names: DART 고유번호 → 화면 이름, keys: 고유번호 → 화면 회사 키(회사 화면으로 잇는다)."""
        n = n if n is not None else config.load("research").get("competitors", 2)
        b = self.basics.get(code) or {}
        ind = (b.get("company") or {}).get("industry_code")
        if not ind:
            return None
        others = [(c, last) for c, last in self.by_industry.get(ind, []) if c != code][:n]
        me = _latest(b)

        def row(c: str, last: dict[str, Any] | None, me_: bool) -> dict[str, Any]:
            legal = ((self.basics.get(c) or {}).get("company") or {}).get("name") or ""
            rev = last["revenue"] if last else None
            op = last["operating"] if last else None
            return {"name": names.get(c) or clean_company(legal) or c, "key": keys.get(c), "self": me_,
                    "year": last["year"] if last else None, "revenue": rev,
                    "margin": round(op / rev * 100, 1) if rev and op is not None else None}

        return {"industry": ind, "rows": [row(code, me, True)] + [row(c, last, False) for c, last in others]}


def tools(texts: list[str]) -> dict[str, Any] | None:
    """공고 본문들에서 칸(클라우드, 데이터 플랫폼, BI, AI 도구)마다 도구별 공고 수. 본문이 하나도 없으면 None."""
    if not texts:
        return None
    cfg = config.load("research")
    slots: dict[str, list[str]] = cfg.get("tools") or {}
    wanted = {name for names in slots.values() for name in names}
    patterns = [(name, pat) for name, pat in matching._skill_patterns() if name in wanted]
    counts: dict[str, int] = {}
    for text in texts:
        found = {name for name, pat in patterns if pat.search(text)}
        for name in found:
            counts[name] = counts.get(name, 0) + 1
    top = cfg.get("max_per_slot", 6)
    out = []
    for slot, names in slots.items():
        items = sorted(((s, counts[s]) for s in names if counts.get(s)), key=lambda x: (-x[1], names.index(x[0])))
        out.append({"name": slot, "items": [{"skill": s, "count": c} for s, c in items[:top]]})
    return {"postings": len(texts), "slots": out}
