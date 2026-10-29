from datetime import date, datetime

from jobpost.models import Detail, Posting, Source
from jobpost.store import Store


def _p(source, sid, title="데이터 엔지니어"):
    return Posting(source=source, source_id=sid, url="u", company="회사", title=title)


def test_new_seen_closed(tmp_path):
    s = Store(tmp_path)
    day1, day2 = date(2026, 10, 13), date(2026, 10, 14)
    new, closed = s.ingest(day1, [_p(Source.ZIGHANG, "a"), _p(Source.SARAMIN, "1")],
                           {"zighang", "saramin"})
    assert sorted(new) == ["saramin:1", "zighang:a"] and closed == []
    s.save()

    s = Store(tmp_path)
    # 다음 날: 직행 a는 사라지고 b가 새로 생김. 사람인은 수집 실패(완료 아님)
    new, closed = s.ingest(day2, [_p(Source.ZIGHANG, "b")], {"zighang"})
    assert new == ["zighang:b"]
    assert closed == ["zighang:a"]  # 사람인 1은 수집이 완료되지 않아 마감으로 보지 않는다
    assert s.state["zighang:a"]["closed_on"] == "2026-10-14"
    assert s.state["saramin:1"]["closed_on"] is None
    assert s.state["zighang:b"]["first_seen"] == "2026-10-14"
    s.save()

    stored = Store(tmp_path).load_postings()
    assert set(stored) == {"zighang:a", "saramin:1", "zighang:b"}


def test_reopen_and_same_day_rerun(tmp_path):
    s = Store(tmp_path)
    d1, d2, d3 = date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)
    s.ingest(d1, [_p(Source.REMEMBER, "9")], {"remember"})
    s.ingest(d2, [], {"remember"})
    assert s.state["remember:9"]["closed_on"] == "2026-10-14"
    s.ingest(d3, [_p(Source.REMEMBER, "9", title="데이터 엔지니어(수정)")], {"remember"})
    assert s.state["remember:9"]["closed_on"] is None
    assert s.state["remember:9"]["title"] == "데이터 엔지니어(수정)"
    # 같은 날 다시 돌려도 새 공고로 세지 않는다
    new, _ = s.ingest(d3, [_p(Source.REMEMBER, "9")], {"remember"})
    assert new == []


def test_details_mark_state(tmp_path):
    s = Store(tmp_path)
    d = date(2026, 10, 13)
    s.ingest(d, [_p(Source.ZIGHANG, "a")], {"zighang"})
    s.add_details(d, [Detail(uid="zighang:a", fetched_at=datetime(2026, 10, 13), description="본문")])
    assert s.state["zighang:a"]["detail"] is True
    assert (tmp_path / "details" / "2026" / "10" / "13.jsonl.gz").exists()


def test_new_source_first_day_is_backfill(tmp_path):
    s = Store(tmp_path)
    s.ingest(date(2026, 10, 13), [_p(Source.ZIGHANG, "a")], {"zighang"})
    # 첫 수집(상태가 비어 있음)은 표시하지 않는다
    assert "backfill" not in s.state["zighang:a"]
    # 원티드를 처음 붙인 날: 원래 열려 있던 공고. 같은 날 기존 수집처의 새 공고는 그대로 새 공고
    s.ingest(date(2026, 10, 14), [_p(Source.ZIGHANG, "a"), _p(Source.ZIGHANG, "b"), _p(Source.WANTED, "1")],
             {"zighang", "wanted"})
    assert s.state["wanted:1"]["backfill"] is True
    assert "backfill" not in s.state["zighang:b"]
    # 다음 날부터 원티드에서 처음 본 공고는 새 공고
    s.ingest(date(2026, 10, 15), [_p(Source.WANTED, "1"), _p(Source.WANTED, "2")], {"wanted"})
    assert "backfill" not in s.state["wanted:2"]


def test_same_day_partial_rerun_merges_sources(tmp_path):
    s = Store(tmp_path)
    day = date(2026, 10, 30)
    s.save_run(day, {"date": "2026-10-30", "sources": {"zighang": {"fetched": 1}}, "details": {"zighang": {"fetched": 1}}})
    s.save_run(day, {"date": "2026-10-30", "sources": {"jobkorea": {"fetched": 2}}, "details": {}})
    import json
    run = json.loads((tmp_path / "runs" / "2026-10-30.json").read_text(encoding="utf-8"))
    assert set(run["sources"]) == {"zighang", "jobkorea"} and set(run["details"]) == {"zighang"}
