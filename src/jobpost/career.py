"""커리어 지표(시장): 화면용 파일의 career 묶음. 계산법은 고정하고 버전으로 관리한다(docs/content-rules.md "커리어 지표").

v2(2026-10-22), 국내·잡음 아닌 공고, 같은 공고 묶음은 하나(처음 본 날은 묶음에서 가장 이른 날) 기준. 직무 유형 × 기업 구분마다 나눠 두고 화면이 내 필터에 맞게 더한다.
- 날짜별 열린 공고 수: 처음 본 날 ≤ 그날 < 내려간 날(state.jsonl). 지난 공고는 소급할 수 없어 수집을 시작한 날부터
- 날짜별 새 공고 수: 그날 처음 본 공고. 수집 첫날은 그동안 열려 있던 공고가 한꺼번에 들어와 세지 않는다(null).
  새로 붙인 수집처가 첫날 가져온 공고(backfill)도 원래 열려 있던 공고라 새 공고로 세지 않는다(열린 공고에는 센다)
- 지금 열린 공고의 연차 분포: 최소 경력 기준 0~3년 미만(신입·N년 이하 포함), 3~7, 7~12, 12년 이상, 연차 무관
- 지금 열린 공고가 요구하는 스킬: 본문에서 스킬 사전(config/skills.yaml)으로 찾은 스킬별 공고 수(전부, 많은 순)
연봉은 공고에 거의 적혀 있지 않아(2026-10-21 공고 정리 340건 중 금액이 적힌 것 5건 남짓) 넣지 않는다.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from . import matching
from .companies import CompanyRegistry

VERSION = 3  # 2: 신입·N년 이하를 3년 미만으로, 같은 공고 묶음의 날짜, 스킬 사전 이름(dictionary), 3: 새로 붙인 수집처의 첫날 공고(backfill)는 새 공고로 세지 않음
CAREER_BUCKETS = [("0-3", 0, 3), ("3-7", 3, 7), ("7-12", 7, 12), ("12+", 12, 99)]


def bucket(career_min: int | None, career_max: int | None = None) -> str:
    """최소 경력 구간. 수집처는 최소 0을 비워 두므로 "신입"(최대 0)·"N년 이하"(최대만)는 3년 미만, 둘 다 없으면 연차 무관."""
    if not career_min:
        return "any" if career_max is None else "0-3"
    return next((name for name, lo, hi in CAREER_BUCKETS if lo <= career_min < hi), "12+")


def build(state: dict[str, dict[str, Any]], registry: CompanyRegistry, postings: list[dict[str, Any]],
          companies: dict[str, dict[str, Any]], bodies: dict[str, dict[str, str]], today: date) -> dict[str, Any]:
    """state: state.jsonl의 공고별 상태, postings·companies·bodies: 화면용 파일에 들어가는 오늘 열린 공고."""
    return {"version": VERSION, **daily(state, registry, today), "current": current(postings, companies, bodies),
            # 스킬 사전에 있는 이름(프로필 스킬이 사전에 없으면 공고에서 셀 수 없어 화면이 "사전에 없음"으로 보여준다)
            "dictionary": sorted({name for name, _ in matching._skill_patterns()})}


def _key(job: str | None, ctype: str) -> str:
    return f"{job or 'none'}|{ctype}"


def daily(state: dict[str, dict[str, Any]], registry: CompanyRegistry, today: date) -> dict[str, Any]:
    """날짜별 열린 공고·새 공고 수(직무 유형 × 기업 구분마다): {since, days, series}."""
    recs = [r for r in state.values()
            if not r.get("overseas") and not r.get("dup_of") and not r.get("noise") and r.get("first_seen")]
    # 같은 공고 묶음(dup_of)은 하나로 센다. 처음 본 날은 묶음에서 가장 이른 날, 아직 열린 수집처가 있으면 열린 공고
    # (화면용 파일의 firstSeen과 같은 기준)
    members: dict[str, list[dict[str, Any]]] = {}
    for r in state.values():
        if r.get("dup_of"):
            members.setdefault(r["dup_of"], []).append(r)

    def span(r: dict[str, Any]) -> tuple[str, str | None, bool]:
        group = [r, *members.get(r["uid"], [])] if "uid" in r else [r]
        first = min(x["first_seen"] for x in group if x.get("first_seen"))
        closed = None if any(not x.get("closed_on") for x in group) else max(x["closed_on"] for x in group)
        backfill = all(x.get("backfill") for x in group if x.get("first_seen") == first)
        return first, closed, backfill

    spans = {id(r): span(r) for r in recs}
    start = min((spans[id(r)][0] for r in recs), default=today.isoformat())
    days = []
    d = date.fromisoformat(start)
    while d <= today:
        days.append(d.isoformat())
        d += timedelta(days=1)
    index = {day: i for i, day in enumerate(days)}
    series: dict[str, dict[str, list[int | None]]] = {}
    for r in recs:
        ckey = r.get("company_key") or r.get("company", "")
        k = _key((r.get("job_type") or {}).get("id"), registry.company_type(ckey, r.get("company", "")).value)
        s = series.setdefault(k, {"open": [0] * len(days), "new": [0] * len(days)})
        first_seen, closed_on, backfill = spans[id(r)]
        first = index.get(first_seen)
        if first is None:
            continue
        end = index.get(closed_on, len(days)) if closed_on else len(days)
        for i in range(first, min(end, len(days))):
            s["open"][i] += 1  # type: ignore[operator]
        if not backfill:
            s["new"][first] += 1  # type: ignore[operator]
    for s in series.values():
        s["new"][0] = None  # 수집 첫날은 새 공고로 세지 않는다
    return {"since": start, "days": days, "series": series}


def current(postings: list[dict[str, Any]], companies: dict[str, dict[str, Any]],
            bodies: dict[str, dict[str, str]]) -> dict[str, Any]:
    """지금 열린 공고의 연차 구간과 요구 스킬(직무 유형 × 기업 구분마다)."""
    groups: dict[str, dict[str, Any]] = {}
    for p in postings:
        if p.get("noise"):
            continue
        k = _key(p.get("jobType"), (companies.get(p["company"]) or {}).get("type", "그 외"))
        g = groups.setdefault(k, {"career": Counter(), "skills": Counter(), "withBody": 0})
        g["career"][bucket(p.get("careerMin"), p.get("careerMax"))] += 1
        body = (bodies.get(p["id"]) or {}).get("text")
        if body:
            g["withBody"] += 1
            for skill in matching.extract_skills(body):
                g["skills"][skill] += 1
    return {k: {"career": dict(g["career"]), "skills": g["skills"].most_common(), "withBody": g["withBody"]}
            for k, g in groups.items()}

