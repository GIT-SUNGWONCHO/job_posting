from test_recommend import BODIES, SCREEN, TODAY, FakeDB

from jobpost import ai_match


class ScoringAI:
    def __init__(self, fail_on=""):
        self.prompts, self.fail_on = [], fail_on

    def json(self, prompt, schema):
        self.prompts.append(prompt)
        if self.fail_on and self.fail_on in prompt:
            raise RuntimeError("429")
        return {"score": 88, "reason": "파이프라인 경험이 맞음", "gaps": ["Airflow 운영"]}


def test_run_puts_ai_and_rule_scores_side_by_side(capsys):
    ai = ScoringAI(fail_on="Data Analyst")
    rows = ai_match.run(SCREEN, BODIES, FakeDB(), ai, TODAY)
    by = {r["id"]: r for r in rows}
    assert set(by) == {"z:1", "z:2"}  # 개인 필터를 통과한 공고만
    assert by["z:1"]["ai"] == 88 and by["z:1"]["rule"] > 0 and by["z:1"]["gaps"] == ["Airflow 운영"]
    assert by["z:2"]["ai"] is None and "429" in by["z:2"]["error"]  # 실패해도 계속
    assert "비밀회사" not in ai.prompts[0] and "(본문 없음)" in ai.prompts[1]
    assert capsys.readouterr().out.count("AIM\t") == 2
