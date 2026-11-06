"""기준 목록을 코드로 옮기기(docs/taxonomy.md '코드로 옮기기'). 저장된 지난 id를 코드로 바꾼다.

업종(2026-11-06): 프로필의 경력 업종(careers[].industry)과 선호·비선호 업종(wants.industriesLike/Avoid).
바꾸기 전에 프로필 전체를 Supabase 비공개 저장소(backups/)에 올린다. 로그에는 건수만 남긴다(프로필 내용은 남기지 않는다).
AI에 보내는 프로필 요약은 업종 이름을 써서 바뀌지 않는다(매칭을 다시 하지 않는다).
"""

from __future__ import annotations

import copy
import gzip
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from . import publish, taxonomy


def _code(x: Any) -> Any:
    """지난 id면 코드로, 코드거나 모르는 값이면 그대로."""
    return taxonomy.industry_code(x) or x if isinstance(x, str) and x else x


def industry_data(data: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    """(바꾼 프로필, 바꾼 값 수, 코드로 못 바꾼 값 수)."""
    new = copy.deepcopy(data)
    changed = unknown = 0
    values: list[tuple[dict[str, Any], str | int]] = []
    for c in new.get("careers") or []:
        if c.get("industry"):
            values.append((c, "industry"))
    wants = new.get("wants") or {}
    for key in ("industriesLike", "industriesAvoid"):
        for i, _ in enumerate(wants.get(key) or []):
            values.append((wants[key], i))
    for holder, k in values:
        old = holder[k]
        code = _code(old)
        if not taxonomy.industry_code(code):
            unknown += 1
        elif code != old:
            holder[k] = code
            changed += 1
    return new, changed, unknown


def industries(db: Any, apply: bool = False, today: date | None = None) -> dict[str, Any]:
    rows = db.select("profiles", "select=user_id,data")
    plans = []
    for r in rows:
        new, changed, unknown = industry_data(r.get("data") or {})
        plans.append((r, new, changed, unknown))
    summary = {"profiles": len(rows), "to_change": sum(1 for p in plans if p[2]),
               "values": sum(p[2] for p in plans), "unknown": sum(p[3] for p in plans), "applied": False}
    if not apply or not summary["values"]:
        return summary
    # 백업(비공개 저장소). 실패하면 바꾸지 않는다
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "profiles.json.gz"
        path.write_bytes(gzip.compress(json.dumps(rows, ensure_ascii=False).encode()))
        name = f"backups/profiles-{(today or date.today()).isoformat()}.json.gz"
        publish.upload(path, name=name)
        summary["backup"] = name
    for r, new, changed, _ in plans:
        if changed:
            db.update("profiles", f"user_id=eq.{r['user_id']}", {"data": new})
    summary["applied"] = True
    return summary
