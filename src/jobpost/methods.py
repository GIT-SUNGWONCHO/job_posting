"""매칭 방식 비교(시험 중, 기획 문서 '매칭 방식 비교'): 같은 공고·같은 정답(내 평가 ○△×)으로 방식을 견준다.

- A 지금: Supabase matches의 AI 결과(지침 v6). 상한 전 점수(parts.base)로 견준다
- B 항목 풀: 공고 정리에서 코드가 뽑은 항목 풀(업무 하나하나, 필수·우대 스킬, 연수, 직급, 도메인, 학력)을 주고
  AI가 3~8개를 골라 가중치·판정을 정함. 점수는 코드가 계산(A와 같은 식)
- C 고정 틀: 코드가 공고 정리로 항목을 만들고 가중치도 고정(핵심 업무 35 · 필수 스킬 25 · 연수·직급 20 · 도메인 10 · 학력 10,
  공고에 없는 항목은 빼고 나머지로 맞춤). AI는 항목마다 판정만
- D AI가 바로 점수: 항목 없이 0~100과 한 줄 이유
같은 지침(config/match_guide.yaml guide)과 같은 지원자 요약·공고 글을 쓴다. 로그에는 지표만 낸다.
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any

from . import config, facts, recommend, taxonomy

log = logging.getLogger(__name__)

C_WEIGHTS = {"핵심 업무": 35, "필수 스킬": 25, "경력 연수·직급": 20, "도메인·업종": 10, "학력·전공": 10}


def _f(fact: dict[str, Any] | None) -> dict[str, Any]:
    return (fact or {}).get("facts") or {}


def frame_items(fact: dict[str, Any] | None) -> list[dict[str, Any]]:
    """C 고정 틀: 공고 정리로 만든 항목(종류, 이름, 공고 요구, 가중치). 공고에 없는 종류는 뺀다."""
    f = _f(fact)
    years = ", ".join(f"{y.get('area', '')} {y.get('min', '')}년 이상" for y in f.get("years") or [])
    level = f.get("level") if f.get("level") not in (None, "적혀 있지 않음") else ""
    domain = [taxonomy.industry_name(d) for d in (f.get("domain_required") or [])]
    degree = f.get("degree") if f.get("degree") not in (None, "적혀 있지 않음", "무관") else ""
    raw = [
        ("핵심 업무", "주요 업무", "; ".join(facts.duty_texts(f))),
        ("필수 스킬", "필수 스킬", ", ".join(f.get("required_skills") or [])),
        ("경력 연수·직급", "연수·직급", " / ".join(x for x in (years, level) if x)),
        ("도메인·업종", "업종 경험", ", ".join(domain)),
        ("학력·전공", "학력", " ".join(x for x in (degree, ", ".join(f.get("majors") or [])) if x)),
    ]
    return [{"kind": k, "name": n, "posting": v, "weight": C_WEIGHTS[k]} for k, n, v in raw if v]


def pool_items(fact: dict[str, Any] | None) -> list[dict[str, str]]:
    """B 항목 풀: 공고 정리의 요구를 하나씩 항목 후보로."""
    f = _f(fact)
    out = [{"kind": "핵심 업무", "posting": d if isinstance(d, str) else f"{d.get('text', '')} ({d.get('scope', '')})"}
           for d in f.get("duties") or []]
    out += [{"kind": "필수 스킬", "posting": s} for s in f.get("required_skills") or []]
    out += [{"kind": "우대 스킬", "posting": s} for s in (f.get("preferred_skills") or [])[:8]]
    out += [{"kind": "경력 연수·직급", "posting": f"{y.get('area', '')} {y.get('min', '')}년 이상"} for y in f.get("years") or []]
    if f.get("level") not in (None, "적혀 있지 않음"):
        out.append({"kind": "경력 연수·직급", "posting": f"직급 {f['level']}"})
    out += [{"kind": "도메인·업종", "posting": f"{taxonomy.industry_name(d)} 경험 필수"} for d in f.get("domain_required") or []]
    out += [{"kind": "도메인·업종", "posting": f"{taxonomy.industry_name(d)} 경험 우대"} for d in f.get("domain_preferred") or []]
    if f.get("degree") not in (None, "적혀 있지 않음", "무관"):
        out.append({"kind": "학력·전공", "posting": f"{f['degree']} {', '.join(f.get('majors') or [])}".strip()})
    out += [{"kind": "자격증", "posting": c} for c in f.get("certs") or []]
    return out


def _head(ptext: str, ptxt: str) -> str:
    g = config.load("match_guide")
    return (f"지원자와 채용공고가 얼마나 맞는지 판단한다. 아래 지침을 따른다.\n[지침]\n{g['guide'].strip()}\n"
            f"- 판정(fit): {', '.join(g['fit'])}\n\n[지원자]\n{ptext}\n\n[공고]\n{ptxt}\n\n")


def run_c(client: Any, ptext: str, ptxt: str, fact: dict[str, Any] | None) -> int | None:
    items = frame_items(fact)
    if not items:
        return None
    fits = list(config.load("match_guide")["fit"])
    lines = "\n".join(f"{i + 1}. [{it['kind']}] {it['posting']}" for i, it in enumerate(items))
    schema = {"type": "OBJECT", "required": ["rows"], "properties": {"rows": {"type": "ARRAY", "items": {
        "type": "OBJECT", "required": ["i", "fit"], "properties": {
            "i": {"type": "INTEGER"}, "fit": {"type": "STRING", "enum": fits}, "me": {"type": "STRING"}}}}}}
    got = client.json(_head(ptext, ptxt) + "[항목] 항목은 정해져 있다. 항목마다 i(번호)와 판정(fit), 지원자 쪽 근거(me, 40자 안쪽)만 낸다.\n"
                      + lines, schema)
    fit = {r["i"]: r.get("fit") for r in got.get("rows") or []}
    return recommend.score_items([{**it, "fit": fit.get(i + 1, "정보 없음")} for i, it in enumerate(items)])


def run_b(client: Any, ptext: str, ptxt: str, fact: dict[str, Any] | None) -> int | None:
    pool = pool_items(fact)
    if not pool:
        return None
    fits = list(config.load("match_guide")["fit"])
    lines = "\n".join(f"{i + 1}. [{it['kind']}] {it['posting']}" for i, it in enumerate(pool))
    schema = {"type": "OBJECT", "required": ["rows"], "properties": {"rows": {"type": "ARRAY", "items": {
        "type": "OBJECT", "required": ["i", "weight", "fit"], "properties": {
            "i": {"type": "INTEGER"}, "weight": {"type": "INTEGER"}, "fit": {"type": "STRING", "enum": fits},
            "me": {"type": "STRING"}}}}}}
    got = client.json(_head(ptext, ptxt) + "[항목 풀] 아래 후보 중 이 공고에서 중요한 것을 3~8개 골라(번호 i), 가중치(합 100)와 "
                      "판정(fit), 지원자 쪽 근거(me, 40자 안쪽)를 낸다. 후보에 없는 항목은 만들지 않는다.\n" + lines, schema)
    items = [{"weight": r.get("weight"), "fit": r.get("fit")} for r in got.get("rows") or [] if 1 <= int(r.get("i") or 0) <= len(pool)]
    return recommend.score_items(items) if items else None


def run_d(client: Any, ptext: str, ptxt: str) -> int | None:
    schema = {"type": "OBJECT", "required": ["score", "reason"], "properties": {
        "score": {"type": "INTEGER"}, "reason": {"type": "STRING"}}}
    got = client.json(_head(ptext, ptxt) + "항목을 나누지 말고 0~100 점수 하나(80 이상 지원할 만함, 60~79 애매, 60 미만 아님)와 "
                      "이유 한 문장(40자 안쪽)을 낸다.", schema)
    s = got.get("score")
    return max(0, min(100, int(s))) if isinstance(s, int) else None


ORDER = {"good": 2, "maybe": 1, "bad": 0}


def concordance(labels: dict[str, str], score: dict[str, int]) -> float | None:
    """평가가 다른 두 공고 쌍에서 더 좋게 평가한 쪽이 점수도 높은 비율(같은 점수는 반)."""
    pairs = ok = 0.0
    have = [p for p in labels if score.get(p) is not None]
    for a, b in combinations(have, 2):
        la, lb = ORDER[labels[a]], ORDER[labels[b]]
        if la == lb:
            continue
        pairs += 1
        hi, lo = (a, b) if la > lb else (b, a)
        ok += 1 if score[hi] > score[lo] else 0.5 if score[hi] == score[lo] else 0
    return ok / pairs if pairs else None


def compare(screen: dict[str, Any], bodies: dict[str, Any], facts: dict[str, Any], db: Any, client: Any,
            today: Any, methods: str = "BCD", limit: int | None = None) -> list[str]:
    """평가한 공고(내 분야)를 방식마다 매겨 지표를 낸다. 공고·회사는 로그에 쓰지 않는다."""
    from . import feedback, profile

    cfg = config.load("ai").get("match") or {}
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    by_id = {p["id"]: p for p in screen["postings"]}
    labels_all: dict[tuple[str, str], str] = {}
    for r in db.select("feedback", "select=user_id,posting_id,label&order=updated_at"):
        labels_all[(r["user_id"], r["posting_id"])] = r["label"]
    memos = recommend.load_memos(db)
    out: list[str] = []
    for prof in db.select("profiles", "select=user_id,data,version"):
        user, data = prof["user_id"], prof.get("data") or {}
        if not profile.is_v2(data):
            continue
        labels = {pid: lab for (u, pid), lab in labels_all.items() if u == user and pid in by_id}
        rated = sorted(labels)[:limit] if limit else sorted(labels)
        ptext = profile.text(data, today)
        if memos.get(user):
            ptext += "\n[매칭 메모(평가하며 남긴 말에서 뽑음)]\n" + "\n".join(f"- {line}" for line in memos[user])
        a = {r["posting_id"]: (r.get("parts") or {}).get("base")
             for r in db.select("matches", f"select=posting_id,parts&user_id=eq.{user}")
             if (r.get("parts") or {}).get("kind") == "ai"}
        scores: dict[str, dict[str, int | None]] = {"A": {p: a.get(p) for p in rated}}
        calls = 0
        for m in methods:
            scores[m] = {}
            for pid in rated:
                p = by_id[pid]
                ptxt = recommend.posting_text(p, screen, texts.get(pid), facts.get(pid), cfg.get("body_chars", 3000))
                try:
                    calls += 1
                    scores[m][pid] = (run_b(client, ptext, ptxt, facts.get(pid)) if m == "B"
                                      else run_c(client, ptext, ptxt, facts.get(pid)) if m == "C"
                                      else run_d(client, ptext, ptxt))
                except Exception as e:  # noqa: BLE001 - 한 건 실패는 점수 없음으로
                    log.warning("방식 %s 실패: %s", m, str(e)[:120])
                    scores[m][pid] = None
        n = {k: sum(1 for p in rated if labels[p] == k) for k in feedback.LABELS}
        out.append(f"평가한 내 분야 공고 {len(rated)}건(○ {n['good']} △ {n['maybe']} × {n['bad']}), AI 호출 {calls}번")
        for m, sc in scores.items():
            got = {p: s for p, s in sc.items() if s is not None}
            conc = concordance({p: labels[p] for p in got}, got)
            out.append(feedback._metric_line(f"{m} 방식", feedback.metrics(list(got), labels, lambda pid, sc=got: sc.get(pid))))
            out.append(f"    순서 맞음 {conc:.0%}" if conc is not None else "    순서 맞음 -")
    return out
