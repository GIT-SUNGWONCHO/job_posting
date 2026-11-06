import requests

from jobpost import db


class FlakySession:
    """첫 요청은 시간 초과, 그다음은 성공하는 연결."""
    made = 0

    def __init__(self, fail=True):
        FlakySession.made += 1
        self.fail = fail

    def request(self, method, url, **kw):
        if self.fail:
            raise requests.Timeout("read timed out")
        resp = requests.Response()
        resp.status_code, resp._content = 200, b"[]"
        resp.request = requests.Request(method, url).prepare()
        return resp


def test_stale_connection_is_retried_on_a_fresh_one(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_x")
    monkeypatch.setattr(db.requests, "Session", lambda: FlakySession(fail=False))
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    store = db.DB(session=FlakySession())
    assert store.select("matches") == []
    assert isinstance(store.http, FlakySession) and not store.http.fail


def test_long_idle_connection_is_replaced_before_sending(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_x")
    monkeypatch.setattr(db.requests, "Session", lambda: FlakySession(fail=False))
    store = db.DB(session=FlakySession())  # 이 연결로 보내면 시간 초과
    store._used -= 300  # AI를 부르느라 5분 쉼
    slept = []
    monkeypatch.setattr(db.time, "sleep", slept.append)
    assert store.select("matches") == [] and not slept  # 기다리지 않고 새 연결로 바로


class PagedSession:
    """2,500줄짜리 표. limit·offset만큼 돌려준다."""
    def __init__(self):
        self.urls = []

    def request(self, method, url, **kw):
        import json
        from urllib.parse import parse_qs, urlparse
        self.urls.append(url)
        q = parse_qs(urlparse(url).query)
        lim, off = int(q.get("limit", ["1000"])[0]), int(q.get("offset", ["0"])[0])
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps([{"i": i} for i in range(off, min(off + lim, 2500))]).encode()
        resp.request = requests.Request(method, url).prepare()
        return resp


def test_select_reads_every_page(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_x")
    s = PagedSession()
    store = db.DB(session=s)
    rows = store.select("matches", "select=posting_id&user_id=eq.u")
    assert len(rows) == 2500 and len(s.urls) == 3
    assert "order=user_id,posting_id" in s.urls[0]
    assert len(store.select("matches", "select=posting_id&limit=10&offset=0")) == 10  # limit이 있으면 한 번만
