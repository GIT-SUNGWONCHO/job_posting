from jobpost.normalize import list_title


def test_list_title_drops_company_and_hiring_words():
    assert list_title("우리은행 데이터 엔지니어 (AI데이터플랫폼부) 전문직 채용공고", "우리은행") == "데이터 엔지니어 (AI데이터플랫폼부) 전문직"
    assert list_title("[한국거래소] 시장분석전문가 채용", "한국거래소") == "시장분석전문가"
    assert list_title("한국전자인증(주) AI Agent 개발자 채용", "한국전자인증") == "AI Agent 개발자"
    assert list_title("(주)세스코 AI Engineer 채용", "세스코") == "AI Engineer"
    assert list_title("[한화투자증권] AI팀_AI프로덕트 개발 직무 경력 채용", "한화투자증권") == "AI팀_AI프로덕트 개발 직무"
    assert list_title("온톨로지(Ontology) 전문가 경력사원 채용", "한화시스템") == "온톨로지(Ontology) 전문가"


def test_list_title_drops_deadline_notes():
    assert list_title("데이터엔지니어링(DE) 직무 인재모집(채용 시 마감)", "신세계아이앤씨") == "데이터엔지니어링(DE) 직무"
    assert list_title("임상통계담당 경력직 채용 (~10/31)", "대웅") == "임상통계담당"


def test_list_title_keeps_other_brackets_and_words():
    # 팀 이름, 계열사 이름(그룹 회사의 공고)은 남긴다
    assert list_title("[AI데이터플랫폼팀] 데이터 엔지니어(4년 이상) 채용", "NHN KCP") == "[AI데이터플랫폼팀] 데이터 엔지니어(4년 이상)"
    assert list_title("[한화시스템/ICT] AI Agent 전문가", "한화") == "[한화시스템/ICT] AI Agent 전문가"
    # 회사 이름으로 시작하는 다른 말은 자르지 않는다
    assert list_title("카카오페이 데이터 엔지니어", "카카오") == "카카오페이 데이터 엔지니어"
    assert list_title("Data Platform Engineer", "티맵모빌리티") == "Data Platform Engineer"


def test_list_title_falls_back_when_too_short():
    assert list_title("[카카오] 채용", "카카오") == "[카카오] 채용"
    assert list_title("", "카카오") == ""
