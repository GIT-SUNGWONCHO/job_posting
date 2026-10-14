"""AI 매칭 시험: 같은 공고를 AI가 0~100점으로 매기고 규칙 점수(matching.py)와 나란히 낸다.

점수 계산법을 정하기 위한 비교용이다. 결과는 Supabase에 쓰지 않고 실행 로그에만 남긴다.
AI에 보내는 지원자 요약은 매칭 이유와 같다(recommend.profile_text, 회사 이름 없음).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any

from . import config, jobtypes, matching, recommend

log = logging.getLogger(__name__)

BODY_CHARS = 2500  # 자격 요건은 본문 뒤쪽에 있는 경우가 많아 매칭 이유(1200자)보다 길게 보낸다

SCHEMA = {"type": "OBJECT", "required": ["score", "reason", "gaps"], "properties": {
    "score": {"type": "INTEGER"},
    "reason": {"type": "STRING"},
    "gaps": {"type": "ARRAY", "items": {"type": "STRING"}},
}}


def prompt(profile: str, posting: str) -> str:
    return (
        "채용 담당자로서 지원자 요약과 채용공고를 보고, 이 지원자가 이 공고에 얼마나 맞는지 0~100점으로 매긴다.\n"
        "판단 기준(중요한 순서):\n"
        "1. 핵심 업무: 공고의 주요 업무를 지원자가 실제로 해 본 적이 있는가\n"
        "2. 필수 요건: 자격 요건을 충족하는가. 우대 사항은 가점만 주고 없다고 크게 깎지 않는다\n"
        "3. 경력 수준: 요구 연차·직급(주니어/시니어/리드)이 지원자와 맞는가. 지원자 연차가 훨씬 높아도 깎는다\n"
        "공고에 없는 내용은 추측하지 않는다. 본문이 없으면 제목과 경력만으로 판단하고 60점을 넘기지 않는다.\n"
        "점수: 90 이상 = 핵심 업무와 필수 요건이 거의 다 맞음, 70~89 = 대부분 맞고 일부 부족, "
        "50~69 = 관련은 있지만 핵심 업무가 다름, 50 미만 = 맞지 않음.\n"
        "reason: 판단 근거 한 문장(80자 이내). gaps: 부족한 필수 요건이나 핵심 업무(최대 3개, 짧게).\n\n"
        f"[지원자 요약]\n{profile}\n\n[공고]\n{posting}"
    )


def run(screen: dict[str, Any], bodies: dict[str, Any], db: Any, client: Any, today: date,
        max_minutes: float = 35) -> list[dict[str, Any]]:
    """프로필이 있는 첫 사람 기준으로 필터 통과 공고 전부를 AI와 규칙으로 매긴다."""
    defaults = config.load("filters")
    names = jobtypes.names()
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    prof = next(p for p in db.select("profiles", "select=user_id,data") if (p.get("data") or {}).get("skills"))
    user, data = prof["user_id"], prof["data"]
    settings = db.select("settings", f"select=filters&user_id=eq.{user}")
    user_filters = {**defaults, **((settings[0].get("filters") or {}) if settings else {})}
    ptext = recommend.profile_text(data, today)

    out: list[dict[str, Any]] = []
    started = time.monotonic()
    failures = 0
    for p in recommend.candidates(screen, user_filters):
        if time.monotonic() - started > max_minutes * 60 or failures >= 5:
            log.info("멈춤(시간 한도 또는 연속 실패): %d건", len(out))
            break
        body = texts.get(p["id"])
        rule = matching.score(data, p, matching.extract_skills(body) if body else None, today)
        c = screen["companies"].get(p["company"]) or {}
        posting = (f"{c.get('name', '')} | {p['title']} | {names.get(p.get('jobType') or '', '')} | {p.get('career', '')}\n"
                   + ((body or "")[:BODY_CHARS] or "(본문 없음)"))
        row = {"id": p["id"], "company": c.get("name", ""), "title": p["title"], "jobType": p.get("jobType"),
               "career": p.get("career"), "hasBody": body is not None, "rule": rule["score"], "parts": rule["parts"]}
        try:
            res = client.json(prompt(ptext, posting), SCHEMA)
            row.update(ai=res.get("score"), reason=res.get("reason"), gaps=res.get("gaps") or [])
            failures = 0
        except Exception as e:  # 한 건 실패해도 나머지는 계속
            row.update(ai=None, error=str(e)[:120])
            failures += 1
        out.append(row)
        print("AIM\t" + json.dumps(row, ensure_ascii=False), flush=True)
    return out
