"""아침 알림: 매일 수집·매칭이 끝난 뒤 사람마다 새 공고 요약을 보낸다. 보낼 곳은 config/notify.yaml channels.

텔레그램(기본, 2026-10-21~)과 카톡 "나에게 보내기"(꺼 둠)가 같은 요약(digest)을 쓴다. 형식은 고정
(docs/content-rules.md "아침 알림·오늘의 리포트"), 개수는 config/notify.yaml.
- 머리: "10/21(수) 새 공고 208건 · 필터 통과 11건 · 마감 임박 7건"
- 필터 통과 새 공고를 점수 높은 순으로: "회사 · 공고 제목" / "92점 지원 추천 · D-12", 공고 상세 링크
- 마감 임박(필터 통과, D-day~D-3) 중 점수 기준 이상
- 대시보드 링크: 리포트, 공고 목록
새 공고는 지난번 알림 다음 날부터 오늘까지 처음 본 공고다(하루 빠져도 놓치지 않게, 최대 1주일). 처음 보낼 때는 오늘 것만.
"""

from __future__ import annotations

import html
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from . import config, kakao, recommend, telegram

log = logging.getLogger(__name__)

WEEKDAYS = "월화수목금토일"
KAKAO_TEXT_MAX = 200


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


def _score_text(m: dict[str, Any] | None) -> str:
    if not m:
        return "점수 없음"
    if m.get("kind") == "rule":
        return f"규칙 {m['score']}점"
    return f"{m['score']}점 {m['verdict']}" if m.get("verdict") else f"{m['score']}점"


def digest(screen: dict[str, Any], filters: dict[str, Any], matches: dict[str, dict[str, Any]], today: date,
           since: date | None = None) -> dict[str, Any]:
    """채널과 상관없는 요약. matches: 공고 id → {score, verdict, kind}."""
    cfg = config.load("notify")
    base = cfg["dashboard_url"].rstrip("/") + "/"
    companies = screen.get("companies") or {}
    start = (since + timedelta(days=1)).isoformat() if since else today.isoformat()

    def score(p: dict[str, Any]) -> float:
        m = matches.get(p["id"])
        return m["score"] if m else -1

    def item(p: dict[str, Any]) -> dict[str, Any]:
        name = (companies.get(p["company"]) or {}).get("name") or p["company"]
        # 수집처 제목에 &amp; 같은 HTML 표기가 섞여 온다. 글자로 풀어 두고 채널마다 다시 바꾼다
        return {"id": p["id"], "title": html.unescape(f"{name} · {p['title']}"), "score": score(p),
                "info": f"{_score_text(matches.get(p['id']))} · {deadline_text(p, today)}",
                "url": base + "#/job/" + quote(p["id"], safe="")}

    new = [p for p in screen["postings"] if start <= p["firstSeen"] <= today.isoformat()]
    passed = {p["id"]: p for p in recommend.candidates(screen, filters)}
    new_passed = sorted((p for p in new if p["id"] in passed), key=lambda p: (score(p), p["firstSeen"]), reverse=True)
    soon = sorted((p for p in passed.values() if (n := days_left(p, today)) is not None and 0 <= n <= cfg["soon_days"]),
                  key=score, reverse=True)
    head = (f"{today.month}/{today.day}({WEEKDAYS[today.weekday()]}) 새 공고 {len(new)}건 · "
            f"필터 통과 {len(new_passed)}건" + (f" · 마감 임박 {len(soon)}건" if soon else ""))
    return {"head": head, "new": [item(p) for p in new_passed], "soon_count": len(soon),
            "soon": [item(p) for p in soon if score(p) >= cfg["soon_min_score"]],
            "report": base + "#/report", "jobs": base + "#/jobs"}


