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
    assert "포스코이앤씨 (건설·부동산) 2023.11~현재" in t and "SQL(4 전문)" in t and "[학력] 학사 건축공학" in t


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


def test_feedback_metrics_and_report():
    labels = {"a": "good", "b": "good", "c": "bad", "d": "maybe"}
    scores = {"a": 90, "b": 50, "c": 70, "d": 60}
    m = feedback.metrics(list(labels), labels, scores.get)
    assert m == {"n": 4, "top10_good": 2, "top20_bad": 1, "pairs": 0.5}  # a>c, b<c

    sample = [{"id": k, "company": "회사", "title": f"공고 {k}"} for k in "abcde"]
    item = {"kind": "핵심 업무", "weight": 60, "fit": "충족", "name": "파이프라인", "posting": "-", "me": "-"}
    matches = [{"user_id": "u1", "posting_id": k, "score": v, "score_v": 1, "reason_meta": {"model": "fake"},
                "parts": {"kind": "ai", "rule": 80, "verdict": "고려", "items": [item]}} for k, v in scores.items()]
    rows = [{"user_id": "u1", "posting_id": k, "label": v, "comment": None, "match_key": "g1"} for k, v in labels.items()]
    rows.append({"user_id": "u1", "posting_id": "b", "label": "good", "comment": "핵심 업무가 딱 맞음", "match_key": "g2"})
    text = "\n".join(feedback.report(sample, matches, rows))
    assert "기준 샘플 5건 중 평가 4건 ○ 2 △ 1 × 1, AI 결과 4건 (지침 v1 · fake)" in text
    assert "AI 점수: 상위 10 중 ○ 2건" in text and "○가 ×보다 위 50%" in text and "미달" in text
    assert "규칙 점수: 상위 10 중 ○ 2건" in text  # 규칙 점수가 다 같으면 반반
    assert "○ AI 50(고려) 규칙 80 | 회사 | 공고 b | 코멘트: 핵심 업무가 딱 맞음" in text  # ○인데 60 미만
    assert "× AI 70(고려)" in text and "[아직 평가 안 함 1건]" in text
    dump = feedback.sample_dump(sample, matches, rows)
    assert len(dump) == 4 and dump[0].startswith("SMP\t") and '"score": 90' in dump[0]
    assert '"label": "good", "comment": "핵심 업무가 딱 맞음"' in dump[3]  # b(50점), 최신 평가
