"""사람마다 매칭: 개인 필터를 통과한 공고(후보)를 AI가 하나씩 매긴다.

지금은 로직을 정하는 단계라 점수를 AI가 매기고 판단 근거를 남긴다(docs/decisions.md 2026-10-14 매칭).
AI는 공고마다 비교할 항목을 고르고 항목마다 공고 요구 · 내 근거 · 판정 · 가중치를 적는다. 점수는 코드가 가중치×판정으로
다시 계산한다. 지침은 config/match_guide.yaml이고, 회차마다 내 피드백을 보고 고친다.
v2부터 AI는 공고 사실(직급·영어·고용 형태·업종)도 따로 적고, 코드가 원하는 조건(프로필 wants)과 개인 필터의
고용 형태에 맞춰 상한·가감점을 준다(adjust). 판정 이름은 최종 점수 구간으로 정한다(bands).
원하는 조건은 AI에 보내지 않아서, 그것만 바꾸면 AI를 다시 부르지 않고 지난 결과에 조정만 다시 한다.
평가 코멘트에서 뽑은 매칭 메모(match_memos 표)는 지원자 요약 끝에 붙인다. 메모가 바뀌면 다시 매긴다.
규칙 점수(matching.py)도 함께 남겨서 규칙으로 얼마나 비슷하게 낼 수 있는지 비교한다.
결과는 Supabase matches 표에 사람마다 통째로 다시 쓴다. 같은 공고 · 프로필 버전 · 지침 버전 · 모델이면 지난 결과를 다시 쓴다.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import Counter
from datetime import date
from typing import Any

from . import ai, bodyread, config, filters, jobtypes, matching, profile, taxonomy
from .models import CompanyType

log = logging.getLogger(__name__)

PROMPT_VERSION = 4  # 2: 항목별 판단 근거, 3: 이유 40자 안쪽, 4: 공고 사실을 따로, 판정은 코드가.
# 2026-11-05 공고 사실에서 업종을 뺐다(회사 업종을 씀). 빼기만 해서 버전은 그대로: 지난 결과를 다시 매기지 않는다(매칭 따라잡기 때 함께). 지침은 match_guide.yaml version


# 매칭 대상(내 분야 공고): 직무 유형과 '절대 안 봄'(제외 키워드·회사)만으로 정한다. 기업 구분·경력·지역·고용 형태는
# 조건 필터라 보기에서만 거른다(바꾸면 바로 보이게 미리 다 매겨 둠, docs/decisions.md 2026-11-03)
SCOPE_KEYS = ("job_types", "exclude_keywords", "exclude_companies", "always_companies")


def match_scope(user_filters: dict[str, Any]) -> dict[str, Any]:
    return {k: user_filters[k] for k in SCOPE_KEYS if k in user_filters}


def candidates(screen: dict[str, Any], user_filters: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in screen["postings"]:
        if p.get("noise"):
            continue
        c = screen["companies"].get(p["company"]) or {}
        ok, _ = filters.passes(
            title=p["title"], company=c.get("name", ""), company_type=CompanyType(p.get("clientType") or c.get("type", "그 외")),
            career_min=p.get("careerMin"), career_max=p.get("careerMax"), regions=p.get("regions") or [],
            filters=user_filters, job_type=p.get("jobType"), employment=p.get("employment"), job_type2=p.get("jobType2"),
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
    pf = g["posting_facts"]
    facts = {"type": "OBJECT", "required": ["level", "english", "employment"], "properties": {
        "level": {"type": "STRING", "enum": pf["level"]},
        "english": {"type": "STRING", "enum": pf["english"]},
        "employment": {"type": "STRING", "enum": pf["employment"]},
    }}
    return {"type": "OBJECT", "required": ["items", "posting", "reason", "gaps"], "properties": {
        "items": {"type": "ARRAY", "items": item},
        "posting": facts,
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
        "- posting: 공고 사실(level, english, employment). 지원자와 상관없이 공고만 보고 적는다\n"
        "- reason: 이 지원자에게 맞는 이유 한 문장(40자 안쪽, 맞는 점 먼저, 크게 부족한 점이 있으면 뒤에 짧게)\n"
        "- gaps: 크게 부족한 점 최대 3개, 짧게\n\n"
        f"[지원자]\n{profile_text}\n\n[공고]\n{posting_text}"
    )


def verdict(score: int) -> str:
    """최종 점수 구간의 판정 이름(config/match_guide.yaml bands)."""
    g = config.load("match_guide")
    for name, low in sorted(g["bands"].items(), key=lambda x: -x[1]):
        if score >= low:
            return name
    return g["below"]


def adjust(base: int, facts: dict[str, Any] | None, english: str | None,
           employment_types: list[str] | None, has_body: bool = True) -> tuple[int, list[str]]:
    """할 수 없는 공고에만 상한을 건다(영어, 필터에서 못 거른 고용 형태). (최종 점수, 조정 설명).
    취향(원하는 조건)은 점수에 넣지 않는다: want_tags로 표시만 한다(docs/decisions.md 2026-11-02 점수 기준)."""
    facts = facts or {}
    g = config.load("match_guide")["gates"]
    notes: list[str] = []
    score = max(0, min(100, base))
    caps: list[tuple[int, str]] = []
    if english and english in config.load("profile").get("english_low", []) and facts.get("english") == "필요":
        caps.append((g["english_cap"], "영어로 일하는 공고"))
    emp = facts.get("employment")
    if employment_types and emp in ("계약직", "인턴", "기타") and not any(a in emp for a in employment_types):
        caps.append((g["employment_cap"], f"{emp} 공고"))
    if not has_body:
        caps.append((g["no_body_cap"], "본문이 없는 공고"))
    for cap, why in sorted(caps):
        if score > cap:
            notes.append(f"{why}라 최대 {cap}점")
            score = cap
    return score, notes


def want_tags(facts: dict[str, Any] | None, wants: dict[str, Any] | None, industry: str | None = None) -> list[str]:
    """공고 사실이 원하는 조건에 걸리는지(점수는 그대로, 화면에 표시만). 업종은 회사 업종(헤드헌팅은 의뢰 회사
    도메인. screen.py). 없으면 예전 매칭 결과의 AI 업종(지난 id)."""
    facts, wants = facts or {}, wants or {}
    code = taxonomy.industry_code(industry or facts.get("industry"))
    out: list[str] = []
    if code:
        name = taxonomy.industry_name(code)
        if code in {taxonomy.industry_code(w) for w in wants.get("industriesLike") or []}:
            out.append(f"선호 업종 {name}")
        if code in {taxonomy.industry_code(w) for w in wants.get("industriesAvoid") or []}:
            out.append(f"비선호 업종 {name}")
    if wants.get("level") == "실무자" and facts.get("level") == "리더·관리자":
        out.append("리더·관리자 공고")
    return out


def finish(row: dict[str, Any], data: dict[str, Any], user_filters: dict[str, Any],
           industry: str | None = None) -> dict[str, Any]:
    """AI 결과(새로 매겼거나 다시 쓰는 것)에 상한·판정과 원하는 조건 표시를 지금 설정으로 다시 단다."""
    parts = row.get("parts") or {}
    if parts.get("kind") != "ai" or "base" not in parts:
        return row  # v1 결과(공고 사실 없음)는 그대로
    score, notes = adjust(parts["base"], parts.get("posting"), data.get("english"), user_filters.get("employment_types"),
                          has_body=parts.get("body", True))
    tags = want_tags(parts.get("posting"), data.get("wants"), industry)
    return {**row, "score": score, "parts": {**parts, "adjust": notes, "wants": tags, "verdict": verdict(score)}}


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
        years = ", ".join(f"{y.get('area', '')} {y.get('min', '')}{'~' + str(y['max']) if y.get('max') else ''}년"
                          for y in f.get("years") or [])
        duties = [d for d in f.get("duties") or [] if isinstance(d, dict)]
        tags = "; ".join(f"{d.get('text', '')}({names.get(d.get('kind', ''), d.get('kind', ''))}·{d.get('scope', '')})" for d in duties)
        out += ("\n[공고 정리]\n"
                + (f"업무: {tags}\n" if tags else "")
                + (f"사람 관리: {f['manages']} / " if f.get("manages") and f["manages"] != "적혀 있지 않음" else "")
                + f"직급: {f.get('level')} / 필수 스킬: {', '.join(f.get('required_skills') or []) or '-'} / "
                f"우대 스킬: {', '.join(f.get('preferred_skills') or []) or '-'} / 연수 요건: {years or '-'} / "
                f"학력: {f.get('degree') or '-'}"
                f"{' (전공 ' + ', '.join(f.get('majors') or []) + ' ' + (f.get('major_need') or '') + ')' if f.get('majors') else ''}"
                + ("\n업종 경험: " + "; ".join(f"{taxonomy.industry_name(d.get('code'))} {d.get('need', '')}(근거: '{d.get('quote', '')}')"
                                            for d in f["domain_exp"]) if f.get("domain_exp") else ""))
    return out


def sample_ids() -> list[str]:
    """기준 샘플(config/match_sample.yaml) 공고 id."""
    return [p["id"] for p in config.load("match_sample").get("postings") or []]


def run(screen: dict[str, Any], bodies: dict[str, Any], db: Any, client: Any | None, today: date,
        facts: dict[str, dict[str, Any]] | None = None, only: set[str] | None = None,
        max_calls: int | None = None, max_minutes: float | None = None) -> dict[str, Any]:
    """only가 있으면 그 공고(기준 샘플)만 개인 필터와 상관없이 매기고, 그 공고의 줄만 바꾼다."""
    cfg = config.load("ai").get("match") or {}
    guide_v = config.load("match_guide")["version"]
    defaults = config.load("filters")
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    facts = facts or {}
    model = getattr(client, "model", None)
    calls_left = max_calls or cfg.get("max_calls", 330)
    deadline = time.monotonic() + (max_minutes or cfg.get("max_minutes", 35)) * 60

    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    profiles = db.select("profiles", "select=user_id,data,version")
    memos = load_memos(db)
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
        if ptext and memos.get(user):
            ptext += "\n[매칭 메모(평가하며 남긴 말에서 뽑음)]\n" + "\n".join(f"- {line}" for line in memos[user])
        phash = hashlib.sha1(ptext.encode()).hexdigest()[:12] if ptext else None

        scored = []
        pool = ([p for p in screen["postings"] if p["id"] in only] if only is not None
                else candidates(screen, match_scope(user_filters)))
        for p in pool:
            body = texts.get(p["id"])
            rule = matching.score(rule_profile, p, matching.extract_skills(body) if body else None, today)
            scored.append((rule, p))
        # 한도가 모자라면 새 공고부터 AI에 묻는다(아침 알림에 나가는 공고 먼저). 같은 날이면 규칙 점수가 높은 것부터
        scored.sort(key=lambda x: (x[1].get("firstSeen", ""), x[0]["score"], x[1]["id"]), reverse=True)

        old = {r["posting_id"]: r for r in db.select(
            "matches", f"select=posting_id,score,parts,matched,missing,reason,reason_meta,profile_v,score_v&user_id=eq.{user}")}
        rows: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for rule, p in scored:
            o = old.get(p["id"])
            meta = (o or {}).get("reason_meta") or {}
            has_body = len(texts.get(p["id"]) or "") >= bodyread.MIN_TEXT
            # 본문 없이 매긴 공고에 본문이 생기면(본문 읽기) 다시 묻는다. 예전 결과(body 칸 없음)는 본문이 있던 것으로 본다
            same = (o and (o.get("parts") or {}).get("kind") == "ai" and o.get("profile_v") == pv
                    and ((o.get("parts") or {}).get("body", True) or not has_body)
                    and o.get("score_v") == guide_v and meta.get("prompt") == PROMPT_VERSION and meta.get("model") == model
                    and (not phash or meta.get("profile_hash") in (None, phash)))
            row = None
            twin = shared.get((p["id"], phash)) if phash else None
            if twin and not ((twin.get("parts") or {}).get("body", True) or not has_body):
                twin = None
            if same or twin:
                src = o if same else twin
                row = {k: src[k] for k in ("score", "parts", "matched", "missing", "reason", "reason_meta")}
                row["parts"] = {**row["parts"], "rule": rule["score"]}
                row = finish(row, data, user_filters, p.get("industry"))
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
                    base = score_items(items)
                    row = {"score": base,
                           "parts": {"kind": "ai", "items": items, "base": base, "posting": got.get("posting") or {},
                                     "rule": rule["score"], "body": has_body},
                           "matched": [i["name"] for i in items if i.get("fit") == "충족"],
                           "missing": [g for g in got.get("gaps") or [] if g][:3],
                           "reason": reason or None,
                           "reason_meta": {"model": model, "prompt": PROMPT_VERSION, "on": today.isoformat(),
                                           "profile_hash": phash}}
                    shared[(p["id"], phash)] = row
                    row = finish(row, data, user_filters, p.get("industry"))
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
            if row.get("reason_meta") and row["reason_meta"].get("on") == today.isoformat() and summary["calls"]:
                pending.append(rows[-1])
                if len(pending) >= 25:  # 중간 저장: 끝에서 실패해도 새로 매긴 AI 결과는 남는다
                    db.insert("matches", pending)
                    pending = []
        if only is None:
            db.delete("matches", f"user_id=eq.{user}")
        elif rows:
            ids = ",".join(f'"{r["posting_id"]}"' for r in rows)
            db.delete("matches", f"user_id=eq.{user}&posting_id=in.({ids})")
        db.insert("matches", rows)
        summary["rows"] += len(rows)
        log.info("매칭: 공고 %d건(AI 새로 %d, 다시 씀 %d, 규칙만 %d)", len(rows), summary["ai_new"],
                 summary["ai_reused"], summary["rule_only"])
    if not summary["errors"]:
        summary.pop("errors")
    return summary


def load_memos(db: Any) -> dict[str, list[str]]:
    """사람마다 매칭 메모 줄(match_memos 표). 표가 아직 없으면(SQL을 안 돌렸으면) 빈 것."""
    try:
        rows = db.select("match_memos", "select=user_id,memo")
    except Exception as e:  # 표가 없거나 권한이 없으면 메모 없이 매긴다
        log.warning("매칭 메모를 읽지 못함: %s", str(e)[:120])
        return {}
    if not isinstance(rows, list):
        return {}
    return {r["user_id"]: [x for x in (r.get("memo") or {}).get("lines") or [] if x] for r in rows}


def make_client(model: str | None = None) -> Any | None:
    """model을 주면 그 모델로(회차 시험), 없으면 config/ai.yaml match.model, 그것도 없으면 기본 모델."""
    if not ai.configured():
        return None
    return ai.Gemini(model=model or (config.load("ai").get("match") or {}).get("model"))


def stats(screen: dict[str, Any], bodies: dict[str, Any], db: Any, today: date) -> list[str]:
    """시험: 규칙 점수로 AI 매칭 대상을 줄여도 되는지 본다. 로그가 공개라 공고·회사 없이 구간별 건수만 낸다.
    1) 이미 AI로 매긴 공고: 규칙 점수 구간별 AI 판정과 내 평가(○△×) 수
    2) 내 분야 열린 공고 전체(직무 유형만): 규칙 점수 구간별 공고 수 = 구간 아래를 건너뛸 때 줄어드는 양"""
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    defaults = config.load("filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    labels: dict[tuple[str, str], str] = {}
    for r in db.select("feedback", "select=user_id,posting_id,label&order=updated_at"):
        labels[(r["user_id"], r["posting_id"])] = r["label"]
    out: list[str] = []
    n_user = 0
    for prof in db.select("profiles", "select=user_id,data,version"):
        user, data = prof["user_id"], prof.get("data") or {}
        if not profile.has_content(data):
            continue
        n_user += 1
        rp = profile.rule_view(data)
        jobs = {**defaults, **settings.get(user, {})}.get("job_types")
        mine = candidates(screen, {"job_types": jobs})
        rule = {}
        for p in mine:
            body = texts.get(p["id"])
            rule[p["id"]] = matching.score(rp, p, matching.extract_skills(body) if body else None, today)["score"]
        band = lambda s: min(int(s) // 10 * 10, 90)  # noqa: E731
        ai = [r for r in db.select("matches", f"select=posting_id,score,parts&user_id=eq.{user}")
              if (r.get("parts") or {}).get("kind") == "ai"]
        out.append(f"사람 {n_user}: 내 분야 열린 공고 {len(mine)}, AI로 매긴 공고 {len(ai)}")
        out.append("규칙 구간 | 내 분야 공고(누적: 이 구간 미만) | AI 매김: 지원 추천/고려/비추천 | AI 80+ | 내 평가 ○/△/×")
        below = 0
        for b in range(0, 100, 10):
            n = sum(1 for s in rule.values() if band(s) == b)
            got = [r for r in ai if band((r["parts"] or {}).get("rule", 0) or 0) == b]
            v = Counter((r["parts"] or {}).get("verdict") for r in got)
            hi = sum(1 for r in got if (r.get("score") or 0) >= 80)
            lab = Counter(labels.get((user, r["posting_id"])) for r in got)
            out.append(f"{b:>2}~{b + 9:<2} | {n:>4} (누적 {below:>4}) | {v.get('지원 추천', 0)}/{v.get('고려', 0)}/"
                       f"{v.get('비추천', 0)} | {hi} | {lab.get('good', 0)}/{lab.get('maybe', 0)}/{lab.get('bad', 0)}")
            below += n
    return out
