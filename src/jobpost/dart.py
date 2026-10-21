"""회사 기본정보(DART): 공고가 들어온 회사를 DART 고유번호와 잇고 기업개황·주요 재무·직원 현황·주요 공시를 모은다.
DART는 이 모듈에서만 부른다(docs/architecture.md "경계"). 설정은 config/dart.yaml.

키는 환경 변수 DART_API_KEY(GitHub Secrets)로만 받는다. 키가 요청 주소(crtfc_key)에 들어가므로
요청 오류를 그대로 올리지 않고 주소를 뺀 문장으로 바꾼다(로그에 키가 남지 않게).

data 폴더(data 브랜치)
  dart/corps.json   회사 키 → DART 고유번호 잇기 결과 {"corp_code", "corp_name", "stock_code", "how", "checked"}
                    못 찾았으면 corp_code null과 why(none: 같은 이름 없음, ambiguous: 같은 이름 여럿)
  dart/basics.json  DART 고유번호 → 받은 기본정보 {"fetched", "company", "finance", "employees", "disclosures"}

opendart.fss.or.kr 개발가이드·FAQ와 공개된 실제 응답에서 확인한 것(2026-10-21):
- 요청: https://opendart.fss.or.kr/api/<이름>.json?crtfc_key=<키>&... (GET). 오류도 HTTP 200에 {"status", "message"}.
  000 정상, 013 데이터 없음(실패 아님), 020 하루 한도 초과(다시 하지 않음), 800 점검·900 알 수 없는 오류.
  개인 키 하루 2만 건(모든 API 합), 분당 1,000건 넘으면 IP가 1시간 막힌다. User-Agent가 비면 404가 날 수 있다
- 값은 모두 문자열. 금액은 원 단위 쉼표("9,457,000,000"), 음수는 앞에 -, 없으면 "-"나 "", 키가 아예 빠지기도 한다
- corpCode.xml: zip(약 3.6MB) 안 CORPCODE.xml. <list><corp_code><corp_name>((주) 없음. 정식명칭이라지만 상장사는
  짧은 이름이 많다: NAVER, 고영, 코오롱인더, 효성 ITX — 2026-10-22 확인)<corp_eng_name>
  <stock_code>(비상장은 " ")<modify_date>. 약 12만 곳, 비상장 외감법인 포함. 상장 폐지돼도 stock_code가 남는다
- company.json: corp_name("삼성전자(주)"처럼 법인 표기 포함), corp_cls Y 유가증권 · K 코스닥 · N 코넥스 · E 기타(비상장·상장폐지),
  ceo_nm(여러 명이면 쉼표), est_dt YYYYMMDD, hm_url(주소 앞 https:// 없음), induty_code(업종 코드, 길이 제각각)
- fnlttSinglAcnt.json: 상장사와 사업보고서를 내는 IFRS 비상장사만(그 밖은 013). 연결(CFS)·별도(OFS) 줄이 함께 오고
  사업보고서는 당기·전기·전전기(thstrm·frmtrm·bfefrmtrm) 3년. 기 이름은 "제 55 기"라 해는 요청한 bsns_year로 센다.
  은행 같은 금융사는 매출액 줄이 없다(영업이익(손실)·당기순이익(손실)은 있다). 당기순이익과 당기순이익(손실)이 같은 값으로 둘 다 오기도 한다
- empSttus.json: 사업부문(fo_bbm) × 성별(sexdstn 남·여) 줄. 인원 sm(정규직+계약직), 평균 근속 avrg_cnwk_sdytrn은
  자유 글("16.1", "19년 6개월", "약 16.9년"), 급여는 원. fo_bbm "성별합계"·"합계"·"전사" 같은 합계 줄이 섞여 오고
  급여는 합계 줄에만 있기도 해서, 합계 줄이 있으면 그것만 쓴다
- list.json: corp_code를 주면 기간 제한 없음(빼면 3개월). bgn_de를 빼면 하루만 찾는다. last_reprt_at=Y면 정정 전 것은 뺀다.
  pblntf_ty B 주요사항보고 · I 거래소공시. 공시 보기 주소 dart.fss.or.kr/dsaf001/main.do?rcpNo=<rcept_no>
- 사업보고서는 결산 뒤 90일 안(12월 결산은 3월 31일, 연장하면 4월 초)
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import requests

from . import config
from .normalize import PUNCT, clean_company, company_key

log = logging.getLogger(__name__)

API = "https://opendart.fss.or.kr/api/{name}"
VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
REPORT_ANNUAL = "11011"  # 사업보고서
CORP_CLS = {"Y": "유가증권", "K": "코스닥", "N": "코넥스", "E": "기타"}


class DartError(RuntimeError):
    pass


class LimitReached(DartError):
    """DART 하루 요청 한도(020)에 걸렸다. 그날은 멈춘다."""


def configured() -> bool:
    return bool(os.environ.get("DART_API_KEY"))


class Client:
    """요청 사이 간격을 지키고 요청 수를 센다. budget을 다 쓰면 Budget을 올린다."""

    class Budget(Exception):
        pass

    def __init__(self, budget: int, interval: float, session: requests.Session | None = None, raw: int = 0,
                 minutes: float | None = None):
        self.budget = budget
        # 이 시간이 지나면 요청 수가 남아도 멈춘다(매일 수집에서 아침 알림이 늦지 않게)
        self.deadline = time.monotonic() + minutes * 60 if minutes else None
        self.raw = raw  # 처음 이만큼의 응답을 로그에 남긴다(해석이 맞는지 볼 때. 응답에 키는 없다)
        self.interval = interval
        self.session = session or requests.Session()
        if session is None:
            self.session.headers["User-Agent"] = "jobpost/0.1 (company basics)"
        self.used = 0
        self._last = 0.0

    def get(self, name: str, params: dict[str, Any], stream: bool = False) -> requests.Response:
        if self.used >= self.budget:
            raise Client.Budget
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise Client.Budget
        wait = self._last + self.interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.used += 1
        try:
            # (연결, 읽기) 초. 읽기 시간은 바이트 사이 간격이라 느리게 오는 큰 파일은 corp_codes가 따로 끊는다
            resp = self.session.get(API.format(name=name), params={"crtfc_key": os.environ["DART_API_KEY"], **params},
                                    timeout=(10, 30), stream=stream)
            resp.raise_for_status()
        except requests.RequestException as e:
            # 오류 문장에 키가 든 주소가 들어 있어 종류만 남긴다
            code = getattr(getattr(e, "response", None), "status_code", None)
            raise DartError(f"DART {name} 요청 실패({type(e).__name__}{f' {code}' if code else ''})") from None
        finally:
            self._last = time.monotonic()
        return resp

    def json(self, name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """정상이면 응답, 데이터가 없으면(013) None."""
        try:
            body = self.get(name, params).json()
        except ValueError:
            raise DartError(f"DART {name} 응답이 JSON이 아님") from None
        if self.raw > 0:
            self.raw -= 1
            log.info("DART %s %s → %s", name, {k: v for k, v in params.items()},
                     json.dumps(body, ensure_ascii=False)[:2000])
        status = body.get("status")
        if status == "000":
            return body
        if status == "013":
            return None
        if status == "020":
            raise LimitReached(f"DART 요청 한도 초과: {body.get('message', '')[:80]}")
        raise DartError(f"DART {name} {status} {(body.get('message') or '')[:120]}")


# ---------- 회사 잇기 ----------

def parse_corp_codes(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ElementTree.fromstring(xml_bytes)
    out = []
    for el in root.iter("list"):
        out.append({
            "corp_code": (el.findtext("corp_code") or "").strip(),
            "corp_name": (el.findtext("corp_name") or "").strip(),
            "stock_code": (el.findtext("stock_code") or "").strip(),
        })
    return [c for c in out if c["corp_code"] and c["corp_name"]]


CORPCODE_SECONDS = 480  # 고유번호 파일(약 3.6MB)을 받는 데 쓸 최대 시간. GitHub에서 4분쯤 걸렸다(2026-10-21)
CORPCODE_DAYS = 7  # 받아 둔 고유번호 파일을 이만큼 다시 쓴다(GitHub Actions 캐시, 폴더는 DART_CACHE)


def corp_codes(client: Client, cache: Path | None = None, today: date | None = None) -> list[dict[str, str]]:
    """DART 고유번호 전체. zip 안 XML 하나. cache 폴더에 받은 지 CORPCODE_DAYS일 안 된 파일이 있으면 그것을 쓴다."""
    today = today or date.today()
    zpath = cache / "corpCode.zip" if cache else None
    dpath = cache / "corpCode.date" if cache else None
    if zpath and dpath and zpath.exists() and dpath.exists():
        try:
            got = date.fromisoformat(dpath.read_text(encoding="utf-8").strip())
            if got + timedelta(days=CORPCODE_DAYS) > today:
                with zipfile.ZipFile(zpath) as z:
                    corps = parse_corp_codes(z.read(z.namelist()[0]))
                log.info("DART 고유번호 파일: %s에 받은 것을 다시 씀(%d곳)", got, len(corps))
                return corps
        except (ValueError, zipfile.BadZipFile, ElementTree.ParseError):
            pass
    data = _download_corp_codes(client)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            corps = parse_corp_codes(z.read(z.namelist()[0]))
    except zipfile.BadZipFile:
        # 오류면 zip 대신 XML 메시지(<status>, <message>)가 온다
        raise DartError(f"DART 고유번호 파일을 받지 못함: {data[:160]!r}") from None
    if zpath and dpath:
        zpath.parent.mkdir(parents=True, exist_ok=True)
        zpath.write_bytes(data)
        dpath.write_text(today.isoformat(), encoding="utf-8")
    return corps


def _download_corp_codes(client: Client) -> bytes:
    """느리게 오면 CORPCODE_SECONDS에서 끊는다."""
    started = time.monotonic()
    resp = client.get("corpCode.xml", {}, stream=True)
    buf = io.BytesIO()
    try:
        for chunk in resp.iter_content(64 * 1024):
            buf.write(chunk)
            if time.monotonic() - started > CORPCODE_SECONDS:
                raise DartError(f"DART 고유번호 파일이 느려 {CORPCODE_SECONDS}초에서 끊음({buf.tell() // 1024} KB 받음)")
    except requests.RequestException as e:
        raise DartError(f"DART 고유번호 파일 받기 실패({type(e).__name__})") from None
    finally:
        resp.close()
    data = buf.getvalue()
    log.info("DART 고유번호 파일 받음 %d KB, %.1f초", len(data) // 1024, time.monotonic() - started)
    return data


class Index:
    """DART 회사를 공고 회사와 같은 규칙(company_key: 법인 표기·공백·기호를 지우고 별칭 적용)으로 묶는다.
    literal은 DART 이름 그대로, hangul은 영문 약자가 든 DART 이름(HDC랩스)의 한글 읽기(에이치디씨랩스).
    둘을 나눠 두고, 같은 이름이 양쪽에서 서로 다른 회사로 나오면 고르지 않는다(Index.find "mixed")."""

    def __init__(self, corps: list[dict[str, str]]):
        self.literal: dict[str, list[dict[str, str]]] = {}
        self.hangul: dict[str, list[dict[str, str]]] = {}
        for c in corps:
            k = company_key(c["corp_name"])
            if k:
                self.literal.setdefault(k, []).append(c)
            if _LATIN.search(c["corp_name"]):
                kh = company_key(_hangul(c["corp_name"]))
                if kh and kh != k:
                    self.hangul.setdefault(kh, []).append(c)

    def get(self, key: str) -> list[dict[str, str]]:
        return self.literal.get(key) or self.hangul.get(key) or []

    def find(self, key: str, name: str) -> tuple[list[dict[str, str]], str]:
        """(후보, 어떻게 찾았나). 공고 키로 글자 그대로 찾은 것은 "key", 괄호 빼기는 "bare", 그 밖(한글 읽기)은 "reading".
        글자 그대로 같은 회사와 한글 읽기로 같은 다른 회사가 함께 있으면 "mixed"(둘 다 후보로).
        상장사는 DART 이름이 짧은 종목명(RFHIC, TP)이라 한글 읽기가 곧 법인명일 때가 많아 어느 쪽이 맞는지
        이름만으로는 모른다(2026-10-22: 알에프에이치아이씨 공고는 상장사 RFHIC, 티피(주) 공고는 상장사 TP가 아니었다)."""
        vs = variants(key, name)
        for k, kind in vs:
            lit = self.literal.get(k) or []
            if lit:
                other = [c for c in self.hangul.get(k) or [] if c not in lit]
                if other:
                    return lit + other, "mixed"
                return lit, ("key" if kind == "key" else "bare" if kind == "bare" else "reading")
        for k, kind in vs:
            han = self.hangul.get(k) or []
            if han:
                return han, ("bare" if kind == "bare" else "reading")
        return [], "none"


def index(corps: list[dict[str, str]]) -> Index:
    return Index(corps)


def _compact(name: str) -> str:
    return PUNCT.sub("", clean_company(name)).lower()


_LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", [
    "에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠", "엔", "오", "피", "큐", "알",
    "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"], strict=True))
_LATIN = re.compile(r"[A-Za-z]+")
BIG = ("대기업", "공기업·공공기관")


def _hangul(name: str) -> str:
    """영문 약자(5글자까지)를 한글 읽기로. 긴 영어 단어는 그대로 둔다."""
    return _LATIN.sub(lambda m: "".join(_LETTERS[c] for c in m.group().lower()) if len(m.group()) <= 5 else m.group(), name)


def _bare(name: str) -> str:
    cleaned = clean_company(name)
    return re.sub(r"\([^)]*\)", "", cleaned).strip() or cleaned


def variants(key: str, name: str) -> list[tuple[str, str]]:
    """DART 이름과 맞춰 볼 (회사 키, 종류). 공고 키("key"), 괄호 속 다른 이름을 뺀 것("bare",
    카카오스타일(Kakao Style) → 카카오스타일), 영문 약자(5글자까지)를 한글 읽기로 바꾼 것("reading",
    CJ올리브영 → 씨제이올리브영). 법인명은 보통 영문 약자를 한글로 쓴다."""
    bare = _bare(name)
    out = [(key, "key")]
    for n, kind in ((bare, "bare"), (_hangul(bare), "reading")):
        k = company_key(n)
        if k and all(k != x for x, _ in out):
            out.append((k, kind))
    return out


def _weak(name: str, ctype: str, how: str) -> bool:
    """공고 키가 아닌 이름으로 찾았을 때 믿기 어려운 경우. 대기업·공기업 계열은 한글 읽기가 법인명과 거의 맞았고,
    틀린 것은 짧은 영문 약자만인 회사(MMS → 엠엠에스, SAP → 에스에이피)와 외국계의 괄호 속 한글 브랜드(테슬라(Tesla) →
    국내 주식회사 테슬라)였다(2026-10-22 리뷰). 이때는 종목코드가 있는 후보만 받는다."""
    if how == "key" or ctype in BIG:
        return False
    short_latin = bool(re.fullmatch(r"[A-Za-z]{1,5}", PUNCT.sub("", _bare(name))))
    return short_latin or (ctype == "외국계" and how == "bare")


def match(key: str, name: str, idx: Index, ctype: str = "그 외") -> tuple[dict[str, str] | None, str]:
    """(DART 회사, 어떻게). 이름이 같은 회사(Index.find)가 하나면 그것, 여럿이면 종목코드가 있는 곳이 하나일 때 그것.
    아니면 잇지 않는다(잘못 잇는 것보다 낫다). 공고 키가 아닌 이름으로만 찾았고 믿기 어려우면(_weak) 종목코드가 있는
    후보만 본다. 여럿이라 못 고른 것("ambiguous")은 run이 _resolve로 한 번 더 고른다. 글자 그대로와 한글 읽기가
    다른 회사를 가리키면("mixed") 고르지 않는다."""
    cands, how = idx.find(key, name)
    if not cands:
        return None, "none"
    if how == "mixed":
        return None, "mixed"  # 손으로 잇기로(config/dart.yaml overrides)
    if _weak(name, ctype, how):
        cands = [c for c in cands if c["stock_code"]]
        if not cands:
            return None, "weak"
    if len(cands) == 1:
        return cands[0], "name"
    listed = [c for c in cands if c["stock_code"]]
    if len(listed) == 1:
        return listed[0], "listed"
    return None, "ambiguous"


# ---------- 기본정보 해석(받은 응답 → 화면에 쓸 값) ----------

def _amount(s: Any) -> int | None:
    """'1,234,567' → 1234567. 비었거나 '-'면 None. 음수는 '-1,234'나 '(1,234)'."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if not t or t == "-" or not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    v = int(float(t))
    return -v if neg else v


