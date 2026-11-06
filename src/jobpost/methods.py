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


def _ptext(data: dict[str, Any], memo: list[str] | None, today: Any) -> str:
    from . import profile
    ptext = profile.text(data, today)
    if memo:
        ptext += "\n[매칭 메모(평가하며 남긴 말에서 뽑음)]\n" + "\n".join(f"- {line}" for line in memo)
    return ptext


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def run_e(client: Any, ptext: str, ptxts: dict[str, str]) -> dict[str, int]:
    """E 임베딩 유사도: 공고 글과 지원자 요약의 의미가 얼마나 가까운지. 판단 문장 없음.
    유사도를 샘플 안 순위(0~100)로 바꿔 다른 방식과 같은 점수 구간으로 본다."""
    ids = list(ptxts)
    vecs = client.embed([ptext] + [ptxts[i] for i in ids])
    sim = {pid: _cos(vecs[0], v) for pid, v in zip(ids, vecs[1:], strict=True)}
    ranked = sorted(ids, key=lambda pid: sim[pid])
    n = max(len(ranked) - 1, 1)
    return {pid: round(100 * k / n) for k, pid in enumerate(ranked)}


SAVE_NAME = "trials/methods.json.gz"  # 비공개 저장소(사람별 점수라 공개 레포·로그에 두지 않는다)


def score_sample(screen: dict[str, Any], bodies: dict[str, Any], facts: dict[str, Any], db: Any, client: Any,
                 today: Any, methods: str = "BCDE", rounds: int = 2) -> tuple[dict[str, Any], list[str]]:
    """기준 샘플 공고 전부(평가 여부와 상관없이)를 방식마다 rounds번 매긴다. 평가 뒤에는 evaluate로 AI 없이 잰다.
    돌려주는 값: ({user_id: {방식: [{공고 id: 점수}, …회차]}}, 건수만 담은 로그 줄)."""
    cfg = config.load("ai").get("match") or {}
    texts = {pid: b["text"] for pid, b in bodies["bodies"].items()}
    by_id = {p["id"]: p for p in screen["postings"]}
    ids = [pid for pid in recommend.sample_ids() if pid in by_id]
    memos = recommend.load_memos(db)
    from . import profile

    saved: dict[str, Any] = {}
    out: list[str] = []
    for prof in db.select("profiles", "select=user_id,data,version"):
        user, data = prof["user_id"], prof.get("data") or {}
        if not profile.is_v2(data) or not profile.has_content(data):
            continue
        ptext = _ptext(data, memos.get(user), today)
        ptxts = {pid: recommend.posting_text(by_id[pid], screen, texts.get(pid), facts.get(pid), cfg.get("body_chars", 3000))
                 for pid in ids}
        mine: dict[str, list[dict[str, int | None]]] = {}
        calls = errors = 0
        for m in methods:
            mine[m] = []
            for _ in range(1 if m == "E" else rounds):  # 임베딩은 같은 글이면 같은 값이라 한 번
                got: dict[str, int | None] = {}
                if m == "E":
                    try:
                        got = dict(run_e(client, ptext, ptxts))
                    except Exception as e:  # noqa: BLE001
                        log.warning("방식 E 실패: %s", str(e)[:120])
                        errors += 1
                    mine[m].append(got)
                    continue
                for pid in ids:
                    try:
                        calls += 1
                        got[pid] = (run_b(client, ptext, ptxts[pid], facts.get(pid)) if m == "B"
                                    else run_c(client, ptext, ptxts[pid], facts.get(pid)) if m == "C"
                                    else run_d(client, ptext, ptxts[pid]))
                    except Exception as e:  # noqa: BLE001 - 한 건 실패는 점수 없음으로
                        log.warning("방식 %s 실패: %s", m, str(e)[:120])
                        errors += 1
                        got[pid] = None
                mine[m].append(got)
        saved[user] = mine
        out.append(f"기준 샘플 {len(ids)}건 · 방식 {methods} · 회차 {rounds} · AI 호출 {calls}번 · 실패 {errors}건")
    return {"date": str(today), "methods": methods, "rounds": rounds, "users": saved}, out


