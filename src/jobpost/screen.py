"""화면용 파일: 오늘 열린 국내 공고와 회사 기본정보를 파일 하나로 묶는다. 본문은 따로 묶는다.

브라우저는 이 파일을 한 번 받아서 필터·검색·정렬을 직접 한다(docs/architecture.md).
같은 공고가 여러 수집처에 있으면 대표 하나로 묶고, 수집처별 링크는 sources에 모은다.
마감 D-숫자는 보는 날에 따라 바뀌어서 브라우저가 계산하고, 경력 표기처럼 바뀌지 않는 글은 여기서 만든다.
본문(bodies)은 커서 목록 파일과 나누고, 공고 상세를 처음 열 때 브라우저가 받는다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config, jobtypes
from .companies import CompanyRegistry
from .normalize import career_text, clean_company
from .store import Store

VERSION = 3  # 2: 직무 유형(jobType, jobTypes), 3: 본문 파일(hasBody, bodies.json.gz)
BODY_MAX = 4000  # 본문 최대 글자 수
BODY_MIN = 50  # 이보다 짧으면 이미지뿐인 공고로 보고 본문 없음으로 둔다
# 본문을 고르는 순서: 리멤버 원문 > 직행이 정리한 요약 > 사람인 원문
BODY_PRIORITY = {"remember": 0, "zighang": 1, "saramin": 2}
# 본문은 공고 id로 나눈 여러 파일에 담는다. 상세를 열면 그 공고가 든 파일 하나만 받는다
BODY_SHARDS = 16


def body_shard(posting_id: str) -> str:
    """FNV-1a 32비트(UTF-8). web/src/lib/load.ts의 bodyShard와 같아야 한다."""
    h = 0x811C9DC5
    for b in posting_id.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h % BODY_SHARDS:02x}"


def write_bodies(bodies: dict[str, Any], out_dir: Path) -> list[Path]:
    """bodies/00.json.gz … bodies/0f.json.gz. 빈 묶음도 쓴다(지난 날의 본문이 남지 않게)."""
    shards: dict[str, dict[str, Any]] = {f"{i:02x}": {} for i in range(BODY_SHARDS)}
    for pid, body in bodies["bodies"].items():
        shards[body_shard(pid)][pid] = body
    return [write({"version": bodies["version"], "date": bodies["date"], "bodies": part}, out_dir / "bodies" / f"{k}.json.gz")
            for k, part in shards.items()]
SOURCE_NAMES = {"zighang": "직행", "remember": "리멤버", "saramin": "사람인"}


def _body(members: list[dict[str, Any]], originals: dict[str, dict[str, Any]],
          details: dict[str, dict[str, Any]]) -> dict[str, str] | None:
    for r in sorted(members, key=lambda m: BODY_PRIORITY.get(m["source"], 9)):
        text = (originals.get(r["uid"]) or {}).get("description") or (details.get(r["uid"]) or {}).get("description")
        if text and len(text.strip()) >= BODY_MIN:
            return {"text": text.strip()[:BODY_MAX], "source": r["source"]}
    return None


def build(data_dir: Path, today: date | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(화면용 파일, 본문 파일)."""
    today = today or date.today()
    store = Store(data_dir)
    registry = CompanyRegistry(data_dir / "companies.json")
    originals = store.load_postings()
    details = store.load_details()
    bodies: dict[str, dict[str, str]] = {}

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
        job_type = next(((x.get("job_type") or {}).get("id") for x in [r, *same] if x.get("job_type")), None)
        first_seen = min([r.get("first_seen", "")] + [d.get("first_seen", "") for d in same])
        body = _body([r, *same], originals, details)
        if body:
            bodies[r["uid"]] = body
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
            "jobType": job_type,
            "hasBody": body is not None,
            "sources": [link(r)] + [link(d) for d in same],
        })
    postings.sort(key=lambda p: (p["firstSeen"], p["id"]), reverse=True)

    counts = {
        "open": len(postings),
        "new": sum(1 for p in postings if p["firstSeen"] == today.isoformat()),
        "companies": len(companies),
    }
    screen = {
        "version": VERSION,
        "date": today.isoformat(),
        "built": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "defaultFilters": config.load("filters"),
        "jobTypes": [{"id": t["id"], "name": t["name"]} for t in jobtypes.taxonomy()["types"]],
        "companies": companies,
        "postings": postings,
    }
    return screen, {"version": VERSION, "date": today.isoformat(), "bodies": bodies}


def write(screen: dict[str, Any], out: Path) -> Path:  # 본문 파일도 같은 함수로 쓴다
    """.gz로 끝나면 압축해서 쓴다. 같은 내용이면 같은 파일이 되도록 mtime=0."""
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(screen, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if out.suffix == ".gz":
        with open(out, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(raw)
    else:
        out.write_bytes(raw)
    return out
