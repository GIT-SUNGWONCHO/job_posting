from datetime import date

from jobpost import career
from jobpost.models import CompanyType


class Registry:
    def company_type(self, key, name=""):
        return CompanyType.LARGE if key == "big" else CompanyType.OTHER


def rec(uid, first, closed=None, job="data_eng", company="big", **kw):
    return {"uid": uid, "first_seen": first, "closed_on": closed, "job_type": {"id": job}, "company_key": company, **kw}


def test_daily_open_and_new_counts_per_job_type_and_company_type():
    state = {r["uid"]: r for r in [
        rec("a", "2026-10-13"), rec("b", "2026-10-13", closed="2026-10-15"), rec("c", "2026-10-14"),
        rec("d", "2026-10-15", company="small"), rec("e", "2026-10-14", overseas=True), rec("f", "2026-10-14", dup_of="a"),
    ]}
    out = career.build(state, Registry(), [], {}, {}, date(2026, 10, 15))
    assert out["days"] == ["2026-10-13", "2026-10-14", "2026-10-15"] and out["since"] == "2026-10-13"
    assert out["series"]["data_eng|대기업"] == {"open": [2, 3, 2], "new": [None, 1, 0]}  # 첫날은 새 공고로 세지 않는다
    assert out["series"]["data_eng|그 외"] == {"open": [0, 0, 1], "new": [None, 0, 1]}


def test_current_career_buckets_and_skills_from_bodies():
    postings = [{"id": "a", "company": "big", "jobType": "data_eng", "careerMin": 8, "noise": None},
                {"id": "b", "company": "big", "jobType": "data_eng", "careerMin": None, "noise": None},
                {"id": "c", "company": "big", "jobType": "data_eng", "careerMin": 2, "noise": "잡음"}]
    bodies = {"a": {"text": "Airflow와 Spark로 파이프라인"}, "b": {"text": "SQL, Airflow"}}
    out = career.build({}, Registry(), postings, {"big": {"type": "대기업"}}, bodies, date(2026, 10, 15))
    cur = out["current"]["data_eng|대기업"]
    assert cur["career"] == {"7-12": 1, "any": 1} and cur["withBody"] == 2
    assert dict(cur["skills"])["Airflow"] == 2


def test_bucket_treats_entry_level_and_upper_bound_only_as_under_three_years():
    assert career.bucket(None, 0) == "0-3"  # 신입
    assert career.bucket(None, 5) == "0-3"  # 경력 5년 이하
    assert career.bucket(0, None) == "any" and career.bucket(None, None) == "any"  # 연차 무관
    assert career.bucket(3, 7) == "3-7" and career.bucket(120, None) == "12+"


def test_duplicate_group_uses_earliest_first_seen_and_stays_open_while_any_member_is():
    state = {r["uid"]: r for r in [
        rec("a", "2026-10-14", closed="2026-10-15"),  # 대표는 늦게 처음 보고 먼저 내려갔다
        rec("f", "2026-10-13", dup_of="a"),           # 같은 공고가 다른 수집처에 먼저, 아직 열려 있다
    ]}
    out = career.build(state, Registry(), [], {}, {}, date(2026, 10, 15))
    assert out["series"]["data_eng|대기업"] == {"open": [1, 1, 1], "new": [None, 0, 0]}
    assert "Airflow" in out["dictionary"]



def test_backfill_counts_as_open_but_not_new():
    state = {r["uid"]: r for r in [
        rec("a", "2026-10-13"), rec("w1", "2026-10-14", backfill=True), rec("w2", "2026-10-15"),
        # 원티드 첫날 공고가 다른 수집처의 같은 날 새 공고와 묶이면 새 공고다
        rec("z", "2026-10-14"), rec("w3", "2026-10-14", dup_of="z", backfill=True),
    ]}
    out = career.build(state, Registry(), [], {}, {}, date(2026, 10, 15))
    assert out["series"]["data_eng|대기업"] == {"open": [1, 3, 4], "new": [None, 1, 1]}


def test_headhunting_postings_count_under_the_client_company_type():
    state = {r["uid"]: r for r in [rec("a", "2026-10-13"), rec("h", "2026-10-14", company="firm", client_type="대기업")]}
    out = career.build(state, Registry(), [], {}, {}, date(2026, 10, 14))
    assert out["series"]["data_eng|대기업"]["open"] == [1, 2]
    postings = [{"id": "h", "company": "firm", "jobType": "data_eng", "careerMin": 5, "noise": None, "clientType": "외국계"}]
    cur = career.current(postings, {"firm": {"type": "그 외"}}, {})
    assert list(cur) == ["data_eng|외국계"]
