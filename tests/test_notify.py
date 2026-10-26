from datetime import date

import pytest
import requests

from jobpost import config, kakao, notify, telegram

TODAY = date(2026, 10, 17)


def posting(pid, company="a", first="2026-10-17", deadline=None, title="Data Engineer", job="data_eng"):
    return {"id": pid, "company": company, "title": title, "jobType": job, "careerMin": 5, "careerMax": None,
            "regions": ["서울"], "noise": None, "firstSeen": first,
            "deadlineType": "date" if deadline else "always", "deadline": deadline}


SCREEN = {
    "companies": {"a": {"name": "가나다", "type": "대기업"}, "b": {"name": "라마바", "type": "그 외"}},
    "postings": [
        posting("z:1"), posting("z:2", deadline="2026-10-29"), posting("z:3", title="A&amp;B <ML>"), posting("z:4"),
        posting("z:5", company="b"),  # 기업 구분 필터에서 빠짐
        posting("z:6", first="2026-10-10", deadline="2026-10-19"),  # 지난 공고, 마감 임박
    ],
}
FILTERS = {"company_types": ["대기업"], "job_types": ["data_eng"]}
MATCHES = {"z:1": {"score": 70, "verdict": "고려", "kind": "ai"}, "z:2": {"score": 92, "verdict": "지원 추천", "kind": "ai"},
           "z:3": {"score": 40, "verdict": "비추천", "kind": "ai"}, "z:4": {"score": 88, "verdict": None, "kind": "rule"},
           "z:6": {"score": 81, "verdict": "지원 추천", "kind": "ai"}}


def test_digest_counts_and_orders_new_postings_that_pass_filters():
    d = notify.digest(SCREEN, FILTERS, MATCHES, TODAY)
    assert d["head"] == "10/17(토) 새 공고 5건 · 필터 통과 4건 · 마감 임박 1건"
    assert [it["id"] for it in d["new"]] == ["z:2", "z:4", "z:1", "z:3"]
    assert [it["info"] for it in d["new"][:2]] == ["92점 지원 추천 · D-12", "규칙 88점 · 상시"]
    assert d["new"][0]["url"] == "https://careermap-web.oroloov.workers.dev/#/job/z%3A2"
    assert [it["id"] for it in d["soon"]] == ["z:6"]


def test_applied_and_dismissed_postings_drop_out_and_interest_ones_lead_closing_soon():
    screen = {**SCREEN, "postings": [*SCREEN["postings"], posting("i:1", company="b", deadline="2026-10-18", first="2026-10-01")]}
    stages = {"z:2": "applied", "z:4": "dismissed", "i:1": "interest", "z:6": "interview"}
    d = notify.digest(screen, FILTERS, MATCHES, TODAY, stages=stages)
    assert [it["id"] for it in d["new"]] == ["z:1", "z:3"]  # 지원·관심 없음은 빼고
    assert [(it["id"], it["interest"]) for it in d["soon"]] == [("i:1", True)]  # 필터 밖이어도 관심 공고는, 면접 중인 공고는 빼고
    assert "★ <b>" not in notify.telegram_rich(d) and '<b>★ <a href="https://careermap-web.oroloov.workers.dev/#/company/b">라마바</a></b>' in notify.telegram_rich(d)


def test_new_postings_since_the_last_message_count_when_a_day_was_missed():
    screen = {**SCREEN, "postings": [posting("y:1", first="2026-10-16"), *SCREEN["postings"]]}
    assert "새 공고 5건" in notify.digest(screen, FILTERS, MATCHES, TODAY)["head"]
    assert "새 공고 6건" in notify.digest(screen, FILTERS, MATCHES, TODAY, since=date(2026, 10, 15))["head"]


def test_starred_companies_new_postings_come_regardless_of_filters_without_repeating_the_list():
    stars = {"a", "b"}
    d = notify.digest(SCREEN, FILTERS, MATCHES, TODAY, stages={"z:5": "dismissed"}, stars=stars)
    assert [it["id"] for it in d["stars"]] == []  # a는 위 목록에 다 보이고, b는 관심 없음
    d = notify.digest(SCREEN, FILTERS, MATCHES, TODAY, stars=stars, prefs=notify.prefs_of({"top": 5}))
    assert [it["id"] for it in d["stars"]] == ["z:5"] and d["top"] == 5
    d = notify.digest(SCREEN, FILTERS, MATCHES, TODAY, stars=stars, prefs={"enabled": True, "top": 1})
    assert [it["id"] for it in d["stars"]] == ["z:4", "z:1", "z:3", "z:5"]  # 위에 1건만 보이면 나머지 a 공고도
    assert "<summary>관심 회사 새 공고 4건</summary>" in notify.telegram_rich(d)
    assert "<b>관심 회사 새 공고</b> 4건\n<blockquote expandable>" in notify.telegram_message(d)[0]


