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
