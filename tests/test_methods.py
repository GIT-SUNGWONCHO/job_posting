from jobpost import methods

FACT = {"facts": {"duties": ["파이프라인 구축", "DW 설계"], "required_skills": ["Python", "Spark"], "preferred_skills": [],
                  "years": [{"area": "데이터 엔지니어링", "min": 5}], "level": "시니어", "domain_required": [],
                  "degree": "적혀 있지 않음", "majors": [], "certs": []}}


def test_frame_drops_missing_kinds():
    items = methods.frame_items(FACT)
    assert [i["kind"] for i in items] == ["핵심 업무", "필수 스킬", "경력 연수·직급"]


def test_pool_lists_each_requirement():
    kinds = [i["kind"] for i in methods.pool_items(FACT)]
    assert kinds.count("핵심 업무") == 2 and kinds.count("필수 스킬") == 2 and "경력 연수·직급" in kinds


def test_concordance():
    labels = {"a": "good", "b": "bad", "c": "maybe"}
    assert methods.concordance(labels, {"a": 90, "b": 30, "c": 60}) == 1.0
    assert methods.concordance(labels, {"a": 30, "b": 90, "c": 60}) == 0.0
