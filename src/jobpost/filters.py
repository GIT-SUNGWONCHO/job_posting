"""개인 필터(1차 필터). 저장된 공고는 그대로 두고 보는 목록에서만 거른다."""

from __future__ import annotations

from typing import Any

from .models import CompanyType


def passes(
    *,
    title: str,
    company: str,
    company_type: CompanyType,
    career_min: int | None,
    career_max: int | None,
    regions: list[str],
    filters: dict[str, Any],
    job_type: str | None = None,
) -> tuple[bool, str | None]:
    """(통과 여부, 걸린 이유)."""
    for kw in filters.get("exclude_keywords") or []:
        if kw.replace(" ", "") in title.replace(" ", ""):
            return False, f"제외 키워드: {kw}"
    for c in filters.get("exclude_companies") or []:
        if c and c in company:
            return False, f"제외 회사: {c}"
    if any(c and c in company for c in filters.get("always_companies") or []):
        return True, None

    # 직무 유형이 아직 분류되지 않은 공고(오늘 새로 들어와 AI가 못 본 것)는 통과시킨다
    allowed_jobs = filters.get("job_types")
    if allowed_jobs and job_type and job_type not in allowed_jobs:
        return False, f"직무 유형: {job_type}"

    allowed_types = filters.get("company_types")
    if allowed_types and company_type.value not in allowed_types:
        return False, f"기업 구분: {company_type.value}"

    career = filters.get("career") or {}
    fmin, fmax = career.get("min"), career.get("max")
    if fmin is not None or fmax is not None:
        lo = career_min or 0
        hi = career_max if career_max is not None else 99
        if fmin is not None and hi < fmin:
            return False, "경력 범위"
        if fmax is not None and lo > fmax:
            return False, "경력 범위"

    allowed_regions = filters.get("regions")
    if allowed_regions and regions:
        remote_ok = "원격" in allowed_regions and any(w in title for w in ("재택", "원격", "리모트"))
        if not remote_ok and not any(any(a in r for a in allowed_regions) for r in regions):
            return False, "지역"
    return True, None