def test_prefs_fall_back_to_config_values():
    assert notify.prefs_of(None) == {"enabled": True, "top": 10}
    assert notify.prefs_of({"enabled": False, "top": 7}) == {"enabled": False, "top": 10}  # 고를 수 없는 개수
    assert notify.prefs_of({"top": 20}) == {"enabled": True, "top": 20}

def test_telegram_message_lists_new_and_urgent_postings_as_escaped_html():
    text, buttons = notify.telegram_message(notify.digest(SCREEN, FILTERS, MATCHES, TODAY))
    assert text.startswith("<b>10/17(토) 오늘의 공고</b>\n새 공고 5 · 필터 통과 4 · 마감 임박 1\n\n<b>필터 통과 새 공고</b>")
    a = '<a href="https://careermap-web.oroloov.workers.dev/#/company/a">가나다</a>'  # 회사 이름은 회사 화면으로
    assert (f'🟢 <b>{a}</b>  92점 · D-12\n'
            '<a href="https://careermap-web.oroloov.workers.dev/#/job/z%3A2">Data Engineer</a>') in text
    assert f"▫️ <b>{a}</b>  88점 · 상시" in text  # 규칙 점수
    assert "A&amp;B &lt;ML&gt;" in text  # 태그가 아닌 <, >, &는 바꾼다
    assert f"<b>마감 임박</b> ★ 관심 공고와 70점 이상 1건\n<blockquote expandable>🟢 <b>{a}</b>  81점 · D-2" in text
    assert text.endswith("🟢 지원 추천 · 🟡 고려 · ⚪ 비추천")
    assert buttons == [[{"text": "리포트", "url": "https://careermap-web.oroloov.workers.dev/#/report"},
                        {"text": "공고 목록", "url": "https://careermap-web.oroloov.workers.dev/#/jobs"}, {"text": "커리어", "url": "https://careermap-web.oroloov.workers.dev/#/career"}]]


def test_telegram_message_folds_postings_after_the_first_five(monkeypatch):
    screen = {**SCREEN, "postings": [posting(f"m:{i}") for i in range(12)]}
    text, _ = notify.telegram_message(notify.digest(screen, FILTERS, {}, TODAY))
    head, folded = text.split("<blockquote expandable>")
    assert head.count("#/job/") == 5 and folded.count("#/job/") == 5  # 10건 중 5건은 접어 둔다
    assert "외 2건은 공고 목록에서" in text


def test_telegram_message_says_so_when_nothing_new_passes_and_stays_under_the_limit(monkeypatch):
    none = {**SCREEN, "postings": [SCREEN["postings"][4]]}
    assert "필터를 통과한 새 공고가 없어요." in notify.telegram_message(notify.digest(none, FILTERS, MATCHES, TODAY))[0]
    many = {**SCREEN, "postings": [posting(f"m:{i}", title="데이터 엔지니어 " * 60) for i in range(10)]}
    assert len(notify.telegram_message(notify.digest(many, FILTERS, {}, TODAY))[0]) <= telegram.TEXT_MAX


def test_kakao_message_uses_the_list_template_and_falls_back_to_text():
    msg = notify.kakao_message(notify.digest(SCREEN, FILTERS, MATCHES, TODAY))
    assert msg["object_type"] == "list" and len(msg["contents"]) == 3
    one = {**SCREEN, "postings": [SCREEN["postings"][1], SCREEN["postings"][5]]}
    msg = notify.kakao_message(notify.digest(one, FILTERS, MATCHES, TODAY))
    assert msg["contents"][1]["description"] == "마감 임박 · 81점 지원 추천 · D-2"
    none = {**SCREEN, "postings": [SCREEN["postings"][4]]}
    msg = notify.kakao_message(notify.digest(none, FILTERS, MATCHES, TODAY))
    assert msg["object_type"] == "text" and len(msg["text"]) <= 200


