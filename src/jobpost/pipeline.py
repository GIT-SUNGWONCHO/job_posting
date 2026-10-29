"""매일 수집 한 번: 수집 → 범위 고르기 → 저장 → 중복 묶기 → 상세(본문) 받기 → 직무 유형 → 요약."""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config, dedup, filters, jobtypes
from .companies import CompanyRegistry, posting_type
from .http import Client
from .models import CompanyType, Posting, Source
from .normalize import company_key
from .scope import in_scope, is_overseas, noise_reason
from .sources import CollectResult
from .sources.jobkorea import JobkoreaCollector
from .sources.remember import RememberCollector
from .sources.saramin import SaraminCollector
from .sources.wanted import WantedCollector
from .sources.zighang import ZighangCollector
from .store import Store

log = logging.getLogger(__name__)

COLLECTORS = {
    Source.ZIGHANG.value: ZighangCollector,
    Source.REMEMBER.value: RememberCollector,
    Source.SARAMIN.value: SaraminCollector,
    Source.WANTED.value: WantedCollector,
    Source.JOBKOREA.value: JobkoreaCollector,
}


def _collect(name: str, cfg: dict[str, Any], max_pages: int | None) -> tuple[CollectResult, Any]:
    client = Client(min_interval=cfg.get("min_interval", 0.5), max_minutes=cfg.get("max_minutes"),
                    backoff=cfg.get("backoff", 1.0))
    collector = COLLECTORS[name](client, cfg)
    try:
        result = collector.collect(max_pages=max_pages)
    except Exception as e:  # 수집처 하나가 통째로 실패해도 나머지는 저장한다
        result = CollectResult(source=name, complete=False, errors=[f"수집 실패: {e}"])
    if max_pages is not None:
        result.complete = False  # 시험 실행은 마감 판단에 쓰지 않는다
    return result, collector


def check_source(name: str, details: int = 2) -> dict[str, Any]:
    """수집처를 한 페이지씩만 받아 본다(저장 없음). 새 수집처를 켜기 전에 GitHub Actions에서 막히지 않는지 본다."""
    scfg = (config.load("collect").get("sources") or {}).get(name) or {}
    result, collector = _collect(name, scfg, max_pages=1)
    out: dict[str, Any] = {"fetched": len(result.postings), "in_scope": sum(in_scope(p) for p in result.postings),
                           "requests": result.requests, "errors": result.errors[:10],
                           "sample": [f"{p.company} | {p.title}" for p in result.postings[:5]]}
    if details and result.postings and hasattr(collector, "fetch_details"):
        collector.client = Client(min_interval=scfg.get("detail_min_interval", scfg.get("min_interval", 0.5)))
        got, errors = collector.fetch_details([p.source_id for p in result.postings[:details]])
        out["details"] = {"fetched": len(got), "chars": [len(d.description or "") for d in got], "errors": errors[:5]}
    out["ok"] = bool(result.postings) and not result.errors
    return out