def telegram_message(d: dict[str, Any]) -> str:
    """텔레그램 HTML 메시지(4096자 안)."""
    cfg = config.load("notify")["telegram"]

    def esc(s: str) -> str:
        return html.escape(s, quote=False)

    def link(url: str, text: str) -> str:
        return f'<a href="{html.escape(url)}">{esc(text)}</a>'

    def build(top: int, soon_top: int) -> str:
        lines = [f"<b>{esc(d['head'])}</b>", ""]
        if d["new"]:
            lines.append("<b>필터 통과 새 공고</b>")
            for i, it in enumerate(d["new"][:top], 1):
                lines += [f"{i}. {link(it['url'], it['title'])}", f"    {esc(it['info'])}"]
            if len(d["new"]) > top:
                lines.append(f"외 {len(d['new']) - top}건은 {link(d['jobs'], '공고 목록')}에서")
        else:
            lines.append("필터를 통과한 새 공고가 없어요.")
        if d["soon"][:soon_top]:
            lines += ["", f"<b>마감 임박</b> ({config.load('notify')['soon_min_score']}점 이상)"]
            lines += [f"· {link(it['url'], it['title'])}  {esc(it['info'])}" for it in d["soon"][:soon_top]]
        lines += ["", f"{link(d['report'], '리포트')} · {link(d['jobs'], '공고 목록')}"]
        return "\n".join(lines)

    top, soon_top = cfg["top"], cfg["soon_top"]
    text = build(top, soon_top)
    while len(text) > telegram.TEXT_MAX and top > 1:  # 태그까지 세어 넉넉히 줄인다
        top -= 1
        soon_top = min(soon_top, top)
        text = build(top, soon_top)
    return text


def kakao_message(d: dict[str, Any]) -> dict[str, Any]:
    """카카오 template_object. 리스트 템플릿은 항목 2~3개라 새 공고 상위 3건, 모자라면 마감 임박으로 채운다."""
    cfg = config.load("notify")["kakao"]

    def link(url: str) -> dict[str, str]:
        return {"web_url": url, "mobile_web_url": url}
    picks = [(it, "") for it in d["new"][:cfg["top"]]]
    if len(picks) < 2:
        shown = {it["id"] for it, _ in picks}
        picks += [(it, "마감 임박 · ") for it in d["soon"] if it["id"] not in shown][:2 - len(picks)]
    buttons = [{"title": "리포트", "link": link(d["report"])}, {"title": "공고 목록", "link": link(d["jobs"])}]
    if len(picks) >= 2:
        return {"object_type": "list", "header_title": d["head"], "header_link": link(d["report"]),
                "contents": [{"title": it["title"], "description": prefix + it["info"], "link": link(it["url"])}
                             for it, prefix in picks], "buttons": buttons}
    lines = [d["head"]]
    lines.append(f"· {picks[0][0]['title']} ({picks[0][1]}{picks[0][0]['info']})" if picks
                 else "필터를 통과한 새 공고가 없어요.")
    text = "\n".join(lines)
    if len(text) > KAKAO_TEXT_MAX:
        text = text[:KAKAO_TEXT_MAX - 1] + "…"
    return {"object_type": "text", "text": text, "link": link(d["report"]), "buttons": buttons}


def channels() -> list[str]:
    """켜 두었고 키도 있는 채널."""
    mods = {"telegram": telegram, "kakao": kakao}
    return [c for c in config.load("notify")["channels"] if mods[c].configured()]


