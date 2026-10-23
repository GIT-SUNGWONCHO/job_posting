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
    """화면에 보여줄 보통 부르는 이름. 별칭(config/company_aliases.yaml)에 있으면 그 이름(케이티 → KT), 아니면 clean_company."""
    cleaned = clean_company(name)
    compact = PUNCT.sub("", cleaned)
    for raw, canon in config.load("company_aliases").get("aliases", {}).items():
        if compact == PUNCT.sub("", raw):
            return canon
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
