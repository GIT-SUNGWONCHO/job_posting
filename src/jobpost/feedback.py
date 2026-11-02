"""회차 리포트: 기준 샘플(config/match_sample.yaml)에서 지금 매칭 결과를 내 평가와 비교한다.

내 평가는 공고에 대한 판단이라 회차와 상관없이 공고별 가장 최근 것을 정답으로 쓴다.
지표는 점수 구간으로 잰다(docs/decisions.md 2026-11-02, 구간은 config/match_guide.yaml bands): 80점 이상에 × 0건이고
○가 절반 이상, 60점 미만에 ○ 0건. 공고가 적은 날도 기준이 같도록 등수가 아니라 점수로 본다. 규칙 점수도 같은 잣대로 잰다.
평가 코멘트에서 지원자에 대한 메모(경험·역량의 한계와 강점)를 AI로 뽑아 match_memos 표에 둔다(memo_lines).
매칭이 지원자 요약 끝에 붙여 쓴다. 화면에는 보이지 않는다.

레포가 공개라 실행 로그도 공개다. 로그에는 건수와 지표만 남기고(private=False), 공고별 평가·코멘트·판단 근거
(프로필에서 나온 "나:" 문장)·바꿀 후보는 비공개 리포트로 따로 만들어 암호화한다(.github/workflows/feedback.yml).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from . import config

LABELS = {"good": "○", "maybe": "△", "bad": "×"}
GOALS = {"high_bad": 0, "high_good": 0.5, "low_good": 0}  # 80점 이상 × 수, 80점 이상 ○ 비율, 60점 미만 ○ 수


def _bands() -> tuple[int, int]:
    b = config.load("match_guide")["bands"]
    return max(b.values()), min(b.values())


def metrics(rated: list[str], labels: dict[str, str], score: Callable[[str], float | None]) -> dict[str, Any]:
    """평가한 공고를 점수 구간(높음·중간·낮음)으로 나눠 구간마다 ○△× 수를 센다. 점수가 없는 공고는 뺀다."""
    hi, lo = _bands()
    have = [pid for pid in rated if score(pid) is not None]
    band = {pid: "high" if score(pid) >= hi else "mid" if score(pid) >= lo else "low" for pid in have}  # type: ignore[operator]
    out: dict[str, Any] = {"n": len(have)}
    for b in ("high", "mid", "low"):
        out[b] = {k: sum(1 for p in have if band[p] == b and labels[p] == k) for k in LABELS}
    return out


def _metric_line(name: str, m: dict[str, Any]) -> str:
    hi, lo = _bands()
    h, low = m["high"], m["low"]
    n_high = sum(h.values())
    good_share = h["good"] / n_high if n_high else None
    ok = (h["bad"] <= GOALS["high_bad"] and good_share is not None and good_share >= GOALS["high_good"]
          and low["good"] <= GOALS["low_good"])
    cell = lambda c: " ".join(f"{mark} {c[k]}" for k, mark in LABELS.items())  # noqa: E731
    return (f"  {name}: {hi}점 이상 {n_high}건({cell(h)}), {lo}~{hi - 1}점 {sum(m['mid'].values())}건({cell(m['mid'])}), "
            f"{lo}점 미만 {sum(low.values())}건({cell(low)}) → 목표({hi}점 이상 × 0·○ 절반 이상, {lo}점 미만 ○ 0) "
            f"{'달성' if ok else '미달'} [평가·점수 있는 {m['n']}건 기준]")


def report(sample: list[dict[str, Any]], matches: list[dict[str, Any]], rows: list[dict[str, Any]],
           private: bool = True) -> list[str]:
    """sample: 기준 샘플 공고, matches: 그 공고들의 지금 매칭 결과, rows: feedback 표(updated_at 오름차순).
    private=False면 건수·지표만(공개 로그용). 공고별 줄, 코멘트, 판단 근거는 private=True일 때만."""
    info = {p["id"]: p for p in sample}
    ids = list(info)
    out: list[str] = []
    for user in sorted({m["user_id"] for m in matches} | {r["user_id"] for r in rows}):
        labels: dict[str, str] = {}
        comments: dict[str, str] = {}
        for r in rows:
            if r["user_id"] == user and r["posting_id"] in info:
                labels[r["posting_id"]] = r["label"]  # 뒤가 최신
                if r.get("comment"):
                    comments[r["posting_id"]] = r["comment"]
        ms = {m["posting_id"]: m for m in matches if m["user_id"] == user}
        rated = [pid for pid in ids if pid in labels]
        ai = [m for m in ms.values() if (m.get("parts") or {}).get("kind") == "ai"]
        rounds = sorted({f"지침 v{m.get('score_v')} · {(m.get('reason_meta') or {}).get('model')}" for m in ai})
        out.append(f"== 사용자 {user[:8]}: 기준 샘플 {len(ids)}건 중 평가 {len(rated)}건 "
                   + " ".join(f"{mark} {sum(1 for p in rated if labels[p] == k)}" for k, mark in LABELS.items())
                   + f", AI 결과 {len(ai)}건 ({', '.join(rounds) or '없음'})")

        def ai_score(pid: str, ms: dict[str, dict[str, Any]] = ms) -> float | None:
            m = ms.get(pid)
            return m["score"] if m and (m.get("parts") or {}).get("kind") == "ai" else None

        def rule_score(pid: str, ms: dict[str, dict[str, Any]] = ms) -> float | None:
            m = ms.get(pid)
            return (m.get("parts") or {}).get("rule") if m else None

        out.append(_metric_line("AI 점수", metrics(rated, labels, ai_score)))
        out.append(_metric_line("규칙 점수", metrics(rated, labels, rule_score)))

        out.append("  [항목 종류별 가중치 평균 / 충족 비율: ○ vs ×]")
        kinds = sorted({i.get("kind") for m in ai for i in (m.get("parts") or {}).get("items") or []} - {None})
        for kind in kinds:
            cells = []
            for k in ("good", "bad"):
                its = [i for pid in rated if labels[pid] == k and ms.get(pid)
                       for i in (ms[pid].get("parts") or {}).get("items") or [] if i.get("kind") == kind]
                weight = f"{sum(i.get('weight') or 0 for i in its) / len(its):.0f}" if its else "-"
                fit = f"{sum(1 for i in its if i.get('fit') == '충족') * 100 // len(its)}%" if its else "-"
                cells.append(f"{weight}/{fit}")
            out.append(f"    {kind}: ○ {cells[0]}  × {cells[1]}")

        if not private:
            out.append(f"  [아직 평가 안 함 {sum(1 for pid in ids if pid not in labels)}건]")
            continue
        hi, lo = _bands()
        out.append(f"  [점수와 내 평가가 어긋난 공고: ○인데 {lo}점 미만, ×인데 {hi}점 이상]")
        for pid in rated:
            s = ai_score(pid)
            if s is None or not ((labels[pid] == "good" and s < lo) or (labels[pid] == "bad" and s >= hi)):
                continue
            out.append("    " + _line(pid, info, labels, comments, ms))
            parts = ms[pid].get("parts") or {}
            if parts.get("posting") or parts.get("adjust"):
                out.append(f"      · 공고 사실 {parts.get('posting')} | 조정 {parts.get('adjust') or '-'} | 조정 전 {parts.get('base')}")
            for i in (ms[pid].get("parts") or {}).get("items") or []:
                out.append(f"      - {i.get('kind')} {i.get('weight')} {i.get('fit')} | {i.get('name')} | "
                           f"공고: {i.get('posting')} | 나: {i.get('me')}")
        out.append("  [코멘트]")
        for pid in rated:
            if pid in comments:
                out.append("    " + _line(pid, info, labels, comments, ms))
        unrated = [pid for pid in ids if pid not in labels]
        out.append(f"  [아직 평가 안 함 {len(unrated)}건]")
    return out or ["매칭 결과와 평가가 아직 없다"]


def _line(pid: str, info: dict[str, Any], labels: dict[str, str], comments: dict[str, str],
          ms: dict[str, dict[str, Any]]) -> str:
    m = ms.get(pid) or {}
    parts = m.get("parts") or {}
    return (f"{LABELS[labels[pid]]} AI {m.get('score') if parts.get('kind') == 'ai' else '-'}({parts.get('verdict') or '-'}) "
            f"규칙 {parts.get('rule')} | {info[pid]['company']} | {info[pid]['title'][:40]} | 코멘트: {comments.get(pid, '-')}")


def sample_dump(sample: list[dict[str, Any]], matches: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[str]:
    """기준 샘플 공고마다 한 줄 JSON(SMP\t...): 점수, 판정, 이유, 판단 근거, 내 최신 평가. 대화에서 함께 평가할 때 쓴다."""
    labels = {(r["user_id"], r["posting_id"]): (r["label"], r.get("comment")) for r in rows}  # 뒤가 최신
    out = []
    for m in sorted(matches, key=lambda m: (m["user_id"], -(m.get("score") or 0))):
        p = next((x for x in sample if x["id"] == m["posting_id"]), None)
        if not p:
            continue
        parts = m.get("parts") or {}
        label = labels.get((m["user_id"], m["posting_id"]))
        out.append("SMP\t" + json.dumps({
            "user": m["user_id"][:8], "id": p["id"], "group": p.get("group"), "company": p.get("company"),
            "title": p.get("title"), "url": p.get("url"), "kind": parts.get("kind"), "score": m.get("score"),
            "verdict": parts.get("verdict"), "rule": parts.get("rule"), "reason": m.get("reason"),
            "gaps": m.get("missing") or [], "items": parts.get("items") or [],
            "label": label[0] if label else None, "comment": label[1] if label else None,
        }, ensure_ascii=False))
    return out


def _order(pid: str, seed: str) -> str:
    return hashlib.sha1(f"{seed}:{pid}".encode()).hexdigest()


def candidates(sample: list[dict[str, Any]], open_postings: list[dict[str, Any]], names: dict[str, str],
               rows: list[dict[str, Any]], seed: str = "sample", n: int = 15) -> list[str]:
    """기준 샘플에서 마감된 공고를 바꿀 후보(비공개 리포트에만). 한 줄 JSON(CAND\t...).
    open_postings: 열린 공고(화면용 파일), rows: 사람별 지금 매칭 줄 {user_id, posting_id, score, rule, kind}.
    매칭 줄이 있는 공고 = 그 사람의 개인 필터를 통과한 후보다. 묶음은 match_sample.yaml과 같다."""
    in_sample = {p["id"] for p in sample}
    titles = {p["id"]: p["title"] for p in sample}
    by_id = {p["id"]: p for p in open_postings}
    closed = [p for p in sample if p["id"] not in by_id]
    out: list[str] = []
    for user in sorted({r["user_id"] for r in rows}):
        pool = [r for r in rows if r["user_id"] == user and r["posting_id"] in by_id and r["posting_id"] not in in_sample
                and by_id[r["posting_id"]]["title"] not in titles.values()]

        def line(group: str, r: dict[str, Any], user: str = user) -> str:
            p = by_id[r["posting_id"]]
            return "CAND\t" + json.dumps({
                "user": user[:8], "group": group, "id": p["id"], "company": names.get(p["company"], p["company"]),
                "title": p["title"], "jobType": p.get("jobType"), "rule": r.get("rule"),
                "ai": r.get("score") if r.get("kind") == "ai" else None,
            }, ensure_ascii=False)

        out.append(f"== 사용자 {user[:8]}: 마감된 샘플 {len(closed)}건, 바꿀 후보 공고 {len(pool)}건")
        out += ["CLOSED\t" + json.dumps({"id": p["id"], "group": p.get("group")}, ensure_ascii=False) for p in closed]
        rule_top = sorted((r for r in pool if r.get("rule") is not None), key=lambda r: -float(r["rule"]))[:n]
        out += [line("규칙 상위", r) for r in rule_top]
        split = sorted((r for r in pool if r.get("kind") == "ai" and r.get("rule") is not None),
                       key=lambda r: -abs(float(r["score"]) - float(r["rule"])))[:n]
        out += [line("판단 갈림", r) for r in split]
        for jt in sorted({p["group"].split(":", 1)[1] for p in closed if p.get("group", "").startswith("직무별:")}):
            same = sorted((r for r in pool if by_id[r["posting_id"]].get("jobType") == jt),
                          key=lambda r: _order(r["posting_id"], seed))[:n // 2]
            out += [line(f"직무별:{jt}", r) for r in same]
        out += [line("무작위", r) for r in sorted(pool, key=lambda r: _order(r["posting_id"], seed))[:n]]
    return out


MEMO_MAX = 12  # 메모 줄 수


def memo_prompt(comments: list[dict[str, Any]], current: list[str]) -> str:
    """comments: [{label, company, title, comment}] 최신 평가만. current: 지금 메모(있으면 고쳐 쓴다)."""
    lines = [f"- {LABELS.get(c['label'], c['label'])} {c.get('company', '')} | {c.get('title', '')} | {c['comment']}"
             for c in comments]
    now = "\n".join(f"- {x}" for x in current) or "(없음)"
    return (
        "채용공고를 평가하며 지원자가 남긴 코멘트다(○ 지원할 만함, △ 애매, × 아님). 지원자 본인에 대해 알게 된 것을 "
        f"짧은 문장 {MEMO_MAX}개 이내로 정리한다. 매칭 AI가 지원자 요약 끝에 붙여 읽는다.\n"
        "- 경험·역량의 한계와 강점만 쓴다(예: 코드로 ETL을 직접 개발한 경험 없음, 데이터 거버넌스 실무 경력 적음).\n"
        "- 고용 형태·직급·업종·회사 규모·영어처럼 프로필의 원하는 조건으로 따로 받는 것은 쓰지 않는다.\n"
        "- 공고 하나에만 해당하는 사실(그 공고가 인턴임 등)은 쓰지 않는다. 코멘트에 없는 내용을 지어내지 않는다.\n"
        "- 지금 메모와 겹치면 합치고, 새 코멘트와 어긋나면 새 코멘트를 따른다. 각 문장 40자 안쪽.\n\n"
        f"[지금 메모]\n{now}\n\n[코멘트]\n" + "\n".join(lines)
    )


def memo_schema() -> dict[str, Any]:
    return {"type": "OBJECT", "required": ["lines"], "properties": {
        "lines": {"type": "ARRAY", "items": {"type": "STRING"}}}}


def latest_comments(rows: list[dict[str, Any]], user: str, titles: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    """한 사람의 공고별 최신 평가 중 코멘트가 있는 것. rows는 updated_at 오름차순. titles: 공고 id → (회사, 제목)."""
    last: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["user_id"] == user:
            last[r["posting_id"]] = r
    out = []
    for pid, r in last.items():
        if (r.get("comment") or "").strip():
            company, title = titles.get(pid, ("", ""))
            out.append({"label": r["label"], "company": company, "title": title, "comment": r["comment"].strip()})
    return out


def memo_lines(comments: list[dict[str, Any]], current: list[str], client: Any) -> list[str]:
    """코멘트에서 메모 줄을 뽑는다. 코멘트가 없으면 지금 메모 그대로."""
    if not comments:
        return current
    got = client.json(memo_prompt(comments, current), memo_schema())
    return [" ".join(str(x).split())[:60] for x in got.get("lines") or [] if str(x).strip()][:MEMO_MAX]
