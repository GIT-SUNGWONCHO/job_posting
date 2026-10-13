"""화면용 파일: 오늘 열린 국내 공고와 회사 기본정보를 파일 하나로 묶는다.

브라우저는 이 파일을 한 번 받아서 필터·검색·정렬을 직접 한다(docs/architecture.md).
같은 공고가 여러 수집처에 있으면 대표 하나로 묶고, 수집처별 링크는 sources에 모은다.
마감 D-숫자는 보는 날에 따라 바뀌어서 브라우저가 계산하고, 경력 표기처럼 바뀌지 않는 글은 여기서 만든다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config
from .companies import CompanyRegistry
from .normalize import career_text, clean_company
from .store import Store

VERSION = 1
SOURCE_NAMES = {"zighang": "직행", "remember": "리멤버", "saramin": "사람인"}


def build(data_dir: Path, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    store = Store(data_dir)
    registry = CompanyRegistry(data_dir / "companies.json")
    originals = store.load_postings()

    open_recs = [r for r in store.open_records() if not r.get("overseas")]
    dups: dict[str, list[dict[str, Any]]] = {}
    for r in open_recs:
        if r.get("dup_of"):
            dups.setdefault(r["dup_of"], []).append(r)

    def link(r: dict[str, Any]) -> dict[str, Any]:
        o = originals.get(r["uid"], {})
        return {"source": r["source"], "name": SOURCE_NAMES.get(r["source"], r["source"]), "url": o.get("url")}

    companies: dict[str, dict[str, Any]] = {}
    postings: list[dict[str, Any]] = []
    for r in open_recs:
        if r.get("dup_of"):
            continue
        o = originals.get(r["uid"], {})
        key = r.get("company_key") or r.get("company", "")
        if key not in companies:
            name = r.get("company") or (registry.data.get(key) or {}).get("name") or key
            companies[key] = {
                "name": clean_company(name),
                "type": registry.company_type(key, r.get("company", "")).value,
                "group": registry.group(key, r.get("company", "")),
            }
        same = sorted(dups.get(r["uid"], []), key=lambda d: d["uid"])
        first_seen = min([r.get("first_seen", "")] + [d.get("first_seen", "") for d in same])
        postings.append({
            "id": r["uid"],
            "company": key,
            "title": r.get("title", ""),
            "careerMin": o.get("career_min"),
            "careerMax": o.get("career_max"),
            "career": career_text(o.get("career_min"), o.get("career_max")),
            "deadlineType": r.get("deadline_type"),
            "deadline": r.get("deadline"),
            "regions": o.get("regions") or [],
            "employment": o.get("employment_types") or [],
            "headhunter": bool(r.get("headhunter")),
            "noise": r.get("noise"),
            "firstSeen": first_seen,
            "sources": [link(r)] + [link(d) for d in same],
        })
    postings.sort(key=lambda p: (p["firstSeen"], p["id"]), reverse=True)

    counts = {
        "open": len(postings),
        "new": sum(1 for p in postings if p["firstSeen"] == today.isoformat()),
        "companies": len(companies),
    }
    return {
        "version": VERSION,
        "date": today.isoformat(),
        "built": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "defaultFilters": config.load("filters"),
        "companies": companies,
        "postings": postings,
    }


def write(screen: dict[str, Any], out: Path) -> Path:
    """.gz로 끝나면 압축해서 쓴다. 같은 내용이면 같은 파일이 되도록 mtime=0."""
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(screen, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if out.suffix == ".gz":
        with open(out, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(raw)
    else:
        out.write_bytes(raw)
    return out
