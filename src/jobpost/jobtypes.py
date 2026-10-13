"""직무 유형 분류. 목록은 config/job_types.yaml(고정, 버전 관리), 고르는 건 AI다.

AI는 제목과 수집처 분류만 보고 직무 유형 하나를 고른다. 결과는 state.jsonl의 공고마다
job_type에 목록 버전, 지시문 버전, 모델과 함께 남긴다(docs/content-rules.md 내용 원칙 5).
목록 버전이나 지시문 버전이 바뀌면 열린 공고를 다시 분류한다.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import ai, config

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
# 수집처 분류 중 너무 넓어서 도움이 안 되는 것
_BROAD = {"saramin", "AI_데이터", "AI·데이터"}


def taxonomy() -> dict[str, Any]:
    return config.load("job_types")


def names() -> dict[str, str]:
    return {t["id"]: t["name"] for t in taxonomy()["types"]}


def is_current(rec: dict[str, Any]) -> bool:
    jt = rec.get("job_type") or {}
    return jt.get("v") == taxonomy()["version"] and jt.get("prompt") == PROMPT_VERSION


def prompt(lines: list[str]) -> str:
    guide = "\n".join(f"- {t['id']}: {t['name']} — {t['desc']}" for t in taxonomy()["types"])
    return (
        "채용공고를 직무 유형 하나로 분류한다. 제목과 수집처 분류를 보고 실제로 하게 될 주 업무로 고른다.\n"
        "제목에 AI나 데이터가 들어가도 주 업무가 마케팅·영업·디자인이면 non_data, 일반 개발이면 software다.\n"
        "판단이 어려우면 가장 가까운 것 하나를 고른다.\n\n"
        f"직무 유형:\n{guide}\n\n"
        "공고(번호, 제목, 수집처 분류):\n" + "\n".join(lines)
    )


def schema() -> dict[str, Any]:
    ids = [t["id"] for t in taxonomy()["types"]]
    return {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["i", "t"], "properties": {
        "i": {"type": "INTEGER"}, "t": {"type": "STRING", "enum": ids}}}}


def classify(items: list[tuple[str, str, list[str]]], client: Any) -> dict[str, str]:
    """[(uid, 제목, 수집처 분류)] → {uid: 직무 유형 id}. 형식이 틀린 답은 버리고 다음에 다시 묻는다."""
    lines = []
    for i, (_, title, cats) in enumerate(items):
        clean = " ".join(title.split())
        lines.append(f"{i}\t{clean}\t{', '.join(c for c in cats if c not in _BROAD)[:120]}")
    valid = {t["id"] for t in taxonomy()["types"]}
    out: dict[str, str] = {}
    for row in client.json(prompt(lines), schema()):
        i, t = row.get("i"), row.get("t")
        if isinstance(i, int) and 0 <= i < len(items) and t in valid:
            out[items[i][0]] = t
    return out


def run(state: dict[str, dict[str, Any]], originals: dict[str, dict[str, Any]], today: str,
        client: Any | None = None) -> dict[str, Any]:
    """열린 국내 공고 중 아직 분류하지 않은 것을 분류한다. 새로 본 공고부터, 하루 한도까지."""
    todo = [r for r in state.values()
            if not r.get("closed_on") and not r.get("overseas") and not is_current(r)]
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
        items = [(r["uid"], r.get("title", ""), (originals.get(r["uid"]) or {}).get("categories") or [])
                 for r in batch]
        summary["calls"] += 1
        try:
            got = classify(items, client)
        except Exception as e:  # AI가 실패해도 수집은 끝까지 간다. 남은 건 내일 다시
            errors.append(str(e)[:200])
            if len(errors) >= 3:
                break
            continue
        for uid, t in got.items():
            state[uid]["job_type"] = {"id": t, "v": version, "prompt": PROMPT_VERSION, "model": model, "on": today}
        summary["classified"] += len(got)
        log.info("직무 유형 %d/%d건", summary["classified"], len(todo))
    summary["pending"] = len(todo) - summary["classified"]
    if errors:
        summary["errors"] = errors
    return summary
