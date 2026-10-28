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


def test_digest_has_three_sections_all_passed_others_and_closing_soon():
    d = notify.digest(SCREEN, FILTERS, MATCHES, TODAY)
    assert d["head"] == "10/17(토) 새 공고 5건 · 필터 통과 4건 · 마감 임박 1건"
    assert [it["id"] for it in d["passed"]] == ["z:2", "z:4", "z:1", "z:3"]  # 전부, 점수 높은 순
    assert [it["id"] for it in d["others"]] == ["z:5"]  # 필터 밖(기업 구분)
    assert [it["id"] for it in d["soon"]] == ["z:6"]
    assert [it["info"] for it in d["passed"][:2]] == ["92점 지원 추천 · D-12", "규칙 88점 · 상시"]
    assert d["passed"][0]["url"] == "https://careermap-web.oroloov.workers.dev/#/job/z%3A2" and d["passed"][0]["companyUrl"] == "https://careermap-web.oroloov.workers.dev/#/company/a"


def test_applied_dismissed_and_noise_drop_out_and_interest_ones_lead_closing_soon():
    screen = {**SCREEN, "postings": [*SCREEN["postings"], posting("i:1", company="b", deadline="2026-10-18", first="2026-10-01"),
                                     {**posting("n:1", company="b"), "noise": "잡음"}]}
    stages = {"z:2": "applied", "z:4": "dismissed", "i:1": "interest", "z:6": "interview", "z:5": "dismissed"}
    d = notify.digest(screen, FILTERS, MATCHES, TODAY, stages=stages)
    assert [it["id"] for it in d["passed"]] == ["z:1", "z:3"] and d["others"] == []  # 잡음·지원·관심 없음은 빼고
    assert [(it["id"], it["interest"]) for it in d["soon"]] == [("i:1", True)]  # 필터 밖이어도 관심 공고는, 면접 중인 공고는 빼고
    assert '<b>★ <a href="https://careermap-web.oroloov.workers.dev/#/company/b">라마바</a></b>' in notify.telegram_rich(d)[0]


def test_new_postings_since_the_last_message_count_when_a_day_was_missed():
    screen = {**SCREEN, "postings": [posting("y:1", first="2026-10-16"), *SCREEN["postings"]]}
    assert "새 공고 5건" in notify.digest(screen, FILTERS, MATCHES, TODAY)["head"]
    assert "새 공고 6건" in notify.digest(screen, FILTERS, MATCHES, TODAY, since=date(2026, 10, 15))["head"]


def test_rich_messages_fold_every_section_and_send_the_others_separately():
    screen = {**SCREEN, "postings": [*SCREEN["postings"], *(posting(f"m:{i}") for i in range(4))]}
    main, others = notify.telegram_rich(notify.digest(screen, FILTERS, MATCHES, TODAY))
    assert main.startswith("<h3>10/17(토) 오늘의 공고</h3><p>새 공고 <b>9</b> · 필터 통과 <b>8</b> · 마감 임박 <b>1</b></p>"
                           "<details><summary>필터 통과 새 공고 8건</summary><table striped compact>")
    assert main.count("#/job/m%3A") == 4  # 필터 통과는 전부
    assert ('<tr><td>🟢</td><td align="left"><b><a href="https://careermap-web.oroloov.workers.dev/#/company/a">가나다</a></b><br>'
            '<a href="https://careermap-web.oroloov.workers.dev/#/job/z%3A2">Data Engineer</a></td>'
            '<td align="right"><b>92</b></td><td align="center">D-12</td></tr>') in main
    assert "A&amp;B &lt;ML&gt;" in main
    assert "<details><summary>마감 임박 · ★ 관심 공고와 70점 이상 1건</summary><table" in main
    assert "필터 밖" not in main  # 첫 통은 짧게(앱이 더보기로 자르지 않게)
    assert '<tg-button type="url" style="primary" url="https://careermap-web.oroloov.workers.dev/#/report">리포트</tg-button>' in main
    assert main.endswith("<footer>🟢 지원 추천 · 🟡 고려 · ⚪ 비추천</footer>")
    assert others.startswith("<details><summary>필터 밖 새 공고(참고) 1건</summary><table")
    assert "<br><i>필터 밖: 기업 구분 그 외</i></td>" in others  # 걸린 이유


