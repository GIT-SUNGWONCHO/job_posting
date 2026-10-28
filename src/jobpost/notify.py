"""아침 알림: 매일 수집·매칭이 끝난 뒤 사람마다 새 공고 요약을 보낸다. 보낼 곳은 config/notify.yaml channels.

세 묶음, 모두 접어서 제목과 건수만 보인다(docs/content-rules.md "아침 알림·오늘의 리포트"). 첫 통에 1·3,
필터 밖은 둘째 통으로 따로(한 통이 길면 텔레그램 앱이 "더보기"로 자른다):
1. 필터 통과 새 공고: 전부, 점수 높은 순
2. 필터 밖 새 공고: 참고용(잡음 빼고). 필터가 안정될 때까지 공고마다 걸린 이유(config/notify.yaml others_reason)
3. 마감 임박: D-day~D-3. 관심 공고 먼저, 그다음 필터 통과 공고 중 점수 기준(soon_min_score) 이상
새 공고는 지난번 알림 다음 날부터 오늘까지 처음 본 공고다(하루 빠져도 놓치지 않게, 최대 1주일). 처음 보낼 때는 오늘 것만.
지원했거나 관심 없음으로 둔 공고는 뺀다. 공고마다 "판정 표시 회사 · 점수 · 마감" + 제목(회사는 회사 화면, 제목은 공고 상세 링크).
텔레그램(기본)과 카톡 "나에게 보내기"(꺼 둠)가 같은 요약(digest)을 쓴다.
"""

from __future__ import annotations

import html
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from . import config, kakao, recommend, telegram
from . import filters as personal
from .models import CompanyType

log = logging.getLogger(__name__)

WEEKDAYS = "월화수목금토일"
RICH_MAX = 30000   # 리치 메시지 32768자보다 넉넉히(버튼·꼬리말 몫)
RICH_ROWS = 450    # 리치 메시지 블록 500개(표 줄 포함)보다 넉넉히
KAKAO_TEXT_MAX = 200

# 다시 추천하지 않는 지원 단계: 이미 지원했거나 관심 없음(web/src/lib/applications.ts NOT_AGAIN과 같게)
NOT_AGAIN = {"applied", "passed", "interview", "result", "dismissed"}

MARKS = {"지원 추천": "🟢", "고려": "🟡", "비추천": "⚪"}  # 판정을 한눈에(규칙 점수·점수 없음은 ▫️)


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


def enabled(raw: dict[str, Any] | None) -> bool:
    """관리 화면의 "아침 알림 받기"(Supabase settings.notify.enabled). 고르지 않았거나 모양이 이상하면 받는다
    (한 사람의 잘못된 값이 모두의 알림을 멈추지 않게)."""
    return not (isinstance(raw, dict) and raw.get("enabled") is False)


def screen_defaults() -> dict[str, Any]:
    """관리 화면이 알림에 들어가는 것을 적을 때 쓰는 값(화면용 파일 notify)."""
    cfg = config.load("notify")
    return {"channels": cfg["channels"], "soonMinScore": cfg["soon_min_score"], "soonDays": cfg["soon_days"]}


def why_not(p: dict[str, Any], screen: dict[str, Any], filters: dict[str, Any]) -> tuple[str, int]:
    """필터 밖 공고가 걸린 이유를 한 줄로("직무 데이터 분석 · 경력 3년 이상")와 걸린 조건 수."""
    c = (screen.get("companies") or {}).get(p["company"]) or {}
    jobs = {t["id"]: t.get("short") or t["name"] for t in screen.get("jobTypes") or []}
    found = personal.reasons(title=p["title"], company=c.get("name", ""), company_type=CompanyType(c.get("type", "그 외")),
                             career_min=p.get("careerMin"), career_max=p.get("careerMax"), regions=p.get("regions") or [],
                             filters=filters, job_type=p.get("jobType"))
    text = {"keyword": lambda v: f"제외 키워드 {v}", "company": lambda v: f"제외 회사 {v}",
            "job": lambda v: f"직무 {jobs.get(v, v)}", "company_type": lambda v: f"기업 구분 {v}",
            "career": lambda v: p.get("career") or "경력", "region": lambda v: f"지역 {v}"}
    return " · ".join(text[kind](value) for kind, value in found), len(found)


