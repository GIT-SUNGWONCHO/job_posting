import json
from datetime import date, datetime
from pathlib import Path

from jobpost.models import DeadlineType, Source
from jobpost.normalize import career_text
from jobpost.sources import jobkorea, remember, saramin, wanted, zighang

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_zighang_list_item():
    items = load("zighang_list.json")["data"]["content"]
    p = zighang.parse_item(items[0])
    assert p.source is Source.ZIGHANG
    assert p.company == "한화비전"
    assert (p.career_min, p.career_max) == (5, 12)
    assert p.deadline_type is DeadlineType.UNTIL_FILLED and p.deadline is None
    assert "AI_데이터" in p.categories and "데이터엔지니어" in p.categories
    assert p.url.endswith(items[0]["id"])
    assert p.via is None  # 직행이 직접 모은 공고

    open_ended = zighang.parse_item(items[2])  # careerMax 100 = 상한 없음
    assert (open_ended.career_min, open_ended.career_max) == (10, None)
    assert career_text(open_ended.career_min, open_ended.career_max) == "경력 10년 이상"


def test_zighang_far_deadline_is_always():
    item = dict(load("zighang_list.json")["data"]["content"][0])
    item.update({"deadlineType": "마감일", "endDate": "2999-12-31T23:59:59"})
    p = zighang.parse_item(item)
    assert p.deadline_type is DeadlineType.ALWAYS and p.deadline is None


def test_zighang_detail_text():
    data = load("zighang_detail.json")["data"]
    d = zighang.parse_detail(data, datetime(2026, 10, 13))
    assert d.uid == f"zighang:{data['id']}"
    assert d.description and "담당업무" in d.description
    assert d.apply_url and d.apply_url.startswith("http")
    assert all(r.startswith("zighang:") for r in d.related_ids)


def test_zighang_title_matcher():
    m = zighang._title_matcher("AI")
    assert m.search("AI 엔지니어")
    assert not m.search("Retail 매니저")
    k = zighang._title_matcher("데이터 거버넌스")
    assert k.search("데이터거버넌스 담당")


def test_remember_items():
    items = load("remember_search.json")["data"]
    first = remember.parse_item(items[0])
    assert first.source is Source.REMEMBER
    assert first.company == "(주)모레"
    assert first.url == "https://career.rememberapp.co.kr/job/posting/346665"
    assert (first.career_min, first.career_max) == (None, 4)
    assert "AI·데이터" in first.categories
    assert first.description and "[주요업무]" in first.description

    dated = remember.parse_item(items[1])
    assert dated.deadline_type is DeadlineType.DATE
    assert dated.deadline == date(2026, 10, 18)

    hh = remember.parse_item(items[2])
    assert hh.headhunter


def test_saramin_career_texts():
    cases = {
        "경력 3년↑ · 정규직": (3, None, False, ["정규직"]),
        "3 ~ 10년 · 정규직 외": (3, 10, False, ["정규직"]),
        "경력무관 · 계약직": (None, None, True, ["계약직"]),
        "신입 · 경력 · 정규직": (None, None, True, ["정규직"]),
        "신입 · 인턴직": (None, 0, True, ["인턴직"]),
        "경력(년수무관) · 정규직": (None, None, False, ["정규직"]),
        "경력 · 정규직": (None, None, False, ["정규직"]),
    }
    for text, expected in cases.items():
        assert saramin.parse_career(text) == expected, text


def test_saramin_deadlines():
    today = date(2026, 10, 13)
    assert saramin.parse_deadline("~10.25(일)", today) == (DeadlineType.DATE, date(2026, 10, 25))
    assert saramin.parse_deadline("~01.05(화)", today) == (DeadlineType.DATE, date(2027, 1, 5))
    assert saramin.parse_deadline("D-9", today) == (DeadlineType.DATE, date(2026, 10, 22))
    assert saramin.parse_deadline("채용시", today) == (DeadlineType.UNTIL_FILLED, None)
    assert saramin.parse_deadline("상시채용", today) == (DeadlineType.ALWAYS, None)
    assert saramin.parse_deadline("오늘마감", today) == (DeadlineType.DATE, today)


def test_saramin_list_page():
    html = (FIX / "saramin_list.html").read_text(encoding="utf-8")
    postings, last_page = saramin.parse_list(html, date(2026, 10, 13), datetime(2026, 10, 13, 12))
    assert len(postings) == 4
    assert last_page == 10
    first = postings[0]
    assert first.source_id == "55271847"
    assert first.company == "국립암센터"
    assert first.regions == ["경기"]
    assert first.deadline == date(2026, 10, 25)
    assert first.raw and first.raw["career"].startswith("경력무관")


def _saramin_page(n, start):
    html = (FIX / "saramin_list.html").read_text(encoding="utf-8")
    item = html[html.index('<div class="list_item"'):html.index('<div class="list_item"', 10 + html.index('<div class="list_item"'))]
    items = "".join(item.replace("rec-55271847", f"rec-{start + i}") for i in range(n))
    return f"<html><body>{items}</body></html>"


def test_saramin_pages_until_short_page():
    from types import SimpleNamespace

    pages = [_saramin_page(100, 1000), _saramin_page(100, 2000), _saramin_page(7, 3000)]

    class FakeClient:
        requests = 0

        def get(self, url, params=None, **kw):
            self.requests += 1
            return SimpleNamespace(text=pages[params["page"] - 1])

    collector = saramin.SaraminCollector(FakeClient(), {"categories": {83: "데이터엔지니어"}})
    postings, done = collector._pages(80)
    assert done and len(postings) == 207
    postings, done = collector._pages(2)
    assert not done and len(postings) == 200


