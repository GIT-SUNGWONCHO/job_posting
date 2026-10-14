"""사람마다 매칭: 개인 필터를 통과한 공고(후보)를 AI가 하나씩 매긴다.

지금은 로직을 정하는 단계라 점수를 AI가 매기고 판단 근거를 남긴다(docs/decisions.md 2026-10-14 매칭).
AI는 공고마다 비교할 항목을 고르고 항목마다 공고 요구 · 내 근거 · 판정 · 가중치를 적는다. 점수는 코드가 가중치×판정으로
다시 계산한다. 지침은 config/match_guide.yaml이고, 회차마다 내 피드백을 보고 고친다.
규칙 점수(matching.py)도 함께 남겨서 규칙으로 얼마나 비슷하게 낼 수 있는지 비교한다.
결과는 Supabase matches 표에 사람마다 통째로 다시 쓴다. 같은 공고 · 프로필 버전 · 지침 버전 · 모델이면 지난 결과를 다시 쓴다.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date
from typing import Any

from . import ai, config, filters, jobtypes, matching, profile
from .models import CompanyType

log = logging.getLogger(__name__)

PROMPT_VERSION = 2  # 2: 항목별 판단 근거(지침은 match_guide.yaml의 version으로 따로 센다)


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


def schema() -> dict[str, Any]:
    g = config.load("match_guide")
    item = {"type": "OBJECT", "required": ["kind", "name", "posting", "me", "fit", "weight"], "properties": {
        "kind": {"type": "STRING", "enum": g["item_kinds"]},
        "name": {"type": "STRING"},
        "posting": {"type": "STRING"},
        "me": {"type": "STRING"},
        "fit": {"type": "STRING", "enum": list(g["fit"])},
        "weight": {"type": "INTEGER"},
    }}
    return {"type": "OBJECT", "required": ["items", "verdict", "reason", "gaps"], "properties": {
        "items": {"type": "ARRAY", "items": item},
        "verdict": {"type": "STRING", "enum": g["verdicts"]},
        "reason": {"type": "STRING"},
        "gaps": {"type": "ARRAY", "items": {"type": "STRING"}},
    }}


def prompt(profile_text: str, posting_text: str) -> str:
    g = config.load("match_guide")
    return (
        "지원자와 채용공고가 얼마나 맞는지 항목별로 판단한다. 아래 지침을 따른다.\n"
        f"[지침]\n{g['guide'].strip()}\n"
        f"- 항목 종류(kind): {', '.join(g['item_kinds'])}\n"
        f"- 판정(fit): {', '.join(g['fit'])}\n"
        "- 항목마다 name은 짧은 이름, posting은 공고가 요구하는 것, me는 지원자 쪽 근거(각 40자 안쪽)\n"
        f"- verdict: {', '.join(g['verdicts'])} 중 하나\n"
        "- reason: 이 지원자에게 맞는 이유 한 문장(70자 안쪽, 맞는 점 먼저, 크게 부족한 점이 있으면 뒤에 짧게)\n"
        "- gaps: 크게 부족한 점 최대 3개, 짧게\n\n"
        f"[지원자]\n{profile_text}\n\n[공고]\n{posting_text}"
    )


def score_items(items: list[dict[str, Any]]) -> int:
    """가중치를 합 100으로 맞추고 판정 비율을 곱해 더한다. AI가 쓴 합계는 믿지 않는다."""
    fit = config.load("match_guide")["fit"]
    total = sum(max(0, int(i.get("weight") or 0)) for i in items)
    if not total:
        return 0
    return round(sum(max(0, int(i.get("weight") or 0)) * fit.get(i.get("fit"), 0.5) for i in items) * 100 / total)


def posting_text(p: dict[str, Any], screen: dict[str, Any], body: str | None, fact: dict[str, Any] | None,
                 body_chars: int) -> str:
    c = screen["companies"].get(p["company"]) or {}
    names = jobtypes.names()
    head = (f"{c.get('name', '')} ({c.get('type', '')}) | {p['title']} | {names.get(p.get('jobType') or '', '')} | "
            f"{p.get('career', '')} | {', '.join(p.get('employment') or [])}")
    out = head + "\n" + ((body or "")[:body_chars] or "(본문 없음)")
    if fact:
        f = fact["facts"]
        years = ", ".join(f"{y.get('area', '')} {y.get('min', '')}년" for y in f.get("years") or [])
        out += ("\n[공고 정리]\n"
                f"직급: {f.get('level')} / 필수 스킬: {', '.join(f.get('required_skills') or []) or '-'} / "
                f"우대 스킬: {', '.join(f.get('preferred_skills') or []) or '-'} / 연수 요건: {years or '-'}")
    return out


def run(screen: dict[str, Any], bodies: dict[str, Any], db: Any, client: Any | None, today: date,
        facts: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    cfg = config.load("ai").get("match") or {}
    guide_v = config.load("match_guide")["version"]
    defaults = config.load("filters")
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    facts = facts or {}
    model = getattr(client, "model", None)
    calls_left = cfg.get("max_calls", 330)
    deadline = time.monotonic() + cfg.get("max_minutes", 35) * 60

    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    profiles = db.select("profiles", "select=user_id,data,version")
    summary: dict[str, Any] = {"settings": len(settings), "profiles": len(profiles), "users": 0, "rows": 0,
                               "ai_new": 0, "ai_reused": 0, "rule_only": 0, "calls": 0, "errors": []}
    # 같은 프로필 내용(계정이 둘이어도)이면 AI 결과를 함께 쓴다: (공고, 프로필 요약 해시) → 결과
    shared: dict[tuple[str, str], dict[str, Any]] = {}
    for r in db.select("matches", "select=posting_id,score,parts,matched,missing,reason,reason_meta,score_v"):
        meta = r.get("reason_meta") or {}
        if ((r.get("parts") or {}).get("kind") == "ai" and meta.get("profile_hash") and r.get("score_v") == guide_v
                and meta.get("prompt") == PROMPT_VERSION and meta.get("model") == model):
            shared[(r["posting_id"], meta["profile_hash"])] = r
    for prof in profiles:
        user, data, pv = prof["user_id"], prof.get("data") or {}, prof.get("version", 1)
        if not profile.has_content(data):
            summary["skipped_empty"] = summary.get("skipped_empty", 0) + 1
            continue
        summary["users"] += 1
        user_filters = {**defaults, **settings.get(user, {})}
        rule_profile = profile.rule_view(data)
        ptext = profile.text(data, today) if profile.is_v2(data) else None
        phash = hashlib.sha1(ptext.encode()).hexdigest()[:12] if ptext else None

        scored = []
        for p in candidates(screen, user_filters):
            body = texts.get(p["id"])
            rule = matching.score(rule_profile, p, matching.extract_skills(body) if body else None, today)
            scored.append((rule, p))
        # 한도가 모자라면 규칙 점수가 높은 공고부터 AI에 묻는다
        scored.sort(key=lambda x: (x[0]["score"], x[1].get("firstSeen", ""), x[1]["id"]), reverse=True)

        old = {r["posting_id"]: r for r in db.select(
            "matches", f"select=posting_id,score,parts,matched,missing,reason,reason_meta,profile_v,score_v&user_id=eq.{user}")}
        rows = []
        for rule, p in scored:
            o = old.get(p["id"])
            meta = (o or {}).get("reason_meta") or {}
            same = (o and (o.get("parts") or {}).get("kind") == "ai" and o.get("profile_v") == pv
                    and o.get("score_v") == guide_v and meta.get("prompt") == PROMPT_VERSION and meta.get("model") == model)
            row = None
            twin = shared.get((p["id"], phash)) if phash else None
            if same or twin:
                src = o if same else twin
                row = {k: src[k] for k in ("score", "parts", "matched", "missing", "reason", "reason_meta")}
                row["parts"] = {**row["parts"], "rule": rule["score"]}
                if phash:  # 예전 결과에는 해시가 없을 수 있어 여기서 붙여 둔다
                    row["reason_meta"] = {**(row["reason_meta"] or {}), "profile_hash": phash}
                    shared[(p["id"], phash)] = row
                summary["ai_reused"] += 1
            elif ptext and client is not None and calls_left > 0 and time.monotonic() < deadline and len(summary["errors"]) < 5:
                calls_left -= 1
                summary["calls"] += 1
                try:
                    got = client.json(prompt(ptext, posting_text(p, screen, texts.get(p["id"]), facts.get(p["id"]),
                                                                 cfg.get("body_chars", 3000))), schema())
                    items = [i for i in got.get("items") or [] if i.get("kind")]
                    reason = (got.get("reason") or "").strip()
                    if len(reason) > cfg.get("reason_chars", 120):
                        reason = reason[:cfg.get("reason_chars", 120) - 1] + "…"
                    row = {"score": score_items(items),
                           "parts": {"kind": "ai", "items": items, "verdict": got.get("verdict"), "rule": rule["score"]},
                           "matched": [i["name"] for i in items if i.get("fit") == "충족"],
                           "missing": [g for g in got.get("gaps") or [] if g][:3],
                           "reason": reason or None,
                           "reason_meta": {"model": model, "prompt": PROMPT_VERSION, "on": today.isoformat(),
                                           "profile_hash": phash}}
                    shared[(p["id"], phash)] = row
                    summary["ai_new"] += 1
                    if summary["ai_new"] % 25 == 0:
                        log.info("AI 매칭 %d건", summary["ai_new"])
                except Exception as e:  # AI가 실패해도 규칙 점수는 남긴다
                    summary["errors"].append(str(e)[:200])
            if row is None:
                row = {"score": rule["score"], "parts": {"kind": "rule", "rule": rule["score"], **rule["parts"]},
                       "matched": rule["matched"], "missing": rule["missing"][:6], "reason": None, "reason_meta": None}
                summary["rule_only"] += 1
                score_v = rule["v"]
            else:
                score_v = guide_v
            rows.append({"user_id": user, "posting_id": p["id"], **row, "score_v": score_v, "profile_v": pv,
                         "computed_on": today.isoformat()})
        db.delete("matches", f"user_id=eq.{user}")
        db.insert("matches", rows)
        summary["rows"] += len(rows)
        log.info("매칭: 공고 %d건(AI 새로 %d, 다시 씀 %d, 규칙만 %d)", len(rows), summary["ai_new"],
                 summary["ai_reused"], summary["rule_only"])
    if not summary["errors"]:
        summary.pop("errors")
    return summary


def make_client() -> Any | None:
    if not ai.configured():
        return None
    return ai.Gemini(model=(config.load("ai").get("match") or {}).get("model"))