def digest(screen: dict[str, Any], filters: dict[str, Any], matches: dict[str, dict[str, Any]], today: date,
           since: date | None = None, stages: dict[str, str] | None = None) -> dict[str, Any]:
    """채널과 상관없는 요약. matches: 공고 id → {score, verdict, kind}, stages: 공고 id → 지원 단계."""
    stages = stages or {}
    cfg = config.load("notify")
    base = cfg["dashboard_url"].rstrip("/") + "/"
    companies = screen.get("companies") or {}
    start = (since + timedelta(days=1)).isoformat() if since else today.isoformat()

    def score(p: dict[str, Any]) -> float:
        m = matches.get(p["id"])
        return m["score"] if m else -1

    def by_score(ps: Any) -> list[dict[str, Any]]:
        return sorted(ps, key=lambda p: (score(p), p["firstSeen"]), reverse=True)

    def item(p: dict[str, Any]) -> dict[str, Any]:
        name = (companies.get(p["company"]) or {}).get("name") or p["company"]
        # 수집처 제목에 &amp; 같은 HTML 표기가 섞여 온다. 글자로 풀어 두고 채널마다 다시 바꾼다
        m = matches.get(p["id"]) or {}
        title = p.get("listTitle") or p["title"]  # 목록 제목(회사 이름·'채용' 같은 말을 뺀 제목), 없으면 원문
        return {"id": p["id"], "title": html.unescape(f"{name} · {title}"),
                "company": html.unescape(name), "name": html.unescape(title), "score": score(p),
                "verdict": m.get("verdict") if m.get("kind") == "ai" else ("규칙 점수" if m else None),
                "deadline": deadline_text(p, today),
                "info": f"{_score_text(matches.get(p['id']))} · {deadline_text(p, today)}",
                "url": base + "#/job/" + quote(p["id"], safe=""),
                "companyUrl": base + "#/company/" + quote(p["company"], safe=""),
                "interest": stages.get(p["id"]) == "interest"}

    def closing(p: dict[str, Any]) -> bool:
        n = days_left(p, today)
        return n is not None and 0 <= n <= cfg["soon_days"]

    wanted = [p for p in screen["postings"] if stages.get(p["id"]) not in NOT_AGAIN]
    passing = {p["id"] for p in recommend.candidates(screen, filters)}  # 잡음은 빠져 있다
    new = [p for p in wanted if start <= p["firstSeen"] <= today.isoformat()]
    passed = by_score(p for p in new if p["id"] in passing)
    # 필터 밖: 걸린 조건이 적은(아깝게 빠진) 공고부터. 한도에 걸리면 뒤에서 줄인다
    why = {p["id"]: why_not(p, screen, filters) for p in new if p["id"] not in passing and not p.get("noise")}
    others = sorted(by_score(p for p in new if p["id"] in why), key=lambda p: why[p["id"]][1])
    interest = sorted((p for p in wanted if stages.get(p["id"]) == "interest" and closing(p)), key=lambda p: p.get("deadline") or "")
    soon = by_score(p for p in wanted if p["id"] in passing and closing(p) and stages.get(p["id"]) != "interest")
    soon = [p for p in soon if score(p) >= cfg["soon_min_score"]]
    # 머리 건수는 두 통에 실제로 든 공고 수(새 공고 = 필터 통과 + 필터 밖, 잡음·지원·관심 없음은 빼고)
    n_new, n_soon = len(passed) + len(others), len(interest) + len(soon)
    # 며칠 만에 보내면 기간을 적는다(지난 알림 다음 날부터 오늘까지)
    first = date.fromisoformat(start)
    day = f"{today.month}/{today.day}({WEEKDAYS[today.weekday()]})"
    if first < today:
        day = f"{first.month}/{first.day}~{day}"
    return {"date": day,
            "head": f"{day} 새 공고 {n_new}건 · 필터 통과 {len(passed)}건" + (f" · 마감 임박 {n_soon}건" if n_soon else ""),
            "counts": {"new": n_new, "passed": len(passed), "soon": n_soon},
            "passed": [item(p) for p in passed],
            "others": [{**item(p), "why": why[p["id"]][0] if cfg.get("others_reason") else None} for p in others],
            "soon": [item(p) for p in interest] + [item(p) for p in soon],
            "soonMinScore": cfg["soon_min_score"],
            "report": base + "#/report", "jobs": base + "#/jobs", "career": base + "#/career"}