# 주요 계정 이름(회사·해마다 조금씩 다르다). 매출액 대신 영업수익으로 적는 회사(증권사, NAVER·두나무 같은 플랫폼)가 있어
# 영업수익도 받되 어느 계정인지 revenue_name에 남겨 화면이 그 이름 그대로 보여준다. 은행은 둘 다 없다
ACCOUNTS = {
    "revenue": ["매출액", "수익(매출액)", "영업수익"],
    "operating": ["영업이익", "영업이익(손실)", "영업손익"],
    "net": ["당기순이익(손실)", "당기순이익", "연결당기순이익"],
}


def parse_finance(rows: list[dict[str, Any]], bsns_year: int) -> dict[str, Any] | None:
    """fnlttSinglAcnt 응답 → {"year", "basis": 연결|별도, "rcept_no", "years": [{"year", "revenue", "operating", "net"}]}.
    연결재무제표가 있으면 연결, 없으면 별도. 오래된 해부터."""
    if not rows:
        return None
    cfs = [r for r in rows if r.get("fs_div") == "CFS"]
    use = cfs or [r for r in rows if r.get("fs_div") == "OFS"] or rows
    by_name = {}
    for r in use:
        by_name.setdefault((r.get("account_nm") or "").replace(" ", ""), r)
    years: dict[int, dict[str, int | None]] = {}
    terms = [("bfefrmtrm", bsns_year - 2), ("frmtrm", bsns_year - 1), ("thstrm", bsns_year)]
    revenue_name = None
    for field, names in ACCOUNTS.items():
        name = next((n for n in names if n.replace(" ", "") in by_name), None)
        if not name:
            continue
        r = by_name[name.replace(" ", "")]
        if field == "revenue":
            revenue_name = "영업수익" if name == "영업수익" else "매출액"
        for term, y in terms:
            years.setdefault(y, {"year": y})[field] = _amount(r.get(f"{term}_amount"))
    rows_out = [years[y] for y in sorted(years) if any(v is not None for k, v in years[y].items() if k != "year")]
    if not rows_out:
        return None
    return {"year": bsns_year, "basis": "연결" if cfs else "별도", "rcept_no": use[0].get("rcept_no"),
            "revenue_name": revenue_name, "years": rows_out}


