from jobpost import company_class as cc


def _c(key="가나", corp=None, basics=None, groups=None, public=None, nps=None, src="그 외"):
    return cc.classify(key, corp=corp, basics=basics, group_keys=groups or {}, public_keys=public or set(),
                       nps=nps or {}, source_type=src)


def test_sme_limit_by_industry():
    assert cc.sme_limit("62010") == 800    # 정보통신
    assert cc.sme_limit("26110") == 1000   # 전자부품
    assert cc.sme_limit("64191") == 400    # 금융
    assert cc.sme_limit(None) == 1500


def test_order_of_evidence():
    fin = {"finance": {"years": [{"revenue": 2000e8}]}, "company": {"industry_code": "62010"}}
    corp = {"corp_code": "1", "corp_name": "가나"}
    assert _c(public={"가나": "공공기관 지정현황(재정경제부)"}).basis == "공공기관 지정현황(재정경제부)"
    assert _c(groups={"가나": "가나그룹"}, corp=corp, basics=fin).type == "대기업"
    assert _c(corp={**corp, "dart_key": "다라"}, groups={"다라": "다라그룹"}).type == "대기업"
    assert _c(corp=corp, basics=fin).type == "중견"
    small = {"finance": {"years": [{"revenue": 300e8}]}}
    assert _c(corp=corp, basics=small).type == "중소·스타트업"


def test_no_dart_uses_small_company_check():
    assert _c(nps={"가나": (1, 40)}).type == "중소·스타트업"
    assert _c(nps={"가나": (1, 900)}).type == "확인 안 됨"
    assert _c().type == "확인 안 됨"
    r = _c(src="대기업")
    assert (r.type, r.basis) == ("대기업", "수집처 표시")


def test_group_by_corporate_number():
    gi = cc.group_index({"companies": [{"group": "씨제이", "key": "cj이엔엠", "jurirno": "110111-1234567"}]})
    b = {"company": {"jurir_no": "1101111234567"}}
    assert _c(key="cjenm", corp={"corp_code": "1"}, basics=b, groups=gi).basis == "공정위 기업집단 씨제이"


def test_foreign_from_dart_owner():
    corp = {"corp_code": "1"}
    fin = {"finance": {"years": [{"revenue": 9000e8}]}}
    oracle = {**fin, "owner": {"name": "Oracle Corporation", "source": "감사보고서 지배기업", "foreign": "외국 회사 표기"}}
    assert _c(corp=corp, basics=oracle).type == "외국계"
    domestic = {**fin, "owner": {"name": "가나㈜", "source": "감사보고서 지배기업", "foreign": None}}
    assert _c(corp=corp, basics=domestic, src="외국계").type == "중견"  # 수집처 표시를 버림
    assert _c(corp=corp, basics=fin, src="외국계").basis == "수집처 표시"  # 아직 안 읽음


def test_manual_exception_comes_first():
    r = cc.classify("가나", corp=None, basics=None, group_keys={}, public_keys={}, nps={}, source_type="그 외",
                    manual={"type": "중견", "basis": "2025 감사보고서 매출 1,900억"})
    assert (r.type, r.basis) == ("중견", "직접 확인: 2025 감사보고서 매출 1,900억")


def test_industry_order():
    from jobpost.company_class import industry
    # 예외가 먼저
    assert industry(manual={"industry": "IN0201", "basis": "확인"}, public_label="x", ksic="64110", domains=[])[0] == "IN0201"
    # 공공기관 목록 → 공공기관
    assert industry(manual=None, public_label="공공기관 지정", ksic="64110", domains=[]) == ("IN1101", "공공기관 지정")
    # KSIC 대응표
    assert industry(manual=None, public_label=None, ksic="64110", domains=["IN0105"]) == ("IN0101", "DART 업종 코드 64110")
    # 도메인을 모르는 KSIC(소프트웨어)·DART 없음 → 회사 도메인 다수결
    code, basis = industry(manual=None, public_label=None, ksic="58221", domains=["IN0201", "IN0702", "IN0201"])
    assert code == "IN0201" and "3개 중 2개" in basis
    assert industry(manual=None, public_label=None, ksic=None, domains=[])[0] is None


def test_industry_exception_basis_and_check():
    from jobpost.company_class import industry
    m = {"type": "중견", "basis": "매출 근거", "industry": "IN0105", "industry_basis": "앱 결제 서비스"}
    assert industry(manual=m, public_label=None, ksic=None, domains=[]) == ("IN0105", "직접 확인: 앱 결제 서비스")
    # 기업 구분 예외만 있는 회사는 업종을 정하지 않고 다음 근거로
    assert industry(manual={"type": "중견", "basis": "x"}, public_label=None, ksic="64110", domains=[])[0] == "IN0101"
    # 지난 id로 적어도 코드로, 없는 값이면 무시
    assert industry(manual={"industry": "bank"}, public_label=None, ksic=None, domains=[])[0] == "IN0101"
    assert industry(manual={"industry": "없는값"}, public_label=None, ksic=None, domains=[])[0] is None