def test_saramin_detail_text():
    from datetime import datetime

    from jobpost.sources.saramin import parse_detail

    html = ("<html><body><h1>채용공고 상세</h1><script>x=1</script><div>📋 주요업무</div>"
            "<p>데이터  파이프라인 구축</p><img src='a.png'></body></html>")
    d = parse_detail(html, "123", datetime(2026, 10, 13))
    assert d.uid == "saramin:123"
    assert d.description == "📋 주요업무\n데이터 파이프라인 구축"
    assert d.raw == {"images": 1}


def test_wanted_list_item():
    tags = {655: "데이터 엔지니어", 1024: "데이터 사이언티스트", 1025: "빅데이터 엔지니어"}
    dated, open_, newcomer = (wanted.parse_item(x, tags) for x in load("wanted_list.json")["data"])
    assert dated.source is Source.WANTED
    assert dated.url == "https://www.wanted.co.kr/wd/395306"
    assert dated.company == "케이에스피아이"
    assert (dated.career_min, dated.career_max, dated.newcomer) == (4, 10, False)
    assert (dated.deadline_type, dated.deadline) == (DeadlineType.DATE, date(2026, 11, 13))
    assert dated.regions == ["서울"]
    assert "데이터 엔지니어" in dated.categories
    # annual_to 100은 상한 없음, 마감일이 없으면 상시
    assert (open_.career_min, open_.career_max) == (3, None)
    assert (open_.deadline_type, open_.deadline) == (DeadlineType.ALWAYS, None)
    assert (newcomer.career_min, newcomer.newcomer) == (None, True)


def test_wanted_detail():
    job = load("wanted_detail.json")["job"]
    d = wanted.parse_detail(job, "395306", datetime(2026, 10, 29))
    assert d.uid == "wanted:395306"
    assert d.description and d.description.startswith("[주요업무]")
    assert "[자격요건]" in d.description and "[회사 소개]" not in d.description
    assert {t["title"] for t in d.raw["company_tags"]} >= {"50명이하", "설립3년이하"}


def test_wanted_company_names():
    known = {"컷백", "cj올리브영", "엔비디아nvidia"}
    assert wanted.pick_company("컷백(Cutback)", known) == "컷백"
    assert wanted.pick_company("씨제이올리브영(CJ올리브영)", known) == "CJ올리브영"
    assert wanted.pick_company("엔비디아(NVIDIA)", known) == "엔비디아(NVIDIA)"
    # 처음 보는 회사: 괄호 앞 이름, 다른 이름이 보통 이름이면 그쪽
    assert wanted.pick_company("앤톡(Antock)", set()) == "앤톡"
    assert wanted.pick_company("씨제이이엔엠(CJ이엔엠)", set()) == "CJ이엔엠"
    assert wanted.pick_company("케이에스피아이(주)", set()) == "케이에스피아이"


def test_jobkorea_headhunting_rows():
    rows = jobkorea.parse_rows((FIX / "jobkorea_hh_list.html").read_text(encoding="utf-8"))
    assert len(rows) == 2
    p = jobkorea.parse_item(rows[0], "AI/ML엔지니어")
    assert p.source is Source.JOBKOREA and p.headhunter
    assert p.url == "https://www.jobkorea.co.kr/Recruit/GI_Read/50264615"
    assert p.company == "피플워크㈜"  # 회사 자리는 서치펌
    assert p.title.startswith("AI Engineer / AI Scientist")
    assert p.client_type == "대기업" and p.raw["client_label"] == "대기업"
    assert (p.career_min, p.regions, p.employment_types) == (3, ["인천"], ["정규직"])
    assert (p.deadline_type, p.deadline) == (DeadlineType.DATE, date(2027, 1, 27))
    # 헤드헌터 이름은 읽지 않는다
    assert "홍길동" not in json.dumps(p.raw, ensure_ascii=False)
    # 중견기업 의뢰는 "그 외"
    second = jobkorea.parse_item(rows[1], "데이터분석가")
    assert second.raw["client_label"] == "중견기업" and second.client_type == "그 외"


def test_jobkorea_client_label():
    assert jobkorea.client_label("대기업 - 국내 대기업 시중은행") == "대기업"
    assert jobkorea.client_label("외국계 - Management Consulting") == "외국계"
    assert jobkorea.client_label("잡뉴스솔로몬서치 - 25년 역사") is None


def test_jobkorea_detail_keeps_position_and_drops_contacts():
    page = (FIX / "jobkorea_hh_detail.html").read_text(encoding="utf-8")
    d = jobkorea.parse_detail(page, "50264615", datetime(2026, 10, 30))
    assert d.uid == "jobkorea:50264615"
    text = d.description or ""
    assert "[ 담당업무 ]" in text and "LLM 기반 모델" in text
    assert "설립된 회사" not in text  # 서치펌 소개는 뺀다
    assert "@" not in text and "010-0000-0000" not in text and "홍길동" not in text


def test_scrub_keeps_work_lines():
    out = jobkorea.scrub("고객 문의 분류 모델 개발\n채용담당 : 홍길동 전무\n메일 hong@example.com, 02-123-4567")
    assert "고객 문의 분류 모델 개발" in out
    assert "홍길동" not in out and "@" not in out and "123-4567" not in out
