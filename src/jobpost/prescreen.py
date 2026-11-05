"""사전 거르기(시험 중, 2026-11-03): AI 매칭 비용을 줄이려고 '명백히 안 맞는' 내 분야 공고를 매칭 전에 뺀다.

후보 세 가지를 같은 정답(내 평가 ○△×, AI 매칭 판정)으로 견준다(docs/content-rules.md 매칭, 기획 문서 '매칭 방식 비교').
- 조건: 경력 겹침 + 고용 형태(조건 필터 값)
- 규칙 v3(rule_v3): 공고 정리(AI가 공고마다 1번 뽑은 항목)와 프로필 v2를 코드로 맞대어 0~100. AI 호출 없음
- AI 묶음(ai_batch): 30건씩 제목·공고 정리만 보여 주고 '명백히 안 맞음'만 고르게 함. 공고 30건에 1번

규칙 v3 배점(지금 규칙 v2와 달리 내 분야 안에서 공짜 점수가 없다. 2026-11-03 공고 정리 v2에 맞춰 업무 부분을 더함):
- 업무 20: 공고 정리 v2의 업무마다 일의 종류(직무 유형)를 내가 해 본 연수와 비교. 1년 이상 → 1, 가까운 직무(matching.yaml related)
  → 0.5, 없음 → 0. 책임 범위가 총괄·결정인데 그 직무에서 리드·단독 프로젝트가 없으면 절반. 업무 평균(v1 공고 정리면 0.5, 모름)
- 필수 스킬 30: 공고 필수 스킬(사전에 있는 것, 바꿔 쓸 수 있는 묶음은 하나)마다 내 숙련도
  3·4 → 1, 2 → 0.7, 1 → 0.3, 없음 → 0의 평균. 필수가 없으면 우대 스킬로, 그것도 없으면 0.5(모름)
- 연수 20: 공고 연수 요건(영역별 최소)마다 그 영역 내 연수와 비교. 모자람 0 → 1, 1년 → 0.7, 2년 → 0.4, 3년 이상 → 0.
  여러 요건이면 가장 낮은 것. 요건이 없으면 공고 경력 하한으로. 상한(max)보다 3년 넘게 많으면 0.5를 곱한다
- 직급 15: 공고 직급이 주니어인데 내 데이터 경력 7년 이상 → 0, 미들 → 0.6, 시니어·리드 → 1. 적혀 있지 않으면
  공고 경력 상한보다 3년 넘게 많을 때 0.3, 아니면 1. 사람 관리(팀장) 자리인데 내 프로젝트에 리드가 없으면 0.3
- 도메인 10: 공고가 특정 업종 경험을 필수로 하면 내 경력 업종에 있을 때만 1
- 학력 5: 공고가 석사·박사를 적으면 내 학력이 그 이상일 때만 1
공고 정리가 없는 공고는 점수를 내지 않는다(None, 거르지 않음).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any

from . import config, matching, profile, taxonomy
from . import facts as facts_mod

log = logging.getLogger(__name__)

RULE_V = 3
WEIGHTS = {"duties": 20, "skills": 30, "years": 20, "level": 15, "domain": 10, "degree": 5}
LEAD_PARTS = {"리드", "단독"}
LEVEL_FIT = {4: 1.0, 3: 1.0, 2: 0.7, 1: 0.3}
DEGREE_RANK = {"고졸": 0, "전문학사": 1, "학사": 2, "석사": 3, "박사": 4}
# 공고 연수 요건의 영역 글 → 프로필 직무 id(이 직무들의 연수를 더한다). 맞는 말이 없으면 데이터 경력 전체
AREA_ROLES = [
    (("아키텍", "거버넌스", "모델링", "DA"), ("data_arch", "data_eng")),
    (("분석", "BI", "애널리", "Analytics"), ("analyst", "bi_eng", "data_eng")),
    (("ML", "머신러닝", "MLOps", "모델 서빙", "AI 플랫폼"), ("mlops", "ai_eng")),
    (("AI", "LLM", "에이전트", "생성형"), ("ai_eng", "mlops")),
    (("데이터", "Data", "ETL", "파이프라인"), ("data_eng", "data_arch", "bi_eng", "analyst", "mlops", "ai_eng")),
]


def _role_years(data: dict[str, Any], today: date) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in data.get("careers") or []:
        for r in c.get("roles") or []:
            out[r.get("role", "")] = out.get(r.get("role", ""), 0) + profile.months(r.get("start"), r.get("end"), today) / 12
    return out


def _job_years(data: dict[str, Any], today: date) -> tuple[dict[str, float], set[str]]:
    """(직무 유형별 내 연수, 리드·단독 프로젝트가 있는 직무 유형). 프로필 직무 id를 직무 유형으로(config/profile.yaml roles job_type)."""
    to_job = {r["id"]: r.get("job_type", r["id"]) for r in config.load("profile")["roles"]}
    years: dict[str, float] = {}
    lead: set[str] = set()
    for c in data.get("careers") or []:
        for r in c.get("roles") or []:
            j = to_job.get(r.get("role", ""), r.get("role", ""))
            years[j] = years.get(j, 0) + profile.months(r.get("start"), r.get("end"), today) / 12
            if any((pj.get("part") or "") in LEAD_PARTS for pj in r.get("projects") or []):
                lead.add(j)
    return years, lead


def _years_for(area: str, ry: dict[str, float], total: float, data_years: float) -> float:
    if "총" in area or not area.strip():
        return total
    for words, roles in AREA_ROLES:
        if any(w.lower() in area.lower() for w in words):
            return sum(ry.get(r, 0) for r in roles)
    return data_years


def _short_fit(short: float) -> float:
    return 1.0 if short <= 0 else 0.7 if short <= 1 else 0.4 if short <= 2 else 0.0


def _skill_fit(names: list[str], mine: dict[str, int]) -> float | None:
    found = matching.extract_skills(" , ".join(names))
    if not found:
        return None
    groups = [set(g) for g in config.load("skills").get("interchangeable") or []]
    fits = []
    for members in matching._collapse(found).values():
        group = next((g for g in groups if members & g), None)
        pool = group or members
        best = max((mine.get(s, 0) for s in pool), default=0)
        fits.append(LEVEL_FIT.get(best, 0.0))
    return sum(fits) / len(fits)


def rule_v3(data: dict[str, Any], posting: dict[str, Any], fact: dict[str, Any] | None, today: date) -> dict[str, Any] | None:
    """{score, parts(부분별 0~1), why(낮은 부분)} 또는 None(공고 정리 없음)."""
    if not fact:
        return None
    f = fact.get("facts") or fact
    mine: dict[str, int] = {}
    for s in data.get("skills") or []:
        for name in matching.extract_skills(s.get("name", "")):
            mine[name] = max(mine.get(name, 0), int(s.get("level") or 1))
    total, data_years = profile.career_totals(data, today)
    ry = _role_years(data, today)
    jy, lead = _job_years(data, today)
    related = config.load("matching").get("related") or {}

    duty_fits = []
    for d in f.get("duties") or []:
        if not isinstance(d, dict) or not d.get("kind"):
            continue
        k = d["kind"]
        fit = 1.0 if jy.get(k, 0) >= 1 else 0.5 if any(jy.get(r, 0) >= 1 for r in related.get(k) or []) else 0.0
        if d.get("scope") == "총괄·결정" and k not in lead:
            fit /= 2
        duty_fits.append(fit)
    duties = sum(duty_fits) / len(duty_fits) if duty_fits else 0.5

    skills = _skill_fit(f.get("required_skills") or [], mine)
    if skills is None:
        skills = _skill_fit(f.get("preferred_skills") or [], mine)
    skills = 0.5 if skills is None else skills

    reqs = [y for y in f.get("years") or [] if isinstance(y.get("min"), int) and y["min"] > 0]
    if reqs:
        years = min(_short_fit(y["min"] - _years_for(y.get("area") or "", ry, total, data_years)) for y in reqs)
        if any(isinstance(y.get("max"), int) and y["max"] > 0
               and _years_for(y.get("area") or "", ry, total, data_years) > y["max"] + 3 for y in reqs):
            years *= 0.5
    elif posting.get("careerMin"):
        years = _short_fit(posting["careerMin"] - data_years)
    else:
        years = 1.0

    lv = f.get("level")
    cmax = posting.get("careerMax")
    if lv == "주니어":
        level = 0.0 if data_years >= 7 else 0.6
    elif lv == "미들":
        level = 0.6 if data_years >= 7 else 1.0
    elif lv in ("시니어", "리드·매니저"):
        level = 1.0
    else:
        level = 0.3 if cmax and data_years > cmax + 3 else 1.0
    if f.get("manages") == "팀장(사람 관리)" and not lead:
        level = min(level, 0.3)

    # 필수 업종 경험: 같은 중분류 또는 대분류 요구 아래면 충족, 같은 대분류면 일부(taxonomy.industry_fit). 여럿이면 하나만 맞아도
    need = f.get("domain_required") or []
    mine_ind = {c.get("industry") for c in data.get("careers") or [] if c.get("industry")}
    domain = max((taxonomy.industry_fit(n, mine_ind) for n in need), default=1.0)

    want = DEGREE_RANK.get(f.get("degree") or "", -1)
    have = DEGREE_RANK.get(((data.get("education") or {}).get("degree")) or "", 2)
    degree = 1.0 if want < 3 or have >= want else 0.0

    parts = {"duties": duties, "skills": skills, "years": years, "level": level, "domain": domain, "degree": degree}
    score = round(sum(WEIGHTS[k] * v for k, v in parts.items()))
    why = [k for k, v in parts.items() if v < 0.5]
    return {"score": score, "parts": {k: round(v, 2) for k, v in parts.items()}, "why": why, "v": RULE_V}


# ---------- AI 묶음 거르기 ----------

BATCH = 30


def batch_prompt(ptext: str, lines: list[str]) -> str:
    return (
        "지원자 요약과 채용공고 목록이다. 각 공고가 이 지원자에게 '명백히 안 맞는지'만 가른다.\n"
        "명백히 안 맞음: 핵심 업무 분야가 지원자 경력과 전혀 다름, 요구 연차·직급이 크게 어긋남(예: 신입·주니어 공고에 10년차, "
        "15년 이상 임원급에 5년차), 필수 학위·필수 업종 경험이 없음. 애매하면 남긴다(drop false). 취향은 판단하지 않는다.\n"
        "공고마다 i(번호), drop(true/false), why(drop이면 15자 안쪽 이유)를 낸다.\n\n"
        f"[지원자]\n{ptext}\n\n[공고]\n" + "\n".join(lines)
    )


def batch_schema() -> dict[str, Any]:
    return {"type": "OBJECT", "required": ["rows"], "properties": {"rows": {"type": "ARRAY", "items": {
        "type": "OBJECT", "required": ["i", "drop"], "properties": {
            "i": {"type": "INTEGER"}, "drop": {"type": "BOOLEAN"}, "why": {"type": "STRING"}}}}}}


def batch_line(i: int, p: dict[str, Any], fact: dict[str, Any] | None) -> str:
    out = f"{i}. {p['title']} | {p.get('career', '')}"
    if fact:
        f = fact.get("facts") or fact
        years = ", ".join(f"{y.get('area', '')} {y.get('min', '')}년" for y in f.get("years") or [])
        out += (f" | 직급 {f.get('level')} | 업무 {'; '.join(facts_mod.duty_texts(f)[:3])} | "
                f"필수 {', '.join((f.get('required_skills') or [])[:8]) or '-'} | 연수 {years or '-'} | 학력 {f.get('degree') or '-'}")
    return out


def ai_batch(client: Any, ptext: str, postings: list[dict[str, Any]], facts: dict[str, Any]) -> dict[str, bool]:
    """{공고 id: drop}. 실패한 묶음은 남긴다(drop False)."""
    out: dict[str, bool] = {}
    for start in range(0, len(postings), BATCH):
        chunk = postings[start:start + BATCH]
        lines = [batch_line(i + 1, p, facts.get(p["id"])) for i, p in enumerate(chunk)]
        try:
            got = client.json(batch_prompt(ptext, lines), batch_schema())
            drops = {r["i"] for r in got.get("rows") or [] if r.get("drop")}
        except Exception as e:  # noqa: BLE001 - 실패하면 거르지 않는다
            log.warning("AI 묶음 거르기 실패: %s", str(e)[:120])
            drops = set()
        for i, p in enumerate(chunk):
            out[p["id"]] = (i + 1) in drops
    return out


# ---------- 시험 ----------

def _line(name: str, drop: set[str], base: list[dict[str, Any]], truth: tuple[set[str], set[str], set[str]]) -> str:
    good, rec, bad = truth
    n = len(base)
    d = sum(1 for p in base if p["id"] in drop)
    return (f"{name} | 줄임 {d}/{n} ({d * 100 // max(n, 1)}%) | 잃은 ○ {len(good & drop)}/{len(good)} | "
            f"잃은 AI 지원 추천 {len(rec & drop)}/{len(rec)} | 걸러진 × {len(bad & drop)}/{len(bad)}")


def trial(screen: dict[str, Any], bodies: dict[str, Any], facts: dict[str, Any], db: Any, client: Any | None,
          today: date, ai_sample: int = 300) -> list[str]:
    """방식마다 내 분야 열린 공고를 얼마나 줄이는지와, 정답(내 평가 ○, AI '지원 추천')을 얼마나 잃는지. 건수만 낸다."""
    from . import recommend

    defaults = config.load("filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    labels: dict[tuple[str, str], str] = {}
    for r in db.select("feedback", "select=user_id,posting_id,label&order=updated_at"):
        labels[(r["user_id"], r["posting_id"])] = r["label"]
    out: list[str] = []
    for prof in db.select("profiles", "select=user_id,data,version"):
        user, data = prof["user_id"], prof.get("data") or {}
        if not profile.is_v2(data) or not profile.has_content(data):
            continue
        f = {**defaults, **settings.get(user, {})}
        mine = recommend.candidates(screen, recommend.match_scope(f))
        by_id = {p["id"]: p for p in screen["postings"]}
        verdict = {r["posting_id"]: (r.get("parts") or {}).get("verdict")
                   for r in db.select("matches", f"select=posting_id,parts&user_id=eq.{user}")
                   if (r.get("parts") or {}).get("kind") == "ai"}
        ids = {p["id"] for p in mine}
        rated = {pid: lab for (u, pid), lab in labels.items() if u == user and pid in ids}
        truth_good = {pid for pid, lab in rated.items() if lab == "good"}
        truth_bad = {pid for pid, lab in rated.items() if lab == "bad"}
        truth_rec = {pid for pid, v in verdict.items() if v == "지원 추천" and pid in ids}
        rp = profile.rule_view(data)
        texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}

        cond = {k: f[k] for k in ("career", "employment_types") if f.get(k)}
        keep_cond = {p["id"] for p in recommend.candidates(screen, {**recommend.match_scope(f), **cond})}
        v2 = {p["id"]: matching.score(rp, p, matching.extract_skills(texts[p["id"]]) if texts.get(p["id"]) else None,
                                      today)["score"] for p in mine}
        v3 = {p["id"]: rule_v3(data, p, facts.get(p["id"]), today) for p in mine}
        have_facts = sum(1 for p in mine if v3.get(p["id"]))

        truth = (truth_good, truth_rec, truth_bad)

        out.append(f"내 분야 열린 공고 {len(mine)}(공고 정리 있음 {have_facts}) · 정답: 내 평가 ○ {len(truth_good)} "
                   f"△ {sum(1 for v in rated.values() if v == 'maybe')} × {len(truth_bad)} · AI 지원 추천 {len(truth_rec)}")
        out.append("방식 | 내 분야에서 줄인 양 | 정답을 잃은 수(적을수록 좋음) | ×를 거른 수(많을수록 좋음)")
        out.append(_line("조건(경력·고용 형태)", ids - keep_cond, mine, truth))
        out.append(_line("규칙 v2 70점 미만", {pid for pid, s in v2.items() if s < 70}, mine, truth))
        for t in (30, 40, 50, 60):
            out.append(_line(f"규칙 v3 {t}점 미만", {pid for pid, r in v3.items() if r and r["score"] < t}, mine, truth))
        # 규칙 v3에서 낮게 나온 부분(×를 거른 근거가 무엇인지)
        whys = Counter(w for pid in truth_bad | truth_good for w in (v3.get(pid) or {}).get("why", []))
        out.append("규칙 v3 낮은 부분(정답 공고에서): " + ", ".join(f"{k} {v}" for k, v in whys.most_common()))

        if client is not None:
            ptext = profile.text(data, today)
            known = truth_good | truth_bad | truth_rec | set(rated)
            sample = ([by_id[pid] for pid in sorted(known)]
                      + [p for p in mine if p["id"] not in known][:max(0, ai_sample - len(known))])
            drops = ai_batch(client, ptext, sample, facts)
            dropped = {pid for pid, d in drops.items() if d}
            calls = (len(sample) + BATCH - 1) // BATCH
            out.append(_line(f"AI 묶음({len(sample)}건 시험, 호출 {calls}번)", dropped, sample, truth))
    return out
