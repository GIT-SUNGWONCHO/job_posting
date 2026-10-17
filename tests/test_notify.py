from datetime import date

from jobpost import kakao, notify

TODAY = date(2026, 10, 17)


def posting(pid, company="a", first="2026-10-17", deadline=None, title="Data Engineer", job="data_eng"):
    return {"id": pid, "company": company, "title": title, "jobType": job, "careerMin": 5, "careerMax": None,
            "regions": ["서울"], "noise": None, "firstSeen": first,
            "deadlineType": "date" if deadline else "always", "deadline": deadline}


SCREEN = {
    "companies": {"a": {"name": "가나다", "type": "대기업"}, "b": {"name": "라마바", "type": "그 외"}},
    "postings": [
        posting("z:1"), posting("z:2", deadline="2026-10-29"), posting("z:3"), posting("z:4"),
        posting("z:5", company="b"),  # 기업 구분 필터에서 빠짐
        posting("z:6", first="2026-10-10", deadline="2026-10-19"),  # 지난 공고, 마감 임박
    ],
}
FILTERS = {"company_types": ["대기업"], "job_types": ["data_eng"]}
MATCHES = {"z:1": {"score": 70, "verdict": "고려", "kind": "ai"}, "z:2": {"score": 92, "verdict": "지원 추천", "kind": "ai"},
           "z:3": {"score": 40, "verdict": "비추천", "kind": "ai"}, "z:4": {"score": 88, "verdict": None, "kind": "rule"},
           "z:6": {"score": 81, "verdict": "지원 추천", "kind": "ai"}}


def test_list_message_shows_top_new_postings_that_pass_filters():
    msg = notify.message(SCREEN, FILTERS, MATCHES, TODAY)
    assert msg["object_type"] == "list"
    assert msg["header_title"] == "10/17(토) 새 공고 5건 · 필터 통과 4건 · 마감 임박 1건"
    assert [c["title"] for c in msg["contents"]] == ["가나다 · Data Engineer"] * 3
    assert [c["description"] for c in msg["contents"]] == ["92점 지원 추천 · D-12", "규칙 88점 · 상시", "70점 고려 · 상시"]
    assert msg["contents"][0]["link"]["web_url"] == "https://careermap-web.oroloov.workers.dev/#/job/z%3A2"
    assert len(msg["buttons"]) == 2


def test_new_postings_since_the_last_message_count_when_a_day_was_missed():
    screen = {**SCREEN, "postings": [posting("y:1", first="2026-10-16"), *SCREEN["postings"]]}
    assert "새 공고 5건" in notify.message(screen, FILTERS, MATCHES, TODAY)["header_title"]
    assert "새 공고 6건" in notify.message(screen, FILTERS, MATCHES, TODAY, since=date(2026, 10, 15))["header_title"]


def test_one_new_posting_is_padded_with_an_urgent_one_and_none_becomes_text():
    one = {**SCREEN, "postings": [SCREEN["postings"][1], SCREEN["postings"][5]]}
    msg = notify.message(one, FILTERS, MATCHES, TODAY)
    assert msg["object_type"] == "list"
    assert msg["contents"][1]["description"] == "마감 임박 · 81점 지원 추천 · D-2"
    none = {**SCREEN, "postings": [SCREEN["postings"][4]]}
    msg = notify.message(none, FILTERS, MATCHES, TODAY)
    assert msg["object_type"] == "text" and "필터를 통과한 새 공고가 없어요" in msg["text"] and len(msg["text"]) <= 200


class FakeDB:
    def __init__(self, links):
        self.rows = {"settings": [], "kakao_links": links, "profiles": [{"user_id": "u1"}],
                     "matches": [{"posting_id": "z:2", "score": 92, "parts": {"kind": "ai", "verdict": "지원 추천"}}]}
        self.updates, self.inserted = [], []

    def select(self, table, query="select=*"):
        return self.rows[table]

    def update(self, table, query, values):
        self.updates.append((table, query, values))

    def insert(self, table, rows):
        self.inserted += rows


def test_run_refreshes_saves_a_rotated_token_and_sends_once_a_day(monkeypatch):
    sent = []
    monkeypatch.setattr(kakao, "refresh", lambda rt, s=None: {"access_token": "AT", "refresh_token": "RT2",
                                                              "refresh_token_expires_in": 5184000})
    monkeypatch.setattr(kakao, "send", lambda at, msg, s=None: sent.append((at, msg)))
    db = FakeDB([{"user_id": "u1", "refresh_token": "RT1", "last_sent_on": "2026-10-16"},
                 {"user_id": "u2", "refresh_token": "RT9", "last_sent_on": "2026-10-17"}])
    s = notify.run(SCREEN, db, TODAY)
    assert s == {"linked": 2, "sent": 1, "skipped": 1}
    assert sent[0][0] == "AT" and sent[0][1]["object_type"] in ("list", "text")
    assert db.updates[0][2]["refresh_token"] == "RT2"  # 바뀐 토큰은 바로 저장
    assert db.updates[-1] == ("kakao_links", "user_id=eq.u1", {"last_sent_on": "2026-10-17"})


def test_run_reports_errors_without_stopping_other_people(monkeypatch):
    def refresh(rt, s=None):
        if rt == "bad":
            raise kakao.KakaoError("카카오 토큰 401 KOE322 만료")
        return {"access_token": "AT"}
    monkeypatch.setattr(kakao, "refresh", refresh)
    monkeypatch.setattr(kakao, "send", lambda at, msg, s=None: None)
    db = FakeDB([{"user_id": "u1", "refresh_token": "bad", "last_sent_on": None},
                 {"user_id": "u2", "refresh_token": "ok", "last_sent_on": None}])
    s = notify.run(SCREEN, db, TODAY)
    assert s["sent"] == 1 and s["errors"] == ["u1: 카카오 토큰 401 KOE322 만료"]


def test_connect_stores_the_token_for_the_only_profile(monkeypatch):
    seen = {}

    def exchange(code, redirect_uri, s=None):
        seen.update(code=code, redirect_uri=redirect_uri)
        return {"access_token": "AT", "refresh_token": "RT", "refresh_token_expires_in": 5184000}
    monkeypatch.setattr(kakao, "exchange", exchange)
    db = FakeDB([])
    assert notify.connect(db, " CODE \n") == "u1"
    assert seen == {"code": "CODE", "redirect_uri": "https://careermap-web.oroloov.workers.dev/kakao"}
    assert db.inserted[0]["user_id"] == "u1" and db.inserted[0]["refresh_token"] == "RT"
    assert db.inserted[0]["last_sent_on"] is None