class FakeDB:
    def __init__(self, telegram_links=(), kakao_links=()):
        self.rows = {"settings": [], "telegram_links": list(telegram_links), "kakao_links": list(kakao_links),
                     "profiles": [{"user_id": "u1"}], "applications": [], "company_stars": [],
                     "matches": [{"posting_id": "z:2", "score": 92, "parts": {"kind": "ai", "verdict": "지원 추천"}}]}
        self.updates, self.inserted = [], []

    def select(self, table, query="select=*"):
        return self.rows[table]

    def update(self, table, query, values):
        self.updates.append((table, query, values))

    def insert(self, table, rows):
        self.inserted += rows


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("KAKAO_REST_KEY", "k")


def test_rich_message_puts_postings_in_tables_with_details_and_buttons():
    screen = {**SCREEN, "postings": [*SCREEN["postings"], *(posting(f"m:{i}") for i in range(4))]}
    rich = notify.telegram_rich(notify.digest(screen, FILTERS, MATCHES, TODAY))
    assert rich.startswith("<h3>10/17(토) 오늘의 공고</h3><p>새 공고 <b>9</b> · 필터 통과 <b>8</b> · 마감 임박 <b>1</b></p>"
                           "<h4>필터 통과 새 공고</h4><table striped compact>")
    assert ('<tr><td>🟢</td><td align="left"><b><a href="https://careermap-web.oroloov.workers.dev/#/company/a">가나다</a></b><br>'
            '<a href="https://careermap-web.oroloov.workers.dev/#/job/z%3A2">Data Engineer</a></td>'
            '<td align="right"><b>92</b></td><td align="center">D-12</td></tr>') in rich
    assert "A&amp;B &lt;ML&gt;" in rich
    assert "<details><summary>3건 더 보기</summary><table" in rich  # 8건 중 5건 다음은 접는다
    assert "<details><summary>마감 임박 1건 · ★ 관심 공고와 70점 이상</summary>" in rich
    assert '<tg-button type="url" style="primary" url="https://careermap-web.oroloov.workers.dev/#/report">리포트</tg-button>' in rich
    assert rich.endswith("<footer>🟢 지원 추천 · 🟡 고려 · ⚪ 비추천</footer>")


def test_run_sends_a_rich_message_once_a_day_and_kakao_only_when_switched_on(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append((chat, rich)))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": "2026-10-16"},
                                {"user_id": "u2", "chat_id": 43, "last_sent_on": "2026-10-17"}],
                kakao_links=[{"user_id": "u1", "refresh_token": "RT", "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s == {"telegram": {"linked": 2, "sent": 1, "skipped": 1}}  # 카톡은 config에서 꺼 둠
    assert sent[0][0] == 42 and sent[0][1].startswith("<h3>10/17(토)")
    assert db.updates == [("telegram_links", "user_id=eq.u1", {"last_sent_on": "2026-10-17"})]
    again = notify.run(SCREEN, db, TODAY, again=True)  # 모양 확인용으로 다시 보내기
    assert again == {"telegram": {"linked": 2, "sent": 2, "skipped": 0}} and len(db.updates) == 2


def test_run_skips_people_who_turned_the_alert_off_and_reads_their_stars(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append((chat, rich)))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None},
                                {"user_id": "u2", "chat_id": 43, "last_sent_on": None}])
    db.rows["settings"] = [{"user_id": "u1", "filters": FILTERS, "notify": {"top": 5}},
                           {"user_id": "u2", "filters": {}, "notify": {"enabled": False}}]
    db.rows["company_stars"] = [{"company_key": "b"}]
    s = notify.run(SCREEN, db, TODAY)
    assert s == {"telegram": {"linked": 2, "sent": 1, "skipped": 0, "off": 1}}
    assert [c for c, _ in sent] == [42] and "관심 회사 새 공고 1건" in sent[0][1]


