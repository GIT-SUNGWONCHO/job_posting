"""공고 정리: 본문에 글로만 있는 매칭 항목(핵심 업무, 필수·우대 스킬, 연수 요건, 직급, 도메인, 학력, 어학 등)을
AI가 공고당 한 번 뽑아 data 폴더 facts.jsonl에 둔다. 공고의 것이라 모든 사람이 함께 쓴다.

적힌 것만 뽑고 추측하지 않는다. 지시문을 바꾸면 PROMPT_VERSION을 올린다(다시 뽑는다).
어느 공고부터 뽑을지는 사람마다 개인 필터를 통과한 공고(후보)의 합집합이다(docs/decisions.md 2026-10-14 매칭).
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from . import config, matching, recommend

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
BODY_CHARS = 3500  # 자격요건·우대사항은 본문 뒤쪽에 있어서 넉넉히 보낸다
FILE = "facts.jsonl"

LEVELS = ["주니어", "미들", "시니어", "리드·매니저", "적혀 있지 않음"]
DEGREES = ["무관", "학사", "석사", "박사", "적혀 있지 않음"]
NEEDS = ["필수", "우대", "적혀 있지 않음"]
WORK = ["출근", "하이브리드", "재택", "적혀 있지 않음"]


def industries() -> dict[str, str]:
    return {i["id"]: i["name"] for i in config.load("profile")["industries"]}


def schema() -> dict[str, Any]:
    ids = list(industries())
    strings = {"type": "ARRAY", "items": {"type": "STRING"}}
    return {"type": "OBJECT", "required": ["level", "duties", "required_skills", "preferred_skills", "years",
                                           "domain_required", "domain_preferred", "degree", "majors", "certs",
                                           "english", "work_mode"],
            "properties": {
                "level": {"type": "STRING", "enum": LEVELS},
                "duties": strings,
                "required_skills": strings,
                "preferred_skills": strings,
                "years": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["area", "min"], "properties": {
                    "area": {"type": "STRING"}, "min": {"type": "INTEGER"}}}},
                "domain_required": {"type": "ARRAY", "items": {"type": "STRING", "enum": ids}},
                "domain_preferred": {"type": "ARRAY", "items": {"type": "STRING", "enum": ids}},
                "degree": {"type": "STRING", "enum": DEGREES},
                "majors": strings,
                "major_need": {"type": "STRING", "enum": NEEDS},
                "certs": strings,
                "english": {"type": "STRING", "enum": NEEDS},
                "work_mode": {"type": "STRING", "enum": WORK},
                "salary": {"type": "STRING"},
            }}


def prompt(posting: str) -> str:
    names = ", ".join(f"{k}={v}" for k, v in industries().items())
    return (
        "채용공고에서 아래 항목을 뽑는다. 공고에 적힌 것만 뽑고, 적혀 있지 않으면 빈 목록이나 '적혀 있지 않음'으로 둔다.\n"
        "- level: 직급. 제목·본문에 주니어/시니어/리드·매니저 표기나 연차로 드러날 때만\n"
        "- duties: 주요 업무 3~5개, 각 30자 안쪽\n"
        "- required_skills / preferred_skills: 자격요건(필수)과 우대사항에 나온 기술·도구·방법론 이름. "
        "'Python', 'Spark', 'Airflow', '데이터 모델링'처럼 짧게, 문장 말고 이름만\n"
        "- years: 연수 요건. 예) '데이터 엔지니어링 5년 이상' → area '데이터 엔지니어링', min 5. 총 경력만 있으면 area '총 경력'\n"
        f"- domain_required / domain_preferred: 특정 업종 경험을 요구·우대할 때 업종 id. 목록: {names}\n"
        "- degree, majors, major_need: 학력, 전공 이름, 전공이 필수인지 우대인지\n"
        "- certs: 자격증 이름. english: 영어가 필수인지 우대인지. work_mode: 근무 방식. salary: 연봉 표기 그대로(없으면 빈 문자열)\n\n"
        f"[공고]\n{posting}"
    )


def load(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / FILE
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["uid"]] = r
    return out


def save(data_dir: Path, rows: dict[str, dict[str, Any]]) -> None:
    lines = [json.dumps(rows[k], ensure_ascii=False, sort_keys=True) for k in sorted(rows)]
    (data_dir / FILE).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def is_current(row: dict[str, Any] | None) -> bool:
    return bool(row) and row.get("prompt") == PROMPT_VERSION and row.get("industries_v") == config.load("profile")["version"]


def posting_text(p: dict[str, Any], company: str, body: str | None) -> str:
    head = f"{company} | {p['title']} | {p.get('career', '')} | {', '.join(p.get('employment') or [])}"
    return head + "\n" + ((body or "")[:BODY_CHARS] or "(본문 없음)")


def run(data_dir: Path, screen: dict[str, Any], bodies: dict[str, Any], wanted: list[str],
        client: Any | None, today: str) -> dict[str, Any]:
    """wanted(후보 공고 id, 앞에서부터 먼저)에서 아직 정리하지 않은 것을 하루 한도까지 정리한다."""
    rows = load(data_dir)
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    todo = [pid for pid in wanted if pid in texts and not is_current(rows.get(pid))]
    summary: dict[str, Any] = {"wanted": len(wanted), "pending": len(todo), "done": 0, "calls": 0}
    if not todo:
        return summary
    if client is None:
        summary["skipped"] = "GEMINI_API_KEY 없음"
        return summary
    cfg = config.load("ai").get("facts") or {}
    by_id = {p["id"]: p for p in screen["postings"]}
    deadline = time.monotonic() + cfg.get("max_minutes", 20) * 60
    errors: list[str] = []
    for pid in todo:
        if summary["calls"] >= cfg.get("max_calls", 250) or time.monotonic() > deadline or len(errors) >= 5:
            break
        p = by_id[pid]
        company = (screen["companies"].get(p["company"]) or {}).get("name", "")
        summary["calls"] += 1
        try:
            got = client.json(prompt(posting_text(p, company, texts.get(pid))), schema())
        except Exception as e:  # 남은 건 다음 실행에서
            errors.append(str(e)[:200])
            continue
        rows[pid] = {"uid": pid, "facts": got, "prompt": PROMPT_VERSION, "industries_v": config.load("profile")["version"],
                     "model": getattr(client, "model", None), "on": today}
        summary["done"] += 1
        if summary["done"] % 25 == 0:
            save(data_dir, rows)  # 중간에 멈춰도 한 일은 남긴다
            log.info("공고 정리 %d/%d건", summary["done"], len(todo))
    save(data_dir, rows)
    summary["pending"] = len(todo) - summary["done"]
    if errors:
        summary["errors"] = errors[:3]
    return summary


def candidates_for_all(screen: dict[str, Any], settings: list[dict[str, Any]]) -> list[str]:
    """사람마다 개인 필터를 통과한 공고의 합집합. 최근 공고부터."""
    defaults = config.load("filters")
    seen: dict[str, str] = {}
    for user_filters in [{**defaults, **(s.get("filters") or {})} for s in settings] or [defaults]:
        for p in recommend.candidates(screen, user_filters):
            seen[p["id"]] = p.get("firstSeen", "")
    return sorted(seen, key=lambda pid: (seen[pid], pid), reverse=True)


def _norm_skill(name: str) -> str | None:
    """공고에서 뽑은 스킬 이름을 사전 이름으로 맞춘다. 사전에 없으면 그대로(목록에 추가할 후보)."""
    n = re.sub(r"\s+", " ", name or "").strip(" -·,./()")
    if not n or len(n) > 30:
        return None
    found = matching.extract_skills(n)
    return next(iter(found)) if len(found) == 1 else n


def skill_catalog(texts: dict[str, str], rows: dict[str, dict[str, Any]], limit: int = 500) -> list[dict[str, Any]]:
    """프로필에서 고르는 스킬 목록: 공고 본문에서 사전으로 찾은 스킬 + 공고 정리에서 뽑은 스킬, 나온 공고 수 순."""
    counts: dict[str, int] = {}
    shown: dict[str, dict[str, int]] = {}
    for pid in set(texts) | set(rows):
        names = set(matching.extract_skills(texts[pid])) if pid in texts else set()
        f = (rows.get(pid) or {}).get("facts") or {}
        for raw in (f.get("required_skills") or []) + (f.get("preferred_skills") or []):
            n = _norm_skill(raw)
            if n:
                names.add(n)
        for n in {x.lower(): x for x in names}.values():
            key = n.lower()
            counts[key] = counts.get(key, 0) + 1
            shown.setdefault(key, {})
            shown[key][n] = shown[key].get(n, 0) + 1
    dictionary = {s.lower() for g in config.load("skills")["groups"].values() for s in (i["name"] for i in g)}
    # 표기가 여럿이면 많이 쓴 것, 같으면 대문자가 있는 것
    out = [{"name": max(shown[k], key=lambda x: (shown[k][x], x != x.lower(), x)), "count": c}
           for k, c in counts.items() if c >= 2 or k in dictionary]
    out.sort(key=lambda x: (-x["count"], x["name"]))
    return out[:limit]