SECTIONS = {"passed": "필터 통과 새 공고", "others": "필터 밖 새 공고(참고)", "soon": "마감 임박"}
# 메시지 두 통: 첫 통은 필터 통과 새 공고와 마감 임박(짧게, 앱이 "더보기"로 자르지 않게), 둘째 통은 필터 밖 새 공고(참고)
MESSAGES = (("passed", "soon"), ("others",))


def _sections(d: dict[str, Any], keys: tuple[str, ...], limits: dict[str, int]) -> list[dict[str, Any]]:
    """묶음(제목, 보일 공고). limits: 묶음마다 보일 개수(한도에 걸리면 줄인다). 줄인 묶음은 "외 N건"."""
    out = []
    for key in keys:
        title = SECTIONS[key] + (f" · ★ 관심 공고와 {d['soonMinScore']}점 이상" if key == "soon" else "")
        shown = d[key][:limits[key]]
        out.append({"key": key, "title": title, "items": shown, "total": len(d[key]), "rest": len(d[key]) - len(shown)})
    return out


def _fit(d: dict[str, Any], keys: tuple[str, ...], render: Any, too_big: Any) -> Any:
    """한도 안에 들 때까지 필터 밖 → 마감 임박 → 필터 통과 순으로 뒤에서 줄인다."""
    cfg = config.load("notify")["telegram"]
    limits = {"passed": len(d["passed"]), "others": len(d["others"]), "soon": min(len(d["soon"]), cfg["soon_top"])}
    out = render(_sections(d, keys, limits))
    while too_big(out):
        key = next((k for k in ("others", "soon", "passed") if k in keys and limits[k] > (1 if k == "passed" else 0)), None)
        if key is None:
            break
        limits[key] = max(0, limits[key] - (5 if key == "others" else 1))
        out = render(_sections(d, keys, limits))
    return out


def _rest_text(sec: dict[str, Any]) -> str:
    """한도에 걸려 줄인 묶음의 안내. 필터 밖 공고는 공고 목록(개인 필터 적용)에 나오지 않는다."""
    if sec["key"] == "others":
        return f"외 {sec['rest']}건은 걸린 조건이 더 많은 공고라 줄였어요"
    return f"외 {sec['rest']}건은 공고 목록에서"


def _legend() -> str:
    return " · ".join(f"{mark} {name}" for name, mark in MARKS.items())


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def telegram_message(d: dict[str, Any]) -> list[tuple[str, list[list[dict[str, str]]] | None]]:
    """텔레그램 일반 메시지(HTML, 한 통 4096자 안)와 아래 버튼. 리치 메시지가 실패한 날 대신 보낸다.
    첫 통은 머리 두 줄 + 필터 통과 새 공고 + 마감 임박(접힌 인용) + 판정 설명, 둘째 통은 필터 밖 새 공고."""

    def entry(it: dict[str, Any], link_company: bool = True) -> str:
        score = "점수 없음" if it["score"] < 0 else f"{it['score']:g}점"
        star = "★ " if it["interest"] else ""
        why = f"\n<i>필터 밖: {_esc(it['why'])}</i>" if it.get("why") else ""
        company = f'<a href="{html.escape(it["companyUrl"])}">{_esc(it["company"])}</a>' if link_company else _esc(it["company"])
        return (f'{MARKS.get(it["verdict"] or "", "▫️")} <b>{star}{company}</b>  {score} · {_esc(it["deadline"])}\n'
                f'<a href="{html.escape(it["url"])}">{_esc(it["name"])}</a>{why}')

    def render(sections: list[dict[str, Any]], first: bool) -> str:
        c = d["counts"]
        lines = [f"<b>{_esc(d['date'])} 오늘의 공고</b>", f"새 공고 {c['new']} · 필터 통과 {c['passed']} · 마감 임박 {c['soon']}"] if first else []
        for sec in sections:
            if sec["key"] == "passed" and not sec["total"]:
                lines += ["", "필터를 통과한 새 공고가 없어요."]
                continue
            if not sec["total"]:
                continue
            lines += ["", f"<b>{_esc(sec['title'])}</b> {sec['total']}건"]
            if sec["items"]:
                lines.append("<blockquote expandable>" + "\n\n".join(entry(it, sec["key"] != "others") for it in sec["items"])
                             + "</blockquote>")
            if sec["rest"]:
                lines.append(_rest_text(sec))
        if first:
            lines += ["", _legend()]
        return "\n".join(lines).strip()

    buttons = [[{"text": "리포트", "url": d["report"]}, {"text": "공고 목록", "url": d["jobs"]},
                {"text": "커리어", "url": d["career"]}]]
    out: list[tuple[str, list[list[dict[str, str]]] | None]] = []
    for n, keys in enumerate(MESSAGES):
        if n and not any(d[k] for k in keys):
            continue
        text = _fit(d, keys, lambda secs, first=(n == 0): render(secs, first), lambda t: len(t) > telegram.TEXT_MAX)
        out.append((text, buttons if n == 0 else None))
    return out


