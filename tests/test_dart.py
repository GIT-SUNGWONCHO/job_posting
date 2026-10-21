import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
import requests

from jobpost import dart

CORPCODE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>00126256</corp_code><corp_name>삼성생명보험</corp_name><stock_code>032830</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>01111111</corp_code><corp_name>비바리퍼블리카</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>02222222</corp_code><corp_name>한빛</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>03333333</corp_code><corp_name>(주)한빛</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>04444444</corp_code><corp_name>카카오</corp_name><stock_code>035720</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>05555555</corp_code><corp_name>카카오</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>06666666</corp_code><corp_name>씨제이올리브영</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>07777777</corp_code><corp_name>삼성물산</corp_name><stock_code>000830</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>08888888</corp_code><corp_name>삼성물산</corp_name><stock_code>028260</stock_code><modify_date>20240101</modify_date></list>
</result>""".encode()


def test_variants_try_korean_reading_of_acronyms():
    assert dart.variants("cj올리브영", "CJ올리브영(주)") == ["cj올리브영", "씨제이올리브영"]
    assert dart.variants("카카오스타일kakaostyle", "카카오스타일(Kakao Style)")[1] == "카카오스타일"
    # 긴 영어 단어는 그대로 둔다
    assert dart.variants("ktcloud", "ktcloud") == ["ktcloud"]


def test_match_by_same_rules_as_postings():
    idx = dart.index(dart.parse_corp_codes(CORPCODE_XML))
    c, how = dart.match("삼성전자", "삼성전자", idx)
    assert c["corp_code"] == "00126380" and how == "name"
    # 별칭(config/company_aliases.yaml): 법인명 삼성생명보험 = 공고의 삼성생명, 비바리퍼블리카 = 토스
    assert dart.match("삼성생명", "삼성생명", idx)[0]["corp_code"] == "00126256"
    assert dart.match("토스", "토스", idx)[0]["corp_code"] == "01111111"
    # 같은 이름이 여럿이면 상장사가 하나일 때만, 아니면 잇지 않는다
    assert dart.match("카카오", "카카오", idx)[0]["corp_code"] == "04444444"
    assert dart.match("한빛", "한빛", idx) == (None, "ambiguous")
    assert dart.match("없는회사", "없는회사", idx) == (None, "none")
    assert dart.match("cj올리브영", "CJ올리브영(주)", idx)[0]["corp_code"] == "06666666"
    assert dart.match("삼성물산", "삼성물산", idx) == (None, "ambiguous")


FIN_ROWS = [
    {"rcept_no": "20260310000123", "fs_div": "CFS", "account_nm": "매출액", "thstrm_nm": "제57기", "thstrm_amount": "300,870,903,000,000",
     "frmtrm_nm": "제56기", "frmtrm_amount": "258,935,494,000,000", "bfefrmtrm_nm": "제55기", "bfefrmtrm_amount": "302,231,360,000,000"},
    {"rcept_no": "20260310000123", "fs_div": "CFS", "account_nm": "영업이익", "thstrm_amount": "32,725,961,000,000",
     "frmtrm_amount": "6,566,976,000,000", "bfefrmtrm_amount": "43,376,630,000,000"},
    {"rcept_no": "20260310000123", "fs_div": "CFS", "account_nm": "당기순이익(손실)", "thstrm_amount": "-1,000",
     "frmtrm_amount": "-", "bfefrmtrm_amount": ""},
    {"rcept_no": "20260310000123", "fs_div": "OFS", "account_nm": "매출액", "thstrm_amount": "1"},
]


def test_parse_finance_prefers_consolidated_and_orders_years():
    f = dart.parse_finance(FIN_ROWS, 2025)
    assert f["basis"] == "연결" and f["rcept_no"] == "20260310000123"
    assert [y["year"] for y in f["years"]] == [2023, 2024, 2025]
    assert f["years"][-1] == {"year": 2025, "revenue": 300870903000000, "operating": 32725961000000, "net": -1000}
    assert f["years"][1]["net"] is None
    only_ofs = dart.parse_finance([{**r, "fs_div": "OFS"} for r in FIN_ROWS[:2]], 2025)
    assert only_ofs["basis"] == "별도"
    # 은행은 매출액 줄이 없다. 다른 계정으로 바꿔 넣지 않는다
    bank = dart.parse_finance([
        {"fs_div": "CFS", "account_nm": "순이자손익", "thstrm_amount": "12,000"},
        {"fs_div": "CFS", "account_nm": "영업이익(손실)", "thstrm_amount": "6,000", "frmtrm_amount": "5,000"},
        {"fs_div": "CFS", "account_nm": "당기순이익(손실)", "thstrm_amount": "4,000"},
        {"fs_div": "CFS", "account_nm": "당기순이익", "thstrm_amount": "4,000"},
    ], 2025)
    assert bank["years"][-1] == {"year": 2025, "operating": 6000, "net": 4000}
    assert dart.parse_finance([], 2025) is None


def test_parse_employees_sums_rows_or_uses_total_row():
    rows = [
        {"fo_bbm": "DX", "sexdstn": "남", "sm": "1,000", "avrg_cnwk_sdytrn": "10.0", "fyer_salary_totamt": "100,000,000,000",
         "jan_salary_am": "100,000,000", "rcept_no": "20260310000123", "stlm_dt": "2025-12-31"},
        {"fo_bbm": "DX", "sexdstn": "여", "sm": "500", "avrg_cnwk_sdytrn": "7년 6개월", "fyer_salary_totamt": "40,000,000,000",
         "jan_salary_am": "80,000,000", "rcept_no": "20260310000123", "stlm_dt": "2025-12-31"},
    ]
    e = dart.parse_employees(rows)
    assert e["count"] == 1500
    assert e["tenure"] == 9.2  # (10×1000 + 7.5×500) / 1500
    assert e["salary"] == 93333333  # 급여 총액 ÷ 인원
    with_total = rows + [{"fo_bbm": "합계", "sexdstn": "합계", "sm": "1,500", "avrg_cnwk_sdytrn": "9.2",
                          "fyer_salary_totamt": "140,000,000,000", "jan_salary_am": "93,000,000"}]
    assert dart.parse_employees(with_total)["count"] == 1500
    assert dart.parse_employees([{"sm": "-"}]) is None


def test_parse_employees_uses_subtotal_rows_when_segments_lack_salary():
    # 삼성전자 2020 사업보고서처럼 사업부문 × 성별 줄 + 성별합계 줄, 급여는 합계 줄에만
    rows = [
        {"fo_bbm": "CE", "sexdstn": "남", "sm": "8,000", "avrg_cnwk_sdytrn": "15.0", "jan_salary_am": "-"},
        {"fo_bbm": "CE", "sexdstn": "여", "sm": "2,000", "avrg_cnwk_sdytrn": "10.0", "jan_salary_am": "-"},
        {"fo_bbm": "DS", "sexdstn": "남", "sm": "40,000", "avrg_cnwk_sdytrn": "12.0", "jan_salary_am": "-"},
        {"fo_bbm": "DS", "sexdstn": "여", "sm": "10,000", "avrg_cnwk_sdytrn": "9.0", "jan_salary_am": "-"},
        {"fo_bbm": "성별합계", "sexdstn": "남", "sm": "48,000", "avrg_cnwk_sdytrn": "약 12.5년", "jan_salary_am": "130,000,000"},
        {"fo_bbm": "성별합계", "sexdstn": "여", "sm": "12,000", "avrg_cnwk_sdytrn": "19년 6개월", "jan_salary_am": "100,000,000"},
    ]
    e = dart.parse_employees(rows)
    assert e["count"] == 60000
    assert e["tenure"] == 13.9  # (12.5×48000 + 19.5×12000) / 60000
    assert e["salary"] == 124000000  # 성별 평균을 인원으로 가중


def test_parse_disclosures_skips_routine_and_dedupes():
    rows = [
        {"rcept_dt": "20260801", "report_nm": "타법인주식및출자증권취득결정", "rcept_no": "1"},
        {"rcept_dt": "20260805", "report_nm": "[기재정정]타법인주식및출자증권취득결정", "rcept_no": "2"},
        {"rcept_dt": "20260301", "report_nm": "대표이사변경", "rcept_no": "3"},
        {"rcept_dt": "20260302", "report_nm": "기업설명회(IR)개최(안내공시)", "rcept_no": "4"},
    ]
    out = dart.parse_disclosures(rows, ["기업설명회"], 5)
    assert [(d["date"], d["rcept_no"]) for d in out] == [("2026-08-05", "2"), ("2026-03-01", "3")]
    assert out[0]["title"] == "타법인주식및출자증권취득결정"


def test_pick_disclosures_filters_at_screen_time():
    items = [{"date": "2026-09-01", "title": "정기주주총회결과"}, {"date": "2026-08-01", "title": "단일판매ㆍ공급계약체결"},
             {"date": "2026-07-01", "title": "대표이사변경"}]
    assert [d["title"] for d in dart.pick_disclosures(items, ["주주총회"], 1)] == ["단일판매ㆍ공급계약체결"]


def test_annual_year():
    assert dart.annual_year(date(2026, 10, 21)) == 2025
    assert dart.annual_year(date(2026, 3, 1)) == 2024
    assert dart.annual_year(date(2026, 4, 9)) == 2024
    assert dart.annual_year(date(2026, 4, 10)) == 2025


class FakeSession:
    """DART 응답 흉내. 요청 주소와 인자를 남긴다."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, timeout=None, stream=False):
        name = url.rsplit("/", 1)[-1]
        self.calls.append((name, dict(params or {})))
        resp = requests.Response()
        resp.status_code = 200
        body = self.responses(name, params or {})
        resp._content = body if isinstance(body, bytes) else json.dumps(body).encode()
        resp._content_consumed = True  # 다 받은 응답처럼(iter_content가 _content를 나눠 준다)
        return resp