def test_plain_messages_fold_every_section_and_send_the_others_separately():
    (text, buttons), (others, none) = notify.telegram_message(notify.digest(SCREEN, FILTERS, MATCHES, TODAY))
    a = '<a href="https://careermap-web.oroloov.workers.dev/#/company/a">가나다</a>'
    assert text.startswith("<b>10/17(토) 오늘의 공고</b>\n새 공고 5 · 필터 통과 4 · 마감 임박 1\n\n<b>필터 통과 새 공고</b> 4건\n"
                           f"<blockquote expandable>🟢 <b>{a}</b>  92점 · D-12\n<a href=\"https://careermap-web.oroloov.workers.dev/#/job/z%3A2\">Data Engineer</a>")
    assert "▫️ <b>" + a + "</b>  88점 · 상시" in text  # 규칙 점수
    assert "A&amp;B &lt;ML&gt;" in text  # 태그가 아닌 <, >, &는 바꾼다
    assert "<b>마감 임박 · ★ 관심 공고와 70점 이상</b> 1건\n<blockquote expandable>🟢 <b>" + a + "</b>  81점 · D-2" in text
    assert text.endswith("🟢 지원 추천 · 🟡 고려 · ⚪ 비추천")
    assert [b["text"] for b in buttons[0]] == ["리포트", "공고 목록", "커리어"]
    assert others.startswith("<b>필터 밖 새 공고(참고)</b> 1건\n<blockquote expandable>") and none is None
    assert "#/job/z%3A5\">Data Engineer</a>\n<i>필터 밖: 기업 구분 그 외</i>" in others


def test_only_one_message_when_nothing_is_outside_the_filters():
    only = {**SCREEN, "postings": SCREEN["postings"][:4]}
    assert len(notify.telegram_rich(notify.digest(only, FILTERS, MATCHES, TODAY))) == 1
    assert len(notify.telegram_message(notify.digest(only, FILTERS, MATCHES, TODAY))) == 1


def test_messages_stay_under_telegram_limits_on_a_busy_day():
    many = {**SCREEN, "postings": [posting(f"m:{i}", company="a" if i % 2 else "b", title="데이터 엔지니어 채용 " * 8)
                                   for i in range(400)]}
    d = notify.digest(many, FILTERS, {}, TODAY)
    assert len(d["passed"]) == 200 and len(d["others"]) == 200
    for rich in notify.telegram_rich(d):
        assert len(rich) <= notify.RICH_MAX + 1000 and rich.count("<tr>") <= notify.RICH_ROWS
    assert "건은 걸린 조건이 더 많은 공고라 줄였어요" in notify.telegram_rich(d)[1]  # 필터 밖은 줄이고 외 N건
    texts = [text for text, _ in notify.telegram_message(d)]
    assert all(len(t) <= telegram.TEXT_MAX for t in texts)
    assert "건은 공고 목록에서" in texts[0] and "줄였어요" in texts[1]


def test_says_so_when_nothing_new_passes():
    none = {**SCREEN, "postings": [SCREEN["postings"][4]]}
    assert "필터를 통과한 새 공고가 없어요." in notify.telegram_message(notify.digest(none, FILTERS, MATCHES, TODAY))[0][0]
    assert "필터를 통과한 새 공고가 없어요." in notify.telegram_rich(notify.digest(none, FILTERS, MATCHES, TODAY))[0]


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
                     "profiles": [{"user_id": "u1"}], "applications": [],
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


def test_run_sends_a_rich_message_once_a_day_and_kakao_only_when_switched_on(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append((chat, rich)))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": "2026-10-16"},
                                {"user_id": "u2", "chat_id": 43, "last_sent_on": "2026-10-17"}],
                kakao_links=[{"user_id": "u1", "refresh_token": "RT", "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s == {"telegram": {"linked": 2, "sent": 1, "skipped": 1}}  # 카톡은 config에서 꺼 둠
    assert [c for c, _ in sent] == [42, 42] and sent[0][1].startswith("<h3>10/17(토)")  # 첫 통과 필터 밖 한 통
    assert db.updates == [("telegram_links", "user_id=eq.u1", {"last_sent_on": "2026-10-17"})]
    again = notify.run(SCREEN, db, TODAY, again=True)  # 모양 확인용으로 다시 보내기
    assert again == {"telegram": {"linked": 2, "sent": 2, "skipped": 0}} and len(db.updates) == 2


def test_run_skips_people_who_turned_the_alert_off(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append(chat))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None},
                                {"user_id": "u2", "chat_id": 43, "last_sent_on": None}])
    db.rows["settings"] = [{"user_id": "u1", "filters": FILTERS, "notify": {}},
                           {"user_id": "u2", "filters": {}, "notify": {"enabled": False}}]
    assert notify.run(SCREEN, db, TODAY) == {"telegram": {"linked": 2, "sent": 1, "skipped": 0, "off": 1}}
    assert sent == [42, 42]