def telegram_rich(d: dict[str, Any]) -> list[str]:
    """텔레그램 리치 메시지(HTML). 첫 통은 제목, 건수, 필터 통과 새 공고와 마감 임박을 접는 블록의 표
    (판정 · 회사와 공고 · 점수 · 마감), 대시보드 버튼, 판정 설명. 둘째 통은 필터 밖 새 공고(걸린 이유)를 접는 블록에.
    보내기가 실패하면 run()이 일반 메시지로 대신 보낸다."""

    def table(items: list[dict[str, Any]], link_company: bool = True) -> str:
        rows = ['<tr><th></th><th align="left">회사 · 공고</th><th align="right">점수</th><th>마감</th></tr>']
        for it in items:
            score = "-" if it["score"] < 0 else f"{it['score']:g}"
            company = f'<a href="{html.escape(it["companyUrl"])}">{_esc(it["company"])}</a>' if link_company else _esc(it["company"])
            rows.append(f'<tr><td>{MARKS.get(it["verdict"] or "", "▫️")}</td>'
                        f'<td align="left"><b>{"★ " if it["interest"] else ""}{company}</b><br>'
                        f'<a href="{html.escape(it["url"])}">{_esc(it["name"])}</a>'
                        + (f'<br><i>필터 밖: {_esc(it["why"])}</i>' if it.get("why") else "") + '</td>'
                        f'<td align="right"><b>{score}</b></td><td align="center">{_esc(it["deadline"])}</td></tr>')
        return "<table striped compact>" + "".join(rows) + "</table>"

    def render(sections: list[dict[str, Any]], first: bool) -> str:
        c = d["counts"]
        parts = [f"<h3>{_esc(d['date'])} 오늘의 공고</h3>",
                 f"<p>새 공고 <b>{c['new']}</b> · 필터 통과 <b>{c['passed']}</b> · 마감 임박 <b>{c['soon']}</b></p>"] if first else []
        for sec in sections:
            if sec["key"] == "passed" and not sec["total"]:
                parts.append("<p>필터를 통과한 새 공고가 없어요.</p>")
                continue
            if not sec["total"]:
                continue
            body = (table(sec["items"], sec["key"] != "others") if sec["items"] else "") + (f"<p>{_rest_text(sec)}</p>" if sec["rest"] else "")
            parts.append(f"<details><summary>{_esc(sec['title'])} {sec['total']}건</summary>{body}</details>")
        if first:
            parts.append('<tg-button-row align="center">'
                         f'<tg-button type="url" style="primary" url="{html.escape(d["report"])}">리포트</tg-button>'
                         f'<tg-button type="url" url="{html.escape(d["jobs"])}">공고 목록</tg-button>'
                         f'<tg-button type="url" url="{html.escape(d["career"])}">커리어</tg-button></tg-button-row>')
            parts.append(f"<footer>{_legend()}</footer>")
        return "".join(parts)

    out = []
    for n, keys in enumerate(MESSAGES):
        if n and not any(d[k] for k in keys):
            continue
        out.append(_fit(d, keys, lambda secs, first=(n == 0): render(secs, first),
                        lambda t: len(t) > RICH_MAX or t.count("<tr>") > RICH_ROWS))
    return out


def kakao_message(d: dict[str, Any]) -> dict[str, Any]:
    """카카오 template_object. 리스트 템플릿은 항목 2~3개라 필터 통과 새 공고 상위 3건, 모자라면 마감 임박으로 채운다."""
    cfg = config.load("notify")["kakao"]

    def link(url: str) -> dict[str, str]:
        return {"web_url": url, "mobile_web_url": url}
    picks = [(it, "") for it in d["passed"][:cfg["top"]]]
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