def run(screen: dict[str, Any], db: Any, today: date, session: Any = None) -> dict[str, Any]:
    """연결한 사람마다 켜 둔 채널로 아침 알림을 보낸다. 같은 날 두 번 보내지 않고, 한 사람이 실패해도 나머지는 보낸다."""
    cfg = config.load("notify")
    defaults = config.load("filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in db.select("settings", "select=user_id,filters")}
    cache: dict[tuple[str, str | None], dict[str, Any]] = {}

    def summary_for(user: str, last_sent_on: str | None) -> dict[str, Any]:
        since = date.fromisoformat(last_sent_on) if last_sent_on else None
        if since and (today - since).days > 7:
            since = today - timedelta(days=7)  # 오래 쉬었으면 지난 1주일만
        key = (user, since.isoformat() if since else None)
        if key not in cache:
            rows = db.select("matches", f"select=posting_id,score,parts&user_id=eq.{user}")
            matches = {r["posting_id"]: {"score": r["score"], "verdict": (r.get("parts") or {}).get("verdict"),
                                         "kind": (r.get("parts") or {}).get("kind")} for r in rows}
            cache[key] = digest(screen, {**defaults, **settings.get(user, {})}, matches, today, since)
        return cache[key]

    out: dict[str, Any] = {"errors": []}
    for channel in cfg["channels"]:
        if channel not in channels():
            out[channel] = "키 없음"
            continue
        table = f"{channel}_links"
        cols = "user_id,chat_id,last_sent_on" if channel == "telegram" else "user_id,refresh_token,last_sent_on"
        links = db.select(table, f"select={cols}")
        s = out[channel] = {"linked": len(links), "sent": 0, "skipped": 0}
        for link in links:
            user = link["user_id"]
            if link.get("last_sent_on") == today.isoformat():
                s["skipped"] += 1  # 오늘 이미 보냄(수집을 다시 돌린 날)
                continue
            try:
                d = summary_for(user, link.get("last_sent_on"))
                if channel == "telegram":
                    telegram.send(link["chat_id"], telegram_message(d), session)
                else:
                    tok = kakao.refresh(link["refresh_token"], session)
                    if tok.get("refresh_token"):  # 1개월 미만 남아 새로 받은 토큰. 바로 저장해야 다음 날도 보낼 수 있다
                        db.update(table, f"user_id=eq.{user}", token_values(tok))
                    kakao.send(tok["access_token"], kakao_message(d), session)
                db.update(table, f"user_id=eq.{user}", {"last_sent_on": today.isoformat()})
                s["sent"] += 1
                log.info("아침 알림(%s) 보냄: 사람 %s, %s", channel, user[:8], d["head"])
            except Exception as e:  # 토큰 값은 오류 문장에 들어가지 않는다(telegram.py, kakao.py)
                out["errors"].append(f"{channel} {user[:8]}: {str(e)[:200]}")
    if not out["errors"]:
        out.pop("errors")
    return out


def _only_user(db: Any, user: str | None) -> str:
    if user:
        return user
    users = [r["user_id"] for r in db.select("profiles", "select=user_id")]
    if len(users) != 1:
        raise ValueError(f"프로필이 {len(users)}개라 누구의 연결인지 정할 수 없다. user_id를 넣어 다시 실행")
    return users[0]


def connect_telegram(db: Any, user: str | None = None, session: Any = None) -> str:
    """텔레그램 연결: 봇에게 가장 최근에 말을 건 1:1 대화방을 그 사람의 알림 받을 곳으로 저장한다."""
    user = _only_user(db, user)
    chat = telegram.latest_chat(session)
    if not chat:
        raise ValueError("봇이 받은 메시지가 없다. 텔레그램에서 봇에게 /start를 보내고(24시간 안에) 다시 실행")
    if chat.get("type") != "private":
        raise ValueError(f"가장 최근 메시지가 1:1 대화가 아니다({chat.get('type')}). 봇과의 1:1 대화에서 /start를 보내고 다시 실행")
    db.insert("telegram_links", [{"user_id": user, "chat_id": chat["id"], "last_sent_on": None,
                                  "updated_at": datetime.now(UTC).isoformat()}])
    return user


def token_values(tok: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=int(tok["refresh_token_expires_in"])) if tok.get("refresh_token_expires_in") else None
    return {"refresh_token": tok["refresh_token"], "refresh_expires_at": expires.isoformat() if expires else None,
            "updated_at": now.isoformat()}


def connect_kakao(db: Any, code: str, user: str | None = None, session: Any = None) -> str:
    """카톡 연결: 인가 코드로 토큰을 받아 저장한다."""
    user = _only_user(db, user)
    cfg = config.load("notify")
    tok = kakao.exchange(code.strip(), cfg["dashboard_url"].rstrip("/") + cfg["kakao"]["redirect_path"], session)
    # 다시 연결하면 새 토큰으로 바꾸고, 오늘 바로 시험 메시지를 받을 수 있게 보낸 날을 비운다
    db.insert("kakao_links", [{"user_id": user, **token_values(tok), "last_sent_on": None}])
    return user
