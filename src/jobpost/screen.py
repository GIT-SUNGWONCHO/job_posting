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

from . import career, config, dart, facts, jobtypes, research
from .companies import CompanyRegistry, major_candidates
from .normalize import career_text, clean_company, common_name, company_key
from .store import Store

VERSION = 5  # 2: 직무 유형(jobType, jobTypes), 3: 본문 파일(hasBody, bodies.json.gz), 4: 스킬 목록·프로필 선택지(skills, profileOptions), 기준 샘플(sample), 5: 커리어 지표(career)
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


def build(data_dir: Path, today: date | None = None, with_career: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """(화면용 파일, 본문 파일). with_career: 커리어 지표까지(본문 스킬을 다 찾느라 20초쯤 더 걸려 화면용 파일을 올릴 때만)."""
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
    texts = {pid: b["text"] for pid, b in bodies.items()}
    screen = {
        "version": VERSION,
        "date": today.isoformat(),
        "built": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "defaultFilters": config.load("filters"),
        "jobTypes": [{"id": t["id"], "name": t["name"], "short": t.get("short", t["name"]), "direction": t.get("direction", True)}
                     for t in jobtypes.taxonomy()["types"]],
        # 프로필 화면에서 고르는 목록(config/profile.yaml)과 공고에서 나온 스킬
        "profileOptions": config.load("profile"),
        "skills": facts.skill_catalog(texts, facts.load(data_dir)),
        # 기준 샘플(config/match_sample.yaml): 화면의 "평가할 공고"
        "sample": [p["id"] for p in config.load("match_sample").get("postings") or []],
        # 커리어 탭 시장 지표(career.py): 날짜별 공고 수, 지금 열린 공고의 연차·스킬
        "career": career.build(store.state, registry, postings, companies, bodies, today) if with_career else None,
        "companies": companies,
        "postings": postings,
    }
    # 공고가 없어도 회사 목록에 두는 주요 기업(커리어 지표·공고 수에는 들어가지 않는다)
    for key, m in major_companies(data_dir, set(companies)).items():
        companies[key] = {"name": m["name"], "type": m["type"], "group": m["group"]}
    return screen, {"version": VERSION, "date": today.isoformat(), "bodies": bodies}


def major_companies(data_dir: Path, posting_keys: set[str]) -> dict[str, dict[str, Any]]:
    """주요 기업(companies.major_candidates) 중 기본정보를 받은 곳. 상장사 목록에서 온 곳은 지금 상장된 곳만(유가증권·코스닥·코넥스).
    공고가 들어온 회사와 키가 같거나 같은 DART 회사로 이어진 곳은 빼서 한 회사가 두 번 나오지 않게 한다.
    키 → {code, name, type, group}."""
    corps = _read_json(data_dir / "dart" / "corps.json")
    basics = _read_json(data_dir / "dart" / "basics.json")
    rows = ((_read_json(data_dir / "dart" / "listed.json").get("corps") or [])
            + (_read_json(data_dir / "dart" / "filers.json").get("corps") or []))
    taken = {(corps.get(k) or {}).get("corp_code") for k in posting_keys} - {None}
    out: dict[str, dict[str, Any]] = {}
    for c in major_candidates(rows):
        b = basics.get(c["code"]) or {}
        if not b or b.get("unlisted"):
            continue
        # 상장사 목록에서 온 곳은 지금 상장된 곳만. 사업보고서를 낸 비상장 회사는 그대로
        if c["stock"] and (b.get("company") or {}).get("market") not in dart.LISTED_MARKETS:
            continue
        key = company_key(c["name"])
        if not key or key in posting_keys or key in out or c["code"] in taken:
            continue
        out[key] = {"code": c["code"], "name": common_name(c["name"]), "type": c["type"], "group": c["group"]}
    return out


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


COMPANIES_VERSION = 1  # 회사 기본정보 파일(companies.json.gz) 형식. web/src/lib/types.ts CompanyBasics와 같게
PAST_MAX = 50  # 회사마다 남길 지난 공고 수(최근 마감 순). 수는 pastByJob에 전부 센다


def build_companies(data_dir: Path, screen: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """회사 기본정보 파일: 오늘 화면에 있는 회사마다 DART 기본정보(dart.py가 data/dart/에 쌓은 것),
    이 앱이 수집한 지난 공고(마감된 국내 공고), 심층분석 중 가진 데이터로 만드는 모듈(research.py: 경쟁사, 직무 환경·도구).
    회사 화면을 열 때 한 번 받는다."""
    today = today or date.today()
    corps = _read_json(data_dir / "dart" / "corps.json")
    basics = _read_json(data_dir / "dart" / "basics.json")
    store = Store(data_dir)
    keys = set(screen["companies"])
    majors = major_companies(data_dir, {p["company"] for p in screen["postings"]})
    # DART 고유번호 → 화면 회사(경쟁사 줄에서 회사 화면으로 잇는다)
    code_key: dict[str, str] = {}
    for key in keys:
        code = (corps.get(key) or {}).get("corp_code") or (majors.get(key) or {}).get("code")
        if code:
            code_key.setdefault(code, key)
    code_name = {code: screen["companies"][key]["name"] for code, key in code_key.items()}
    peers = research.Peers(basics)
    texts = _company_texts(store, keys)
    past: dict[str, list[dict[str, Any]]] = {}
    for r in store.state.values():
        if not r.get("closed_on") or r.get("overseas") or r.get("dup_of") or r.get("noise"):
            continue
        key = r.get("company_key") or r.get("company", "")
        if key in keys:
            past.setdefault(key, []).append({
                "id": r["uid"],
                "title": r.get("title", ""),
                "jobType": (r.get("job_type") or {}).get("id"),
                "firstSeen": r.get("first_seen"),
                "closedOn": r.get("closed_on"),
            })
    out: dict[str, Any] = {}
    for key in sorted(keys):
        item: dict[str, Any] = {}
        m = corps.get(key)
        if not m and key in majors:
            m = {"corp_code": majors[key]["code"], "corp_name": majors[key]["name"], "how": "major"}
        if m:
            code = m.get("corp_code")
            b = basics.get(code) if code else None
            if code and b:
                item["dart"] = _dart_item(code, m, b)
            elif code:
                item["dart"] = {"corpCode": code, "corpName": m.get("corp_name"), "pending": True}
            else:
                item["dart"] = {"none": m.get("why", "none"), "checked": m.get("checked")}
        rows = sorted(past.get(key, []), key=lambda x: (x["closedOn"] or "", x["firstSeen"] or ""), reverse=True)
        if rows:
            item["past"] = rows[:PAST_MAX]
            by_job: dict[str, int] = {}
            for x in rows:
                by_job[x["jobType"] or "none"] = by_job.get(x["jobType"] or "none", 0) + 1
            item["pastByJob"] = by_job
        deep: dict[str, Any] = {}
        code = (item.get("dart") or {}).get("corpCode")
        if code and code in basics:
            comp = peers.competitors(code, code_name, code_key)
            if comp:
                deep["competitors"] = comp
        found = research.tools(texts.get(key, []))
        if found:
            deep["tools"] = found
        if deep:
            item["research"] = deep
        if item:
            out[key] = item
    return {"version": COMPANIES_VERSION, "date": today.isoformat(), "since": min(
        (r.get("first_seen") for r in store.state.values() if r.get("first_seen")), default=today.isoformat()),
        "companies": out}


def _company_texts(store: Store, keys: set[str]) -> dict[str, list[str]]:
    """회사마다 이 앱이 모은 국내 공고(열린 것과 지난 것, 잡음 제외)의 본문. 같은 공고 묶음은 하나로."""
    originals = store.load_postings()
    details = store.load_details()
    members: dict[str, list[dict[str, Any]]] = {}
    for r in store.state.values():
        if r.get("dup_of"):
            members.setdefault(r["dup_of"], []).append(r)
    out: dict[str, list[str]] = {}
    for r in store.state.values():
        if r.get("dup_of") or r.get("overseas") or r.get("noise"):
            continue
        key = r.get("company_key") or r.get("company", "")
        if key not in keys:
            continue
        body = _body([r, *members.get(r["uid"], [])], originals, details)
        if body:
            out.setdefault(key, []).append(body["text"])
    return out


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _dart_item(code: str, m: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    cfg = config.load("dart")
    c = b.get("company") or {}
    fin = b.get("finance")
    emp = b.get("employees")
    return {
        "corpCode": code,
        "corpName": m.get("corp_name") or c.get("name"),  # 고유번호 파일 이름은 (주) 같은 표기가 없다
        # 기업개황의 법인명(현대자동차(주)). 잘못 이은 회사를 알아볼 수 있게 화면에 보여준다
        "legalName": c.get("name") or m.get("corp_name"),
        "market": c.get("market"),
        "ceo": c.get("ceo"),
        "founded": c.get("founded"),
        "homepage": dart.clean_url(c.get("homepage")),  # 예전에 받은 값도 화면을 만들 때 다시 거른다
        "finance": fin and {"year": fin["year"], "basis": fin["basis"], "rceptNo": fin.get("rcept_no"),
                            "revenueName": fin.get("revenue_name") or "매출액", "years": fin["years"]},
        "employees": emp and {"count": emp["count"], "tenure": emp.get("tenure"), "salary": emp.get("salary"),
                              "rceptNo": emp.get("rcept_no")},
        "disclosures": [{"date": d["date"], "title": d["title"], "rceptNo": d.get("rcept_no")}
                        for d in dart.pick_disclosures(b.get("disclosures") or [], cfg.get("disclosure_skip") or [],
                                                       cfg.get("disclosure_max", 8))],
        "fetched": b.get("fetched"),
    }
