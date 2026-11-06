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


class FakeEmbed:
    def embed(self, texts):
        # 첫 글(지원자)과 같은 방향일수록 가깝다
        return [[1.0, 0.0]] + [[1.0, 0.1], [0.0, 1.0], [1.0, 0.5]][:len(texts) - 1]


def test_embedding_scores_are_ranks():
    got = methods.run_e(FakeEmbed(), "나", {"a": "x", "b": "y", "c": "z"})
    assert got == {"a": 100, "c": 50, "b": 0}


def test_stability_counts_band_changes():
    line = methods._stability([{"a": 85, "b": 50, "c": None}, {"a": 75, "b": 52, "c": 70}])
    assert "평균 6.0점" in line and "10점 넘게 다름 0%" in line and "구간 바뀜 50%" in line
    assert "한 번만" in methods._stability([{"a": 1}])


class FakeDB:
    def __init__(self, tables):
        self.tables = tables

    def select(self, table, query="select=*"):
        return self.tables.get(table, [])


def test_evaluate_reads_saved_scores_without_ai(monkeypatch):
    from jobpost import recommend
    monkeypatch.setattr(recommend, "sample_ids", lambda: ["a", "b", "c"])
    monkeypatch.setattr(recommend, "candidates", lambda screen, scope: [{"id": "a"}, {"id": "b"}])
    db = FakeDB({"feedback": [{"user_id": "u1", "posting_id": "a", "label": "good"},
                              {"user_id": "u1", "posting_id": "b", "label": "bad"},
                              {"user_id": "u1", "posting_id": "c", "label": "bad"}],
                 "matches": [{"posting_id": "a", "parts": {"kind": "ai", "base": 90}},
                             {"posting_id": "b", "parts": {"kind": "ai", "base": 40}}]})
    saved = {"date": "2026-11-07", "methods": "D", "rounds": 2,
             "users": {"u1": {"D": [{"a": 30, "b": 80, "c": 10}, {"a": 35, "b": 85, "c": 12}]}}}
    screen = {"postings": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    out = "\n".join(methods.evaluate(screen, db, saved))
    assert "평가한 기준 샘플 3건(○ 1 △ 0 × 2)" in out
    assert "내 분야에서 빠진 평가 공고: ○ 0 △ 0 × 1" in out
    assert "A 방식" in out and "D 방식 1회" in out and "D 방식 2회" in out and "흔들림" in out