def run(screen: dict[str, Any], db: Any, today: date, session: Any = None, again: bool = False) -> dict[str, Any]:
    """연결한 사람마다 켜 둔 채널로 아침 알림을 보낸다. 같은 날 두 번 보내지 않고(again이면 다시 보내며 그때는
    오늘 처음 본 공고만), 한 사람이 실패해도 나머지는 보낸다. 관리 화면에서 알림을 끈 사람에게는 보내지 않는다."""
    cfg = config.load("notify")
    defaults = config.load("filters")
    out: dict[str, Any] = {"errors": []}
    try:
        rows = db.select("settings", "select=user_id,filters,notify")
    except RuntimeError as e:  # 010_notify_settings.sql을 아직 안 돌렸으면 사람별 알림 설정 없이 보낸다
        out.setdefault("notes", []).append(f"알림 설정을 못 읽음: {str(e)[:120]}")
        rows = db.select("settings", "select=user_id,filters")
    settings = {r["user_id"]: r.get("filters") or {} for r in rows}
    off = {r["user_id"] for r in rows if not enabled(r.get("notify"))}
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
            cache[key] = digest(screen, {**defaults, **settings.get(user, {})}, matches, today, since, stages_of(user))
        return cache[key]

    def stages_of(user: str) -> dict[str, str]:
        try:
            rows = db.select("applications", f"select=posting_id,stage&user_id=eq.{user}")
        except RuntimeError as e:  # 007_applications.sql을 아직 안 돌렸으면 지원 상태 없이 보낸다
            out.setdefault("notes", []).append(f"지원 상태를 못 읽음: {str(e)[:120]}")
            return {}
        return {r["posting_id"]: r["stage"] for r in rows}

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
            if user in off:
                s["off"] = s.get("off", 0) + 1  # 관리 화면에서 알림을 끔
                continue
            last = link.get("last_sent_on")
            if last == today.isoformat():
                if not again:
                    s["skipped"] += 1  # 오늘 이미 보냄(수집을 다시 돌린 날)
                    continue
                last = None  # 다시 보낼 때는 오늘 처음 본 공고만
            try:
                d = summary_for(user, last)
                if channel == "telegram":
                    # 통마다 리치 메시지로 보내고, 실패하면 그 통부터 일반 메시지로 대신 보낸다(두 형식의 통 수는 같다).
                    # 첫 통이 갔으면 보낸 것으로 기록한다(다시 돌려도 첫 통이 또 가지 않게). 못 보낸 통은 오류로 남긴다
                    rich = telegram_rich(d) if cfg["telegram"].get("format") == "rich" else []
                    done = 0
                    try:
                        for i, (text, buttons) in enumerate(telegram_message(d)):
                            fallback = None
                            if i < len(rich):
                                try:
                                    telegram.send_rich(link["chat_id"], rich[i], session)
                                    done += 1
                                    continue
                                except telegram.TelegramError as e:  # 새 기능이라 막히면 일반 메시지로 대신 보낸다
                                    rich = []
                                    fallback = f"telegram {user[:8]}: 리치 메시지 실패({i + 1}통째), 일반 메시지로 보냄: {e}"
                            telegram.send(link["chat_id"], text, session, buttons=buttons)
                            done += 1
                            if fallback:
                                out.setdefault("notes", []).append(fallback)
                    except telegram.TelegramError as e:
                        if not done:
                            raise
                        out["errors"].append(f"{channel} {user[:8]}: {done}통만 보냄: {str(e)[:200]}")
                else:
                    tok = kakao.refresh(link["refresh_token"], session)
                    if tok.get("refresh_token"):  # 1개월 미만 남아 새로 받은 토큰. 바로 저장해야 다음 날도 보낼 수 있다
                        db.update(table, f"user_id=eq.{user}", token_values(tok))
                    kakao.send(tok["access_token"], kakao_message(d), session)
                if link.get("last_sent_on") != today.isoformat():
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
        raise ValueError(f"봇 {telegram.bot_name(session)}이 받은 메시지가 없다(최근 24시간). "
                         "텔레그램에서 이 봇과의 대화방을 열어 시작(/start)이나 아무 메시지를 보내고 다시 실행")
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
