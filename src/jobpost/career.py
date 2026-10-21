"""커리어 지표(시장): 화면용 파일의 career 묶음. 계산법은 고정하고 버전으로 관리한다(docs/content-rules.md "커리어 지표").

v1(2026-10-21), 국내·중복 대표·잡음 아닌 공고 기준. 직무 유형 × 기업 구분마다 나눠 두고 화면이 내 필터에 맞게 더한다.
- 날짜별 열린 공고 수: 처음 본 날 ≤ 그날 < 내려간 날(state.jsonl). 지난 공고는 소급할 수 없어 수집을 시작한 날부터
- 날짜별 새 공고 수: 그날 처음 본 공고. 수집 첫날은 그동안 열려 있던 공고가 한꺼번에 들어와 세지 않는다(null)
- 지금 열린 공고의 연차 분포: 최소 경력 기준 0~3년 미만, 3~7, 7~12, 12년 이상, 연차 무관
- 지금 열린 공고가 요구하는 스킬: 본문에서 스킬 사전(config/skills.yaml)으로 찾은 스킬별 공고 수(전부, 많은 순)
연봉은 공고에 거의 적혀 있지 않아(2026-10-21 공고 정리 340건 중 금액이 적힌 것 5건 남짓) 넣지 않는다.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from . import matching
from .companies import CompanyRegistry

VERSION = 1
CAREER_BUCKETS = [("0-3", 0, 3), ("3-7", 3, 7), ("7-12", 7, 12), ("12+", 12, 99)]


def bucket(career_min: int | None) -> str:
    if career_min is None:
        return "any"
    return next(name for name, lo, hi in CAREER_BUCKETS if lo <= career_min < hi)


def build(state: dict[str, dict[str, Any]], registry: CompanyRegistry, postings: list[dict[str, Any]],
          companies: dict[str, dict[str, Any]], bodies: dict[str, dict[str, str]], today: date) -> dict[str, Any]:
    """state: state.jsonl의 공고별 상태, postings·companies·bodies: 화면용 파일에 들어가는 오늘 열린 공고."""
    recs = [r for r in state.values()
            if not r.get("overseas") and not r.get("dup_of") and not r.get("noise") and r.get("first_seen")]
    start = min((r["first_seen"] for r in recs), default=today.isoformat())
    days = []
    d = date.fromisoformat(start)
    while d <= today:
        days.append(d.isoformat())
        d += timedelta(days=1)
    index = {day: i for i, day in enumerate(days)}

    def key_of(job: str | None, ctype: str) -> str:
        return f"{job or 'none'}|{ctype}"

    series: dict[str, dict[str, list[int | None]]] = {}
    for r in recs:
        ckey = r.get("company_key") or r.get("company", "")
        k = key_of((r.get("job_type") or {}).get("id"), registry.company_type(ckey, r.get("company", "")).value)
        s = series.setdefault(k, {"open": [0] * len(days), "new": [0] * len(days)})
        first = index.get(r["first_seen"])
        if first is None:
            continue
        end = index.get(r["closed_on"], len(days)) if r.get("closed_on") else len(days)
        for i in range(first, min(end, len(days))):
            s["open"][i] += 1  # type: ignore[operator]
        s["new"][first] += 1  # type: ignore[operator]
    for s in series.values():
        s["new"][0] = None  # 수집 첫날은 새 공고로 세지 않는다

    groups: dict[str, dict[str, Any]] = {}
    for p in postings:
        if p.get("noise"):
            continue
        k = key_of(p.get("jobType"), (companies.get(p["company"]) or {}).get("type", "그 외"))
        g = groups.setdefault(k, {"career": Counter(), "skills": Counter(), "withBody": 0})
        g["career"][bucket(p.get("careerMin"))] += 1
        body = (bodies.get(p["id"]) or {}).get("text")
        if body:
            g["withBody"] += 1
            for skill in matching.extract_skills(body):
                g["skills"][skill] += 1
    current = {k: {"career": dict(g["career"]), "skills": g["skills"].most_common(), "withBody": g["withBody"]}
               for k, g in groups.items()}
    return {"version": VERSION, "since": start, "days": days, "series": series, "current": current}
