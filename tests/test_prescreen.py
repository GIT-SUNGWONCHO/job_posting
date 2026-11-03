from datetime import date

from jobpost import prescreen

TODAY = date(2026, 11, 3)
PROFILE = {"schema": 2, "careers": [{"company": "가람물산", "industry": "commerce", "start": "2016-01", "end": None,
                                     "roles": [{"role": "data_eng", "start": "2016-01", "end": None}]}],
           "skills": [{"name": "Python", "level": 3}, {"name": "Airflow", "level": 3}, {"name": "Spark", "level": 1}],
           "education": {"degree": "학사"}}


def facts(**kw):
    base = {"level": "적혀 있지 않음", "required_skills": [], "preferred_skills": [], "years": [], "domain_required": [],
            "degree": "적혀 있지 않음"}
    return {"facts": {**base, **kw}}


def test_rule_v3_scores_fit_and_misfit():
    good = prescreen.rule_v3(PROFILE, {"careerMin": 5}, facts(required_skills=["Python", "Airflow"], level="시니어",
                                                                years=[{"area": "데이터 엔지니어링", "min": 5}]), TODAY)
    assert good["score"] == 100 and good["why"] == []
    junior = prescreen.rule_v3(PROFILE, {"careerMax": 3}, facts(required_skills=["Spark"], level="주니어",
                                                                 degree="박사", domain_required=["bank"]), TODAY)
    assert junior["score"] < 40 and set(junior["why"]) == {"skills", "level", "domain", "degree"}
    assert prescreen.rule_v3(PROFILE, {}, None, TODAY) is None


def test_batch_line_shows_facts():
    line = prescreen.batch_line(1, {"title": "Data Engineer", "career": "경력 5년 이상"},
                                facts(required_skills=["Python"], level="시니어"))
    assert line.startswith("1. Data Engineer") and "필수 Python" in line
