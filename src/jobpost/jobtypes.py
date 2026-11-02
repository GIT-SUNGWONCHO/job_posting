"""직무 유형 분류. 목록은 config/job_types.yaml(고정, 버전 관리), 고르는 건 AI다.

AI는 제목, 수집처 분류, 본문의 주요 업무 앞부분(있으면)을 보고 직무 유형 하나를 고른다. 결과는 state.jsonl의
공고마다 job_type에 목록 버전, 지시문 버전, 모델, 본문을 봤는지와 함께 남긴다(docs/content-rules.md 내용 원칙 5).
목록 버전이나 지시문 버전이 바뀌면 열린 공고를 다시 분류한다. 제목만 보고 분류한 공고는 본문이 들어오면 다시 분류한다.
제목만 보면 "AI Solutions Engineer"(사내 AI 서비스 개발)가 컨설팅·사업으로 가 직무 필터에서 빠졌다(2026-11-02).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from . import ai, config

log = logging.getLogger(__name__)

PROMPT_VERSION = 2  # 2: 본문의 주요 업무 앞부분도 본다
# 수집처 분류 중 너무 넓어서 도움이 안 되는 것
_BROAD = {"saramin", "AI_데이터", "AI·데이터"}
SNIPPET_CHARS = 300  # 본문에서 보내는 글자 수(한 번에 80건이라 짧게)
# 본문에서 주요 업무가 시작하는 곳. 없으면 본문 맨 앞(회사 소개일 수 있다)
_DUTY = re.compile(r"담당\s*업무|주요\s*업무|업무\s*내용|직무\s*내용|하는\s*일|하게\s*될\s*일|Responsibilities|What you", re.I)


def taxonomy() -> dict[str, Any]:
    return config.load("job_types")


def names() -> dict[str, str]:
    return {t["id"]: t["name"] for t in taxonomy()["types"]}


def is_current(rec: dict[str, Any], has_body: bool = False) -> bool:
    """지금 목록·지시문으로 분류했고, 본문이 있으면 본문까지 보고 분류했는지."""
    jt = rec.get("job_type") or {}
    return (jt.get("v") == taxonomy()["version"] and jt.get("prompt") == PROMPT_VERSION
            and (jt.get("body", False) or not has_body))


def snippet(text: str | None) -> str:
    """본문에서 주요 업무 앞부분 SNIPPET_CHARS자."""
    if not text:
        return ""
    m = _DUTY.search(text)
    return " ".join(text[m.start() if m else 0:].split())[:SNIPPET_CHARS]


SECONDARY_GUIDE = (
    "주 업무가 두 직무 유형에 실제로 걸치면 s에 보조 직무 유형 하나를 적는다(예: CRM 마케팅 데이터 분석 → 주 non_data, 보조 analyst). "
    "제목에 단어만 들어간 정도로는 보조를 붙이지 않는다. 대부분의 공고는 보조가 없고, 그때 s는 none이다.\n"
)


def prompt(lines: list[str], secondary: bool = False) -> str:
    guide = "\n".join(f"- {t['id']}: {t['name']} — {t['desc']}" for t in taxonomy()["types"])
    return (
        "채용공고를 직무 유형 하나로 분류한다. 제목, 수집처 분류, 본문(주요 업무 앞부분, 없으면 비어 있다)을 보고 "
        "실제로 하게 될 주 업무로 고른다. 제목과 본문이 다르면 본문을 따른다.\n"
        "제목에 AI나 데이터가 들어가도 주 업무가 마케팅·영업·디자인이면 non_data, 일반 개발이면 software다.\n"
        "제목에 Solutions·솔루션이 있어도 사내 서비스·플랫폼을 직접 설계·개발·운영하면 개발 직무로 고르고, "
        "고객사 대상 기술영업·프리세일즈·컨설팅일 때만 consulting이다.\n"
        "판단이 어려우면 가장 가까운 것 하나를 고른다.\n"
        + (SECONDARY_GUIDE if secondary else "") + "\n"
        f"직무 유형:\n{guide}\n\n"
        "공고(번호, 제목, 수집처 분류, 본문):\n" + "\n".join(lines)
    )


def schema(secondary: bool = False) -> dict[str, Any]:
    ids = [t["id"] for t in taxonomy()["types"]]
    props: dict[str, Any] = {"i": {"type": "INTEGER"}, "t": {"type": "STRING", "enum": ids}}
    if secondary:
        props["s"] = {"type": "STRING", "enum": ids + ["none"]}
    return {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["i", "t"] + (["s"] if secondary else []),
                                       "properties": props}}


def classify_with_secondary(items: list[tuple[str, str, list[str], str]], client: Any) -> dict[str, tuple[str, str]]:
    """시험(보조 직무 유형): {uid: (주, 보조 또는 "")}. 보조가 주와 같으면 비운다."""
    lines = [f"{i}\t{' '.join(title.split())}\t{', '.join(c for c in cats if c not in _BROAD)[:120]}\t{body}"
             for i, (_, title, cats, body) in enumerate(items)]
    valid = {t["id"] for t in taxonomy()["types"]}
    out: dict[str, tuple[str, str]] = {}
    for row in client.json(prompt(lines, secondary=True), schema(secondary=True)):
        i, t, s = row.get("i"), row.get("t"), row.get("s") or ""
        if isinstance(i, int) and 0 <= i < len(items) and t in valid:
            out[items[i][0]] = (t, s if s in valid and s != t else "")
    return out


def check_secondary(state: dict[str, dict[str, Any]], originals: dict[str, dict[str, Any]],
                    details: dict[str, dict[str, Any]], client: Any, n: int = 160, seed: str = "secondary") -> dict[str, Any]:
    """시험: 열린 국내 공고 n건(데이터·AI 쪽과 그 밖을 반씩, 무작위)을 보조까지 골라 보고 지금 분류와 비교한다(저장 없음)."""
    import random

    rng = random.Random(seed)
    live = [r for r in state.values() if not r.get("closed_on") and not r.get("overseas") and r.get("job_type")]
    data_side = [r for r in live if r["job_type"]["id"] not in ("non_data", "software", "labeling")]
    other = [r for r in live if r not in data_side]
    pick = rng.sample(data_side, min(n // 2, len(data_side))) + rng.sample(other, min(n - n // 2, len(other)))
    out: dict[str, Any] = {"n": len(pick), "with_secondary": 0, "primary_changed": 0, "rows": []}
    batch = config.load("ai")["job_types"].get("batch", 80)
    for start in range(0, len(pick), batch):
        part = pick[start:start + batch]
        items = [(r["uid"], r.get("title", ""), (originals.get(r["uid"]) or {}).get("categories") or [],
                  snippet((details.get(r["uid"]) or {}).get("description") or (originals.get(r["uid"]) or {}).get("description")))
                 for r in part]
        got = classify_with_secondary(items, client)
        for r in part:
            if r["uid"] not in got:
                continue
            t, s = got[r["uid"]]
            now = r["job_type"]["id"]
            out["with_secondary"] += bool(s)
            out["primary_changed"] += t != now
            if s or t != now:
                out["rows"].append({"title": r.get("title", "")[:60], "now": now, "primary": t, "secondary": s})
    return out


def classify(items: list[tuple[str, str, list[str], str]], client: Any) -> dict[str, str]:
    """[(uid, 제목, 수집처 분류, 본문 앞부분)] → {uid: 직무 유형 id}. 형식이 틀린 답은 버리고 다음에 다시 묻는다."""
    lines = []
    for i, (_, title, cats, body) in enumerate(items):
        clean = " ".join(title.split())
        lines.append(f"{i}\t{clean}\t{', '.join(c for c in cats if c not in _BROAD)[:120]}\t{body}")
    valid = {t["id"] for t in taxonomy()["types"]}
    out: dict[str, str] = {}
    for row in client.json(prompt(lines), schema()):
        i, t = row.get("i"), row.get("t")
        if isinstance(i, int) and 0 <= i < len(items) and t in valid:
            out[items[i][0]] = t
    return out


def run(state: dict[str, dict[str, Any]], originals: dict[str, dict[str, Any]], today: str,
        client: Any | None = None, details: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """열린 국내 공고 중 아직 분류하지 않은 것(본문이 새로 들어온 것 포함)을 분류한다. 새로 본 공고부터, 하루 한도까지.
    details: 상세 본문(store.load_details). 리멤버처럼 목록에 본문이 오는 수집처는 originals의 description."""
    details = details or {}
    bodies = {uid: snippet((details.get(uid) or {}).get("description") or (originals.get(uid) or {}).get("description"))
              for uid, r in state.items() if not r.get("closed_on") and not r.get("overseas")}
    todo = [r for r in state.values()
            if not r.get("closed_on") and not r.get("overseas") and not is_current(r, bool(bodies.get(r["uid"])))]
    summary: dict[str, Any] = {"pending": len(todo), "classified": 0, "calls": 0}
    if not todo:
        return summary
    if client is None:
        if not ai.configured():
            summary["skipped"] = "GEMINI_API_KEY 없음"
            return summary
        client = ai.Gemini()
    cfg = config.load("ai")["job_types"]
    # 새로 본 공고부터. 같은 날이면 잡음·중복이 아닌 것부터
    todo.sort(key=lambda r: (bool(r.get("noise")), bool(r.get("dup_of"))))
    todo.sort(key=lambda r: r.get("first_seen", ""), reverse=True)
    deadline = time.monotonic() + cfg.get("max_minutes", 15) * 60
    version = taxonomy()["version"]
    model = getattr(client, "model", None)
    errors: list[str] = []
    for start in range(0, len(todo), cfg.get("batch", 80)):
        if summary["calls"] >= cfg.get("max_calls", 100) or time.monotonic() > deadline:
            break
        batch = todo[start:start + cfg.get("batch", 80)]
        items = [(r["uid"], r.get("title", ""), (originals.get(r["uid"]) or {}).get("categories") or [],
                  bodies.get(r["uid"], "")) for r in batch]
        summary["calls"] += 1
        try:
            got = classify(items, client)
        except Exception as e:  # AI가 실패해도 수집은 끝까지 간다. 남은 건 내일 다시
            errors.append(str(e)[:200])
            if len(errors) >= 3:
                break
            continue
        for uid, t in got.items():
            state[uid]["job_type"] = {"id": t, "v": version, "prompt": PROMPT_VERSION, "model": model, "on": today,
                                      "body": bool(bodies.get(uid))}
        summary["classified"] += len(got)
        log.info("직무 유형 %d/%d건", summary["classified"], len(todo))
    summary["pending"] = len(todo) - summary["classified"]
    if errors:
        summary["errors"] = errors
    return summary