def _number(s: Any) -> float | None:
    """'1,234' → 1234, '16.9년'·'약 16.9' → 16.9, '19년 6개월' → 19.5. 읽을 수 없으면 None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").removeprefix("약").strip()
    if re.fullmatch(r"\d+(\.\d+)?\s*년", t):
        t = t.rstrip("년").strip()
    if not t or t == "-":
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1))
    # '10년 5개월', '10년' 같은 표기
    m = re.fullmatch(r"(?:(\d+)\s*년)?\s*(?:(\d+)\s*개월)?", t)
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) + int(m.group(2) or 0) / 12
    return None


_TOTAL = re.compile(r"(합계|총계|소계|계|전사|전체|.*합계)")


def _employee_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """더할 줄만 고른다. 사업부문 × 성별 줄에 합계 줄(사업부문 "성별합계"·"합계"·"전사"·"전체", 성별 "합계"·"계")이
    섞여 오면 두 번 세지 않게 가장 큰 합계부터 쓴다. 사업부문이 하나뿐이면 그 줄들이 곧 전체다."""
    def sex(r: dict[str, Any]) -> str:
        return (r.get("sexdstn") or "").strip()

    def div(r: dict[str, Any]) -> str:
        return (r.get("fo_bbm") or "").strip()

    single = len({div(r) for r in rows}) == 1
    total_div = [r for r in rows if single or _TOTAL.fullmatch(div(r))]
    grand = [r for r in total_div if _TOTAL.fullmatch(sex(r))]
    if grand:
        return grand
    if total_div:
        return [r for r in total_div if not _TOTAL.fullmatch(sex(r))]
    by_div = [r for r in rows if _TOTAL.fullmatch(sex(r))]
    return by_div or rows


def parse_employees(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """empSttus 응답 → {"count", "tenure"(년), "salary"(원, 1인 평균), "rcept_no", "date"}.
    근속과 급여는 줄마다 적힌 평균을 인원으로 가중 평균한다(급여 평균이 없으면 급여 총액 ÷ 인원)."""
    if not rows:
        return None
    use = _employee_rows(rows)
    count = tenure_sum = tenure_n = avg_sum = avg_n = total_sum = total_n = 0.0
    for r in use:
        n = _number(r.get("sm")) or 0
        count += n
        t = _number(r.get("avrg_cnwk_sdytrn"))
        if t is not None and n:
            tenure_sum += t * n
            tenure_n += n
        avg = _number(r.get("jan_salary_am"))
        if avg is not None and n:
            avg_sum += avg * n
            avg_n += n
        total = _number(r.get("fyer_salary_totamt"))
        if total is not None and n:
            total_sum += total
            total_n += n
    if not count:
        return None
    salary = avg_sum / avg_n if avg_n else (total_sum / total_n if total_n else None)
    return {
        "count": int(round(count)),
        "tenure": round(tenure_sum / tenure_n, 1) if tenure_n else None,
        "salary": int(round(salary)) if salary is not None else None,
        "rcept_no": rows[0].get("rcept_no"),
        "date": rows[0].get("stlm_dt"),
    }


def parse_disclosures(rows: list[dict[str, Any]], skip: list[str], limit: int) -> list[dict[str, str]]:
    """list.json 응답 → [{"date", "title", "rcept_no"}] 최근 순. 정기적인 공시(skip)는 빼고, 같은 접수번호는 하나만.
    제목은 DART 그대로 둔다([기재정정] 같은 머리도). 같은 종류의 다른 공시(공급계약 여러 건)는 따로 남긴다."""
    out = []
    seen = set()
    squash = [s.replace(" ", "") for s in skip]
    for r in sorted(rows, key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""), reverse=True):
        title = re.sub(r"\s+", " ", (r.get("report_nm") or "")).strip()
        no = r.get("rcept_no")
        if not title or any(s in title.replace(" ", "") for s in squash) or (no and no in seen):
            continue
        seen.add(no)
        d = r.get("rcept_dt") or ""
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d, "title": title, "rcept_no": no})
        if len(out) >= limit:
            break
    return out


DISCLOSURES_KEPT = 40  # 회사마다 남길 최근 공시 수(거르기 전)


def pick_disclosures(items: list[dict[str, Any]], skip: list[str], limit: int) -> list[dict[str, Any]]:
    """받아 둔 공시(최근 순)에서 이름에 skip의 말이 든 것을 빼고 limit개."""
    squash = [w.replace(" ", "") for w in skip]
    return [d for d in items if not any(w in (d.get("title") or "").replace(" ", "") for w in squash)][:limit]


def clean_url(raw: Any) -> str | None:
    """기업개황 홈페이지 칸을 쓸 수 있는 주소로. "-", "없음", 주소·우편번호 같은 글은 None.
    실제로 본 값(2026-10-22): "https:///www.nota.ai", "www. eie.co.kr", "주식회사 제이엘티", "13201"."""
    s = re.sub(r"\s+", "", str(raw or ""))
    s = re.sub(r"^https?:/*", "", s, flags=re.IGNORECASE).lstrip("/")
    host, _, rest = s.partition("/")
    if not re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(:\d+)?", host):
        return None
    return f"https://{host.lower()}" + (f"/{rest}" if rest else "")


def parse_company(body: dict[str, Any]) -> dict[str, Any]:
    est = body.get("est_dt") or ""
    url = clean_url(body.get("hm_url"))
    return {
        "name": body.get("corp_name"),
        "stock_code": (body.get("stock_code") or "").strip() or None,
        "market": CORP_CLS.get(body.get("corp_cls") or "", None),
        "ceo": (body.get("ceo_nm") or "").strip() or None,
        "founded": f"{est[:4]}-{est[4:6]}-{est[6:8]}" if len(est) == 8 else None,
        "homepage": url or None,
        "industry_code": body.get("induty_code") or None,
    }


# ---------- 받기 ----------

def annual_year(today: date) -> int:
    """받을 사업보고서 해. 12월 결산 회사는 다음 해 3월 말(연장하면 4월 초)까지 내므로 4월 10일부터 작년, 그 전엔 재작년.
    없으면(013) fetch가 한 해 전 것을 받는다."""
    return today.year - 1 if (today.month, today.day) >= (4, 10) else today.year - 2


MATCH_VERSION = 5  # 잇기 규칙 판. 올리면 다음 실행에서 모든 회사를 다시 잇는다
# 2: 공고 이름의 한글 읽기·괄호 빼기, 지금 상장된 곳 고르기 3: DART 이름의 한글 읽기, 최근 공시를 낸 곳 고르기
# 4: 리뷰(2026-10-22) — 믿기 어려운 대체 이름(_weak) 거르기, 최근 공시로 고르기는 대기업·공기업만, 글자까지 같은 이름 규칙 뺌
# 5: 글자 그대로와 한글 읽기가 다른 회사면 잇지 않음(4의 "글자 그대로 먼저"가 RFHIC를 옛 법인으로 바꿨다)
BASICS_VERSION = 3  # 받아 둔 기본정보 형식. 올리면 다음 실행부터 회사마다 다시 받는다
# 2: 공시를 거르지 않고 40건 3: 영업수익도 매출 자리에(revenue_name). 2에서 매출액이 있던 회사는 다시 받지 않는다


def _upgrade(got: dict[str, Any]) -> None:
    """받아 둔 기본정보를 다시 받지 않고 새 판으로 올릴 수 있으면 올린다(2 → 3: 매출액이 있었거나 실적이 없던 회사)."""
    if got.get("v") == 2:
        fin = got.get("finance")
        if not fin:
            got["v"] = 3
        elif any(y.get("revenue") is not None for y in fin.get("years") or []):
            fin["revenue_name"] = "매출액"
            got["v"] = 3


def fetch(client: Client, corp_code: str, today: date) -> dict[str, Any]:
    cfg = config.load("dart")
    out: dict[str, Any] = {"fetched": today.isoformat(), "v": BASICS_VERSION}
    body = client.json("company.json", {"corp_code": corp_code})
    out["company"] = parse_company(body) if body else None

    year = annual_year(today)
    finance = employees = None
    for y in (year, year - 1):  # 결산이 늦거나 올해 것이 아직 없으면 한 해 전
        fin = client.json("fnlttSinglAcnt.json", {"corp_code": corp_code, "bsns_year": y, "reprt_code": REPORT_ANNUAL})
        finance = parse_finance((fin or {}).get("list") or [], y)
        if finance:
            emp = client.json("empSttus.json", {"corp_code": corp_code, "bsns_year": y, "reprt_code": REPORT_ANNUAL})
            employees = parse_employees((emp or {}).get("list") or [])
            break
    out["finance"] = finance
    out["employees"] = employees

    rows: list[dict[str, Any]] = []
    begin = (today - timedelta(days=cfg.get("disclosure_days", 365))).strftime("%Y%m%d")
    for ty in cfg.get("disclosure_types") or []:
        found = client.json("list.json", {"corp_code": corp_code, "bgn_de": begin, "end_de": today.strftime("%Y%m%d"),
                                          "pblntf_ty": ty, "last_reprt_at": "Y", "page_count": 100})
        rows += (found or {}).get("list") or []
    # 거르기(disclosure_skip)는 화면용 파일을 만들 때 한다(pick_disclosures). 거를 말을 고쳐도 다시 받지 않게 다 둔다
    out["disclosures"] = parse_disclosures(rows, [], DISCLOSURES_KEPT)
    return out


# ---------- 하루 실행 ----------

def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    """다 쓴 뒤 바꿔 넣는다(실행이 중간에 끊겨도 반쯤 쓴 파일이 남지 않게)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def targets(state: dict[str, dict[str, Any]], registry_type: Any) -> list[tuple[str, str]]:
    """오늘 열린 국내 공고의 회사(키, 이름). 대기업·공기업·외국계 먼저, 그다음 공고가 많은 순."""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for r in state.values():
        if r.get("closed_on") or r.get("overseas") or r.get("dup_of"):
            continue
        key = r.get("company_key") or company_key(r.get("company", ""))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        names.setdefault(key, r.get("company", key))
    rank = {"대기업": 0, "공기업·공공기관": 1, "외국계": 2}
    return sorted(((k, names[k]) for k in counts),
                  key=lambda kn: (rank.get(registry_type(kn[0], kn[1]), 3), -counts[kn[0]], kn[0]))


