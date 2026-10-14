from datetime import date

from test_recommend import BODIES, SCREEN

from jobpost import facts, feedback, profile

TODAY = date(2026, 10, 14)
V2 = {
    "schema": 2,
    "careers": [
        {"company": "한샘", "industry": "consumer", "start": "2016-12", "end": "2023-11",
         "roles": [{"role": "pi", "start": "2016-12", "end": "2018-03"},
                   {"role": "analyst", "start": "2018-04", "end": "2022-10"},
                   {"role": "data_eng", "start": "2022-11", "end": "2023-11"}]},
        {"company": "포스코이앤씨", "industry": "construction", "start": "2023-11", "end": "",
         "roles": [{"role": "other", "roleName": "BI 플랫폼 운영", "start": "2023-11", "end": "2025-12"}]},
    ],
    "targetRoles": ["data_eng"],
    "skills": [{"name": "SQL", "level": 4}, {"name": "Python", "level": 2}],
    "education": {"degree": "학사", "major": "건축공학", "majorGroup": "공학(기타)"},
    "english": "읽기·쓰기",
}


def test_months_and_role_years():
    assert profile.months("2026-01", "2026-09", TODAY) == 9
    assert profile.months("2026-01", "", TODAY) == 10  # 이번 달까지
    years = profile.role_years(V2, TODAY)
    assert round(years["데이터 엔지니어"], 1) == 1.1 and round(years["데이터 분석가"], 1) == 4.6
    assert "BI 플랫폼 운영" in years  # 기타는 직접 쓴 이름으로


def test_career_totals_drop_non_data_roles():
    total, data_years = profile.career_totals(V2, TODAY)
    assert round(total, 1) == 10.0 and round(data_years, 1) == 8.7  # PI 기획 16개월을 뺌


def test_rule_view_and_text():
    v = profile.rule_view(V2)
    assert v["careerStart"] == "2016-12" and v["currentRole"] == "other" and v["skills"] == ["SQL", "Python"]
    t = profile.text(V2, TODAY)
    assert "포스코이앤씨 (건설·부동산) 2023.11~현재" in t and "SQL(4 리드)" in t and "[학력] 학사 건축공학" in t


def test_facts_run_extracts_wanted_postings_once(tmp_path):
    class AI:
        model = "fake"

        def __init__(self):
            self.prompts = []

        def json(self, prompt, schema):
            self.prompts.append(prompt)
            return {"level": "시니어", "duties": ["파이프라인 구축"], "required_skills": ["Apache Spark", "Airflow"],
                    "preferred_skills": ["dbt"], "years": [], "domain_required": [], "domain_preferred": [],
                    "degree": "무관", "majors": [], "certs": [], "english": "적혀 있지 않음", "work_mode": "출근"}

    ai = AI()
    s = facts.run(tmp_path, SCREEN, BODIES, ["z:1", "z:2"], ai, "2026-10-14")
    assert s == {"wanted": 2, "pending": 0, "done": 1, "calls": 1}  # 본문 없는 z:2는 건너뜀
    assert facts.load(tmp_path)["z:1"]["facts"]["level"] == "시니어"
    assert facts.run(tmp_path, SCREEN, BODIES, ["z:1"], ai, "2026-10-15")["pending"] == 0 and len(ai.prompts) == 1


def test_skill_catalog_merges_dictionary_and_extracted_names():
    rows = {"z:1": {"facts": {"required_skills": ["Apache Spark", "Great Expectations"], "preferred_skills": []}},
            "z:2": {"facts": {"required_skills": ["great expectations"], "preferred_skills": ["그런 경험이 있으신 분을 찾고 있어요 정말로요 진짜로"]}}}
    cat = {c["name"]: c["count"] for c in facts.skill_catalog({"z:1": "Spark와 Airflow"}, rows)}
    assert cat["Spark"] == 1 and cat["Airflow"] == 1  # 사전 이름으로 맞춤
    assert cat["Great Expectations"] == 2  # 사전에 없어도 두 공고 이상이면 넣는다
    assert not any(len(n) > 30 for n in cat)


def test_feedback_report_groups_by_round():
    snap = {"score": 80, "rule": 70, "verdict": "고려", "company": "가나다", "title": "DE",
            "items": [{"kind": "핵심 업무", "weight": 60, "fit": "충족", "name": "파이프라인"}]}
    rows = [{"match_key": "g1-p3-m", "label": "bad", "comment": "주니어 공고", "snapshot": snap},
            {"match_key": "g1-p3-m", "label": "good", "comment": None, "snapshot": {**snap, "score": 55}}]
    lines = feedback.report(rows)
    assert lines[0].startswith("== 회차 g1-p3-m: 평가 2건")
    joined = "\n".join(lines)
    assert "× AI 80(고려) 규칙 70 | 가나다 | DE | 코멘트: 주니어 공고" in joined
    assert "핵심 업무: 가중치 60 / 60, 충족 100% / 100%" in joined
