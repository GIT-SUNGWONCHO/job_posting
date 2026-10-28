"""회사 이름, 경력, 마감일을 공통 형식으로 바꾼다. 표기는 docs/glossary.md를 따른다."""

from __future__ import annotations

import re
from datetime import date

from . import config
from .models import DeadlineType

_LEGAL_FORMS = re.compile(
    r"\(\s*(주|유|재|사|합|株)\s*\)|㈜|주식회사|유한회사|유한책임회사|재단법인|사단법인|"
    r"\b(inc|corp|co|ltd|llc|limited|corporation|company)\b\.?",
    re.IGNORECASE,
)
PUNCT = re.compile(r"[\s\.\,\-_·&'\"/()\[\]]+")


def clean_company(name: str) -> str:
    """화면에 보여줄 회사 이름. 법인 표기만 지운다."""
    s = _LEGAL_FORMS.sub(" ", name or "")
    s = re.sub(r"\s+", " ", s).strip(" ,.")
    return s or (name or "").strip()


def common_name(name: str) -> str:
    """화면에 보여줄 보통 부르는 이름. 별칭(config/company_aliases.yaml)에 있으면 그 이름(케이티 → KT),
    아니면 그룹 이름 앞부분의 한글 읽기를 영문으로(에스케이온 → SK온, display_prefixes), 그것도 아니면 clean_company."""
    cfg = config.load("company_aliases")
    cleaned = clean_company(name)
    compact = PUNCT.sub("", cleaned)
    for raw, canon in (cfg.get("aliases") or {}).items():
        if compact == PUNCT.sub("", raw):
            return canon
    if cleaned in (cfg.get("display_names") or {}):
        return cfg["display_names"][cleaned]
    for prefix, latin in (cfg.get("display_prefixes") or {}).items():
        if cleaned.startswith(prefix):
            return latin + cleaned[len(prefix):]
    return cleaned


def company_key(name: str) -> str:
    """중복 판단용 회사 키. 법인 표기, 공백, 기호를 지우고 별칭을 적용한다."""
    cleaned = clean_company(name)
    aliases: dict[str, str] = config.load("company_aliases").get("aliases", {})
    compact = PUNCT.sub("", cleaned)
    for raw, canon in aliases.items():
        if compact == PUNCT.sub("", raw):
            compact = PUNCT.sub("", canon)
            break
    return compact.lower()


_LEAD_LEGAL = re.compile(r"^\s*(?:\(\s*주\s*\)|㈜|주식회사)\s*")
_LEAD_GROUP = re.compile(r"^\s*[\[【(]([^\]】)]{1,40})[\]】)]\s*")
_DEADLINE_NOTE = re.compile(r"\s*[(\[]\s*(?:~\s*\d{1,2}\s*[./]\s*\d{1,2}|~?\s*채용\s*시\s*(?:마감|까지)|상시\s*채용)\s*[)\]]")
_TAIL_WORDS = re.compile(
    r"\s*(?:(?:경력|신입)\s*(?:사원|직)?\s*)?(?:인재\s*)?(?:채용\s*공고|모집\s*공고|채용|모집)(?:\s*합니다)?\.?\s*$"
    r"|\s*[을를]\s*모집합니다\.?\s*$"
)
_SEPARATORS = " _-·:|/"


def list_title(title: str, company: str) -> str:
    """목록 제목: 목록에서 보이는 다듬은 제목(규칙만, AI 없음). 원문 제목은 공고 상세에 그대로 둔다.
    앞의 [회사 이름]·회사 이름·(주), 마감 표기((채용 시 마감), (~10/31)), 끝의 '채용'·'채용공고'·'모집'·'경력사원 채용'을 뺀다.
    [팀 이름]처럼 회사 이름이 아닌 묶음은 남긴다. 너무 짧아지면 원문을 쓴다."""
    t = (title or "").strip()
    key = company_key(company) if company else ""
    names = sorted({n for n in (clean_company(company), common_name(company)) if n}, key=len, reverse=True) if company else []
    for _ in range(3):
        before = t
        t = _LEAD_LEGAL.sub("", t)
        m = _LEAD_GROUP.match(t)
        if m and key and company_key(m.group(1)) == key:
            t = t[m.end():]
        for name in names:
            # 회사 이름 바로 뒤가 띄어쓰기·기호·(주)일 때만 뺀다(카카오 공고의 "카카오페이"를 자르지 않게)
            rest = t[len(name):] if t.startswith(name) else None
            if rest is not None and (not rest or rest[0] in _SEPARATORS or rest.lstrip().startswith(("(주)", "㈜"))):
                t = _LEAD_LEGAL.sub("", rest.lstrip(_SEPARATORS))
                break
        if t == before:
            break
    t = _DEADLINE_NOTE.sub("", t)
    for _ in range(2):
        shorter = _TAIL_WORDS.sub("", t).rstrip(_SEPARATORS + ",")
        if shorter == t or len(shorter) < 4:
            break
        t = shorter
    t = re.sub(r"\s{2,}", " ", t).strip(_SEPARATORS)
    return t if len(t) >= 4 else (title or "").strip()


def career_text(career_min: int | None, career_max: int | None) -> str:
    """경력 표기. 예: 경력 1~10년, 경력 8년 이상, 경력 5년 이하, 연차 무관, 신입."""
    if career_max == 0:
        return "신입"
    lo = career_min if career_min else None
    hi = career_max
    if lo is None and hi is None:
        return "연차 무관"
    if lo is not None and hi is None:
        return f"경력 {lo}년 이상"
    if lo is None and hi is not None:
        return f"경력 {hi}년 이하"
    if lo == hi:
        return f"경력 {lo}년"
    return f"경력 {lo}~{hi}년"


def deadline_text(deadline_type: DeadlineType, deadline: date | None, today: date) -> str:
    """마감 표기. 예: D-12, D-day, 상시, 마감."""
    if deadline_type is not DeadlineType.DATE or deadline is None:
        return "상시"
    days = (deadline - today).days
    if days < 0:
        return "마감"
    if days == 0:
        return "D-day"
    return f"D-{days}"