def run(data_dir: Path, sources: list[str] | None = None, max_pages: int | None = None,
        detail_budget: int | None = None, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    started = datetime.now()
    cfg = config.load("collect")
    store = Store(data_dir)
    registry = CompanyRegistry(data_dir / "companies.json")
    summary: dict[str, Any] = {"date": today.isoformat(), "started": started.isoformat(timespec="seconds"),
                               "sources": {}}

    collected: list[Posting] = []
    complete: set[str] = set()
    collectors: dict[str, Any] = {}
    for name in sources or list(COLLECTORS):
        scfg = (cfg.get("sources") or {}).get(name) or {}
        if sources is None and not scfg.get("enabled", True):
            continue  # 꺼 둔 수집처는 --sources로 이름을 줄 때만 받는다(영향 미리 보기)
        t0 = time.monotonic()
        log.info("%s 수집 시작", name)
        result, collector = _collect(name, scfg, max_pages)
        collectors[name] = collector
        if hasattr(collector, "resolve_companies"):  # 회사 이름 표기가 다른 수집처(원티드)
            collector.resolve_companies(result.postings,
                                        {r.get("company_key") for r in store.state.values()} | set(registry.data))
        names = {company_key(p.company): p.company for p in result.postings}
        registry.update(result.company_types, names, today.isoformat())
        kept = [p for p in result.postings if in_scope(p)]
        collected += kept
        if result.complete:
            complete.add(name)
        summary["sources"][name] = {
            "fetched": len(result.postings),
            "in_scope": len(kept),
            "complete": result.complete,
            "requests": result.requests,
            "seconds": round(time.monotonic() - t0, 1),
            "errors": result.errors[:20],
            "error_count": len(result.errors),
        }

    extra = {
        p.uid: {
            "company_key": company_key(p.company),
            "noise": noise_reason(p),
            "overseas": is_overseas(p),
            "headhunter": p.headhunter,
            "client_type": p.client_type,
            "via": p.via,
        }
        for p in collected
    }
    new_uids, closed_uids = store.ingest(today, collected, complete, extra)
    new_by_source = Counter(u.split(":")[0] for u in new_uids)
    closed_by_source = Counter(u.split(":")[0] for u in closed_uids)
    for name, s in summary["sources"].items():
        s["new"] = new_by_source.get(name, 0)
        s["closed"] = closed_by_source.get(name, 0)

    # 중복 묶기(지금 열려 있는 국내 공고끼리). 요약 숫자도 국내 공고 기준이다
    all_open = store.open_records()
    open_recs = [r for r in all_open if not r.get("overseas")]
    items = [dedup.Item(uid=r["uid"], source=r["source"], company=r.get("company", ""),
                        title=r.get("title", ""), via=r.get("via"),
                        deadline=date.fromisoformat(r["deadline"]) if r.get("deadline") else None)
             for r in open_recs]
    rep_of = dedup.cluster(items)
    for r in store.state.values():
        rep = rep_of.get(r["uid"])
        r["dup_of"] = rep if rep and rep != r["uid"] else None

    # 상세(본문): 직행·사람인·원티드·잡코리아. 리멤버는 목록에 본문이 같이 온다.
    # 묶인 공고는 대표만 받는다(대표 순서가 리멤버 > 직행 > 사람인 > 원티드 > 잡코리아라 본문이 있는 쪽이 대표다).
    # 대기업·공공·외국계부터, 새로 본 공고부터 하루 한도만큼
    summary["details"] = {}
    for name in ("zighang", "saramin", "wanted", "jobkorea"):
        scfg = (cfg.get("sources") or {}).get(name) or {}
        budget = scfg.get("detail_budget", 0) if detail_budget is None else detail_budget
        if not budget or name not in collectors:
            continue
        wanted = [r for r in store.open_records()
                  if r["source"] == name and not r.get("detail") and not r.get("overseas")
                  and not r.get("dup_of") and not r.get("noise")]
        wanted.sort(key=lambda r: r.get("first_seen", ""), reverse=True)
        wanted.sort(key=lambda r: posting_type(
            registry, r.get("company_key", ""), r.get("company", ""), r.get("client_type")) is CompanyType.OTHER)
        ids = [r["uid"].split(":", 1)[1] for r in wanted[:budget]]
        t0 = time.monotonic()
        collector = collectors[name]
        collector.client = Client(min_interval=scfg.get("detail_min_interval", scfg.get("min_interval", 0.5)),
                                  max_minutes=scfg.get("detail_max_minutes"))
        details, errors = collector.fetch_details(ids)
        store.add_details(today, details)
        summary["details"][name] = {"requested": len(ids), "fetched": len(details),
                                    "remaining": max(len(wanted) - len(details), 0),
                                    "errors": errors[:20], "seconds": round(time.monotonic() - t0, 1)}

    # 직무 유형(AI). 키가 없거나 실패해도 수집 결과는 그대로 저장한다
    summary["job_types"] = jobtypes.run(store.state, store.load_postings(), today.isoformat())

    # 요약
    reps = [r for r in open_recs if not r.get("dup_of")]
    types = Counter(posting_type(registry, r.get("company_key", ""), r.get("company", ""), r.get("client_type")).value
                    for r in reps)
    personal = config.load("filters")
    today_reps = [p for p in collected
                  if not store.state[p.uid].get("dup_of") and not store.state[p.uid].get("overseas")]
    passed = 0
    for p in today_reps:
        if store.state[p.uid].get("noise"):
            continue
        ok, _ = filters.passes(
            title=p.title, company=p.company,
            company_type=posting_type(registry, company_key(p.company), p.company, p.client_type),
            career_min=p.career_min, career_max=p.career_max, regions=p.regions, filters=personal,
            job_type=(store.state[p.uid].get("job_type") or {}).get("id"),
        )
        passed += ok
    summary.update({
        "open": len(open_recs),
        "overseas_open": len(all_open) - len(open_recs),
        "open_unique": len(reps),
        "duplicates": len(open_recs) - len(reps),
        "noise": sum(1 for r in reps if r.get("noise")),
        "company_types": dict(types),
        "personal_filter_pass": passed,
        "new": len(new_uids),
        "closed": len(closed_uids),
        "finished": datetime.now().isoformat(timespec="seconds"),
    })
    store.save()
    registry.save()
    store.save_run(today, summary)
    return summary

