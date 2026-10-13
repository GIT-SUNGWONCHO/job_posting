"""수집 결과를 파일로 쌓는다. 매일 실행은 이 폴더를 data 브랜치에 커밋한다.

data/
  state.jsonl                     공고별 현재 상태(처음 본 날, 마지막 본 날, 마감일, 중복 대표 등). 매일 다시 쓴다
  postings/YYYY/MM/DD.jsonl.gz    그날 처음 본 공고의 원본. 한 번 쓰면 고치지 않는다
  details/YYYY/MM/DD.jsonl.gz     그날 받은 공고 상세(본문). 한 번 쓰면 고치지 않는다
  companies.json                  회사별 기업 구분
  runs/YYYY-MM-DD.json            실행 요약

지난 공고는 소급해서 모을 수 없어서, 추이 분석은 이 파일들이 쌓인 날부터 가능하다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from .models import Detail, Posting


def _day_path(base: Path, kind: str, day: date) -> Path:
    return base / kind / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.jsonl.gz"


def _read_gz(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_gz(path: Path, rows: list[dict[str, Any]], key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r[key])
    # mtime=0으로 같은 내용이면 같은 파일이 되게 한다(불필요한 커밋 방지)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))


class Store:
    def __init__(self, base: Path):
        self.base = base
        self.state: dict[str, dict[str, Any]] = {}
        path = base / "state.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.state[rec["uid"]] = rec

    def ingest(self, today: date, postings: list[Posting], complete_sources: set[str],
               extra: dict[str, dict[str, Any]] | None = None) -> tuple[list[str], list[str]]:
        """오늘 본 공고를 반영한다. (새 공고 uid, 오늘 내려간 공고 uid)를 돌려준다."""
        day = today.isoformat()
        new_rows: list[dict[str, Any]] = []
        new_uids: list[str] = []
        seen: set[str] = set()
        for p in postings:
            uid = p.uid
            seen.add(uid)
            rec = self.state.get(uid)
            if rec is None:
                rec = {"uid": uid, "source": p.source.value, "first_seen": day, "detail": False}
                self.state[uid] = rec
                new_uids.append(uid)
                row = p.model_dump(mode="json")
                row["uid"] = uid
                new_rows.append(row)
            rec.update({
                "last_seen": day,
                "closed_on": None,
                "company": p.company,
                "title": p.title,
                "deadline_type": p.deadline_type.value,
                "deadline": p.deadline.isoformat() if p.deadline else None,
            })
            if extra and uid in extra:
                rec.update(extra[uid])

        closed: list[str] = []
        for uid, rec in self.state.items():
            if uid in seen or rec.get("closed_on") or rec["source"] not in complete_sources:
                continue
            rec["closed_on"] = day
            closed.append(uid)

        if new_rows:
            path = _day_path(self.base, "postings", today)
            existing = {r["uid"]: r for r in _read_gz(path)}
            for r in new_rows:
                existing[r["uid"]] = r
            _write_gz(path, list(existing.values()), "uid")
        return new_uids, closed

    def add_details(self, today: date, details: list[Detail]) -> None:
        if not details:
            return
        path = _day_path(self.base, "details", today)
        existing = {r["uid"]: r for r in _read_gz(path)}
        for d in details:
            existing[d.uid] = d.model_dump(mode="json")
            if d.uid in self.state:
                self.state[d.uid]["detail"] = True
        _write_gz(path, list(existing.values()), "uid")

    def open_records(self) -> list[dict[str, Any]]:
        return [r for r in self.state.values() if not r.get("closed_on")]

    def save(self) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(self.state[k], ensure_ascii=False, sort_keys=True) for k in sorted(self.state)]
        (self.base / "state.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def save_run(self, today: date, summary: dict[str, Any]) -> Path:
        path = self.base / "runs" / f"{today.isoformat()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def load_details(self) -> dict[str, dict[str, Any]]:
        """저장된 모든 상세(본문). 같은 공고를 다시 받았으면 나중 것."""
        out: dict[str, dict[str, Any]] = {}
        for path in sorted((self.base / "details").rglob("*.jsonl.gz")):
            for r in _read_gz(path):
                out[r["uid"]] = r
        return out

    def load_postings(self) -> dict[str, dict[str, Any]]:
        """저장된 모든 공고 원본(처음 본 날 기준 파일들)을 읽는다."""
        out: dict[str, dict[str, Any]] = {}
        for path in sorted((self.base / "postings").rglob("*.jsonl.gz")):
            for r in _read_gz(path):
                out[r["uid"]] = r
        return out