def test_run_still_sends_before_the_notify_settings_column_exists(monkeypatch, keys):
    sent = []
    monkeypatch.setattr(telegram, "send_rich", lambda chat, rich, s=None: sent.append(chat))

    class Old(FakeDB):
        def select(self, table, query="select=*"):
            if "notify" in query:
                raise RuntimeError("Supabase GET 400 column settings.notify does not exist")
            return super().select(table, query)
    db = Old(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert sent == [42, 42] and s["telegram"]["sent"] == 1 and len(s["notes"]) == 1


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
    assert len(sent) == 2 and sent[1][1].startswith("<b>필터 밖 새 공고(참고)</b>")


def test_a_failed_second_rich_message_falls_back_without_repeating_the_first(monkeypatch, keys):
    rich, plain = [], []

    def send_rich(chat, part, s=None):
        if rich:
            raise telegram.TelegramError("텔레그램 sendRichMessage 400 Bad Request: too many blocks")
        rich.append(part)
    monkeypatch.setattr(telegram, "send_rich", send_rich)
    monkeypatch.setattr(telegram, "send", lambda chat, text, s=None, buttons=None: plain.append(text))
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    notify.run(SCREEN, db, TODAY)
    assert len(rich) == 1 and len(plain) == 1 and plain[0].startswith("<b>필터 밖 새 공고(참고)</b>")


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


def test_reasons_name_every_filter_a_posting_missed(monkeypatch):
    screen = {**SCREEN, "jobTypes": [{"id": "analyst", "name": "데이터 분석가", "short": "데이터 분석"}],
              "postings": [{**posting("o:1", company="b", job="analyst"), "careerMin": 2, "careerMax": 4, "career": "경력 2~4년",
                            "regions": ["부산"]}]}
    filters = {**FILTERS, "career": {"min": 7, "max": 15}, "regions": ["서울"]}
    d = notify.digest(screen, filters, {}, TODAY)
    assert d["others"][0]["why"] == "직무 데이터 분석 · 기업 구분 그 외 · 경력 2~4년 · 지역 부산"
    monkeypatch.setitem(config.load("notify"), "others_reason", False)  # 필터가 안정되면 끈다
    assert notify.digest(screen, filters, {}, TODAY)["others"][0]["why"] is None


def test_header_counts_what_the_messages_hold_and_names_the_days_covered():
    screen = {**SCREEN, "postings": [*SCREEN["postings"], {**posting("n:1", company="b"), "noise": "잡음"},
                                     posting("y:1", first="2026-10-15")]}
    d = notify.digest(screen, FILTERS, MATCHES, TODAY, stages={"z:3": "dismissed"}, since=date(2026, 10, 14))
    assert d["counts"] == {"new": len(d["passed"]) + len(d["others"]), "passed": 4, "soon": 1}  # 잡음·관심 없음은 세지 않는다
    assert d["date"] == "10/15~10/17(토)"  # 며칠 만에 보내면 기간
    low = notify.digest(SCREEN, FILTERS, {**MATCHES, "z:6": {"score": 50, "kind": "ai"}}, TODAY)
    assert low["counts"]["soon"] == 0 and low["soon"] == []  # 70점 아래뿐이면 건수도 0


def test_others_closest_to_my_filters_come_first_without_company_links():
    screen = {**SCREEN, "postings": [{**posting("o:far", company="b", job="labeling"), "regions": ["부산"]},
                                     posting("o:near", company="b")]}
    d = notify.digest(screen, {**FILTERS, "regions": ["서울"]}, {}, TODAY)
    assert [it["id"] for it in d["others"]] == ["o:near", "o:far"]  # 걸린 조건 1개 → 3개
    others = notify.telegram_rich(d)[1]
    assert "#/company/" not in others and "<b>라마바</b>" in others


def test_a_first_message_that_went_out_still_counts_when_the_second_fails(monkeypatch, keys):
    monkeypatch.setitem(config.load("notify")["telegram"], "format", "text")
    sent = []

    def send(chat, text, s=None, buttons=None):
        if sent:
            raise telegram.TelegramError("텔레그램 sendMessage 429 Too Many Requests")
        sent.append(text)
    monkeypatch.setattr(telegram, "send", send)
    db = FakeDB(telegram_links=[{"user_id": "u1", "chat_id": 42, "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s["telegram"]["sent"] == 1 and db.updates == [("telegram_links", "user_id=eq.u1", {"last_sent_on": "2026-10-17"})]
    assert s["errors"] == ["telegram u1: 1통만 보냄: 텔레그램 sendMessage 429 Too Many Requests"]


def test_digest_uses_list_title():
    screen = {**SCREEN, "postings": [{**posting("z:1", title="[가나다] 데이터 엔지니어 채용"), "listTitle": "데이터 엔지니어"}]}
    d = notify.digest(screen, FILTERS, MATCHES, TODAY)
    assert d["passed"][0]["name"] == "데이터 엔지니어" and d["passed"][0]["title"] == "가나다 · 데이터 엔지니어"
