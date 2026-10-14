"""회차 리포트: 내 평가(Supabase feedback)와 그때의 AI 판단 근거를 모아 매칭 지침을 고칠 재료를 낸다.

결과는 실행 로그로만 본다(.github/workflows/feedback.yml). 평가 원문에는 개인 의견이 있어 레포에 남기지 않는다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

LABELS = {"good": "○", "maybe": "△", "bad": "×"}


def _avg(xs: list[float]) -> str:
    return f"{sum(xs) / len(xs):.0f}" if xs else "-"


def report(rows: list[dict[str, Any]]) -> list[str]:
    """rows: feedback 표의 줄(snapshot 포함). 회차(match_key)별로 묶는다."""
    if not rows:
        return ["평가가 아직 없다"]
    out: list[str] = []
    by_round: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_round[r["match_key"]].append(r)
    for key, rs in sorted(by_round.items()):
        out.append(f"== 회차 {key}: 평가 {len(rs)}건 "
                   + " ".join(f"{LABELS[k]} {sum(1 for r in rs if r['label'] == k)}" for k in LABELS))
        for k, mark in LABELS.items():
            snaps = [r.get("snapshot") or {} for r in rs if r["label"] == k]
            out.append(f"  {mark}: AI 점수 평균 {_avg([s['score'] for s in snaps if s.get('score') is not None])}, "
                       f"규칙 점수 평균 {_avg([s['rule'] for s in snaps if s.get('rule') is not None])}, "
                       f"AI 판정 {dict(sorted(_count(s.get('verdict') for s in snaps).items()))}")
        # 항목 종류별 가중치 평균과 충족 비율: ○와 ×에서 무엇이 달랐나
        out.append("  항목 종류별 가중치 평균(○ / ×), 충족 비율(○ / ×):")
        kinds = sorted({i.get("kind") for r in rs for i in (r.get("snapshot") or {}).get("items") or []} - {None})
        for kind in kinds:
            stats = []
            for k in ("good", "bad"):
                its = [i for r in rs if r["label"] == k for i in (r.get("snapshot") or {}).get("items") or []
                       if i.get("kind") == kind]
                stats.append((_avg([i.get("weight") or 0 for i in its]),
                              f"{sum(1 for i in its if i.get('fit') == '충족') * 100 // len(its)}%" if its else "-"))
            out.append(f"    {kind}: 가중치 {stats[0][0]} / {stats[1][0]}, 충족 {stats[0][1]} / {stats[1][1]}")
        out.append("  [평가와 점수가 어긋난 공고]")
        for r in rs:
            s = r.get("snapshot") or {}
            if (r["label"] == "bad" and (s.get("score") or 0) >= 70) or (r["label"] == "good" and (s.get("score") or 100) < 60):
                out.append("    " + _line(r))
        out.append("  [전체]")
        for r in sorted(rs, key=lambda r: (r["label"], -((r.get("snapshot") or {}).get("score") or 0))):
            out.append("    " + _line(r))
            for i in (r.get("snapshot") or {}).get("items") or []:
                out.append(f"      - {i.get('kind')} {i.get('weight')} {i.get('fit')} | {i.get('name')} | "
                           f"공고: {i.get('posting')} | 나: {i.get('me')}")
    return out


def _count(xs: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return out


def _line(r: dict[str, Any]) -> str:
    s = r.get("snapshot") or {}
    return (f"{LABELS[r['label']]} AI {s.get('score')}({s.get('verdict')}) 규칙 {s.get('rule')} | "
            f"{s.get('company', '')} | {s.get('title', '')} | 코멘트: {r.get('comment') or '-'}")
