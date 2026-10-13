"""사람마다 매칭: 개인 필터를 통과한 공고에 점수를 매기고, 상위 공고에 매칭 이유 한 줄을 AI로 쓴다.

점수는 matching.py(규칙), 매칭 이유는 AI 의견이다. AI에는 이름·연락처·회사명을 보내지 않고
업종·연차·직무·프로젝트 요약·스킬만 보낸다(docs/decisions.md 2026-10-13 매칭).
결과는 Supabase matches 표에 사람마다 통째로 다시 쓴다. 같은 공고·같은 프로필 버전이면 지난 매칭 이유를 다시 쓴다.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from . import config, filters, jobtypes, matching
from .models import CompanyType

log = logging.getLogger(__name__)

PROMPT_VERSION = 1


def profile_text(profile: dict[str, Any], today: date) -> str:
    """AI에 보내는 지원자 요약. 회사 이름은 넣지 않는다."""
    names = jobtypes.names()
    years = matching.career_years(profile.get("careerStart", ""), today)
    lines = []
    if years is not None:
        lines.append(f"경력: 약 {years}년")
    if profile.get("currentRole"):
        lines.append(f"현재 직무: {names.get(profile['currentRole'], profile['currentRole'])}")
    if profile.get("targetRoles"):
        lines.append("희망 직무: " + ", ".join(names.get(r, r) for r in profile["targetRoles"]))
    for j in profile.get("jobs") or []:
        period = f"{j.get('start', '')}~{j.get('end') or '현재'}"
        lines.append(f"경력: {j.get('industry') or '업종 미기재'} · {j.get('role', '')} ({period})")
    for p in profile.get("projects") or []:
        lines.append(f"프로젝트: {p.get('title', '')} — {p.get('result', '')}")
    if profile.get("skills"):
        lines.append("스킬: " + ", ".join(profile["skills"]))
    return "\n".join(lines)


def reason_prompt(profile: str, items: list[str], short: bool = False) -> str:
    extra = "이번에는 반드시 40자 이내로 쓴다.\n" if short else ""
    return extra + (
        "지원자 요약과 채용공고를 보고, 공고마다 이 지원자에게 맞는 이유를 한 줄로 쓴다.\n"
        "규칙: 50자 안팎, 70자를 넘지 않는 한 문장. 지원자 요약과 공고에 있는 내용만 쓰고 숫자나 사실을 지어내지 않는다. "
        "맞는 점을 먼저 쓰고, 크게 부족한 점이 있으면 뒤에 짧게 덧붙인다. 존댓말 없이 '~와 맞음', '~ 경험이 강점' 같은 끝맺음.\n\n"
        f"[지원자 요약]\n{profile}\n\n[공고]\n" + "\n\n".join(items)
    )


REASON_SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["i", "reason"], "properties": {
    "i": {"type": "INTEGER"}, "reason": {"type": "STRING"}}}}


def candidates(screen: dict[str, Any], user_filters: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in screen["postings"]:
        if p.get("noise"):
            continue
        c = screen["companies"].get(p["company"]) or {}
        ok, _ = filters.passes(
            title=p["title"], company=c.get("name", ""), company_type=CompanyType(c.get("type", "그 외")),
            career_min=p.get("careerMin"), career_max=p.get("careerMax"), regions=p.get("regions") or [],
            filters=user_filters, job_type=p.get("jobType"),
        )
        if ok:
            out.append(p)
    return out


def run(screen: dict[str, Any], bodies: dict[str, Any], db: Any, client: Any | None, today: date) -> dict[str, Any]:
    cfg = config.load("ai").get("match_reasons") or {}
    defaults = config.load("filters")
    names = jobtypes.names()
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    skills_cache: dict[str, set[str] | None] = {}

    def posting_skills(pid: str) -> set[str] | None:
        if pid not in skills_cache:
            skills_cache[pid] = matching.extract_skills(texts[pid]) if pid in texts else None
        return skills_cache[pid]

    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    summary: dict[str, Any] = {"users": 0, "rows": 0, "reasons_new": 0, "reasons_reused": 0, "calls": 0, "errors": []}
    for prof in db.select("profiles", "select=user_id,data,version"):
        user, data, pv = prof["user_id"], prof.get("data") or {}, prof.get("version", 1)
        if not data.get("skills") and not data.get("currentRole"):
            continue  # 프로필이 비어 있으면 건너뛴다
        summary["users"] += 1
        user_filters = {**defaults, **settings.get(user, {})}
        scored = []
        for p in candidates(screen, user_filters):
            s = matching.score(data, p, posting_skills(p["id"]), today)
            scored.append((s, p))
        scored.sort(key=lambda x: (-x[0]["score"], x[1]["id"]))

        old = {r["posting_id"]: r for r in db.select(
            "matches", f"select=posting_id,reason,reason_meta,profile_v&user_id=eq.{user}")}
        reasons: dict[str, tuple[str, dict[str, Any]]] = {}
        need: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for s, p in scored[:cfg.get("top", 20)]:
            o = old.get(p["id"])
            meta = (o or {}).get("reason_meta") or {}
            if o and o.get("reason") and o.get("profile_v") == pv and meta.get("prompt") == PROMPT_VERSION:
                reasons[p["id"]] = (o["reason"], meta)
                summary["reasons_reused"] += 1
            else:
                need.append((s, p))

        if need and client is not None:
            ptext = profile_text(data, today)
            for start in range(0, len(need), cfg.get("batch", 10)):
                batch = need[start:start + cfg.get("batch", 10)]
                items = []
                for i, (s, p) in enumerate(batch):
                    c = screen["companies"].get(p["company"]) or {}
                    body = (texts.get(p["id"]) or "")[:cfg.get("body_chars", 1200)]
                    items.append(f"#{i} {c.get('name', '')} | {p['title']} | {names.get(p.get('jobType') or '', '')} | {p.get('career', '')}\n"
                                 f"맞는 스킬: {', '.join(s['matched']) or '없음'} / 없는 스킬: {', '.join(s['missing'][:6]) or '없음'}\n{body}")
                meta = {"model": getattr(client, "model", None), "prompt": PROMPT_VERSION, "on": today.isoformat()}
                # 형식이 틀리거나 길면 한 번만 더 짧게 묻고, 그래도 안 되면 버린다
                for short in (False, True):
                    todo = [i for i in range(len(batch)) if batch[i][1]["id"] not in reasons]
                    if not todo:
                        break
                    summary["calls"] += 1
                    try:
                        out = client.json(reason_prompt(ptext, items, short), REASON_SCHEMA)
                    except Exception as e:  # 이유를 못 써도 점수는 저장한다
                        summary["errors"].append(str(e)[:200])
                        break
                    for row in out:
                        i, text = row.get("i"), (row.get("reason") or "").strip()
                        if (isinstance(i, int) and i in todo and 0 < len(text) <= cfg.get("max_chars", 70)):
                            reasons[batch[i][1]["id"]] = (text, meta)
                            summary["reasons_new"] += 1

        rows = []
        for s, p in scored:
            reason, meta = reasons.get(p["id"], (None, None))
            rows.append({"user_id": user, "posting_id": p["id"], "score": s["score"], "parts": s["parts"],
                         "matched": s["matched"], "missing": s["missing"], "reason": reason, "reason_meta": meta,
                         "score_v": s["v"], "profile_v": pv, "computed_on": today.isoformat()})
        db.delete("matches", f"user_id=eq.{user}")
        db.insert("matches", rows)
        summary["rows"] += len(rows)
        log.info("매칭: 공고 %d건, 매칭 이유 %d건", len(rows), len(reasons))
    if not summary["errors"]:
        summary.pop("errors")
    return summary