def _stability(runs: list[dict[str, int | None]]) -> str:
    """같은 공고를 두 번 매긴 점수 차이(평균, 10점 넘게 다른 비율, 판정 구간이 바뀐 비율)."""
    if len(runs) < 2:
        return "    흔들림 -(한 번만 매김)"
    from . import feedback
    hi, lo = feedback._bands()
    both = [(runs[0][p], runs[1].get(p)) for p in runs[0] if runs[0][p] is not None and runs[1].get(p) is not None]
    if not both:
        return "    흔들림 -"
    band = lambda s: 2 if s >= hi else 1 if s >= lo else 0  # noqa: E731
    diff = [abs(a - b) for a, b in both]
    return (f"    흔들림: 평균 {sum(diff) / len(diff):.1f}점, 10점 넘게 다름 {sum(d > 10 for d in diff) * 100 // len(diff)}%, "
            f"구간 바뀜 {sum(band(a) != band(b) for a, b in both) * 100 // len(both)}% ({len(both)}건)")


def evaluate(screen: dict[str, Any], db: Any, saved: dict[str, Any]) -> list[str]:
    """저장된 점수(score_sample)와 내 평가를 맞대 지표만 낸다. AI를 부르지 않는다.
    A(지금 매칭)는 matches의 상한 전 점수. 내 분야에서 빠진 평가 공고(업무가 다른 분야 등)도 센다."""
    from . import feedback

    labels_all: dict[tuple[str, str], str] = {}
    for r in db.select("feedback", "select=user_id,posting_id,label&order=updated_at"):
        labels_all[(r["user_id"], r["posting_id"])] = r["label"]
    sample = set(recommend.sample_ids())
    defaults = config.load("filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    out: list[str] = [f"저장한 점수: {saved.get('date')} · 방식 {saved.get('methods')} · 회차 {saved.get('rounds')}"]
    for user, mine in (saved.get("users") or {}).items():
        labels = {pid: lab for (u, pid), lab in labels_all.items() if u == user and pid in sample}
        rated = sorted(labels)
        n = {k: sum(1 for p in rated if labels[p] == k) for k in feedback.LABELS}
        out.append(f"평가한 기준 샘플 {len(rated)}건(○ {n['good']} △ {n['maybe']} × {n['bad']})")
        scope = recommend.match_scope({**defaults, **settings.get(user, {})})
        inside = {p["id"] for p in recommend.candidates(screen, scope)}
        open_ids = {p["id"] for p in screen["postings"]}
        gone = [p for p in rated if p in open_ids and p not in inside]
        out.append("  내 분야에서 빠진 평가 공고: " + " ".join(f"{mark} {sum(1 for p in gone if labels[p] == k)}"
                                                    for k, mark in feedback.LABELS.items()))
        a = {r["posting_id"]: (r.get("parts") or {}).get("base")
             for r in db.select("matches", f"select=posting_id,parts&user_id=eq.{user}")
             if (r.get("parts") or {}).get("kind") == "ai"}
        table = {"A": [{p: a.get(p) for p in rated}], **mine}
        for m, runs in table.items():
            for k, run in enumerate(runs):
                got = {p: s for p, s in run.items() if s is not None and p in labels}
                conc = concordance({p: labels[p] for p in got}, got)
                top = sorted(got, key=lambda p: -got[p])[:10]
                name = f"{m} 방식" + (f" {k + 1}회" if len(runs) > 1 else "")
                out.append(feedback._metric_line(name, feedback.metrics(list(got), labels, lambda pid, sc=got: sc.get(pid))))
                out.append(f"    순서 맞음 {conc:.0%} · 상위 10 중 ○ {sum(labels[p] == 'good' for p in top)}"
                           if conc is not None else "    순서 맞음 -")
            if m != "A":
                out.append(_stability(runs))
    return out
