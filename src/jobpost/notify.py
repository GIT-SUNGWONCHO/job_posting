"""아침 카톡: 매일 수집·매칭이 끝난 뒤 사람마다 새 공고 중 매칭 점수가 높은 공고를 카톡 "나에게 보내기"로 보낸다.

형식은 고정(docs/content-rules.md "카톡·오늘의 리포트"), 값은 config/notify.yaml.
- 머리: "10/17(금) 새 공고 31건 · 필터 통과 12건 · 마감 임박 2건"
- 항목(최대 3): 필터를 통과한 새 공고를 점수 높은 순으로. "회사 · 공고 제목" / "92점 지원 추천 · D-12"
  2건이 안 되면 마감 임박 공고(점수 기준 이상)로 채우고, 그래도 2건이 안 되면 텍스트 메시지(200자)로 보낸다
- 버튼: 리포트, 공고 목록(대시보드)
새 공고는 지난번 아침 카톡 다음 날부터 오늘까지 처음 본 공고다(하루 빠져도 놓치지 않게). 처음 보낼 때는 오늘 것만.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from . import config, kakao, recommend

log = logging.getLogger(__name__)

WEEKDAYS = "월화수목금토일"
TEXT_MAX = 200


def days_left(p: dict[str, Any], today: date) -> int | None:
    if p.get("deadlineType") != "date" or not p.get("deadline"):
        return None
    return (date.fromisoformat(p["deadline"][:10]) - today).days


def deadline_text(p: dict[str, Any], today: date) -> str:
    """용어집 표기: D-12, D-day, 상시(채용 시 마감 포함), 마감."""
    n = days_left(p, today)
    if n is None:
        return "상시"
    return "마감" if n < 0 else "D-day" if n == 0 else f"D-{n}"


def _link(url: str) -> dict[str, str]:
    return {"web_url": url, "mobile_web_url": url}


def _score_text(m: dict[str, Any] | None) -> str:
    if not m:
        return "점수 없음"
    if m.get("kind") == "rule":
        return f"규칙 {m['score']}점"
    return f"{m['score']}점 {m['verdict']}" if m.get("verdict") else f"{m['score']}점"


def message(screen: dict[str, Any], filters: dict[str, Any], matches: dict[str, dict[str, Any]], today: date,
            since: date | None = None) -> dict[str, Any]:
    """카카오 template_object 하나를 만든다. matches: 공고 id → {score, verdict, kind}."""
    cfg = config.load("notify")
    base = cfg["dashboard_url"].rstrip("/") + "/"
    companies = screen.get("companies") or {}
    start = (since + timedelta(days=1)).isoformat() if since else today.isoformat()
    end = today.isoformat()

    def score(p: dict[str, Any]) -> float:
        m = matches.get(p["id"])
        return m["score"] if m else -1

    new = [p for p in screen["postings"] if start <= p["firstSeen"] <= end]
    passed = {p["id"]: p for p in recommend.candidates(screen, filters)}
    new_passed = sorted((p for p in new if p["id"] in passed), key=lambda p: (score(p), p["firstSeen"]), reverse=True)
    soon = sorted((p for p in passed.values() if (n := days_left(p, today)) is not None and 0 <= n <= cfg["soon_days"]),
                  key=score, reverse=True)

    head = (f"{today.month}/{today.day}({WEEKDAYS[today.weekday()]}) 새 공고 {len(new)}건 · "
            f"필터 통과 {len(new_passed)}건" + (f" · 마감 임박 {len(soon)}건" if soon else ""))
    picks = [(p, "") for p in new_passed[:cfg["top"]]]
    if len(picks) < 2:
        shown = {p["id"] for p, _ in picks}
        picks += [(p, "마감 임박 · ") for p in soon if p["id"] not in shown and score(p) >= cfg["soon_min_score"]
                  ][:2 - len(picks)]

    def item(p: dict[str, Any], prefix: str) -> dict[str, Any]:
        name = (companies.get(p["company"]) or {}).get("name") or p["company"]
        return {"title": f"{name} · {p['title']}",
                "description": f"{prefix}{_score_text(matches.get(p['id']))} · {deadline_text(p, today)}",
                "link": _link(base + "#/job/" + quote(p["id"], safe=""))}

    buttons = [{"title": "리포트", "link": _link(base + "#/report")},
               {"title": "공고 목록", "link": _link(base + "#/jobs")}]
    if len(picks) >= 2:
        return {"object_type": "list", "header_title": head, "header_link": _link(base + "#/report"),
                "contents": [item(p, prefix) for p, prefix in picks], "buttons": buttons}
    lines = [head]
    if picks:
        it = item(*picks[0])
        lines.append(f"· {it['title']} ({it['description']})")
    else:
        lines.append("필터를 통과한 새 공고가 없어요.")
    text = "\n".join(lines)
    if len(text) > TEXT_MAX:
        text = text[:TEXT_MAX - 1] + "…"
    return {"object_type": "text", "text": text, "link": _link(base + "#/report"), "buttons": buttons}


def run(screen: dict[str, Any], db: Any, today: date, session: Any = None) -> dict[str, Any]:
    """카톡을 연결한 사람마다 아침 카톡을 보낸다. 한 사람이 실패해도 나머지는 보낸다."""
    defaults = config.load("filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    links = db.select("kakao_links", "select=user_id,refresh_token,last_sent_on")
    summary: dict[str, Any] = {"linked": len(links), "sent": 0, "skipped": 0, "errors": []}
    for link in links:
        user = link["user_id"]
        if link.get("last_sent_on") == today.isoformat():
            summary["skipped"] += 1  # 오늘 이미 보냄(수집을 다시 돌린 날)
            continue
        try:
            tok = kakao.refresh(link["refresh_token"], session)
            if tok.get("refresh_token"):  # 1개월 미만 남아 새로 받은 토큰. 바로 저장해야 다음 날도 보낼 수 있다
                db.update("kakao_links", f"user_id=eq.{user}", token_values(tok))
            rows = db.select("matches", f"select=posting_id,score,parts&user_id=eq.{user}")
            matches = {r["posting_id"]: {"score": r["score"], "verdict": (r.get("parts") or {}).get("verdict"),
                                         "kind": (r.get("parts") or {}).get("kind")} for r in rows}
            since = date.fromisoformat(link["last_sent_on"]) if link.get("last_sent_on") else None
            if since and (today - since).days > 7:
                since = today - timedelta(days=7)  # 오래 쉬었으면 지난 1주일만
            msg = message(screen, {**defaults, **settings.get(user, {})}, matches, today, since)
            kakao.send(tok["access_token"], msg, session)
            db.update("kakao_links", f"user_id=eq.{user}", {"last_sent_on": today.isoformat()})
            summary["sent"] += 1
            log.info("아침 카톡 보냄: 사람 %s, %s", user[:8], msg.get("header_title") or msg.get("text", "").split("\n")[0])
        except Exception as e:  # 토큰 값은 오류 문장에 들어가지 않는다(kakao.py)
            summary["errors"].append(f"{user[:8]}: {str(e)[:200]}")
    if not summary["errors"]:
        summary.pop("errors")
    return summary


def token_values(tok: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=int(tok["refresh_token_expires_in"])) if tok.get("refresh_token_expires_in") else None
    return {"refresh_token": tok["refresh_token"], "refresh_expires_at": expires.isoformat() if expires else None,
            "updated_at": now.isoformat()}


def connect(db: Any, code: str, user: str | None = None, session: Any = None) -> str:
    """카톡 연결: 인가 코드로 토큰을 받아 저장한다. user가 없으면 프로필이 하나뿐일 때 그 사람."""
    if not user:
        users = [r["user_id"] for r in db.select("profiles", "select=user_id")]
        if len(users) != 1:
            raise ValueError(f"프로필이 {len(users)}개라 누구의 카톡인지 정할 수 없다. user_id를 넣어 다시 실행")
        user = users[0]
    cfg = config.load("notify")
    tok = kakao.exchange(code.strip(), cfg["dashboard_url"].rstrip("/") + cfg["redirect_path"], session)
    # 다시 연결하면 새 토큰으로 바꾸고, 오늘 바로 시험 메시지를 받을 수 있게 보낸 날을 비운다
    db.insert("kakao_links", [{"user_id": user, **token_values(tok), "last_sent_on": None}])
    return user
