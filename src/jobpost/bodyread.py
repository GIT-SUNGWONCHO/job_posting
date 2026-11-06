"""본문 읽기: 원문이 이미지뿐인 후보 공고의 이미지 글자를 AI로 읽어 본문으로 쓴다(2026-11-02).

열린 공고의 약 18%(직행·사람인)는 본문이 이미지라 글이 300자도 안 된다. 그대로면 공고 정리·매칭이 제목만 보고
판단한다. 후보 공고(누군가의 개인 필터를 통과한 공고)만 공고당 1번 읽는다(설정 config/ai.yaml bodyread).

data 폴더
  ocr.jsonl  {"uid", "text", "images", "prompt", "model", "on"} 공고마다 한 줄. Store.load_details가 짧은 본문 뒤에 붙인다
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
MIN_TEXT = 300  # 본문 글이 이보다 짧으면 본문이 없는 것으로 본다(화면 "본문 없음", 매칭 상한도 같은 기준)
FILE = "ocr.jsonl"

PROMPT = (
    "채용공고 이미지다. 이미지에 적힌 글을 위에서 아래로 그대로 옮겨 적는다.\n"
    "- 요약하거나 고치거나, 이미지에 없는 내용을 지어내지 않는다.\n"
    "- 제목·소제목은 한 줄로, 목록은 줄마다 '- '로 시작한다. 표는 '항목: 내용' 줄로 바꾼다.\n"
    "- 회사 로고·장식 글자, 지원 버튼 같은 화면 문구는 뺀다. 글이 없으면 text를 빈 문자열로 둔다."
)


def schema() -> dict[str, Any]:
    return {"type": "OBJECT", "required": ["text"], "properties": {"text": {"type": "STRING"}}}


def image_urls(detail: dict[str, Any]) -> list[str]:
    """상세(details)에 남은 원문 이미지 주소. 직행: raw.content의 image 노드, 사람인: raw.image_urls."""
    raw = detail.get("raw") or {}
    urls: list[str] = list(raw.get("image_urls") or [])

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "image":
                src = (node.get("attrs") or {}).get("src")
                if src:
                    urls.append(src)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("content"))
    seen: list[str] = []
    for u in urls:
        if u.startswith("http") and u not in seen:
            seen.append(u)
    return seen


def needs_reading(detail: dict[str, Any] | None) -> bool:
    return bool(detail) and len((detail or {}).get("description") or "") < MIN_TEXT and bool(image_urls(detail or {}))


def load(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / FILE
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    return {r["uid"]: r for r in rows}


def save(data_dir: Path, rows: dict[str, dict[str, Any]]) -> None:
    path = data_dir / FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(rows[k], ensure_ascii=False) + "\n" for k in sorted(rows)), encoding="utf-8")
    tmp.replace(path)


def _download(session: requests.Session, url: str, max_bytes: int) -> tuple[str, bytes] | None:
    try:
        resp = session.get(url, timeout=(10, 30))
    except requests.RequestException:
        return None
    mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    if resp.status_code != 200 or not mime.startswith("image/") or len(resp.content) > max_bytes:
        return None
    return mime, resp.content


def run(data_dir: Path, wanted: list[str], details: dict[str, dict[str, Any]], client: Any | None, today: str,
        session: requests.Session | None = None) -> dict[str, Any]:
    """wanted(후보 공고 id, 앞에서부터 먼저) 중 본문이 이미지뿐이고 아직 읽지 않은 공고를 하루 한도까지 읽는다."""
    rows = load(data_dir)
    todo = [u for u in wanted if needs_reading(details.get(u))
            and (rows.get(u) or {}).get("prompt") != PROMPT_VERSION]
    summary: dict[str, Any] = {"wanted": len(wanted), "pending": len(todo), "done": 0, "calls": 0, "empty": 0}
    if not todo:
        return summary
    if client is None:
        summary["skipped"] = "GEMINI_API_KEY 없음"
        return summary
    cfg = config.load("ai").get("bodyread") or {}
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", "Mozilla/5.0 (jobpost body reader)")
    deadline = time.monotonic() + cfg.get("max_minutes", 10) * 60
    errors: list[str] = []
    for uid in todo:
        if summary["calls"] >= cfg.get("max_calls", 80) or time.monotonic() > deadline or len(errors) >= 5:
            break
        urls = image_urls(details[uid])[:cfg.get("max_images", 3)]
        images = [x for x in (_download(session, u, cfg.get("max_bytes", 4_000_000)) for u in urls) if x]
        if not images:
            rows[uid] = {"uid": uid, "text": "", "images": 0, "prompt": PROMPT_VERSION, "model": None, "on": today}
            summary["empty"] += 1
            continue
        summary["calls"] += 1
        try:
            got = client.json(PROMPT, schema(), images=images)
        except Exception as e:  # 남은 건 다음 실행에서
            errors.append(str(e)[:200])
            continue
        text = (got.get("text") or "").strip()
        rows[uid] = {"uid": uid, "text": text, "images": len(images), "prompt": PROMPT_VERSION,
                     "model": getattr(client, "model", None), "on": today}
        summary["done"] += 1
        if not text:
            summary["blank"] = summary.get("blank", 0) + 1  # 읽었지만 글이 없던 이미지(pending 계산에는 done으로 셈)
        if summary["done"] % 20 == 0:
            save(data_dir, rows)
            log.info("본문 읽기 %d/%d건", summary["done"], len(todo))
    save(data_dir, rows)
    summary["pending"] = len(todo) - summary["done"] - summary["empty"]
    if errors:
        summary["errors"] = errors[:3]
    return summary


def merge(detail: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
    """짧은 본문 뒤에 읽은 글을 붙인다. 읽은 글이 없으면 그대로."""
    text = (row or {}).get("text") or ""
    if not text:
        return detail
    desc = (detail.get("description") or "").strip()
    return {**detail, "description": (desc + "\n\n" + text).strip() if desc else text, "ocr": True}
