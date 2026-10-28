"""내 리서치 노트: data 폴더 notes/*.json을 사람마다 Supabase research_notes에 넣는다. 앱은 본인 줄만 읽는다.

노트는 앱이 그리는 정해진 블록으로만 쓴다(형식과 원칙은 docs/content-rules.md "내 리서치 노트",
화면 쪽 형식은 web/src/lib/notes.ts). 확인된 사실만 넣고 섹션마다 출처를 단다.
누구의 노트인지는 파일의 user_id, 없으면 프로필이 하나뿐일 때 그 사람(지금은 나 혼자 쓴다).
조사 엔진은 아직 없다: 지금은 대화에서 요청해 만든 노트를 data 브랜치 notes/에 올린다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

VERSION = 1
# 블록 종류: 숫자 칸, 소제목, 사실 목록, 표, 연표, 쌓은 막대, 구성비 막대, 단계 흐름, 인용, 경로, 카드
BLOCKS = {"kv", "sub", "facts", "table", "timeline", "stack", "mix", "steps", "quote", "path", "cards"}


def load(data_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    out = []
    for path in sorted((data_dir / "notes").glob("*.json")):
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as e:
            log.warning("노트 파일을 읽지 못함 %s: %s", path.name, e)
    return out


def problems(note: dict[str, Any]) -> list[str]:
    """화면이 그리지 못하는 노트를 걸러낸다(빠진 칸, 모르는 블록, 출처 없는 섹션)."""
    errs = []
    if note.get("v") != VERSION:
        errs.append(f"형식 버전 {note.get('v')}(지금 {VERSION})")
    for key in ("company", "name", "updated", "summary", "sections"):
        if not note.get(key):
            errs.append(f"{key} 없음")
    for i, sec in enumerate(note.get("sections") or []):
        title = sec.get("title") or f"{i + 1}번째"
        if not sec.get("title"):
            errs.append(f"섹션 {i + 1} 제목 없음")
        if not sec.get("sources"):
            errs.append(f"{title}: 출처 없음")
        for b in sec.get("blocks") or []:
            if b.get("t") not in BLOCKS:
                errs.append(f"{title}: 모르는 블록 {b.get('t')}")
    return errs


def run(data_dir: Path, store: Any) -> dict[str, Any]:
    notes = load(data_dir)
    summary: dict[str, Any] = {"files": len(notes), "saved": 0, "skipped": []}
    if not notes:
        return summary
    users = [r["user_id"] for r in store.select("profiles", "select=user_id")]
    rows = []
    for path, note in notes:
        errs = problems(note)
        user = note.get("user_id") or (users[0] if len(users) == 1 else None)
        if not user:
            errs.append(f"누구의 노트인지 모름(user_id 없음, 프로필 {len(users)}명)")
        if errs:
            log.warning("노트 %s 건너뜀: %s", path.name, "; ".join(errs))
            summary["skipped"].append(path.name)
            continue
        body = {k: v for k, v in note.items() if k != "user_id"}
        rows.append({"user_id": user, "company_key": note["company"], "note": body, "updated_on": note["updated"]})
    if rows:
        store.insert("research_notes", rows)
    summary["saved"] = len(rows)
    return summary