def _override(value: Any, idx: Index, by_code: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """손으로 잇기: 8자리 고유번호, 또는 DART 이름(같은 이름이 하나이거나, 여럿이면 종목코드가 있는 곳이 하나일 때).
    null이면 잇지 않는다. 따옴표 없이 적은 고유번호(00547033)는 YAML이 8진수로 읽어 숫자가 되므로 되돌린다."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        value = format(value, "o").zfill(8)
    v = str(value).strip()
    if re.fullmatch(r"\d{8}", v):
        return by_code.get(v)
    cands = idx.get(company_key(v))
    listed = [c for c in cands if c["stock_code"]]
    return cands[0] if len(cands) == 1 else (listed[0] if len(listed) == 1 else None)


def _resolve(client: Client, key: str, name: str, idx: Index, today: date,
             ctype: str = "그 외") -> tuple[dict[str, str] | None, str]:
    """같은 이름이 여럿일 때 한 번 더 고른다(후보 4곳까지, 요청이 든다).
    1) 종목코드가 있는 후보 중 기업개황상 지금 상장된(corp_cls Y·K·N) 곳이 하나면 그것(합병 전후 삼성물산처럼
       상장 폐지돼도 종목코드는 남는다).
    2) 대기업·공기업만: 최근 400일 안에 공시를 낸 곳이 하나면 그것(CJ올리브영처럼 없어진 옛 법인을 거른다).
       일반 회사는 짧은 이름이 겹치는 일이 많아(일동홀딩스 공고 → 아파트 관리 회사 "일동") 쓰지 않는다."""
    cands, how = idx.find(key, name)
    if _weak(name, ctype, how):
        cands = [c for c in cands if c["stock_code"]]
    listed = [c for c in cands if c["stock_code"]]
    if 1 < len(listed) <= 4:
        now = [c for c in listed
               if (client.json("company.json", {"corp_code": c["corp_code"]}) or {}).get("corp_cls") in ("Y", "K", "N")]
        if len(now) == 1:
            return now[0], "listed_now"
    if ctype in BIG and 1 < len(cands) <= 4:
        begin = (today - timedelta(days=400)).strftime("%Y%m%d")
        active = [c for c in cands
                  if client.json("list.json", {"corp_code": c["corp_code"], "bgn_de": begin,
                                               "end_de": today.strftime("%Y%m%d"), "page_count": 1})]
        if len(active) == 1:
            return active[0], "active"
    return None, "ambiguous"


def run(data_dir: Path, today: date, budget: int | None = None, session: requests.Session | None = None,
        raw: int = 0, minutes: float | None = None, find: list[str] | None = None,
        cache: Path | None = None) -> dict[str, Any]:
    """find: 고유번호 파일에서 이 말이 들어간 회사 이름을 로그에 남긴다(못 이은 회사를 손으로 이을 때).
    cache: 고유번호 파일을 받아 두는 폴더(비우면 환경 변수 DART_CACHE)."""
    from .companies import CompanyRegistry
    from .store import Store

    cfg = config.load("dart")
    started = time.monotonic()
    if cache is None and os.environ.get("DART_CACHE"):
        cache = Path(os.environ["DART_CACHE"])
    client = Client(budget if budget is not None else cfg.get("budget", 800), cfg.get("interval", 0.2), session, raw,
                    minutes if minutes is not None else cfg.get("max_minutes"))
    corps_path = data_dir / "dart" / "corps.json"
    basics_path = data_dir / "dart" / "basics.json"
    corps: dict[str, Any] = _load(corps_path)
    basics: dict[str, Any] = _load(basics_path)
    store = Store(data_dir)
    registry = CompanyRegistry(data_dir / "companies.json")
    todo = targets(store.state, lambda k, n: registry.company_type(k, n).value)
    overrides: dict[str, Any] = cfg.get("overrides") or {}
    summary: dict[str, Any] = {"companies": len(todo), "matched_new": 0, "unmatched_new": 0, "fetched": 0,
                               "failed": 0, "stopped": None}
    day = today.isoformat()
    retry = timedelta(days=cfg.get("retry_unmatched_days", 30))

    def due_match(key: str) -> bool:
        m = corps.get(key)
        if key in overrides:
            return not m or m.get("how") != "override" or m.get("override") != overrides[key]
        if m and m.get("how") == "override":
            return True  # 손으로 잇기를 지웠으면 규칙으로 다시 잇는다
        return (not m or m.get("mv") != MATCH_VERSION
                or (not m.get("corp_code") and date.fromisoformat(m["checked"]) + retry <= today))

    try:
        need = [(k, n) for k, n in todo if due_match(k)]
        if need or find:
            corps_all = corp_codes(client, cache, today)
            idx = index(corps_all)
            by_code = {c["corp_code"]: c for c in corps_all}
            for word in find or []:
                hits = [c for c in corps_all if word.replace(" ", "").lower() in c["corp_name"].replace(" ", "").lower()]
                log.info("DART 이름 찾기 %r: %d곳 %s", word, len(hits),
                         [(c["corp_name"], c["corp_code"], c["stock_code"]) for c in hits[:15]])
            for key, name in need:
                ctype = registry.company_type(key, name).value
                if key in overrides:
                    c = _override(overrides[key], idx, by_code)
                    how = "override" if c else "none"
                    if not c:
                        log.warning("DART 손으로 잇기가 안 됨: %s → %r(고유번호는 따옴표로, 이름은 같은 이름이 하나여야)",
                                    key, overrides[key])
                else:
                    c, how = match(key, name, idx, ctype)
                    if how == "ambiguous":
                        try:
                            c, how = _resolve(client, key, name, idx, today, ctype)
                        except LimitReached:
                            raise
                        except DartError as e:
                            # 한 회사에서 난 오류로 그날 전체가 멈추지 않게
                            summary["failed"] += 1
                            log.warning("DART 같은 이름 고르기 %s: %s", key, e)
                if c:
                    corps[key] = {"corp_code": c["corp_code"], "corp_name": c["corp_name"],
                                  "stock_code": c["stock_code"] or None, "how": how, "checked": day, "mv": MATCH_VERSION}
                    if how == "override":
                        corps[key]["override"] = overrides[key]
                    summary["matched_new"] += 1
                else:
                    corps[key] = {"corp_code": None, "why": how, "checked": day, "mv": MATCH_VERSION}
                    summary["unmatched_new"] += 1

        for got in basics.values():
            _upgrade(got)
        refresh = timedelta(days=cfg.get("refresh_days", 30))
        seen: set[str] = set()
        for key, _ in todo:
            code = (corps.get(key) or {}).get("corp_code")
            if not code or code in seen:
                continue
            seen.add(code)
            got = basics.get(code)
            if got and got.get("v") == BASICS_VERSION and date.fromisoformat(got["fetched"]) + refresh > today:
                continue
            try:
                basics[code] = fetch(client, code, today)
                summary["fetched"] += 1
            except DartError as e:
                if isinstance(e, LimitReached):
                    raise
                summary["failed"] += 1
                log.warning("DART %s(%s): %s", key, code, e)
                if summary["failed"] >= 20:
                    summary["stopped"] = "실패가 많아 멈춤"
                    break
    except Client.Budget:
        summary["stopped"] = "오늘 요청 수나 시간을 다 씀"
    except LimitReached as e:
        summary["stopped"] = str(e)
    except DartError as e:
        # 고유번호 파일을 못 받은 날: 이미 이은 회사는 그대로 두고 멈춘다
        summary["stopped"] = str(e)
    finally:
        _save(corps_path, corps)
        _save(basics_path, basics)
    linked = [k for k, _ in todo if (corps.get(k) or {}).get("corp_code")]
    summary.update({
        "requests": client.used,
        "seconds": round(time.monotonic() - started),
        "linked": len(linked),
        "with_basics": sum(1 for k in linked if corps[k]["corp_code"] in basics),
    })
    return summary