def _zip(xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def _state(tmp_path: Path, companies: list[tuple[str, str]]):
    lines = [json.dumps({"uid": f"zighang:{i}", "source": "zighang", "company": name, "company_key": key,
                         "first_seen": "2026-10-20", "last_seen": "2026-10-21", "closed_on": None, "title": "데이터 엔지니어"},
                        ensure_ascii=False) for i, (key, name) in enumerate(companies)]
    (tmp_path / "state.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_run_links_fetches_and_respects_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(dart.time, "sleep", lambda s: None)
    _state(tmp_path, [("삼성전자", "삼성전자"), ("한빛", "한빛"), ("없는회사", "없는회사"), ("삼성물산", "삼성물산")])

    def respond(name, params):
        if name == "corpCode.xml":
            return _zip(CORPCODE_XML)
        if name == "company.json" and params["corp_code"] == "07777777":
            return {"status": "000", "corp_name": "삼성물산(주)", "corp_cls": "E"}  # 합병 전 회사(상장 폐지)
        if name == "company.json":
            return {"status": "000", "corp_name": "삼성전자", "stock_code": "005930", "corp_cls": "Y", "ceo_nm": "대표",
                    "est_dt": "19690113", "hm_url": "www.samsung.com/sec"}
        if name == "fnlttSinglAcnt.json":
            return {"status": "000", "list": FIN_ROWS} if params["bsns_year"] == 2025 else {"status": "013"}
        if name == "empSttus.json":
            return {"status": "000", "list": [{"fo_bbm": "전체", "sexdstn": "남", "sm": "10"}]}
        if name == "list.json":
            return {"status": "013", "message": "조회된 데이타가 없습니다."}
        raise AssertionError(name)

    s = FakeSession(respond)
    summary = dart.run(tmp_path, date(2026, 10, 21), session=s, cache=tmp_path / "cache")
    assert summary["matched_new"] == 2 and summary["unmatched_new"] == 2 and summary["fetched"] == 2
    assert all(p.get("crtfc_key") == "test-key" for _, p in s.calls)
    corps = json.loads((tmp_path / "dart" / "corps.json").read_text(encoding="utf-8"))
    assert corps["삼성전자"]["corp_code"] == "00126380"
    assert corps["한빛"] == {"corp_code": None, "why": "ambiguous", "checked": "2026-10-21", "mv": dart.MATCH_VERSION}
    # 같은 이름이 여럿이면 지금 상장된 쪽(기업개황 corp_cls)으로 고른다
    assert corps["삼성물산"]["corp_code"] == "08888888" and corps["삼성물산"]["how"] == "listed_now"
    basics = json.loads((tmp_path / "dart" / "basics.json").read_text(encoding="utf-8"))
    got = basics["00126380"]
    assert got["company"]["market"] == "유가증권" and got["company"]["homepage"] == "https://www.samsung.com/sec"
    assert got["finance"]["years"][-1]["revenue"] == 300870903000000
    assert got["employees"]["count"] == 10 and got["disclosures"] == []

    # 다음 날: 이미 이은 회사·받은 기본정보는 다시 요청하지 않는다
    s2 = FakeSession(respond)
    again = dart.run(tmp_path, date(2026, 10, 22), session=s2, cache=tmp_path / "cache")
    assert s2.calls == [] and again["linked"] == 2 and again["with_basics"] == 2

    # 손으로 잇기(DART 이름): 받아 둔 고유번호 파일을 다시 쓰고 요청하지 않는다
    monkeypatch.setattr(dart.config, "load", lambda name: {"overrides": {"한빛": "(주)한빛"}})
    s4 = FakeSession(respond)
    dart.run(tmp_path, date(2026, 10, 22), session=s4, cache=tmp_path / "cache", budget=0)
    corps = json.loads((tmp_path / "dart" / "corps.json").read_text(encoding="utf-8"))
    assert corps["한빛"]["corp_code"] is None  # 같은 이름이 둘이라 이름으로는 못 잇는다
    monkeypatch.setattr(dart.config, "load", lambda name: {"overrides": {"한빛": "03333333"}})
    dart.run(tmp_path, date(2026, 10, 22), session=s4, cache=tmp_path / "cache", budget=0)
    corps = json.loads((tmp_path / "dart" / "corps.json").read_text(encoding="utf-8"))
    assert corps["한빛"]["corp_code"] == "03333333" and corps["한빛"]["how"] == "override"
    assert s4.calls == []
    monkeypatch.undo()
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(dart.time, "sleep", lambda s: None)

    # 요청 수를 다 쓰면 받은 데까지 저장하고 멈춘다
    (tmp_path / "dart" / "basics.json").unlink()
    s3 = FakeSession(respond)
    stopped = dart.run(tmp_path, date(2026, 10, 23), budget=2, session=s3, cache=tmp_path / "cache")
    assert stopped["stopped"] == "오늘 요청 수나 시간을 다 씀" and len(s3.calls) == 2


def test_errors_do_not_leak_the_key(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "secret-key-123")

    class Boom:
        def get(self, url, params=None, timeout=None, stream=False):
            raise requests.ConnectionError(f"failed {url}?crtfc_key={params['crtfc_key']}")

    client = dart.Client(5, 0, Boom())
    with pytest.raises(dart.DartError) as e:
        client.json("company.json", {"corp_code": "1"})
    assert "secret-key-123" not in str(e.value)