def test_run_still_sends_before_the_notify_settings_column_exists(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append(chat))

    class Old(FakeDB):
        def select(self, table, query="select=*"):
            if "notify" in query or table == "company_stars":
                raise RuntimeError("Supabase GET 400 column settings.notify does not exist")
            return super().select(table, query)
    db = Old(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert sent == [42] and s["telegram"]["sent"] == 1 and len(s["notes"]) == 2


def test_rich_message_failure_falls_back_to_a_plain_message(monkeypatch, keys):
    def send_rich(chat, rich, s=None):
        raise telegram.TelegramError("텔레그램 sendRichMessage 400 Bad Request: can't parse rich message")
    sent = []
    monkeypatch.setattr(telegram, "send_rich", send_rich)
    monkeypatch.setattr(telegram, "send", lambda chat, text, s=None, buttons=None: sent.append((chat, text, buttons)))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s["telegram"]["sent"] == 1 and "errors" not in s  # 알림은 갔으니 실패로 치지 않는다
    assert "리치 메시지 실패" in s["notes"][0]
    assert sent[0][1].startswith("<b>10/17(토) 오늘의 공고</b>") and sent[0][2]


def test_plain_format_sends_the_text_message_with_buttons(monkeypatch, keys):
    monkeypatch.setitem(config.load("notify")["telegram"], "format", "text")
    sent = []
    monkeypatch.setattr(telegram, "send", lambda chat, text, s=None, buttons=None: sent.append((chat, text, buttons)))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    notify.run(SCREEN, db, TODAY)
    assert sent and sent[0][2][0][0]["text"] == "리포트"


def test_run_keeps_kakao_working_and_saves_a_rotated_token(monkeypatch, keys):
    monkeypatch.setitem(config.load("notify"), "channels", ["kakao"])
    monkeypatch.setattr(kakao, "refresh", lambda rt, s=None: {"access_token": "AT", "refresh_token": "RT2",
                                                              "refresh_token_expires_in": 5184000})
    sent = []
    monkeypatch.setattr(kakao, "send", lambda at, msg, s=None: sent.append(msg))
    db = FakeDB(kakao_links=[{"user_id": "u1", "refresh_token": "RT1", "last_sent_on": None}])
    assert notify.run(SCREEN, db, TODAY) == {"kakao": {"linked": 1, "sent": 1, "skipped": 0}}
    assert db.updates[0][2]["refresh_token"] == "RT2" and sent[0]["object_type"] == "list"


def test_run_reports_errors_without_stopping_other_people(monkeypatch, keys):
    def send(chat, text, s=None, buttons=None):
        if chat == 1:
            raise telegram.TelegramError("텔레그램 sendMessage 403 Forbidden: bot was blocked by the user")
    monkeypatch.setitem(config.load("notify")["telegram"], "format", "text")
    monkeypatch.setattr(telegram, "send", send)
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 1, "last_sent_on": None},
                                {"user_id": "u2", "chat_id": 2, "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s["telegram"]["sent"] == 1
    assert s["errors"] == ["telegram u1: 텔레그램 sendMessage 403 Forbidden: bot was blocked by the user"]


def test_telegram_request_errors_do_not_carry_the_token(monkeypatch, keys):
    class Boom:
        def post(self, url, **kw):
            raise requests.ConnectionError(f"Max retries exceeded with url: {url}")
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send(1, "hi", Boom())
    assert "secret" not in str(e.value) and e.value.__cause__ is None


def test_connect_telegram_saves_the_latest_private_chat(monkeypatch, keys):
    monkeypatch.setattr(telegram, "latest_chat", lambda s=None: {"id": 777, "type": "private"})
    db = FakeDB()
    assert notify.connect_telegram(db) == "u1"
    assert db.inserted[0]["chat_id"] == 777 and db.inserted[0]["last_sent_on"] is None
    monkeypatch.setattr(telegram, "latest_chat", lambda s=None: {"id": -5, "type": "group"})
    with pytest.raises(ValueError):
        notify.connect_telegram(db)
    monkeypatch.setattr(telegram, "latest_chat", lambda s=None: None)
    monkeypatch.setattr(telegram, "bot_name", lambda s=None: "@careermap_bot")
    with pytest.raises(ValueError, match="@careermap_bot"):  # 어느 봇에 보내야 하는지 알려 준다
        notify.connect_telegram(db)


def test_connect_kakao_stores_the_token_for_the_only_profile(monkeypatch):
    seen = {}

    def exchange(code, redirect_uri, s=None):
        seen.update(code=code, redirect_uri=redirect_uri)
        return {"access_token": "AT", "refresh_token": "RT", "refresh_token_expires_in": 5184000}
    monkeypatch.setattr(kakao, "exchange", exchange)
    db = FakeDB()
    assert notify.connect_kakao(db, " CODE \n") == "u1"
    assert seen == {"code": "CODE", "redirect_uri": "https://careermap-web.oroloov.workers.dev/kakao"}
    assert db.inserted[0]["refresh_token"] == "RT" and db.inserted[0]["last_sent_on"] is None
